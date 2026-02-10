"""Audit trail with in-memory and SQLite persistence."""

from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.models import HandoffValidationResult, ValidationResult, PolicySeverity


class AuditLogger:
    def __init__(self, db_path: Optional[str] = None):
        self._records: list[HandoffValidationResult] = []
        self._db_path = db_path
        
        if db_path:
            self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                handoff_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                contract_id TEXT,
                consumer_agent TEXT NOT NULL,
                provider_agent TEXT NOT NULL,
                direction TEXT NOT NULL,
                overall_result TEXT NOT NULL,
                is_blocked INTEGER NOT NULL,
                total_violations INTEGER NOT NULL,
                validation_duration_ms REAL,
                payload_json TEXT,
                violations_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    def log(self, result: HandoffValidationResult) -> None:
        self._records.append(result)
        
        if self._db_path:
            self._persist(result)
    
    def _persist(self, result: HandoffValidationResult) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """INSERT INTO audit_trail 
               (handoff_id, timestamp, contract_id, consumer_agent, provider_agent,
                direction, overall_result, is_blocked, total_violations,
                validation_duration_ms, payload_json, violations_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.handoff_id,
                result.timestamp.isoformat(),
                result.contract_id,
                result.consumer_agent,
                result.provider_agent,
                result.direction.value,
                result.overall_result.value,
                1 if result.is_blocked else 0,
                result.total_violations,
                result.validation_duration_ms,
                json.dumps(result.payload_snapshot) if result.payload_snapshot else None,
                json.dumps({
                    "schema": [v.to_dict() for v in result.schema_violations],
                    "policy": [v.to_dict() for v in result.policy_violations],
                    "authority": [v.to_dict() for v in result.authority_violations],
                }),
            )
        )
        conn.commit()
        conn.close()
    
    def get_all(self) -> list[HandoffValidationResult]:
        return list(self._records)
    
    def get_failures(self) -> list[HandoffValidationResult]:
        return [r for r in self._records if r.overall_result == ValidationResult.FAIL]
    
    def get_blocked(self) -> list[HandoffValidationResult]:
        return [r for r in self._records if r.is_blocked]
    
    def get_by_agent(self, agent_name: str) -> list[HandoffValidationResult]:
        return [
            r for r in self._records 
            if r.consumer_agent == agent_name or r.provider_agent == agent_name
        ]
    
    def get_by_contract(self, contract_id: str) -> list[HandoffValidationResult]:
        return [r for r in self._records if r.contract_id == contract_id]
    
    def generate_summary_report(self) -> dict:
        total = len(self._records)
        if total == 0:
            return {"total_handoffs": 0, "message": "No handoffs recorded"}
        
        passed = sum(1 for r in self._records if r.overall_result == ValidationResult.PASS)
        warned = sum(1 for r in self._records if r.overall_result == ValidationResult.WARN)
        failed = sum(1 for r in self._records if r.overall_result == ValidationResult.FAIL)
        blocked = sum(1 for r in self._records if r.is_blocked)
        
        all_violations = []
        for r in self._records:
            all_violations.extend(r.schema_violations)
            all_violations.extend(r.policy_violations)
            all_violations.extend(r.authority_violations)
        
        severity_counts = {}
        for v in all_violations:
            severity_counts[v.severity.value] = severity_counts.get(v.severity.value, 0) + 1
        
        rule_counts = {}
        for v in all_violations:
            key = f"{v.rule_id}: {v.rule_name}"
            rule_counts[key] = rule_counts.get(key, 0) + 1
        
        top_violations = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        agent_stats = {}
        for r in self._records:
            for agent in [r.consumer_agent, r.provider_agent]:
                if agent not in agent_stats:
                    agent_stats[agent] = {"total": 0, "passed": 0, "failed": 0, "blocked": 0}
                agent_stats[agent]["total"] += 1
                if r.overall_result == ValidationResult.PASS:
                    agent_stats[agent]["passed"] += 1
                elif r.overall_result == ValidationResult.FAIL:
                    agent_stats[agent]["failed"] += 1
                if r.is_blocked:
                    agent_stats[agent]["blocked"] += 1
        
        avg_duration = sum(r.validation_duration_ms for r in self._records) / total
        
        return {
            "report_generated": datetime.utcnow().isoformat(),
            "period": {
                "start": min(r.timestamp for r in self._records).isoformat(),
                "end": max(r.timestamp for r in self._records).isoformat(),
            },
            "summary": {
                "total_handoffs": total,
                "passed": passed,
                "warned": warned,
                "failed": failed,
                "blocked": blocked,
                "pass_rate": f"{(passed / total) * 100:.1f}%",
                "block_rate": f"{(blocked / total) * 100:.1f}%",
            },
            "violations": {
                "total": len(all_violations),
                "by_severity": severity_counts,
                "top_violations": [{"rule": r, "count": c} for r, c in top_violations],
            },
            "agents": agent_stats,
            "performance": {
                "avg_validation_ms": round(avg_duration, 2),
            },
        }
    
    def print_report(self) -> str:
        report = self.generate_summary_report()
        
        if report.get("summary", {}).get("total_handoffs", 0) == 0:
            return "📊 No handoffs recorded yet."
        
        lines = []
        lines.append("=" * 60)
        lines.append("  Failsafe Compliance Report")
        lines.append("=" * 60)
        lines.append(f"  Generated: {report['report_generated']}")
        lines.append(f"  Period: {report['period']['start'][:19]} → {report['period']['end'][:19]}")
        lines.append("")
        
        s = report["summary"]
        lines.append("  SUMMARY")
        lines.append("  " + "-" * 40)
        lines.append(f"  Total Handoffs:  {s['total_handoffs']}")
        lines.append(f"  ✅ Passed:       {s['passed']}")
        lines.append(f"  ⚠️  Warned:       {s['warned']}")
        lines.append(f"  ❌ Failed:       {s['failed']}")
        lines.append(f"  🚫 Blocked:      {s['blocked']}")
        lines.append(f"  Pass Rate:       {s['pass_rate']}")
        lines.append(f"  Block Rate:      {s['block_rate']}")
        lines.append("")
        
        v = report["violations"]
        if v["total"] > 0:
            lines.append("  VIOLATIONS")
            lines.append("  " + "-" * 40)
            for severity, count in v["by_severity"].items():
                icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(severity, "⚪")
                lines.append(f"  {icon} {severity.upper()}: {count}")
            lines.append("")
            
            if v["top_violations"]:
                lines.append("  TOP VIOLATIONS")
                lines.append("  " + "-" * 40)
                for item in v["top_violations"][:5]:
                    lines.append(f"  [{item['count']}x] {item['rule']}")
                lines.append("")
        
        lines.append("  AGENT STATISTICS")
        lines.append("  " + "-" * 40)
        for agent, stats in report["agents"].items():
            rate = (stats["passed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            lines.append(f"  {agent}: {stats['total']} handoffs, {rate:.0f}% pass rate")
        
        lines.append("")
        lines.append(f"  Avg validation time: {report['performance']['avg_validation_ms']:.2f}ms")
        lines.append("=" * 60)
        
        return "\n".join(lines)
