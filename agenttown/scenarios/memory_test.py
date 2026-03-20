"""Memory Test scenario — a simple 2-room puzzle that requires remembering a clue.

The agent MUST:
  1. Read a note in Room A that says the code is "7392"
  2. Move to Room B
  3. Enter "7392" on the lock from memory (the note stays in Room A)

If memory works → agent remembers the code and solves it.
If memory fails → agent can't recall the code in Room B.

Room Layout:
  ┌─────────────┐         ┌─────────────┐
  │   Library    │──east──►│   Lab       │
  │              │         │             │
  │  - Code Note │         │  - Lock Box │
  │  - Hint Book │         │  - Agent B  │
  │  - Agent A   │         │             │
  └─────────────┘         └─────────────┘
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


def build_memory_test() -> tuple[World, list[str]]:
    """Build a minimal memory test scenario."""

    # --- Rooms ---
    library = Room(
        id="library",
        name="The Library",
        description=(
            "A quiet room with a single desk and a bookshelf. "
            "A note and a book sit on the desk."
        ),
    )

    lab = Room(
        id="lab",
        name="The Lab",
        description=(
            "A sterile white room with a locked box on a pedestal in the center. "
            "The box has a 4-digit combination lock."
        ),
    )

    # --- Library items ---

    # The critical clue — agent must remember this code
    code_note = Item(
        id="code_note",
        name="Code Note",
        description="A small card with numbers printed on it.",
        portable=True,
        properties={
            "examine_text": (
                'The card reads: "Lab access code: 7392". '
                "Memorize it — you'll need it next door."
            ),
        },
    )
    library.add_entity(code_note)

    # A secondary clue that requires combining two pieces of info
    hint_book = Entity(
        id="hint_book",
        name="Hint Book",
        description="A thin book with a blue cover.",
        properties={
            "examine_text": (
                'Page 1: "The lab box holds the exit key." '
                'Page 2: "Agent B knows a secret word. Ask them."'
            ),
        },
    )
    library.add_entity(hint_book)

    # --- Lab items ---

    # Combination lock — needs code 7392
    lock_box = Entity(
        id="lock_box",
        name="Lock Box",
        description="A metal box with a 4-digit combination lock.",
        properties={
            "puzzle_type": "combination_lock",
            "combination": "7392",
            "examine_text": "The lock has four dials. Enter the correct code to open it.",
            "on_solve": {
                "set_state": "solved",
                "reveal": ["exit_key"],
                "message": "The lock clicks open! Inside you find a golden key!",
            },
        },
    )
    lab.add_entity(lock_box)

    # Hidden key — revealed when lock box is solved
    exit_key = Item(
        id="exit_key",
        name="Golden Key",
        description="A shiny golden key.",
        state=EntityState.HIDDEN,
        portable=True,
        properties={
            "examine_text": "The key has 'EXIT' engraved on it.",
        },
    )
    lab.add_entity(exit_key)

    # Secret word entity — Agent B knows a secret
    secret_plaque = Entity(
        id="plaque",
        name="Wall Plaque",
        description="A plaque on the wall with faded text.",
        properties={
            "examine_text": 'The plaque reads: "Speak the word PHOENIX to complete the trial."',
        },
    )
    lab.add_entity(secret_plaque)

    # Password listener
    trial = Entity(
        id="trial",
        name="Trial Pedestal",
        description="A stone pedestal with a glowing rune. It seems to be listening.",
        properties={
            "puzzle_type": "password_door",
            "password": "phoenix",
            "case_sensitive": False,
            "examine_text": "The rune pulses gently. It seems to respond to spoken words.",
            "on_solve": {
                "set_state": "solved",
                "message": "The rune blazes with light! The trial is complete. You've proven your memory!",
                "finish": "Trial complete! The agents demonstrated perfect memory by recalling the code and the secret word.",
            },
        },
    )
    lab.add_entity(trial)

    # --- Door ---
    door = Door(
        id="door_lib_lab",
        name="Glass Door",
        description="A transparent glass door connecting the library and the lab.",
        room_a="library",
        room_b="lab",
        locked=False,
        state=EntityState.OPEN,
    )

    # --- World ---
    ws = WorldState()
    ws.add_room(library)
    ws.add_room(lab)
    ws.add_door(door, "east", "west")

    # Agent A starts in library (needs to find code, tell B)
    agent_a = AgentState(
        id="agent_a",
        name="Agent A",
        description="A careful reader who examines everything thoroughly.",
        room_id="library",
        goal=(
            "Find the code for the lock box in the lab. Examine the note and book in the library. "
            "Remember the code, then go to the lab and enter it on the Lock Box. "
            "Also find the secret word and say it to the Trial Pedestal. "
            "Share all clues with Agent B."
        ),
    )

    # Agent B starts in lab (needs code from A, knows about plaque)
    agent_b = AgentState(
        id="agent_b",
        name="Agent B",
        description="An observant explorer who pays attention to details.",
        room_id="lab",
        goal=(
            "Examine everything in the lab. Find any clues on the Wall Plaque. "
            "Wait for Agent A to share the code for the Lock Box. "
            "Cooperate with Agent A to solve all puzzles. "
            "Share what you discover with Agent A."
        ),
    )

    ws.add_agent(agent_a)
    ws.add_agent(agent_b)

    world = World(state=ws)
    return world, ["agent_a", "agent_b"]
