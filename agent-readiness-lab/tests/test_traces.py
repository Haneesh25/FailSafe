"""Tests for trace parsing."""

import pytest
from datetime import datetime

import sys
sys.path.insert(0, "packages")

from arlab.traces import (
    Session,
    Step,
    ActionType,
    parse_trace_content,
    serialize_session,
)


class TestTraceSchema:
    """Tests for trace schema validation."""

    def test_step_creation(self):
        """Test creating a valid step."""
        step = Step(
            ts=1.0,
            action=ActionType.CLICK,
            selector="[data-testid='button']",
        )
        assert step.ts == 1.0
        assert step.action == ActionType.CLICK
        assert step.selector == "[data-testid='button']"

    def test_step_with_text(self):
        """Test creating a step with text."""
        step = Step(
            ts=2.0,
            action=ActionType.TYPE,
            selector="input",
            text="hello world",
        )
        assert step.text == "hello world"

    def test_session_creation(self):
        """Test creating a valid session."""
        session = Session(
            session_id="test_001",
            goal="Test the login flow",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1, action=ActionType.CLICK, selector="#login"),
            ],
        )
        assert session.session_id == "test_001"
        assert len(session.steps) == 2

    def test_session_total_duration(self):
        """Test session duration calculation."""
        session = Session(
            session_id="test_002",
            goal="Test",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=5.5, action=ActionType.CLICK, selector="#btn"),
            ],
        )
        assert session.total_duration() == 5.5

    def test_empty_session_duration(self):
        """Test empty session has zero duration."""
        session = Session(
            session_id="test_003",
            goal="Empty",
            steps=[],
        )
        assert session.total_duration() == 0.0


class TestTraceParsing:
    """Tests for JSONL trace parsing."""

    def test_parse_simple_trace(self):
        """Test parsing a simple trace."""
        content = '''{"session_id": "test_001", "goal": "Test goal", "start_url": "http://example.com"}
{"ts": 0, "action": "goto", "url": "http://example.com"}
{"ts": 1, "action": "click", "selector": "#button"}'''

        session = parse_trace_content(content)

        assert session.session_id == "test_001"
        assert session.goal == "Test goal"
        assert len(session.steps) == 2
        assert session.steps[0].action == ActionType.GOTO
        assert session.steps[1].action == ActionType.CLICK

    def test_parse_trace_with_expectations(self):
        """Test parsing trace with expectations."""
        content = '''{"session_id": "test_002", "goal": "Test with expect"}
{"ts": 0, "action": "click", "selector": "#submit", "expect": {"url_contains": "/success"}}'''

        session = parse_trace_content(content)

        assert session.steps[0].expect == {"url_contains": "/success"}

    def test_parse_trace_with_metadata(self):
        """Test parsing trace with step metadata."""
        content = '''{"session_id": "test_003", "goal": "Test with metadata"}
{"ts": 0, "action": "wait", "metadata": {"wait_ms": 1000}}'''

        session = parse_trace_content(content)

        assert session.steps[0].metadata == {"wait_ms": 1000}

    def test_parse_empty_trace_raises(self):
        """Test that parsing empty content raises an error."""
        with pytest.raises(ValueError, match="Empty trace file"):
            parse_trace_content("")


class TestTraceSerialization:
    """Tests for trace serialization."""

    def test_serialize_session(self):
        """Test serializing a session to JSONL."""
        session = Session(
            session_id="test_001",
            goal="Test goal",
            start_url="http://example.com",
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1, action=ActionType.CLICK, selector="#btn"),
            ],
        )

        content = serialize_session(session)
        lines = content.strip().split("\n")

        assert len(lines) == 3  # 1 header + 2 steps
        assert '"session_id": "test_001"' in lines[0]
        assert '"action": "goto"' in lines[1]
        assert '"action": "click"' in lines[2]

    def test_roundtrip_serialization(self):
        """Test that serialization and parsing are inverse operations."""
        original = Session(
            session_id="roundtrip_001",
            goal="Test roundtrip",
            start_url="http://example.com",
            tags=["test"],
            steps=[
                Step(ts=0, action=ActionType.GOTO, url="http://example.com"),
                Step(ts=1.5, action=ActionType.TYPE, selector="input", text="hello"),
            ],
        )

        content = serialize_session(original)
        parsed = parse_trace_content(content)

        assert parsed.session_id == original.session_id
        assert parsed.goal == original.goal
        assert len(parsed.steps) == len(original.steps)
        assert parsed.steps[0].action == original.steps[0].action
        assert parsed.steps[1].text == original.steps[1].text
