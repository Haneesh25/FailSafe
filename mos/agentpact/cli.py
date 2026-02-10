"""Command-line interface for Failsafe."""

from __future__ import annotations
import argparse
import importlib.util
import os
import sys
from datetime import datetime
from typing import Optional

from .core.models import (
    HandoffValidationResult,
    PolicySeverity,
    ValidationResult,
)


# ANSI escape codes (stdlib only)
class _C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    BRIGHT_RED = "\033[91m"


def _ts(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now()).strftime("%H:%M:%S")


def _dur(ms: float) -> str:
    if ms < 1:
        return f"{ms:.2f}ms"
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.1f}s"


_SEV_STYLE = {
    "critical": (_C.BRIGHT_RED, "\U0001f534"),
    "high":     (_C.YELLOW,     "\U0001f7e0"),
    "medium":   (_C.BLUE,       "\U0001f7e1"),
    "low":      (_C.DIM,        "\U0001f535"),
}


def print_validation(result: HandoffValidationResult, verbose: bool = False) -> None:
    """Print a single validation result with colored terminal output."""
    ts = _ts(result.timestamp)
    dur = _dur(result.validation_duration_ms)

    if result.overall_result == ValidationResult.PASS:
        icon, sc, st = "\u2705", _C.GREEN, "PASS"
    elif result.is_blocked:
        icon, sc, st = "\u274c", _C.RED, "FAIL"
    else:
        icon, sc, st = "\u26a0\ufe0f ", _C.YELLOW, "WARN"

    handoff = f"{result.consumer_agent} \u2192 {result.provider_agent}"
    blocked = f"  {_C.BRIGHT_RED}[BLOCKED]{_C.RESET}" if result.is_blocked else ""

    print(
        f"{_C.DIM}{ts}{_C.RESET} "
        f"{icon} "
        f"{_C.CYAN}{handoff:<40}{_C.RESET} "
        f"{sc}{st:>4}{_C.RESET}  "
        f"{result.total_violations} violations  "
        f"{_C.DIM}{dur}{_C.RESET}"
        f"{blocked}"
    )

    if result.total_violations > 0 and verbose:
        all_v = sorted(
            result.schema_violations + result.policy_violations + result.authority_violations,
            key=lambda v: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(v.severity.value, 9),
        )
        limit = 5
        for i, v in enumerate(all_v[:limit]):
            tree = "\u2514\u2500" if i == min(len(all_v), limit) - 1 else "\u251c\u2500"
            color, sev_icon = _SEV_STYLE.get(v.severity.value, (_C.DIM, "\u26aa"))
            msg = v.message[:80] + "..." if len(v.message) > 80 else v.message
            print(
                f"         {_C.DIM}{tree}{_C.RESET} "
                f"{sev_icon} {color}{v.severity.value.upper()}{_C.RESET} "
                f"{_C.BOLD}{v.rule_id}{_C.RESET}: {msg}"
            )
        if len(all_v) > limit:
            print(f"         {_C.DIM}... and {len(all_v) - limit} more{_C.RESET}")

    if result.total_violations > 0:
        print()


def _cmd_watch(args: argparse.Namespace) -> None:
    if not args.script:
        print(f"{_C.RED}Usage: failsafe watch <script.py>{_C.RESET}")
        sys.exit(1)
    if not os.path.exists(args.script):
        print(f"{_C.RED}File not found: {args.script}{_C.RESET}")
        sys.exit(1)

    print(f"\n{_C.BOLD}Failsafe v0.1.0{_C.RESET} \u2014 watching handoffs...\n")

    os.environ["FAILSAFE_WATCH_MODE"] = "1"
    if args.verbose:
        os.environ["FAILSAFE_VERBOSE"] = "1"

    spec = importlib.util.spec_from_file_location("__failsafe_script__", args.script)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules["__failsafe_script__"] = module
        try:
            spec.loader.exec_module(module)
        except SystemExit:
            pass
        except Exception as e:
            print(f"{_C.RED}Error: {e}{_C.RESET}")
            sys.exit(1)


def _cmd_demo(args: argparse.Namespace) -> None:
    from .api import Failsafe
    from datetime import timezone

    print(f"\n{_C.BOLD}Failsafe v0.1.0{_C.RESET} \u2014 running demo...\n")

    fs = Failsafe()
    verbose = args.verbose
    fs._interceptor.on_validation(lambda r: print_validation(r, verbose=verbose))

    fs.agent("customer_service", authority="read_only",
             compliance=["SOX", "SEC"], allowed_domains=["customer_data", "pii"],
             max_classification="confidential")
    fs.agent("research_agent", authority="read_write",
             compliance=["SOX", "SEC", "FINRA"], allowed_domains=["financial_records", "market_data"],
             max_classification="restricted")
    fs.agent("trading_agent", authority="execute",
             compliance=["SOX", "SEC", "FINRA"], allowed_domains=["financial_records", "market_data"],
             max_classification="restricted")

    fs.contract("customer_service", "research_agent", fields={
        "customer_id": {"type": "string", "pattern": r"^CUST-\d{6}$", "pii": True},
        "request_type": {"type": "string", "enum": ["portfolio_review", "rebalance_request", "risk_assessment"]},
        "account_id": {"type": "string", "pattern": r"^(ACCT-\d{8}|\*{4}\d{4})$"},
    }, authority="read_only", compliance=["SOX", "SEC"])

    fs.contract("research_agent", "trading_agent", fields={
        "symbol": {"type": "string", "pattern": r"^[A-Z]{1,5}$"},
        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "amount": {"type": "number", "min_value": 0, "max_value": 500000, "financial_data": True},
        "rationale": {"type": "string", "max_length": 1000},
    }, authority="read_write", compliance=["SOX", "SEC", "FINRA"])

    now = datetime.now(timezone.utc).isoformat()
    meta = lambda req: {"action": "query", "request_id": req, "timestamp": now, "initiator": "demo"}

    # 1) Valid handoff
    print(f"{_C.DIM}--- Scenario 1: Valid request ---{_C.RESET}")
    fs.validate("customer_service", "research_agent",
                {"customer_id": "CUST-123456", "request_type": "portfolio_review", "account_id": "ACCT-00112233"},
                meta("REQ-001"))

    # 2) Valid trade
    print(f"{_C.DIM}--- Scenario 2: Valid trade recommendation ---{_C.RESET}")
    fs.validate("research_agent", "trading_agent",
                {"symbol": "AAPL", "action": "buy", "amount": 5000.0, "rationale": "Portfolio underweight in tech."},
                {"action": "recommend", "request_id": "REQ-002", "timestamp": now, "initiator": "research"})

    # 3) SSN leak
    print(f"{_C.DIM}--- Scenario 3: SSN in payload ---{_C.RESET}")
    fs.validate("research_agent", "trading_agent",
                {"symbol": "TSLA", "action": "buy", "amount": 3000.0,
                 "rationale": "Client (SSN: 456-78-9012) wants EV exposure"},
                {"action": "recommend", "request_id": "REQ-003", "timestamp": now, "initiator": "research"})

    # 4) Large transaction, no approval
    print(f"{_C.DIM}--- Scenario 4: Large tx without approval ---{_C.RESET}")
    fs.validate("research_agent", "trading_agent",
                {"symbol": "GOOGL", "action": "buy", "amount": 75000.0, "rationale": "Major rebalancing"},
                {"action": "recommend", "request_id": "REQ-004", "timestamp": now, "initiator": "research"})

    # 5) Schema violation
    print(f"{_C.DIM}--- Scenario 5: Bad customer ID ---{_C.RESET}")
    fs.validate("customer_service", "research_agent",
                {"customer_id": "BAD-FORMAT", "request_type": "rebalance_request", "account_id": "ACCT-00112233"},
                meta("REQ-005"))

    # 6) No contract
    print(f"{_C.DIM}--- Scenario 6: No contract (authority escalation) ---{_C.RESET}")
    fs.validate("customer_service", "trading_agent",
                {"symbol": "HACK", "action": "buy", "amount": 50000.0, "rationale": "Direct trade attempt"},
                {"action": "trade", "request_id": "REQ-006", "timestamp": now, "initiator": "customer_service"})

    print(f"\n{_C.DIM}{'=' * 60}{_C.RESET}")
    print(fs.report())


def _cmd_report(args: argparse.Namespace) -> None:
    from .audit.logger import AuditLogger

    db = getattr(args, "db", None)
    if not db:
        print(f"{_C.YELLOW}No audit records (specify --db path/to/audit.db){_C.RESET}")
        return
    if not os.path.exists(db):
        print(f"{_C.RED}Database not found: {db}{_C.RESET}")
        sys.exit(1)

    audit = AuditLogger(db_path=db)
    print(audit.print_report())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="failsafe",
        description="Contract testing and compliance validation for multi-agent AI systems",
    )
    sub = parser.add_subparsers(dest="command")

    w = sub.add_parser("watch", help="Stream validation events from a script")
    w.add_argument("script", nargs="?", help="Python script to run")
    w.add_argument("-v", "--verbose", action="store_true", help="Show violation details")

    d = sub.add_parser("demo", help="Run built-in financial agents demo")
    d.add_argument("-v", "--verbose", action="store_true", help="Show violation details")

    r = sub.add_parser("report", help="Print compliance report from audit DB")
    r.add_argument("--db", help="Path to SQLite audit database")

    args = parser.parse_args()

    if args.command == "watch":
        _cmd_watch(args)
    elif args.command == "demo":
        _cmd_demo(args)
    elif args.command == "report":
        _cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
