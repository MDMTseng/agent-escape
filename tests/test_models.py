"""Tests for core data models."""

from agenttown.world.models import (
    AgentState,
    Door,
    Entity,
    EntityState,
    Item,
    Room,
    WorldState,
)


def test_entity_describe():
    e = Entity(name="Box", description="A wooden box")
    assert e.describe() == "A wooden box"

    e2 = Entity(name="Box")
    assert e2.describe() == "Box"


def test_item_inventory():
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    key = Item(id="k1", name="Brass Key", description="A small key")

    agent.add_item(key)
    assert agent.has_item("brass key") is not None
    assert agent.has_item("nonexistent") is None

    removed = agent.remove_item("k1")
    assert removed is not None
    assert removed.name == "Brass Key"
    assert agent.has_item("brass key") is None


def test_room_entities():
    room = Room(id="r1", name="Study")
    item = Item(id="i1", name="Note", state=EntityState.DEFAULT)
    hidden = Item(id="i2", name="Secret Key", state=EntityState.HIDDEN)

    room.add_entity(item)
    room.add_entity(hidden)

    assert len(room.visible_entities()) == 1
    assert room.visible_entities()[0].name == "Note"
    assert len(room.get_entities_by_name("note")) == 1
    assert len(room.get_entities_by_name("key")) == 1  # hidden but still findable by name

    removed = room.remove_entity("i1")
    assert removed is not None
    assert len(room.visible_entities()) == 0


def test_door_other_side():
    door = Door(id="d1", name="Door", room_a="r1", room_b="r2")
    assert door.other_side("r1") == "r2"
    assert door.other_side("r2") == "r1"


def test_world_state_agents_in_room():
    ws = WorldState()
    room = Room(id="r1", name="Study")
    ws.add_room(room)

    a1 = AgentState(id="a1", name="Alice", room_id="r1")
    a2 = AgentState(id="a2", name="Bob", room_id="r1")
    ws.add_agent(a1)
    ws.add_agent(a2)

    assert len(ws.agents_in_room("r1")) == 2


def test_world_state_serializable():
    ws = WorldState()
    room = Room(id="r1", name="Study", description="A room")
    ws.add_room(room)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)

    data = ws.model_dump()
    restored = WorldState.model_validate(data)
    assert restored.rooms["r1"].name == "Study"
    assert restored.agents["a1"].name == "Alice"
