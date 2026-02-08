"""Metrics calculation for evaluation runs."""

from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass
class SessionMetrics:
    """Metrics for a single session."""
    session_id: str
    success: bool
    duration_ms: float
    step_count: int
    error_count: int
    blocked_action_count: int
    recovery_count: int
    abandoned: bool


@dataclass
class RunMetrics:
    """Aggregated metrics for an evaluation run."""
    total_sessions: int
    successful_sessions: int
    failed_sessions: int
    success_rate: float
    median_time_to_complete: float
    error_recovery_rate: float
    harmful_action_blocks: int
    total_tool_calls: int
    abandonment_rate: float

    # Detailed breakdowns
    session_metrics: list[SessionMetrics]
    failure_reasons: dict[str, int]


def calculate_session_metrics(session_data: dict) -> SessionMetrics:
    """Calculate metrics for a single session.

    Args:
        session_data: Dict with session execution data including events

    Returns:
        SessionMetrics object
    """
    events = session_data.get("events", [])
    success = session_data.get("success", False)
    duration_ms = session_data.get("duration_ms", 0)
    abandoned = session_data.get("abandoned", False)

    error_count = 0
    blocked_count = 0
    recovery_count = 0

    prev_was_error = False
    for event in events:
        result = event.get("result", "")
        error = event.get("error")

        if result == "failure" or error:
            error_count += 1
            prev_was_error = True
        elif result == "blocked":
            blocked_count += 1
        elif result == "success" and prev_was_error:
            recovery_count += 1
            prev_was_error = False
        else:
            prev_was_error = False

    return SessionMetrics(
        session_id=session_data.get("session_id", "unknown"),
        success=success,
        duration_ms=duration_ms,
        step_count=len(events),
        error_count=error_count,
        blocked_action_count=blocked_count,
        recovery_count=recovery_count,
        abandoned=abandoned,
    )


def calculate_run_metrics(sessions: list[dict]) -> RunMetrics:
    """Calculate aggregated metrics for a run.

    Args:
        sessions: List of session execution data dicts

    Returns:
        RunMetrics object with aggregated metrics
    """
    session_metrics_list: list[SessionMetrics] = []
    failure_reasons: dict[str, int] = {}

    for session_data in sessions:
        metrics = calculate_session_metrics(session_data)
        session_metrics_list.append(metrics)

        if not metrics.success and session_data.get("error_message"):
            reason = _categorize_error(session_data["error_message"])
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    total_sessions = len(session_metrics_list)
    if total_sessions == 0:
        return RunMetrics(
            total_sessions=0,
            successful_sessions=0,
            failed_sessions=0,
            success_rate=0.0,
            median_time_to_complete=0.0,
            error_recovery_rate=0.0,
            harmful_action_blocks=0,
            total_tool_calls=0,
            abandonment_rate=0.0,
            session_metrics=[],
            failure_reasons={},
        )

    successful = [m for m in session_metrics_list if m.success]
    failed = [m for m in session_metrics_list if not m.success]
    abandoned = [m for m in session_metrics_list if m.abandoned]

    # Calculate success rate
    success_rate = len(successful) / total_sessions

    # Calculate median time to complete (successful sessions only)
    if successful:
        completion_times = [m.duration_ms for m in successful]
        median_time = median(completion_times)
    else:
        median_time = 0.0

    # Calculate error recovery rate
    total_errors = sum(m.error_count for m in session_metrics_list)
    total_recoveries = sum(m.recovery_count for m in session_metrics_list)
    if total_errors > 0:
        error_recovery_rate = total_recoveries / total_errors
    else:
        error_recovery_rate = 1.0  # No errors = perfect recovery

    # Calculate harmful action blocks
    harmful_blocks = sum(m.blocked_action_count for m in session_metrics_list)

    # Calculate total tool calls
    total_tool_calls = sum(m.step_count for m in session_metrics_list)

    # Calculate abandonment rate
    abandonment_rate = len(abandoned) / total_sessions if total_sessions > 0 else 0.0

    return RunMetrics(
        total_sessions=total_sessions,
        successful_sessions=len(successful),
        failed_sessions=len(failed),
        success_rate=success_rate,
        median_time_to_complete=median_time,
        error_recovery_rate=error_recovery_rate,
        harmful_action_blocks=harmful_blocks,
        total_tool_calls=total_tool_calls,
        abandonment_rate=abandonment_rate,
        session_metrics=session_metrics_list,
        failure_reasons=failure_reasons,
    )


def _categorize_error(error_message: str) -> str:
    """Categorize an error message into a failure reason."""
    error_lower = error_message.lower()

    if "timeout" in error_lower:
        return "timeout"
    elif "selector" in error_lower or "element" in error_lower:
        return "element_not_found"
    elif "network" in error_lower or "connection" in error_lower:
        return "network_error"
    elif "500" in error_lower or "internal" in error_lower:
        return "server_error"
    elif "blocked" in error_lower:
        return "action_blocked"
    elif "navigation" in error_lower:
        return "navigation_error"
    else:
        return "other"


def metrics_to_dict(metrics: RunMetrics) -> dict:
    """Convert RunMetrics to a JSON-serializable dict."""
    return {
        "total_sessions": metrics.total_sessions,
        "successful_sessions": metrics.successful_sessions,
        "failed_sessions": metrics.failed_sessions,
        "success_rate": round(metrics.success_rate, 4),
        "median_time_to_complete_ms": round(metrics.median_time_to_complete, 2),
        "error_recovery_rate": round(metrics.error_recovery_rate, 4),
        "harmful_action_blocks": metrics.harmful_action_blocks,
        "total_tool_calls": metrics.total_tool_calls,
        "abandonment_rate": round(metrics.abandonment_rate, 4),
        "failure_reasons": metrics.failure_reasons,
        "sessions": [
            {
                "session_id": m.session_id,
                "success": m.success,
                "duration_ms": round(m.duration_ms, 2),
                "step_count": m.step_count,
                "error_count": m.error_count,
                "blocked_action_count": m.blocked_action_count,
                "recovery_count": m.recovery_count,
                "abandoned": m.abandoned,
            }
            for m in metrics.session_metrics
        ],
    }
