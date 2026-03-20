"""Agent memory — tracks observations, conversations, and working knowledge."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory record."""

    tick: int
    content: str
    category: str = "observation"  # observation, conversation, discovery, plan


class AgentMemory:
    """Manages an agent's memory as a rolling window of observations.

    Memory is primarily the Claude message history itself, but this
    provides a structured summary layer for prompt construction.
    """

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: list[MemoryEntry] = []
        self._max_entries = max_entries

    def record(self, tick: int, content: str, category: str = "observation") -> None:
        self._entries.append(MemoryEntry(tick=tick, content=content, category=category))
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

    def recent(self, n: int = 20) -> list[MemoryEntry]:
        return self._entries[-n:]

    def by_category(self, category: str) -> list[MemoryEntry]:
        return [e for e in self._entries if e.category == category]

    def summary(self, n: int = 10) -> str:
        """Build a text summary of recent memories for prompt injection."""
        entries = self.recent(n)
        if not entries:
            return "No memories yet."
        lines = []
        for entry in entries:
            lines.append(f"[Tick {entry.tick}] ({entry.category}) {entry.content}")
        return "\n".join(lines)

    def all_entries(self) -> list[MemoryEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
