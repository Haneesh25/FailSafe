"""python examples/demo.py"""

import asyncio
from failsafe import FailSafe


async def main():

    fs = FailSafe(mode="block", audit_db=":memory:")

    fs.register_agent("research_agent", description="Searches and retrieves sources")
    fs.register_agent("writer_agent", description="Drafts content from research")
    fs.register_agent("review_agent", description="Reviews and approves drafts")

    fs.contract(
        name="research-to-writer",
        source="research_agent",
        target="writer_agent",
        allow=["query", "sources", "summary"],
        deny=["api_key", "internal_config"],
        require=["query", "sources"],
    )

    fs.contract(
        name="writer-to-review",
        source="writer_agent",
        target="review_agent",
        allow=["draft", "sources", "metadata"],
        deny=["raw_prompt", "system_prompt"],
        require=["draft"],
        rules=[{"type": "field_value", "field": "draft", "min_length": 1}],
    )

    # clean handoff — passes
    r1 = await fs.handoff(
        source="research_agent",
        target="writer_agent",
        payload={"query": "AI safety", "sources": ["arxiv.org/1234", "arxiv.org/5678"], "summary": "Overview of recent alignment research"},
    )
    print(f"research → writer:  {'PASS' if r1.passed else 'FAIL'}")

    # leaking secrets — blocked
    r2 = await fs.handoff(
        source="research_agent",
        target="writer_agent",
        payload={"query": "AI safety", "sources": ["arxiv.org/1234"], "api_key": "sk-secret-123"},
    )
    print(f"research → writer:  {'PASS' if r2.passed else 'FAIL'} — {r2.violations[0].message}")

    # missing required field — blocked
    r3 = await fs.handoff(
        source="writer_agent",
        target="review_agent",
        payload={"sources": ["arxiv.org/1234"]},
    )
    print(f"writer → review:    {'PASS' if r3.passed else 'FAIL'} — {r3.violations[0].message}")

    # clean review handoff — passes
    r4 = await fs.handoff(
        source="writer_agent",
        target="review_agent",
        payload={"draft": "AI safety is a growing field...", "sources": ["arxiv.org/1234"]},
    )
    print(f"writer → review:    {'PASS' if r4.passed else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
