"""Tests for the World simulation container."""

from agenttown.world.actions import Examine, Move, PickUp, Talk
from agenttown.world.models import (
    AgentState,
    Door,
    Entity,
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


# ---------------------------------------------------------------------------
# Change detection tests
# ---------------------------------------------------------------------------

def test_changes_empty_on_first_perceive():
    """First perception should have no changes (no previous state)."""
    world, agent = _make_world()
    perception = world.perceive(agent)
    assert perception["changes"] == []


def test_changes_detect_entity_gone():
    """Picking up an entity should show it as gone in changes."""
    world, agent = _make_world()
    # First perceive to establish baseline
    world.perceive(agent)
    world.advance_tick()

    # Pick up the key
    world.process_action(PickUp(target="Key"), agent)
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Key" in c and "gone" in c for c in perception["changes"])


def test_changes_detect_room_move():
    """Moving to a new room should show in changes."""
    world, agent = _make_world()
    world.perceive(agent)
    world.advance_tick()

    world.process_action(Move(direction="north"), agent)
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("moved to Room B" in c for c in perception["changes"])


def test_changes_detect_agent_arrived():
    """A new agent appearing in the room should show in changes."""
    world, agent = _make_world()
    # Add a second agent in room 2
    bob = AgentState(id="b1", name="Bob", room_id="r2")
    world.state.add_agent(bob)

    # First perceive for alice (alone in r1)
    world.perceive(agent)
    world.advance_tick()

    # Move bob to r1
    bob.room_id = "r1"
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Bob" in c and "arrived" in c for c in perception["changes"])


def test_changes_detect_agent_left():
    """An agent leaving the room should show in changes."""
    world, agent = _make_world()
    bob = AgentState(id="b1", name="Bob", room_id="r1")
    world.state.add_agent(bob)

    world.perceive(agent)
    world.advance_tick()

    bob.room_id = "r2"
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Bob" in c and "left" in c for c in perception["changes"])


def test_changes_detect_entity_state_change():
    """An entity changing state should show in changes."""
    world, agent = _make_world()
    # Add a lockbox entity
    lockbox = Entity(id="lb1", name="Lockbox", state=EntityState.LOCKED)
    world.state.rooms["r1"].add_entity(lockbox)

    world.perceive(agent)
    world.advance_tick()

    lockbox.state = EntityState.UNLOCKED
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Lockbox" in c and "unlocked" in c for c in perception["changes"])


def test_changes_detect_door_unlocked():
    """A door becoming unlocked should show in changes."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    r2 = Room(id="r2", name="Room B")
    ws.add_room(r1)
    ws.add_room(r2)
    door = Door(id="d1", name="Iron Gate", room_a="r1", room_b="r2", locked=True, key_id="key1")
    ws.add_door(door, direction_from_a="east", direction_from_b="west")
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    world.perceive(agent)
    world.advance_tick()

    # Unlock the door
    door.locked = False
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Iron Gate" in c and "unlocked" in c for c in perception["changes"])


def test_changes_detect_entity_appeared():
    """A new entity appearing in the room should show in changes."""
    world, agent = _make_world()
    world.perceive(agent)
    world.advance_tick()

    # Add a new entity
    gem = Entity(id="gem1", name="Ruby Gem")
    world.state.rooms["r1"].add_entity(gem)
    world.advance_tick()

    perception = world.perceive(agent)
    assert any("Ruby Gem" in c and "appeared" in c for c in perception["changes"])


# ---------------------------------------------------------------------------
# Directed messages tests
# ---------------------------------------------------------------------------

def test_messages_for_agent_directed_talk():
    """Talk events directed to this agent should appear in messages_for_agent."""
    world, agent = _make_world()
    bob = AgentState(id="b1", name="Bob", room_id="r1")
    world.state.add_agent(bob)

    # Bob talks to Alice
    world.process_action(Talk(message="The code is 1234", to="Alice"), bob)
    world.advance_tick()

    perception = world.perceive(agent)
    assert len(perception["messages_for_agent"]) == 1
    assert "1234" in perception["messages_for_agent"][0]
    assert "Bob" in perception["messages_for_agent"][0]


def test_messages_for_agent_excludes_broadcast():
    """Broadcast talk events should NOT appear in messages_for_agent."""
    world, agent = _make_world()
    bob = AgentState(id="b1", name="Bob", room_id="r1")
    world.state.add_agent(bob)

    # Bob talks to room (no 'to' specified)
    world.process_action(Talk(message="Hello everyone"), bob)
    world.advance_tick()

    perception = world.perceive(agent)
    assert len(perception["messages_for_agent"]) == 0


# ---------------------------------------------------------------------------
# Subtle hints tests
# ---------------------------------------------------------------------------

def test_hints_subtle_key_door():
    """Key+door hint should be subtle, not give the solution."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    r2 = Room(id="r2", name="Room B")
    ws.add_room(r1)
    ws.add_room(r2)
    door = Door(id="d1", name="Steel Door", room_a="r1", room_b="r2", locked=True, key_id="key1")
    ws.add_door(door, direction_from_a="east", direction_from_b="west")
    key = Item(id="key1", name="Brass Key", portable=True)
    agent = AgentState(id="a1", name="Alice", room_id="r1", inventory=[key])
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    # Should NOT say "Use it!" or mention the key by name
    assert "Use it!" not in hint
    assert "Brass Key" not in hint
    # Should be subtle
    assert "keyhole" in hint
    assert "inventory" in hint.lower()


def test_hints_subtle_combination_lock():
    """Combination lock hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    puzzle = Entity(id="p1", name="Puzzle Box", properties={"puzzle_type": "combination_lock"})
    r1.add_entity(puzzle)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "numbered dial" in hint
    assert "await input" in hint
    # Should NOT say "Use interact"
    assert "Use interact" not in hint


def test_hints_subtle_pressure_plate():
    """Pressure plate hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    plate = Entity(id="pp1", name="Floor Plate", properties={"puzzle_type": "pressure_plate"})
    r1.add_entity(plate)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "depressed" in hint
    assert "Heavy objects" in hint


def test_hints_subtle_password_door():
    """Password door hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    pw_door = Entity(id="pwd1", name="Magic Archway", properties={"puzzle_type": "password_door"})
    r1.add_entity(pw_door)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "hums with energy" in hint
    assert "respond to sound" in hint


def test_hints_subtle_lever():
    """Lever hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    lever = Entity(id="lv1", name="Iron Lever", properties={"puzzle_type": "lever"})
    r1.add_entity(lever)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "Iron Lever" in hint
    assert "pulled" in hint
    # Should NOT say "Use interact"
    assert "Use interact" not in hint


def test_hints_subtle_combinable():
    """Combinable items hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    part_a = Item(id="pa", name="Handle", properties={"combine_with": "Blade"})
    part_b = Item(id="pb", name="Blade")
    agent = AgentState(id="a1", name="Alice", room_id="r1", inventory=[part_a, part_b])
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "fit together" in hint
    # Should NOT say "You can combine"
    assert "You can combine" not in hint


def test_hints_subtle_usable_on():
    """Usable item hint should be subtle."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    pedestal = Entity(id="ped1", name="Stone Pedestal")
    r1.add_entity(pedestal)
    orb = Item(id="orb1", name="Crystal Orb", usable_on=["Stone Pedestal"])
    agent = AgentState(id="a1", name="Alice", room_id="r1", inventory=[orb])
    ws.add_agent(agent)
    world = World(state=ws)

    hints = world._generate_hints(agent, r1)
    assert len(hints) >= 1
    hint = hints[0]
    assert "Stone Pedestal" in hint
    assert "something you're carrying" in hint
    # Should NOT say "You can use"
    assert "You can use" not in hint


# ---------------------------------------------------------------------------
# Explored rooms tracking tests
# ---------------------------------------------------------------------------

def test_explored_rooms_empty_initially():
    """No rooms should be explored at start."""
    world, agent = _make_world()
    assert world.get_explored_rooms(agent.id) == set()


def test_explored_rooms_after_two_examines():
    """A room should be 'explored' after examining at least 2 entities."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    ws.add_room(r1)
    e1 = Entity(id="e1", name="Painting")
    e2 = Entity(id="e2", name="Bookshelf")
    e3 = Entity(id="e3", name="Desk")
    r1.add_entity(e1)
    r1.add_entity(e2)
    r1.add_entity(e3)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    # Examine first entity
    world.process_action(Examine(target="Painting"), agent)
    world.advance_tick()
    world.perceive(agent)  # triggers _track_examine
    assert world.get_explored_rooms(agent.id) == set()

    # Examine second entity
    world.process_action(Examine(target="Bookshelf"), agent)
    world.advance_tick()
    world.perceive(agent)
    assert "r1" in world.get_explored_rooms(agent.id)


def test_visited_vs_explored_in_perception():
    """Perception should distinguish visited from explored rooms."""
    ws = WorldState()
    r1 = Room(id="r1", name="Room A")
    r2 = Room(id="r2", name="Room B")
    ws.add_room(r1)
    ws.add_room(r2)
    e1 = Entity(id="e1", name="Painting")
    e2 = Entity(id="e2", name="Bookshelf")
    r1.add_entity(e1)
    r1.add_entity(e2)
    door = Door(id="d1", name="Door", room_a="r1", room_b="r2", locked=False)
    ws.add_door(door, direction_from_a="north", direction_from_b="south")
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    world = World(state=ws)

    # Examine 2 entities in room A to make it explored
    world.process_action(Examine(target="Painting"), agent)
    world.process_action(Examine(target="Bookshelf"), agent)
    world.advance_tick()
    world.perceive(agent)  # track examine events

    # Move to room B
    world.process_action(Move(direction="north"), agent)
    world.advance_tick()

    perception = world.perceive(agent)
    assert "Room A" in perception["explored_rooms"]
    assert "Room B" in perception["visited_rooms"]
    assert "Room A" not in perception["visited_rooms"]
    assert "Room B" not in perception["explored_rooms"]


def test_perception_has_changes_key():
    """Perception dict should always have 'changes' key."""
    world, agent = _make_world()
    perception = world.perceive(agent)
    assert "changes" in perception
    assert isinstance(perception["changes"], list)


def test_perception_has_messages_for_agent_key():
    """Perception dict should always have 'messages_for_agent' key."""
    world, agent = _make_world()
    perception = world.perceive(agent)
    assert "messages_for_agent" in perception
    assert isinstance(perception["messages_for_agent"], list)
