"""Rule-based stub agent for testing."""

import re
from typing import Any

from ..traces.schema import Observation, AgentAction, ActionType
from .agent import BaseAgent, AgentContext


class StubAgent(BaseAgent):
    """Rule-based stub agent that handles common scenarios.

    Behaviors:
    - If sees login page → type credentials
    - If search empty → broaden query
    - If checkout fails → retry up to 2 times
    """

    def __init__(self):
        self.retry_counts: dict[str, int] = {}
        self.search_attempts: dict[str, int] = {}
        self.last_action: AgentAction | None = None

    async def reset(self) -> None:
        """Reset agent state."""
        self.retry_counts = {}
        self.search_attempts = {}
        self.last_action = None

    async def decide(
        self,
        observation: Observation,
        context: AgentContext
    ) -> AgentAction:
        """Decide next action based on rules."""
        url = observation.url.lower()
        visible_text = observation.visible_text.lower()
        elements = observation.elements

        # Handle login page
        if self._is_login_page(observation):
            return self._handle_login(observation, context)

        # Handle search results
        if "search" in url or self._has_search_form(observation):
            return self._handle_search(observation, context)

        # Handle empty results
        if self._is_empty_results(observation):
            return self._handle_empty_results(observation, context)

        # Handle product page
        if self._is_product_page(observation):
            return self._handle_product_page(observation, context)

        # Handle cart page
        if "cart" in url:
            return self._handle_cart(observation, context)

        # Handle checkout page
        if "checkout" in url:
            return self._handle_checkout(observation, context)

        # Handle error pages
        if self._is_error_page(observation):
            return self._handle_error(observation, context)

        # Default: try to find a navigation action
        return self._find_navigation_action(observation, context)

    def _is_login_page(self, obs: Observation) -> bool:
        """Check if current page is a login page."""
        indicators = ["login", "sign in", "username", "password"]
        text = obs.visible_text.lower()
        return any(ind in text for ind in indicators) and "password" in text

    def _handle_login(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle login page."""
        # Find username field
        username_selectors = [
            '[data-testid="username"]',
            '[name="username"]',
            '[type="email"]',
            '#username',
            '#email',
        ]
        password_selectors = [
            '[data-testid="password"]',
            '[name="password"]',
            '[type="password"]',
            '#password',
        ]

        # Check if we need to type username
        for sel in username_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.TYPE,
                    selector=sel,
                    text="testuser",
                    reasoning="Entering username for login"
                )

        # Check if we need to type password
        for sel in password_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.TYPE,
                    selector=sel,
                    text="password123",
                    reasoning="Entering password for login"
                )

        # Try to submit
        submit_selectors = [
            '[data-testid="login-submit"]',
            '[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
        ]
        for sel in submit_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.CLICK,
                    selector=sel,
                    reasoning="Submitting login form"
                )

        return AgentAction(
            action=ActionType.WAIT,
            wait_ms=500,
            reasoning="Waiting for login page to load"
        )

    def _has_search_form(self, obs: Observation) -> bool:
        """Check if page has a search form."""
        search_indicators = ["search", "query", "find"]
        for elem in obs.elements:
            elem_str = str(elem).lower()
            if any(ind in elem_str for ind in search_indicators):
                return True
        return False

    def _handle_search(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle search functionality."""
        search_selectors = [
            '[data-testid="search-input"]',
            '[name="q"]',
            '[name="query"]',
            '[name="search"]',
            '#search',
            'input[type="search"]',
        ]

        # Try to find and use search input
        for sel in search_selectors:
            if self._has_element(obs, sel):
                attempt = self.search_attempts.get(ctx.session_id, 0)
                queries = ["laptop", "computer", "electronics", "phone"]
                query = queries[min(attempt, len(queries) - 1)]
                self.search_attempts[ctx.session_id] = attempt + 1

                return AgentAction(
                    action=ActionType.TYPE,
                    selector=sel,
                    text=query,
                    reasoning=f"Searching for: {query}"
                )

        # Try to submit search
        submit_selectors = [
            '[data-testid="search-submit"]',
            'button[type="submit"]',
            'button:has-text("Search")',
        ]
        for sel in submit_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.CLICK,
                    selector=sel,
                    reasoning="Submitting search"
                )

        return AgentAction(
            action=ActionType.WAIT,
            wait_ms=500,
            reasoning="Waiting for search results"
        )

    def _is_empty_results(self, obs: Observation) -> bool:
        """Check if search returned empty results."""
        empty_indicators = ["no results", "nothing found", "no items", "0 results"]
        return any(ind in obs.visible_text.lower() for ind in empty_indicators)

    def _handle_empty_results(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle empty search results by broadening query."""
        return AgentAction(
            action=ActionType.GOTO,
            url=f"{ctx.start_url}/search",
            reasoning="Returning to search to try broader query"
        )

    def _is_product_page(self, obs: Observation) -> bool:
        """Check if on a product page."""
        indicators = ["add to cart", "buy now", "price", "quantity"]
        return sum(1 for ind in indicators if ind in obs.visible_text.lower()) >= 2

    def _handle_product_page(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle product page - add to cart."""
        add_cart_selectors = [
            '[data-testid="add-to-cart"]',
            'button:has-text("Add to Cart")',
            'button:has-text("Add to Bag")',
            '.add-to-cart',
            '#add-to-cart',
        ]

        for sel in add_cart_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.CLICK,
                    selector=sel,
                    reasoning="Adding item to cart"
                )

        return AgentAction(
            action=ActionType.WAIT,
            wait_ms=500,
            reasoning="Looking for add to cart button"
        )

    def _handle_cart(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle cart page - proceed to checkout."""
        checkout_selectors = [
            '[data-testid="checkout-button"]',
            'button:has-text("Checkout")',
            'button:has-text("Proceed")',
            'a:has-text("Checkout")',
            '.checkout-button',
        ]

        for sel in checkout_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.CLICK,
                    selector=sel,
                    reasoning="Proceeding to checkout"
                )

        return AgentAction(
            action=ActionType.WAIT,
            wait_ms=500,
            reasoning="Looking for checkout button"
        )

    def _handle_checkout(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle checkout page with retry logic."""
        retry_key = f"{ctx.session_id}:checkout"
        retries = self.retry_counts.get(retry_key, 0)

        # Check for success
        if "order confirmed" in obs.visible_text.lower():
            return AgentAction(
                action=ActionType.WAIT,
                wait_ms=100,
                reasoning="Order complete"
            )

        # Check for error and retry
        if self._is_error_page(obs) and retries < 2:
            self.retry_counts[retry_key] = retries + 1
            return AgentAction(
                action=ActionType.CLICK,
                selector='[data-testid="submit-order"]',
                reasoning=f"Retrying checkout (attempt {retries + 2})"
            )

        # Try to complete checkout
        submit_selectors = [
            '[data-testid="submit-order"]',
            'button:has-text("Place Order")',
            'button:has-text("Complete Order")',
            'button[type="submit"]',
        ]

        for sel in submit_selectors:
            if self._has_element(obs, sel):
                return AgentAction(
                    action=ActionType.CLICK,
                    selector=sel,
                    reasoning="Submitting order"
                )

        return AgentAction(
            action=ActionType.WAIT,
            wait_ms=500,
            reasoning="Looking for order submission"
        )

    def _is_error_page(self, obs: Observation) -> bool:
        """Check if page shows an error."""
        error_indicators = ["error", "failed", "500", "something went wrong", "try again"]
        return any(ind in obs.visible_text.lower() for ind in error_indicators)

    def _handle_error(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Handle error page with refresh or retry."""
        return AgentAction(
            action=ActionType.REFRESH,
            reasoning="Refreshing after error"
        )

    def _find_navigation_action(self, obs: Observation, ctx: AgentContext) -> AgentAction:
        """Find a reasonable navigation action."""
        goal = ctx.goal.lower()

        # Try to navigate based on goal
        if "checkout" in goal or "purchase" in goal:
            nav_selectors = [
                'a:has-text("Shop")',
                'a:has-text("Products")',
                '[data-testid="nav-products"]',
            ]
            for sel in nav_selectors:
                if self._has_element(obs, sel):
                    return AgentAction(
                        action=ActionType.CLICK,
                        selector=sel,
                        reasoning="Navigating to products"
                    )

        # Default: go to search
        return AgentAction(
            action=ActionType.GOTO,
            url=f"{ctx.start_url}/search",
            reasoning="Navigating to search page"
        )

    def _has_element(self, obs: Observation, selector: str) -> bool:
        """Check if an element exists (simplified check)."""
        # This is a simplified check - real implementation would use actual selectors
        selector_parts = selector.lower().replace("[", "").replace("]", "").replace('"', "")

        for elem in obs.elements:
            elem_str = str(elem).lower()
            if any(part in elem_str for part in selector_parts.split("=")):
                return True

        # Check in DOM summary
        if selector_parts in obs.dom_summary.lower():
            return True

        return False
