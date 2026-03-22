"""Reverse Escape Room Architect — builds multi-ending puzzle graphs from story inputs.

Architecture:
  Phase 1: Determine endings based on difficulty
  Phase 2: Build reverse chains from each ending back to entrance
  Phase 3: Mark entrance nodes
  Phase 4: Insert fork points connecting different ending routes
  Phase 5: Convert abstract graph to playable AgentTown world

The "reverse" approach means we start from the goal and work backwards,
ensuring every puzzle chain is solvable by construction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any

import anthropic

from agenttown.auth import get_api_key
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

PUZZLE_TYPES = ("lock", "cipher", "hidden", "mechanism", "riddle", "trap", "key")

ENDING_CONFIG: dict[str, dict[str, Any]] = {
    "good": {"color": "#22c55e", "depth_offset": 0},
    "bad": {"color": "#ef4444", "depth_offset": -1, "min_depth": 2},
    "secret": {"color": "#f59e0b", "depth_offset": 1},
    "true_": {"color": "#a855f7", "depth_offset": 1},
}

# Maps abstract puzzle types to the mechanics supported by the rules engine.
PUZZLE_TYPE_TO_MECHANIC: dict[str, str] = {
    "lock": "key_lock",
    "cipher": "combination_lock",
    "hidden": "examine_reveal",
    "mechanism": "pressure_plate",
    "riddle": "password_door",
    "key": "key_lock",
    "trap": "trap_trigger",
}

# Label templates keyed by puzzle type
PUZZLE_LABELS: dict[str, list[str]] = {
    "lock": ["Sealed Lock", "Iron Padlock", "Arcane Lock", "Bound Gate"],
    "cipher": ["Cipher Wheel", "Encoded Panel", "Rotating Dials", "Rune Matrix"],
    "hidden": ["Concealed Alcove", "Secret Panel", "Hidden Compartment", "False Wall"],
    "mechanism": ["Weighted Plate", "Gear Assembly", "Pressure Trigger", "Counterbalance"],
    "riddle": ["Speaking Stone", "Riddle Gate", "Whispering Arch", "Oracle Door"],
    "trap": ["Pitfall", "Poison Mist", "Collapsing Floor", "Blade Corridor"],
    "key": ["Ornate Key", "Crystal Shard", "Sigil Token", "Master Seal"],
}


@dataclass
class StoryInput:
    """Input specification for generating a reverse escape room."""

    builder: str        # Builder identity (e.g., "Mad Alchemist Ethos")
    goal: str           # What they protect (e.g., "Philosopher's Stone")
    background: str     # Scene description
    difficulty: int     # 2-5 (determines endings and depth)

    def seed_string(self) -> str:
        """Deterministic seed derived from the story input."""
        return f"{self.builder}|{self.goal}|{self.difficulty}"


@dataclass
class PuzzleNode:
    """A node in the puzzle DAG."""

    id: str
    type: str           # lock, cipher, hidden, mechanism, riddle, trap, key
    label: str
    desc: str
    depth: int
    is_goal: bool = False
    is_entrance: bool = False
    is_fork: bool = False
    ending_type: str = ""    # good, bad, secret, true_
    path_color: str = ""
    x: float = 0.0          # SVG X coordinate
    y: float = 0.0          # SVG Y coordinate


@dataclass
class PuzzleEdge:
    """A directed edge in the puzzle DAG (from deeper node to shallower)."""

    from_id: str        # deeper node (prerequisite)
    to_id: str          # shallower node (unlocked by from)
    ending_type: str = ""
    color: str = ""
    is_branch: bool = False


@dataclass
class EndingSpec:
    """Specification for one ending route."""

    ending_type: str    # good, bad, secret, true_
    color: str
    chain_depth: int
    description: str = ""


# ---------------------------------------------------------------------------
# Phase 1: Determine Endings
# ---------------------------------------------------------------------------

def _determine_endings(difficulty: int) -> list[EndingSpec]:
    """Based on difficulty, decide which endings exist and their chain depths."""
    endings: list[EndingSpec] = []

    # Good ending is always present
    endings.append(EndingSpec(
        ending_type="good",
        color=ENDING_CONFIG["good"]["color"],
        chain_depth=difficulty,
        description="The intended solution — clever and rewarding.",
    ))

    # Bad ending is always present
    bad_depth = max(2, difficulty - 1)
    endings.append(EndingSpec(
        ending_type="bad",
        color=ENDING_CONFIG["bad"]["color"],
        chain_depth=bad_depth,
        description="A shortcut trap — seems easy but leads to a bad outcome.",
    ))

    if difficulty >= 3:
        endings.append(EndingSpec(
            ending_type="secret",
            color=ENDING_CONFIG["secret"]["color"],
            chain_depth=difficulty + 1,
            description="A hidden path for the most observant explorers.",
        ))

    if difficulty >= 4:
        endings.append(EndingSpec(
            ending_type="true_",
            color=ENDING_CONFIG["true_"]["color"],
            chain_depth=difficulty + 1,
            description="The ultimate ending — requires mastering every system.",
        ))

    return endings


# ---------------------------------------------------------------------------
# Phase 2: Build Reverse Chains
# ---------------------------------------------------------------------------

def _build_reverse_chains(
    endings: list[EndingSpec],
    rng: random.Random,
) -> tuple[list[PuzzleNode], list[PuzzleEdge]]:
    """Build a shared-trunk graph with fork-based branching to multiple endings.

    Structure:
      Entrance → shared puzzles → FORK → ending A path → 🏆
                                    └→ ending B path → 💀
                                    (deeper fork for secret/true)
    """
    nodes: list[PuzzleNode] = []
    edges: list[PuzzleEdge] = []
    nc = 0  # node counter

    def _make_node(puzzle_type: str, depth: int, ending_type: str, color: str,
                   is_goal: bool = False, is_fork: bool = False, label_override: str = "") -> PuzzleNode:
        nonlocal nc
        nc += 1
        if label_override:
            label = label_override
        else:
            labels = PUZZLE_LABELS.get(puzzle_type, ["Puzzle"])
            label = rng.choice(labels)
        return PuzzleNode(
            id=f"n{nc}",
            type=puzzle_type, label=label, desc="",
            depth=depth, is_goal=is_goal, is_fork=is_fork,
            ending_type=ending_type, path_color=color,
        )

    def _pick_type(exclude_trap: bool = True) -> str:
        types = [t for t in PUZZLE_TYPES if not (exclude_trap and t == "trap")]
        return rng.choice(types)

    max_depth = max(e.chain_depth for e in endings)

    # --- Step 1: Create ending goal nodes (depth 0, rightmost) ---
    goal_nodes: dict[str, PuzzleNode] = {}
    for ending in endings:
        label = {"good": "Victory", "bad": "Defeat", "secret": "Hidden Truth", "true_": "True Revelation"}.get(ending.ending_type, "Ending")
        goal = _make_node("riddle", 0, ending.ending_type, ending.color, is_goal=True, label_override=label)
        goal_nodes[ending.ending_type] = goal
        nodes.append(goal)

    # --- Step 2: Build ending-specific tails (depth 1 to ~2, unique per ending) ---
    # Each ending gets 1-2 unique puzzle nodes before the fork
    ending_tails: dict[str, str] = {}  # ending_type → deepest tail node id
    for ending in endings:
        tail_length = min(2, ending.chain_depth - 1) if ending.chain_depth > 2 else 1
        prev_id = goal_nodes[ending.ending_type].id
        for d in range(1, tail_length + 1):
            pt = "trap" if ending.ending_type == "bad" and d == 1 else _pick_type()
            node = _make_node(pt, d, ending.ending_type, ending.color)
            nodes.append(node)
            edges.append(PuzzleEdge(from_id=node.id, to_id=prev_id, ending_type=ending.ending_type, color=ending.color))
            prev_id = node.id
        ending_tails[ending.ending_type] = prev_id

    # --- Step 3: Create fork points connecting ending tails to shared trunk ---
    # Primary fork: connects good and bad
    fork_depth = 3
    primary_fork = _make_node("riddle", fork_depth, "", "#8b949e", is_fork=True, label_override="Crossroads")
    nodes.append(primary_fork)
    # Connect fork → good tail and fork → bad tail
    edges.append(PuzzleEdge(from_id=primary_fork.id, to_id=ending_tails["good"], ending_type="good", color=goal_nodes["good"].path_color, is_branch=True))
    edges.append(PuzzleEdge(from_id=primary_fork.id, to_id=ending_tails["bad"], ending_type="bad", color=goal_nodes["bad"].path_color, is_branch=True))

    # Secondary fork for secret/true (if they exist)
    shared_trunk_start = primary_fork.id
    if "secret" in ending_tails:
        fork2_depth = fork_depth + 1
        fork2 = _make_node("riddle", fork2_depth, "", "#8b949e", is_fork=True, label_override="Hidden Path")
        nodes.append(fork2)
        # fork2 connects to primary fork (main path) and secret tail (hidden path)
        edges.append(PuzzleEdge(from_id=fork2.id, to_id=primary_fork.id, ending_type="good", color="#8b949e"))
        edges.append(PuzzleEdge(from_id=fork2.id, to_id=ending_tails["secret"], ending_type="secret", color=goal_nodes["secret"].path_color, is_branch=True))
        shared_trunk_start = fork2.id

    if "true_" in ending_tails:
        fork3_depth = fork_depth + 2
        fork3 = _make_node("riddle", fork3_depth, "", "#8b949e", is_fork=True, label_override="Deepest Secret")
        nodes.append(fork3)
        prev_trunk = shared_trunk_start
        edges.append(PuzzleEdge(from_id=fork3.id, to_id=prev_trunk, ending_type="good", color="#8b949e"))
        edges.append(PuzzleEdge(from_id=fork3.id, to_id=ending_tails["true_"], ending_type="true_", color=goal_nodes["true_"].path_color, is_branch=True))
        shared_trunk_start = fork3.id

    # --- Step 4: Build shared trunk (from last fork back to entrance) ---
    trunk_depth = max_depth
    prev_id = shared_trunk_start
    current_depth = max(n.depth for n in nodes) + 1

    trunk_length = max(2, trunk_depth - current_depth + 2)
    for i in range(trunk_length):
        d = current_depth + i
        pt = _pick_type()
        node = _make_node(pt, d, "shared", "#58a6ff")
        nodes.append(node)
        edges.append(PuzzleEdge(from_id=node.id, to_id=prev_id, ending_type="shared", color="#58a6ff"))
        prev_id = node.id

    return nodes, edges


# ---------------------------------------------------------------------------
# Phase 3: Mark Entrances
# ---------------------------------------------------------------------------

def _mark_entrances(nodes: list[PuzzleNode]) -> None:
    """Mark nodes near max depth as entrances (where agents start)."""
    if not nodes:
        return
    max_depth = max(n.depth for n in nodes)
    for node in nodes:
        if node.depth >= max_depth - 1 and not node.is_goal:
            node.is_entrance = True


# ---------------------------------------------------------------------------
# Phase 4: Insert Fork Points
# ---------------------------------------------------------------------------

def _insert_forks(
    nodes: list[PuzzleNode],
    edges: list[PuzzleEdge],
    rng: random.Random,
) -> None:
    """Forks are now built inline in _build_reverse_chains. This is a no-op."""
    # Forks are already created during chain building
    pass


def _LEGACY_insert_forks(
    nodes: list[PuzzleNode],
    edges: list[PuzzleEdge],
    rng: random.Random,
) -> None:
    """Legacy fork insertion — kept for reference."""
    if len({n.ending_type for n in nodes if not n.is_goal}) < 2:
        return

    by_depth: dict[int, list[PuzzleNode]] = {}
    for node in nodes:
        if node.is_goal or node.is_entrance:
            continue
        by_depth.setdefault(node.depth, []).append(node)

    all_depths = sorted(by_depth.keys())
    if len(all_depths) < 2:
        return

    mid_start = all_depths[len(all_depths) // 3]
    mid_end = all_depths[2 * len(all_depths) // 3]
    mid_depths = [d for d in all_depths if mid_start <= d <= mid_end]

    forks_created = 0
    max_forks = max(1, len(mid_depths) // 2)

    for depth in mid_depths:
        if forks_created >= max_forks:
            break

        candidates = by_depth.get(depth, [])
        if len(candidates) < 2:
            continue

        ending_groups: dict[str, list[PuzzleNode]] = {}
        for c in candidates:
            ending_groups.setdefault(c.ending_type, []).append(c)

        ending_types = list(ending_groups.keys())
        if len(ending_types) < 2:
            continue

        et_a, et_b = rng.sample(ending_types, 2)
        node_a = rng.choice(ending_groups[et_a])
        node_b = rng.choice(ending_groups[et_b])

        fork_id = f"fork_{forks_created}"
        fork_node = PuzzleNode(
            id=fork_id,
            type="riddle",
            label=f"Crossroads ({node_a.ending_type.rstrip('_')}/{node_b.ending_type.rstrip('_')})",
            desc="A decision point where paths diverge.",
            depth=depth,
            is_fork=True,
            ending_type="fork",
            path_color="#6b7280",  # neutral gray
        )
        nodes.append(fork_node)

        # Fork connects TO both nodes (fork is a predecessor of both)
        edges.append(PuzzleEdge(
            from_id=fork_id,
            to_id=node_a.id,
            ending_type=node_a.ending_type,
            color=node_a.path_color,
            is_branch=True,
        ))
        edges.append(PuzzleEdge(
            from_id=fork_id,
            to_id=node_b.id,
            ending_type=node_b.ending_type,
            color=node_b.path_color,
            is_branch=True,
        ))

        forks_created += 1


# ---------------------------------------------------------------------------
# Main Generation: reverse_generate
# ---------------------------------------------------------------------------

def reverse_generate(
    story_input: StoryInput,
) -> tuple[list[PuzzleNode], list[PuzzleEdge], list[EndingSpec]]:
    """Generate a puzzle DAG using the reverse-chain algorithm.

    Returns: (nodes, edges, endings)
    """
    # Semi-random seed: story input + current time for variation on regenerate
    import time
    seed_str = story_input.seed_string() + str(int(time.time() * 1000))
    seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()
    seed_int = int(seed_hash[:8], 16)
    rng = random.Random(seed_int)

    # Phase 1: Determine endings
    endings = _determine_endings(story_input.difficulty)
    logger.info(
        f"Architect: {len(endings)} endings for difficulty {story_input.difficulty}: "
        f"{[e.ending_type for e in endings]}"
    )

    # Phase 2: Build reverse chains
    nodes, edges = _build_reverse_chains(endings, rng)
    logger.info(f"Architect: built {len(nodes)} nodes, {len(edges)} edges")

    # Phase 3: Mark entrances
    _mark_entrances(nodes)
    entrance_count = sum(1 for n in nodes if n.is_entrance)
    logger.info(f"Architect: {entrance_count} entrance nodes")

    # Phase 4: Insert fork points
    _insert_forks(nodes, edges, rng)
    fork_count = sum(1 for n in nodes if n.is_fork)
    logger.info(f"Architect: {fork_count} fork points inserted")

    # Phase 5: Calculate layout coordinates
    _layout_nodes(nodes, edges)

    return nodes, edges, endings


def _layout_nodes(nodes: list[PuzzleNode], edges: list[PuzzleEdge]) -> None:
    """Assign x/y coordinates for SVG rendering. Right-to-left layout (goals on right)."""
    if not nodes:
        return

    W = 800  # canvas width
    max_depth = max(n.depth for n in nodes)

    # Group nodes by ending_type for Y spacing
    ending_groups: dict[str, list[PuzzleNode]] = {}
    for n in nodes:
        key = n.ending_type or "_fork"
        ending_groups.setdefault(key, []).append(n)

    # Assign Y base per ending route
    y_base = 100
    ending_y: dict[str, float] = {}
    for key in ending_groups:
        ending_y[key] = y_base
        y_base += 140

    # Assign coordinates
    depth_counters: dict[int, int] = {}
    for n in nodes:
        # X: goals on right, entrances on left
        n.x = W - 40 - n.depth * 120

        # Y: base from ending route + offset within depth
        base_y = ending_y.get(n.ending_type or "_fork", 200)
        depth_key = n.depth
        count = depth_counters.get(depth_key, 0)
        depth_counters[depth_key] = count + 1
        n.y = base_y + (count % 3) * 30 - 30

    # Fork nodes: position between their connected nodes
    for n in nodes:
        if n.is_fork:
            connected = []
            for e in edges:
                if e.from_id == n.id:
                    target = next((nd for nd in nodes if nd.id == e.to_id), None)
                    if target:
                        connected.append(target)
            if connected:
                n.x = min(c.x for c in connected) - 60
                n.y = sum(c.y for c in connected) / len(connected)


# ---------------------------------------------------------------------------
# AI Content Fill
# ---------------------------------------------------------------------------

FILL_CONTENT_PROMPT = """\
You are {builder}, a master architect who has built an elaborate escape room to protect \
the {goal}.

Background: {background}

You have constructed a puzzle network with multiple endings:
{endings_desc}

Below are the puzzle nodes in your creation. For each node, fill in:
1. "desc" — a 1-2 sentence atmospheric description of the puzzle/room
2. "clue_text" — what clue or hint the solver would find (if applicable)
3. "atmosphere" — a short evocative description of the room's feel
4. "builder_note" — a sentence from the builder's perspective explaining why they placed this puzzle here

Nodes:
{nodes_json}

Return a JSON object mapping node IDs to their filled content:
{{
  "node_id_here": {{
    "desc": "...",
    "clue_text": "...",
    "atmosphere": "...",
    "builder_note": "..."
  }}
}}

Stay in character as {builder}. Be creative and thematic. Return ONLY the JSON object.\
"""


def fill_content(
    story_input: StoryInput,
    nodes: list[PuzzleNode],
    edges: list[PuzzleEdge],
) -> list[PuzzleNode]:
    """Ask AI to fill creative content for each node.

    Returns the nodes list with updated descriptions.
    """
    client = anthropic.Anthropic(api_key=get_api_key())
    model = os.environ.get(
        "ANTHROPIC_MAP_MODEL",
        os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5"),
    )

    endings_in_graph = {n.ending_type for n in nodes if n.is_goal}
    endings_desc = "\n".join(
        f"  - {et}: color={n.path_color}, depth={n.depth}"
        for n in nodes
        if n.is_goal
        for et in [n.ending_type]
    )

    nodes_for_prompt = [
        {
            "id": n.id,
            "type": n.type,
            "label": n.label,
            "depth": n.depth,
            "ending_type": n.ending_type,
            "is_goal": n.is_goal,
            "is_entrance": n.is_entrance,
            "is_fork": n.is_fork,
        }
        for n in nodes
    ]

    prompt = FILL_CONTENT_PROMPT.format(
        builder=story_input.builder,
        goal=story_input.goal,
        background=story_input.background,
        endings_desc=endings_desc,
        nodes_json=json.dumps(nodes_for_prompt, indent=2),
    )

    logger.info(f"Filling content for {len(nodes)} nodes via AI...")

    response = client.messages.create(
        model=model,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip() if response.content else "{}"

    # Extract JSON from response
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start != end:
            inner = text[start + 3: end]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()

    try:
        content_map = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        brace_start = text.find("{")
        if brace_start >= 0:
            try:
                content_map = json.loads(text[brace_start:])
            except json.JSONDecodeError:
                logger.error(f"Failed to parse AI content JSON: {text[:200]}")
                content_map = {}
        else:
            content_map = {}

    # Apply content to nodes
    for node in nodes:
        if node.id in content_map:
            data = content_map[node.id]
            if isinstance(data, dict):
                node.desc = data.get("desc", node.desc) or node.desc
                # Store extra content in a way we can use during world building
                if not node.desc and "atmosphere" in data:
                    node.desc = data["atmosphere"]

    filled_count = sum(1 for n in nodes if n.desc)
    logger.info(f"Filled content for {filled_count}/{len(nodes)} nodes")
    return nodes


# ---------------------------------------------------------------------------
# Escape Chain Extraction
# ---------------------------------------------------------------------------

def extract_escape_chains(
    nodes: list[PuzzleNode],
    edges: list[PuzzleEdge],
) -> dict[str, list[dict[str, Any]]]:
    """For each ending, trace the path from entrance to goal.

    Returns a dict mapping ending_type to an ordered list of steps.
    """
    node_map = {n.id: n for n in nodes}

    # Build adjacency: from_id -> to_id (deeper to shallower)
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.from_id, []).append(edge.to_id)

    # Find goal nodes and entrance nodes per ending type
    goals_by_ending: dict[str, list[str]] = {}
    entrances_by_ending: dict[str, list[str]] = {}

    for node in nodes:
        if node.is_goal:
            goals_by_ending.setdefault(node.ending_type, []).append(node.id)
        if node.is_entrance:
            entrances_by_ending.setdefault(node.ending_type, []).append(node.id)

    chains: dict[str, list[dict[str, Any]]] = {}

    for ending_type, goal_ids in goals_by_ending.items():
        entrance_ids = entrances_by_ending.get(ending_type, [])
        if not entrance_ids:
            # Try to find any entrance that can reach this goal
            entrance_ids = [n.id for n in nodes if n.is_entrance]

        if not entrance_ids or not goal_ids:
            continue

        # BFS/DFS from each entrance to find path to goal
        goal_id = goal_ids[0]

        # Reverse adjacency for path finding (we want entrance -> goal)
        # Our edges go from deeper (entrance side) to shallower (goal side)
        # So adjacency already goes entrance-direction -> goal-direction
        best_path: list[str] | None = None

        for entrance_id in entrance_ids:
            path = _find_path(entrance_id, goal_id, adjacency)
            if path is not None:
                if best_path is None or len(path) < len(best_path):
                    best_path = path

        if best_path is None:
            # Fallback: collect all nodes of this ending sorted by depth desc
            ending_nodes = sorted(
                [n for n in nodes if n.ending_type == ending_type],
                key=lambda n: -n.depth,
            )
            best_path = [n.id for n in ending_nodes]

        chain_steps: list[dict[str, Any]] = []
        for step_num, nid in enumerate(best_path, 1):
            node = node_map[nid]
            chain_steps.append({
                "step": step_num,
                "node_id": node.id,
                "type": node.type,
                "label": node.label,
                "depth": node.depth,
                "is_entrance": node.is_entrance,
                "is_goal": node.is_goal,
                "description": node.desc or node.label,
            })

        chains[ending_type] = chain_steps

    return chains


def _find_path(
    start: str,
    end: str,
    adjacency: dict[str, list[str]],
) -> list[str] | None:
    """BFS to find a path from start to end in the adjacency graph."""
    if start == end:
        return [start]

    visited: set[str] = {start}
    queue: list[list[str]] = [[start]]

    while queue:
        path = queue.pop(0)
        current = path[-1]

        for neighbor in adjacency.get(current, []):
            if neighbor == end:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    return None


# ---------------------------------------------------------------------------
# World Builder: Convert Graph to Playable World
# ---------------------------------------------------------------------------

# Direction pairs for connecting rooms
_DIRECTION_PAIRS = [
    ("east", "west"),
    ("north", "south"),
    ("northeast", "southwest"),
    ("northwest", "southeast"),
]


def build_world_from_graph(
    story_input: StoryInput,
    nodes: list[PuzzleNode],
    edges: list[PuzzleEdge],
    endings: list[EndingSpec],
) -> tuple[World, list[str], dict[str, list[dict[str, Any]]]]:
    """Convert the abstract puzzle graph into a playable AgentTown world.

    Each node becomes a Room with puzzle entities.
    Each edge becomes a locked Door between rooms.

    Returns: (world, agent_ids, escape_chains)
    """
    ws = WorldState()
    node_map = {n.id: n for n in nodes}

    # Deterministic RNG for world building details
    seed_hash = hashlib.sha256(story_input.seed_string().encode()).hexdigest()
    rng = random.Random(int(seed_hash[:8], 16) + 42)

    # --- Create rooms for each node ---
    room_map: dict[str, str] = {}  # node_id -> room_id

    for node in nodes:
        room_id = f"room_{node.id}"
        room_name = _room_name_for_node(node, story_input)
        room_desc = node.desc or _default_room_desc(node, story_input)

        room = Room(
            id=room_id,
            name=room_name,
            description=room_desc,
        )

        # Add goal entities to goal rooms
        if node.is_goal:
            _add_goal_entities(room, node, story_input)

        ws.add_room(room)
        room_map[node.id] = room_id

    # --- Create doors for each edge ---
    direction_counter: dict[str, int] = {}  # room_id -> count of doors used

    for edge_idx, edge in enumerate(edges):
        from_node = node_map.get(edge.from_id)
        to_node = node_map.get(edge.to_id)
        if from_node is None or to_node is None:
            continue

        from_room_id = room_map[edge.from_id]
        to_room_id = room_map[edge.to_id]
        door_id = f"door_{edge_idx}"

        # Pick directions that haven't been used
        dir_idx_a = direction_counter.get(from_room_id, 0)
        dir_idx_b = direction_counter.get(to_room_id, 0)
        dir_pair_idx = max(dir_idx_a, dir_idx_b) % len(_DIRECTION_PAIRS)
        dir_from, dir_to = _DIRECTION_PAIRS[dir_pair_idx]

        direction_counter[from_room_id] = dir_idx_a + 1
        direction_counter[to_room_id] = dir_idx_b + 1

        # Create the puzzle mechanics for this edge
        mechanic = PUZZLE_TYPE_TO_MECHANIC.get(from_node.type, "combination_lock")

        if to_node.is_goal and from_node.type == "trap":
            # Trap rooms have an open door to the bad ending
            _create_trap_room(ws, from_room_id, to_room_id, door_id,
                              from_node, to_node, dir_from, dir_to, rng)
        elif mechanic == "key_lock":
            _create_key_lock(ws, from_room_id, to_room_id, door_id,
                             from_node, to_node, dir_from, dir_to, edge_idx, rng)
        elif mechanic == "combination_lock":
            _create_combination_lock(ws, from_room_id, to_room_id, door_id,
                                     from_node, to_node, dir_from, dir_to, edge_idx, rng)
        elif mechanic == "examine_reveal":
            _create_examine_reveal(ws, from_room_id, to_room_id, door_id,
                                   from_node, to_node, dir_from, dir_to, edge_idx, rng)
        elif mechanic == "pressure_plate":
            _create_pressure_plate(ws, from_room_id, to_room_id, door_id,
                                   from_node, to_node, dir_from, dir_to, edge_idx, rng)
        elif mechanic == "password_door":
            _create_password_door(ws, from_room_id, to_room_id, door_id,
                                  from_node, to_node, dir_from, dir_to, edge_idx, rng)
        else:
            # Default: combination lock
            _create_combination_lock(ws, from_room_id, to_room_id, door_id,
                                     from_node, to_node, dir_from, dir_to, edge_idx, rng)

    # --- Extract escape chains ---
    escape_chains = extract_escape_chains(nodes, edges)

    # --- Create agents ---
    entrance_nodes = [n for n in nodes if n.is_entrance]
    if not entrance_nodes:
        # Fallback: use the deepest non-goal node
        non_goals = [n for n in nodes if not n.is_goal]
        if non_goals:
            entrance_nodes = [max(non_goals, key=lambda n: n.depth)]
        else:
            entrance_nodes = [nodes[0]]

    start_room_id = room_map[entrance_nodes[0].id]

    # Build goal description for agents
    ending_descs = ", ".join(
        f"{e.ending_type.rstrip('_')} ending (depth {e.chain_depth})"
        for e in endings
    )
    chain_summary = ""
    for et, chain in escape_chains.items():
        steps_text = " -> ".join(s["label"] for s in chain)
        chain_summary += f"\n  {et}: {steps_text}"

    agent_ids = ["agent_a", "agent_b"]

    ws.add_agent(AgentState(
        id="agent_a",
        name="Alice",
        description=f"Explorer in {story_input.builder}'s domain. Reads clues and solves puzzles.",
        room_id=start_room_id,
        goal=(
            f"Escape {story_input.builder}'s domain and find the {story_input.goal}! "
            f"Possible endings: {ending_descs}. "
            f"Explore carefully, examine everything, share clues with Bob."
        ),
    ))
    ws.add_agent(AgentState(
        id="agent_b",
        name="Bob",
        description=f"Action-taker in {story_input.builder}'s domain. Carries items and operates mechanisms.",
        room_id=start_room_id,
        goal=(
            f"Escape {story_input.builder}'s domain and find the {story_input.goal}! "
            f"Possible endings: {ending_descs}. "
            f"Carry heavy items, use keys, pull levers. Coordinate with Alice."
        ),
    ))

    world = World(state=ws)
    logger.info(
        f"Architect world built: {len(ws.rooms)} rooms, "
        f"{sum(len(r.entities) for r in ws.rooms.values())} entities, "
        f"{len(ws.doors)} doors"
    )
    return world, agent_ids, escape_chains


# ---------------------------------------------------------------------------
# Room / Entity Creation Helpers
# ---------------------------------------------------------------------------

def _room_name_for_node(node: PuzzleNode, story: StoryInput) -> str:
    """Generate a thematic room name based on the node."""
    if node.is_goal:
        return f"{story.goal} Chamber ({node.ending_type.rstrip('_')})"
    if node.is_fork:
        return "The Crossroads"
    if node.is_entrance:
        return f"Entrance Hall ({node.ending_type.rstrip('_')})"

    type_names = {
        "lock": "Locked Chamber",
        "cipher": "Cipher Room",
        "hidden": "Secret Alcove",
        "mechanism": "Mechanism Hall",
        "riddle": "Riddle Chamber",
        "trap": "Danger Room",
        "key": "Key Vault",
    }
    base = type_names.get(node.type, "Chamber")
    return f"{base} (d{node.depth})"


def _default_room_desc(node: PuzzleNode, story: StoryInput) -> str:
    """Generate a default room description if AI content was not filled."""
    if node.is_goal:
        return (
            f"The heart of {story.builder}'s domain. "
            f"The {story.goal} rests here, protected by the final challenge."
        )
    if node.is_fork:
        return "A junction where multiple paths converge. The air crackles with possibility."
    if node.is_entrance:
        return f"The entry point into {story.builder}'s domain. {story.background}"

    return f"A chamber built by {story.builder}. A {node.type} puzzle guards the way forward."


def _add_goal_entities(room: Room, node: PuzzleNode, story: StoryInput) -> None:
    """Add finish trigger entities to a goal room."""
    if node.ending_type == "bad":
        # Bad ending: a trap finish
        finish_entity = Entity(
            id=f"finish_{node.ending_type}",
            name=f"{story.goal} (Cursed)",
            description=f"A tainted version of the {story.goal}. Something is wrong...",
            properties={
                "examine_text": f"This is a decoy! {story.builder} left this trap.",
                "on_use": {
                    "finish": (
                        f"You grabbed the cursed {story.goal}! "
                        f"{story.builder}'s trap springs shut. Bad ending."
                    ),
                    "message": "The room shakes as the trap activates...",
                },
            },
        )
    elif node.ending_type == "secret":
        finish_entity = Entity(
            id=f"finish_{node.ending_type}",
            name=f"True {story.goal}",
            description=f"The genuine {story.goal}, hidden by {story.builder}.",
            properties={
                "examine_text": f"This is the real {story.goal}! {story.builder} hid it well.",
                "on_use": {
                    "finish": (
                        f"You found the secret {story.goal}! "
                        f"{story.builder} would be impressed. Secret ending!"
                    ),
                    "message": "A hidden passage opens as you claim your prize!",
                },
            },
        )
    elif node.ending_type == "true_":
        finish_entity = Entity(
            id=f"finish_{node.ending_type}",
            name=f"{story.goal} (Perfected)",
            description=f"The perfected form of the {story.goal}, the ultimate prize.",
            properties={
                "examine_text": (
                    f"The perfected {story.goal}. Only a true master could reach this."
                ),
                "on_use": {
                    "finish": (
                        f"You obtained the perfected {story.goal}! "
                        f"Even {story.builder} acknowledges your mastery. True ending!"
                    ),
                    "message": "Reality shifts as the ultimate prize is claimed!",
                },
            },
        )
    else:
        # Good ending
        finish_entity = Entity(
            id=f"finish_{node.ending_type}",
            name=story.goal,
            description=f"The {story.goal}, finally within reach!",
            properties={
                "examine_text": f"The {story.goal} gleams before you. Take it to escape!",
                "on_use": {
                    "finish": (
                        f"You claimed the {story.goal}! "
                        f"{story.builder}'s challenge is overcome. Victory!"
                    ),
                    "message": "Light floods the chamber as the final barrier falls!",
                },
            },
        )

    room.add_entity(finish_entity)


def _create_key_lock(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    edge_idx: int,
    rng: random.Random,
) -> None:
    """Create a key-lock puzzle: key in from_room, locked door to to_room."""
    key_id = f"key_{edge_idx}"

    # Hider entity in from_room — examining it reveals the key
    hider = Entity(
        id=f"hider_{edge_idx}",
        name=f"Suspicious {rng.choice(['Statue', 'Shelf', 'Painting', 'Chest'])}",
        description=f"Something about this seems off. Part of {from_node.label}.",
        properties={
            "examine_text": "It seems like something could be hidden here...",
            "on_examine": {
                "reveal": [key_id],
                "message": "You find a key hidden behind it!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(hider)

    key_item = Item(
        id=key_id,
        name=f"{from_node.label} Key",
        description=f"A key found near the {from_node.label}.",
        state=EntityState.HIDDEN,
        portable=True,
    )
    ws.rooms[from_room_id].add_entity(key_item)

    door = Door(
        id=door_id,
        name=f"Locked Gate ({from_node.label})",
        description=f"A locked gate leading toward the {to_node.label}.",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=True,
        key_id=key_id,
        state=EntityState.LOCKED,
    )
    ws.add_door(door, dir_from, dir_to)


def _create_combination_lock(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    edge_idx: int,
    rng: random.Random,
) -> None:
    """Create a combination lock puzzle: clue in from_room, lock on door."""
    code = str(rng.randint(1000, 9999))

    # Clue item in from_room
    clue = Item(
        id=f"clue_{edge_idx}",
        name=f"Encoded Note ({from_node.label})",
        description=f"A note with encoded information near the {from_node.label}.",
        portable=True,
        properties={
            "examine_text": f"The numbers read: {code}",
        },
    )
    ws.rooms[from_room_id].add_entity(clue)

    # Lock entity in from_room
    lock = Entity(
        id=f"lock_{edge_idx}",
        name=f"Cipher Lock ({from_node.label})",
        description=f"A combination lock mechanism. Part of the {from_node.label}.",
        properties={
            "puzzle_type": "combination_lock",
            "combination": code,
            "examine_text": "A lock with four rotating dials. Enter the correct code.",
            "on_solve": {
                "set_state": "solved",
                "unlock_door": door_id,
                "message": f"The code {code} works! The lock clicks open!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(lock)

    door = Door(
        id=door_id,
        name=f"Sealed Door ({from_node.label})",
        description=f"A sealed door leading toward the {to_node.label}.",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=True,
        state=EntityState.LOCKED,
    )
    ws.add_door(door, dir_from, dir_to)


def _create_examine_reveal(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    edge_idx: int,
    rng: random.Random,
) -> None:
    """Create an examine-reveal puzzle: examine object to find item, use on mechanism."""
    revealed_id = f"revealed_{edge_idx}"
    lock_entity_id = f"mechanism_{edge_idx}"

    examiner = Entity(
        id=f"examiner_{edge_idx}",
        name=f"Hidden {rng.choice(['Mirror', 'Tapestry', 'Panel', 'Alcove'])}",
        description=f"Something worth examining closely. Part of {from_node.label}.",
        properties={
            "examine_text": "There seems to be something concealed here...",
            "on_examine": {
                "reveal": [revealed_id],
                "message": "You discover something hidden!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(examiner)

    revealed = Item(
        id=revealed_id,
        name=f"Secret Token ({from_node.label})",
        description=f"A token found hidden near the {from_node.label}.",
        state=EntityState.HIDDEN,
        portable=True,
        usable_on=[lock_entity_id],
        properties={
            "examine_text": "This looks like it fits into a mechanism nearby.",
        },
    )
    ws.rooms[from_room_id].add_entity(revealed)

    lock_entity = Entity(
        id=lock_entity_id,
        name=f"Token Slot ({from_node.label})",
        description="A mechanism with a slot that matches something.",
        properties={
            "on_use": {
                "unlock_door": door_id,
                "set_state": "solved",
                "consume_item": True,
                "message": "The token fits! The mechanism activates and a door opens!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(lock_entity)

    door = Door(
        id=door_id,
        name=f"Hidden Passage ({from_node.label})",
        description=f"A concealed passage leading toward the {to_node.label}.",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=True,
        state=EntityState.LOCKED,
    )
    ws.add_door(door, dir_from, dir_to)


def _create_pressure_plate(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    edge_idx: int,
    rng: random.Random,
) -> None:
    """Create a pressure plate puzzle: heavy item + plate."""
    heavy_name = rng.choice([
        "Stone Idol", "Iron Weight", "Bronze Sphere", "Lead Block", "Marble Bust",
    ])

    heavy = Item(
        id=f"heavy_{edge_idx}",
        name=f"{heavy_name} ({from_node.label})",
        description=f"A very heavy {heavy_name.lower()}.",
        portable=True,
        properties={"weight": "heavy"},
    )
    ws.rooms[from_room_id].add_entity(heavy)

    plate = Entity(
        id=f"plate_{edge_idx}",
        name=f"Floor Plate ({from_node.label})",
        description=f"A sunken stone tile. Part of the {from_node.label} mechanism.",
        properties={
            "puzzle_type": "pressure_plate",
            "required_weight": "heavy",
            "examine_text": "The plate has a weight symbol carved into it.",
            "on_solve": {
                "set_state": "solved",
                "unlock_door": door_id,
                "message": "The plate sinks! A grinding sound — a door opens!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(plate)

    door = Door(
        id=door_id,
        name=f"Weighted Door ({from_node.label})",
        description=f"A heavy door leading toward the {to_node.label}.",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=True,
        state=EntityState.LOCKED,
    )
    ws.add_door(door, dir_from, dir_to)


def _create_password_door(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    edge_idx: int,
    rng: random.Random,
) -> None:
    """Create a password door puzzle: clue with password, speaking stone."""
    passwords = [
        "arcanum", "verithas", "solaris", "nocturn", "luminos",
        "eternum", "shadow", "radiant", "whisper", "echoval",
    ]
    password = rng.choice(passwords)

    # Clue with password
    clue = Item(
        id=f"pwd_clue_{edge_idx}",
        name=f"Inscribed Tablet ({from_node.label})",
        description=f"A stone tablet with ancient writing near the {from_node.label}.",
        portable=True,
        properties={
            "examine_text": f"The inscription reads: 'Speak the word {password.upper()} to pass.'",
        },
    )
    ws.rooms[from_room_id].add_entity(clue)

    # Speaking stone / listener
    listener = Entity(
        id=f"listener_{edge_idx}",
        name=f"Speaking Stone ({from_node.label})",
        description=f"A stone face that seems to listen. Part of the {from_node.label}.",
        properties={
            "puzzle_type": "password_door",
            "password": password,
            "examine_text": "The stone face awaits a spoken word...",
            "on_solve": {
                "set_state": "solved",
                "unlock_door": door_id,
                "message": f"The word '{password}' echoes! The passage opens!",
            },
        },
    )
    ws.rooms[from_room_id].add_entity(listener)

    door = Door(
        id=door_id,
        name=f"Enchanted Gate ({from_node.label})",
        description=f"An enchanted gate leading toward the {to_node.label}.",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=True,
        state=EntityState.LOCKED,
    )
    ws.add_door(door, dir_from, dir_to)


def _create_trap_room(
    ws: WorldState,
    from_room_id: str,
    to_room_id: str,
    door_id: str,
    from_node: PuzzleNode,
    to_node: PuzzleNode,
    dir_from: str,
    dir_to: str,
    rng: random.Random,
) -> None:
    """Create a trap room that leads to the bad ending (open door, but room has danger)."""
    # Add a warning entity
    warning = Entity(
        id=f"warning_{from_node.id}",
        name="Ominous Warning",
        description="Strange markings on the wall seem to warn of danger ahead.",
        properties={
            "examine_text": "The markings depict someone falling into a trap. Proceed with caution!",
        },
    )
    ws.rooms[from_room_id].add_entity(warning)

    # The door is unlocked (the trap is that it's too easy)
    door = Door(
        id=door_id,
        name=f"Suspiciously Open Door ({from_node.label})",
        description="This door stands wide open. Almost too inviting...",
        room_a=from_room_id,
        room_b=to_room_id,
        locked=False,
        state=EntityState.OPEN,
    )
    ws.add_door(door, dir_from, dir_to)


# ---------------------------------------------------------------------------
# Preset Story Templates
# ---------------------------------------------------------------------------

PRESET_ALCHEMY_LAB = StoryInput(
    builder="Mad Alchemist Ethos",
    goal="Philosopher's Stone",
    background=(
        "Deep beneath an abandoned university, the Mad Alchemist Ethos built "
        "a labyrinthine laboratory to protect the Philosopher's Stone. "
        "The halls reek of sulfur and failed experiments. Glowing vials line "
        "the walls, and mechanical contraptions guard every passage."
    ),
    difficulty=3,
)

PRESET_COLD_WAR = StoryInput(
    builder="Colonel Volkov",
    goal="Nuclear Launch Codes",
    background=(
        "A decommissioned Soviet bunker hidden beneath the Ural Mountains. "
        "Colonel Volkov, a paranoid Cold War strategist, designed this facility "
        "with layers of security to protect the nuclear launch codes. "
        "The concrete walls hum with old electronics and flickering fluorescent lights."
    ),
    difficulty=4,
)

PRESET_SPACE_STATION = StoryInput(
    builder="AI Overseer ARIA",
    goal="Override Key",
    background=(
        "Orbital Station Kepler-7, controlled by the rogue AI ARIA. "
        "The station's corridors are sterile white, broken by holographic "
        "interfaces and sealed blast doors. ARIA watches through every camera, "
        "manipulating the environment to test intruders. The override key is "
        "the only way to regain control."
    ),
    difficulty=5,
)

PRESET_HAUNTED_MANSION = StoryInput(
    builder="Lady Ravencroft",
    goal="Cursed Amulet",
    background=(
        "Ravencroft Manor has stood for centuries, its halls haunted by the "
        "spirit of Lady Ravencroft who guards the Cursed Amulet. "
        "Cobwebs drape from chandeliers, portraits watch with moving eyes, "
        "and the floorboards creak with every step."
    ),
    difficulty=2,
)

PRESET_TEMPLATES: dict[str, StoryInput] = {
    "alchemy_lab": PRESET_ALCHEMY_LAB,
    "cold_war": PRESET_COLD_WAR,
    "space_station": PRESET_SPACE_STATION,
    "haunted_mansion": PRESET_HAUNTED_MANSION,
}


# ---------------------------------------------------------------------------
# Convenience: Full Pipeline
# ---------------------------------------------------------------------------

def build_from_preset(
    preset_name: str,
    use_ai_content: bool = False,
) -> tuple[World, list[str], dict[str, list[dict[str, Any]]]]:
    """Build a complete world from a preset template.

    Args:
        preset_name: Key into PRESET_TEMPLATES.
        use_ai_content: If True, call AI to fill creative descriptions.

    Returns: (world, agent_ids, escape_chains)
    """
    story = PRESET_TEMPLATES[preset_name]
    return build_from_story(story, use_ai_content=use_ai_content)


def build_from_story(
    story_input: StoryInput,
    use_ai_content: bool = False,
) -> tuple[World, list[str], dict[str, list[dict[str, Any]]]]:
    """Full pipeline: generate graph, optionally fill content, build world.

    Args:
        story_input: The story specification.
        use_ai_content: If True, call AI to fill creative descriptions.

    Returns: (world, agent_ids, escape_chains)
    """
    nodes, edges, endings = reverse_generate(story_input)

    if use_ai_content:
        nodes = fill_content(story_input, nodes, edges)

    world, agent_ids, escape_chains = build_world_from_graph(
        story_input, nodes, edges, endings,
    )

    return world, agent_ids, escape_chains
