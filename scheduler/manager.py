"""SchedulerManager — singleton that owns all scheduling logic.

Manages asyncio timer handles for scheduled tasks, persisted via scheduler.db.
Injected with broadcast_fn (WebSocket broadcast) and chat_fn (AI agent chat).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional

from croniter import croniter

from scheduler.db import (
    DEFAULT_DB_PATH,
    get_active_tasks,
    get_all_tasks,
    insert_task,
    update_task_fire_at,
    update_task_status,
)

logger = logging.getLogger(__name__)


class SchedulerManager:
    def __init__(
        self,
        broadcast_fn: Callable[[dict], Awaitable[None]],
        chat_fn: Callable[[str], Awaitable[str]],
        db_path: str = DEFAULT_DB_PATH,
    ):
        self._broadcast = broadcast_fn
        self._chat = chat_fn
        self._db_path = db_path
        self._handles: dict[int, asyncio.TimerHandle] = {}

    async def start(self) -> None:
        """Load active tasks from DB and register asyncio handles."""
        tasks = get_active_tasks(self._db_path)
        now = datetime.now(timezone.utc)

        for task in tasks:
            task_id = task["id"]
            fire_at = datetime.fromisoformat(task["fire_at"])
            delta = (fire_at - now).total_seconds()

            if delta <= 0:
                if task["type"] == "recurring" and task["cron_expr"]:
                    # Advance to next cycle
                    next_fire = croniter(task["cron_expr"], now).get_next(datetime)
                    next_fire_str = next_fire.isoformat()
                    update_task_fire_at(self._db_path, task_id, next_fire_str)
                    new_delta = (next_fire - now).total_seconds()
                    self._register_handle(task_id, new_delta)
                else:
                    # Fire immediately
                    self._register_handle(task_id, 0)
            else:
                self._register_handle(task_id, delta)

    async def create_task(
        self,
        type: str,
        label: str,
        fire_at: str,
        cron_expr: Optional[str] = None,
        agent_prompt: Optional[str] = None,
    ) -> int:
        """Write to DB and register asyncio.call_later handle. Returns task id."""
        task_id = insert_task(
            self._db_path,
            task_type=type,
            label=label,
            agent_prompt=agent_prompt,
            fire_at=fire_at,
            cron_expr=cron_expr,
        )

        now = datetime.now(timezone.utc)
        fire_dt = datetime.fromisoformat(fire_at)
        delay = max(0, (fire_dt - now).total_seconds())
        self._register_handle(task_id, delay)

        await self._broadcast({
            "type": "tasks_updated",
            "tasks": get_all_tasks(self._db_path),
        })

        return task_id

    async def cancel_task(self, task_id: int) -> bool:
        """Mark cancelled in DB and cancel asyncio handle."""
        handle = self._handles.pop(task_id, None)
        if handle is not None:
            handle.cancel()

        update_task_status(self._db_path, task_id, "cancelled")
        return True

    async def reactivate_task(self, task_id: int) -> Optional[str]:
        """Reactivate a task.

        Returns None on success, or an error message string on failure.
        - One-time expired/fired -> error (don't reschedule)
        - Recurring -> compute next fire_at, update DB, re-register
        """
        tasks = get_all_tasks(self._db_path)
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task is None:
            return "任务不存在"

        now = datetime.now(timezone.utc)

        if task["type"] == "recurring" and task["cron_expr"]:
            next_fire = croniter(task["cron_expr"], now).get_next(datetime)
            next_fire_str = next_fire.isoformat()
            update_task_fire_at(self._db_path, task_id, next_fire_str)
            update_task_status(self._db_path, task_id, "active")
            delay = (next_fire - now).total_seconds()
            self._register_handle(task_id, delay)
            return None
        else:
            # One-time task
            fire_at = datetime.fromisoformat(task["fire_at"])
            if fire_at <= now or task["status"] == "fired":
                return "该任务已过期，请通过对话重新设置"
            # Still in the future and not fired — re-register
            update_task_status(self._db_path, task_id, "active")
            delay = (fire_at - now).total_seconds()
            self._register_handle(task_id, delay)
            return None

    def list_tasks(self) -> list[dict]:
        """Return all tasks from DB (active + cancelled + fired)."""
        return get_all_tasks(self._db_path)

    async def shutdown(self) -> None:
        """Cancel all pending handles."""
        for handle in self._handles.values():
            handle.cancel()
        self._handles.clear()

    def _register_handle(self, task_id: int, delay: float) -> None:
        """Register an asyncio.call_later handle for a task."""
        loop = asyncio.get_running_loop()
        handle = loop.call_later(
            delay,
            lambda tid=task_id: asyncio.create_task(self._on_fire(tid)),
        )
        self._handles[task_id] = handle

    async def _on_fire(self, task_id: int) -> None:
        """Handle a task firing.

        1. Fetch task from DB
        2. Broadcast scheduled_task_fire
        3. If agent_prompt: call chat_fn, broadcast assistant_message
        4. If recurring: compute next fire_at, update DB, re-register
        5. If one-time: update status=fired in DB
        6. Broadcast tasks_updated with full task list
        """
        try:
            tasks = get_all_tasks(self._db_path)
            task = next((t for t in tasks if t["id"] == task_id), None)
            if task is None:
                logger.warning("Task %d not found in DB during _on_fire", task_id)
                return

            # 1. Broadcast fire event
            await self._broadcast({
                "type": "scheduled_task_fire",
                "task": task,
            })

            # 2. If agent_prompt, call chat and broadcast response
            if task.get("agent_prompt"):
                try:
                    response = await self._chat(task["agent_prompt"])
                    await self._broadcast({
                        "type": "assistant_message",
                        "text": response,
                    })
                except Exception:
                    logger.exception("chat_fn failed for task %d", task_id)

            # 3. Recurring: reschedule; one-time: mark fired
            if task["type"] == "recurring" and task.get("cron_expr"):
                now = datetime.now(timezone.utc)
                next_fire = croniter(task["cron_expr"], now).get_next(datetime)
                next_fire_str = next_fire.isoformat()
                update_task_fire_at(self._db_path, task_id, next_fire_str)
                delay = (next_fire - now).total_seconds()
                self._register_handle(task_id, delay)
            else:
                update_task_status(self._db_path, task_id, "fired")
                self._handles.pop(task_id, None)

            # 4. Broadcast updated task list
            await self._broadcast({
                "type": "tasks_updated",
                "tasks": get_all_tasks(self._db_path),
            })

        except Exception:
            logger.exception("Unhandled error in _on_fire for task %d", task_id)
