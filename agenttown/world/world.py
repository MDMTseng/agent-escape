"""World — the simulation container that ties everything together."""

from __future__ import annotations

from .actions import Action
from .events import Event, EventLog
from .models import AgentState, EntityState, Item, Room, WorldState
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

        # Generate action hints — tell agent what they CAN do
        hints = self._generate_hints(agent, room)

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
            "hints": hints,
            "goal": agent.goal,
        }

    def _generate_hints(self, agent: AgentState, room: Room) -> list[str]:
        """Generate actionable hints based on current state."""
        hints = []

        # Check if any inventory item is a key for a door in this room
        for direction, door_id in room.doors.items():
            door = self.state.doors[door_id]
            if door.locked and door.key_id:
                key_item = agent.has_item_by_id(door.key_id)
                if key_item:
                    hints.append(f"You have {key_item.name} which unlocks {door.name} ({direction}). Use it!")

        # Check for combination locks + known codes in inventory/entities
        for entity in room.visible_entities():
            pt = entity.properties.get("puzzle_type", "")
            if pt == "combination_lock" and entity.state != EntityState.SOLVED:
                hints.append(f"{entity.name} needs a code. Use interact to enter it.")
            elif pt == "password_door" and entity.state != EntityState.SOLVED:
                hints.append(f"{entity.name} responds to a spoken word. Try talking.")
            elif pt == "lever" and entity.state != EntityState.ACTIVATED:
                hints.append(f"{entity.name} can be pulled. Use interact.")
            elif pt == "pressure_plate" and entity.state != EntityState.SOLVED:
                hints.append(f"{entity.name} needs something heavy dropped on it.")

        # Check for combinable items
        for item in agent.inventory:
            combine_with = item.properties.get("combine_with")
            if combine_with:
                partner = agent.has_item(combine_with)
                if partner:
                    hints.append(f"You can combine {item.name} with {partner.name}!")

        # Check for usable items on room entities
        for item in agent.inventory:
            if item.usable_on:
                for target_name in item.usable_on:
                    matches = room.get_entities_by_name(target_name)
                    visible = [e for e in matches if e.state != EntityState.HIDDEN]
                    if visible:
                        hints.append(f"You can use {item.name} on {visible[0].name}.")

        return hints

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

    def full_snapshot(self) -> dict:
        """Snapshot including event log (for persistence)."""
        return {
            "state": self.state.model_dump(),
            "events": [e.model_dump() for e in self.event_log.all_events()],
        }

    @classmethod
    def from_full_snapshot(cls, data: dict) -> World:
        """Restore world with event history."""
        w = cls.from_snapshot(data["state"])
        for e_data in data.get("events", []):
            w.event_log.record(Event.model_validate(e_data))
        return w
