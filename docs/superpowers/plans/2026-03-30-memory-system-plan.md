# Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent memory system to Jarvis that remembers user information, facts, events, and preferences across sessions using Markdown files with a JSON index.

**Architecture:** Markdown files in `data/memory/<type>/` store individual memories with YAML frontmatter. A `data/memory/index.json` file indexes all memories for fast search. A `MemoryStore` class handles CRUD, `MemoryLoader` injects user profile into the system prompt each turn, `MemoryExtractor` runs async post-conversation to auto-extract memories, and two new agent tools (`save_memory`, `recall_memory`) let Claude explicitly store and retrieve.

**Tech Stack:** Python 3.11+, PyYAML (for frontmatter parsing), asyncio, Anthropic SDK (for extraction calls)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `memory/__init__.py` | Package init |
| Create | `memory/store.py` | `MemoryStore` class: CRUD, index management, dedup, search |
| Create | `memory/loader.py` | `MemoryLoader` class: build system prompt context from memories |
| Create | `memory/extractor.py` | `MemoryExtractor` class: async background memory extraction |
| Create | `agent/tools/memory.py` | `save_memory()` and `recall_memory()` tool implementations |
| Modify | `agent/tools/definitions.py` | Add `save_memory` and `recall_memory` tool schemas |
| Modify | `agent/tool_executor.py` | Route `save_memory` and `recall_memory` calls |
| Modify | `agent/client.py` | Inject memory context into system prompt via `MemoryLoader` |
| ~~No change~~ | `pipeline/orchestrator.py` | ~~Not modified — extraction triggered in client.py instead~~ |
| Modify | `config.py` | Add `MEMORY_DIR` constant |
| Modify | `requirements.txt` | Add `pyyaml` dependency |

---

### Task 1: Add PyYAML Dependency and Memory Config

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

- [ ] **Step 1: Add pyyaml to requirements.txt**

Add `pyyaml` at the end of `requirements.txt`:

```
PyYAML>=6.0
```

- [ ] **Step 2: Add memory config to config.py**

Add at the end of `config.py`, before any trailing newline:

```python
# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------
MEMORY_DIR = "data/memory"
```

- [ ] **Step 3: Install the new dependency**

Run: `pip install pyyaml`
Expected: Successfully installed PyYAML

- [ ] **Step 4: Commit**

```bash
git add requirements.txt config.py
git commit -m "feat(memory): add PyYAML dependency and MEMORY_DIR config"
```

---

### Task 2: Implement MemoryStore — Core CRUD and Index Management

**Files:**
- Create: `memory/__init__.py`
- Create: `memory/store.py`

- [ ] **Step 1: Create the memory package**

Create `memory/__init__.py`:

```python
```

(Empty file — just makes it a package.)

- [ ] **Step 2: Write MemoryStore implementation**

Create `memory/store.py`:

```python
"""MemoryStore: persistent memory storage using Markdown files + JSON index."""

import asyncio
import json
import os
import re
from datetime import datetime

import yaml

import config

MEMORY_TYPES = ("user_profile", "fact", "event", "preference")


class MemoryStore:
    """CRUD operations on Markdown memory files with a JSON index."""

    def __init__(self, base_dir: str | None = None):
        self._base_dir = base_dir or config.MEMORY_DIR
        self._index_path = os.path.join(self._base_dir, "index.json")
        self._lock = asyncio.Lock()
        self._index: dict | None = None  # lazy-loaded

    def _ensure_dirs(self):
        """Create base directory and type subdirectories if they don't exist."""
        for memory_type in MEMORY_TYPES:
            os.makedirs(os.path.join(self._base_dir, memory_type), exist_ok=True)

    def _load_index(self) -> dict:
        """Load index from disk, or return empty index if missing/corrupt."""
        if self._index is not None:
            return self._index
        if os.path.exists(self._index_path):
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                    return self._index
            except (json.JSONDecodeError, OSError):
                pass
        self._index = {"memories": []}
        return self._index

    def _save_index(self):
        """Atomically write index to disk."""
        self._ensure_dirs()
        tmp_path = self._index_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self._index_path)

    def _generate_id(self) -> str:
        """Generate a unique memory ID based on timestamp."""
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        index = self._load_index()
        # Avoid collisions by appending a counter
        existing = {m["id"] for m in index["memories"]}
        candidate = f"mem_{now}"
        counter = 1
        while candidate in existing:
            candidate = f"mem_{now}_{counter}"
            counter += 1
        return candidate

    def _tokenize(self, text: str) -> set[str]:
        """Split text into lowercase tokens for matching."""
        return set(re.findall(r"[\w\u4e00-\u9fff]+", text.lower()))

    def _find_duplicate(self, memory_type: str, tags: list[str], summary: str, source: str) -> dict | None:
        """Find an existing memory that is likely a duplicate."""
        index = self._load_index()
        new_tokens = self._tokenize(summary)
        if not new_tokens:
            return None

        new_tags = set(tags)
        # Stricter threshold for auto-extracted memories
        threshold = 0.7 if source == "inferred" else 0.5

        for entry in index["memories"]:
            if entry["type"] != memory_type:
                continue
            existing_tags = set(entry.get("tags", []))
            if not new_tags.intersection(existing_tags):
                continue
            existing_tokens = self._tokenize(entry["summary"])
            if not existing_tokens:
                continue
            overlap = len(new_tokens.intersection(existing_tokens)) / len(new_tokens)
            if overlap >= threshold:
                return entry
        return None

    def _write_memory_file(self, memory_id: str, memory_type: str, tags: list[str],
                           summary: str, content: str, source: str,
                           created: str, updated: str) -> str:
        """Write a single memory Markdown file. Returns relative file path."""
        self._ensure_dirs()
        filename = f"{memory_id}.md"
        rel_path = os.path.join(memory_type, filename)
        abs_path = os.path.join(self._base_dir, rel_path)

        frontmatter = {
            "id": memory_id,
            "type": memory_type,
            "tags": tags,
            "summary": summary,
            "created": created,
            "updated": updated,
            "source": source,
        }
        md_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)}---\n\n{content}\n"

        # Atomic write
        tmp_path = abs_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        os.replace(tmp_path, abs_path)
        return rel_path

    def _read_memory_file(self, rel_path: str) -> str | None:
        """Read the content body (after frontmatter) from a memory file."""
        abs_path = os.path.join(self._base_dir, rel_path)
        if not os.path.exists(abs_path):
            return None
        with open(abs_path, "r", encoding="utf-8") as f:
            text = f.read()
        # Split on YAML frontmatter delimiter
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
        return text.strip()

    async def save(self, memory_type: str, tags: list[str], summary: str,
                   content: str, source: str = "explicit") -> str:
        """Save a memory. Returns the memory ID. Updates existing if duplicate found."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory type: {memory_type}. Must be one of {MEMORY_TYPES}")

        async with self._lock:
            index = self._load_index()
            now = datetime.now().isoformat(timespec="seconds")

            # Check for duplicate
            dup = self._find_duplicate(memory_type, tags, summary, source)
            if dup:
                # Update existing memory
                dup["tags"] = list(set(dup.get("tags", []) + tags))
                dup["summary"] = summary
                dup["updated"] = now
                self._write_memory_file(
                    dup["id"], memory_type, dup["tags"],
                    summary, content, dup.get("source", source),
                    dup["created"], now,
                )
                self._save_index()
                return dup["id"]

            # Create new memory
            memory_id = self._generate_id()
            rel_path = self._write_memory_file(
                memory_id, memory_type, tags,
                summary, content, source, now, now,
            )
            index["memories"].append({
                "id": memory_id,
                "type": memory_type,
                "tags": tags,
                "summary": summary,
                "source": source,
                "file": rel_path,
                "created": now,
                "updated": now,
            })
            self._save_index()
            return memory_id

    async def search(self, query: str, memory_type: str | None = None,
                     limit: int = 5) -> list[dict]:
        """Search memories by keyword matching on summary and tags.

        Returns list of dicts with keys: id, type, tags, summary, content, created, updated.
        """
        index = self._load_index()
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored = []
        for entry in index["memories"]:
            if memory_type and entry["type"] != memory_type:
                continue
            entry_tokens = self._tokenize(entry["summary"])
            tag_tokens = self._tokenize(" ".join(entry.get("tags", [])))
            all_tokens = entry_tokens | tag_tokens

            if not all_tokens:
                continue
            overlap = len(query_tokens.intersection(all_tokens))
            if overlap > 0:
                scored.append((overlap, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, entry in scored[:limit]:
            content = self._read_memory_file(entry["file"])
            results.append({
                "id": entry["id"],
                "type": entry["type"],
                "tags": entry.get("tags", []),
                "summary": entry["summary"],
                "content": content or "",
                "created": entry["created"],
                "updated": entry.get("updated", entry["created"]),
            })
        return results

    async def get(self, memory_id: str) -> dict | None:
        """Get a single memory by ID. Returns dict or None."""
        index = self._load_index()
        for entry in index["memories"]:
            if entry["id"] == memory_id:
                content = self._read_memory_file(entry["file"])
                return {
                    "id": entry["id"],
                    "type": entry["type"],
                    "tags": entry.get("tags", []),
                    "summary": entry["summary"],
                    "content": content or "",
                    "created": entry["created"],
                    "updated": entry.get("updated", entry["created"]),
                }
        return None

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if deleted, False if not found."""
        async with self._lock:
            index = self._load_index()
            for i, entry in enumerate(index["memories"]):
                if entry["id"] == memory_id:
                    # Remove file
                    abs_path = os.path.join(self._base_dir, entry["file"])
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
                    # Remove from index
                    index["memories"].pop(i)
                    self._save_index()
                    return True
            return False

    def get_summaries_by_type(self, *types: str) -> list[str]:
        """Get summary strings for all memories of given types. Synchronous, index-only."""
        index = self._load_index()
        return [
            entry["summary"]
            for entry in index["memories"]
            if entry["type"] in types
        ]

    def get_recent_events(self, days: int = 7) -> list[str]:
        """Get summaries of events created/updated within the last N days."""
        index = self._load_index()
        cutoff = datetime.now().isoformat(timespec="seconds")
        # Simple approach: parse the date prefix from the updated field
        from datetime import timedelta
        cutoff_dt = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff_dt.isoformat(timespec="seconds")

        results = []
        for entry in index["memories"]:
            if entry["type"] != "event":
                continue
            updated = entry.get("updated", entry.get("created", ""))
            if updated >= cutoff_str:
                results.append(entry["summary"])
        return results
```

- [ ] **Step 3: Verify the module imports correctly**

Run: `cd /c/Users/10692/.cline/worktrees/fe69d/voice-assistant && python -c "from memory.store import MemoryStore; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add memory/__init__.py memory/store.py
git commit -m "feat(memory): implement MemoryStore with CRUD, index, and dedup"
```

---

### Task 3: Implement MemoryLoader — System Prompt Injection

**Files:**
- Create: `memory/loader.py`

- [ ] **Step 1: Write MemoryLoader implementation**

Create `memory/loader.py`:

```python
"""MemoryLoader: builds memory context for injection into the system prompt."""

from memory.store import MemoryStore


class MemoryLoader:
    """Loads user profile, preferences, and recent events from the memory index
    and formats them for system prompt injection."""

    def __init__(self, store: MemoryStore):
        self._store = store

    def build_context(self) -> str:
        """Build a memory context string to append to the system prompt.

        Returns empty string if no memories exist.
        """
        sections = []

        # User profile + preferences
        profile_items = self._store.get_summaries_by_type("user_profile", "preference")
        if profile_items:
            lines = "\n".join(f"- {item}" for item in profile_items)
            sections.append(f"## User Profile\n{lines}")

        # Recent events (last 7 days)
        event_items = self._store.get_recent_events(days=7)
        if event_items:
            lines = "\n".join(f"- {item}" for item in event_items)
            sections.append(f"## Recent Events\n{lines}")

        if not sections:
            return ""

        return "\n\n" + "\n\n".join(sections)
```

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from memory.loader import MemoryLoader; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add memory/loader.py
git commit -m "feat(memory): implement MemoryLoader for system prompt injection"
```

---

### Task 4: Implement Agent Tools — save_memory and recall_memory

**Files:**
- Create: `agent/tools/memory.py`
- Modify: `agent/tools/definitions.py`
- Modify: `agent/tool_executor.py`

- [ ] **Step 1: Create agent/tools/memory.py**

Create `agent/tools/memory.py`:

```python
"""Memory tools for the AI agent — save and recall memories."""

from memory.store import MemoryStore

# Module-level store instance, initialized in main.py or on first use
_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    """Get or create the shared MemoryStore instance."""
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def set_store(store: MemoryStore):
    """Set the shared MemoryStore instance (for dependency injection)."""
    global _store
    _store = store


async def save_memory(memory_type: str, summary: str, content: str,
                      tags: list[str] | None = None) -> str:
    """Save a memory explicitly. Returns confirmation message."""
    store = get_store()
    tags = tags or []
    try:
        memory_id = await store.save(
            memory_type=memory_type,
            tags=tags,
            summary=summary,
            content=content,
            source="explicit",
        )
        return f"Saved to memory (id: {memory_id}): {summary}"
    except Exception as e:
        return f"Failed to save memory: {e}"


async def recall_memory(query: str, memory_type: str | None = None) -> str:
    """Search memories and return results as formatted text."""
    store = get_store()
    try:
        results = await store.search(query=query, memory_type=memory_type, limit=5)
        if not results:
            return "No matching memories found."

        parts = []
        for r in results:
            tags_str = ", ".join(r["tags"]) if r["tags"] else "none"
            parts.append(
                f"[{r['type']}] {r['summary']}\n"
                f"  Tags: {tags_str}\n"
                f"  Content: {r['content']}\n"
                f"  Updated: {r['updated']}"
            )
        return "\n\n".join(parts)
    except Exception as e:
        return f"Memory search failed: {e}"
```

- [ ] **Step 2: Add tool schemas to definitions.py**

Add these two tool definitions to the end of the `TOOLS` list in `agent/tools/definitions.py` (before the closing `]`):

```python
    {
        "name": "save_memory",
        "description": (
            "Save information to long-term memory. Use when the user explicitly "
            "asks you to remember something, e.g. '记住...', '记下来...', 'remember that...'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["user_profile", "fact", "event", "preference"],
                    "description": "Category of information to save",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords for searchability",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief one-line summary of the memory",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to remember",
                },
            },
            "required": ["type", "summary", "content"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Search long-term memory for stored information. Use when the user asks "
            "about something they previously told you, or when you need stored facts, "
            "contacts, or knowledge."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memory",
                },
                "type": {
                    "type": "string",
                    "enum": ["user_profile", "fact", "event", "preference"],
                    "description": "Optional: filter by memory type",
                },
            },
            "required": ["query"],
        },
    },
```

- [ ] **Step 3: Register tools in tool_executor.py**

Add import at the top of `agent/tool_executor.py`:

```python
from agent.tools.memory import save_memory, recall_memory
```

Add two new `elif` branches before the final `else` in the `execute_tool` function:

```python
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
```

- [ ] **Step 4: Verify imports work**

Run: `python -c "from agent.tools.memory import save_memory, recall_memory; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent/tools/memory.py agent/tools/definitions.py agent/tool_executor.py
git commit -m "feat(memory): add save_memory and recall_memory agent tools"
```

---

### Task 5: Integrate MemoryLoader into Agent Client

**Files:**
- Modify: `agent/client.py`

- [ ] **Step 1: Add MemoryLoader import and initialization**

Add these imports at the top of `agent/client.py` (after existing imports):

```python
from memory.store import MemoryStore
from memory.loader import MemoryLoader
```

Add after the `_client = ...` initialization (around line 17):

```python
_memory_store = MemoryStore()
_memory_loader = MemoryLoader(_memory_store)
```

- [ ] **Step 2: Modify the system prompt in chat() to include memory context**

In the `chat()` function, replace the `system=` line (line 51) in the `_client.messages.create()` call:

Replace:
```python
                system=f"{config.SYSTEM_PROMPT}\nCurrent date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}",
```

With:
```python
                system=(
                    f"{config.SYSTEM_PROMPT}\n"
                    f"Current date and time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %A')}"
                    f"{_memory_loader.build_context()}"
                ),
```

- [ ] **Step 3: Wire up the shared MemoryStore to agent tools**

Add after the `_memory_store = MemoryStore()` line:

```python
from agent.tools.memory import set_store as _set_memory_store
_set_memory_store(_memory_store)
```

This ensures the tools and the loader share the same `MemoryStore` instance and its index cache.

- [ ] **Step 4: Verify the module loads**

Run: `python -c "from agent.client import chat; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent/client.py
git commit -m "feat(memory): integrate MemoryLoader into agent system prompt"
```

---

### Task 6: Implement MemoryExtractor — Async Background Extraction

**Files:**
- Create: `memory/extractor.py`

- [ ] **Step 1: Write MemoryExtractor implementation**

Create `memory/extractor.py`:

```python
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

    def trigger(self, user_text: str, assistant_text: str):
        """Fire-and-forget: schedule extraction as a background task."""
        asyncio.create_task(self._extract(user_text, assistant_text))

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
```

- [ ] **Step 2: Verify the module imports**

Run: `python -c "from memory.extractor import MemoryExtractor; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add memory/extractor.py
git commit -m "feat(memory): implement async MemoryExtractor for background extraction"
```

---

### Task 7: Integrate MemoryExtractor into Agent Client

**Files:**
- Modify: `agent/client.py`

- [ ] **Step 1: Add MemoryExtractor to agent/client.py**

Add import at the top of `agent/client.py` (with the other memory imports):

```python
from memory.extractor import MemoryExtractor
```

Add after the `_memory_loader = ...` line:

```python
_memory_extractor = MemoryExtractor(_memory_store)
```

Modify the `chat()` function: after the line `return final_text` (around line 76), insert extraction trigger logic. Replace:

```python
            final_text = "\n".join(text_parts) if text_parts else ""
            conversation.add_assistant(final_text)
            print(f"[agent] Response: {final_text[:100]}")
            return final_text
```

With:

```python
            final_text = "\n".join(text_parts) if text_parts else ""
            conversation.add_assistant(final_text)
            print(f"[agent] Response: {final_text[:100]}")
            # Trigger async memory extraction (non-blocking)
            _memory_extractor.trigger(user_text, final_text)
            return final_text
```

- [ ] **Step 2: Verify everything loads together**

Run: `python -c "from agent.client import chat; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/client.py
git commit -m "feat(memory): trigger async memory extraction after each conversation turn"
```

---

### Task 8: Update System Prompt to Mention Memory Capabilities

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Update SYSTEM_PROMPT in config.py**

Replace the existing `SYSTEM_PROMPT` in `config.py`:

```python
SYSTEM_PROMPT = (
    "You are Jarvis, a helpful voice assistant. "
    "You can search the web, set alarms, play music, and remember things. "
    "You have a long-term memory — you can save and recall information across conversations. "
    "When the user asks you to remember something, use the save_memory tool. "
    "When you need to recall stored information, use the recall_memory tool. "
    "Keep responses concise and conversational — they will be spoken aloud. "
    "Respond in the same language the user speaks (Chinese or English). "
    "The user is located in Shanghai, China. "
    "The user input comes from speech recognition which may contain errors. "
    "Infer the intended meaning from context — for example 'cloud code' likely means 'Claude Code', "
    "'check GPT' might mean 'ChatGPT', etc. Do not ask for clarification on obvious misrecognitions."
)
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat(memory): update system prompt to describe memory capabilities"
```

---

### Task 9: Manual Integration Test

**Files:** None (testing only)

- [ ] **Step 1: Verify the full application starts**

Run: `python -c "import main; print('Imports OK')"`

If this fails due to runtime dependencies (e.g., audio devices), verify individual modules instead:

```bash
python -c "
from memory.store import MemoryStore
from memory.loader import MemoryLoader
from memory.extractor import MemoryExtractor
from agent.tools.memory import save_memory, recall_memory
from agent.tools.definitions import TOOLS
from agent.tool_executor import execute_tool
print(f'Tools defined: {len(TOOLS)}')
print(f'Memory tools: {[t[\"name\"] for t in TOOLS if \"memory\" in t[\"name\"]]}')
print('All imports OK')
"
```

Expected:
```
Tools defined: 5
Memory tools: ['save_memory', 'recall_memory']
All imports OK
```

- [ ] **Step 2: Test MemoryStore save and search**

```bash
python -c "
import asyncio
from memory.store import MemoryStore

async def test():
    store = MemoryStore('data/memory_test')
    mid = await store.save('fact', ['test'], 'Test memory', 'This is a test memory.', 'explicit')
    print(f'Saved: {mid}')
    results = await store.search('test')
    print(f'Found: {len(results)} results')
    print(f'Content: {results[0][\"content\"]}')
    await store.delete(mid)
    print('Deleted OK')
    # Cleanup
    import shutil
    shutil.rmtree('data/memory_test', ignore_errors=True)

asyncio.run(test())
"
```

Expected:
```
Saved: mem_20260330_...
Found: 1 results
Content: This is a test memory.
Deleted OK
```

- [ ] **Step 3: Test MemoryLoader with empty memory**

```bash
python -c "
from memory.store import MemoryStore
from memory.loader import MemoryLoader

store = MemoryStore('data/memory_test')
loader = MemoryLoader(store)
ctx = loader.build_context()
print(f'Empty context: \"{ctx}\"')
assert ctx == '', 'Should be empty string when no memories exist'
print('OK')
"
```

Expected:
```
Empty context: ""
OK
```

- [ ] **Step 4: Commit (no changes, just verify)**

No files to commit — this task is verification only. If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix(memory): fixes from integration testing"
```
