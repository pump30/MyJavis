"""Tests for agent/tools/scheduler_tools.py — the 3 agent tool functions."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.tools.scheduler_tools import schedule_task, list_tasks, cancel_task


@pytest.fixture
def mock_scheduler():
    scheduler = AsyncMock()
    scheduler.create_task = AsyncMock(return_value=42)
    scheduler.cancel_task = AsyncMock(return_value=True)
    scheduler.list_tasks = MagicMock(return_value=[
        {"id": 1, "type": "reminder", "label": "Test", "status": "active",
         "fire_at": "2026-03-30T15:00:00+00:00", "cron_expr": None,
         "agent_prompt": None},
    ])
    return scheduler


# ---- schedule_task with delay_seconds ----

@pytest.mark.asyncio
async def test_schedule_task_with_delay_seconds(mock_scheduler):
    """Creates task with delay_seconds — should compute fire_at from now + delay."""
    result = await schedule_task(mock_scheduler, {
        "type": "reminder",
        "label": "Take a break",
        "delay_seconds": 300,
    })

    mock_scheduler.create_task.assert_called_once()
    call_kwargs = mock_scheduler.create_task.call_args
    assert call_kwargs[1]["type"] == "reminder"
    assert call_kwargs[1]["label"] == "Take a break"
    # fire_at should be an ISO string
    fire_at = datetime.fromisoformat(call_kwargs[1]["fire_at"])
    assert fire_at > datetime.now(timezone.utc)
    assert "42" in result  # task id in confirmation


# ---- schedule_task with fire_at ----

@pytest.mark.asyncio
async def test_schedule_task_with_fire_at(mock_scheduler):
    """Creates task with absolute fire_at ISO8601 time."""
    fire_at_str = "2026-03-30T15:00:00+08:00"
    result = await schedule_task(mock_scheduler, {
        "type": "reminder",
        "label": "Meeting reminder",
        "fire_at": fire_at_str,
    })

    mock_scheduler.create_task.assert_called_once()
    call_kwargs = mock_scheduler.create_task.call_args[1]
    assert call_kwargs["type"] == "reminder"
    assert call_kwargs["label"] == "Meeting reminder"
    # fire_at should be preserved (parsed and re-serialized)
    assert "42" in result


# ---- schedule_task recurring requires cron ----

@pytest.mark.asyncio
async def test_schedule_task_recurring_requires_cron(mock_scheduler):
    """Recurring task without cron_expr should return an error."""
    result = await schedule_task(mock_scheduler, {
        "type": "recurring",
        "label": "Daily standup",
    })

    mock_scheduler.create_task.assert_not_called()
    assert "error" in result.lower() or "cron" in result.lower()


# ---- schedule_task missing time returns error ----

@pytest.mark.asyncio
async def test_schedule_task_missing_time_returns_error(mock_scheduler):
    """Non-recurring task without fire_at or delay_seconds should return error."""
    result = await schedule_task(mock_scheduler, {
        "type": "reminder",
        "label": "No time specified",
    })

    mock_scheduler.create_task.assert_not_called()
    assert "error" in result.lower() or "time" in result.lower() or "fire_at" in result.lower()


# ---- schedule_task recurring with cron_expr (no fire_at/delay) ----

@pytest.mark.asyncio
async def test_schedule_task_recurring_with_cron(mock_scheduler):
    """Recurring task with cron_expr should compute first fire_at from cron."""
    result = await schedule_task(mock_scheduler, {
        "type": "recurring",
        "label": "Every morning",
        "cron_expr": "0 9 * * *",
    })

    mock_scheduler.create_task.assert_called_once()
    call_kwargs = mock_scheduler.create_task.call_args[1]
    assert call_kwargs["cron_expr"] == "0 9 * * *"
    fire_at = datetime.fromisoformat(call_kwargs["fire_at"])
    assert fire_at > datetime.now(timezone.utc)
    assert "42" in result


# ---- list_tasks ----

@pytest.mark.asyncio
async def test_list_tasks_returns_json(mock_scheduler):
    """list_tasks should return a JSON string of all tasks."""
    result = await list_tasks(mock_scheduler)

    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["id"] == 1
    assert parsed[0]["label"] == "Test"


# ---- cancel_task ----

@pytest.mark.asyncio
async def test_cancel_task_calls_manager(mock_scheduler):
    """cancel_task should call manager.cancel_task and return confirmation."""
    result = await cancel_task(mock_scheduler, 42)

    mock_scheduler.cancel_task.assert_called_once_with(42)
    assert "42" in result
