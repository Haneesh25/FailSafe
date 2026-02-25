"""Playwright-based session replayer."""

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from ..traces.schema import Session, Step, ActionType, Observation, AgentAction
from ..harness.agent import BaseAgent, AgentContext, AgentHarness
from ..harness.tools import ToolRegistry, ToolResult, ToolResultStatus


@dataclass
class ReplayResult:
    """Result of replaying a session."""
    session_id: str
    success: bool
    steps_completed: int
    total_steps: int
    duration_ms: float
    events: list[dict] = field(default_factory=list)
    error_message: str | None = None
    screenshots: list[str] = field(default_factory=list)
    abandoned: bool = False


class PlaywrightReplayer:
    """Replay session traces using Playwright."""

    def __init__(
        self,
        headless: bool = True,
        screenshot_dir: str | None = None,
        timeout_ms: int = 30000,
        slow_mo: int = 0,
    ):
        self.headless = headless
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        self.timeout_ms = timeout_ms
        self.slow_mo = slow_mo
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.tool_registry = ToolRegistry()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self):
        """Start the browser."""
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)

    async def stop(self):
        """Stop the browser."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    async def replay_session(self, session: Session) -> ReplayResult:
        """Replay a session trace."""
        if not self._page:
            await self.start()

        events: list[dict] = []
        screenshots: list[str] = []
        start_time = datetime.now(timezone.utc)
        steps_completed = 0
        error_message: str | None = None
        success = True
        abandoned = "abandoned" in session.tags

        try:
            # Navigate to start URL
            await self._page.goto(session.start_url)
            await self._page.wait_for_load_state("networkidle")

            for i, step in enumerate(session.steps):
                step_start = datetime.now(timezone.utc)

                # Handle timing (relative delay)
                if i > 0:
                    delay = (step.ts - session.steps[i - 1].ts) * 1000
                    if delay > 0:
                        await asyncio.sleep(min(delay / 1000, 5))  # Cap at 5s

                event = {
                    "step_index": i,
                    "action": step.action.value,
                    "selector": step.selector,
                    "text": step.text,
                    "url": step.url,
                    "result": "pending",
                    "error": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                try:
                    result = await self._execute_step(step, session.session_id, i)
                    event["result"] = result.status.value
                    if result.error:
                        event["error"] = result.error
                    if result.screenshot_path:
                        screenshots.append(result.screenshot_path)
                    steps_completed += 1
                except Exception as e:
                    event["result"] = "failure"
                    event["error"] = str(e)
                    error_message = str(e)

                    # Check if this is a mutation-induced step that we can skip
                    if step.metadata.get("mutation"):
                        event["result"] = "skipped"
                        event["error"] = f"Skipped mutation step: {str(e)}"
                    else:
                        success = False

                event["duration_ms"] = (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
                events.append(event)

                # Check expectations if defined
                if step.expect and success:
                    expect_result = await self._check_expectations(step.expect)
                    if not expect_result:
                        event["result"] = "expectation_failed"
                        success = False

        except Exception as e:
            error_message = str(e)
            success = False

        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - start_time).total_seconds() * 1000

        return ReplayResult(
            session_id=session.session_id,
            success=success,
            steps_completed=steps_completed,
            total_steps=len(session.steps),
            duration_ms=duration_ms,
            events=events,
            error_message=error_message,
            screenshots=screenshots,
            abandoned=abandoned,
        )

    async def _execute_step(self, step: Step, session_id: str, step_index: int) -> ToolResult:
        """Execute a single step."""
        page = self._page
        assert page is not None

        try:
            if step.action == ActionType.CLICK:
                if step.selector:
                    await page.click(step.selector)
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.TYPE:
                if step.selector and step.text:
                    await page.fill(step.selector, step.text)
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.GOTO:
                if step.url:
                    await page.goto(step.url)
                    await page.wait_for_load_state("networkidle")
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.WAIT:
                wait_ms = step.metadata.get("wait_ms", 1000)
                await asyncio.sleep(wait_ms / 1000)
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.SUBMIT:
                if step.selector:
                    await page.click(step.selector)
                    await page.wait_for_load_state("networkidle")
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.SELECT:
                if step.selector and step.text:
                    await page.select_option(step.selector, step.text)
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.BACK:
                await page.go_back()
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.REFRESH:
                await page.reload()
                return ToolResult(status=ToolResultStatus.SUCCESS)

            elif step.action == ActionType.SCREENSHOT:
                screenshot_path = await self._take_screenshot(session_id, step_index)
                return ToolResult(
                    status=ToolResultStatus.SUCCESS,
                    screenshot_path=screenshot_path
                )

            elif step.action == ActionType.READ_DOM:
                dom = await self._read_dom()
                return ToolResult(status=ToolResultStatus.SUCCESS, data=dom)

            elif step.action == ActionType.ADD_TO_CART:
                # Domain action - click add to cart button
                selectors = [
                    '[data-testid="add-to-cart"]',
                    'button:has-text("Add to Cart")',
                    '.add-to-cart',
                ]
                for sel in selectors:
                    try:
                        await page.click(sel, timeout=5000)
                        return ToolResult(status=ToolResultStatus.SUCCESS)
                    except Exception:
                        continue
                return ToolResult(
                    status=ToolResultStatus.FAILURE,
                    error="Could not find add to cart button"
                )

            else:
                return ToolResult(
                    status=ToolResultStatus.FAILURE,
                    error=f"Unknown action: {step.action}"
                )

        except Exception as e:
            return ToolResult(
                status=ToolResultStatus.FAILURE,
                error=str(e)
            )

    async def _check_expectations(self, expect: dict) -> bool:
        """Check if expectations are met."""
        page = self._page
        assert page is not None

        try:
            if "url_contains" in expect:
                return expect["url_contains"] in page.url

            if "text_visible" in expect:
                content = await page.content()
                return expect["text_visible"].lower() in content.lower()

            if "element_visible" in expect:
                try:
                    await page.wait_for_selector(expect["element_visible"], timeout=5000)
                    return True
                except Exception:
                    return False

            return True
        except Exception:
            return False

    async def _take_screenshot(self, session_id: str, step_index: int) -> str | None:
        """Take a screenshot and save it."""
        if not self.screenshot_dir:
            return None

        page = self._page
        assert page is not None

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{session_id}_{step_index}.png"
        await page.screenshot(path=str(path))
        return str(path)

    async def _read_dom(self) -> dict:
        """Read simplified DOM structure."""
        page = self._page
        assert page is not None

        # Extract key elements
        elements = await page.evaluate("""() => {
            const result = [];
            const selectors = [
                'input', 'button', 'a', 'select', 'textarea',
                '[data-testid]', '[role="button"]', '[role="link"]'
            ];

            for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        result.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            testId: el.getAttribute('data-testid') || null,
                            ariaLabel: el.getAttribute('aria-label') || null,
                            text: el.textContent?.trim().slice(0, 100) || null,
                            type: el.type || null,
                            name: el.name || null,
                            href: el.href || null,
                            classes: Array.from(el.classList).slice(0, 5),
                        });
                    }
                }
            }
            return result.slice(0, 100);
        }""")

        title = await page.title()
        url = page.url
        visible_text = await page.evaluate("() => document.body.innerText.slice(0, 5000)")

        return {
            "url": url,
            "title": title,
            "elements": elements,
            "visible_text": visible_text,
        }

    async def get_observation(self) -> Observation:
        """Get current page observation for agent mode."""
        page = self._page
        assert page is not None

        dom_data = await self._read_dom()

        return Observation(
            url=dom_data["url"],
            title=dom_data["title"],
            dom_summary=str(dom_data["elements"])[:2000],
            visible_text=dom_data["visible_text"],
            elements=dom_data["elements"],
        )

    async def execute_action(self, action: AgentAction) -> str:
        """Execute an agent action."""
        step = Step(
            ts=0,
            action=action.action,
            selector=action.selector,
            text=action.text,
            url=action.url,
            metadata={"wait_ms": action.wait_ms} if action.wait_ms else {},
        )

        result = await self._execute_step(step, "agent", 0)

        if result.status == ToolResultStatus.SUCCESS:
            return "success"
        elif result.status == ToolResultStatus.BLOCKED:
            return "blocked"
        else:
            return f"failure: {result.error}"

    async def run_agent_session(
        self,
        agent: BaseAgent,
        goal: str,
        start_url: str,
        session_id: str,
        max_steps: int = 100,
    ) -> dict:
        """Run an agent-driven session."""
        if not self._page:
            await self.start()

        # Navigate to start
        await self._page.goto(start_url)
        await self._page.wait_for_load_state("networkidle")

        harness = AgentHarness(agent, max_steps=max_steps)

        result = await harness.run_session(
            goal=goal,
            start_url=start_url,
            session_id=session_id,
            get_observation=self.get_observation,
            execute_action=self.execute_action,
        )

        return result
