"""Tests for scheduler.db — the SQLite persistence layer for scheduled tasks."""

import sqlite3
from datetime import datetime, timezone

import pytest

from scheduler.db import (
    get_active_tasks,
    get_all_tasks,
    init_db,
    insert_task,
    update_task_fire_at,
    update_task_status,
)


@pytest.fixture
def db_path(tmp_path):
    """Use a temporary file database for test isolation."""
    path = str(tmp_path / "test_scheduler.db")
    init_db(path)
    return path


# ---- Tests ----


def test_init_db_creates_table(tmp_path):
    """init_db is idempotent — calling it twice must not raise."""
    path = str(tmp_path / "idempotent_test.db")
    init_db(path)
    init_db(path)  # second call should not raise

    # Verify the table exists by querying it
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_insert_and_get_active(db_path):
    """An inserted active task appears in get_active_tasks."""
    now = datetime.now(timezone.utc).isoformat()
    task_id = insert_task(
        db_path=db_path,
        task_type="once",
        label="Test reminder",
        agent_prompt="Say hello",
        fire_at=now,
        cron_expr=None,
    )
    assert isinstance(task_id, int)
    assert task_id > 0

    active = get_active_tasks(db_path)
    assert len(active) == 1
    assert active[0]["id"] == task_id
    assert active[0]["label"] == "Test reminder"
    assert active[0]["status"] == "active"


def test_update_status_to_fired(db_path):
    """After updating status to 'fired', the task no longer appears in get_active_tasks."""
    now = datetime.now(timezone.utc).isoformat()
    task_id = insert_task(
        db_path=db_path,
        task_type="once",
        label="Fire me",
        agent_prompt="Do something",
        fire_at=now,
        cron_expr=None,
    )

    update_task_status(db_path, task_id, "fired")

    active = get_active_tasks(db_path)
    assert len(active) == 0


def test_get_all_tasks_includes_cancelled(db_path):
    """get_all_tasks returns tasks regardless of status, including cancelled."""
    now = datetime.now(timezone.utc).isoformat()
    id1 = insert_task(
        db_path=db_path,
        task_type="once",
        label="Active task",
        agent_prompt=None,
        fire_at=now,
        cron_expr=None,
    )
    id2 = insert_task(
        db_path=db_path,
        task_type="recurring",
        label="Cancelled task",
        agent_prompt="Prompt",
        fire_at=now,
        cron_expr="*/5 * * * *",
    )
    update_task_status(db_path, id2, "cancelled")

    all_tasks = get_all_tasks(db_path)
    assert len(all_tasks) == 2

    ids = {t["id"] for t in all_tasks}
    assert ids == {id1, id2}

    statuses = {t["id"]: t["status"] for t in all_tasks}
    assert statuses[id1] == "active"
    assert statuses[id2] == "cancelled"


def test_update_fire_at(db_path):
    """update_task_fire_at correctly changes the fire_at value."""
    original_time = "2026-04-01T10:00:00+00:00"
    new_time = "2026-04-01T10:05:00+00:00"

    task_id = insert_task(
        db_path=db_path,
        task_type="recurring",
        label="Recurring task",
        agent_prompt="Check status",
        fire_at=original_time,
        cron_expr="*/5 * * * *",
    )

    update_task_fire_at(db_path, task_id, new_time)

    all_tasks = get_all_tasks(db_path)
    assert len(all_tasks) == 1
    assert all_tasks[0]["fire_at"] == new_time
