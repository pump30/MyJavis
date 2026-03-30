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
