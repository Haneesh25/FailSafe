"""Pydantic schemas for trace data."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Types of actions that can be performed."""
    CLICK = "click"
    TYPE = "type"
    GOTO = "goto"
    WAIT = "wait"
    READ_DOM = "read_dom"
    SCREENSHOT = "screenshot"
    ADD_TO_CART = "add_to_cart"
    SUBMIT = "submit"
    SELECT = "select"
    BACK = "back"
    REFRESH = "refresh"


class Step(BaseModel):
    """A single step in a session trace."""
    ts: float = Field(..., description="Timestamp in seconds from session start")
    action: ActionType = Field(..., description="Action type")
    selector: str | None = Field(None, description="CSS selector for the target element")
    text: str | None = Field(None, description="Text to type or value to select")
    url: str | None = Field(None, description="URL for goto actions")
    expect: dict[str, Any] | None = Field(None, description="Expected outcome after action")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Session(BaseModel):
    """A complete session trace."""
    session_id: str = Field(..., description="Unique session identifier")
    goal: str = Field(..., description="Human-readable goal of this session")
    start_url: str = Field(default="http://webapp:3000", description="Starting URL")
    steps: list[Step] = Field(default_factory=list, description="Ordered list of steps")
    expected_outcome: str | None = Field(None, description="Expected final outcome")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def total_duration(self) -> float:
        """Return total duration of the session in seconds."""
        if not self.steps:
            return 0.0
        return self.steps[-1].ts


class TraceSet(BaseModel):
    """A collection of session traces."""
    name: str = Field(..., description="Name of this trace set")
    description: str = Field(default="", description="Description of the trace set")
    sessions: list[Session] = Field(default_factory=list)


class Observation(BaseModel):
    """An observation of the current state."""
    url: str = Field(..., description="Current URL")
    title: str = Field(default="", description="Page title")
    dom_summary: str = Field(default="", description="Simplified DOM representation")
    visible_text: str = Field(default="", description="Visible text on page")
    elements: list[dict[str, Any]] = Field(default_factory=list, description="Key interactive elements")
    screenshot_path: str | None = Field(None, description="Path to screenshot if taken")
    error: str | None = Field(None, description="Any error message displayed")


class AgentAction(BaseModel):
    """An action from an agent."""
    action: ActionType = Field(..., description="Action to perform")
    selector: str | None = Field(None)
    text: str | None = Field(None)
    url: str | None = Field(None)
    wait_ms: int | None = Field(None)
    reasoning: str | None = Field(None, description="Agent's reasoning for this action")


class EventRecord(BaseModel):
    """Record of a single event during execution."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_index: int = Field(..., description="Index of the step")
    observation: Observation | None = Field(None)
    action: AgentAction | None = Field(None)
    result: str = Field(default="pending", description="success, failure, blocked, skipped")
    error_message: str | None = Field(None)
    duration_ms: float = Field(default=0.0)
    screenshot_path: str | None = Field(None)
