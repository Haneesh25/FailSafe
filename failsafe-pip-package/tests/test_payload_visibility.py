"""Tests for payload visibility — event bus enrichment, masking, and dashboard endpoints."""

import asyncio

import httpx
import pytest

from failsafe.core.engine import FailSafe
from failsafe.dashboard.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fs():
    return FailSafe(mode="warn", audit_db=":memory:")


# ---------------------------------------------------------------------------
# Payload in event bus tests
# ---------------------------------------------------------------------------

class TestPayloadInEventBus:
    def test_handoff_emits_payload_keys(self, fs):
        fs.trace("a", "b", {"name": "alice", "age": 30})
        history = fs.event_bus._history
        assert len(history) >= 1
        data = history[-1]["data"]
        assert "payload_keys" in data
        assert set(data["payload_keys"]) == {"name", "age"}

    def test_handoff_emits_payload_preview(self, fs):
        fs.trace("a", "b", {"name": "alice"})
        data = fs.event_bus._history[-1]["data"]
        assert "payload_preview" in data
        preview = data["payload_preview"]
        assert isinstance(preview, str)
        # Should be valid JSON (or truncated JSON)
        assert "alice" in preview

    def test_handoff_emits_masked_payload(self, fs):
        fs.trace("a", "b", {"password": "secret123", "name": "alice"})
        data = fs.event_bus._history[-1]["data"]
        assert "payload" in data
        payload = data["payload"]
        assert payload["password"] == "***MASKED***"
        assert payload["name"] == "alice"

    def test_large_payload_preview_truncated(self, fs):
        large = {"data": "x" * 1000}
        fs.trace("a", "b", large)
        data = fs.event_bus._history[-1]["data"]
        preview = data["payload_preview"]
        assert preview.endswith("...")
        assert len(preview) <= 203  # 200 + "..."


# ---------------------------------------------------------------------------
# Masking tests
# ---------------------------------------------------------------------------

class TestMaskSensitive:
    def test_mask_sensitive_ssn_key(self, fs):
        result = fs._mask_sensitive({"ssn": "123-45-6789"})
        assert result["ssn"] == "***MASKED***"

    def test_mask_sensitive_password_key(self, fs):
        result = fs._mask_sensitive({"password": "secret123"})
        assert result["password"] == "***MASKED***"

    def test_mask_sensitive_nested(self, fs):
        result = fs._mask_sensitive({"user": {"ssn": "123"}})
        assert result["user"]["ssn"] == "***MASKED***"

    def test_mask_sensitive_ssn_in_value(self, fs):
        result = fs._mask_sensitive({"notes": "SSN is 123-45-6789"})
        assert "123-45-6789" not in result["notes"]
        assert "***-**-****" in result["notes"]

    def test_mask_sensitive_credit_card_in_value(self, fs):
        result = fs._mask_sensitive({"info": "card 4111-1111-1111-1111"})
        assert "4111" not in result["info"]
        assert "****-****-****-****" in result["info"]

    def test_mask_preserves_safe_values(self, fs):
        result = fs._mask_sensitive({"name": "Alice", "age": 30})
        assert result == {"name": "Alice", "age": 30}

    def test_mask_handles_lists(self, fs):
        result = fs._mask_sensitive({"items": [{"token": "abc"}]})
        assert result["items"][0]["token"] == "***MASKED***"

    def test_mask_handles_non_string_values(self, fs):
        result = fs._mask_sensitive({
            "count": 42,
            "active": True,
            "empty": None,
        })
        assert result["count"] == 42
        assert result["active"] is True
        assert result["empty"] is None


# ---------------------------------------------------------------------------
# Dashboard endpoint tests
# ---------------------------------------------------------------------------

class TestDashboardHandoffEndpoints:
    @pytest.mark.asyncio
    async def test_recent_handoffs_endpoint(self, fs):
        await fs.handoff("agent_a", "agent_b", {"key": "val"})
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/handoffs/recent")
            assert response.status_code == 200
            handoffs = response.json()
            assert len(handoffs) >= 1
            h = handoffs[-1]
            assert h["source"] == "agent_a"
            assert h["target"] == "agent_b"
            assert "payload" in h
            assert "payload_preview" in h
            assert "payload_keys" in h

    @pytest.mark.asyncio
    async def test_handoff_detail_by_trace_id(self, fs):
        await fs.handoff("agent_a", "agent_b", {"key": "val"})
        # Get trace_id from the event bus
        trace_id = fs.event_bus._history[-1]["data"]["trace_id"]
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/handoffs/{trace_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["source"] == "agent_a"
            assert data["target"] == "agent_b"
            assert data["trace_id"] == trace_id

    @pytest.mark.asyncio
    async def test_handoff_detail_not_found(self, fs):
        app = create_app(fs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/handoffs/nonexistent-trace-id")
            assert response.status_code == 200
            data = response.json()
            assert data["error"] == "Not found"
