"""Core data models for the AgentTown virtual world."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _id() -> str:
    return uuid4().hex[:8]


class EntityState(str, Enum):
    DEFAULT = "default"
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    OPEN = "open"
    CLOSED = "closed"
    HIDDEN = "hidden"
    SOLVED = "solved"
    ACTIVATED = "activated"


class Entity(BaseModel):
    """Base world entity — anything that exists in a room."""

    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    state: EntityState = EntityState.DEFAULT
    properties: dict[str, Any] = Field(default_factory=dict)

    def describe(self) -> str:
        return self.description or self.name


class Item(Entity):
    """An entity that can be picked up and carried."""

    portable: bool = True
    usable_on: list[str] = Field(default_factory=list)


class Door(Entity):
    """Connects two rooms. May be locked."""

    room_a: str  # room id
    room_b: str  # room id
    locked: bool = False
    key_id: str | None = None
    state: EntityState = EntityState.CLOSED

    def other_side(self, room_id: str) -> str:
        if room_id == self.room_a:
            return self.room_b
        if room_id == self.room_b:
            return self.room_a
        raise ValueError(f"Room {room_id} is not connected to door {self.id}")


class Room(BaseModel):
    """A location in the world containing entities."""

    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    entities: dict[str, Entity] = Field(default_factory=dict)
    doors: dict[str, str] = Field(default_factory=dict)  # direction -> door_id

    def add_entity(self, entity: Entity) -> None:
        self.entities[entity.id] = entity

    def remove_entity(self, entity_id: str) -> Entity | None:
        return self.entities.pop(entity_id, None)

    def get_entities_by_name(self, name: str) -> list[Entity]:
        name_lower = name.lower()
        return [e for e in self.entities.values() if name_lower in e.name.lower()]

    def visible_entities(self) -> list[Entity]:
        return [e for e in self.entities.values() if e.state != EntityState.HIDDEN]


class AgentState(BaseModel):
    """The world-facing state of an agent."""

    id: str = Field(default_factory=_id)
    name: str
    description: str = ""
    room_id: str
    inventory: list[Item] = Field(default_factory=list)
    goal: str = ""

    def has_item(self, item_name: str) -> Item | None:
        name_lower = item_name.lower()
        for item in self.inventory:
            if name_lower in item.name.lower():
                return item
        return None

    def add_item(self, item: Item) -> None:
        self.inventory.append(item)

    def remove_item(self, item_id: str) -> Item | None:
        for i, item in enumerate(self.inventory):
            if item.id == item_id:
                return self.inventory.pop(i)
        return None


class WorldState(BaseModel):
    """Complete snapshot of the world at a point in time."""

    rooms: dict[str, Room] = Field(default_factory=dict)
    agents: dict[str, AgentState] = Field(default_factory=dict)
    doors: dict[str, Door] = Field(default_factory=dict)
    tick: int = 0
    finished: bool = False
    finish_reason: str = ""

    def get_room(self, room_id: str) -> Room:
        return self.rooms[room_id]

    def get_agent_room(self, agent: AgentState) -> Room:
        return self.rooms[agent.room_id]

    def agents_in_room(self, room_id: str) -> list[AgentState]:
        return [a for a in self.agents.values() if a.room_id == room_id]

    def add_room(self, room: Room) -> None:
        self.rooms[room.id] = room

    def add_agent(self, agent: AgentState) -> None:
        self.agents[agent.id] = agent

    def add_door(self, door: Door, direction_from_a: str, direction_from_b: str) -> None:
        self.doors[door.id] = door
        self.rooms[door.room_a].doors[direction_from_a] = door.id
        self.rooms[door.room_b].doors[direction_from_b] = door.id
