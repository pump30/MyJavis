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
