"""Tests for dashboard server and SSE stream."""

import asyncio

import httpx
import pytest

from failsafe.core.engine import FailSafe
from failsafe.dashboard.server import create_app


@pytest.fixture
def fs():
    fs = FailSafe(mode="warn", audit_db=":memory:")
    fs.register_agent("kyc_agent", description="KYC verification")
    fs.register_agent("onboarding_agent", description="Onboarding flow")
    fs.contract(
        name="kyc-to-onboarding",
        source="kyc_agent",
        target="onboarding_agent",
        allow=["name", "status"],
        deny=["ssn"],
    )
    return fs


class TestRESTEndpoints:
    @pytest.mark.asyncio
    async def test_get_agents(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/agents")
            assert response.status_code == 200
            agents = response.json()
            assert len(agents) == 2
            names = {a["name"] for a in agents}
            assert "kyc_agent" in names
            assert "onboarding_agent" in names

    @pytest.mark.asyncio
    async def test_get_contracts(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/contracts")
            assert response.status_code == 200
            contracts = response.json()
            assert len(contracts) == 1
            assert contracts[0]["name"] == "kyc-to-onboarding"

    @pytest.mark.asyncio
    async def test_get_coverage(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/coverage")
            assert response.status_code == 200
            matrix = response.json()
            assert matrix["kyc_agent"]["onboarding_agent"] == "covered"

    @pytest.mark.asyncio
    async def test_get_graph(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/graph")
            assert response.status_code == 200
            data = response.json()
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1

    @pytest.mark.asyncio
    async def test_get_validations_empty(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/validations")
            assert response.status_code == 200
            assert response.json() == []


class TestSSEStream:
    def test_sse_history_available(self, fs):
        """EventBus history is populated and available for SSE consumers."""
        asyncio.run(fs.event_bus.emit("validation", {"passed": True, "source": "a"}))
        history = fs.event_bus.history
        assert len(history) == 1
        assert history[0]["type"] == "validation"
        assert history[0]["data"]["passed"] is True

    def test_sse_route_registered(self, fs):
        """SSE endpoint route is registered on the app."""
        app = create_app(fs)
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/stream" in routes


class TestEventBus:
    def test_emit_and_history(self, fs):
        """EventBus stores emitted events in history."""
        async def _test():
            await fs.event_bus.emit("test", {"key": "value"})
            assert len(fs.event_bus.history) == 1
            assert fs.event_bus.history[0]["type"] == "test"
            assert fs.event_bus.history[0]["data"]["key"] == "value"

        asyncio.run(_test())

    def test_subscribe_receives_events(self, fs):
        """Subscribers receive emitted events via their queue."""
        async def _test():
            queue = fs.event_bus.subscribe()
            await fs.event_bus.emit("validation", {"passed": True})
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            assert event["type"] == "validation"
            assert event["data"]["passed"] is True
            fs.event_bus.unsubscribe(queue)

        asyncio.run(_test())

    def test_unsubscribe(self, fs):
        """After unsubscribe, queue is removed from subscribers."""
        async def _test():
            queue = fs.event_bus.subscribe()
            assert len(fs.event_bus._subscribers) == 1
            fs.event_bus.unsubscribe(queue)
            assert len(fs.event_bus._subscribers) == 0

        asyncio.run(_test())
