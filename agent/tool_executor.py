"""Tool dispatcher — routes tool calls to their implementations."""

from agent.tools.web_search import web_search
from agent.tools.music import play_music
from agent.tools.scheduler_tools import schedule_task, list_tasks, cancel_task
from agent.tools.memory import save_memory, recall_memory

# Set by main.py at startup.
scheduler_manager = None


async def execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool by name and return the result as a string."""
    if name == "web_search":
        return await web_search(input_data["query"])
    elif name == "schedule_task":
        return await schedule_task(scheduler_manager, input_data)
    elif name == "list_tasks":
        return await list_tasks(scheduler_manager)
    elif name == "cancel_task":
        return await cancel_task(scheduler_manager, input_data["task_id"])
    elif name == "play_music":
        return await play_music(input_data["query"])
    elif name == "save_memory":
        return await save_memory(
            memory_type=input_data["type"],
            summary=input_data["summary"],
            content=input_data["content"],
            tags=input_data.get("tags"),
        )
    elif name == "recall_memory":
        return await recall_memory(
            query=input_data["query"],
            memory_type=input_data.get("type"),
        )
    else:
        return f"Unknown tool: {name}"
