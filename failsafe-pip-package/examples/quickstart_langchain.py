"""FailSafe + LangChain — 1-line observability.

This example shows the LangChain integration.
If you don't have langchain installed, it simulates the callback interface.

Run:
    python examples/quickstart_langchain.py
"""

import asyncio

from failsafe import observe


async def main():
    # THE ONE LINE:
    handler = observe(framework="langchain", dashboard=False)

    # Add a contract (optional — works without it too)
    handler.fs.contract(
        name="research-to-analysis",
        source="research_chain",
        target="analysis_chain",
        deny=["api_key", "internal_config"],
    )

    # Simulate what LangChain does internally when you pass the handler
    print("Simulating LangChain execution with FailSafe observing...\n")

    await handler.on_chain_start(
        {"name": "research_chain"},
        {"question": "What is AAPL's market cap?"},
    )

    await handler.on_tool_start({"name": "market_data_api"}, "AAPL")
    await handler.on_tool_end("$3.2T")

    await handler.on_chain_start(
        {"name": "analysis_chain"},
        {"data": "$3.2T"},
    )
    await handler.on_chain_end({
        "analysis": "AAPL is highly valued",
        "api_key": "sk-secret-123",  # This will be caught!
    })
    await handler.on_chain_end({"answer": "AAPL market cap is ~$3.2T"})

    # Check results
    print("Summary:")
    summary = handler.summary()
    print(f"   Chains seen: {summary['chains_seen']}")
    print(f"   Tools called: {summary['tools_called']}")
    print(f"   Handoffs: {len(summary['handoffs'])}")
    print(f"   Violations: {summary['total_violations']}")

    for v in summary["violations"]:
        print(f"\n   [{v['severity'].upper()}] {v['rule']}: {v['message']}")


if __name__ == "__main__":
    asyncio.run(main())
