"""SQLite persistence layer for scheduled tasks.

All times are stored as ISO 8601 strings.
The default database path is data/scheduler.db (created automatically).
Every public function accepts a db_path parameter so tests can pass `:memory:`.
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scheduler.db")

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    label TEXT NOT NULL,
    agent_prompt TEXT,
    fire_at TEXT NOT NULL,
    cron_expr TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create the tasks table if it does not already exist. Idempotent."""
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.execute(_CREATE_TABLE)
        conn.commit()
    finally:
        conn.close()


def insert_task(
    db_path: str = DEFAULT_DB_PATH,
    *,
    task_type: str,
    label: str,
    agent_prompt: Optional[str],
    fire_at: str,
    cron_expr: Optional[str],
) -> int:
    """Insert a new task and return its id."""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO tasks (type, label, agent_prompt, fire_at, cron_expr, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (task_type, label, agent_prompt, fire_at, cron_expr, created_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_active_tasks(db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Return all tasks with status='active'."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM tasks WHERE status = 'active'").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_all_tasks(db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    """Return all tasks regardless of status."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM tasks").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_task_status(db_path: str, task_id: int, status: str) -> None:
    """Update the status of a task."""
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        conn.commit()
    finally:
        conn.close()


def update_task_fire_at(db_path: str, task_id: int, fire_at: str) -> None:
    """Update the fire_at timestamp of a task (used for recurring reschedule)."""
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE tasks SET fire_at = ? WHERE id = ?", (fire_at, task_id))
        conn.commit()
    finally:
        conn.close()
