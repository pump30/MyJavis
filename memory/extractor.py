"""MemoryExtractor: async background extraction of memories from conversations."""

import asyncio
import json
import logging

import anthropic

import config
from memory.store import MemoryStore

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze the following conversation turn and extract any information worth remembering long-term.
Only extract clear, explicit facts — do not speculate or infer. Categories:
- user_profile: user identity, role, habits
- fact: explicit knowledge, contacts, data
- event: events, schedules, plans
- preference: how the user likes to interact

Return a JSON array. Each item: {"type": "...", "tags": ["..."], "summary": "one-line summary", "content": "full detail"}.
If nothing is worth remembering, return [].

Conversation:
"""


class MemoryExtractor:
    """Extracts memories from conversation turns in the background."""

    def __init__(self, store: MemoryStore):
        self._store = store
        self._client = anthropic.AsyncAnthropic(
            base_url=config.ANTHROPIC_BASE_URL,
            api_key=config.ANTHROPIC_API_KEY,
        )
        self._tasks: set[asyncio.Task] = set()

    def trigger(self, user_text: str, assistant_text: str):
        """Fire-and-forget: schedule extraction as a background task."""
        task = asyncio.create_task(self._extract(user_text, assistant_text))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _extract(self, user_text: str, assistant_text: str):
        """Call Claude to analyze the conversation turn and save any extracted memories."""
        try:
            conversation_text = f"User: {user_text}\nAssistant: {assistant_text}"
            response = await self._client.messages.create(
                model=config.MODEL,
                max_tokens=1024,
                system="You are a memory extraction assistant. Return only valid JSON arrays.",
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT + conversation_text,
                }],
            )

            # Parse the response
            text = response.content[0].text.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            memories = json.loads(text)
            if not isinstance(memories, list):
                return

            for mem in memories:
                if not isinstance(mem, dict):
                    continue
                mem_type = mem.get("type", "")
                summary = mem.get("summary", "")
                content = mem.get("content", "")
                tags = mem.get("tags", [])

                if not mem_type or not summary or not content:
                    continue

                await self._store.save(
                    memory_type=mem_type,
                    tags=tags,
                    summary=summary,
                    content=content,
                    source="inferred",
                )
                logger.info(f"[memory-extractor] Auto-saved: {summary}")

        except json.JSONDecodeError:
            logger.warning("[memory-extractor] Failed to parse extraction response as JSON")
        except Exception as e:
            logger.warning(f"[memory-extractor] Extraction failed: {e}")
