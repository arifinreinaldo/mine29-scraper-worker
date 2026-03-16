import sqlite3

import pytest

from src.dedup import DedupStore
from src.models import Job


def _make_job(uuid: str = "test-uuid", **kwargs) -> Job:
    defaults = dict(
        uuid=uuid,
        title="Test Job",
        company="Test Co",
        category="IT",
        min_salary=6000,
        max_salary=10000,
        position_level="Executive",
        employment_type="Full Time",
        posting_date="2026-03-15",
    )
    defaults.update(kwargs)
    return Job(**defaults)


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    with DedupStore(db_path) as s:
        yield s


class TestDedupStore:
    def test_new_job_is_not_seen(self, store):
        assert not store.is_seen("new-uuid")

    def test_mark_seen_then_is_seen(self, store):
        job = _make_job("abc-123")
        store.mark_seen([job])
        assert store.is_seen("abc-123")

    def test_filter_new_returns_only_unseen(self, store):
        j1 = _make_job("seen-1")
        j2 = _make_job("new-1")
        j3 = _make_job("new-2")

        store.mark_seen([j1])
        result = store.filter_new([j1, j2, j3])

        uuids = [j.uuid for j in result]
        assert "seen-1" not in uuids
        assert "new-1" in uuids
        assert "new-2" in uuids

    def test_filter_new_empty_list(self, store):
        assert store.filter_new([]) == []

    def test_mark_seen_is_idempotent(self, store):
        job = _make_job("dup-1")
        store.mark_seen([job])
        store.mark_seen([job])
        assert store.is_seen("dup-1")

    def test_mark_notified(self, store):
        job = _make_job("notif-1")
        store.mark_seen([job])
        store.mark_notified(["notif-1"])

        row = store._conn.execute(
            "SELECT notified_at FROM seen_jobs WHERE uuid = ?", ("notif-1",)
        ).fetchone()
        assert row[0] is not None

    def test_mark_notified_empty_list(self, store):
        store.mark_notified([])

    def test_cleanup_old_removes_expired(self, store):
        job = _make_job("old-1")
        store.mark_seen([job])
        store._conn.execute(
            "UPDATE seen_jobs SET first_seen_at = datetime('now', '-100 days') WHERE uuid = ?",
            ("old-1",),
        )
        store._conn.commit()

        removed = store.cleanup_old(90)
        assert removed == 1
        assert not store.is_seen("old-1")

    def test_cleanup_old_keeps_recent(self, store):
        job = _make_job("recent-1")
        store.mark_seen([job])

        removed = store.cleanup_old(90)
        assert removed == 0
        assert store.is_seen("recent-1")

    def test_wal_mode_enabled(self, store):
        result = store._conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_creates_parent_directory(self, tmp_path):
        db_path = tmp_path / "nested" / "dir" / "test.db"
        with DedupStore(db_path) as s:
            assert s.is_seen("x") is False
