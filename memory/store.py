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

            dup = self._find_duplicate(memory_type, tags, summary, source)
            if dup:
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
        """Search memories by keyword matching on summary and tags."""
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
                    abs_path = os.path.join(self._base_dir, entry["file"])
                    if os.path.exists(abs_path):
                        os.remove(abs_path)
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
