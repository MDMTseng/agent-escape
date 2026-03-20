"""World — the simulation container that ties everything together."""

from __future__ import annotations

from .actions import Action
from .events import Event, EventLog
from .models import AgentState, Room, WorldState
from .rules import execute_action


class World:
    """Manages world state, processes actions, and records events."""

    def __init__(self, state: WorldState | None = None) -> None:
        self.state = state or WorldState()
        self.event_log = EventLog()

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def finished(self) -> bool:
        return self.state.finished

    def perceive(self, agent: AgentState) -> dict:
        """Build a perception payload for an agent — what they can see/know right now."""
        room = self.state.get_agent_room(agent)
        others = [
            {"name": a.name, "description": a.description}
            for a in self.state.agents_in_room(room.id)
            if a.id != agent.id
        ]
        visible_entities = [
            {"name": e.name, "description": e.describe(), "state": e.state.value}
            for e in room.visible_entities()
        ]
        doors = []
        for direction, door_id in room.doors.items():
            door = self.state.doors[door_id]
            lock_info = " (locked)" if door.locked else ""
            doors.append({"direction": direction, "name": door.name + lock_info})

        recent_events = self.event_log.events_for_agent(agent.id, tick=self.state.tick - 1)
        event_descriptions = [e.description for e in recent_events]

        return {
            "tick": self.state.tick,
            "room": {
                "name": room.name,
                "description": room.description,
            },
            "entities": visible_entities,
            "exits": doors,
            "others": others,
            "inventory": [
                {"name": item.name, "description": item.describe()} for item in agent.inventory
            ],
            "recent_events": event_descriptions,
            "goal": agent.goal,
        }

    def process_action(self, action: Action, agent: AgentState) -> list[Event]:
        """Validate and execute an action, recording resulting events."""
        result = execute_action(action, agent, self.state, self.state.tick)
        for event in result.events:
            self.event_log.record(event)
        return result.events

    def advance_tick(self) -> None:
        """Move to the next tick."""
        self.state.tick += 1

    def snapshot(self) -> dict:
        """Serialize the full world state for saving or UI sync."""
        return self.state.model_dump()

    @classmethod
    def from_snapshot(cls, data: dict) -> World:
        """Restore a world from a serialized snapshot."""
        state = WorldState.model_validate(data)
        return cls(state=state)
