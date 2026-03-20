"""Tests for all 5 puzzle mechanisms + updated escape room."""

from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.actions import Combine, Drop, Examine, Interact, Move, PickUp, Talk, Use
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


# ---- Helpers ----

def _make_world_with_agent():
    ws = WorldState()
    room = Room(id="r1", name="Room", description="A room")
    ws.add_room(room)
    agent = AgentState(id="a1", name="Alice", room_id="r1")
    ws.add_agent(agent)
    return ws, room, agent


# ---- Mechanism 1: Combination Lock ----

class TestCombinationLock:
    def test_correct_code(self):
        ws, room, agent = _make_world_with_agent()
        box = Entity(
            id="box", name="Puzzle Box",
            properties={
                "puzzle_type": "combination_lock",
                "combination": "1847",
                "on_solve": {"set_state": "solved", "message": "It opens!"},
            },
        )
        room.add_entity(box)

        result = execute_action(Interact(target="Puzzle Box", payload="1847"), agent, ws, tick=0)
        assert result.success
        assert room.entities["box"].state == EntityState.SOLVED

    def test_wrong_code(self):
        ws, room, agent = _make_world_with_agent()
        box = Entity(
            id="box", name="Puzzle Box",
            properties={
                "puzzle_type": "combination_lock",
                "combination": "1847",
                "on_solve": {"set_state": "solved"},
            },
        )
        room.add_entity(box)

        result = execute_action(Interact(target="Puzzle Box", payload="0000"), agent, ws, tick=0)
        assert not result.success
        assert room.entities["box"].state != EntityState.SOLVED

    def test_reveals_hidden_item(self):
        ws, room, agent = _make_world_with_agent()
        hidden = Item(id="prize", name="Prize", state=EntityState.HIDDEN)
        room.add_entity(hidden)
        box = Entity(
            id="box", name="Puzzle Box",
            properties={
                "puzzle_type": "combination_lock",
                "combination": "42",
                "on_solve": {"set_state": "solved", "reveal": ["prize"]},
            },
        )
        room.add_entity(box)

        execute_action(Interact(target="Puzzle Box", payload="42"), agent, ws, tick=0)
        assert room.entities["prize"].state == EntityState.DEFAULT

    def test_already_solved(self):
        ws, room, agent = _make_world_with_agent()
        box = Entity(
            id="box", name="Puzzle Box", state=EntityState.SOLVED,
            properties={"puzzle_type": "combination_lock", "combination": "42"},
        )
        room.add_entity(box)

        result = execute_action(Interact(target="Puzzle Box", payload="42"), agent, ws, tick=0)
        assert not result.success


# ---- Mechanism 2: Pressure Plate ----

class TestPressurePlate:
    def test_heavy_item_triggers(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="d1", name="Secret Door", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        plate = Entity(
            id="plate", name="Floor Plate",
            properties={
                "puzzle_type": "pressure_plate",
                "required_weight": "heavy",
                "on_solve": {"unlock_door": "d1", "set_state": "solved"},
            },
        )
        room.add_entity(plate)

        heavy = Item(id="rock", name="Heavy Rock", portable=True,
                     properties={"weight": "heavy"})
        agent.add_item(heavy)

        result = execute_action(Drop(target="Heavy Rock"), agent, ws, tick=0)
        assert result.success
        assert not ws.doors["d1"].locked
        assert room.entities["plate"].state == EntityState.SOLVED

    def test_light_item_no_trigger(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="d1", name="Door", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        plate = Entity(
            id="plate", name="Floor Plate",
            properties={
                "puzzle_type": "pressure_plate",
                "required_weight": "heavy",
                "on_solve": {"unlock_door": "d1"},
            },
        )
        room.add_entity(plate)

        light = Item(id="feather", name="Feather", portable=True,
                     properties={"weight": "light"})
        agent.add_item(light)

        execute_action(Drop(target="Feather"), agent, ws, tick=0)
        assert ws.doors["d1"].locked  # still locked


# ---- Mechanism 3: Item Combination ----

class TestItemCombination:
    def test_combine_success(self):
        ws, _, agent = _make_world_with_agent()

        stick = Item(
            id="stick", name="Stick", portable=True,
            properties={
                "combine_with": "Cloth",
                "combine_result": {
                    "id": "torch", "name": "Torch",
                    "description": "A makeshift torch", "portable": True,
                },
                "combine_message": "You made a torch!",
            },
        )
        cloth = Item(id="cloth", name="Cloth", portable=True)
        agent.add_item(stick)
        agent.add_item(cloth)

        result = execute_action(Combine(item_a="Stick", item_b="Cloth"), agent, ws, tick=0)
        assert result.success
        assert agent.has_item("torch") is not None
        assert agent.has_item("stick") is None
        assert agent.has_item("cloth") is None

    def test_combine_reverse_order(self):
        ws, _, agent = _make_world_with_agent()

        stick = Item(
            id="stick", name="Stick", portable=True,
            properties={
                "combine_with": "Cloth",
                "combine_result": {"id": "torch", "name": "Torch", "portable": True},
            },
        )
        cloth = Item(id="cloth", name="Cloth", portable=True)
        agent.add_item(stick)
        agent.add_item(cloth)

        # Order reversed — should still work
        result = execute_action(Combine(item_a="Cloth", item_b="Stick"), agent, ws, tick=0)
        assert result.success
        assert agent.has_item("torch") is not None

    def test_combine_wrong_items(self):
        ws, _, agent = _make_world_with_agent()

        rock = Item(id="rock", name="Rock", portable=True)
        leaf = Item(id="leaf", name="Leaf", portable=True)
        agent.add_item(rock)
        agent.add_item(leaf)

        result = execute_action(Combine(item_a="Rock", item_b="Leaf"), agent, ws, tick=0)
        assert not result.success
        # Items should still be in inventory
        assert agent.has_item("rock") is not None
        assert agent.has_item("leaf") is not None

    def test_combine_missing_item(self):
        ws, _, agent = _make_world_with_agent()
        rock = Item(id="rock", name="Rock", portable=True)
        agent.add_item(rock)

        result = execute_action(Combine(item_a="Rock", item_b="Nothing"), agent, ws, tick=0)
        assert not result.success


# ---- Mechanism 4: Password Door ----

class TestPasswordDoor:
    def test_correct_password_via_talk(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="d1", name="Magic Door", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        guardian = Entity(
            id="guardian", name="Stone Guardian",
            properties={
                "puzzle_type": "password_door",
                "password": "open sesame",
                "case_sensitive": False,
                "on_solve": {"unlock_door": "d1", "set_state": "solved"},
            },
        )
        room.add_entity(guardian)

        result = execute_action(Talk(message="Open Sesame!"), agent, ws, tick=0)
        assert result.success
        assert not ws.doors["d1"].locked

    def test_wrong_password_via_talk(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="d1", name="Door", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        guardian = Entity(
            id="guardian", name="Guardian",
            properties={
                "puzzle_type": "password_door",
                "password": "open sesame",
                "on_solve": {"unlock_door": "d1"},
            },
        )
        room.add_entity(guardian)

        execute_action(Talk(message="hello world"), agent, ws, tick=0)
        assert ws.doors["d1"].locked  # still locked

    def test_password_via_interact(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="d1", name="Door", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        guardian = Entity(
            id="guardian", name="Stone Guardian",
            properties={
                "puzzle_type": "password_door",
                "password": "open sesame",
                "on_solve": {"unlock_door": "d1", "set_state": "solved"},
            },
        )
        room.add_entity(guardian)

        result = execute_action(Interact(target="Stone Guardian", payload="open sesame"), agent, ws, tick=0)
        assert result.success
        assert not ws.doors["d1"].locked


# ---- Mechanism 5: Sequential Levers ----

class TestSequentialLevers:
    def _setup_levers(self):
        ws, room, agent = _make_world_with_agent()
        r2 = Room(id="r2", name="Room 2")
        ws.add_room(r2)
        door = Door(id="gate", name="Gate", room_a="r1", room_b="r2", locked=True)
        ws.add_door(door, "north", "south")

        controller = Entity(
            id="ctrl", name="Mechanism", state=EntityState.HIDDEN,
            properties={
                "puzzle_type": "sequential",
                "sequence": ["lA", "lB", "lC"],
                "progress": [],
                "on_solve": {"unlock_door": "gate"},
                "on_reset": {"message": "Wrong! Levers reset."},
            },
        )
        room.add_entity(controller)

        for lid, lname in [("lA", "Lever A"), ("lB", "Lever B"), ("lC", "Lever C")]:
            lever = Entity(
                id=lid, name=lname,
                properties={"puzzle_type": "lever", "controller": "ctrl"},
            )
            room.add_entity(lever)

        return ws, room, agent

    def test_correct_order(self):
        ws, room, agent = self._setup_levers()

        execute_action(Interact(target="Lever A", payload="pull"), agent, ws, tick=0)
        execute_action(Interact(target="Lever B", payload="pull"), agent, ws, tick=1)
        result = execute_action(Interact(target="Lever C", payload="pull"), agent, ws, tick=2)

        assert result.success
        assert not ws.doors["gate"].locked
        assert room.entities["ctrl"].state == EntityState.SOLVED

    def test_wrong_order_resets(self):
        ws, room, agent = self._setup_levers()

        execute_action(Interact(target="Lever A", payload="pull"), agent, ws, tick=0)
        result = execute_action(Interact(target="Lever C", payload="pull"), agent, ws, tick=1)

        assert not result.success
        assert ws.doors["gate"].locked  # still locked
        assert room.entities["ctrl"].properties["progress"] == []
        # Levers should be reset
        assert room.entities["lA"].state == EntityState.DEFAULT

    def test_partial_progress(self):
        ws, room, agent = self._setup_levers()

        result = execute_action(Interact(target="Lever A", payload="pull"), agent, ws, tick=0)
        assert result.success
        assert room.entities["lA"].state == EntityState.ACTIVATED
        assert ws.doors["gate"].locked  # not yet solved

    def test_already_solved(self):
        ws, room, agent = self._setup_levers()
        room.entities["ctrl"].state = EntityState.SOLVED

        result = execute_action(Interact(target="Lever A", payload="pull"), agent, ws, tick=0)
        assert not result.success


# ---- Full Escape Room Integration ----

class TestEscapeRoomIntegration:
    def test_builds(self):
        world, agent_ids = build_escape_room()
        assert len(agent_ids) == 2
        assert len(world.state.rooms) == 5
        assert len(world.state.doors) == 5

    def test_combination_lock_path(self):
        """Solve puzzle box with code from the book."""
        world, _ = build_escape_room()
        alice = world.state.agents["alice"]

        # Enter code on puzzle box (need to be in workshop first)
        world.process_action(Move(direction="east"), alice)
        assert alice.room_id == "workshop"

        world.process_action(Interact(target="Puzzle Box", payload="1847"), alice)
        assert world.state.rooms["workshop"].entities["puzzle_box"].state == EntityState.SOLVED
        assert world.state.rooms["workshop"].entities["cloth_rag"].state == EntityState.DEFAULT

    def test_pressure_plate_path(self):
        """Use stone bust on pressure plate to open hidden panel."""
        world, _ = build_escape_room()
        alice = world.state.agents["alice"]

        # Go to workshop, pick up stone bust
        world.process_action(Move(direction="east"), alice)
        world.process_action(PickUp(target="Stone Bust"), alice)

        # Need brass key to get to vault
        world.process_action(Examine(target="Old Painting"), alice)
        world.process_action(PickUp(target="Brass Key"), alice)
        world.process_action(Use(item="Brass Key", target="Steel Door"), alice)
        world.process_action(Move(direction="east"), alice)
        assert alice.room_id == "vault"

        # Drop stone bust → pressure plate triggers
        world.process_action(Drop(target="Stone Bust"), alice)
        assert not world.state.doors["door_workshop_sanctum"].locked

    def test_password_path(self):
        """Say 'lumina' to open the enchanted archway."""
        world, _ = build_escape_room()
        alice = world.state.agents["alice"]

        # First need to reach sanctum via pressure plate
        world.process_action(Move(direction="east"), alice)
        world.process_action(PickUp(target="Stone Bust"), alice)
        world.process_action(Examine(target="Old Painting"), alice)
        world.process_action(PickUp(target="Brass Key"), alice)
        world.process_action(Use(item="Brass Key", target="Steel Door"), alice)
        world.process_action(Move(direction="east"), alice)
        world.process_action(Drop(target="Stone Bust"), alice)

        # Go back to workshop and through hidden panel
        world.process_action(Move(direction="west"), alice)
        world.process_action(Move(direction="south"), alice)
        assert alice.room_id == "sanctum"

        # Say the password
        world.process_action(Talk(message="lumina"), alice)
        assert not world.state.doors["door_sanctum_hallway"].locked

    def test_item_combination_path(self):
        """Combine stick + cloth into torch."""
        world, _ = build_escape_room()
        alice = world.state.agents["alice"]

        # Pick up stick from study
        world.process_action(PickUp(target="Wooden Stick"), alice)

        # Go to workshop, solve puzzle box, get cloth
        world.process_action(Move(direction="east"), alice)
        world.process_action(Interact(target="Puzzle Box", payload="1847"), alice)
        world.process_action(PickUp(target="Cloth Rag"), alice)

        # Combine
        world.process_action(Combine(item_a="Wooden Stick", item_b="Cloth Rag"), alice)
        assert alice.has_item("makeshift torch") is not None
        assert alice.has_item("wooden stick") is None
        assert alice.has_item("cloth rag") is None
