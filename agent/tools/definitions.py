"""Tool definitions for the AI agent (Anthropic tool use format)."""

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use when the user asks about "
            "news, facts, weather, or anything requiring up-to-date information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "schedule_task",
        "description": (
            "Create a scheduled task: reminder, action, or recurring. "
            "Use 'reminder' for simple notifications, 'action' for tasks "
            "that need AI agent execution, 'recurring' for periodic tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["reminder", "action", "recurring"],
                    "description": "Task type",
                },
                "label": {
                    "type": "string",
                    "description": "Task description",
                },
                "fire_at": {
                    "type": "string",
                    "description": "ISO8601 absolute time, e.g. 2026-03-30T15:00:00+08:00",
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "Relative delay in seconds (alternative to fire_at)",
                },
                "cron_expr": {
                    "type": "string",
                    "description": "Cron expression for recurring tasks, e.g. '0 9 * * *'",
                },
                "agent_prompt": {
                    "type": "string",
                    "description": "Prompt to send to agent when task fires (required for action/recurring type)",
                },
            },
            "required": ["type", "label"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List all scheduled tasks (active, fired, and cancelled).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "cancel_task",
        "description": "Cancel a scheduled task by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "Task ID to cancel",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "play_music",
        "description": (
            "Search and play music. Use when the user asks to play a song, "
            "artist, or genre."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Song name, artist, or description to search for",
                },
            },
            "required": ["query"],
        },
    },
]
