"""End-to-end integration tests for the observe() -> trace -> violations pipeline."""

from types import SimpleNamespace

import httpx
import pytest

from failsafe import FailSafe, observe
from failsafe.dashboard.server import create_app
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler
from failsafe.observe import FailSafeObserver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline(obs: FailSafeObserver):
    """Create a 3-agent pipeline decorated with @obs.watch."""

    @obs.watch("research_agent")
    def research(query: str) -> dict:
        return {
            "customer_name": "Alice",
            "ssn": "123-45-6789",
            "credit_score": 750,
            "query": query,
        }

    @obs.watch("underwriting_agent")
    def underwrite(data: dict) -> dict:
        return {
            "risk_level": "low",
            "approved": True,
            "customer_name": data.get("customer_name"),
            "internal_weights": [0.3, 0.7],
        }

    @obs.watch("notification_agent")
    def notify(data: dict) -> dict:
        return {
            "email_sent": True,
            "recipient": data.get("customer_name"),
        }

    return research, underwrite, notify


# ---------------------------------------------------------------------------
# test_e2e_generic_pipeline
# ---------------------------------------------------------------------------


class TestE2EGenericPipeline:
    def test_e2e_generic_pipeline(self):
        """Full flow: observe -> @watch -> contracts -> violations -> event bus."""
        obs = observe(dashboard=False)
        assert isinstance(obs, FailSafeObserver)

        research, underwrite, notify = _make_pipeline(obs)

        # --- First run: no contracts, everything should pass ---
        r1 = research("loan for Alice")
        r2 = underwrite(r1)
        r3 = notify(r2)

        # Two handoffs occurred:
        #   research() -> no previous agent, no trace
        #   underwrite() -> traces research_agent -> underwriting_agent
        #   notify() -> traces underwriting_agent -> notification_agent
        first_run_events = len(obs.audit_log)
        assert first_run_events == 2
        first_run_violations = len(obs.violations)
        assert first_run_violations == 0  # No contracts yet

        # --- Add contracts ---
        obs.fs.contract(
            name="research-to-underwriting",
            source="research_agent",
            target="underwriting_agent",
            deny=["ssn"],
        )
        obs.fs.contract(
            name="underwriting-to-notification",
            source="underwriting_agent",
            target="notification_agent",
            deny=["internal_weights"],
        )

        # --- Second run: contracts enforced ---
        # Note: The watch() decorator remembers _last_agent from the first run,
        # so research() triggers a notification_agent -> research_agent handoff too.
        r1 = research("loan for Bob")
        r2 = underwrite(r1)
        r3 = notify(r2)

        # Event bus has entries for ALL calls (both runs):
        # First run: 2 handoffs + Second run: 3 handoffs (including carryover) = 5
        assert len(obs.audit_log) == 5

        # Violations caught in second run (at least ssn + internal_weights)
        violations = obs.violations
        assert len(violations) >= 2
        rules = {v["rule"] for v in violations}
        assert "deny_fields" in rules


# ---------------------------------------------------------------------------
# test_e2e_langchain_pipeline
# ---------------------------------------------------------------------------


class TestE2ELangchainPipeline:
    @pytest.mark.asyncio
    async def test_e2e_langchain_pipeline(self):
        """Full flow: observe(langchain) -> callbacks -> contracts -> violations."""
        handler = observe(framework="langchain", dashboard=False)
        assert isinstance(handler, FailSafeCallbackHandler)

        # --- First run: no contracts ---
        await handler.on_chain_start({"name": "research_chain"}, {"q": "test"})
        await handler.on_chain_start({"name": "analysis_chain"}, {"data": "x"})
        await handler.on_chain_end({"result": "clean data"})
        await handler.on_chain_end({"answer": "42"})

        assert len(handler.violations) == 0

        # --- Add deny contract ---
        handler.fs.contract(
            name="research-to-analysis",
            source="research_chain",
            target="analysis_chain",
            deny=["api_key"],
        )

        # --- Second run: denied field in output ---
        await handler.on_chain_start({"name": "research_chain"}, {"q": "test2"})
        await handler.on_chain_start({"name": "analysis_chain"}, {"data": "y"})
        await handler.on_chain_end({
            "result": "data",
            "api_key": "sk-secret-123",
        })
        await handler.on_chain_end({"answer": "done"})

        assert len(handler.violations) > 0
        assert any(v.rule == "deny_fields" for v in handler.violations)

        # Verify summary
        s = handler.summary()
        assert s["total_violations"] > 0
        assert len(s["handoffs"]) >= 1


# ---------------------------------------------------------------------------
# test_e2e_dashboard_serves_events
# ---------------------------------------------------------------------------


class TestE2EDashboardServesEvents:
    @pytest.mark.asyncio
    async def test_e2e_dashboard_serves_events(self):
        """Run handoffs -> query dashboard API -> verify payload data present and masked."""
        fs = FailSafe(mode="warn", audit_db=":memory:")

        # Run some handoffs
        await fs.handoff(
            source="agent_a",
            target="agent_b",
            payload={"name": "Alice", "ssn": "123-45-6789"},
        )
        await fs.handoff(
            source="agent_b",
            target="agent_c",
            payload={"result": "clean data", "score": 95},
        )

        # Create the dashboard app and query the API
        app = create_app(fs)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/handoffs/recent")
            assert resp.status_code == 200
            handoffs = resp.json()

            assert len(handoffs) == 2

            # First handoff: ssn should be masked (key-based masking)
            h0 = handoffs[0]
            assert h0["source"] == "agent_a"
            assert h0["target"] == "agent_b"
            assert h0["payload"]["ssn"] == "***MASKED***"
            assert h0["payload"]["name"] == "Alice"  # Non-sensitive stays

            # Second handoff
            h1 = handoffs[1]
            assert h1["source"] == "agent_b"
            assert h1["payload"]["result"] == "clean data"


# ---------------------------------------------------------------------------
# test_e2e_mixed_valid_and_invalid_handoffs
# ---------------------------------------------------------------------------


class TestE2EMixedHandoffs:
    @pytest.mark.asyncio
    async def test_e2e_mixed_valid_and_invalid_handoffs(self):
        """5 handoffs: 3 valid, 2 with violations. Verify exact counts."""
        fs = FailSafe(mode="warn", audit_db=":memory:")
        fs.contract(
            name="a-to-b",
            source="a",
            target="b",
            deny=["secret"],
        )

        results = []

        # 3 valid handoffs
        results.append(await fs.handoff("a", "b", {"data": "ok1"}))
        results.append(await fs.handoff("a", "b", {"data": "ok2"}))
        results.append(await fs.handoff("a", "b", {"data": "ok3"}))

        # 2 invalid handoffs
        results.append(await fs.handoff("a", "b", {"data": "x", "secret": "bad1"}))
        results.append(await fs.handoff("a", "b", {"data": "y", "secret": "bad2"}))

        assert len(results) == 5

        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]

        assert len(passed) == 3
        assert len(failed) == 2

        # All violations come from deny_fields
        all_violations = [v for r in results for v in r.violations]
        assert len(all_violations) == 2
        assert all(v.rule == "deny_fields" for v in all_violations)

        # Event bus has all 5
        assert len(fs.event_bus.history) == 5


# ---------------------------------------------------------------------------
# test_e2e_observe_then_add_contracts
# ---------------------------------------------------------------------------


class TestE2EObserveThenAddContracts:
    def test_e2e_observe_then_add_contracts(self):
        """Key UX flow: start with NO contracts, see payloads, then add contracts."""
        obs = observe(dashboard=False)
        research, underwrite, notify = _make_pipeline(obs)

        # --- Phase 1: No contracts, just observe ---
        research("check Alice")
        underwrite({"customer_name": "Alice", "ssn": "111-22-3333", "credit_score": 700})
        notify({"approved": True, "customer_name": "Alice"})

        # Everything passes — no violations
        assert len(obs.violations) == 0

        # But event bus shows the payloads flowing
        events = obs.audit_log
        assert len(events) >= 2  # At least 2 handoffs

        # User sees SSN flowing in payloads — adds a deny contract
        obs.fs.contract(
            name="block-ssn",
            source="research_agent",
            target="underwriting_agent",
            deny=["ssn"],
        )

        # --- Phase 2: Same handoffs now catch violations ---
        research("check Bob")
        underwrite({"customer_name": "Bob", "ssn": "444-55-6666", "credit_score": 650})

        violations = obs.violations
        assert len(violations) >= 1
        assert any("ssn" in str(v.get("message", "")) for v in violations)


# ---------------------------------------------------------------------------
# test_e2e_multiple_observers_independent
# ---------------------------------------------------------------------------


class TestE2EMultipleObservers:
    def test_e2e_multiple_observers_independent(self):
        """Two separate observe() instances don't share state."""
        obs1 = observe(dashboard=False)
        obs2 = observe(dashboard=False)

        @obs1.watch("agent_x")
        def agent_x_1(data: str) -> dict:
            return {"result": data, "from": "obs1"}

        @obs1.watch("agent_y")
        def agent_y_1(data: dict) -> dict:
            return {"done": True}

        @obs2.watch("agent_x")
        def agent_x_2(data: str) -> dict:
            return {"result": data, "from": "obs2"}

        @obs2.watch("agent_y")
        def agent_y_2(data: dict) -> dict:
            return {"done": True}

        # Add contract only to obs1
        obs1.fs.contract(
            name="x-to-y",
            source="agent_x",
            target="agent_y",
            deny=["from"],
        )

        # Run both pipelines
        agent_x_1("hello")
        agent_y_1({"x": 1})

        agent_x_2("world")
        agent_y_2({"x": 2})

        # obs1 should have violations (deny "from" field)
        assert len(obs1.violations) >= 1

        # obs2 should have NO violations (no contracts)
        assert len(obs2.violations) == 0

        # Audit logs are independent
        assert len(obs1.audit_log) >= 1
        assert len(obs2.audit_log) >= 1

        # They don't share the same event bus
        assert obs1.fs.event_bus is not obs2.fs.event_bus
