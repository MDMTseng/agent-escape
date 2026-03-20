"""Tests for the World simulation container."""

from agenttown.world.actions import Examine, Move, PickUp
from agenttown.world.models import (
    AgentState,
    Door,
    EntityState,
    Item,
    Room,
    WorldState,
)
from agenttown.world.world import World


def _make_world():
    ws = WorldState()
    r1 = Room(id="r1", name="Room A", description="First room")
    r2 = Room(id="r2", name="Room B", description="Second room")
    ws.add_room(r1)
    ws.add_room(r2)

    key = Item(id="key1", name="Key", portable=True)
    r1.add_entity(key)

    door = Door(id="d1", name="Door", room_a="r1", room_b="r2", locked=False)
    ws.add_door(door, direction_from_a="north", direction_from_b="south")

    agent = AgentState(id="a1", name="Alice", room_id="r1", goal="Escape")
    ws.add_agent(agent)

    return World(state=ws), agent


def test_perceive_sees_room_contents():
    world, agent = _make_world()
    perception = world.perceive(agent)

    assert perception["room"]["name"] == "Room A"
    assert any(e["name"] == "Key" for e in perception["entities"])
    assert any(e["direction"] == "north" for e in perception["exits"])
    assert perception["goal"] == "Escape"


def test_perceive_shows_inventory():
    world, agent = _make_world()
    world.process_action(PickUp(target="Key"), agent)

    perception = world.perceive(agent)
    assert any(i["name"] == "Key" for i in perception["inventory"])
    assert not any(e["name"] == "Key" for e in perception["entities"])


def test_process_action_records_events():
    world, agent = _make_world()
    events = world.process_action(Examine(target="room"), agent)

    assert len(events) > 0
    assert events[0].event_type == "examine"

    log_events = world.event_log.events_for_agent("a1")
    assert len(log_events) > 0


def test_advance_tick():
    world, _ = _make_world()
    assert world.tick == 0
    world.advance_tick()
    assert world.tick == 1


def test_snapshot_and_restore():
    world, agent = _make_world()
    world.process_action(PickUp(target="Key"), agent)
    world.advance_tick()

    snapshot = world.snapshot()
    restored = World.from_snapshot(snapshot)

    assert restored.tick == 1
    assert restored.state.agents["a1"].has_item("key") is not None


def test_perceive_recent_events():
    world, agent = _make_world()
    # Tick 0: do something
    world.process_action(Examine(target="room"), agent)
    world.advance_tick()

    # Tick 1: perceive should show tick 0's events
    perception = world.perceive(agent)
    assert len(perception["recent_events"]) > 0
