# Scheduled Tasks Design

## Overview

为 Jarvis 语音助手添加统一的定时任务系统，替换现有的 `set_alarm` 工具。支持三种任务类型：定时提醒、延时执行动作、周期性任务。任务持久化到 SQLite，服务重启后自动恢复。UI 改为 Tab 式布局。

## Task Types

| 类型 | 说明 | 触发行为 |
|------|------|----------|
| `reminder` | 定时提醒 | 播放提示音 + UI 通知 + 对话消息 |
| `action` | 延时/定时执行 | 调用 `agent.client.chat(agent_prompt)` + 广播结果 + 可选 TTS |
| `recurring` | 周期性任务 | 同上，触发后自动计算下一次时间 |

## Data Model

SQLite 数据库：`data/scheduler.db`

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,          -- 'reminder' | 'action' | 'recurring'
    label TEXT NOT NULL,         -- 任务描述
    agent_prompt TEXT,           -- 触发时发给 agent 的指令（action/recurring）
    fire_at TEXT NOT NULL,       -- 下次触发时间 ISO8601
    cron_expr TEXT,              -- cron 表达式（recurring 类型）
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'fired' | 'cancelled'
    created_at TEXT NOT NULL     -- 创建时间 ISO8601
);
```

## Scheduler Core (SchedulerManager)

新文件：`scheduler/manager.py`，单例类。

### 启动流程

1. 服务启动时，从 SQLite 加载所有 `status=active` 的任务
2. 对每个任务，计算距 `fire_at` 的秒数，用 `asyncio.call_later` 注册回调
3. 已过期的一次性任务立即触发
4. 已过期的 recurring 任务跳到下一个周期

### 核心方法

- `create_task(type, label, fire_at, cron_expr, agent_prompt)` — 写入 SQLite + 注册调度
- `cancel_task(task_id)` — 标记 `cancelled` + 取消 asyncio handle
- `reactivate_task(task_id)` — recurring/未过期任务恢复为 `active` + 重新注册调度
- `list_tasks()` — 返回所有 active + cancelled 任务
- `_on_fire(task_id)` — 触发回调：
  - 广播 `{"type": "scheduled_task_fire", "task_id": ..., "label": ...}` 到 WebSocket
  - 如果有 `agent_prompt`：调用 `chat(agent_prompt)`，广播 agent 回复
  - recurring 类型：用 `croniter` 计算下一次 `fire_at`，更新 DB，重新注册
  - 一次性类型：标记 `status=fired`

### 依赖

- `croniter`：cron 表达式解析，新增到 `requirements.txt`

## Agent Tools

替换现有 `set_alarm`，暴露 3 个工具：

### 1. `schedule_task` — 创建定时任务

```json
{
  "name": "schedule_task",
  "description": "Create a scheduled task: reminder, action, or recurring.",
  "input_schema": {
    "type": "object",
    "properties": {
      "type": {"type": "string", "enum": ["reminder", "action", "recurring"]},
      "label": {"type": "string", "description": "Task description"},
      "fire_at": {"type": "string", "description": "ISO8601 absolute time, e.g. 2026-03-30T15:00:00"},
      "delay_seconds": {"type": "integer", "description": "Relative delay in seconds (alternative to fire_at)"},
      "cron_expr": {"type": "string", "description": "Cron expression for recurring tasks, e.g. '0 9 * * *'"},
      "agent_prompt": {"type": "string", "description": "Prompt to send to agent when task fires"}
    },
    "required": ["type", "label"]
  }
}
```

`fire_at` 和 `delay_seconds` 二选一。recurring 类型必须提供 `cron_expr`。

### 2. `list_tasks` — 查询任务

```json
{
  "name": "list_tasks",
  "description": "List all scheduled tasks (active and cancelled).",
  "input_schema": {"type": "object", "properties": {}}
}
```

### 3. `cancel_task` — 取消任务

```json
{
  "name": "cancel_task",
  "description": "Cancel a scheduled task by ID.",
  "input_schema": {
    "type": "object",
    "properties": {
      "task_id": {"type": "integer", "description": "Task ID to cancel"}
    },
    "required": ["task_id"]
  }
}
```

## Migration

- 删除 `agent/tools/alarm.py`
- 从 `agent/tools/definitions.py` 移除 `set_alarm` schema
- 从 `agent/tool_executor.py` 移除 `set_alarm` 分支
- 更新 `config.py` 中 `SYSTEM_PROMPT` 的工具描述
- 删除 `main.py` 中 `set_broadcast` 调用的相关 alarm wiring

## UI Design — Tab Layout

### 整体结构

```
┌─────────────────────────────────────┐
│  Jarvis          [Chat] [Tasks] [+] │  ← 顶栏 + Tab 切换
├─────────────────────────────────────┤
│                                     │
│         Tab 内容区域                 │
│                                     │
├─────────────────────────────────────┤
│  [🎤] [  输入框...           ] [➤]  │  ← 输入栏（仅 Chat tab 显示）
└─────────────────────────────────────┘
```

### Tab 1 — Chat

- 保持现有对话界面不变：消息列表 + 底部输入栏
- 状态指示灯、stop 按钮保留在顶栏
- 任务触发时在对话中也插入一条通知消息

### Tab 2 — Tasks

- 任务列表，每行：状态开关（toggle）、label、类型标签、下次触发时间
- toggle 可以 cancel / reactivate
- reactivate 已过期一次性任务时提示"该任务已过期，请通过对话重新设置"
- recurring 任务直接恢复到下一个周期
- 无输入栏
- 空状态："暂无定时任务，试试对 Jarvis 说「每天早上9点提醒我站会」"

### Tab 扩展

- `[+]` 预留位置，未来可加更多 tab
- Tab 切换用 CSS class 切换 `display: none/block`，不引入框架

### 跨 Tab 通知

- 任务触发时如果不在 Chat tab，Tasks tab 显示红点 badge
- 触发音效照常播放

### UI 设计质量

使用 Impeccable 前端设计技能（已安装在 `.claude/skills/`）指导 UI 实现：
- 实现前通过 `/audit` 检查现有 UI 问题
- 新 UI 遵循 Impeccable 的排版、色彩、空间设计规范
- 避免 AI 生成的通用风格（Inter 字体、紫色渐变、卡片套卡片等）
- Tab 切换、任务状态切换添加有目的的微动画
- 保持现有暗色主题风格，但提升设计精致度

## WebSocket Protocol Changes

### 新增 server → client 消息

| type | payload | 说明 |
|------|---------|------|
| `scheduled_task_fire` | `{task_id, label, type, agent_response?}` | 任务触发通知 |
| `tasks_updated` | `{tasks: [...]}` | 任务列表变更，前端刷新面板 |

### 新增 client → server 消息

| type | payload | 说明 |
|------|---------|------|
| `task_toggle` | `{task_id, action: "cancel"/"reactivate"}` | UI 开关操作 |

### 移除

- `alarm` 消息类型（被 `scheduled_task_fire` 替代）

## File Changes Summary

### New Files
- `scheduler/__init__.py`
- `scheduler/manager.py` — SchedulerManager 核心
- `scheduler/db.py` — SQLite 初始化和操作
- `agent/tools/scheduler_tools.py` — 3 个工具实现

### Modified Files
- `agent/tools/definitions.py` — 移除 set_alarm，新增 3 个工具 schema
- `agent/tool_executor.py` — 移除 set_alarm 分支，新增 3 个分支
- `config.py` — 更新 SYSTEM_PROMPT
- `main.py` — 初始化 SchedulerManager，移除 alarm wiring
- `web/server.py` — 处理 task_toggle，广播 tasks_updated
- `web/templates/index.html` — Tab 布局改造
- `web/static/app.js` — Tab 切换、任务面板、新消息处理
- `web/static/style.css` — Tab 样式、任务面板样式

### Deleted Files
- `agent/tools/alarm.py`

### Dependencies
- `croniter` — 新增到 `requirements.txt`
