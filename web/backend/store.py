"""SQLite-backed run store — replaces the in-memory _runs dict.

The database is created automatically at web/backend/verdict_runs.db on first
use.  All reads and writes use short-lived connections (one per call) so the
store is safe to call from FastAPI's async handlers and from background threads
via asyncio.to_thread.

Public API
----------
run_store.save(run_id, data)   — persist or overwrite a run
run_store.get(run_id)          — fetch one run dict, or None
run_store.all_runs()           — list all runs, newest first (summary dicts)
run_store.get_full(run_id)     — fetch full report dict, or None
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_DB_PATH = Path(__file__).parent / "verdict_runs.db"
_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    target_system TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    pass_rate     REAL NOT NULL,
    total_tests   INTEGER NOT NULL,
    data          TEXT NOT NULL,
    label         TEXT
)
"""
_MIGRATION_ADD_LABEL = "ALTER TABLE runs ADD COLUMN label TEXT"


class RunStore:
    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(_DDL)
                try:
                    conn.execute(_MIGRATION_ADD_LABEL)
                except sqlite3.OperationalError:
                    pass  # column already exists
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, run_id: str, data: dict) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs
                        (run_id, target_system, timestamp, pass_rate, total_tests, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        data["target_system"],
                        data["timestamp"],
                        data["pass_rate"],
                        data["total_tests"],
                        json.dumps(data),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, run_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            conn.close()
        return json.loads(row["data"]) if row else None

    def all_runs(self) -> list[dict]:
        """Return lightweight summary dicts for every run, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT run_id, target_system, timestamp, pass_rate, total_tests, label
                FROM runs ORDER BY timestamp DESC
                """
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]

    def set_label(self, run_id: str, label: str | None) -> bool:
        """Set or clear the label for a run. Returns True if the run existed."""
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "UPDATE runs SET label = ? WHERE run_id = ?",
                    (label or None, run_id),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()


run_store = RunStore()
