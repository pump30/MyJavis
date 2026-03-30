"""Alarm / timer tool."""

import asyncio
import time

# Active alarms: list of {id, label, fire_at, task}
_alarms: list[dict] = []
_next_id = 1
_broadcast_fn = None  # set by main.py


def set_broadcast(fn):
    """Register the broadcast function for alarm notifications."""
    global _broadcast_fn
    _broadcast_fn = fn


async def _alarm_fire(alarm_id: int, label: str, delay: float):
    """Wait and then fire the alarm."""
    await asyncio.sleep(delay)
    # Remove from active list
    global _alarms
    _alarms = [a for a in _alarms if a["id"] != alarm_id]
    # Notify via broadcast
    if _broadcast_fn:
        await _broadcast_fn({
            "type": "alarm",
            "label": label,
            "time": time.strftime("%H:%M:%S"),
        })


async def set_alarm(seconds: int, label: str = "Alarm") -> str:
    """Set a timer that fires after `seconds` seconds."""
    global _next_id
    alarm_id = _next_id
    _next_id += 1

    fire_at = time.time() + seconds
    task = asyncio.create_task(_alarm_fire(alarm_id, label, seconds))
    _alarms.append({
        "id": alarm_id,
        "label": label,
        "fire_at": fire_at,
        "task": task,
    })

    if seconds >= 3600:
        time_str = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    elif seconds >= 60:
        time_str = f"{seconds // 60}m {seconds % 60}s"
    else:
        time_str = f"{seconds}s"

    return f"Alarm '{label}' set for {time_str} from now."


def get_active_alarms() -> list[dict]:
    """Return list of active alarms."""
    now = time.time()
    return [
        {"id": a["id"], "label": a["label"], "remaining": int(a["fire_at"] - now)}
        for a in _alarms
        if a["fire_at"] > now
    ]
