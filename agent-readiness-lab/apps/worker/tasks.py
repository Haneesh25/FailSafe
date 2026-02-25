"""Worker tasks for running evaluations."""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure packages are in path
if "/app/packages" not in sys.path:
    sys.path.insert(0, "/app/packages")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from arlab.traces import parse_trace_content, TraceMutator, MutationConfig
from arlab.replayer import PlaywrightReplayer
from arlab.harness import StubAgent, ExternalAgent, AgentHarness
from arlab.scoring import calculate_run_metrics, metrics_to_dict
from arlab.db.models import (
    Base, Run, TraceRecord, SessionRecord, Event, Artifact,
    RunStatus, EventResult
)


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://arlab:arlab@db:5432/arlab"
    )


def get_db_session():
    """Get a database session."""
    engine = create_engine(get_database_url())
    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory()


def run_evaluation(job_data: dict) -> dict:
    """Run an evaluation job.

    Args:
        job_data: Dict with run configuration

    Returns:
        Result dict
    """
    return asyncio.run(_run_evaluation_async(job_data))


async def _run_evaluation_async(job_data: dict) -> dict:
    """Async implementation of evaluation runner."""
    run_id = job_data["run_id"]
    mode = job_data["mode"]
    trace_ids = job_data["trace_ids"]
    runs_per_trace = job_data.get("runs_per_trace", 1)
    seed = job_data.get("seed")
    agent_url = job_data.get("agent_url")
    apply_mutations = job_data.get("apply_mutations", False)

    db = get_db_session()

    # Update run status
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        return {"error": "Run not found"}

    run.status = RunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    # Get traces
    trace_records = db.query(TraceRecord).filter(
        TraceRecord.session_id.in_(trace_ids)
    ).all()

    # Setup mutator if needed
    mutator = None
    if apply_mutations and seed is not None:
        mutator = TraceMutator(seed=seed)

    # Setup screenshot directory
    screenshot_dir = Path("/app/artifacts/screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # Results collection
    session_results = []
    completed = 0

    try:
        async with PlaywrightReplayer(
            headless=True,
            screenshot_dir=str(screenshot_dir),
        ) as replayer:

            for trace_record in trace_records:
                trace_session = parse_trace_content(trace_record.content)

                for run_num in range(runs_per_trace):
                    # Create unique session ID for this run
                    session_id = f"{trace_session.session_id}_{run_num}"

                    # Apply mutations if configured
                    session = trace_session
                    mutation_summary = {}
                    if mutator:
                        session = mutator.mutate(trace_session)
                        mutation_summary = mutator.get_mutation_summary(
                            trace_session, session
                        )

                    # Create session record
                    session_record = SessionRecord(
                        run_id=run.id,
                        session_id=session_id,
                        trace_session_id=trace_session.session_id,
                        goal=trace_session.goal,
                        status=RunStatus.RUNNING,
                        was_mutated=bool(mutator),
                        mutation_summary=mutation_summary,
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(session_record)
                    db.commit()

                    # Run based on mode
                    if mode == "replay":
                        result = await replayer.replay_session(session)
                    else:
                        # Agent mode
                        if agent_url == "stub":
                            agent = StubAgent()
                        else:
                            agent = ExternalAgent(agent_url)

                        result = await replayer.run_agent_session(
                            agent=agent,
                            goal=trace_session.goal,
                            start_url=trace_session.start_url,
                            session_id=session_id,
                        )

                    # Record events
                    events = result.get("events", [])
                    for i, event in enumerate(events):
                        event_record = Event(
                            session_record_id=session_record.id,
                            step_index=i,
                            url=event.get("observation", {}).get("url") if isinstance(event.get("observation"), dict) else None,
                            action_type=event.get("action", {}).get("action") if isinstance(event.get("action"), dict) else event.get("action"),
                            action_selector=event.get("action", {}).get("selector") if isinstance(event.get("action"), dict) else event.get("selector"),
                            result=EventResult.SUCCESS if event.get("result") == "success" else EventResult.FAILURE,
                            error_message=event.get("error"),
                            duration_ms=event.get("duration_ms", 0),
                        )
                        db.add(event_record)

                    # Update session record
                    session_record.status = RunStatus.COMPLETED
                    session_record.success = result.get("success", False)
                    session_record.abandoned = result.get("abandoned", False)
                    session_record.duration_ms = result.get("duration_ms", 0)
                    session_record.step_count = len(events)
                    session_record.error_count = sum(
                        1 for e in events if e.get("error")
                    )
                    session_record.blocked_action_count = sum(
                        1 for e in events if e.get("result") == "blocked"
                    )
                    session_record.recovery_count = sum(
                        1 for e in events if e.get("result") == "success" and e.get("step_index", 0) > 0
                    )
                    session_record.completed_at = datetime.now(timezone.utc)

                    db.commit()

                    # Add to results
                    session_results.append({
                        "session_id": session_id,
                        "success": result.get("success", False),
                        "duration_ms": result.get("duration_ms", 0),
                        "events": events,
                        "abandoned": result.get("abandoned", False),
                        "error_message": result.get("error_message"),
                    })

                    completed += 1
                    run.completed_sessions = completed
                    db.commit()

        # Calculate metrics
        metrics = calculate_run_metrics(session_results)

        # Update run with final metrics
        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        run.success_rate = metrics.success_rate
        run.median_time_to_complete = metrics.median_time_to_complete
        run.error_recovery_rate = metrics.error_recovery_rate
        run.harmful_action_blocks = metrics.harmful_action_blocks
        run.tool_call_count = metrics.total_tool_calls
        run.abandonment_rate = metrics.abandonment_rate

        db.commit()

        return {
            "run_id": run_id,
            "status": "completed",
            "metrics": metrics_to_dict(metrics),
        }

    except Exception as e:
        run.status = RunStatus.FAILED
        run.error_message = str(e)
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        return {
            "run_id": run_id,
            "status": "failed",
            "error": str(e),
        }

    finally:
        db.close()
