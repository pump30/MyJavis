"""Scheduler agent tools — schedule_task, list_tasks, cancel_task."""

import json
from datetime import datetime, timezone, timedelta

from croniter import croniter


async def schedule_task(scheduler, input_data: dict) -> str:
    """Create a scheduled task. Resolves fire_at from input variants."""
    task_type = input_data.get("type", "reminder")
    label = input_data.get("label", "")
    fire_at_str = input_data.get("fire_at")
    delay_seconds = input_data.get("delay_seconds")
    cron_expr = input_data.get("cron_expr")
    agent_prompt = input_data.get("agent_prompt")

    now = datetime.now(timezone.utc)

    # Resolve fire_at
    if fire_at_str:
        fire_at = datetime.fromisoformat(fire_at_str)
        fire_at_iso = fire_at.isoformat()
    elif delay_seconds is not None:
        fire_at = now + timedelta(seconds=delay_seconds)
        fire_at_iso = fire_at.isoformat()
    elif task_type == "recurring" and cron_expr:
        fire_at = croniter(cron_expr, now).get_next(datetime)
        fire_at_iso = fire_at.isoformat()
    else:
        if task_type == "recurring":
            return "Error: recurring tasks require a cron_expr."
        return "Error: please provide fire_at or delay_seconds to specify when the task should fire."

    task_id = await scheduler.create_task(
        type=task_type,
        label=label,
        fire_at=fire_at_iso,
        cron_expr=cron_expr,
        agent_prompt=agent_prompt,
    )

    return f"Task #{task_id} '{label}' scheduled. It will fire at {fire_at_iso}."


async def list_tasks(scheduler) -> str:
    """Return all tasks as a JSON string."""
    tasks = scheduler.list_tasks()
    return json.dumps(tasks, ensure_ascii=False)


async def cancel_task(scheduler, task_id: int) -> str:
    """Cancel a task by ID."""
    await scheduler.cancel_task(task_id)
    return f"Task #{task_id} has been cancelled."
