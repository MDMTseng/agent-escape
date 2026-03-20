"""Tests for actions and the rules engine."""

from agenttown.world.actions import (
    Drop,
    Examine,
    Move,
    PickUp,
    Talk,
    Use,
    Wait,
    parse_action,
)
from agenttown.world.models import (
    AgentState,
    Door,
    Entity,
    EntityState,
    Item,
    Room,
    WorldState,
)
from agenttown.world.rules import execute_action


def _make_simple_world():
    """Two rooms connected by a door, one agent, one item."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A", description="First room")
    r2 = Room(id="r2", name="Room B", description="Second room")
    ws.add_room(r1)
    ws.add_room(r2)

    key = Item(id="key1", name="Silver Key", description="A shiny key", portable=True)
    r1.add_entity(key)

    heavy = Entity(id="heavy1", name="Heavy Statue", description="Too heavy to lift")
    r1.add_entity(heavy)

    door = Door(
        id="d1", name="Oak Door", room_a="r1", room_b="r2",
        locked=False, state=EntityState.OPEN,
    )
    ws.add_door(door, direction_from_a="north", direction_from_b="south")

    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)

    return ws, agent


def test_parse_action():
    a = parse_action({"type": "move", "direction": "north"})
    assert isinstance(a, Move)
    assert a.direction == "north"

    a = parse_action({"type": "unknown_thing"})
    assert isinstance(a, Wait)


def test_move_success():
    ws, agent = _make_simple_world()
    result = execute_action(Move(direction="north"), agent, ws, tick=0)
    assert result.success
    assert agent.room_id == "r2"


def test_move_no_exit():
    ws, agent = _make_simple_world()
    result = execute_action(Move(direction="west"), agent, ws, tick=0)
    assert not result.success
    assert agent.room_id == "r1"


def test_move_locked_door():
    ws, agent = _make_simple_world()
    ws.doors["d1"].locked = True
    result = execute_action(Move(direction="north"), agent, ws, tick=0)
    assert not result.success
    assert agent.room_id == "r1"


def test_pick_up_success():
    ws, agent = _make_simple_world()
    result = execute_action(PickUp(target="Silver Key"), agent, ws, tick=0)
    assert result.success
    assert agent.has_item("silver key") is not None
    assert "key1" not in ws.rooms["r1"].entities


def test_pick_up_not_found():
    ws, agent = _make_simple_world()
    result = execute_action(PickUp(target="nonexistent"), agent, ws, tick=0)
    assert not result.success


def test_pick_up_non_portable():
    ws, agent = _make_simple_world()
    # Heavy Statue is an Entity, not an Item — should fail
    result = execute_action(PickUp(target="Heavy Statue"), agent, ws, tick=0)
    assert not result.success


def test_drop_item():
    ws, agent = _make_simple_world()
    execute_action(PickUp(target="Silver Key"), agent, ws, tick=0)
    assert agent.has_item("silver key") is not None

    result = execute_action(Drop(target="Silver Key"), agent, ws, tick=1)
    assert result.success
    assert agent.has_item("silver key") is None
    # Item should be back in the room
    assert any(e.name == "Silver Key" for e in ws.rooms["r1"].entities.values())


def test_examine_room():
    ws, agent = _make_simple_world()
    result = execute_action(Examine(target="room"), agent, ws, tick=0)
    assert result.success
    assert "Room A" in result.events[0].description


def test_examine_entity():
    ws, agent = _make_simple_world()
    result = execute_action(Examine(target="Silver Key"), agent, ws, tick=0)
    assert result.success
    assert "Silver Key" in result.events[0].description


def test_examine_reveals_hidden():
    ws, agent = _make_simple_world()
    room = ws.rooms["r1"]

    hidden = Item(id="secret", name="Secret Note", state=EntityState.HIDDEN)
    room.add_entity(hidden)

    painting = Entity(
        id="painting", name="Painting",
        description="A painting",
        properties={"on_examine": {"reveal": ["secret"], "message": "Found something!"}},
    )
    room.add_entity(painting)

    result = execute_action(Examine(target="Painting"), agent, ws, tick=0)
    assert result.success
    assert room.entities["secret"].state == EntityState.DEFAULT


def test_talk_broadcast():
    ws, agent = _make_simple_world()
    bob = AgentState(id="a2", name="Bob", room_id="r1")
    ws.add_agent(bob)

    result = execute_action(Talk(message="Hello!"), agent, ws, tick=0)
    assert result.success
    assert "a2" in result.events[0].visible_to


def test_talk_direct():
    ws, agent = _make_simple_world()
    bob = AgentState(id="a2", name="Bob", room_id="r1")
    ws.add_agent(bob)

    result = execute_action(Talk(message="Hey Bob", to="Bob"), agent, ws, tick=0)
    assert result.success
    assert "a2" in result.events[0].visible_to


def test_talk_target_not_found():
    ws, agent = _make_simple_world()
    result = execute_action(Talk(message="Hello", to="Nobody"), agent, ws, tick=0)
    assert not result.success


def test_use_key_on_door():
    ws, agent = _make_simple_world()
    ws.doors["d1"].locked = True
    ws.doors["d1"].key_id = "key1"

    # Pick up the key first
    execute_action(PickUp(target="Silver Key"), agent, ws, tick=0)
    assert agent.has_item("silver key") is not None

    # Use key on door
    result = execute_action(Use(item="Silver Key", target="Oak Door"), agent, ws, tick=1)
    assert result.success
    assert not ws.doors["d1"].locked
    assert agent.has_item("silver key") is None  # key consumed


def test_use_without_item():
    ws, agent = _make_simple_world()
    result = execute_action(Use(item="Silver Key", target="Oak Door"), agent, ws, tick=0)
    # Key is in the room, not in inventory
    assert not result.success


def test_wait():
    ws, agent = _make_simple_world()
    result = execute_action(Wait(), agent, ws, tick=0)
    assert result.success


def test_event_visibility():
    """Events should only be visible to agents in the same room."""
    ws, agent = _make_simple_world()
    bob = AgentState(id="a2", name="Bob", room_id="r2")  # Bob is in room B
    ws.add_agent(bob)

    result = execute_action(Examine(target="room"), agent, ws, tick=0)
    assert result.success
    # Bob should NOT see Alice's action (different room)
    assert "a2" not in result.events[0].visible_to
    assert "a1" in result.events[0].visible_to
