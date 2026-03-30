"""Conversation history manager."""


class ConversationManager:
    def __init__(self, max_turns: int = 50):
        self._messages: list[dict] = []
        self._max_turns = max_turns

    @property
    def messages(self) -> list[dict]:
        return self._messages

    def add_user(self, text: str):
        self._messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant(self, content):
        """Add assistant message. `content` can be a string or list of content blocks."""
        if isinstance(content, str):
            self._messages.append({"role": "assistant", "content": content})
        else:
            self._messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_result(self, tool_use_id: str, result: str):
        self._messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                }
            ],
        })

    def clear(self):
        self._messages.clear()

    def _trim(self):
        """Keep only the last max_turns pairs of messages."""
        if len(self._messages) > self._max_turns * 2:
            self._messages = self._messages[-(self._max_turns * 2):]
