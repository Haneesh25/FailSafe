"""Tests for LLM-as-judge with mocked API responses."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from failsafe.core.llm_judge import LLMJudge
from failsafe.core.models import HandoffPayload


@pytest.fixture
def judge():
    return LLMJudge(api_key="test-key")


@pytest.fixture
def payload():
    return HandoffPayload(
        source="kyc_agent",
        target="onboarding_agent",
        data={
            "name": "Alice",
            "country": "DE",
            "verification_status": "verified",
        },
    )


class FakeResponse:
    """Fake httpx response with sync json() method."""

    def __init__(self, evaluations):
        self.status_code = 200
        self._data = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({"evaluations": evaluations})
                    }
                }
            ]
        }

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


@pytest.mark.asyncio
async def test_no_violations(judge, payload):
    evaluations = [
        {"rule": "Must include GDPR tag", "passed": True, "reason": "GDPR tag present", "severity": "high"}
    ]
    mock_post = AsyncMock(return_value=FakeResponse(evaluations))
    with patch("httpx.AsyncClient.post", mock_post):
        violations = await judge.evaluate(
            payload, ["Must include GDPR tag"]
        )
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_violation_detected(judge, payload):
    evaluations = [
        {
            "rule": "Must include GDPR tag for EU clients",
            "passed": False,
            "reason": "Payload contains EU country but no GDPR processing tag",
            "severity": "high",
        }
    ]
    mock_post = AsyncMock(return_value=FakeResponse(evaluations))
    with patch("httpx.AsyncClient.post", mock_post):
        violations = await judge.evaluate(
            payload, ["Must include GDPR tag for EU clients"]
        )
    assert len(violations) == 1
    assert violations[0].severity == "high"
    assert "GDPR" in violations[0].message


@pytest.mark.asyncio
async def test_no_api_key_returns_empty():
    judge = LLMJudge(api_key=None)
    payload = HandoffPayload(source="a", target="b", data={"x": 1})
    with patch.dict("os.environ", {}, clear=True):
        judge.api_key = None
        violations = await judge.evaluate(payload, ["some rule"])
    assert violations == []


@pytest.mark.asyncio
async def test_empty_rules(judge, payload):
    violations = await judge.evaluate(payload, [])
    assert violations == []


@pytest.mark.asyncio
async def test_multiple_rules(judge, payload):
    evaluations = [
        {"rule": "Rule 1", "passed": True, "reason": "OK", "severity": "low"},
        {"rule": "Rule 2", "passed": False, "reason": "Failed", "severity": "critical"},
        {"rule": "Rule 3", "passed": False, "reason": "Also failed", "severity": "medium"},
    ]
    mock_post = AsyncMock(return_value=FakeResponse(evaluations))
    with patch("httpx.AsyncClient.post", mock_post):
        violations = await judge.evaluate(
            payload, ["Rule 1", "Rule 2", "Rule 3"]
        )
    assert len(violations) == 2
    assert violations[0].severity == "critical"
    assert violations[1].severity == "medium"
