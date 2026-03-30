"""Tool dispatcher — routes tool calls to their implementations."""

from agent.tools.web_search import web_search
from agent.tools.alarm import set_alarm
from agent.tools.music import play_music


async def execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool by name and return the result as a string."""
    if name == "web_search":
        return await web_search(input_data["query"])
    elif name == "set_alarm":
        return await set_alarm(
            seconds=input_data["seconds"],
            label=input_data.get("label", "Alarm"),
        )
    elif name == "play_music":
        return await play_music(input_data["query"])
    else:
        return f"Unknown tool: {name}"
