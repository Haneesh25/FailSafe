"""LLM-as-judge for natural language rules — calls Cerebras API."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from failsafe.core.models import HandoffPayload, Violation

DEFAULT_API_URL = "https://api.cerebras.ai/v1/chat/completions"
DEFAULT_MODEL = "llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are a compliance judge evaluating whether data passed between AI agents violates any rules.

You will be given:
1. A payload of data being passed from one agent to another
2. A list of natural language rules to evaluate

For each rule, determine if it is violated by the payload data.

Respond with ONLY valid JSON in this exact format:
{
  "evaluations": [
    {"rule": "<rule text>", "passed": true/false, "reason": "<explanation>", "severity": "low|medium|high|critical"}
  ]
}"""


class LLMJudge:
    """Evaluates natural language rules against handoff payloads using an LLM."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
    ):
        self.api_url = api_url
        self.api_key = api_key or os.environ.get("CEREBRAS_API_KEY")
        self.model = model

    async def evaluate(
        self, payload: HandoffPayload, nl_rules: list[str]
    ) -> list[Violation]:
        if not nl_rules or not self.api_key:
            return []

        prompt = self._build_prompt(payload, nl_rules)
        response = await self._call_llm(prompt)
        return self._parse_response(response, payload)

    def _build_prompt(self, payload: HandoffPayload, nl_rules: list[str]) -> str:
        rules_text = "\n".join(f"  {i + 1}. {r}" for i, r in enumerate(nl_rules))
        payload_text = json.dumps(payload.data, indent=2, default=str)

        return f"""Evaluate the following data payload against these rules:

Source agent: {payload.source}
Target agent: {payload.target}

Payload:
{payload_text}

Rules to evaluate:
{rules_text}

Return your evaluation as JSON."""

    async def _call_llm(self, prompt: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)

    def _parse_response(
        self, response: dict[str, Any], payload: HandoffPayload
    ) -> list[Violation]:
        violations: list[Violation] = []
        evaluations = response.get("evaluations", [])

        for ev in evaluations:
            if not ev.get("passed", True):
                violations.append(
                    Violation(
                        rule=f"nl_rule: {ev.get('rule', 'unknown')}",
                        severity=ev.get("severity", "medium"),
                        message=ev.get("reason", "Natural language rule violated"),
                        evidence={"llm_evaluation": ev},
                        source_agent=payload.source,
                        target_agent=payload.target,
                    )
                )

        return violations
