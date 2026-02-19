"""Zero-code callback handler example.

Demonstrates how to add FailSafe observability to an existing LangChain
pipeline with just one line of code — no contracts required.

Usage:
    python examples/callback_observability.py
"""

import asyncio

from failsafe import FailSafe
from failsafe.integrations.langchain.callback import FailSafeCallbackHandler


async def main():
    # 1. Initialize FailSafe (no contracts, no policies — pure observability)
    fs = FailSafe(mode="warn", audit_db=":memory:")

    # 2. Create the callback handler
    handler = FailSafeCallbackHandler(failsafe=fs, mode="warn")

    # 3. Simulate what LangChain would do (chain starts/ends, tool calls)
    print("=" * 60)
    print("FailSafe Callback Observability Example")
    print("=" * 60)

    # Simulate chain execution
    print("\n--- Simulating LangChain execution ---")

    await handler.on_chain_start(
        {"name": "research_chain", "id": ["research_chain"]},
        {"question": "What is the market cap of AAPL?"},
    )
    print("  Chain started: research_chain")

    await handler.on_tool_start(
        {"name": "market_data_api"},
        "AAPL market cap",
    )
    print("  Tool called: market_data_api")

    await handler.on_tool_end("AAPL market cap: $3.2T")
    print("  Tool returned: AAPL market cap: $3.2T")

    # Nested chain
    await handler.on_chain_start(
        {"name": "analysis_chain", "id": ["analysis_chain"]},
        {"data": "AAPL market cap: $3.2T"},
    )
    print("  Nested chain started: analysis_chain")

    await handler.on_chain_end(
        {"analysis": "AAPL is the most valuable company by market cap"}
    )
    print("  Nested chain ended: analysis_chain")

    await handler.on_chain_end(
        {"answer": "AAPL has a market cap of ~$3.2 trillion"}
    )
    print("  Chain ended: research_chain")

    # 4. Review the audit log
    print("\n--- Audit Log ---")
    for entry in handler.audit_log:
        event = entry["event"]
        details = ""
        if "chain" in entry:
            details = f" chain={entry['chain']}"
        if "tool" in entry:
            details = f" tool={entry['tool']}"
        print(f"  [{entry['timestamp']}] {event}{details}")

    print(f"\n--- Violations detected: {len(handler.violations)} ---")
    if handler.violations:
        for v in handler.violations:
            print(f"  [{v.severity}] {v.rule}: {v.message}")
    else:
        print("  None (observability-only mode, no contracts defined)")

    print(f"\nTrace ID: {handler._trace_id}")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
