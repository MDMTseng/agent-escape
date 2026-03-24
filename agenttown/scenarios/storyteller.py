"""Story-driven world generation pipeline.

Architecture:
  1. Generate World Bible — setting, characters (traits/secrets/relationships), inciting incident
  2. Map character traits → puzzle types
  3. Generate clues (intentional + accidental) for each puzzle
  4. Build room structure with parallel puzzle clusters
  5. Validate solvability (clue reachability BFS)
  6. Return playable World + narrative metadata

The core principle: Characters create puzzles, not designers.
Every lock exists because someone had something to protect.
Every clue exists because humans are imperfect and leave traces.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

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


# ---------------------------------------------------------------------------
# Character trait → puzzle type mapping
# ---------------------------------------------------------------------------

TRAIT_PUZZLE_MAP: dict[str, list[str]] = {
    "paranoid": ["key_lock", "combination_lock", "sequential"],
    "artistic": ["combination_lock", "password_door", "examine_reveal"],
    "scholarly": ["combination_lock", "password_door"],
    "sentimental": ["combination_lock", "examine_reveal"],
    "meticulous": ["combination_lock", "sequential"],
    "secretive": ["examine_reveal", "key_lock"],
    "protective": ["key_lock", "pressure_plate"],
    "grieving": ["examine_reveal", "password_door"],
}

VALID_TRAITS = list(TRAIT_PUZZLE_MAP.keys())

# Theme-specific room/entity name banks (no AI needed for basic generation)
THEME_ROOMS: dict[str, list[dict[str, str]]] = {
    "gothic_manor": [
        {"name": "The Study", "desc": "A dusty study with bookshelves lining the walls and a faint draft from the east."},
        {"name": "The Workshop", "desc": "A cluttered workshop with tools scattered across a heavy oak table."},
        {"name": "The Vault", "desc": "A cold stone vault with iron reinforcements and dim torchlight."},
        {"name": "The Sanctum", "desc": "A mysterious chamber lit by pale blue flames in brass sconces."},
        {"name": "The Gallery", "desc": "Portraits of forgotten ancestors stare from gilded frames."},
        {"name": "The Cellar", "desc": "Damp stone walls drip with condensation. Barrels line the far wall."},
        {"name": "The Hallway", "desc": "A long corridor with a heavy iron door at the far end — the exit."},
    ],
    "sci_fi_lab": [
        {"name": "Command Deck", "desc": "Blinking consoles line the walls. A viewport shows nothing but stars."},
        {"name": "Research Bay", "desc": "Sealed containment units hum with energy. Data screens flash warnings."},
        {"name": "Engineering", "desc": "Pipes and conduits snake across the ceiling. The reactor hums below."},
        {"name": "Cryo Chamber", "desc": "Frost coats the pods. One is open — and empty."},
        {"name": "Server Room", "desc": "Racks of blinking servers stretch into darkness. The AI core pulses."},
        {"name": "Airlock", "desc": "The outer door is sealed. Red warning lights pulse rhythmically."},
        {"name": "Escape Pod Bay", "desc": "Three pods remain. Only one has power."},
    ],
    "ancient_tomb": [
        {"name": "Entrance Hall", "desc": "Hieroglyphs cover every surface. Torchlight flickers across carved faces."},
        {"name": "The Burial Chamber", "desc": "A massive sarcophagus dominates the room. Gold glints in the shadows."},
        {"name": "The Trial Room", "desc": "Four pedestals stand at compass points. The ceiling bears a painted sky."},
        {"name": "The Treasury", "desc": "Jewels and artifacts fill alcoves carved into the stone walls."},
        {"name": "The Passage of Shadows", "desc": "The corridor narrows. Strange sounds echo from ahead."},
        {"name": "The Inner Sanctum", "desc": "An altar of black stone sits beneath a shaft of light from above."},
        {"name": "The Exit Tunnel", "desc": "Daylight filters through cracks in the ancient stone. Freedom awaits."},
    ],
}

# Character name banks by theme
THEME_CHARACTERS: dict[str, list[dict[str, str]]] = {
    "gothic_manor": [
        {"name": "Lord Ashworth", "desc": "A paranoid industrialist who trusts no one", "trait": "paranoid"},
        {"name": "Eleanor", "desc": "An artistic spirit who hides messages in beauty", "trait": "artistic"},
        {"name": "Thomas", "desc": "A meticulous servant who recorded everything", "trait": "meticulous"},
        {"name": "Dr. Voss", "desc": "A scholarly chemist obsessed with his formula", "trait": "scholarly"},
        {"name": "Margaret", "desc": "A grieving widow preserving her late husband's memory", "trait": "grieving"},
    ],
    "sci_fi_lab": [
        {"name": "Dr. Chen", "desc": "A paranoid researcher who triple-locks everything", "trait": "paranoid"},
        {"name": "ARIA", "desc": "An AI entity that communicates through patterns", "trait": "artistic"},
        {"name": "Commander Hayes", "desc": "A protective officer guarding classified data", "trait": "protective"},
        {"name": "Dr. Okafor", "desc": "A meticulous scientist with obsessive documentation habits", "trait": "meticulous"},
        {"name": "Subject-7", "desc": "A secretive test subject with hidden memories", "trait": "secretive"},
    ],
    "ancient_tomb": [
        {"name": "Pharaoh Khet", "desc": "A protective ruler who guarded his treasures fiercely", "trait": "protective"},
        {"name": "Priestess Nefari", "desc": "An artistic priestess who encoded rituals in murals", "trait": "artistic"},
        {"name": "Scribe Imhotep", "desc": "A scholarly scribe who documented every passage", "trait": "scholarly"},
        {"name": "Queen Ankhet", "desc": "A sentimental queen who kept mementos of her children", "trait": "sentimental"},
        {"name": "Vizier Set", "desc": "A secretive advisor with hidden loyalties", "trait": "secretive"},
    ],
}

# Inciting incidents by theme
THEME_INCIDENTS: dict[str, list[str]] = {
    "gothic_manor": [
        "Lord Ashworth discovered his formula was being stolen and locked down the estate before vanishing.",
        "A mysterious letter summoned everyone to the manor. Now the doors are sealed and the clock is ticking.",
        "The manor's security system activated at midnight. No one knows who triggered it — or why.",
    ],
    "sci_fi_lab": [
        "An unauthorized experiment breached containment. The station locked down automatically.",
        "The AI detected an intruder and sealed all bulkheads. But there's no intruder on the sensors.",
        "A distress signal activated from inside the decommissioned wing. Someone — or something — is alive.",
    ],
    "ancient_tomb": [
        "The expedition accidentally triggered an ancient mechanism. The entrance sealed behind them.",
        "The tomb's guardians have awakened. The trials must be completed before the sands fill the chamber.",
        "A rival expedition is racing to reach the inner sanctum first. Time is running out.",
    ],
}


def _stable_id(seed: str) -> str:
    """Generate a short stable ID from a seed string."""
    return hashlib.md5(seed.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def puzzles_for_trait(trait: str) -> list[str]:
    """Return puzzle types that a character with this trait would create."""
    return list(TRAIT_PUZZLE_MAP.get(trait, ["combination_lock"]))


def generate_world_bible(
    theme: str,
    premise: str,
    num_characters: int = 3,
    difficulty: int = 3,
) -> dict[str, Any]:
    """Generate a world bible with characters, setting, and inciting incident.

    This is the deterministic (no-AI) version for testing and fast generation.
    """
    rng = random.Random(f"{theme}-{premise}-{difficulty}")

    # Normalize theme
    theme_key = theme.replace(" ", "_").replace("-", "_").lower()
    if theme_key not in THEME_ROOMS:
        theme_key = "gothic_manor"  # fallback

    # Pick characters
    char_pool = list(THEME_CHARACTERS[theme_key])
    rng.shuffle(char_pool)
    characters = char_pool[:num_characters]

    # Add relationships (each character references at least one other)
    for i, char in enumerate(characters):
        others = [c["name"] for j, c in enumerate(characters) if j != i]
        rels = []
        # Always relate to at least one other character
        target = rng.choice(others)
        rel_types = ["distrusts", "protects", "fears", "depends on", "secretly admires", "competes with"]
        rels.append({"target": target, "type": rng.choice(rel_types)})
        char["relationships"] = rels
        # Add secrets based on trait
        secrets_by_trait = {
            "paranoid": "Believes someone is stealing their work",
            "artistic": "Hides coded messages in their artwork",
            "scholarly": "Discovered a dangerous formula",
            "sentimental": "Keeps a locket with a forbidden photograph",
            "meticulous": "Accidentally recorded evidence of a crime",
            "secretive": "Maintains a hidden identity",
            "protective": "Guards a passage to something terrible",
            "grieving": "Preserves a shrine to someone who may not be dead",
        }
        char["secret"] = secrets_by_trait.get(char["trait"], "Has a hidden agenda")
        char["role"] = rng.choice(["builder", "inhabitant", "visitor", "guardian"])

    # Pick rooms based on difficulty
    room_pool = list(THEME_ROOMS[theme_key])
    num_rooms = min(3 + difficulty, len(room_pool))
    rooms = room_pool[:num_rooms]

    # Inciting incident
    incidents = THEME_INCIDENTS[theme_key]
    incident = rng.choice(incidents)

    return {
        "setting": {
            "theme": theme_key,
            "premise": premise,
            "rooms": rooms,
        },
        "characters": characters,
        "inciting_incident": incident,
    }


def generate_clues_for_puzzle(
    puzzle_type: str,
    solution: str,
    character: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate intentional + accidental clues for a puzzle.

    Returns list of clue dicts with: clue_type, text, entity_name, entity_desc.
    """
    name = character.get("name", "Unknown")
    trait = character.get("trait", "paranoid")
    clues: list[dict[str, Any]] = []

    if puzzle_type == "combination_lock":
        # Intentional: character deliberately wrote the code somewhere
        clues.append({
            "clue_type": "intentional",
            "text": f'A journal entry reads: "Remember the number — {solution}. Never forget."',
            "entity_name": f"{name}'s Journal",
            "entity_desc": f"A leather-bound journal belonging to {name}. The handwriting is meticulous.",
        })
        # Accidental: character used the code in other places
        clues.append({
            "clue_type": "accidental",
            "text": f'A receipt is dated {solution}. {name} circled this number on multiple documents.',
            "entity_name": "Scattered Documents",
            "entity_desc": f"Papers scattered across the desk. The number {solution} appears several times.",
        })

    elif puzzle_type == "key_lock":
        # Intentional: character hid the key behind something meaningful
        hiding_spots = {
            "paranoid": f"behind a false panel in {name}'s desk",
            "artistic": f"inside a hollow sculpture {name} created",
            "scholarly": f"tucked inside {name}'s favorite reference book",
            "sentimental": f"hidden in a music box that plays {name}'s wedding song",
            "secretive": f"concealed beneath a loose floorboard near {name}'s bed",
        }
        spot = hiding_spots.get(trait, f"hidden behind a painting of {name}")
        clues.append({
            "clue_type": "intentional",
            "text": f"The key is hidden {spot}.",
            "entity_name": f"{name}'s Hiding Spot",
            "entity_desc": f"Something about this area suggests {name} spent time here.",
        })
        # Accidental: wear marks show where character accessed it
        clues.append({
            "clue_type": "accidental",
            "text": f"Scratch marks on the wall suggest something was frequently moved here.",
            "entity_name": "Worn Marks",
            "entity_desc": "Subtle scratches and wear on the surface. Someone accessed this spot regularly.",
        })

    elif puzzle_type == "password_door":
        # Intentional: character embedded the password in a meaningful phrase
        clues.append({
            "clue_type": "intentional",
            "text": f'An inscription reads: "Speak the word \'{solution}\' and the way shall open."',
            "entity_name": f"Ancient Inscription",
            "entity_desc": f"Words carved into stone by {name}'s own hand.",
        })
        # Accidental: character muttered the word in a letter
        clues.append({
            "clue_type": "accidental",
            "text": f'A letter from {name} mentions: "I always whisper \'{solution}\' before entering."',
            "entity_name": f"{name}'s Letter",
            "entity_desc": f"A personal letter from {name}, never meant to be read by others.",
        })

    elif puzzle_type == "pressure_plate":
        clues.append({
            "clue_type": "intentional",
            "text": f"{name} designed the plate to respond to a heavy object.",
            "entity_name": "Blueprint Fragment",
            "entity_desc": f"A torn blueprint showing {name}'s design for a weight-triggered mechanism.",
        })
        clues.append({
            "clue_type": "accidental",
            "text": f"A heavy item sits nearby, as if {name} tested the mechanism here.",
            "entity_name": "Heavy Object",
            "entity_desc": "A surprisingly heavy item. It looks like it was placed here deliberately.",
        })

    elif puzzle_type == "examine_reveal":
        clues.append({
            "clue_type": "intentional",
            "text": f"{name} concealed something behind this object.",
            "entity_name": f"{name}'s Hidden Cache",
            "entity_desc": f"Something {name} wanted to keep safe. Examine carefully.",
        })
        clues.append({
            "clue_type": "accidental",
            "text": f"Fingerprints cover this area. {name} touched it frequently.",
            "entity_name": "Smudged Surface",
            "entity_desc": "Oil and fingerprints show heavy use. Someone checked this spot often.",
        })

    else:
        # Fallback
        clues.append({
            "clue_type": "intentional",
            "text": f"A note from {name} hints at the solution: {solution}",
            "entity_name": f"{name}'s Note",
            "entity_desc": f"A handwritten note from {name}.",
            "description": f"A handwritten note from {name}.",
        })

    return clues


# ---------------------------------------------------------------------------
# Room structure builder
# ---------------------------------------------------------------------------

def _build_rooms_and_puzzles(
    bible: dict[str, Any],
    difficulty: int,
    rng: random.Random,
) -> tuple[WorldState, list[dict[str, Any]]]:
    """Build rooms, doors, entities, and puzzles from the world bible.

    Returns (WorldState, escape_chain_steps).
    """
    ws = WorldState()
    room_seeds = bible["setting"]["rooms"]
    characters = bible["characters"]
    escape_chain: list[dict[str, Any]] = []

    # Create rooms
    room_ids: list[str] = []
    for i, rseed in enumerate(room_seeds):
        rid = _stable_id(f"room-{i}-{rseed['name']}")
        room = Room(id=rid, name=rseed["name"], description=rseed["desc"])
        ws.add_room(room)
        room_ids.append(rid)

    # Assign one puzzle per room (except first=start and last=exit)
    puzzle_rooms = room_ids[1:-1]  # Middle rooms get puzzles
    exit_room_id = room_ids[-1]
    start_room_id = room_ids[0]

    # Generate puzzle solutions
    solutions = {
        "combination_lock": str(rng.randint(1000, 9999)),
        "key_lock": "brass_key",
        "password_door": rng.choice(["lumina", "eternum", "veritas", "phoenix", "shadow", "aurora"]),
        "pressure_plate": "heavy_item",
        "examine_reveal": "hidden_item",
    }

    # Connect rooms with doors — linear chain + optional parallel paths
    directions = ["east", "south", "east", "south", "east", "south"]
    opposites = {"east": "west", "south": "north", "north": "south", "west": "east"}

    for i in range(len(room_ids) - 1):
        dir_idx = i % len(directions)
        direction = directions[dir_idx]
        opp = opposites[direction]

        # Determine if this door should be locked
        is_puzzle_door = room_ids[i + 1] in puzzle_rooms or room_ids[i + 1] == exit_room_id
        door_id = _stable_id(f"door-{i}")

        # Pick puzzle type based on character trait
        char_idx = i % len(characters)
        char = characters[char_idx]
        trait = char.get("trait", "paranoid")
        available_types = puzzles_for_trait(trait)
        puzzle_type = rng.choice(available_types)

        # Get solution for this puzzle type
        solution = solutions.get(puzzle_type, "1234")
        if puzzle_type == "combination_lock":
            # Make each combo unique
            solution = str(rng.randint(1000, 9999))

        # Create door
        door = Door(
            id=door_id,
            name=f"Door to {ws.rooms[room_ids[i + 1]].name}",
            room_a=room_ids[i],
            room_b=room_ids[i + 1],
            locked=is_puzzle_door,
            key_id=f"key_{door_id}" if puzzle_type == "key_lock" and is_puzzle_door else None,
        )
        ws.add_door(door, direction, opp)

        if not is_puzzle_door:
            continue

        # Create puzzle entity and clues
        source_room = ws.rooms[room_ids[i]]  # Clues go in the room BEFORE the lock

        clues = generate_clues_for_puzzle(puzzle_type, solution, char)

        # Place intentional clue entity in source room
        for clue in clues:
            if clue["clue_type"] == "intentional":
                clue_id = _stable_id(f"clue-{i}-{clue['entity_name']}")
                entity = Entity(
                    id=clue_id,
                    name=clue["entity_name"],
                    description=clue["entity_desc"],
                    properties={
                        "on_examine": {"message": clue["text"]},
                        "clue_for": door_id,
                    },
                )
                source_room.add_entity(entity)
                escape_chain.append({
                    "step": len(escape_chain) + 1,
                    "action": "examine",
                    "target": clue["entity_name"],
                    "room": source_room.name,
                    "room_id": source_room.id,
                    "description": f"Examine {clue['entity_name']} for clue",
                    "status": "pending",
                    "check_type": "examine",
                })
                break

        # Place accidental clue entity too
        for clue in clues:
            if clue["clue_type"] == "accidental":
                clue_id = _stable_id(f"aclue-{i}-{clue['entity_name']}")
                entity = Entity(
                    id=clue_id,
                    name=clue["entity_name"],
                    description=clue["entity_desc"],
                    properties={"on_examine": {"message": clue["text"]}},
                )
                source_room.add_entity(entity)
                break

        # Create the puzzle mechanism in the target room (or on the door)
        target_room = ws.rooms[room_ids[i + 1]]

        if puzzle_type == "combination_lock":
            lock_id = _stable_id(f"lock-{i}")
            lock_entity = Entity(
                id=lock_id,
                name=f"{char['name']}'s Lock",
                description=f"A combination lock designed by {char['name']}. It requires a code.",
                properties={
                    "puzzle_type": "combination_lock",
                    "combination": solution,
                    "on_solve": {
                        "set_state": "solved",
                        "unlock_door": door_id,
                        "message": f"The lock clicks open! {char['name']}'s security has been bypassed.",
                    },
                },
            )
            source_room.add_entity(lock_entity)
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "solve",
                "target": lock_entity.name,
                "entity_id": lock_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Enter code {solution} on {lock_entity.name}",
                "status": "pending",
                "check_type": "solve",
            })

        elif puzzle_type == "key_lock":
            # Key hidden behind an examinable entity
            hider_id = _stable_id(f"hider-{i}")
            key_id = f"key_{door_id}"
            hider = Entity(
                id=hider_id,
                name=f"{char['name']}'s Cache",
                description=f"Something {char['name']} valued deeply. Worth examining closely.",
                properties={
                    "on_examine": {
                        "reveal": [key_id],
                        "message": f"Behind it, you find a key that {char['name']} hid!",
                    },
                },
            )
            key_item = Item(
                id=key_id,
                name=f"{char['name']}'s Key",
                description=f"A key crafted by {char['name']}. It feels important.",
                state=EntityState.HIDDEN,
                portable=True,
            )
            source_room.add_entity(hider)
            source_room.add_entity(key_item)
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "reveal",
                "target": key_item.name,
                "entity_id": key_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Find {key_item.name} behind {hider.name}",
                "status": "pending",
                "check_type": "reveal",
            })
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "unlock",
                "target": door.name,
                "entity_id": door_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Use {key_item.name} on {door.name}",
                "status": "pending",
                "check_type": "door",
            })

        elif puzzle_type == "password_door":
            listener_id = _stable_id(f"listener-{i}")
            listener = Entity(
                id=listener_id,
                name=f"{char['name']}'s Ward",
                description=f"A mystical barrier created by {char['name']}. It seems to listen...",
                properties={
                    "puzzle_type": "password_door",
                    "password": solution,
                    "case_sensitive": False,
                    "on_solve": {
                        "set_state": "solved",
                        "unlock_door": door_id,
                        "message": f"The ward dissolves! {char['name']}'s enchantment is broken.",
                    },
                },
            )
            source_room.add_entity(listener)
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "solve",
                "target": listener.name,
                "entity_id": listener_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Say '{solution}' to {listener.name}",
                "status": "pending",
                "check_type": "solve",
            })

        elif puzzle_type == "pressure_plate":
            plate_id = _stable_id(f"plate-{i}")
            heavy_id = _stable_id(f"heavy-{i}")
            plate = Entity(
                id=plate_id,
                name=f"{char['name']}'s Mechanism",
                description=f"A weight-triggered mechanism designed by {char['name']}.",
                properties={
                    "puzzle_type": "pressure_plate",
                    "required_weight": "heavy",
                    "on_solve": {
                        "set_state": "solved",
                        "unlock_door": door_id,
                        "message": f"The mechanism activates! {char['name']}'s trap has been disarmed.",
                    },
                },
            )
            heavy = Item(
                id=heavy_id,
                name=f"Stone Weight",
                description=f"A surprisingly heavy stone object. {char['name']} used it for testing.",
                portable=True,
                properties={"weight": "heavy"},
            )
            source_room.add_entity(plate)
            source_room.add_entity(heavy)
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "solve",
                "target": plate.name,
                "entity_id": plate_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Drop Stone Weight on {plate.name}",
                "status": "pending",
                "check_type": "solve",
            })

        elif puzzle_type == "examine_reveal":
            examiner_id = _stable_id(f"examiner-{i}")
            hidden_id = _stable_id(f"hidden-{i}")
            mechanism_id = _stable_id(f"mech-{i}")
            examiner = Entity(
                id=examiner_id,
                name=f"{char['name']}'s Artifact",
                description=f"An object that {char['name']} treasured. Something is hidden within.",
                properties={
                    "on_examine": {
                        "reveal": [hidden_id],
                        "message": f"You discover something hidden inside {char['name']}'s artifact!",
                    },
                },
            )
            hidden_item = Item(
                id=hidden_id,
                name=f"Hidden Mechanism Part",
                description=f"A small device that fits into a slot near the door.",
                state=EntityState.HIDDEN,
                portable=True,
                usable_on=[f"{char['name']}'s Door Lock"],
            )
            mechanism = Entity(
                id=mechanism_id,
                name=f"{char['name']}'s Door Lock",
                description=f"A slot near the door. Something fits here.",
                properties={
                    "on_use": {
                        "set_state": "solved",
                        "unlock_door": door_id,
                        "consume_item": True,
                        "message": f"The mechanism clicks. {char['name']}'s final barrier falls.",
                    },
                },
            )
            source_room.add_entity(examiner)
            source_room.add_entity(hidden_item)
            source_room.add_entity(mechanism)
            escape_chain.append({
                "step": len(escape_chain) + 1,
                "action": "solve",
                "target": examiner.name,
                "entity_id": examiner_id,
                "room": source_room.name,
                "room_id": source_room.id,
                "description": f"Examine {examiner.name}, use hidden part on {mechanism.name}",
                "status": "pending",
                "check_type": "solve",
            })

    # --- Exit mechanism in final room ---
    exit_room = ws.rooms[exit_room_id]
    exit_id = _stable_id("exit-door")
    exit_door = Entity(
        id=exit_id,
        name="Exit Door",
        description="A heavy door. Beyond it — freedom.",
        properties={
            "on_use": {
                "finish": "You escaped! The story of this place will be told for generations.",
            },
        },
    )
    exit_room.add_entity(exit_door)
    escape_chain.append({
        "step": len(escape_chain) + 1,
        "action": "escape",
        "target": "Exit Door",
        "entity_id": exit_id,
        "room": exit_room.name,
        "room_id": exit_room_id,
        "description": "Use Exit Door to escape!",
        "status": "pending",
        "check_type": "finish",
    })

    # --- Create agents (the investigators) ---
    agent_a = AgentState(
        id="investigator_a",
        name="Alice",
        description="A sharp-eyed scholar who reads between the lines",
        room_id=start_room_id,
        goal="Examine everything. Read clues. Share discoveries with your partner. Find a way out.",
    )
    agent_b = AgentState(
        id="investigator_b",
        name="Bob",
        description="A bold explorer who acts first and thinks later",
        room_id=start_room_id,
        goal="Explore rooms. Try doors and mechanisms. Use items. Work with your partner to escape.",
    )
    ws.add_agent(agent_a)
    ws.add_agent(agent_b)

    return ws, escape_chain


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_clue_reachability(world: World) -> list[str]:
    """Verify that every puzzle's clue is reachable before the puzzle.

    Uses sequential unlock simulation: start from the beginning, unlock doors
    one at a time as their puzzles become reachable, and verify all doors
    can eventually be unlocked.

    Returns list of issues (empty = all good).
    """
    issues: list[str] = []
    state = world.state

    start_room = list(state.agents.values())[0].room_id
    unlocked_doors: set[str] = set()

    # Iteratively expand reachable area by solving accessible puzzles
    changed = True
    while changed:
        changed = False

        # BFS with currently unlocked doors
        visited: set[str] = set()
        queue = [start_room]
        while queue:
            rid = queue.pop(0)
            if rid in visited:
                continue
            visited.add(rid)
            room = state.rooms.get(rid)
            if not room:
                continue
            for d_id in room.doors.values():
                d = state.doors.get(d_id)
                if not d:
                    continue
                # Can traverse if door is unlocked or we've already solved it
                if d.locked and d.id not in unlocked_doors:
                    continue
                other = d.other_side(rid)
                if other and other not in visited:
                    queue.append(other)

        # Check which locked doors have their puzzle accessible in visited rooms
        for door in state.doors.values():
            if not door.locked or door.id in unlocked_doors:
                continue

            # Look for a puzzle entity that unlocks this door in reachable rooms
            for rid in visited:
                room = state.rooms[rid]
                for entity in room.entities.values():
                    on_solve = entity.properties.get("on_solve", {})
                    on_use = entity.properties.get("on_use", {})
                    clue_for = entity.properties.get("clue_for")

                    unlocks_this = False
                    if isinstance(on_solve, dict) and on_solve.get("unlock_door") == door.id:
                        unlocks_this = True
                    if isinstance(on_use, dict) and on_use.get("unlock_door") == door.id:
                        unlocks_this = True
                    # Key locks: check if the key is in a reachable room
                    if door.key_id:
                        for vrid in visited:
                            vroom = state.rooms[vrid]
                            if door.key_id in vroom.entities:
                                unlocks_this = True
                                break

                    if unlocks_this:
                        unlocked_doors.add(door.id)
                        changed = True
                        break
                if door.id in unlocked_doors:
                    break

    # After simulation, check for any doors still locked
    for door in state.doors.values():
        if door.locked and door.id not in unlocked_doors:
            issues.append(
                f"Door '{door.name}' (id={door.id}) has no reachable clue/puzzle from start"
            )

    return issues


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def build_story_world(
    theme: str,
    premise: str,
    difficulty: int = 3,
    num_characters: int = 3,
) -> tuple[World, list[str], dict[str, Any]]:
    """Full pipeline: story seed → playable World + metadata.

    Returns:
        (world, agent_ids, metadata)
        metadata contains: world_bible, escape_chain, characters
    """
    rng = random.Random(f"{theme}-{premise}-{difficulty}")

    # Step 1: Generate world bible
    bible = generate_world_bible(
        theme=theme,
        premise=premise,
        num_characters=num_characters,
        difficulty=difficulty,
    )

    # Step 2-4: Build rooms, puzzles, clues
    ws, escape_chain = _build_rooms_and_puzzles(bible, difficulty, rng)

    # Step 5: Create World and validate
    world = World(ws)

    issues = validate_clue_reachability(world)
    if issues:
        # Log but don't fail — we'll fix in future iterations
        import logging
        logger = logging.getLogger(__name__)
        for issue in issues:
            logger.warning(f"Solvability issue: {issue}")

    agent_ids = list(ws.agents.keys())

    metadata = {
        "world_bible": bible,
        "escape_chain": escape_chain,
        "theme": theme,
        "premise": premise,
        "difficulty": difficulty,
    }

    return world, agent_ids, metadata
