"""SQLAlchemy database models."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Any
import json

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    ForeignKey,
    Enum,
    Boolean,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class RunMode(str, PyEnum):
    """Mode of evaluation run."""
    REPLAY = "replay"
    AGENT = "agent"


class RunStatus(str, PyEnum):
    """Status of an evaluation run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventResult(str, PyEnum):
    """Result of an event."""
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class TraceRecord(Base):
    """Stored trace in the database."""
    __tablename__ = "traces"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    goal = Column(Text, nullable=False)
    content = Column(Text, nullable=False)  # JSONL content
    step_count = Column(Integer, default=0)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Run(Base):
    """An evaluation run containing multiple sessions."""
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True)
    run_id = Column(String(255), unique=True, nullable=False, index=True)
    mode = Column(Enum(RunMode), nullable=False)
    status = Column(Enum(RunStatus), default=RunStatus.PENDING)
    trace_set = Column(String(255), nullable=True)
    seed = Column(Integer, nullable=True)
    agent_url = Column(String(512), nullable=True)
    total_sessions = Column(Integer, default=0)
    completed_sessions = Column(Integer, default=0)

    # Metrics (computed after completion)
    success_rate = Column(Float, nullable=True)
    median_time_to_complete = Column(Float, nullable=True)
    error_recovery_rate = Column(Float, nullable=True)
    harmful_action_blocks = Column(Integer, default=0)
    tool_call_count = Column(Integer, default=0)
    abandonment_rate = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Config
    config = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)

    # Relationships
    sessions = relationship("SessionRecord", back_populates="run", cascade="all, delete-orphan")


class SessionRecord(Base):
    """Record of a single session execution."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    session_id = Column(String(255), nullable=False, index=True)
    trace_session_id = Column(String(255), nullable=True)  # Original trace ID if replaying
    goal = Column(Text, nullable=True)

    # Status
    status = Column(Enum(RunStatus), default=RunStatus.PENDING)
    success = Column(Boolean, nullable=True)
    abandoned = Column(Boolean, default=False)

    # Metrics
    duration_ms = Column(Float, nullable=True)
    step_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    blocked_action_count = Column(Integer, default=0)
    recovery_count = Column(Integer, default=0)

    # Timestamps
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Mutation info
    was_mutated = Column(Boolean, default=False)
    mutation_summary = Column(JSON, default=dict)

    # Relationships
    run = relationship("Run", back_populates="sessions")
    events = relationship("Event", back_populates="session", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="session", cascade="all, delete-orphan")


class Event(Base):
    """A single event during session execution."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    session_record_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    step_index = Column(Integer, nullable=False)

    # Observation
    url = Column(String(2048), nullable=True)
    page_title = Column(String(512), nullable=True)
    dom_summary = Column(Text, nullable=True)
    visible_elements = Column(JSON, default=list)

    # Action
    action_type = Column(String(50), nullable=True)
    action_selector = Column(String(512), nullable=True)
    action_text = Column(Text, nullable=True)
    action_url = Column(String(2048), nullable=True)
    action_reasoning = Column(Text, nullable=True)

    # Result
    result = Column(Enum(EventResult), default=EventResult.SUCCESS)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, default=0.0)

    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("SessionRecord", back_populates="events")


class Artifact(Base):
    """Artifacts from session execution (screenshots, etc.)."""
    __tablename__ = "artifacts"

    id = Column(Integer, primary_key=True)
    session_record_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    step_index = Column(Integer, nullable=True)
    artifact_type = Column(String(50), nullable=False)  # screenshot, dom_snapshot, etc.
    file_path = Column(String(1024), nullable=False)
    content_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("SessionRecord", back_populates="artifacts")
