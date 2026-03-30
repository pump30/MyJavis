"""Anthropic SDK client with agentic tool-use loop."""

from datetime import datetime
import anthropic

import config
from agent.conversation import ConversationManager
from agent.tool_executor import execute_tool
from agent.tools.definitions import TOOLS
from memory.store import MemoryStore
from memory.loader import MemoryLoader
from agent.tools.memory import set_store as _set_memory_store

# Shared conversation state
conversation = ConversationManager()

_client = anthropic.AsyncAnthropic(
    base_url=config.ANTHROPIC_BASE_URL,
    api_key=config.ANTHROPIC_API_KEY,
)

_memory_store = MemoryStore()
_memory_loader = MemoryLoader(_memory_store)
_set_memory_store(_memory_store)


def _serialize_content(content) -> list[dict]:
    """Convert SDK content blocks to dicts for the messages API."""
    result = []
    for block in content:
        if block.type == "text":
            result.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return result


async def chat(user_text: str) -> str:
    """Send user text to the agent and run the tool-use loop until end_turn.

    Returns the final assistant text response.
    """
    conversation.add_user(user_text)
    print(f"[agent] User: {user_text}")

    max_iterations = 10
    for i in range(max_iterations):
        print(f"[agent] Calling API (iteration {i + 1})...")
        try:
            response = await _client.messages.create(
                model=config.MODEL,
                max_tokens=config.MAX_TOKENS,
                system=(
                    f"{config.SYSTEM_PROMPT}\n"
                    f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}"
                    f"{_memory_loader.build_context()}"
                ),
                tools=TOOLS,
                messages=conversation.messages,
            )
        except Exception as e:
            print(f"[agent] API error: {e}")
            raise

        print(f"[agent] Stop reason: {response.stop_reason}")

        # Collect text and tool_use blocks
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
                print(f"[agent] Tool call: {block.name}({block.input})")

        # If no tool calls, we're done
        if response.stop_reason == "end_turn" or not tool_uses:
            final_text = "\n".join(text_parts) if text_parts else ""
            conversation.add_assistant(final_text)
            print(f"[agent] Response: {final_text[:100]}")
            return final_text

        # Add the full assistant response (serialized) to conversation
        conversation.add_assistant(_serialize_content(response.content))

        # Execute each tool and add results
        for tool_block in tool_uses:
            result = await execute_tool(tool_block.name, tool_block.input)
            print(f"[agent] Tool result ({tool_block.name}): {result[:100]}")
            conversation.add_tool_result(tool_block.id, result)

    # Safety: if we exceeded max iterations
    return "Sorry, I wasn't able to complete the request."
