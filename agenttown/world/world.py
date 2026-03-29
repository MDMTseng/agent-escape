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
        # Track room visit history per agent: {agent_id: [(tick, room_id, room_name), ...]}
        self._room_history: dict[str, list[tuple[int, str, str]]] = {}
        # Track last action results per agent for feedback
        self._last_results: dict[str, list[str]] = {}
        # Track previous perception state per agent for change detection
        self._prev_perception: dict[str, dict] = {}
        # Track entities examined per room per agent: {agent_id: {room_id: set(entity_ids)}}
        self._examined_entities: dict[str, dict[str, set[str]]] = {}

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def finished(self) -> bool:
        return self.state.finished

    def _compute_changes(self, agent: AgentState, room: Room,
                         others: list[dict], visible_entities: list[dict],
                         doors: list[dict]) -> list[str]:
        """Compute what changed since last tick for this agent."""
        changes: list[str] = []
        prev = self._prev_perception.get(agent.id)
        if prev is None:
            return changes

        # Room changed
        if prev.get("room_id") != room.id:
            changes.append(f"You moved to {room.name}")

        # Entities appeared or changed state
        prev_entities = {e["name"]: e["state"] for e in prev.get("entities", [])}
        curr_entities = {e["name"]: e["state"] for e in visible_entities}

        for name, state in curr_entities.items():
            if name not in prev_entities:
                changes.append(f"{name} appeared")
            elif prev_entities[name] != state:
                changes.append(f"{name} changed to {state}")

        for name in prev_entities:
            if name not in curr_entities:
                changes.append(f"{name} is gone")

        # Doors unlocked
        prev_doors = {d["direction"]: d["name"] for d in prev.get("doors", [])}
        for d in doors:
            prev_name = prev_doors.get(d["direction"], "")
            if "(locked)" in prev_name and "(locked)" not in d["name"]:
                clean_name = d["name"].replace(" (locked)", "")
                changes.append(f"{clean_name} ({d['direction']}) is now unlocked")

        # Agents arrived / left
        prev_others = {o["name"] for o in prev.get("others", [])}
        curr_others = {o["name"] for o in others}
        for name in sorted(curr_others - prev_others):
            changes.append(f"{name} arrived")
        for name in sorted(prev_others - curr_others):
            changes.append(f"{name} left")

        return changes

    def _get_messages_for_agent(self, agent: AgentState) -> list[str]:
        """Extract Talk events directed specifically to this agent from recent events."""
        messages: list[str] = []
        recent = self.event_log.events_for_agent(agent.id, tick=self.state.tick - 1)
        for event in recent:
            if event.event_type == "talk" and event.data.get("to") == agent.id:
                actor_name = event.description.split(" says to ")[0] if " says to " in event.description else "Someone"
                msg = event.data.get("message", "")
                messages.append(f"{actor_name}: \"{msg}\"")
        return messages

    def _track_examine(self, agent: AgentState) -> None:
        """Track examined entities from recent events for exploration tracking."""
        recent = self.event_log.events_for_agent(agent.id, tick=self.state.tick - 1)
        agent_rooms = self._examined_entities.setdefault(agent.id, {})
        for event in recent:
            if event.event_type == "examine" and event.actor_id == agent.id:
                room_set = agent_rooms.setdefault(event.room_id, set())
                desc = event.description
                if " examines " in desc:
                    after_examines = desc.split(" examines ", 1)[1]
                    entity_name = after_examines.split(":")[0].strip()
                    room = self.state.rooms.get(event.room_id)
                    if room:
                        for e in room.entities.values():
                            if e.name == entity_name:
                                room_set.add(e.id)
                                break

    def get_explored_rooms(self, agent_id: str) -> set[str]:
        """Return set of room IDs where agent has examined at least 2 entities."""
        agent_rooms = self._examined_entities.get(agent_id, {})
        return {room_id for room_id, entities in agent_rooms.items()
                if len(entities) >= 2}

    def get_visited_rooms(self, agent_id: str) -> set[str]:
        """Return set of room IDs the agent has visited."""
        history = self._room_history.get(agent_id, [])
        return {h[1] for h in history}

    def perceive(self, agent: AgentState) -> dict:
        """Build a perception payload for an agent — what they can see/know right now."""
        room = self.state.get_agent_room(agent)

        # Track room visit history
        history = self._room_history.setdefault(agent.id, [])
        if not history or history[-1][1] != room.id:
            history.append((self.state.tick, room.id, room.name))

        # Track examined entities from last tick
        self._track_examine(agent)

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
        # Structured event data for programmatic fact extraction (no regex needed)
        structured_events = [
            {
                "type": e.event_type,
                "actor": e.actor_id,
                "description": e.description,
                **e.data,
            }
            for e in recent_events
        ]

        # Compute changes since last perception
        changes = self._compute_changes(agent, room, others, visible_entities, doors)

        # Get messages directed to this agent
        messages_for_agent = self._get_messages_for_agent(agent)

        # Store current state for next tick's diff
        self._prev_perception[agent.id] = {
            "room_id": room.id,
            "entities": visible_entities,
            "doors": doors,
            "others": others,
        }

        # Generate subtle observation hints
        hints = self._generate_hints(agent, room)

        # Last action results for this agent
        last_results = self._last_results.get(agent.id, [])

        # Build room exploration info
        visited = self.get_visited_rooms(agent.id)
        explored = self.get_explored_rooms(agent.id)
        visited_names = []
        explored_names = []
        seen_visited: set[str] = set()
        seen_explored: set[str] = set()
        for h in history:
            rid, rname = h[1], h[2]
            if rid in explored:
                if rname not in seen_explored:
                    explored_names.append(rname)
                    seen_explored.add(rname)
            else:
                if rname not in seen_visited:
                    visited_names.append(rname)
                    seen_visited.add(rname)

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
            "structured_events": structured_events,
            "last_results": last_results,
            "hints": hints,
            "changes": changes,
            "messages_for_agent": messages_for_agent,
            "room_history": [h[2] for h in history],
            "visited_rooms": visited_names,
            "explored_rooms": explored_names,
            "goal": agent.goal,
        }

    def _generate_hints(self, agent: AgentState, room: Room) -> list[str]:
        """Generate subtle observational hints — describe the world, don't give solutions."""
        hints = []

        # Check if any inventory item is a key for a door in this room
        for direction, door_id in room.doors.items():
            door = self.state.doors[door_id]
            if door.locked and door.key_id:
                key_item = agent.has_item_by_id(door.key_id)
                if key_item:
                    hints.append(
                        f"The {direction} door has a brass keyhole. "
                        f"Something in your inventory might fit."
                    )

        # Check for puzzle entities — subtle descriptions
        for entity in room.visible_entities():
            pt = entity.properties.get("puzzle_type", "")
            if pt == "combination_lock" and entity.state != EntityState.SOLVED:
                hints.append(
                    f"The {entity.name} has a numbered dial. It seems to await input."
                )
            elif pt == "password_door" and entity.state != EntityState.SOLVED:
                hints.append(
                    f"The archway hums with energy. It seems to respond to sound."
                )
            elif pt == "lever" and entity.state != EntityState.ACTIVATED:
                hints.append(
                    f"The {entity.name} juts from the wall. It looks like it can be pulled."
                )
            elif pt == "pressure_plate" and entity.state != EntityState.SOLVED:
                hints.append(
                    f"The floor plate is slightly depressed. Heavy objects might trigger it."
                )

        # Check for combinable items — subtle
        for item in agent.inventory:
            combine_with = item.properties.get("combine_with")
            if combine_with:
                partner = agent.has_item(combine_with)
                if partner:
                    hints.append(
                        f"{item.name} and {partner.name} look like they could fit together."
                    )

        # Check for usable items on room entities — subtle
        for item in agent.inventory:
            if item.usable_on:
                for target_name in item.usable_on:
                    matches = room.get_entities_by_name(target_name)
                    visible = [e for e in matches if e.state != EntityState.HIDDEN]
                    if visible:
                        hints.append(
                            f"{visible[0].name} looks like it could interact with "
                            f"something you're carrying."
                        )

        # If no specific hints, suggest exploring
        if not hints:
            for direction, door_id in room.doors.items():
                door = self.state.doors[door_id]
                if not door.locked:
                    hints.append(f"An open passage leads {direction}.")
                    break

        return hints

    def process_action(self, action: Action, agent: AgentState) -> list[Event]:
        """Validate and execute an action, recording resulting events."""
        result = execute_action(action, agent, self.state, self.state.tick)
        for event in result.events:
            self.event_log.record(event)

        # Track action results for feedback to agent on next perception
        agent_results = self._last_results.setdefault(agent.id, [])
        for event in result.events:
            agent_results.append(event.description)
        return result.events

    def clear_last_results(self, agent_id: str) -> None:
        """Clear last results after agent has seen them."""
        self._last_results[agent_id] = []

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
