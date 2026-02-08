"""Parse and serialize trace files in JSONL format."""

import json
from pathlib import Path
from typing import Iterator

from .schema import Session, Step


def parse_trace_lines(lines: Iterator[str]) -> Session:
    """Parse JSONL lines into a Session object.

    Format: First line is session metadata, subsequent lines are steps.
    """
    session_data: dict | None = None
    steps: list[Step] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        data = json.loads(line)

        if session_data is None:
            session_data = data
        else:
            steps.append(Step(**data))

    if session_data is None:
        raise ValueError("Empty trace file - no session metadata found")

    session_data["steps"] = steps
    return Session(**session_data)


def parse_trace_file(path: Path | str) -> Session:
    """Parse a JSONL trace file into a Session object."""
    path = Path(path)

    with path.open("r") as f:
        return parse_trace_lines(iter(f))


def parse_trace_content(content: str) -> Session:
    """Parse JSONL content string into a Session object."""
    return parse_trace_lines(iter(content.strip().split("\n")))


def serialize_session(session: Session) -> str:
    """Serialize a Session to JSONL format."""
    lines = []

    session_meta = session.model_dump(exclude={"steps"})
    session_meta["created_at"] = session_meta["created_at"].isoformat()
    lines.append(json.dumps(session_meta))

    for step in session.steps:
        step_data = step.model_dump(exclude_none=True)
        lines.append(json.dumps(step_data))

    return "\n".join(lines)


def load_trace_set(directory: Path | str) -> list[Session]:
    """Load all trace files from a directory."""
    directory = Path(directory)
    sessions = []

    for path in sorted(directory.glob("*.jsonl")):
        try:
            session = parse_trace_file(path)
            sessions.append(session)
        except Exception as e:
            print(f"Warning: Failed to parse {path}: {e}")

    return sessions
