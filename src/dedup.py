from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from src.models import Job

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    uuid TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    first_seen_at TEXT DEFAULT (datetime('now')),
    notified_at TEXT
);
"""


class DedupStore:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA)

    def is_seen(self, uuid: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_jobs WHERE uuid = ?", (uuid,)
        ).fetchone()
        return row is not None

    def filter_new(self, jobs: list[Job]) -> list[Job]:
        if not jobs:
            return []
        placeholders = ",".join("?" for _ in jobs)
        uuids = [j.uuid for j in jobs]
        rows = self._conn.execute(
            f"SELECT uuid FROM seen_jobs WHERE uuid IN ({placeholders})", uuids
        ).fetchall()
        seen = {r[0] for r in rows}
        return [j for j in jobs if j.uuid not in seen]

    def mark_seen(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        self._conn.executemany(
            """INSERT OR IGNORE INTO seen_jobs (uuid, category, title, company)
               VALUES (?, ?, ?, ?)""",
            [(j.uuid, j.category, j.title, j.company) for j in jobs],
        )
        self._conn.commit()

    def mark_notified(self, uuids: list[str]) -> None:
        if not uuids:
            return
        self._conn.executemany(
            "UPDATE seen_jobs SET notified_at = datetime('now') WHERE uuid = ?",
            [(u,) for u in uuids],
        )
        self._conn.commit()

    def cleanup_old(self, retention_days: int) -> int:
        cursor = self._conn.execute(
            "DELETE FROM seen_jobs WHERE first_seen_at < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        self._conn.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info("Cleaned up %d old job entries", count)
        return count

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> DedupStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
