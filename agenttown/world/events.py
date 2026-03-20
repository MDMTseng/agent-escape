"""Event system — records what happens each tick for agent perception."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Something that happened in the world."""

    tick: int
    event_type: str  # "move", "pick_up", "use", "talk", "examine", "fail", "state_change"
    actor_id: str  # agent who caused it
    room_id: str  # room where it happened
    description: str  # human-readable description
    visible_to: list[str] = Field(default_factory=list)  # agent ids who can perceive this
    data: dict = Field(default_factory=dict)  # structured payload for programmatic use


class EventLog:
    """Collects and queries events."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def record(self, event: Event) -> None:
        self._events.append(event)

    def events_for_agent(self, agent_id: str, tick: int | None = None) -> list[Event]:
        results = [e for e in self._events if agent_id in e.visible_to]
        if tick is not None:
            results = [e for e in results if e.tick == tick]
        return results

    def events_at_tick(self, tick: int) -> list[Event]:
        return [e for e in self._events if e.tick == tick]

    def all_events(self) -> list[Event]:
        return list(self._events)

    @property
    def last_tick(self) -> int:
        if not self._events:
            return -1
        return self._events[-1].tick
