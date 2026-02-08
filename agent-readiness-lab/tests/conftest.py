"""Pytest configuration and fixtures."""

import os
import sys

# Add packages to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages"))

import pytest


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    from arlab.traces import Session, Step, ActionType

    return Session(
        session_id="sample_001",
        goal="Sample test session",
        start_url="http://example.com",
        steps=[
            Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
            Step(ts=1, action=ActionType.CLICK, selector="#login"),
            Step(ts=2, action=ActionType.TYPE, selector="#username", text="testuser"),
            Step(ts=3, action=ActionType.TYPE, selector="#password", text="password"),
            Step(ts=4, action=ActionType.CLICK, selector="#submit"),
        ],
    )


@pytest.fixture
def sample_trace_content():
    """Create sample trace JSONL content."""
    return '''{"session_id": "sample_trace", "goal": "Test login flow", "start_url": "http://example.com"}
{"ts": 0, "action": "goto", "url": "http://example.com/login"}
{"ts": 1, "action": "type", "selector": "#username", "text": "user"}
{"ts": 2, "action": "type", "selector": "#password", "text": "pass"}
{"ts": 3, "action": "click", "selector": "#submit"}'''
