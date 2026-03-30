"""Tests for scheduler.manager — the SchedulerManager core logic."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scheduler.db import get_all_tasks, get_active_tasks, init_db, insert_task
from scheduler.manager import SchedulerManager


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test_scheduler.db")
    init_db(path)
    return path


@pytest.fixture
def broadcast_fn():
    return AsyncMock()


@pytest.fixture
def chat_fn():
    return AsyncMock(return_value="OK, I'll do that.")


@pytest.fixture
def manager(db_path, broadcast_fn, chat_fn):
    return SchedulerManager(broadcast_fn=broadcast_fn, chat_fn=chat_fn, db_path=db_path)


# ---- create_task ----

@pytest.mark.asyncio
async def test_create_task_registers_handle(manager):
    """create_task should insert into DB and register an asyncio handle."""
    fire_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    task_id = await manager.create_task(
        type="once", label="Test reminder", fire_at=fire_at,
    )
    assert task_id in manager._handles
    assert manager._handles[task_id] is not None


# ---- cancel_task ----

@pytest.mark.asyncio
async def test_cancel_task_cancels_handle(manager, db_path):
    """cancel_task should cancel the handle and mark DB status=cancelled."""
    fire_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    task_id = await manager.create_task(
        type="once", label="Cancel me", fire_at=fire_at,
    )
    result = await manager.cancel_task(task_id)
    assert result is True
    assert task_id not in manager._handles

    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "cancelled"


# ---- _on_fire: reminder (no agent_prompt) ----

@pytest.mark.asyncio
async def test_on_fire_reminder_broadcasts(manager, broadcast_fn, db_path):
    """Firing a reminder (no agent_prompt) should broadcast scheduled_task_fire."""
    fire_at = (datetime.now(timezone.utc) + timedelta(seconds=0.1)).isoformat()
    task_id = await manager.create_task(
        type="once", label="Ring ring", fire_at=fire_at,
    )
    await manager._on_fire(task_id)

    # Check that broadcast was called with scheduled_task_fire
    calls = broadcast_fn.call_args_list
    fire_calls = [c for c in calls if c[0][0].get("type") == "scheduled_task_fire"]
    assert len(fire_calls) >= 1


# ---- _on_fire: action (with agent_prompt) ----

@pytest.mark.asyncio
async def test_on_fire_action_calls_chat(manager, chat_fn, broadcast_fn, db_path):
    """Firing a task with agent_prompt should call chat_fn."""
    fire_at = (datetime.now(timezone.utc) + timedelta(seconds=0.1)).isoformat()
    task_id = await manager.create_task(
        type="once", label="Action task", fire_at=fire_at,
        agent_prompt="Check the weather",
    )
    await manager._on_fire(task_id)

    chat_fn.assert_called_once_with("Check the weather")

    # Should also broadcast the assistant response
    calls = broadcast_fn.call_args_list
    assistant_calls = [c for c in calls if c[0][0].get("type") == "assistant_message"]
    assert len(assistant_calls) >= 1


# ---- _on_fire: recurring reschedules ----

@pytest.mark.asyncio
async def test_on_fire_recurring_reschedules(manager, db_path):
    """A recurring task should be rescheduled after firing."""
    fire_at = (datetime.now(timezone.utc) + timedelta(seconds=0.1)).isoformat()
    task_id = await manager.create_task(
        type="recurring", label="Every 5 min", fire_at=fire_at,
        cron_expr="*/5 * * * *",
    )
    original_fire_at = fire_at
    await manager._on_fire(task_id)

    # Handle should be re-registered
    assert task_id in manager._handles

    # fire_at in DB should be updated to a future time
    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["fire_at"] != original_fire_at
    assert task["status"] == "active"


# ---- _on_fire: one-time marks fired ----

@pytest.mark.asyncio
async def test_on_fire_one_time_marks_fired(manager, db_path):
    """A one-time task should be marked as fired after firing."""
    fire_at = (datetime.now(timezone.utc) + timedelta(seconds=0.1)).isoformat()
    task_id = await manager.create_task(
        type="once", label="One shot", fire_at=fire_at,
    )
    await manager._on_fire(task_id)

    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "fired"
    assert task_id not in manager._handles


# ---- start: recovery ----

@pytest.mark.asyncio
async def test_start_recovers_active_tasks(manager, db_path):
    """start() should load active tasks from DB and register handles."""
    fire_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    insert_task(
        db_path=db_path, task_type="once", label="Future task",
        agent_prompt=None, fire_at=fire_at, cron_expr=None,
    )
    await manager.start()
    assert len(manager._handles) == 1


@pytest.mark.asyncio
async def test_start_fires_overdue_one_time(manager, db_path, broadcast_fn):
    """start() should fire overdue one-time tasks immediately."""
    fire_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    task_id = insert_task(
        db_path=db_path, task_type="once", label="Overdue task",
        agent_prompt=None, fire_at=fire_at, cron_expr=None,
    )
    await manager.start()

    # Give the event loop a tick to run the call_later(0, ...) callback
    await asyncio.sleep(0.05)

    # The overdue task should have been registered with delay=0
    # After firing, it should be marked as fired
    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "fired"


@pytest.mark.asyncio
async def test_start_skips_overdue_recurring(manager, db_path):
    """start() should advance overdue recurring tasks to next cycle."""
    fire_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    task_id = insert_task(
        db_path=db_path, task_type="recurring", label="Overdue recurring",
        agent_prompt=None, fire_at=fire_at, cron_expr="*/5 * * * *",
    )
    await manager.start()

    # Should be registered with a future fire_at
    assert task_id in manager._handles
    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    new_fire_at = datetime.fromisoformat(task["fire_at"])
    assert new_fire_at > datetime.now(timezone.utc)


# ---- reactivate_task ----

@pytest.mark.asyncio
async def test_reactivate_expired_one_time_returns_error(manager, db_path):
    """Reactivating an expired one-time task should return an error message."""
    from scheduler.db import update_task_status
    fire_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    task_id = insert_task(
        db_path=db_path, task_type="once", label="Expired",
        agent_prompt=None, fire_at=fire_at, cron_expr=None,
    )
    update_task_status(db_path, task_id, "fired")

    result = await manager.reactivate_task(task_id)
    assert isinstance(result, str)
    assert "过期" in result


@pytest.mark.asyncio
async def test_reactivate_recurring_reschedules(manager, db_path):
    """Reactivating a cancelled recurring task should reschedule it."""
    from scheduler.db import update_task_status
    fire_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    task_id = insert_task(
        db_path=db_path, task_type="recurring", label="Recurring cancelled",
        agent_prompt=None, fire_at=fire_at, cron_expr="*/5 * * * *",
    )
    update_task_status(db_path, task_id, "cancelled")

    result = await manager.reactivate_task(task_id)
    assert result is None  # success, no error

    assert task_id in manager._handles
    tasks = get_all_tasks(db_path)
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["status"] == "active"
    new_fire_at = datetime.fromisoformat(task["fire_at"])
    assert new_fire_at > datetime.now(timezone.utc)


# ---- shutdown ----

@pytest.mark.asyncio
async def test_shutdown_cancels_all_handles(manager):
    """shutdown() should cancel all pending handles."""
    fire_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    await manager.create_task(type="once", label="Task 1", fire_at=fire_at)
    await manager.create_task(type="once", label="Task 2", fire_at=fire_at)
    assert len(manager._handles) == 2

    await manager.shutdown()
    assert len(manager._handles) == 0


# ---- list_tasks ----

@pytest.mark.asyncio
async def test_list_tasks_returns_all(manager, db_path):
    """list_tasks returns all tasks from DB."""
    fire_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    await manager.create_task(type="once", label="A", fire_at=fire_at)
    await manager.create_task(type="once", label="B", fire_at=fire_at)

    tasks = manager.list_tasks()
    assert len(tasks) == 2
    labels = {t["label"] for t in tasks}
    assert labels == {"A", "B"}
