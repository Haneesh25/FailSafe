"""Persistent audit log — SQLite-backed."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import aiosqlite

from failsafe.core.models import HandoffPayload, ValidationResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handoff_id INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    contract_name TEXT NOT NULL,
    mode TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (handoff_id) REFERENCES handoffs (id)
);

CREATE TABLE IF NOT EXISTS violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    validation_id INTEGER NOT NULL,
    rule TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    field TEXT,
    evidence TEXT NOT NULL,
    FOREIGN KEY (validation_id) REFERENCES validations (id)
);

CREATE INDEX IF NOT EXISTS idx_handoffs_trace ON handoffs (trace_id);
CREATE INDEX IF NOT EXISTS idx_handoffs_source ON handoffs (source);
CREATE INDEX IF NOT EXISTS idx_handoffs_target ON handoffs (target);
CREATE INDEX IF NOT EXISTS idx_validations_passed ON validations (passed);
CREATE INDEX IF NOT EXISTS idx_violations_severity ON violations (severity);
"""


class AuditLog:
    """Persistent audit log for all validations."""

    def __init__(self, db_path: str = "failsafe_audit.db") -> None:
        self._initialized = False
        # For :memory: databases, use a temp file so all connections share the same db
        if db_path == ":memory:":
            import tempfile
            self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            self.db_path = self._tmp.name
        else:
            self._tmp = None
            self.db_path = db_path

    def _connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.db_path)

    async def _ensure_tables(self) -> None:
        if self._initialized:
            return
        async with self._connect() as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    async def record(
        self, handoff: HandoffPayload, result: ValidationResult
    ) -> None:
        await self._ensure_tables()
        payload_hash = hashlib.sha256(
            json.dumps(handoff.data, sort_keys=True, default=str).encode()
        ).hexdigest()

        async with self._connect() as db:
            cursor = await db.execute(
                "INSERT INTO handoffs (source, target, payload_hash, trace_id, timestamp) VALUES (?, ?, ?, ?, ?)",
                (
                    handoff.source,
                    handoff.target,
                    payload_hash,
                    handoff.trace_id,
                    handoff.timestamp.isoformat(),
                ),
            )
            handoff_id = cursor.lastrowid

            cursor = await db.execute(
                "INSERT INTO validations (handoff_id, passed, contract_name, mode, duration_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    handoff_id,
                    1 if result.passed else 0,
                    result.contract_name,
                    result.validation_mode,
                    result.duration_ms,
                    result.timestamp.isoformat(),
                ),
            )
            validation_id = cursor.lastrowid

            for v in result.violations:
                await db.execute(
                    "INSERT INTO violations (validation_id, rule, severity, message, field, evidence) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        validation_id,
                        v.rule,
                        v.severity,
                        v.message,
                        v.field,
                        json.dumps(v.evidence, default=str),
                    ),
                )

            await db.commit()

    async def query(
        self,
        source: str | None = None,
        target: str | None = None,
        passed: bool | None = None,
        trace_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        await self._ensure_tables()
        conditions: list[str] = []
        params: list[Any] = []

        if source:
            conditions.append("h.source = ?")
            params.append(source)
        if target:
            conditions.append("h.target = ?")
            params.append(target)
        if passed is not None:
            conditions.append("v.passed = ?")
            params.append(1 if passed else 0)
        if trace_id:
            conditions.append("h.trace_id = ?")
            params.append(trace_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT h.id as handoff_id, h.source, h.target, h.trace_id, h.timestamp,
                       v.passed, v.contract_name, v.mode, v.duration_ms
                FROM handoffs h
                JOIN validations v ON v.handoff_id = h.id
                {where}
                ORDER BY h.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                params,
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_violations(self, validation_id: int) -> list[dict[str, Any]]:
        await self._ensure_tables()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM violations WHERE validation_id = ?",
                (validation_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def export_report(
        self, start: datetime, end: datetime
    ) -> dict[str, Any]:
        await self._ensure_tables()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN v.passed = 1 THEN 1 ELSE 0 END) as passed,
                       SUM(CASE WHEN v.passed = 0 THEN 1 ELSE 0 END) as failed,
                       AVG(v.duration_ms) as avg_duration_ms
                FROM handoffs h
                JOIN validations v ON v.handoff_id = h.id
                WHERE h.timestamp BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            )
            summary = dict(await cursor.fetchone())

            cursor = await db.execute(
                """
                SELECT viol.severity, COUNT(*) as count
                FROM handoffs h
                JOIN validations v ON v.handoff_id = h.id
                JOIN violations viol ON viol.validation_id = v.id
                WHERE h.timestamp BETWEEN ? AND ?
                GROUP BY viol.severity
                """,
                (start.isoformat(), end.isoformat()),
            )
            severity_rows = await cursor.fetchall()
            by_severity = {row["severity"]: row["count"] for row in severity_rows}

            return {
                "period": {"start": start.isoformat(), "end": end.isoformat()},
                "summary": summary,
                "violations_by_severity": by_severity,
            }
