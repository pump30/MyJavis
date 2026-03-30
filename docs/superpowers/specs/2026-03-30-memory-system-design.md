# Jarvis Memory System Design

**Date:** 2026-03-30
**Status:** Approved

## Overview

Add a persistent memory system to Jarvis that enables it to remember user information, facts, events, and preferences across sessions. The system uses Markdown files for human-readable storage, a JSON index for efficient retrieval, and an abstraction layer that allows future migration to vector-based retrieval.

## Goals

1. Remember user identity, preferences, and habits (user profile)
2. Store knowledge the user explicitly teaches Jarvis (facts, contacts, etc.)
3. Automatically extract noteworthy information from conversations (async, non-blocking)
4. Retrieve relevant memories during conversations via dual-layer architecture
5. Design for progressive upgrade: keyword search now, vector search later

## Memory Categories

| Type | Description | Examples |
|------|-------------|----------|
| `user_profile` | User identity, role, habits | "User is named 小明, software engineer" |
| `fact` | Explicit knowledge/data | "Wi-Fi password is abc123", "张三's phone: 138xxxx" |
| `event` | Events, schedules, experiences | "Business trip to Beijing next Tuesday" |
| `preference` | Interaction preferences | "User prefers short answers", "Don't call user 先生" |

## Storage Design

### Directory Structure

```
data/memory/
  index.json              # Metadata index for all memories
  user_profile/
    mem_20260330_001.md
  fact/
    mem_20260330_002.md
  event/
    mem_20260330_003.md
  preference/
    mem_20260330_004.md
```

### Memory File Format (Markdown with YAML Frontmatter)

```markdown
---
id: "mem_20260330_001"
type: "fact"
tags: ["contact", "phone"]
summary: "张三的电话号码"
created: "2026-03-30T14:22:00"
updated: "2026-03-30T14:22:00"
source: "explicit"
---

张三的电话号码是 138-0000-1234，他是用户的同事。
```

- `source`: `explicit` (user said "remember this") or `inferred` (auto-extracted)

### index.json Structure

```json
{
  "memories": [
    {
      "id": "mem_20260330_001",
      "type": "fact",
      "tags": ["contact", "phone"],
      "summary": "张三的电话号码",
      "source": "explicit",
      "file": "fact/mem_20260330_001.md",
      "created": "2026-03-30T14:22:00",
      "updated": "2026-03-30T14:22:00"
    }
  ]
}
```

The index is small enough to load fully into memory. Search operates on `summary` and `tags` fields. On match, full Markdown content is read from disk.

## Memory Extraction (Write Flow)

### Trigger 1: Explicit Storage

When the user says "记住...", "记下来...", etc., Claude calls the `save_memory` tool synchronously within the current conversation. The user gets immediate confirmation.

### Trigger 2: Async Auto-Extraction

After each conversation turn completes (TTS response sent), a background task runs:

```
User speaks → STT → Claude replies → TTS plays
                                        ↓ (async, non-blocking)
                                  MemoryExtractor
                                        ↓
                               Claude API (lightweight prompt)
                                        ↓
                             New memories? → Write files + update index
```

The extraction prompt asks Claude to analyze the conversation turn and return structured JSON. Only clear facts are extracted — no speculation.

### Deduplication

Before writing, the system checks index.json for existing memories with overlapping `tags` AND keyword overlap in `summary` (using token intersection — if >50% of tokens in the new summary appear in an existing summary with the same type, it's considered a match). If a match is found (e.g., same person's phone number changed), the existing memory is updated rather than creating a duplicate. For auto-extracted memories (`source: inferred`), the dedup threshold is stricter to avoid false merges.

## Memory Retrieval (Read Flow)

### Layer 1: Profile Injection (Automatic, Every Turn)

Before each `chat()` call, `MemoryLoader` reads summaries from `user_profile`, `preference`, and recent `event` types from `index.json` (summary fields only — no file I/O for full content). These are appended to the system prompt:

```
{SYSTEM_PROMPT}
Current date and time: 2026-03-30 14:22:00 Monday

## User Profile
- User is 小明, a software engineer
- Prefers short answers
- Located in Shanghai

## Recent Events
- Business trip to Beijing on 2026-04-01
```

This has minimal performance impact — it only reads the in-memory index.

### Layer 2: Deep Retrieval Tool (On-Demand)

A `recall_memory` tool allows Claude to search for specific stored information when needed:

1. Search `index.json` — match `summary` and `tags` against query keywords
2. Read full Markdown content for matched memories
3. Return top-N results (default 5)

## New Agent Tools

### save_memory

```json
{
  "name": "save_memory",
  "description": "Save information to long-term memory. Use when the user explicitly asks you to remember something.",
  "input_schema": {
    "type": "object",
    "properties": {
      "type": {
        "type": "string",
        "enum": ["user_profile", "fact", "event", "preference"]
      },
      "tags": {
        "type": "array",
        "items": {"type": "string"}
      },
      "summary": {
        "type": "string",
        "description": "Brief one-line summary"
      },
      "content": {
        "type": "string",
        "description": "Full content to remember"
      }
    },
    "required": ["type", "summary", "content"]
  }
}
```

### recall_memory

```json
{
  "name": "recall_memory",
  "description": "Search Jarvis's memory for stored information. Use when the user asks about something they previously told you, or when you need stored facts, contacts, or knowledge.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "What to search for in memory"
      },
      "type": {
        "type": "string",
        "enum": ["user_profile", "fact", "event", "preference"],
        "description": "Optional: filter by memory type"
      }
    },
    "required": ["query"]
  }
}
```

## Module Architecture

### New Files

```
memory/                       # Memory system core (new package)
  __init__.py
  store.py                    # MemoryStore: file I/O, index management, CRUD
  extractor.py                # MemoryExtractor: async background extraction
  loader.py                   # MemoryLoader: load profile for system prompt injection

agent/tools/memory.py         # save_memory and recall_memory tool implementations
```

### Core Classes

**`MemoryStore`** — CRUD operations on memory files and index:
- `save(type, tags, summary, content, source) → str` — write Markdown + update index, return memory ID
- `search(query, type=None, limit=5) → list[dict]` — search index, return matched memories with full content
- `get(memory_id) → dict` — read single memory's full content
- `update(memory_id, **kwargs)` — update memory fields and file
- `delete(memory_id)` — remove memory file and index entry
- Internal: ID generation, dedup detection, asyncio Lock for concurrent writes

**`MemoryExtractor`** — async background extraction:
- `extract_from_conversation(messages) → None` — fire-and-forget async task
- Uses a lightweight Claude prompt to analyze conversation
- Calls `MemoryStore.save()` for each extracted memory
- Triggered in orchestrator's post-conversation callback

**`MemoryLoader`** — profile injection:
- `load_profile_summary() → str` — read user_profile + preference summaries from index
- `load_recent_events(days=7) → str` — read recent event summaries
- `build_context() → str` — combine into system prompt appendix
- Called in `agent/client.py` `chat()` before API call

### Integration Points

1. **`agent/tools/definitions.py`** — add `save_memory` and `recall_memory` tool schemas
2. **`agent/tool_executor.py`** — register routing for the two new tools
3. **`agent/client.py`** — call `MemoryLoader.build_context()` in `chat()` to inject profile into system prompt
4. **`pipeline/orchestrator.py`** — trigger `MemoryExtractor.extract_from_conversation()` after conversation turn completes
5. **`config.py`** — add `MEMORY_DIR = "data/memory"` and extraction-related constants

## Upgrade Path

The `MemoryStore` class provides the abstraction layer. Current implementation uses keyword matching on index.json. Future upgrade:

1. Add an `EmbeddingIndex` class that vectorizes summaries and content
2. Swap `MemoryStore.search()` internals to use cosine similarity
3. No changes needed to tools, loader, or extractor — only the store internals change

## Error Handling

- If memory directory doesn't exist, create it on first save
- If index.json is corrupted, rebuild from Markdown file frontmatter
- Extractor failures are logged but never surface to the user (background task)
- File write uses atomic write (write to temp file, then rename) to prevent corruption
