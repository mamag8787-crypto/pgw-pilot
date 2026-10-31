"""Хранилище прогонов: SQLite, таблица runs.

    DB_PATH — путь к файлу БД (по умолчанию ./data/runs.sqlite)
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    client TEXT NOT NULL,
    material_id TEXT,
    step_index INTEGER,
    prompt TEXT NOT NULL,
    output TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts);
"""


class RunStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.environ.get("DB_PATH", os.path.join("data", "runs.sqlite"))
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def add(self, client: str, material_id: str | None, step_index: int | None, prompt: str, output: str) -> str:
        run_id = uuid.uuid4().hex[:16]
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO runs(id, ts, client, material_id, step_index, prompt, output) VALUES (?,?,?,?,?,?,?)",
                (run_id, time.time(), client, material_id, step_index, prompt, output),
            )
        return run_id

    def stats(self) -> dict:
        with self._lock, self._connect() as con:
            total = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            day = con.execute("SELECT COUNT(*) FROM runs WHERE ts > ?", (time.time() - 86400,)).fetchone()[0]
        return {"total": total, "last_24h": day}
