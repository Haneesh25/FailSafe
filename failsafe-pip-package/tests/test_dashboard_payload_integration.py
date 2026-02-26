"""
Comprehensive integration tests verifying the dashboard API and event bus
emit payload data in the exact shapes the React frontend expects.

The frontend components rely on specific field names, types, and nesting.
If any of these break, the UI fails silently. These tests are the contract
between the Python backend and the React frontend.
"""

import asyncio
import json

import httpx
import pytest

from failsafe.core.engine import FailSafe
from failsafe.dashboard.server import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fs():
    """Fresh FailSafe instance with in-memory DB, no dashboard server."""
    return FailSafe(audit_db=":memory:", dashboard=False)


@pytest.fixture
def fs_with_contracts():
    """FailSafe with multiple contracts pre-configured."""
    fs = FailSafe(audit_db=":memory:", dashboard=False)
    fs.contract("deny-ssn", "research", "underwriting", deny=["ssn", "tax_id"])
    fs.contract("require-name", "intake", "research", require=["customer_name"])
    fs.contract("deny-internal", "underwriting", "notification",
                deny=["internal_weights", "model_version"])
    return fs


def _last_event_data(fs):
    """Helper to get data dict from the most recent event bus emission."""
    return fs.event_bus._history[-1]["data"]


def _last_event(fs):
    """Helper to get the full event dict from the most recent emission."""
    return fs.event_bus._history[-1]


# ===========================================================================
# 1. EVENT SCHEMA COMPLETENESS
# The frontend destructures event.data and reads these fields directly.
# Missing fields cause undefined errors in React.
# ===========================================================================

class TestEventSchemaCompleteness:
    """Every field the frontend reads from event.data must always be present."""

    REQUIRED_FIELDS = [
        "source", "target", "passed", "violations", "contract",
        "trace_id", "timestamp", "duration_ms",
        "payload_keys", "payload_size", "payload_preview", "payload",
    ]

    def test_all_fields_present_with_contract(self, fs):
        """With a matching contract, all 12 required fields exist."""
        fs.contract("c1", "a", "b", deny=["x"])
        asyncio.run(fs.handoff("a", "b", {"x": 1, "y": 2}))
        data = _last_event_data(fs)
        for field in self.REQUIRED_FIELDS:
            assert field in data, f"Missing required field: {field}"

    def test_all_fields_present_without_contract(self, fs):
        """Without any contract, all 12 required fields still exist."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        data = _last_event_data(fs)
        for field in self.REQUIRED_FIELDS:
            assert field in data, f"Missing field without contract: {field}"

    def test_all_fields_present_empty_payload(self, fs):
        """Even with an empty payload dict, all fields exist."""
        asyncio.run(fs.handoff("a", "b", {}))
        data = _last_event_data(fs)
        for field in self.REQUIRED_FIELDS:
            assert field in data, f"Missing field for empty payload: {field}"

    def test_event_has_type_field(self, fs):
        """The top-level event must have a 'type' field (used for SSE routing)."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        event = _last_event(fs)
        assert "type" in event
        assert event["type"] == "validation"

    def test_event_has_timestamp_at_top_level(self, fs):
        """The top-level event has its own timestamp (separate from data.timestamp)."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        event = _last_event(fs)
        assert "timestamp" in event

    def test_schema_identical_pass_vs_fail(self, fs):
        """Pass and fail events have the exact same set of keys."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        pass_keys = set(_last_event_data(fs).keys())

        fs.contract("c1", "a", "b", deny=["x"])
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        fail_keys = set(_last_event_data(fs).keys())

        assert pass_keys == fail_keys, f"Key mismatch: {pass_keys.symmetric_difference(fail_keys)}"


# ===========================================================================
# 2. FIELD TYPE CONTRACTS
# The frontend uses typeof checks, .map(), .length, JSON.parse(), etc.
# Wrong types cause runtime crashes.
# ===========================================================================

class TestFieldTypes:
    """Verify exact types for every field the frontend accesses."""

    def test_source_is_string(self, fs):
        asyncio.run(fs.handoff("agent_a", "agent_b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["source"], str)

    def test_target_is_string(self, fs):
        asyncio.run(fs.handoff("agent_a", "agent_b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["target"], str)

    def test_passed_is_boolean(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["passed"], bool)

    def test_violations_is_list(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["violations"], list)

    def test_contract_is_string_or_none(self, fs):
        """contract is null when no contract matches, string when one does."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert _last_event_data(fs)["contract"] is None

        fs.contract("c1", "a", "b")
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["contract"], str)

    def test_trace_id_is_string(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["trace_id"], str)
        assert len(_last_event_data(fs)["trace_id"]) > 0

    def test_timestamp_is_string(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["timestamp"], str)

    def test_duration_ms_is_number(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["duration_ms"], (int, float))

    def test_payload_keys_is_list_of_strings(self, fs):
        asyncio.run(fs.handoff("a", "b", {"name": "Alice", "age": 30}))
        keys = _last_event_data(fs)["payload_keys"]
        assert isinstance(keys, list)
        assert all(isinstance(k, str) for k in keys)

    def test_payload_size_is_positive_int(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        size = _last_event_data(fs)["payload_size"]
        assert isinstance(size, int)
        assert size > 0

    def test_payload_preview_is_string(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["payload_preview"], str)

    def test_payload_is_dict(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert isinstance(_last_event_data(fs)["payload"], dict)


# ===========================================================================
# 3. PAYLOAD KEYS — used by ValidationStream pills, DataFlow field sidebar
# ===========================================================================

class TestPayloadKeys:
    """payload_keys drives the key pill rendering and field frequency sidebar."""

    def test_keys_match_payload_top_level_keys(self, fs):
        asyncio.run(fs.handoff("a", "b", {"name": "Alice", "score": 95, "active": True}))
        data = _last_event_data(fs)
        assert set(data["payload_keys"]) == {"name", "score", "active"}

    def test_empty_payload_gives_empty_keys(self, fs):
        asyncio.run(fs.handoff("a", "b", {}))
        assert _last_event_data(fs)["payload_keys"] == []

    def test_nested_payload_only_top_level_keys(self, fs):
        """The frontend shows top-level keys only. Nested keys should NOT appear."""
        asyncio.run(fs.handoff("a", "b", {"user": {"name": "Alice", "ssn": "123"}, "scores": [1, 2]}))
        keys = _last_event_data(fs)["payload_keys"]
        assert set(keys) == {"user", "scores"}
        assert "name" not in keys
        assert "ssn" not in keys

    def test_large_payload_many_keys(self, fs):
        """100 keys should all appear in payload_keys."""
        big = {f"key_{i}": f"value_{i}" for i in range(100)}
        asyncio.run(fs.handoff("a", "b", big))
        keys = _last_event_data(fs)["payload_keys"]
        assert len(keys) == 100

    def test_keys_order_preserved(self, fs):
        """Keys should maintain insertion order (Python 3.7+ dict ordering)."""
        payload = {"zebra": 1, "apple": 2, "mango": 3}
        asyncio.run(fs.handoff("a", "b", payload))
        keys = _last_event_data(fs)["payload_keys"]
        assert keys == list(payload.keys())


# ===========================================================================
# 4. PAYLOAD MASKING — the frontend displays masked values + lock icons
# ===========================================================================

class TestPayloadMasking:
    """Verify sensitive data is masked before reaching the frontend."""

    def test_ssn_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"ssn": "123-45-6789"}))
        assert _last_event_data(fs)["payload"]["ssn"] == "***MASKED***"

    def test_password_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"password": "secret123"}))
        assert _last_event_data(fs)["payload"]["password"] == "***MASKED***"

    def test_api_key_variations_masked(self, fs):
        """Both api_key and apikey patterns should be masked."""
        asyncio.run(fs.handoff("a", "b", {"api_key": "sk-abc", "apikey": "sk-def"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["api_key"] == "***MASKED***"
        assert payload["apikey"] == "***MASKED***"

    def test_token_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"token": "tok_123", "access_key": "ak_456"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["token"] == "***MASKED***"
        # access_key is in the sensitive key set (exact match)
        assert payload["access_key"] == "***MASKED***"

    def test_credit_card_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"credit_card": "4111-1111-1111-1111"}))
        assert _last_event_data(fs)["payload"]["credit_card"] == "***MASKED***"

    def test_secret_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"secret_key": "shh", "secret": "quiet"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["secret_key"] == "***MASKED***"
        assert payload["secret"] == "***MASKED***"

    def test_private_key_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"private_key": "-----BEGIN RSA-----"}))
        assert _last_event_data(fs)["payload"]["private_key"] == "***MASKED***"

    def test_tax_id_and_account_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"tax_id": "12-3456789", "bank_account": "9876543210"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["tax_id"] == "***MASKED***"
        assert payload["bank_account"] == "***MASKED***"

    def test_safe_values_not_masked(self, fs):
        asyncio.run(fs.handoff("a", "b", {"name": "Alice", "age": 30, "active": True}))
        payload = _last_event_data(fs)["payload"]
        assert payload["name"] == "Alice"
        assert payload["age"] == 30
        assert payload["active"] is True

    def test_nested_sensitive_keys_masked(self, fs):
        """Masking recurses into nested dicts."""
        asyncio.run(fs.handoff("a", "b", {"user": {"name": "Alice", "ssn": "111-22-3333"}}))
        payload = _last_event_data(fs)["payload"]
        assert payload["user"]["name"] == "Alice"
        assert payload["user"]["ssn"] == "***MASKED***"

    def test_sensitive_in_list_masked(self, fs):
        """Masking recurses into lists of dicts."""
        asyncio.run(fs.handoff("a", "b", {"items": [{"token": "abc"}, {"name": "ok"}]}))
        payload = _last_event_data(fs)["payload"]
        assert payload["items"][0]["token"] == "***MASKED***"
        assert payload["items"][1]["name"] == "ok"

    def test_ssn_pattern_in_value_masked(self, fs):
        """SSN patterns (NNN-NN-NNNN) in string values are replaced."""
        asyncio.run(fs.handoff("a", "b", {"notes": "SSN is 123-45-6789 for reference"}))
        payload = _last_event_data(fs)["payload"]
        assert "123-45-6789" not in payload["notes"]
        assert "***-**-****" in payload["notes"]

    def test_credit_card_pattern_in_value_masked(self, fs):
        """16-digit card patterns in string values are replaced."""
        asyncio.run(fs.handoff("a", "b", {"info": "card 4111-1111-1111-1111 on file"}))
        payload = _last_event_data(fs)["payload"]
        assert "4111" not in payload["info"]
        assert "****-****-****-****" in payload["info"]

    def test_non_string_values_preserved(self, fs):
        """Masking should not corrupt int, float, bool, None types."""
        asyncio.run(fs.handoff("a", "b", {
            "count": 42, "ratio": 3.14, "active": True, "deleted": False, "extra": None
        }))
        payload = _last_event_data(fs)["payload"]
        assert payload["count"] == 42
        assert payload["ratio"] == 3.14
        assert payload["active"] is True
        assert payload["deleted"] is False
        assert payload["extra"] is None

    def test_empty_payload_masking(self, fs):
        asyncio.run(fs.handoff("a", "b", {}))
        assert _last_event_data(fs)["payload"] == {}

    def test_masking_does_not_mutate_original(self, fs):
        """The original payload passed to handoff() must not be modified."""
        original = {"ssn": "123-45-6789", "name": "Alice"}
        original_copy = original.copy()
        asyncio.run(fs.handoff("a", "b", original))
        assert original == original_copy, "Original payload was mutated by masking!"


# ===========================================================================
# 5. PAYLOAD PREVIEW — shown as truncated one-liner in stream and DataFlow
# ===========================================================================

class TestPayloadPreview:
    """payload_preview is displayed as a compact one-liner."""

    def test_small_payload_not_truncated(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        preview = _last_event_data(fs)["payload_preview"]
        assert "..." not in preview
        assert "x" in preview

    def test_large_payload_truncated_with_ellipsis(self, fs):
        """Payloads over 200 chars should be truncated."""
        big = {"data": "x" * 1000}
        asyncio.run(fs.handoff("a", "b", big))
        preview = _last_event_data(fs)["payload_preview"]
        assert preview.endswith("...")
        assert len(preview) <= 203  # 200 + "..."

    def test_empty_payload_preview(self, fs):
        asyncio.run(fs.handoff("a", "b", {}))
        preview = _last_event_data(fs)["payload_preview"]
        assert preview == "{}"

    def test_preview_is_valid_json_prefix(self, fs):
        """The preview should start with valid JSON (for non-truncated payloads)."""
        asyncio.run(fs.handoff("a", "b", {"name": "Alice"}))
        preview = _last_event_data(fs)["payload_preview"]
        parsed = json.loads(preview)
        assert parsed["name"] == "Alice"


# ===========================================================================
# 6. PAYLOAD SIZE — shown next to preview in the stream
# ===========================================================================

class TestPayloadSize:
    """payload_size is the byte size of str(payload)."""

    def test_empty_payload_size(self, fs):
        asyncio.run(fs.handoff("a", "b", {}))
        size = _last_event_data(fs)["payload_size"]
        # Engine uses len(str(payload))
        assert size == len(str({}))

    def test_size_reflects_original_not_masked(self, fs):
        """Size should be of the ORIGINAL payload, not the masked version."""
        payload = {"name": "Alice", "ssn": "123-45-6789"}
        asyncio.run(fs.handoff("a", "b", payload))
        # Engine uses len(str(payload))
        expected_size = len(str(payload))
        actual_size = _last_event_data(fs)["payload_size"]
        assert actual_size == expected_size


# ===========================================================================
# 7. VIOLATIONS — drives red coloring, severity badges, HandoffDetail cards
# ===========================================================================

class TestViolationShape:
    """The frontend reads specific fields from each violation object."""

    REQUIRED_VIOLATION_FIELDS = ["rule", "severity", "message"]

    def test_no_violations_when_passing(self, fs):
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        assert _last_event_data(fs)["violations"] == []

    def test_violation_has_required_fields(self, fs):
        fs.contract("c1", "a", "b", deny=["x"])
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        violations = _last_event_data(fs)["violations"]
        assert len(violations) >= 1
        v = violations[0]
        for field in self.REQUIRED_VIOLATION_FIELDS:
            assert field in v, f"Violation missing field: {field}"

    def test_violation_has_field_attribute(self, fs):
        """The 'field' attribute is used to color payload key pills red."""
        fs.contract("c1", "a", "b", deny=["ssn"])
        asyncio.run(fs.handoff("a", "b", {"ssn": "123", "name": "Alice"}))
        v = _last_event_data(fs)["violations"][0]
        assert "field" in v
        assert "ssn" in v["field"]

    def test_violation_has_evidence_dict(self, fs):
        """Evidence is expandable in HandoffDetail."""
        fs.contract("c1", "a", "b", deny=["ssn"])
        asyncio.run(fs.handoff("a", "b", {"ssn": "123"}))
        v = _last_event_data(fs)["violations"][0]
        assert "evidence" in v
        assert isinstance(v["evidence"], dict)

    def test_violation_severity_values(self, fs):
        """Severity drives badge coloring: critical, high, medium, low."""
        fs.contract("c1", "a", "b", deny=["x"])
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        severity = _last_event_data(fs)["violations"][0]["severity"]
        assert severity in ("critical", "high", "medium", "low")

    def test_multiple_violations_from_multiple_rules(self, fs):
        """Multiple contract rules can fire, producing multiple violations."""
        fs.contract("c1", "a", "b", deny=["ssn", "password"], require=["name"])
        asyncio.run(fs.handoff("a", "b", {"ssn": "123", "password": "secret"}))
        violations = _last_event_data(fs)["violations"]
        assert len(violations) >= 2
        rules = {v["rule"] for v in violations}
        assert "deny_fields" in rules
        assert "require_fields" in rules

    def test_violation_field_comma_separated_for_multi_deny(self, fs):
        """When multiple denied fields are found, field may be comma-separated."""
        fs.contract("c1", "a", "b", deny=["ssn", "password"])
        asyncio.run(fs.handoff("a", "b", {"ssn": "123", "password": "secret", "name": "Alice"}))
        violations = _last_event_data(fs)["violations"]
        deny_v = [v for v in violations if v["rule"] == "deny_fields"][0]
        # Frontend splits on ", " to find which keys to highlight red
        assert "ssn" in deny_v["field"]
        assert "password" in deny_v["field"]


# ===========================================================================
# 8. TRACE ID — used for grouping in DataFlow, detail lookup, prev/next nav
# ===========================================================================

class TestTraceId:
    """trace_id is the primary key for DataFlow trace grouping."""

    def test_auto_generated_trace_id(self, fs):
        """When no trace_id is provided, one is auto-generated."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        tid = _last_event_data(fs)["trace_id"]
        assert isinstance(tid, str)
        assert len(tid) > 8

    def test_custom_trace_id_preserved(self, fs):
        """When trace_id is explicitly passed, it appears in the event."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}, trace_id="my-custom-trace"))
        assert _last_event_data(fs)["trace_id"] == "my-custom-trace"

    def test_same_trace_id_groups_pipeline(self, fs):
        """Multiple handoffs with the same trace_id form a pipeline group."""
        tid = "pipeline-001"
        asyncio.run(fs.handoff("a", "b", {"step": 1}, trace_id=tid))
        asyncio.run(fs.handoff("b", "c", {"step": 2}, trace_id=tid))
        asyncio.run(fs.handoff("c", "d", {"step": 3}, trace_id=tid))

        matching = [e for e in fs.event_bus._history if e["data"].get("trace_id") == tid]
        assert len(matching) == 3
        sources = [e["data"]["source"] for e in matching]
        assert sources == ["a", "b", "c"]

    def test_different_trace_ids_are_separate(self, fs):
        """Handoffs without shared trace_ids are not grouped."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        tid1 = fs.event_bus._history[-1]["data"]["trace_id"]
        asyncio.run(fs.handoff("a", "b", {"x": 2}))
        tid2 = fs.event_bus._history[-1]["data"]["trace_id"]
        assert tid1 != tid2


# ===========================================================================
# 9. EDGE FILTERING — the AgentGraph EdgePayloadPanel filters by source+target
# ===========================================================================

class TestEdgeFiltering:
    """The EdgePayloadPanel filters events by source->target pair."""

    def test_filter_events_by_source_target(self, fs):
        """Simulates what the frontend does to populate the edge panel."""
        asyncio.run(fs.handoff("a", "b", {"x": 1}))
        asyncio.run(fs.handoff("a", "b", {"x": 2}))
        asyncio.run(fs.handoff("b", "c", {"x": 3}))
        asyncio.run(fs.handoff("a", "c", {"x": 4}))

        all_events = fs.event_bus._history
        a_to_b = [e for e in all_events
                   if e["data"]["source"] == "a" and e["data"]["target"] == "b"]
        assert len(a_to_b) == 2

        b_to_c = [e for e in all_events
                   if e["data"]["source"] == "b" and e["data"]["target"] == "c"]
        assert len(b_to_c) == 1

    def test_edge_stats_calculation(self, fs):
        """Simulates the pass rate / failure count the edge panel shows."""
        fs.contract("c1", "a", "b", deny=["bad"])
        asyncio.run(fs.handoff("a", "b", {"ok": 1}))       # pass
        asyncio.run(fs.handoff("a", "b", {"ok": 2}))       # pass
        asyncio.run(fs.handoff("a", "b", {"bad": "x"}))    # fail

        a_to_b = [e for e in fs.event_bus._history
                   if e["data"]["source"] == "a" and e["data"]["target"] == "b"]
        passes = sum(1 for e in a_to_b if e["data"]["passed"])
        fails = sum(1 for e in a_to_b if not e["data"]["passed"])
        assert passes == 2
        assert fails == 1
        # Frontend shows: "3 handoffs, 1 failure" and "66.7% pass rate"


# ===========================================================================
# 10. SPECIAL CHARACTERS — XSS, unicode, multi-line in payloads
# ===========================================================================

class TestSpecialCharacters:
    """Payloads with special chars must not break JSON serialization or the UI."""

    def test_html_in_payload(self, fs):
        """HTML content should pass through without corruption."""
        asyncio.run(fs.handoff("a", "b", {"html": "<script>alert('xss')</script>"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["html"] == "<script>alert('xss')</script>"

    def test_unicode_in_payload(self, fs):
        asyncio.run(fs.handoff("a", "b", {"text": "\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8", "emoji": "\U0001f389\U0001f525"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["text"] == "\u65e5\u672c\u8a9e\u30c6\u30b9\u30c8"
        assert payload["emoji"] == "\U0001f389\U0001f525"

    def test_newlines_in_payload(self, fs):
        asyncio.run(fs.handoff("a", "b", {"multiline": "line1\nline2\nline3"}))
        payload = _last_event_data(fs)["payload"]
        assert payload["multiline"] == "line1\nline2\nline3"

    def test_empty_string_values(self, fs):
        asyncio.run(fs.handoff("a", "b", {"empty": "", "space": " "}))
        payload = _last_event_data(fs)["payload"]
        assert payload["empty"] == ""
        assert payload["space"] == " "

    def test_very_long_key_names(self, fs):
        long_key = "a" * 500
        asyncio.run(fs.handoff("a", "b", {long_key: "value"}))
        keys = _last_event_data(fs)["payload_keys"]
        assert long_key in keys

    def test_json_serializable_event(self, fs):
        """The entire event must be JSON-serializable (SSE sends JSON strings)."""
        asyncio.run(fs.handoff("a", "b", {
            "nested": {"deep": {"value": [1, 2, {"x": True}]}},
            "unicode": "\u65e5\u672c\u8a9e",
            "html": "<b>bold</b>",
        }))
        event = _last_event(fs)
        # This must not raise
        serialized = json.dumps(event, default=str)
        assert len(serialized) > 0
        # And must round-trip
        parsed = json.loads(serialized)
        assert parsed["data"]["payload"]["unicode"] == "\u65e5\u672c\u8a9e"


# ===========================================================================
# 11. DASHBOARD API ENDPOINTS — /api/handoffs/recent, /api/handoffs/{trace_id}
# ===========================================================================

class TestHandoffsRecentAPI:
    """/api/handoffs/recent must return the same shape as SSE events."""

    @pytest.mark.asyncio
    async def test_returns_list(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("a", "b", {"x": 1})
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/recent")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_contains_payload_data(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("a", "b", {"name": "Alice", "password": "secret"})
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/recent")
            h = resp.json()[0]
            assert h["source"] == "a"
            assert h["target"] == "b"
            assert "payload" in h
            assert h["payload"]["name"] == "Alice"
            assert h["payload"]["password"] == "***MASKED***"
            assert "payload_keys" in h
            assert "payload_preview" in h

    @pytest.mark.asyncio
    async def test_ordering_newest_first(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("a", "b", {"order": 1})
        await fs.handoff("c", "d", {"order": 2})
        await fs.handoff("e", "f", {"order": 3})
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/recent")
            handoffs = resp.json()
            assert len(handoffs) == 3
            # All three should be present
            sources = [h["source"] for h in handoffs]
            assert "a" in sources and "c" in sources and "e" in sources

    @pytest.mark.asyncio
    async def test_empty_when_no_handoffs(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/recent")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_multiple_handoffs_with_violations(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        fs.contract("c1", "a", "b", deny=["secret"])
        await fs.handoff("a", "b", {"ok": 1})
        await fs.handoff("a", "b", {"secret": "bad"})
        await fs.handoff("a", "b", {"ok": 2})
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/recent")
            handoffs = resp.json()
            assert len(handoffs) == 3
            failed = [h for h in handoffs if not h["passed"]]
            passed = [h for h in handoffs if h["passed"]]
            assert len(failed) == 1
            assert len(passed) == 2
            assert len(failed[0]["violations"]) > 0


class TestHandoffDetailAPI:
    """/api/handoffs/{trace_id} returns full detail for a single handoff."""

    @pytest.mark.asyncio
    async def test_detail_by_trace_id(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("x", "y", {"data": "test"}, trace_id="trace-abc-123")
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/trace-abc-123")
            assert resp.status_code == 200
            detail = resp.json()
            assert detail["source"] == "x"
            assert detail["target"] == "y"
            assert detail["trace_id"] == "trace-abc-123"
            assert "payload" in detail
            assert detail["payload"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_detail_not_found(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/nonexistent-trace")
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("error") == "Not found"

    @pytest.mark.asyncio
    async def test_detail_has_masked_payload(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("a", "b", {"name": "Alice", "ssn": "123-45-6789"}, trace_id="mask-test")
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/mask-test")
            detail = resp.json()
            assert detail["payload"]["name"] == "Alice"
            assert detail["payload"]["ssn"] == "***MASKED***"

    @pytest.mark.asyncio
    async def test_detail_includes_violations(self):
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        fs.contract("c1", "a", "b", deny=["secret"])
        await fs.handoff("a", "b", {"secret": "bad", "ok": "fine"}, trace_id="viol-test")
        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/handoffs/viol-test")
            detail = resp.json()
            assert detail["passed"] is False
            assert len(detail["violations"]) > 0
            assert detail["violations"][0]["rule"] == "deny_fields"


# ===========================================================================
# 12. E2E PIPELINE — multi-agent pipeline with trace grouping + violations
# ===========================================================================

class TestE2EPipelineDataFlow:
    """Simulates the exact scenario the DataFlow tab renders."""

    @pytest.mark.asyncio
    async def test_three_agent_pipeline_trace_group(self):
        """
        Pipeline: research -> underwriting -> notification
        Same trace_id. One violation in the middle.
        DataFlow groups these into one collapsible trace group.
        """
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        fs.contract("r-to-u", "research", "underwriting", deny=["ssn"])
        fs.contract("u-to-n", "underwriting", "notification", deny=["internal_weights"])

        tid = "pipeline-e2e-001"
        await fs.handoff("research", "underwriting",
                         {"customer_name": "Alice", "ssn": "123-45-6789", "credit_score": 750},
                         trace_id=tid)
        await fs.handoff("underwriting", "notification",
                         {"risk_level": "low", "approved": True, "internal_weights": [0.3, 0.7]},
                         trace_id=tid)
        await fs.handoff("notification", "output",
                         {"email_sent": True, "recipient": "Alice"},
                         trace_id=tid)

        # All three events share the trace_id
        pipeline_events = [e for e in fs.event_bus._history
                           if e["data"].get("trace_id") == tid]
        assert len(pipeline_events) == 3

        # First handoff: fails (ssn denied)
        assert pipeline_events[0]["data"]["passed"] is False
        assert pipeline_events[0]["data"]["source"] == "research"
        assert pipeline_events[0]["data"]["target"] == "underwriting"
        assert "ssn" in pipeline_events[0]["data"]["violations"][0]["field"]

        # Second handoff: fails (internal_weights denied)
        assert pipeline_events[1]["data"]["passed"] is False
        assert pipeline_events[1]["data"]["source"] == "underwriting"
        assert pipeline_events[1]["data"]["target"] == "notification"

        # Third handoff: passes (no contract for notification->output)
        assert pipeline_events[2]["data"]["passed"] is True
        assert pipeline_events[2]["data"]["source"] == "notification"

        # Payload masking worked
        assert pipeline_events[0]["data"]["payload"]["ssn"] == "***MASKED***"
        assert pipeline_events[0]["data"]["payload"]["customer_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_field_frequency_calculation(self):
        """
        Simulates what the DataFlow sidebar does: count field occurrences.
        This is a backend-verified version of the frontend logic.
        """
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        await fs.handoff("a", "b", {"name": "Alice", "score": 95})
        await fs.handoff("a", "b", {"name": "Bob", "age": 30})
        await fs.handoff("a", "b", {"name": "Charlie", "score": 88, "age": 25})

        all_events = fs.event_bus._history
        field_counts = {}
        for e in all_events:
            for key in e["data"].get("payload_keys", []):
                field_counts[key] = field_counts.get(key, 0) + 1

        assert field_counts["name"] == 3    # appears in all 3
        assert field_counts["score"] == 2   # appears in 2
        assert field_counts["age"] == 2     # appears in 2

    @pytest.mark.asyncio
    async def test_dashboard_serves_pipeline_via_api(self):
        """Full round-trip: handoff -> event bus -> API -> verify shapes."""
        fs = FailSafe(audit_db=":memory:", dashboard=False)
        fs.contract("c1", "a", "b", deny=["password"])
        tid = "api-pipeline-001"

        await fs.handoff("a", "b", {"user": "alice", "password": "secret"}, trace_id=tid)
        await fs.handoff("b", "c", {"result": "processed"}, trace_id=tid)

        app = create_app(fs)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            # Recent handoffs has both
            resp = await c.get("/api/handoffs/recent")
            handoffs = resp.json()
            assert len(handoffs) == 2

            # Detail for specific trace — returns the LAST matching event (reversed search)
            resp = await c.get(f"/api/handoffs/{tid}")
            detail = resp.json()
            assert detail["trace_id"] == tid
            # The API returns the most recent event with this trace_id (b->c)
            assert detail["source"] == "b"
            assert detail["target"] == "c"
            assert detail["payload"]["result"] == "processed"


# ===========================================================================
# 13. EVENT BUS HISTORY LIMITS AND ORDERING
# ===========================================================================

class TestEventBusHistoryBehavior:
    """The frontend fetches history on connect — verify it's correct."""

    def test_history_preserves_order(self, fs):
        for i in range(10):
            asyncio.run(fs.handoff("a", "b", {"order": i}))
        history = fs.event_bus._history
        orders = [e["data"]["payload"]["order"] for e in history]
        assert orders == list(range(10))

    def test_history_contains_all_event_types(self, fs):
        """All handoff events should be in history regardless of pass/fail."""
        fs.contract("c1", "a", "b", deny=["bad"])
        asyncio.run(fs.handoff("a", "b", {"ok": 1}))   # pass
        asyncio.run(fs.handoff("a", "b", {"bad": 1}))   # fail
        asyncio.run(fs.handoff("a", "b", {"ok": 2}))   # pass

        history = fs.event_bus._history
        assert len(history) == 3
        statuses = [e["data"]["passed"] for e in history]
        assert statuses == [True, False, True]

    def test_subscriber_receives_events_in_order(self, fs):
        """SSE subscribers get events in emission order."""
        async def _test():
            queue = fs.event_bus.subscribe()
            for i in range(5):
                await fs.handoff("a", "b", {"i": i})
            received = []
            for _ in range(5):
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                received.append(event["data"]["payload"]["i"])
            fs.event_bus.unsubscribe(queue)
            assert received == list(range(5))

        asyncio.run(_test())
