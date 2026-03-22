"""Escape Room scenario — a multi-room puzzle for agents to solve.

Puzzle Mechanisms Used:
  1. Key + Lock        — brass key unlocks the steel door
  2. Combination Lock  — puzzle box requires code "1847" (clue in the old book)
  3. Pressure Plate    — drop the stone bust on the floor plate to open the vault
  4. Item Combination  — combine stick + cloth into a makeshift torch
  5. Password Door     — say "lumina" near the enchanted archway
  6. Sequential Levers — pull red, green, blue levers in order to open exit

Room Layout:
  ┌───────────┐    ┌────────────┐    ┌────────────┐
  │  The Study │───►│ The Workshop│───►│ The Vault  │
  │  (start)   │east│            │east│            │
  └───────────┘    └─────┬──────┘    └────────────┘
                         │south
                   ┌─────▼──────┐    ┌────────────┐
                   │ The Sanctum │───►│ The Hallway│
                   │             │east│  (exit)    │
                   └─────────────┘    └────────────┘
"""

from __future__ import annotations

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


def build_escape_room() -> tuple[World, list[str]]:
    """Build the escape room world. Returns (world, list_of_agent_ids)."""

    # ===================================================================
    # ROOMS
    # ===================================================================

    start_room = Room(
        id="start",
        name="The Study",
        description=(
            "A dusty study with bookshelves lining the walls. "
            "A faint draft comes from the east. A large desk sits in the corner."
        ),
    )

    workshop = Room(
        id="workshop",
        name="The Workshop",
        description=(
            "A cluttered workshop with tools on the walls and a heavy workbench. "
            "The air smells of oil and old wood."
        ),
    )

    vault = Room(
        id="vault",
        name="The Vault",
        description=(
            "A cold stone chamber. The walls are bare except for three colored levers "
            "mounted on the far wall. A heavy gate blocks the eastern passage."
        ),
    )

    sanctum = Room(
        id="sanctum",
        name="The Sanctum",
        description=(
            "A mysterious round room lit by flickering blue flames. "
            "Strange runes are carved into the floor. An ornate archway "
            "stands on the east wall, shimmering faintly."
        ),
    )

    hallway = Room(
        id="hallway",
        name="The Hallway",
        description="A narrow hallway leading to a heavy iron door — the way out.",
    )

    # ===================================================================
    # THE STUDY — start room
    # ===================================================================

    # Crumpled Note — hints at the painting in the workshop
    note = Item(
        id="note",
        name="Crumpled Note",
        description="A crumpled piece of paper with writing on it.",
        portable=True,
        properties={
            "examine_text": (
                'The note reads: "The painting in the workshop hides a secret. '
                'Look behind it. And remember — the builder\'s year opens the box."'
            ),
        },
    )
    start_room.add_entity(note)

    # Old Book — contains the combination code (1847) and a password hint
    old_book = Entity(
        id="book",
        name="Old Book",
        description="A leather-bound book sitting on the desk.",
        properties={
            "examine_text": (
                'The book is titled "History of Ravenwood Manor, est. 1847". '
                'A passage is underlined: "The sanctum responds only to the word of light — '
                'LUMINA — spoken aloud."'
            ),
        },
    )
    start_room.add_entity(old_book)

    # Stick — half of a torch recipe
    stick = Item(
        id="stick",
        name="Wooden Stick",
        description="A sturdy wooden stick, about arm's length.",
        portable=True,
        properties={
            "examine_text": "Could be useful as a handle for something.",
            "combine_with": "Cloth Rag",
            "combine_result": {
                "id": "torch",
                "name": "Makeshift Torch",
                "description": "A stick wrapped in cloth, ready to be lit.",
                "portable": True,
                "usable_on": ["Brazier"],
                "properties": {
                    "examine_text": "A crude but functional torch. Needs a flame to light it.",
                },
            },
            "combine_message": "You wrap the cloth tightly around the stick. You now have a makeshift torch!",
        },
    )
    start_room.add_entity(stick)

    # ===================================================================
    # THE WORKSHOP — puzzle box + painting + pressure plate
    # ===================================================================

    # Painting — reveals the brass key when examined
    painting = Entity(
        id="painting",
        name="Old Painting",
        description="A large oil painting of a countryside scene, hanging slightly askew.",
        properties={
            "on_examine": {
                "reveal": ["brass_key"],
                "message": "Looking behind the painting, you find a small brass key taped to the back!",
            },
        },
    )
    workshop.add_entity(painting)

    # Brass Key — hidden behind painting, unlocks workshop→vault door
    brass_key = Item(
        id="brass_key",
        name="Brass Key",
        description="A small, ornate brass key.",
        state=EntityState.HIDDEN,
        portable=True,
    )
    workshop.add_entity(brass_key)

    # Puzzle Box — combination lock (code: 1847), reveals cloth rag
    puzzle_box = Entity(
        id="puzzle_box",
        name="Puzzle Box",
        description="A wooden box with a 4-digit combination lock on the front.",
        properties={
            "puzzle_type": "combination_lock",
            "combination": "1847",
            "examine_text": "The combination lock has four dials, each numbered 0-9. It's currently locked.",
            "on_solve": {
                "set_state": "solved",
                "reveal": ["cloth_rag"],
                "message": "The lock clicks open! Inside the box you find a cloth rag.",
            },
        },
    )
    workshop.add_entity(puzzle_box)

    # Cloth Rag — hidden in puzzle box, combine with stick
    cloth_rag = Item(
        id="cloth_rag",
        name="Cloth Rag",
        description="An oily cloth rag.",
        state=EntityState.HIDDEN,
        portable=True,
        properties={
            "examine_text": "The rag is soaked in some kind of flammable oil. Could burn well.",
        },
    )
    workshop.add_entity(cloth_rag)

    # Stone Bust — heavy item for the pressure plate
    stone_bust = Item(
        id="stone_bust",
        name="Stone Bust",
        description="A heavy stone bust of an old man with a stern expression.",
        portable=True,
        properties={
            "examine_text": "It's surprisingly heavy for its size. The base reads 'Founder'.",
            "weight": "heavy",
        },
    )
    workshop.add_entity(stone_bust)

    # ===================================================================
    # THE VAULT — levers puzzle + pressure plate + brazier
    # ===================================================================

    # Pressure Plate — drop a heavy item here to unlock the sanctum door
    pressure_plate = Entity(
        id="pressure_plate",
        name="Stone Floor Plate",
        description="A large stone tile on the floor that seems slightly raised.",
        properties={
            "puzzle_type": "pressure_plate",
            "required_weight": "heavy",
            "examine_text": "The plate has a carved symbol of a weight on it. It seems like it needs something heavy placed on it.",
            "on_solve": {
                "unlock_door": "door_workshop_sanctum",
                "set_state": "solved",
                "message": "A grinding sound echoes from the south wall!",
            },
        },
    )
    vault.add_entity(pressure_plate)

    # Lever Controller — hidden entity tracking lever sequence
    lever_controller = Entity(
        id="lever_controller",
        name="Lever Mechanism",
        state=EntityState.HIDDEN,
        properties={
            "puzzle_type": "sequential",
            "sequence": ["lever_red", "lever_green", "lever_blue"],
            "progress": [],
            "on_solve": {
                "unlock_door": "door_vault_hallway_secret",
                "message": "The gate rumbles and rises! A passage is revealed!",
            },
            "on_reset": {
                "message": "Wrong order! All levers snap back to their starting positions with a clang!",
            },
        },
    )
    vault.add_entity(lever_controller)

    # Three levers
    lever_red = Entity(
        id="lever_red",
        name="Red Lever",
        description="A lever with a red handle mounted on the wall.",
        properties={
            "puzzle_type": "lever",
            "controller": "lever_controller",
            "examine_text": "The lever has a faded label: '1st - the color of fire'.",
        },
    )
    vault.add_entity(lever_red)

    lever_green = Entity(
        id="lever_green",
        name="Green Lever",
        description="A lever with a green handle mounted on the wall.",
        properties={
            "puzzle_type": "lever",
            "controller": "lever_controller",
            "examine_text": "The lever has a faded label: '2nd - the color of the forest'.",
        },
    )
    vault.add_entity(lever_green)

    lever_blue = Entity(
        id="lever_blue",
        name="Blue Lever",
        description="A lever with a blue handle mounted on the wall.",
        properties={
            "puzzle_type": "lever",
            "controller": "lever_controller",
            "examine_text": "The lever has a faded label: '3rd - the color of the sky'.",
        },
    )
    vault.add_entity(lever_blue)

    # Clue scroll — hints at lever order
    lever_clue = Item(
        id="lever_clue",
        name="Faded Scroll",
        description="A partially legible scroll pinned to the wall.",
        portable=True,
        properties={
            "examine_text": (
                'The scroll reads: "Fire first, then forest, then sky. '
                'Pull them in nature\'s order and the gate shall rise."'
            ),
        },
    )
    vault.add_entity(lever_clue)

    # ===================================================================
    # THE SANCTUM — password door + brazier
    # ===================================================================

    # Enchanted Archway — password door (password: "lumina")
    archway = Entity(
        id="archway",
        name="Enchanted Archway",
        description="An ornate stone archway covered in glowing runes. It shimmers with magical energy.",
        properties={
            "puzzle_type": "password_door",
            "password": "lumina",
            "case_sensitive": False,
            "examine_text": (
                'The runes seem to spell fragments of words. '
                'One inscription reads: "Speak the word of light and the path shall open."'
            ),
            "on_solve": {
                "unlock_door": "door_sanctum_hallway",
                "set_state": "solved",
                "message": "The runes blaze with golden light! The archway shimmers and a passage opens!",
            },
        },
    )
    sanctum.add_entity(archway)

    # Brazier — use torch on it to reveal a hidden clue
    brazier = Entity(
        id="brazier",
        name="Brazier",
        description="A stone brazier filled with old coals. It hasn't been lit in years.",
        properties={
            "examine_text": "The coals look like they could still catch fire if given a flame.",
            "on_use": {
                "set_state": "activated",
                "consume_item": True,
                "reveal": ["wall_inscription"],
                "message": "The torch catches the coals! Flames leap up, illuminating hidden writing on the wall!",
            },
        },
    )
    sanctum.add_entity(brazier)

    # Hidden wall inscription — revealed by lighting the brazier
    wall_inscription = Entity(
        id="wall_inscription",
        name="Wall Inscription",
        description="Glowing text revealed by the brazier's flames.",
        state=EntityState.HIDDEN,
        properties={
            "examine_text": (
                'The inscription reads: "Three paths lead to freedom. '
                'The levers in the vault, the word of light here, '
                'or the iron door at the end of the hall."'
            ),
        },
    )
    sanctum.add_entity(wall_inscription)

    # ===================================================================
    # THE HALLWAY — exit
    # ===================================================================

    exit_door = Entity(
        id="exit_door",
        name="Iron Door",
        description="A heavy iron door with a simple push handle. This is the way out!",
        properties={
            "examine_text": "The door is heavy but has a push bar. Push it to escape!",
            "on_use": {
                "finish": "The iron door swings open with a groan. Daylight floods in. You've escaped Ravenwood Manor!",
                "message": "You push the heavy iron door open...",
            },
        },
    )
    hallway.add_entity(exit_door)

    # ===================================================================
    # DOORS
    # ===================================================================

    # Study → Workshop (open)
    door_study_workshop = Door(
        id="door_study_workshop",
        name="Wooden Door",
        description="A solid wooden door connecting the study to the workshop.",
        room_a="start",
        room_b="workshop",
        locked=False,
        state=EntityState.OPEN,
    )

    # Workshop → Vault (locked, needs brass key)
    door_workshop_vault = Door(
        id="door_workshop_vault",
        name="Steel Door",
        description="A sturdy steel door with a brass keyhole.",
        room_a="workshop",
        room_b="vault",
        locked=True,
        key_id="brass_key",
        state=EntityState.LOCKED,
    )

    # Workshop → Sanctum (locked, opened by pressure plate in vault)
    door_workshop_sanctum = Door(
        id="door_workshop_sanctum",
        name="Hidden Panel",
        description="A section of wall that slides open to reveal a passage.",
        room_a="workshop",
        room_b="sanctum",
        locked=True,
        state=EntityState.LOCKED,
    )

    # Sanctum → Hallway (locked, opened by password "lumina")
    door_sanctum_hallway = Door(
        id="door_sanctum_hallway",
        name="Archway Passage",
        description="A passage through the enchanted archway.",
        room_a="sanctum",
        room_b="hallway",
        locked=True,
        state=EntityState.LOCKED,
    )

    # Vault → Hallway (locked, opened by levers — secret exit)
    door_vault_hallway_secret = Door(
        id="door_vault_hallway_secret",
        name="Rising Gate",
        description="A heavy iron gate that can be raised by a mechanism.",
        room_a="vault",
        room_b="hallway",
        locked=True,
        state=EntityState.LOCKED,
    )

    # ===================================================================
    # BUILD WORLD
    # ===================================================================

    world_state = WorldState()

    for room in [start_room, workshop, vault, sanctum, hallway]:
        world_state.add_room(room)

    world_state.add_door(door_study_workshop, "east", "west")
    world_state.add_door(door_workshop_vault, "east", "west")
    world_state.add_door(door_workshop_sanctum, "south", "north")
    world_state.add_door(door_sanctum_hallway, "east", "west")
    world_state.add_door(door_vault_hallway_secret, "east", "west")

    # ===================================================================
    # AGENTS
    # ===================================================================

    alice = AgentState(
        id="alice",
        name="Alice",
        description="Explorer and puzzle solver. Focuses on reading clues and entering codes.",
        room_id="start",
        goal=(
            "Escape Ravenwood Manor! You are the CLUE READER. "
            "STEP 1: Examine Note and Book in Study, pick up Wooden Stick, move east. "
            "STEP 2: In Workshop, examine Painting (reveals key), solve Puzzle Box (code from book), pick up items. "
            "STEP 3: Use Brass Key on Steel Door to reach Vault. "
            "STEP 4: In Vault, read scroll for lever order, pull levers (Red→Green→Blue). "
            "STEP 5: Reach Hallway, use any item on Iron Door to escape. "
            "Act fast — do multiple actions per turn. Share clues with Bob."
        ),
    )

    bob = AgentState(
        id="bob",
        name="Bob",
        description="Action-taker. Focuses on using items, pulling levers, and solving physical puzzles.",
        room_id="start",
        goal=(
            "Escape Ravenwood Manor! You are the ACTION TAKER. "
            "STEP 1: In Study, pick up items and move east quickly. "
            "STEP 2: In Workshop, pick up Stone Bust, combine Stick+Cloth into Torch. "
            "STEP 3: After Alice opens Steel Door, go to Vault. Drop Stone Bust on Floor Plate. "
            "STEP 4: Go south to Sanctum, use Torch on Brazier, say LUMINA aloud. "
            "STEP 5: Reach Hallway through any path, use any item on Iron Door to escape. "
            "Act fast — do multiple actions per turn. Coordinate with Alice."
        ),
    )

    world_state.add_agent(alice)
    world_state.add_agent(bob)

    world = World(state=world_state)
    return world, ["alice", "bob"]
