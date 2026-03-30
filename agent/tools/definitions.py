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
        "name": "set_alarm",
        "description": (
            "Set an alarm or timer. Use when the user asks to be reminded at a "
            "specific time or wants a countdown timer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "Number of seconds from now until the alarm fires",
                },
                "label": {
                    "type": "string",
                    "description": "A short label for the alarm, e.g. 'Take a break'",
                },
            },
            "required": ["seconds"],
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
