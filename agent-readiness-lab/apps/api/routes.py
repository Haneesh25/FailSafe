"""API routes for Agent Readiness Lab."""

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from rq import Queue

from .dependencies import get_db, get_queue

import sys
sys.path.insert(0, "/app/packages")

from arlab.traces import parse_trace_content, serialize_session
from arlab.db.models import Run, TraceRecord, SessionRecord, Event, RunMode, RunStatus
from arlab.scoring.metrics import metrics_to_dict, RunMetrics, SessionMetrics


router = APIRouter()


# Request/Response models
class RunEvalRequest(BaseModel):
    """Request to run an evaluation."""
    mode: str  # "replay" or "agent"
    trace_set: str | None = None
    trace_ids: list[str] | None = None
    runs: int = 1
    seed: int | None = None
    agent_url: str | None = None
    apply_mutations: bool = False


class RunResponse(BaseModel):
    """Response with run information."""
    run_id: str
    status: str
    message: str


class RunStatusResponse(BaseModel):
    """Response with run status and metrics."""
    run_id: str
    status: str
    mode: str
    total_sessions: int
    completed_sessions: int
    metrics: dict | None = None
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


# Routes
@router.post("/ingest_trace", response_model=dict)
async def ingest_trace(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload and ingest a JSONL trace file."""
    content = await file.read()
    content_str = content.decode("utf-8")

    try:
        session = parse_trace_content(content_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid trace format: {str(e)}")

    # Check if already exists
    existing = db.query(TraceRecord).filter(
        TraceRecord.session_id == session.session_id
    ).first()

    if existing:
        # Update existing
        existing.content = content_str
        existing.goal = session.goal
        existing.step_count = len(session.steps)
        existing.tags = session.tags
        existing.updated_at = datetime.utcnow()
        db.commit()
        return {"status": "updated", "session_id": session.session_id}

    # Create new
    trace_record = TraceRecord(
        session_id=session.session_id,
        name=file.filename or session.session_id,
        goal=session.goal,
        content=content_str,
        step_count=len(session.steps),
        tags=session.tags,
    )
    db.add(trace_record)
    db.commit()

    return {"status": "created", "session_id": session.session_id}


@router.post("/run_eval", response_model=RunResponse)
async def run_eval(
    request: RunEvalRequest,
    db: Session = Depends(get_db),
    queue: Queue = Depends(get_queue),
):
    """Start an evaluation run."""
    # Validate mode
    if request.mode not in ("replay", "agent"):
        raise HTTPException(status_code=400, detail="Mode must be 'replay' or 'agent'")

    if request.mode == "agent" and not request.agent_url:
        # Use stub agent if no URL provided
        request.agent_url = "stub"

    # Get traces
    trace_records = []
    if request.trace_ids:
        trace_records = db.query(TraceRecord).filter(
            TraceRecord.session_id.in_(request.trace_ids)
        ).all()
    elif request.trace_set:
        trace_records = db.query(TraceRecord).filter(
            TraceRecord.tags.contains([request.trace_set])
        ).all()
    else:
        # Get all traces
        trace_records = db.query(TraceRecord).all()

    if not trace_records:
        raise HTTPException(status_code=404, detail="No traces found")

    # Create run
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    run = Run(
        run_id=run_id,
        mode=RunMode.REPLAY if request.mode == "replay" else RunMode.AGENT,
        status=RunStatus.PENDING,
        trace_set=request.trace_set,
        seed=request.seed,
        agent_url=request.agent_url,
        total_sessions=len(trace_records) * request.runs,
        config={
            "runs_per_trace": request.runs,
            "apply_mutations": request.apply_mutations,
            "trace_ids": [t.session_id for t in trace_records],
        },
    )
    db.add(run)
    db.commit()

    # Queue the job
    job_data = {
        "run_id": run_id,
        "mode": request.mode,
        "trace_ids": [t.session_id for t in trace_records],
        "runs_per_trace": request.runs,
        "seed": request.seed,
        "agent_url": request.agent_url,
        "apply_mutations": request.apply_mutations,
    }

    queue.enqueue(
        "worker.tasks.run_evaluation",
        job_data,
        job_timeout=3600,  # 1 hour timeout
    )

    return RunResponse(
        run_id=run_id,
        status="queued",
        message=f"Evaluation queued with {len(trace_records)} traces, {request.runs} runs each",
    )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
async def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Get status and metrics for a run."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    metrics = None
    if run.status == RunStatus.COMPLETED:
        metrics = {
            "success_rate": run.success_rate,
            "median_time_to_complete_ms": run.median_time_to_complete,
            "error_recovery_rate": run.error_recovery_rate,
            "harmful_action_blocks": run.harmful_action_blocks,
            "tool_call_count": run.tool_call_count,
            "abandonment_rate": run.abandonment_rate,
        }

    return RunStatusResponse(
        run_id=run.run_id,
        status=run.status.value,
        mode=run.mode.value,
        total_sessions=run.total_sessions,
        completed_sessions=run.completed_sessions,
        metrics=metrics,
        error_message=run.error_message,
        created_at=run.created_at.isoformat(),
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )


@router.get("/runs/{run_id}/report", response_class=HTMLResponse)
async def get_run_report(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Get HTML report for a run."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Get session records
    sessions = db.query(SessionRecord).filter(SessionRecord.run_id == run.id).all()

    # Build HTML report
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Run Report: {run_id}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
            .header {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}
            .metric {{ background: #fff; border: 1px solid #dee2e6; padding: 15px; border-radius: 8px; text-align: center; }}
            .metric-value {{ font-size: 32px; font-weight: bold; color: #007bff; }}
            .metric-label {{ color: #6c757d; font-size: 14px; }}
            .success {{ color: #28a745; }}
            .failure {{ color: #dc3545; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
            th {{ background: #f8f9fa; }}
            .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
            .badge-success {{ background: #d4edda; color: #155724; }}
            .badge-failure {{ background: #f8d7da; color: #721c24; }}
            .badge-pending {{ background: #fff3cd; color: #856404; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Evaluation Report</h1>
            <p><strong>Run ID:</strong> {run_id}</p>
            <p><strong>Mode:</strong> {run.mode.value}</p>
            <p><strong>Status:</strong> <span class="{'success' if run.status == RunStatus.COMPLETED else 'failure'}">{run.status.value}</span></p>
            <p><strong>Created:</strong> {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <h2>Metrics</h2>
        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{run.success_rate * 100 if run.success_rate else 0:.1f}%</div>
                <div class="metric-label">Success Rate</div>
            </div>
            <div class="metric">
                <div class="metric-value">{run.median_time_to_complete / 1000 if run.median_time_to_complete else 0:.2f}s</div>
                <div class="metric-label">Median Time</div>
            </div>
            <div class="metric">
                <div class="metric-value">{run.error_recovery_rate * 100 if run.error_recovery_rate else 0:.1f}%</div>
                <div class="metric-label">Error Recovery</div>
            </div>
            <div class="metric">
                <div class="metric-value">{run.harmful_action_blocks or 0}</div>
                <div class="metric-label">Blocked Actions</div>
            </div>
            <div class="metric">
                <div class="metric-value">{run.tool_call_count or 0}</div>
                <div class="metric-label">Tool Calls</div>
            </div>
            <div class="metric">
                <div class="metric-value">{run.abandonment_rate * 100 if run.abandonment_rate else 0:.1f}%</div>
                <div class="metric-label">Abandonment</div>
            </div>
        </div>

        <h2>Sessions</h2>
        <table>
            <thead>
                <tr>
                    <th>Session ID</th>
                    <th>Goal</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Steps</th>
                    <th>Errors</th>
                </tr>
            </thead>
            <tbody>
    """

    for session in sessions:
        status_class = "success" if session.success else "failure"
        badge_class = f"badge-{status_class}"
        duration = f"{session.duration_ms / 1000:.2f}s" if session.duration_ms else "-"

        html += f"""
                <tr>
                    <td>{session.session_id[:20]}...</td>
                    <td>{session.goal or '-'}</td>
                    <td><span class="badge {badge_class}">{'Success' if session.success else 'Failed'}</span></td>
                    <td>{duration}</td>
                    <td>{session.step_count}</td>
                    <td>{session.error_count}</td>
                </tr>
        """

    html += """
            </tbody>
        </table>

        <div style="margin-top: 40px; color: #6c757d; font-size: 12px;">
            Generated by Agent Readiness Lab
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/runs/{run_id}/json")
async def get_run_json(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Get JSON report for a run."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    sessions = db.query(SessionRecord).filter(SessionRecord.run_id == run.id).all()

    return {
        "run_id": run.run_id,
        "mode": run.mode.value,
        "status": run.status.value,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "metrics": {
            "success_rate": run.success_rate,
            "median_time_to_complete_ms": run.median_time_to_complete,
            "error_recovery_rate": run.error_recovery_rate,
            "harmful_action_blocks": run.harmful_action_blocks,
            "tool_call_count": run.tool_call_count,
            "abandonment_rate": run.abandonment_rate,
        },
        "sessions": [
            {
                "session_id": s.session_id,
                "goal": s.goal,
                "success": s.success,
                "duration_ms": s.duration_ms,
                "step_count": s.step_count,
                "error_count": s.error_count,
                "blocked_action_count": s.blocked_action_count,
                "abandoned": s.abandoned,
            }
            for s in sessions
        ],
    }


@router.get("/traces")
async def list_traces(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """List all ingested traces."""
    traces = db.query(TraceRecord).offset(offset).limit(limit).all()

    return {
        "traces": [
            {
                "session_id": t.session_id,
                "name": t.name,
                "goal": t.goal,
                "step_count": t.step_count,
                "tags": t.tags,
                "created_at": t.created_at.isoformat(),
            }
            for t in traces
        ],
        "count": len(traces),
    }


@router.get("/runs")
async def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List all evaluation runs."""
    runs = db.query(Run).order_by(Run.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "runs": [
            {
                "run_id": r.run_id,
                "mode": r.mode.value,
                "status": r.status.value,
                "total_sessions": r.total_sessions,
                "completed_sessions": r.completed_sessions,
                "success_rate": r.success_rate,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ],
        "count": len(runs),
    }
