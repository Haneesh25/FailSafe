"""Tests for scoring and metrics."""

import pytest

import sys
sys.path.insert(0, "packages")

from arlab.scoring import (
    calculate_run_metrics,
    calculate_session_metrics,
    SessionMetrics,
    RunMetrics,
)
from arlab.scoring.metrics import metrics_to_dict


class TestSessionMetrics:
    """Tests for session metrics calculation."""

    def test_successful_session(self):
        """Test metrics for a successful session."""
        session_data = {
            "session_id": "test_001",
            "success": True,
            "duration_ms": 5000,
            "events": [
                {"result": "success"},
                {"result": "success"},
                {"result": "success"},
            ],
        }

        metrics = calculate_session_metrics(session_data)

        assert metrics.success is True
        assert metrics.duration_ms == 5000
        assert metrics.step_count == 3
        assert metrics.error_count == 0

    def test_failed_session(self):
        """Test metrics for a failed session."""
        session_data = {
            "session_id": "test_002",
            "success": False,
            "duration_ms": 3000,
            "events": [
                {"result": "success"},
                {"result": "failure", "error": "Element not found"},
            ],
        }

        metrics = calculate_session_metrics(session_data)

        assert metrics.success is False
        assert metrics.error_count == 1

    def test_session_with_recovery(self):
        """Test metrics for session with error recovery."""
        session_data = {
            "session_id": "test_003",
            "success": True,
            "duration_ms": 8000,
            "events": [
                {"result": "success", "step_index": 0},
                {"result": "failure", "error": "Timeout", "step_index": 1},
                {"result": "success", "step_index": 2},  # Recovery
                {"result": "success", "step_index": 3},
            ],
        }

        metrics = calculate_session_metrics(session_data)

        assert metrics.error_count == 1
        assert metrics.recovery_count == 1

    def test_session_with_blocked_actions(self):
        """Test metrics for session with blocked actions."""
        session_data = {
            "session_id": "test_004",
            "success": False,
            "duration_ms": 2000,
            "events": [
                {"result": "success"},
                {"result": "blocked"},
                {"result": "blocked"},
            ],
        }

        metrics = calculate_session_metrics(session_data)

        assert metrics.blocked_action_count == 2

    def test_abandoned_session(self):
        """Test metrics for abandoned session."""
        session_data = {
            "session_id": "test_005",
            "success": False,
            "abandoned": True,
            "duration_ms": 1500,
            "events": [
                {"result": "success"},
            ],
        }

        metrics = calculate_session_metrics(session_data)

        assert metrics.abandoned is True


class TestRunMetrics:
    """Tests for run metrics aggregation."""

    def test_all_successful(self):
        """Test metrics when all sessions succeed."""
        sessions = [
            {"session_id": "s1", "success": True, "duration_ms": 1000, "events": []},
            {"session_id": "s2", "success": True, "duration_ms": 2000, "events": []},
            {"session_id": "s3", "success": True, "duration_ms": 1500, "events": []},
        ]

        metrics = calculate_run_metrics(sessions)

        assert metrics.total_sessions == 3
        assert metrics.successful_sessions == 3
        assert metrics.failed_sessions == 0
        assert metrics.success_rate == 1.0

    def test_mixed_results(self):
        """Test metrics with mixed success/failure."""
        sessions = [
            {"session_id": "s1", "success": True, "duration_ms": 1000, "events": []},
            {"session_id": "s2", "success": False, "duration_ms": 500, "error_message": "Timeout", "events": []},
            {"session_id": "s3", "success": True, "duration_ms": 2000, "events": []},
            {"session_id": "s4", "success": False, "duration_ms": 300, "error_message": "Element not found", "events": []},
        ]

        metrics = calculate_run_metrics(sessions)

        assert metrics.total_sessions == 4
        assert metrics.successful_sessions == 2
        assert metrics.failed_sessions == 2
        assert metrics.success_rate == 0.5

    def test_median_time(self):
        """Test median time calculation."""
        sessions = [
            {"session_id": "s1", "success": True, "duration_ms": 1000, "events": []},
            {"session_id": "s2", "success": True, "duration_ms": 3000, "events": []},
            {"session_id": "s3", "success": True, "duration_ms": 2000, "events": []},
        ]

        metrics = calculate_run_metrics(sessions)

        assert metrics.median_time_to_complete == 2000  # Middle value

    def test_error_recovery_rate(self):
        """Test error recovery rate calculation."""
        sessions = [
            {
                "session_id": "s1",
                "success": True,
                "duration_ms": 1000,
                "events": [
                    {"result": "failure"},
                    {"result": "success"},  # Recovery
                ],
            },
            {
                "session_id": "s2",
                "success": False,
                "duration_ms": 500,
                "events": [
                    {"result": "failure"},
                    {"result": "failure"},  # No recovery
                ],
            },
        ]

        metrics = calculate_run_metrics(sessions)

        # 1 recovery out of 3 errors
        assert metrics.error_recovery_rate == pytest.approx(1/3)

    def test_abandonment_rate(self):
        """Test abandonment rate calculation."""
        sessions = [
            {"session_id": "s1", "success": True, "abandoned": False, "duration_ms": 1000, "events": []},
            {"session_id": "s2", "success": False, "abandoned": True, "duration_ms": 500, "events": []},
            {"session_id": "s3", "success": True, "abandoned": False, "duration_ms": 1500, "events": []},
            {"session_id": "s4", "success": False, "abandoned": True, "duration_ms": 200, "events": []},
        ]

        metrics = calculate_run_metrics(sessions)

        assert metrics.abandonment_rate == 0.5  # 2 out of 4

    def test_empty_sessions(self):
        """Test metrics with no sessions."""
        metrics = calculate_run_metrics([])

        assert metrics.total_sessions == 0
        assert metrics.success_rate == 0.0
        assert metrics.median_time_to_complete == 0.0

    def test_failure_reasons(self):
        """Test failure reason categorization."""
        sessions = [
            {"session_id": "s1", "success": False, "error_message": "Timeout waiting for element", "events": []},
            {"session_id": "s2", "success": False, "error_message": "Element not found: #button", "events": []},
            {"session_id": "s3", "success": False, "error_message": "Server returned 500", "events": []},
        ]

        metrics = calculate_run_metrics(sessions)

        assert "timeout" in metrics.failure_reasons
        assert "element_not_found" in metrics.failure_reasons
        assert "server_error" in metrics.failure_reasons


class TestMetricsSerialization:
    """Tests for metrics serialization."""

    def test_metrics_to_dict(self):
        """Test converting metrics to dict."""
        sessions = [
            {"session_id": "s1", "success": True, "duration_ms": 1000, "events": []},
            {"session_id": "s2", "success": False, "duration_ms": 500, "events": []},
        ]

        metrics = calculate_run_metrics(sessions)
        result = metrics_to_dict(metrics)

        assert "total_sessions" in result
        assert "success_rate" in result
        assert "sessions" in result
        assert len(result["sessions"]) == 2
        assert isinstance(result["success_rate"], float)

    def test_metrics_dict_roundable(self):
        """Test that metric values are properly rounded."""
        sessions = [
            {"session_id": "s1", "success": True, "duration_ms": 1234.5678, "events": []},
        ]

        metrics = calculate_run_metrics(sessions)
        result = metrics_to_dict(metrics)

        # Check that duration is rounded
        assert result["sessions"][0]["duration_ms"] == 1234.57
