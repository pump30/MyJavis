# Implementation Plan: Scheduled Tasks System

**Spec:** `docs/superpowers/specs/2026-03-30-scheduled-tasks-design.md`  
**Date:** 2026-03-30  
**Workflow:** Brainstorm → **Plan** → Develop (TDD) → Review

---

## Overview

Replace the in-memory `set_alarm` tool with a persistent, full-featured scheduled task system. Three task types (`reminder`, `action`, `recurring`), SQLite persistence, and a redesigned Tab-based UI.

---

## Implementation Phases

### Phase 1 — Scaffold & Database Layer

**Goal:** Get the SQLite layer working and tested before touching any existing code.

#### 1.1 Add dependency
- Add `croniter` to `requirements.txt`

#### 1.2 Create `scheduler/` package
- `scheduler/__init__.py` — empty
- `scheduler/db.py` — all SQLite operations

**`scheduler/db.py` responsibilities:**
```
init_db()                  → CREATE TABLE IF NOT EXISTS tasks (...)
insert_task(...)           → INSERT, return new id
get_active_tasks()         → SELECT WHERE status='active'
get_all_tasks()            → SELECT all (for list_tasks tool)
update_task_status(id, s)  → UPDATE status
update_task_fire_at(id, t) → UPDATE fire_at (for recurring reschedule)
```

Database path: `data/scheduler.db` (create `data/` dir if absent).

Schema exactly as spec:
```sql
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
```

**Tests to write first (`tests/test_scheduler_db.py`):**
- `test_init_db_creates_table` — init twice is idempotent
- `test_insert_and_get_active` — insert active task, appears in get_active_tasks
- `test_update_status_to_fired` — task disappears from get_active_tasks
- `test_get_all_tasks_includes_cancelled` — cancelled tasks appear in get_all_tasks
- `test_update_fire_at` — fire_at is updated correctly

---

### Phase 2 — SchedulerManager Core

**Goal:** Implement `scheduler/manager.py` as a singleton that owns all scheduling logic.

#### 2.1 Class structure

```python
class SchedulerManager:
    def __init__(self, broadcast_fn, chat_fn):
        ...

    async def start(self):
        """Load active tasks from DB and register asyncio handles."""

    async def create_task(self, type, label, fire_at, cron_expr=None, agent_prompt=None) -> int:
        """Write to DB + register asyncio.call_later handle. Returns task id."""

    async def cancel_task(self, task_id: int) -> bool:
        """Mark cancelled in DB + cancel asyncio handle."""

    async def reactivate_task(self, task_id: int) -> str:
        """
        - one-time expired → return error message (don't reschedule)
        - recurring → compute next fire_at via croniter, update DB, re-register
        - active one-time → re-register (handle was lost on restart)
        """

    def list_tasks(self) -> list[dict]:
        """Return all tasks from DB (active + cancelled + fired)."""

    async def _on_fire(self, task_id: int):
        """
        1. Fetch task from DB
        2. Broadcast scheduled_task_fire
        3. If agent_prompt: call chat_fn(agent_prompt), broadcast assistant_message
        4. If recurring: compute next fire_at, update DB, re-register handle
        5. If one-time: update status=fired in DB
        6. Broadcast tasks_updated with full task list
        """
```

**Internal handle registry:** `_handles: dict[int, asyncio.TimerHandle]`  
Use `loop.call_later(delay, callback)` where callback schedules `asyncio.create_task(self._on_fire(task_id))`.

**Startup recovery logic (`start()`):**
```
for each active task in DB:
    delta = (fire_at - now).total_seconds()
    if delta <= 0:
        if recurring:  compute next fire_at, update DB, register with new delta
        else:          fire immediately (delta=0)
    else:
        register with delta
```

**Tests to write first (`tests/test_scheduler_manager.py`):**
- `test_create_task_registers_handle` — handle appears in `_handles`
- `test_cancel_task_cancels_handle` — handle removed, DB status=cancelled
- `test_on_fire_reminder_broadcasts` — broadcast called with `scheduled_task_fire`
- `test_on_fire_action_calls_chat` — chat_fn called with agent_prompt
- `test_on_fire_recurring_reschedules` — new handle registered, DB fire_at updated
- `test_on_fire_one_time_marks_fired` — DB status=fired, handle removed
- `test_start_recovers_active_tasks` — tasks loaded from DB on start
- `test_start_fires_overdue_one_time` — overdue task fires immediately
- `test_start_skips_overdue_recurring` — overdue recurring jumps to next cycle
- `test_reactivate_expired_one_time_returns_error`
- `test_reactivate_recurring_reschedules`

---

### Phase 3 — Agent Tools

**Goal:** Implement the 3 new tools and wire them into the executor.

#### 3.1 `agent/tools/scheduler_tools.py`

```python
async def schedule_task(scheduler: SchedulerManager, input_data: dict) -> str:
    """
    Resolve fire_at:
      - if fire_at provided: parse ISO8601
      - elif delay_seconds provided: now + delay_seconds
      - elif recurring + cron_expr: compute first fire from cron
      - else: error
    Call scheduler.create_task(...)
    Return confirmation string with task id and fire time.
    """

async def list_tasks(scheduler: SchedulerManager) -> str:
    """Return formatted task list (JSON string)."""

async def cancel_task(scheduler: SchedulerManager, task_id: int) -> str:
    """Call scheduler.cancel_task(task_id), return confirmation."""
```

#### 3.2 `agent/tools/definitions.py` — replace `set_alarm`

Remove `set_alarm` entry. Add three new tool schemas exactly as specified in the spec.

#### 3.3 `agent/tool_executor.py` — replace `set_alarm` branch

```python
# Remove:
from agent.tools.alarm import set_alarm
# Add:
from agent.tools.scheduler_tools import schedule_task, list_tasks, cancel_task

# In execute_tool():
# Remove set_alarm branch
# Add:
elif name == "schedule_task":
    return await schedule_task(scheduler_manager, input_data)
elif name == "list_tasks":
    return await list_tasks(scheduler_manager)
elif name == "cancel_task":
    return await cancel_task(scheduler_manager, input_data["task_id"])
```

`execute_tool` needs access to the `SchedulerManager` singleton. Options:
- Pass it as a parameter (preferred — testable)
- Or use a module-level reference set at startup

**Decision:** Add `scheduler_manager` as a module-level variable in `tool_executor.py`, set by `main.py` at startup (same pattern as `set_broadcast` today).

**Tests to write first (`tests/test_scheduler_tools.py`):**
- `test_schedule_task_with_delay_seconds`
- `test_schedule_task_with_fire_at`
- `test_schedule_task_recurring_requires_cron`
- `test_schedule_task_missing_time_returns_error`
- `test_list_tasks_returns_json`
- `test_cancel_task_calls_manager`

---

### Phase 4 — Migration (remove alarm)

**Goal:** Delete old alarm code and update wiring.

#### 4.1 Delete `agent/tools/alarm.py`

#### 4.2 Update `main.py`
- Remove `from agent.tools.alarm import set_broadcast`
- Remove `set_broadcast(web_module.broadcast)` call
- Add `from scheduler.manager import SchedulerManager`
- In `lifespan()`:
  ```python
  scheduler = SchedulerManager(broadcast_fn=web_module.broadcast, chat_fn=chat)
  await scheduler.start()
  web_module.scheduler_manager = scheduler
  # also set on tool_executor:
  import agent.tool_executor as tool_executor_module
  tool_executor_module.scheduler_manager = scheduler
  ```
- In shutdown: `await scheduler.shutdown()` (cancel all pending handles)

#### 4.3 Update `config.py` — `SYSTEM_PROMPT`
```python
SYSTEM_PROMPT = (
    "You are Jarvis, a helpful voice assistant. "
    "You can search the web, schedule tasks (reminders, actions, recurring jobs), "
    "and play music. ..."
)
```

---

### Phase 5 — WebSocket Protocol

**Goal:** Add `task_toggle` handler in `web/server.py` and broadcast `tasks_updated`.

#### 5.1 `web/server.py` changes

Add module-level: `scheduler_manager: SchedulerManager = None`

In `websocket_endpoint`, add new message type handler:
```python
elif msg_type == "task_toggle":
    task_id = msg.get("task_id")
    action = msg.get("action")  # "cancel" | "reactivate"
    if scheduler_manager:
        if action == "cancel":
            await scheduler_manager.cancel_task(task_id)
        elif action == "reactivate":
            result = await scheduler_manager.reactivate_task(task_id)
            if result:  # error message for expired one-time
                await ws.send_text(json.dumps({"type": "error", "text": result}))
        tasks = scheduler_manager.list_tasks()
        await broadcast({"type": "tasks_updated", "tasks": tasks})
```

Remove `alarm_manager = None` (dead code).

---

### Phase 6 — UI Redesign

**Goal:** Tab layout with Chat and Tasks panels.

#### 6.1 `web/templates/index.html`

Restructure to:
```html
<div class="app">
  <header class="topbar">
    <span class="logo">Jarvis</span>
    <nav class="tabs">
      <button class="tab-btn active" data-tab="chat">Chat</button>
      <button class="tab-btn" data-tab="tasks">
        Tasks <span class="badge" id="tasks-badge" hidden></span>
      </button>
      <button class="tab-btn tab-plus" disabled>+</button>
    </nav>
    <div class="topbar-controls"><!-- status dot, stop btn --></div>
  </header>

  <main class="tab-content">
    <section id="tab-chat" class="tab-panel active">
      <!-- existing message list -->
    </section>
    <section id="tab-tasks" class="tab-panel">
      <!-- task list or empty state -->
    </section>
  </main>

  <footer class="input-bar" id="input-bar">
    <!-- existing mic + text input — hidden when Tasks tab active -->
  </footer>
</div>
```

#### 6.2 `web/static/app.js`

**Tab switching:**
```javascript
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`tab-${name}`).classList.add('active');
  document.querySelector(`[data-tab="${name}"]`).classList.add('active');
  document.getElementById('input-bar').style.display = name === 'chat' ? '' : 'none';
  if (name === 'tasks') clearTasksBadge();
}
```

**New WebSocket message handlers:**
```javascript
case 'scheduled_task_fire':
  appendChatNotification(data.label);
  if (currentTab !== 'chat') showTasksBadge();
  break;

case 'tasks_updated':
  renderTaskList(data.tasks);
  break;
```

**Task list rendering (`renderTaskList`):**
- For each task: toggle switch, label, type badge, fire_at display
- Toggle sends `task_toggle` message to server
- Empty state message when no tasks

**Task toggle handler:**
```javascript
function toggleTask(taskId, currentStatus) {
  const action = currentStatus === 'active' ? 'cancel' : 'reactivate';
  ws.send(JSON.stringify({ type: 'task_toggle', task_id: taskId, action }));
}
```

#### 6.3 `web/static/style.css`

New styles needed:
- `.topbar` — flex row, logo left, tabs center, controls right
- `.tabs` / `.tab-btn` — pill-style tabs, active state
- `.tab-panel` — `display: none` by default; `.active` → `display: flex/block`
- `.badge` — red dot on Tasks tab button
- `.task-list` / `.task-row` — task list layout
- `.task-toggle` — toggle switch component
- `.type-badge` — colored label for reminder/action/recurring
- `.empty-state` — centered empty state text
- Micro-animations: tab switch fade, toggle transition, badge pop-in
- Keep existing dark theme; refine spacing and typography

**Design constraints (from spec):**
- No Inter font / purple gradients / card-in-card patterns
- Purposeful micro-animations only
- Consistent with existing dark theme

---

### Phase 7 — Integration & Smoke Test

**Goal:** Verify the full flow end-to-end.

1. Start the app: `python main.py`
2. Open `http://localhost:8088`
3. Verify Chat tab is default, input bar visible
4. Switch to Tasks tab — input bar hides, empty state shown
5. Say/type: "提醒我5秒后站会" → agent calls `schedule_task` with `delay_seconds=5`
6. After 5s: `scheduled_task_fire` broadcast → chat notification + Tasks badge
7. Switch to Tasks tab — task shows as `fired`
8. Say: "每天早上9点提醒我站会" → agent calls `schedule_task` with `cron_expr="0 9 * * *"`
9. Tasks tab shows recurring task as active
10. Toggle the task off → status becomes `cancelled`
11. Toggle back on → recurring task reactivated with next fire_at
12. Restart server → recurring task reloaded from DB

---

## File Change Summary

| Action | File |
|--------|------|
| **Create** | `scheduler/__init__.py` |
| **Create** | `scheduler/db.py` |
| **Create** | `scheduler/manager.py` |
| **Create** | `agent/tools/scheduler_tools.py` |
| **Create** | `tests/test_scheduler_db.py` |
| **Create** | `tests/test_scheduler_manager.py` |
| **Create** | `tests/test_scheduler_tools.py` |
| **Modify** | `agent/tools/definitions.py` |
| **Modify** | `agent/tool_executor.py` |
| **Modify** | `config.py` |
| **Modify** | `main.py` |
| **Modify** | `web/server.py` |
| **Modify** | `web/templates/index.html` |
| **Modify** | `web/static/app.js` |
| **Modify** | `web/static/style.css` |
| **Modify** | `requirements.txt` |
| **Delete** | `agent/tools/alarm.py` |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `asyncio.call_later` (not `asyncio.sleep` loop) | Single callback per task, no polling overhead |
| `SchedulerManager` holds `_handles` dict | Enables O(1) cancel by task_id |
| `chat_fn` injected into SchedulerManager | Avoids circular import; testable with mock |
| `broadcast_fn` injected same way | Consistent with existing alarm pattern |
| `tool_executor.scheduler_manager` module var | Matches existing `set_broadcast` pattern; minimal refactor |
| Expired one-time tasks on reactivate → error | UX: user must set a new time via conversation |
| `data/` directory for SQLite | Keeps DB out of source tree; easy to `.gitignore` |

---

## TDD Order

```
Phase 1: tests/test_scheduler_db.py        (pure SQLite, no async)
Phase 2: tests/test_scheduler_manager.py   (mock broadcast + chat, use asyncio)
Phase 3: tests/test_scheduler_tools.py     (mock SchedulerManager)
Phase 6: manual browser smoke test         (UI has no unit tests)
```

Run tests with: `python -m pytest tests/ -v`

---

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| `asyncio.call_later` handle lost on restart | `start()` re-registers all active tasks from DB |
| Clock skew / DST | Store all times as UTC ISO8601; display in local time in UI |
| `croniter` not installed | Added to `requirements.txt`; `start()` fails fast with clear error |
| Concurrent task fires overwhelming agent | `_on_fire` is a coroutine; agent calls are sequential per task |
| `data/` directory missing | `db.py` calls `Path("data").mkdir(exist_ok=True)` before connecting |