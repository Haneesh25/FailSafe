"""Constrained tool API for agents."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable
import re


class ToolResultStatus(str, Enum):
    """Status of a tool execution."""
    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"


@dataclass
class ToolResult:
    """Result of executing a tool."""
    status: ToolResultStatus
    data: Any = None
    error: str | None = None
    screenshot_path: str | None = None


@dataclass
class Tool:
    """Definition of an available tool."""
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Awaitable[ToolResult]] | None = None


# Blocked patterns for security
BLOCKED_SELECTORS = [
    r".*eval\s*\(.*",
    r".*javascript:.*",
    r".*<script.*",
]

BLOCKED_URLS = [
    r"^file://.*",
    r"^javascript:.*",
    r".*\.\..*",
]

BLOCKED_TEXT_PATTERNS = [
    r".*<script.*",
    r".*javascript:.*",
    r".*on\w+\s*=.*",
]


def is_selector_safe(selector: str) -> bool:
    """Check if a selector is safe to use."""
    for pattern in BLOCKED_SELECTORS:
        if re.match(pattern, selector, re.IGNORECASE):
            return False
    return True


def is_url_safe(url: str) -> bool:
    """Check if a URL is safe to navigate to."""
    for pattern in BLOCKED_URLS:
        if re.match(pattern, url, re.IGNORECASE):
            return False
    return True


def is_text_safe(text: str) -> bool:
    """Check if text is safe to type."""
    for pattern in BLOCKED_TEXT_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return False
    return True


class ToolRegistry:
    """Registry of available tools with security constraints."""

    AVAILABLE_TOOLS: list[Tool] = [
        Tool(
            name="click",
            description="Click on an element identified by selector",
            parameters={
                "selector": {"type": "string", "description": "CSS selector for the element"}
            }
        ),
        Tool(
            name="type",
            description="Type text into an input element",
            parameters={
                "selector": {"type": "string", "description": "CSS selector for the input"},
                "text": {"type": "string", "description": "Text to type"}
            }
        ),
        Tool(
            name="goto",
            description="Navigate to a URL",
            parameters={
                "url": {"type": "string", "description": "URL to navigate to"}
            }
        ),
        Tool(
            name="wait",
            description="Wait for a specified duration",
            parameters={
                "ms": {"type": "integer", "description": "Milliseconds to wait (max 10000)"}
            }
        ),
        Tool(
            name="read_dom",
            description="Read simplified DOM structure with key elements",
            parameters={}
        ),
        Tool(
            name="screenshot",
            description="Take a screenshot of the current page",
            parameters={}
        ),
        Tool(
            name="add_to_cart",
            description="Add an item to cart (domain action)",
            parameters={
                "item_id": {"type": "string", "description": "ID of the item to add"}
            }
        ),
        Tool(
            name="submit",
            description="Submit a form",
            parameters={
                "selector": {"type": "string", "description": "CSS selector for the form or submit button"}
            }
        ),
        Tool(
            name="select",
            description="Select an option from a dropdown",
            parameters={
                "selector": {"type": "string", "description": "CSS selector for the select element"},
                "value": {"type": "string", "description": "Value to select"}
            }
        ),
        Tool(
            name="back",
            description="Navigate back in browser history",
            parameters={}
        ),
        Tool(
            name="refresh",
            description="Refresh the current page",
            parameters={}
        ),
    ]

    def __init__(self):
        self._tools = {tool.name: tool for tool in self.AVAILABLE_TOOLS}

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """List all available tools."""
        return list(self._tools.values())

    def validate_action(self, action: str, args: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate an action and its arguments.

        Returns (is_valid, error_message).
        """
        tool = self.get_tool(action)
        if tool is None:
            return False, f"Unknown tool: {action}"

        # Validate selector safety
        if "selector" in args:
            selector = args["selector"]
            if not isinstance(selector, str):
                return False, "Selector must be a string"
            if not is_selector_safe(selector):
                return False, f"Blocked selector pattern: {selector}"

        # Validate URL safety
        if "url" in args:
            url = args["url"]
            if not isinstance(url, str):
                return False, "URL must be a string"
            if not is_url_safe(url):
                return False, f"Blocked URL pattern: {url}"

        # Validate text safety
        if "text" in args:
            text = args["text"]
            if not isinstance(text, str):
                return False, "Text must be a string"
            if not is_text_safe(text):
                return False, f"Blocked text pattern detected"

        # Validate wait duration
        if action == "wait" and "ms" in args:
            ms = args["ms"]
            if not isinstance(ms, int) or ms < 0 or ms > 10000:
                return False, "Wait duration must be 0-10000ms"

        return True, None

    def get_tools_schema(self) -> list[dict]:
        """Get JSON schema for all tools (OpenAI-compatible format)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": list(tool.parameters.keys())
                }
            }
            for tool in self._tools.values()
        ]
