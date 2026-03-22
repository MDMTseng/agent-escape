"""AgentTown WebSocket server — streams world state to connected clients."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

import anthropic
from agenttown.auth import get_api_key
from agenttown.main import RandomBrain, run_simulation
from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.events import Event
from agenttown.world.world import World

# In-memory ring buffer for recent log lines (viewable via /api/log)
_log_buffer: list[str] = []
_LOG_BUFFER_MAX = 200


class _BufferHandler(logging.Handler):
    def emit(self, record):
        line = self.format(record)
        _log_buffer.append(line)
        if len(_log_buffer) > _LOG_BUFFER_MAX:
            del _log_buffer[: len(_log_buffer) - _LOG_BUFFER_MAX]

logger = logging.getLogger(__name__)
_bh = _BufferHandler()
_bh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_bh)

# Connected WebSocket clients
connected_clients: set[WebSocket] = set()

# Shared simulation state
sim_world: World | None = None
sim_task: asyncio.Task | None = None
sim_paused: bool = False
sim_step_event: asyncio.Event | None = None
sim_brains: dict = {}  # agent_id -> brain, module-level so save/load can access
sim_scenario: str = ""
sim_store: Any = None  # GameStore instance
sim_token_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
sim_escape_chain: list = []  # escape chain steps for progress tracking


async def broadcast(message: dict) -> None:
    """Send a JSON message to all connected clients."""
    data = json.dumps(message)
    disconnected = set()
    for ws in connected_clients:
        try:
            await ws.send_text(data)
        except Exception:
            disconnected.add(ws)
    connected_clients.difference_update(disconnected)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start simulation on server startup. Auto-resumes from latest save if available."""
    global sim_world, sim_task, sim_brains, sim_scenario, sim_store

    from agenttown.persistence import GameStore
    sim_store = GameStore()

    sim_scenario = os.environ.get("AGENTTOWN_SCENARIO", "escape_room")
    use_claude = os.environ.get("AGENTTOWN_CLAUDE", "").lower() in ("1", "true", "yes")

    # Try to auto-resume from latest save
    latest = sim_store.latest()
    if latest and latest["scenario"] == sim_scenario:
        from agenttown.agents.brain import LLMBrain
        sim_world = World.from_full_snapshot(latest["world_snapshot"])
        sim_brains = {
            aid: LLMBrain.from_snapshot(bdata)
            for aid, bdata in latest["brain_snapshots"].items()
        }
        logger.info(f"Resumed from save '{latest['name']}' at tick {latest['tick']}")
    else:
        # Fresh start
        if sim_scenario == "memory_test":
            from agenttown.scenarios.memory_test import build_memory_test
            sim_world, agent_ids = build_memory_test()
            logger.info("Loaded scenario: memory_test")
        else:
            sim_world, agent_ids = build_escape_room()
            from agenttown.scenarios.escape_room_chain import DEFAULT_ESCAPE_CHAIN
            import copy
            sim_escape_chain = copy.deepcopy(DEFAULT_ESCAPE_CHAIN)
            logger.info("Loaded scenario: escape_room")

        if use_claude:
            from agenttown.agents.brain import LLMBrain
            sim_brains = {aid: LLMBrain() for aid in agent_ids}
            logger.info("Using LLM brains")
        else:
            sim_brains = {aid: RandomBrain() for aid in agent_ids}
            logger.info("Using random brains")

    # Narrator — transforms events into story prose
    narrator = None
    use_narrator = os.environ.get("AGENTTOWN_NARRATOR", "").lower() in ("1", "true", "yes")
    if use_narrator:
        from agenttown.agents.narrator import Narrator
        narrator = Narrator()
        logger.info("Narrator enabled")

    global sim_step_event
    sim_step_event = asyncio.Event()

    async def run_one_tick():
        """Execute a single simulation tick."""
        import time as _time

        tick = sim_world.tick
        agents = list(sim_world.state.agents.values())
        perceptions = {a.id: sim_world.perceive(a) for a in agents}

        logger.info(f"{'='*60}")
        logger.info(f"TICK {tick}")
        logger.info(f"{'='*60}")

        # Log agent positions before decisions
        agent_locs = {}
        for a in agents:
            room = sim_world.state.rooms.get(a.room_id)
            room_name = room.name if room else a.room_id
            inv = [i.name for i in a.inventory]
            agent_locs[a.name] = room_name
            logger.info(f"  {a.name}: {room_name} | inv={inv}")

        # Broadcast "processing" so UI shows thinking status
        await broadcast({
            "type": "processing",
            "tick": tick,
            "step": "deciding",
            "message": f"Tick {tick}: Agents thinking...",
            "agents": {a.name: agent_locs.get(a.name, "") for a in agents},
        })

        t0 = _time.time()
        # Each agent returns a list of up to 5 actions
        all_action_lists = await asyncio.gather(*[
            sim_brains[a.id].decide(a, perceptions[a.id]) for a in agents
        ])
        decide_time = _time.time() - t0
        logger.info(f"  Decisions took {decide_time:.1f}s")

        # Log and execute all actions for each agent sequentially
        tick_events: list[Event] = []
        for agent, action_list in zip(agents, all_action_lists):
            action_count = len(action_list)
            for i, action in enumerate(action_list):
                action_str = f"{action.type}"
                if hasattr(action, "direction"):
                    action_str += f"({action.direction})"
                elif hasattr(action, "target"):
                    action_str += f"({action.target})"
                elif hasattr(action, "message"):
                    action_str += f"(\"{action.message[:50]}\")"
                elif hasattr(action, "item_a"):
                    action_str += f"({action.item_a} + {action.item_b})"
                elif hasattr(action, "payload"):
                    action_str += f"({action.target}: {action.payload})"
                step = f"[{i+1}/{action_count}]" if action_count > 1 else ""
                logger.info(f"  {agent.name} {step}-> {action_str}")

                events = sim_world.process_action(action, agent)
                tick_events.extend(events)

        # Log events
        for e in tick_events:
            icon = {"move": ">>", "pick_up": "++", "drop": "--", "use": "**",
                    "examine": "??", "talk": "''", "fail": "XX", "state_change": "!!",
                    "wait": ".."}.get(e.event_type, "  ")
            logger.info(f"  {icon} {e.description}")

        # Run narrator in background thread to not block next tick
        narrative = ""
        if narrator and tick_events:
            interesting = [e for e in tick_events if e.event_type != "wait"]
            if interesting:
                try:
                    narrative = await asyncio.to_thread(
                        narrator.narrate, tick_events, sim_world.state, sim_world.tick
                    )
                except Exception as e:
                    logger.debug(f"Narrator failed: {e}")

        total_time = _time.time() - t0
        logger.info(f"  Total tick time: {total_time:.1f}s")

        # Aggregate token usage from all brains
        _update_token_usage()

        # Log memory & tokens
        for aid, brain in sim_brains.items():
            if hasattr(brain, "memory"):
                wm = brain.memory.get_working_memory()
                if wm:
                    logger.info(f"  [{aid} memory] {wm}")
        t = sim_token_usage
        logger.info(f"  TOKENS: {t['total_tokens']} total ({t['prompt_tokens']} in / {t['completion_tokens']} out)")

        # Token profiler — breakdown by call type
        for aid, brain in sim_brains.items():
            if hasattr(brain, "profile"):
                p = brain.profile
                parts = []
                for call_type in ("decide", "extract", "reflect"):
                    d = p[call_type]
                    if d["calls"] > 0:
                        parts.append(f"{call_type}={d['input']}in/{d['output']}out({d['calls']}x)")
                if parts:
                    logger.info(f"  [{aid} profile] {' | '.join(parts)}")
        logger.info("")

        await broadcast({
            "type": "tick",
            "tick": tick,
            "events": [
                {"type": e.event_type, "description": e.description, "room": e.room_id}
                for e in tick_events
            ],
            "narrative": narrative,
            "token_usage": dict(sim_token_usage),
            "token_profile": {
                aid: brain.profile for aid, brain in sim_brains.items()
                if hasattr(brain, "profile")
            },
            "world_state": sim_world.snapshot(),
            "escape_chain": _get_updated_chain(),
        })

        sim_world.advance_tick()

        if sim_world.finished:
            logger.info(f"GAME OVER: {sim_world.state.finish_reason}")
            finish_narrative = ""
            if narrator:
                finish_narrative = narrator.narrate(
                    tick_events, sim_world.state, sim_world.tick
                )
            await broadcast({
                "type": "finished",
                "reason": sim_world.state.finish_reason,
                "narrative": finish_narrative,
            })

    async def sim_loop():
        """Tick loop with pause/resume/step support. Survives resets."""
        global sim_paused
        sim_paused = True  # start paused
        while True:
            # Wait while paused or finished
            if sim_paused or sim_world.finished or sim_world.tick >= 200:
                sim_step_event.clear()
                if sim_world.finished:
                    await broadcast({"type": "finished_idle", "tick": sim_world.tick})
                else:
                    await broadcast({"type": "paused", "tick": sim_world.tick})
                await sim_step_event.wait()
                # After wake-up, check if it's a step or resume
                if sim_paused and not sim_world.finished and sim_world.tick < 200:
                    await run_one_tick()
                continue
            await run_one_tick()
            if not sim_world.finished:
                await asyncio.sleep(0.5)

    sim_task = asyncio.create_task(sim_loop())
    yield
    if sim_task and not sim_task.done():
        sim_task.cancel()


def _get_updated_chain() -> list[dict]:
    """Update and return escape chain with current world status."""
    if not sim_escape_chain or not sim_world:
        return []
    from agenttown.scenarios.generator import update_chain_status
    return update_chain_status(sim_escape_chain, sim_world.snapshot())


def _update_token_usage() -> None:
    """Sum token usage from all brains into the global counter."""
    sim_token_usage["prompt_tokens"] = 0
    sim_token_usage["completion_tokens"] = 0
    sim_token_usage["total_tokens"] = 0
    for brain in sim_brains.values():
        if hasattr(brain, "token_usage"):
            sim_token_usage["prompt_tokens"] += brain.token_usage.get("prompt_tokens", 0)
            sim_token_usage["completion_tokens"] += brain.token_usage.get("completion_tokens", 0)
            sim_token_usage["total_tokens"] += brain.token_usage.get("total_tokens", 0)


def _auto_pause_if_no_clients() -> None:
    """Pause simulation when all viewers disconnect."""
    global sim_paused
    if not connected_clients and not sim_paused:
        sim_paused = True
        logger.info("No clients connected — auto-paused")


app = FastAPI(title="AgentTown", lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)

    # Send current state on connect
    if sim_world:
        await ws.send_text(json.dumps({
            "type": "snapshot",
            "tick": sim_world.tick,
            "paused": sim_paused,
            "world_state": sim_world.snapshot(),
        }))

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(ws)
        # Don't auto-pause on disconnect — mobile browsers drop WebSocket
        # frequently. The game keeps running; user can reconnect anytime.


@app.get("/")
async def index():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/state")
async def get_state():
    if sim_world:
        return sim_world.snapshot()
    return {"error": "No simulation running"}


@app.post("/api/pause")
async def pause():
    global sim_paused
    sim_paused = True
    return {"status": "paused"}


@app.post("/api/resume")
async def resume():
    global sim_paused
    sim_paused = False
    if sim_step_event:
        sim_step_event.set()
    return {"status": "running"}


@app.post("/api/step")
async def step():
    global sim_paused
    sim_paused = True
    if sim_step_event:
        sim_step_event.set()
    return {"status": "stepped"}


@app.post("/api/save")
async def save_game(name: str | None = None):
    if not sim_world or not sim_store:
        return {"error": "No simulation running"}
    save_name = name or f"Tick {sim_world.tick}"
    save_id = sim_store.save(sim_world, sim_brains, sim_scenario, save_name)
    return {"save_id": save_id, "name": save_name, "status": "saved"}


@app.get("/api/saves")
async def list_saves():
    if not sim_store:
        return {"saves": []}
    return {"saves": sim_store.list_saves()}


@app.post("/api/load/{save_id}")
async def load_game(save_id: int):
    global sim_world, sim_brains, sim_paused
    if not sim_store:
        return {"error": "Store not initialized"}

    data = sim_store.load(save_id)
    if not data:
        return {"error": "Save not found"}

    sim_paused = True

    from agenttown.agents.brain import LLMBrain
    sim_world = World.from_full_snapshot(data["world_snapshot"])
    sim_brains.clear()
    sim_brains.update({
        aid: LLMBrain.from_snapshot(bdata)
        for aid, bdata in data["brain_snapshots"].items()
    })

    await broadcast({
        "type": "snapshot",
        "tick": sim_world.tick,
        "paused": True,
        "world_state": sim_world.snapshot(),
    })

    return {"status": "loaded", "tick": sim_world.tick, "name": data["name"]}


@app.delete("/api/saves/{save_id}")
async def delete_save(save_id: int):
    if sim_store and sim_store.delete(save_id):
        return {"status": "deleted"}
    return {"error": "Save not found"}


@app.post("/api/reset")
async def reset_game():
    """Reset the game to a fresh state without restarting the server."""
    global sim_world, sim_brains, sim_paused, sim_token_usage

    sim_paused = True

    scenario = os.environ.get("AGENTTOWN_SCENARIO", "escape_room")
    if scenario == "memory_test":
        from agenttown.scenarios.memory_test import build_memory_test
        sim_world, agent_ids = build_memory_test()
    else:
        sim_world, agent_ids = build_escape_room()

    use_claude = os.environ.get("AGENTTOWN_CLAUDE", "").lower() in ("1", "true", "yes")
    if use_claude:
        from agenttown.agents.brain import LLMBrain
        sim_brains.clear()
        sim_brains.update({aid: LLMBrain() for aid in agent_ids})
    else:
        sim_brains.clear()
        sim_brains.update({aid: RandomBrain() for aid in agent_ids})

    sim_token_usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    _log_buffer.clear()
    logger.info(f"Game reset — scenario: {scenario}")

    await broadcast({
        "type": "snapshot",
        "tick": sim_world.tick,
        "paused": True,
        "world_state": sim_world.snapshot(),
    })

    # Wake up sim_loop so it can start processing the new world
    if sim_step_event:
        sim_step_event.set()

    return {"status": "reset", "scenario": scenario}


@app.get("/api/map-rules")
async def get_map_rules():
    """Return the map creation rules reference."""
    from agenttown.scenarios.generator import MAP_RULES_REFERENCE
    return {"rules": MAP_RULES_REFERENCE}


@app.post("/api/generate-map")
async def generate_map(body: dict | None = None):
    """Generate a new scenario from user description using AI."""
    global sim_world, sim_brains, sim_paused, sim_token_usage, sim_scenario

    if not body:
        return {"error": "Missing request body"}

    theme = body.get("theme", "")
    logic = body.get("logic", "")

    if not theme:
        return {"error": "Theme is required"}

    sim_paused = True

    try:
        from agenttown.scenarios.builder import generate_puzzles, build_map
        import time as _time

        # Step 1: AI generates themed puzzles
        await broadcast({
            "type": "processing", "tick": 0, "step": "generating",
            "message": "Step 1/2: AI is designing puzzles...",
        })

        t0 = _time.time()
        try:
            puzzles = await asyncio.wait_for(
                asyncio.to_thread(generate_puzzles, theme, logic, 4),
                timeout=60,
            )
        except asyncio.TimeoutError:
            return {"error": "Puzzle generation timed out. Try a simpler theme."}
        gen_time = _time.time() - t0
        logger.info(f"  Puzzles generated in {gen_time:.1f}s")

        # Step 2: Code arranges puzzles into solvable map
        await broadcast({
            "type": "processing", "tick": 0, "step": "building",
            "message": f"Step 2/2: Building rooms & connections... ({gen_time:.0f}s)",
        })

        sim_world, agent_ids, escape_chain = build_map(theme, puzzles)

        global sim_escape_chain
        sim_escape_chain = escape_chain
        sim_scenario = "custom"

        # Create fresh brains
        use_claude = os.environ.get("AGENTTOWN_CLAUDE", "").lower() in ("1", "true", "yes")
        if use_claude:
            from agenttown.agents.brain import LLMBrain
            sim_brains.clear()
            sim_brains.update({aid: LLMBrain() for aid in agent_ids})
        else:
            sim_brains.clear()
            sim_brains.update({aid: RandomBrain() for aid in agent_ids})

        sim_token_usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        _log_buffer.clear()

        title = f"Custom: {theme[:40]}"
        n_rooms = len(sim_world.state.rooms)
        n_entities = sum(len(r.entities) for r in sim_world.state.rooms.values())
        logger.info(f"Built scenario: {n_rooms} rooms, {n_entities} entities, {len(escape_chain)} chain steps")

        await broadcast({
            "type": "snapshot",
            "tick": sim_world.tick,
            "paused": True,
            "world_state": sim_world.snapshot(),
            "escape_chain": sim_escape_chain,
        })

        if sim_step_event:
            sim_step_event.set()

        return {
            "status": "generated",
            "title": title,
            "rooms": n_rooms,
            "entities": n_entities,
            "agents": len(agent_ids),
            "chain_steps": len(escape_chain),
            "warnings": [],
        }

    except Exception as e:
        logger.error(f"Map generation failed: {e}")
        return {"error": str(e)}


@app.get("/api/presets")
async def list_presets():
    """List available preset story templates."""
    from agenttown.scenarios.architect import PRESET_TEMPLATES
    return {"presets": {k: {"builder": v.builder, "goal": v.goal, "background": v.background[:80], "difficulty": v.difficulty} for k, v in PRESET_TEMPLATES.items()}}


@app.post("/api/preview-architect")
async def preview_architect(body: dict | None = None):
    """Preview a generated map without loading it into the game."""
    if not body:
        return {"error": "Missing body"}

    try:
        from agenttown.scenarios.architect import (
            StoryInput, reverse_generate, extract_escape_chains, PRESET_TEMPLATES,
        )

        preset = body.get("preset")
        if preset and preset in PRESET_TEMPLATES:
            story = PRESET_TEMPLATES[preset]
        else:
            story = StoryInput(
                builder=body.get("builder", "Unknown"),
                goal=body.get("goal", "Unknown"),
                background=body.get("background", "A mysterious place"),
                difficulty=body.get("difficulty", 3),
            )

        nodes, edges, endings = reverse_generate(story)
        chains = extract_escape_chains(nodes, edges)

        # Build preview data
        node_list = []
        for n in nodes:
            node_list.append({
                "id": n.id, "type": n.type, "label": n.label,
                "depth": n.depth, "is_goal": n.is_goal,
                "is_entrance": n.is_entrance, "is_fork": n.is_fork,
                "ending_type": n.ending_type, "path_color": n.path_color,
                "x": n.x, "y": n.y,
            })

        edge_list = []
        for e in edges:
            edge_list.append({
                "from": e.from_id, "to": e.to_id,
                "ending_type": e.ending_type, "color": e.color,
                "is_branch": e.is_branch,
            })

        ending_labels = {"good": "Good Ending", "bad": "Bad Ending", "secret": "Secret Ending", "true_": "True Ending"}
        ending_info = []
        for ending in endings:
            ending_info.append({
                "key": ending.ending_type,
                "label": ending_labels.get(ending.ending_type, ending.ending_type),
                "color": ending.color,
                "chain_length": len(chains.get(ending.ending_type, [])),
            })

        return {
            "status": "preview",
            "story": {"builder": story.builder, "goal": story.goal, "background": story.background, "difficulty": story.difficulty},
            "nodes": node_list,
            "edges": edge_list,
            "endings": ending_info,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "endings": len(endings),
                "entrances": sum(1 for n in nodes if n.is_entrance),
                "forks": sum(1 for n in nodes if n.is_fork),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/generate-architect")
async def generate_architect(body: dict | None = None):
    """Generate a scenario using the Reverse Escape Room Architect."""
    global sim_world, sim_brains, sim_paused, sim_token_usage, sim_scenario, sim_escape_chain

    if not body:
        return {"error": "Missing request body"}

    sim_paused = True

    try:
        from agenttown.scenarios.architect import StoryInput, build_from_story, build_from_preset, PRESET_TEMPLATES
        import time as _time

        preset = body.get("preset")
        if preset and preset in PRESET_TEMPLATES:
            await broadcast({
                "type": "processing", "tick": 0, "step": "generating",
                "message": f"Building preset: {preset}...",
            })
            t0 = _time.time()
            sim_world, agent_ids, chains = build_from_preset(preset)
        else:
            story = StoryInput(
                builder=body.get("builder", "Unknown Builder"),
                goal=body.get("goal", "Unknown Treasure"),
                background=body.get("background", "A mysterious place"),
                difficulty=body.get("difficulty", 3),
            )

            await broadcast({
                "type": "processing", "tick": 0, "step": "generating",
                "message": f"Step 1/2: Building puzzle graph (depth {story.difficulty})...",
            })
            t0 = _time.time()
            sim_world, agent_ids, chains = build_from_story(story)

        gen_time = _time.time() - t0

        # Flatten chains for the escape chain UI
        all_steps = []
        step_num = 0
        for ending, steps in chains.items():
            for s in steps:
                step_num += 1
                all_steps.append({
                    "step": step_num,
                    "action": s.get("type", "solve"),
                    "target": s.get("label", "?"),
                    "entity_id": s.get("node_id", ""),
                    "room": s.get("label", ""),
                    "room_id": s.get("node_id", ""),
                    "description": f"[{ending}] {s.get('description', s.get('label', '?'))}",
                    "status": "pending",
                    "check_type": "solve" if not s.get("is_goal") else "finish",
                    "ending_type": ending,
                })
        sim_escape_chain = all_steps
        sim_scenario = "architect"

        # Create brains
        use_claude = os.environ.get("AGENTTOWN_CLAUDE", "").lower() in ("1", "true", "yes")
        if use_claude:
            from agenttown.agents.brain import LLMBrain
            sim_brains.clear()
            sim_brains.update({aid: LLMBrain() for aid in agent_ids})
        else:
            sim_brains.clear()
            sim_brains.update({aid: RandomBrain() for aid in agent_ids})

        sim_token_usage.update({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
        _log_buffer.clear()

        n_rooms = len(sim_world.state.rooms)
        n_doors = len(sim_world.state.doors)
        n_endings = len(chains)
        logger.info(f"Architect built: {n_rooms}R {n_doors}D {n_endings} endings, {len(all_steps)} chain steps in {gen_time:.1f}s")

        await broadcast({
            "type": "snapshot",
            "tick": sim_world.tick,
            "paused": True,
            "world_state": sim_world.snapshot(),
            "escape_chain": sim_escape_chain,
        })

        if sim_step_event:
            sim_step_event.set()

        return {
            "status": "generated",
            "title": f"{body.get('builder', preset or 'Custom')}",
            "rooms": n_rooms,
            "doors": n_doors,
            "endings": n_endings,
            "chain_steps": len(all_steps),
            "gen_time": round(gen_time, 1),
        }

    except Exception as e:
        logger.error(f"Architect failed: {e}")
        return {"error": str(e)}


@app.post("/api/auto-generate")
async def auto_generate(body: dict | None = None):
    """Auto-generate theme or logic text using AI. Uses existing input as context."""
    field = (body or {}).get("field", "theme")
    existing_theme = (body or {}).get("theme", "")
    existing_logic = (body or {}).get("logic", "")

    try:
        client = anthropic.Anthropic(api_key=get_api_key())
        model = os.environ.get("ANTHROPIC_MAP_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5"))

        if field == "theme":
            ctx = ""
            if existing_theme:
                ctx = f"The user has started writing a theme:\n\"{existing_theme}\"\n\nExpand and improve this into a complete theme. Keep their ideas but make it richer.\n\n"
            else:
                ctx = ""
            response = client.messages.create(
                model=model, max_tokens=200,
                messages=[{"role": "user", "content":
                    f"{ctx}"
                    "Generate a creative escape room theme with a background story in 2-3 sentences. "
                    "Be imaginative — sci-fi, horror, fantasy, historical, underwater, space, etc. "
                    "Include WHO is trapped, WHERE, and WHY they need to escape. "
                    "Return ONLY the theme text, no markdown headers."}],
            )
            return {"text": response.content[0].text.strip()}

        elif field == "logic":
            ctx_parts = []
            if existing_theme:
                ctx_parts.append(f"Theme: {existing_theme}")
            if existing_logic:
                ctx_parts.append(f"The user has started writing map logic:\n\"{existing_logic}\"\n\nExpand and complete this into a full map design. Keep their ideas.")
            ctx = "\n\n".join(ctx_parts) + "\n\n" if ctx_parts else ""
            response = client.messages.create(
                model=model, max_tokens=400,
                messages=[{"role": "user", "content":
                    f"{ctx}"
                    "Generate escape room map logic. Include:\n"
                    "- 4-5 rooms with names and connections (which direction each door is)\n"
                    "- 3-4 different puzzle types (combination lock, pressure plate, password, levers, item combine)\n"
                    "- A puzzle chain: solving one reveals clue/item for the next\n"
                    "- Specific items in each room\n"
                    "- The codes/passwords and where their clues are hidden\n"
                    "Return ONLY bullet points, no markdown headers."}],
            )
            return {"text": response.content[0].text.strip()}

        elif field == "all":
            ctx_parts = []
            if existing_theme:
                ctx_parts.append(f"User's theme idea: \"{existing_theme}\"")
            if existing_logic:
                ctx_parts.append(f"User's logic idea: \"{existing_logic}\"")
            ctx = "Build on the user's ideas:\n" + "\n".join(ctx_parts) + "\n\n" if ctx_parts else ""

            response = client.messages.create(
                model=model, max_tokens=600,
                messages=[{"role": "user", "content":
                    f"{ctx}"
                    "Generate a creative escape room concept. Return in this exact format:\n\n"
                    "THEME:\n[2-3 sentence theme with setting, characters, and reason to escape]\n\n"
                    "LOGIC:\n[bullet point list of 4-5 rooms, connections, and 3-4 puzzles with specific codes/passwords]\n\n"
                    "Be creative. Return ONLY this format, no extra text."}],
            )
            text = response.content[0].text.strip()
            theme_text = ""
            logic_text = ""
            if "THEME:" in text and "LOGIC:" in text:
                parts = text.split("LOGIC:")
                theme_text = parts[0].replace("THEME:", "").strip()
                logic_text = parts[1].strip()
            else:
                theme_text = text
            return {"theme": theme_text, "logic": logic_text}

    except Exception as e:
        return {"error": str(e)}


@app.get("/api/log")
async def get_log(n: int = 50):
    """Return recent log lines. View from mobile: /api/log?n=100"""
    return {"lines": _log_buffer[-n:]}


@app.get("/log")
async def log_page():
    """Simple HTML log viewer for mobile."""
    return HTMLResponse(LOG_HTML)


LOG_HTML = """\
<!DOCTYPE html>
<html>
<head>
<title>AgentTown Log</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    body { background: #0d1117; color: #c9d1d9; font-family: monospace; font-size: 12px; padding: 10px; margin: 0; }
    h1 { color: #e3b341; font-size: 16px; margin-bottom: 8px; }
    #controls { margin-bottom: 10px; }
    button { font-family: monospace; font-size: 11px; padding: 4px 10px; border: 1px solid #30363d; border-radius: 4px; background: #21262d; color: #c9d1d9; cursor: pointer; margin-right: 5px; }
    button:hover { border-color: #58a6ff; }
    #log { white-space: pre-wrap; line-height: 1.5; }
    .tick-line { color: #e3b341; font-weight: bold; }
    .event-line { color: #79c0ff; }
    .memory-line { color: #d2a8ff; }
    .token-line { color: #3fb950; }
    .error-line { color: #f85149; }
    .action-line { color: #f0f6fc; }
</style>
</head>
<body>
<h1>AgentTown Log</h1>
<div id="controls">
    <button onclick="refresh()">Refresh</button>
    <button onclick="autoRefresh()">Auto (3s)</button>
    <button onclick="stopAuto()">Stop</button>
    <span id="status" style="color:#8b949e"></span>
</div>
<div id="log"></div>
<script>
    let timer = null;
    const logDiv = document.getElementById('log');
    const statusEl = document.getElementById('status');

    function colorize(line) {
        if (line.includes('TICK ') || line.includes('====')) return 'tick-line';
        if (line.includes('->')) return 'action-line';
        if (line.includes('??') || line.includes('>>') || line.includes('++') || line.includes('**') || line.includes("''") || line.includes('!!') || line.includes('XX')) return 'event-line';
        if (line.includes('[') && line.includes('memory]')) return 'memory-line';
        if (line.includes('TOKENS:')) return 'token-line';
        if (line.includes('error') || line.includes('Error') || line.includes('GAME OVER')) return 'error-line';
        return '';
    }

    function refresh() {
        fetch('/api/log?n=100').then(r => r.json()).then(d => {
            logDiv.innerHTML = d.lines.map(l => {
                const cls = colorize(l);
                return cls ? `<span class="${cls}">${l}</span>` : l;
            }).join('\\n');
            logDiv.scrollTop = logDiv.scrollHeight;
            statusEl.textContent = 'Updated ' + new Date().toLocaleTimeString();
        });
    }

    function autoRefresh() {
        if (timer) clearInterval(timer);
        timer = setInterval(refresh, 3000);
        refresh();
        statusEl.textContent = 'Auto-refreshing...';
    }

    function stopAuto() {
        if (timer) { clearInterval(timer); timer = null; }
        statusEl.textContent = 'Stopped';
    }

    refresh();
</script>
</body>
</html>
"""


DASHBOARD_HTML = """\
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>AgentTown — Ravenwood Manor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Georgia', serif;
            background: #0d1117;
            color: #c9d1d9;
            display: flex;
            height: 100vh;
        }
        /* Left: narrative */
        #story-panel {
            flex: 3;
            padding: 24px;
            overflow-y: auto;
            border-right: 1px solid #21262d;
            display: flex;
            flex-direction: column;
        }
        #story-panel h1 { color: #e3b341; font-size: 24px; margin-bottom: 4px; }
        .subtitle { color: #8b949e; font-style: italic; margin-bottom: 12px; font-size: 13px; }
        #controls {
            display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
        }
        #controls button {
            font-family: monospace; font-size: 11px; padding: 4px 12px;
            border: 1px solid #30363d; border-radius: 4px; cursor: pointer;
            background: #21262d; color: #c9d1d9; transition: all 0.2s;
        }
        #controls button:hover:not(:disabled) { background: #30363d; border-color: #58a6ff; }
        #controls button:disabled { opacity: 0.4; cursor: default; }
        #controls button.active { background: #1f6feb; border-color: #58a6ff; color: #fff; }
        #controls .sep { color: #30363d; margin: 0 2px; }
        #status { color: #3fb950; font-family: monospace; font-size: 11px; }
        #token-display {
            margin-left: auto;
            font-family: monospace; font-size: 12px; font-weight: bold;
            color: #e3b341; background: #2d2006; padding: 3px 10px;
            border-radius: 4px; border: 1px solid #e3b341;
        }
        #save-list {
            background: #161b22; border: 1px solid #30363d; border-radius: 6px;
            padding: 10px; font-family: monospace; font-size: 11px; max-height: 150px; overflow-y: auto;
        }
        .save-entry {
            display: flex; justify-content: space-between; align-items: center;
            padding: 4px 6px; border-bottom: 1px solid #21262d;
        }
        .save-entry:last-child { border-bottom: none; }
        .save-entry .save-info { color: #8b949e; }
        .save-entry .save-name { color: #e6edf3; font-weight: bold; }
        .save-entry button {
            font-family: monospace; font-size: 10px; padding: 2px 8px;
            border: 1px solid #30363d; border-radius: 3px; cursor: pointer;
            background: #21262d; color: #c9d1d9; margin-left: 6px;
        }
        .save-entry button:hover { border-color: #58a6ff; }
        .save-entry button.del:hover { border-color: #f85149; color: #f85149; }
        /* Card-based story viewer */
        #story { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
        #story-card-container {
            flex: 1; display: flex; align-items: center; justify-content: center;
            position: relative; overflow: hidden; padding: 10px;
        }
        .story-card {
            background: #161b22; border: 1px solid #30363d; border-radius: 10px;
            padding: 24px; max-width: 100%; width: 100%;
            line-height: 1.8; font-size: 15px; color: #e6edf3;
            box-shadow: 0 4px 20px rgba(0,0,0,0.4);
            min-height: 120px;
        }
        .story-card .chapter-num {
            color: #e3b341; font-family: monospace; font-size: 11px;
            margin-bottom: 10px; letter-spacing: 1px;
        }
        .story-card .card-events {
            color: #8b949e; font-family: monospace; font-size: 10px;
            margin-top: 12px; padding-top: 10px; border-top: 1px solid #21262d;
        }
        .story-card.finished { border-color: #3fb950; }
        .story-card.finished .chapter-num { color: #3fb950; }
        #story-nav {
            display: flex; align-items: center; justify-content: center; gap: 12px;
            padding: 10px; flex-shrink: 0;
        }
        #story-nav button {
            font-family: monospace; font-size: 16px; width: 36px; height: 36px;
            border: 1px solid #30363d; border-radius: 6px; cursor: pointer;
            background: #21262d; color: #c9d1d9;
        }
        #story-nav button:hover:not(:disabled) { border-color: #58a6ff; }
        #story-nav button:disabled { opacity: 0.3; cursor: default; }
        #story-nav .page-info { color: #8b949e; font-family: monospace; font-size: 11px; min-width: 60px; text-align: center; }
        #btn-copy-scene {
            font-family: monospace; font-size: 11px; padding: 4px 10px;
            border: 1px solid #e3b341; border-radius: 4px; cursor: pointer;
            background: #2d2006; color: #e3b341;
        }
        #btn-copy-scene:hover { background: #3d3010; }
        #copy-toast {
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: #3fb950; color: #0d1117; padding: 8px 20px; border-radius: 6px;
            font-family: monospace; font-size: 12px; display: none; z-index: 999;
        }

        /* Right: status panels + log */
        #right-panel {
            flex: 2;
            display: flex;
            flex-direction: column;
            background: #0a0e14;
        }

        /* Scene graph */
        #map-panel {
            padding: 16px;
            border-bottom: 1px solid #21262d;
        }
        #map-panel h2 { color: #e3b341; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #scene-graph { width: 100%; }
        #scene-graph svg { width: 100%; height: auto; }

        /* Puzzle panel */
        #puzzle-panel {
            padding: 16px;
            border-bottom: 1px solid #21262d;
        }
        #puzzle-panel h2 { color: #d2a8ff; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #puzzle-list { display: flex; flex-direction: column; gap: 6px; }
        .puzzle-row {
            display: flex;
            align-items: center;
            gap: 8px;
            font-family: monospace;
            font-size: 11px;
            padding: 6px 8px;
            background: #161b22;
            border-radius: 4px;
        }
        .puzzle-icon { font-size: 14px; width: 20px; text-align: center; }
        .puzzle-name { color: #e6edf3; flex: 1; }
        .puzzle-status { padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: bold; }
        .puzzle-status.locked { background: #3d1f1f; color: #f85149; }
        .puzzle-status.solved { background: #1a3a1a; color: #3fb950; }
        .puzzle-status.partial { background: #3d3520; color: #e3b341; }

        /* Agent panel */
        #agent-panel {
            padding: 16px;
            border-bottom: 1px solid #21262d;
        }
        #agent-panel h2 { color: #58a6ff; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #agent-list { display: flex; gap: 8px; }
        .agent-card {
            flex: 1;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 8px 10px;
            font-family: monospace;
            font-size: 11px;
        }
        .agent-card .agent-name { color: #58a6ff; font-weight: bold; font-size: 12px; margin-bottom: 4px; }
        .agent-card .agent-location { color: #8b949e; margin-bottom: 3px; }
        .agent-card .agent-inv { color: #3fb950; font-size: 10px; }
        .agent-card .agent-inv-empty { color: #484f58; font-size: 10px; }

        /* Tabbed log panel */
        #log-panel {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            font-family: 'Courier New', monospace;
            font-size: 11px;
        }
        .log-tabs {
            display: flex; gap: 0; padding: 8px 16px 0; flex-shrink: 0;
        }
        .log-tab {
            padding: 4px 14px; cursor: pointer; font-family: monospace; font-size: 11px;
            border: 1px solid #30363d; border-bottom: none; border-radius: 4px 4px 0 0;
            background: #0a0e14; color: #8b949e;
        }
        .log-tab.active { background: #161b22; color: #58a6ff; border-color: #58a6ff; }
        .log-content {
            flex: 1; overflow-y: auto; padding: 12px 16px;
        }
        #server-log { display: none; white-space: pre-wrap; line-height: 1.5; }
        #server-log .sl-tick { color: #e3b341; font-weight: bold; }
        #server-log .sl-action { color: #f0f6fc; }
        #server-log .sl-event { color: #79c0ff; }
        #server-log .sl-memory { color: #d2a8ff; }
        #server-log .sl-token { color: #3fb950; }
        #server-log .sl-error { color: #f85149; }
        .tick-group { margin-bottom: 8px; border-left: 2px solid #30363d; padding-left: 8px; }
        .tick-label { color: #8b949e; font-size: 10px; margin-bottom: 2px; }
        .event { padding: 1px 0; font-size: 11px; }
        .event.move { color: #79c0ff; }
        .event.pick_up { color: #3fb950; }
        .event.drop { color: #d29922; }
        .event.use { color: #d2a8ff; }
        .event.examine { color: #58a6ff; }
        .event.talk { color: #f0f6fc; }
        .event.fail { color: #f85149; }
        .event.state_change { color: #e3b341; }
        .event.wait { color: #484f58; }

        @media (max-width: 900px) {
            body { flex-direction: column; height: auto; min-height: 100vh; }
            #story-panel {
                flex: none; border-right: none; padding: 12px;
                border-bottom: 1px solid #21262d;
            }
            #story-panel h1 { font-size: 18px; }
            .subtitle { font-size: 11px; margin-bottom: 6px; }
            #controls {
                flex-wrap: wrap; gap: 4px;
            }
            #controls button { font-size: 10px; padding: 3px 8px; }
            #controls .sep { display: none; }
            #token-display { font-size: 10px; padding: 2px 6px; margin-left: 0; margin-top: 4px; width: 100%; text-align: center; }
            #save-list { font-size: 10px; }
            #story-card-container { padding: 6px; }
            .story-card { padding: 14px; font-size: 13px; line-height: 1.6; }
            .story-card .chapter-num { font-size: 10px; }
            .story-card .card-events { font-size: 9px; }
            #story-nav { padding: 6px; gap: 8px; }
            #story-nav button { width: 32px; height: 32px; font-size: 14px; }
            #btn-copy-scene { font-size: 10px; padding: 3px 8px; }
            #right-panel { flex: none; }
            #map-panel { padding: 10px; }
            #map-panel h2, #puzzle-panel h2, #agent-panel h2 { font-size: 11px; }
            .room-card { font-size: 10px; padding: 6px; min-width: 80px; }
            .room-card .room-name { font-size: 10px; }
            .puzzle-row { font-size: 10px; padding: 4px 6px; }
            .puzzle-status { font-size: 9px; }
            .agent-card { font-size: 10px; padding: 6px; }
            #log-panel { max-height: 40vh; }
            .log-tabs { padding: 6px 10px 0; }
            .log-tab { font-size: 10px; padding: 3px 10px; }
            .log-content { padding: 8px 10px; font-size: 10px; }
            .tick-group { font-size: 10px; }
            .event { font-size: 10px; }
        }
    </style>
</head>
<body>
    <div id="story-panel">
        <h1>Ravenwood Manor</h1>
        <div class="subtitle">An escape room experience</div>
        <div id="controls">
            <button id="btn-pause" onclick="simPause()">Pause</button>
            <button id="btn-resume" onclick="simResume()" disabled>Resume</button>
            <button id="btn-step" onclick="simStep()" disabled>Step 1 Tick</button>
            <span class="sep">|</span>
            <button id="btn-save" onclick="simSave()">Save</button>
            <button id="btn-load" onclick="toggleSaveList()">Load</button>
            <button id="btn-reset" onclick="simReset()" style="color:#f85149">Reset</button>
            <button id="btn-create" onclick="toggleCreator()" style="color:#e3b341">Create</button>
            <span id="status">Connecting...</span>
            <span id="token-display">Tokens: 0</span>
        </div>
        <div id="save-list" style="display:none; margin-bottom: 12px;"></div>
        <div id="story">
            <div id="story-card-container">
                <div class="story-card" id="current-card">
                    <div class="chapter-num">Waiting for first tick...</div>
                </div>
            </div>
            <div id="story-nav">
                <button id="btn-prev" onclick="prevCard()" disabled>&lt;</button>
                <span class="page-info" id="page-info">0 / 0</span>
                <button id="btn-next" onclick="nextCard()" disabled>&gt;</button>
                <button id="btn-copy-scene" onclick="copyScene()">Copy Scene</button>
            </div>
        </div>
        <div id="copy-toast">Copied to clipboard!</div>

        <!-- Map Creator Modal (Reverse Architect) -->
        <div id="creator-overlay" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.85); z-index:1000; overflow-y:auto; padding:12px;">
            <div style="max-width:600px; margin:0 auto; background:#161b22; border:1px solid #30363d; border-radius:10px; padding:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h2 style="color:#e3b341; font-size:16px; font-family:monospace;">Escape Room Architect</h2>
                    <button onclick="toggleCreator()" style="background:none; border:1px solid #30363d; color:#8b949e; border-radius:4px; padding:3px 8px; cursor:pointer; font-family:monospace; font-size:11px;">Close</button>
                </div>

                <!-- Presets -->
                <div style="margin-bottom:12px;">
                    <label style="color:#8b949e; font-family:monospace; font-size:10px; margin-bottom:4px; display:block;">Quick Presets</label>
                    <div id="preset-buttons" style="display:flex; gap:4px; flex-wrap:wrap;"></div>
                </div>

                <!-- Builder Inputs -->
                <div style="display:flex; gap:8px; margin-bottom:8px;">
                    <div style="flex:1;">
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Builder</label>
                        <input id="arc-builder" placeholder="Mad Scientist, Pharaoh..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:13px;">
                    </div>
                    <div style="flex:1;">
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Protects</label>
                        <input id="arc-goal" placeholder="Secret formula, treasure..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:13px;">
                    </div>
                </div>

                <div style="margin-bottom:8px;">
                    <label style="color:#8b949e; font-family:monospace; font-size:10px;">Background</label>
                    <textarea id="arc-background" rows="2" placeholder="Scene description..." style="width:100%; background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:6px; font-family:monospace; font-size:12px; resize:vertical;"></textarea>
                </div>

                <!-- Difficulty & Endings -->
                <div style="display:flex; gap:12px; margin-bottom:12px; align-items:center;">
                    <div>
                        <label style="color:#8b949e; font-family:monospace; font-size:10px;">Difficulty</label>
                        <select id="arc-difficulty" onchange="updateEndingPreview()" style="background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:4px 8px; font-family:monospace; font-size:13px;">
                            <option value="2">2 - Simple</option>
                            <option value="3" selected>3 - Medium</option>
                            <option value="4">4 - Complex</option>
                            <option value="5">5 - Epic</option>
                        </select>
                    </div>
                    <div id="ending-preview" style="display:flex; gap:4px; flex-wrap:wrap;"></div>
                </div>

                <!-- Action Buttons -->
                <div style="display:flex; gap:6px; margin-bottom:10px;">
                    <button onclick="previewMap()" id="btn-preview" style="flex:1; padding:8px; background:#21262d; border:1px solid #58a6ff; border-radius:6px; color:#58a6ff; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold;">Preview Map</button>
                    <button onclick="previewMap()" id="btn-regenerate" style="flex:1; padding:8px; background:#21262d; border:1px solid #e3b341; border-radius:6px; color:#e3b341; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold; display:none;">Regenerate</button>
                    <button onclick="playPreviewedMap()" id="btn-play-map" style="flex:1; padding:8px; background:#1f6feb; border:none; border-radius:6px; color:#fff; font-family:monospace; font-size:12px; cursor:pointer; font-weight:bold; display:none;">Play This Map</button>
                </div>

                <div id="creator-status" style="color:#8b949e; font-family:monospace; font-size:11px; margin-bottom:8px;"></div>

                <!-- Preview Graph -->
                <div id="preview-container" style="display:none;">
                    <div id="preview-stats" style="display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;"></div>
                    <div id="preview-graph" style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:8px; overflow:hidden;"></div>
                    <div id="preview-endings" style="margin-top:8px;"></div>
                </div>
            </div>
        </div>
    </div>
    <div id="right-panel">
        <div id="map-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <h2>SCENE VIEW</h2>
                <button onclick="toggleFullscreenScene()" style="background:none;border:1px solid #30363d;color:#8b949e;border-radius:3px;padding:2px 6px;cursor:pointer;font-family:monospace;font-size:10px;">Fullscreen</button>
            </div>
            <div id="scene-graph"></div>
        </div>
        <div id="puzzle-panel">
            <h2>PUZZLE PROGRESS</h2>
            <div id="puzzle-list"></div>
        </div>
        <div id="agent-panel">
            <h2>AGENTS</h2>
            <div id="agent-list"></div>
        </div>
        <div id="log-panel">
            <div class="log-tabs">
                <div class="log-tab active" onclick="switchLogTab('events')">Events</div>
                <div class="log-tab" onclick="switchLogTab('server-log')">Server Log</div>
            </div>
            <div id="events" class="log-content"></div>
            <div id="server-log" class="log-content"></div>
        </div>
    </div>
    <script>
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        const tokenDiv = document.getElementById('token-display');
        const sceneDiv = document.getElementById('scene-graph');
        const puzzleDiv = document.getElementById('puzzle-list');
        const agentDiv = document.getElementById('agent-list');
        const currentCard = document.getElementById('current-card');
        const pageInfo = document.getElementById('page-info');
        const btnPrev = document.getElementById('btn-prev');
        const btnNext = document.getElementById('btn-next');
        const copyToast = document.getElementById('copy-toast');

        // --- Story card system ---
        const storyCards = [];  // [{tick, narrative, events, agents, rooms}]
        let cardIndex = -1;
        let autoFollow = true;  // auto-advance to latest card

        function addCard(data) {
            storyCards.push(data);
            if (autoFollow) {
                cardIndex = storyCards.length - 1;
                renderCard();
            } else {
                updateNav();
            }
        }

        function renderCard() {
            if (cardIndex < 0 || cardIndex >= storyCards.length) return;
            const c = storyCards[cardIndex];
            const isFinished = c.finished;
            let html = `<div class="chapter-num">CHAPTER ${c.tick + 1}</div>`;
            html += `<div>${(c.narrative || 'No narration.').replace(/\\n/g, '<br>')}</div>`;
            if (c.events && c.events.length) {
                html += `<div class="card-events">${c.events.map(e => e.description).join(' | ')}</div>`;
            }
            currentCard.innerHTML = html;
            currentCard.className = 'story-card' + (isFinished ? ' finished' : '');
            updateNav();
        }

        function updateNav() {
            const total = storyCards.length;
            pageInfo.textContent = total > 0 ? `${cardIndex + 1} / ${total}` : '0 / 0';
            btnPrev.disabled = cardIndex <= 0;
            btnNext.disabled = cardIndex >= total - 1;
        }

        function prevCard() {
            if (cardIndex > 0) { cardIndex--; autoFollow = false; renderCard(); }
        }
        function nextCard() {
            if (cardIndex < storyCards.length - 1) {
                cardIndex++;
                if (cardIndex === storyCards.length - 1) autoFollow = true;
                renderCard();
            }
        }

        function copyScene() {
            if (cardIndex < 0 || cardIndex >= storyCards.length) return;
            const c = storyCards[cardIndex];
            // Build a rich scene description for image generation
            const parts = [];
            parts.push('IMAGE GENERATION PROMPT:');
            parts.push('Style: Dark atmospheric digital painting, escape room horror, dramatic lighting');
            parts.push('');
            parts.push('Scene: ' + (c.narrative || 'No narration'));
            parts.push('');
            if (c.agents) {
                for (const a of Object.values(c.agents)) {
                    const room = c.rooms && c.rooms[a.room_id] ? c.rooms[a.room_id].name : a.room_id;
                    const inv = (a.inventory || []).map(i => i.name).join(', ') || 'nothing';
                    parts.push(`Character: ${a.name} (${a.description}) in ${room}, carrying ${inv}`);
                }
            }
            if (c.rooms) {
                for (const r of Object.values(c.rooms)) {
                    parts.push(`Location: ${r.name} - ${r.description}`);
                }
            }
            if (c.events && c.events.length) {
                parts.push('');
                parts.push('Actions: ' + c.events.map(e => e.description).join('. '));
            }
            const text = parts.join('\\n');
            navigator.clipboard.writeText(text).then(() => {
                copyToast.style.display = 'block';
                setTimeout(() => { copyToast.style.display = 'none'; }, 2000);
            });
        }

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') prevCard();
            else if (e.key === 'ArrowRight') nextCard();
        });

        // --- Scene Fullscreen ---
        function toggleFullscreenScene() {
            const panel = document.getElementById('map-panel');
            if (panel.style.position === 'fixed') {
                panel.style.position = '';
                panel.style.top = '';
                panel.style.left = '';
                panel.style.right = '';
                panel.style.bottom = '';
                panel.style.zIndex = '';
                panel.style.background = '';
                panel.style.padding = '';
                panel.style.overflow = '';
            } else {
                panel.style.position = 'fixed';
                panel.style.top = '0';
                panel.style.left = '0';
                panel.style.right = '0';
                panel.style.bottom = '0';
                panel.style.zIndex = '999';
                panel.style.background = '#0a0e14';
                panel.style.padding = '16px';
                panel.style.overflow = 'auto';
            }
        }

        // --- Log tab switching ---
        const serverLogDiv = document.getElementById('server-log');
        let activeLogTab = 'events';
        let logTimer = null;

        function switchLogTab(tab) {
            activeLogTab = tab;
            document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.log-content').forEach(c => c.style.display = 'none');
            event.target.classList.add('active');
            document.getElementById(tab).style.display = 'block';

            if (tab === 'server-log') {
                refreshServerLog();
                if (!logTimer) logTimer = setInterval(refreshServerLog, 3000);
            } else {
                if (logTimer) { clearInterval(logTimer); logTimer = null; }
            }
        }

        function slColorize(line) {
            if (line.includes('TICK ') || line.includes('====')) return 'sl-tick';
            if (line.includes('->')) return 'sl-action';
            if (line.includes('??') || line.includes('>>') || line.includes('++') || line.includes('**') || line.includes("''") || line.includes('!!') || line.includes('XX')) return 'sl-event';
            if (line.includes('memory]')) return 'sl-memory';
            if (line.includes('TOKENS:')) return 'sl-token';
            if (line.includes('error') || line.includes('Error') || line.includes('GAME OVER')) return 'sl-error';
            return '';
        }

        function refreshServerLog() {
            fetch('/api/log?n=100').then(r => r.json()).then(d => {
                serverLogDiv.innerHTML = d.lines.map(l => {
                    const cls = slColorize(l);
                    const escaped = l.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    return cls ? `<span class="${cls}">${escaped}</span>` : escaped;
                }).join('\\n');
                serverLogDiv.scrollTop = serverLogDiv.scrollHeight;
            }).catch(() => {});
        }

        function updateTokens(usage, profile) {
            if (!usage) return;
            const fmt = n => n >= 1000 ? (n/1000).toFixed(1) + 'k' : n;
            const t = usage.total_tokens || 0;

            // Build profile breakdown if available
            let breakdown = '';
            if (profile) {
                const totals = {decide: {i:0,o:0}, extract: {i:0,o:0}, reflect: {i:0,o:0}};
                for (const [aid, p] of Object.entries(profile)) {
                    for (const ct of ['decide','extract','reflect']) {
                        if (p[ct]) { totals[ct].i += p[ct].input; totals[ct].o += p[ct].output; }
                    }
                }
                const parts = [];
                for (const [ct, v] of Object.entries(totals)) {
                    const sum = v.i + v.o;
                    if (sum > 0) parts.push(`${ct}:${fmt(v.i)}`);
                }
                if (parts.length) breakdown = ' [' + parts.join(' ') + ']';
            }

            tokenDiv.textContent = `Tokens: ${fmt(t)}${breakdown}`;
        }
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        const btnPause = document.getElementById('btn-pause');
        const btnResume = document.getElementById('btn-resume');
        const btnStep = document.getElementById('btn-step');
        let isPaused = false;

        function setButtonState(paused) {
            isPaused = paused;
            btnPause.disabled = paused;
            btnResume.disabled = !paused;
            btnStep.disabled = !paused;
            if (paused) btnPause.classList.remove('active');
            else btnPause.classList.add('active');
        }

        function simPause() {
            fetch('/api/pause', {method:'POST'}).then(() => {
                setButtonState(true);
                statusDiv.textContent = 'Paused';
                statusDiv.style.color = '#e3b341';
            });
        }
        function simResume() {
            fetch('/api/resume', {method:'POST'}).then(() => {
                setButtonState(false);
                statusDiv.textContent = 'Running...';
                statusDiv.style.color = '#3fb950';
            });
        }
        function simStep() {
            statusDiv.textContent = 'Stepping...';
            statusDiv.style.color = '#58a6ff';
            fetch('/api/step', {method:'POST'}).then(() => {
                statusDiv.textContent = 'Paused (after step)';
                statusDiv.style.color = '#e3b341';
            });
        }
        function simSave() {
            fetch('/api/save', {method:'POST'}).then(r => r.json()).then(d => {
                statusDiv.textContent = `Saved: ${d.name} (id=${d.save_id})`;
                statusDiv.style.color = '#3fb950';
            });
        }
        const saveListDiv = document.getElementById('save-list');
        let saveListOpen = false;
        function toggleSaveList() {
            saveListOpen = !saveListOpen;
            if (saveListOpen) {
                refreshSaveList();
                saveListDiv.style.display = 'block';
            } else {
                saveListDiv.style.display = 'none';
            }
        }
        function refreshSaveList() {
            fetch('/api/saves').then(r => r.json()).then(d => {
                if (!d.saves || d.saves.length === 0) {
                    saveListDiv.innerHTML = '<div style="color:#8b949e">No saves yet</div>';
                    return;
                }
                saveListDiv.innerHTML = d.saves.map(s => `
                    <div class="save-entry">
                        <div>
                            <span class="save-name">${s.name}</span>
                            <span class="save-info"> — ${s.scenario} — ${s.created_at.slice(0,19)}</span>
                        </div>
                        <div>
                            <button onclick="simLoad(${s.id})">Load</button>
                            <button class="del" onclick="simDelete(${s.id})">Del</button>
                        </div>
                    </div>
                `).join('');
            });
        }
        function simLoad(saveId) {
            fetch('/api/load/' + saveId, {method:'POST'}).then(r => r.json()).then(d => {
                statusDiv.textContent = `Loaded: ${d.name} (tick ${d.tick})`;
                statusDiv.style.color = '#58a6ff';
                setButtonState(true);
                saveListDiv.style.display = 'none';
                saveListOpen = false;
            });
        }
        function simDelete(saveId) {
            fetch('/api/saves/' + saveId, {method:'DELETE'}).then(() => refreshSaveList());
        }
        function simReset() {
            if (!confirm('Reset the game? All unsaved progress will be lost.')) return;
            fetch('/api/reset', {method:'POST'}).then(r => r.json()).then(d => {
                statusDiv.textContent = `Game reset (${d.scenario}) — press Resume or Step`;
                statusDiv.style.color = '#e3b341';
                setButtonState(true);
                storyCards.length = 0;
                cardIndex = -1;
                autoFollow = true;
                currentCard.innerHTML = '<div class="chapter-num">Waiting for first tick...</div>';
                updateNav();
                eventsDiv.innerHTML = '';
                tokenDiv.textContent = 'Tokens: 0';
            });
        }

        // --- Map Creator (Reverse Architect) ---
        const creatorOverlay = document.getElementById('creator-overlay');
        const creatorStatus = document.getElementById('creator-status');
        let lastPreviewData = null;

        const ENDING_BADGES = {
            good: {icon:'\\u{1F3C6}', label:'Good', color:'#22c55e'},
            bad: {icon:'\\u{1F480}', label:'Bad', color:'#ef4444'},
            secret: {icon:'\\u{1F31F}', label:'Secret', color:'#f59e0b'},
            true_: {icon:'\\u{1F52E}', label:'True', color:'#a855f7'},
        };

        function toggleCreator() {
            const o = creatorOverlay;
            o.style.display = o.style.display === 'none' ? 'block' : 'none';
            if (o.style.display === 'block') loadPresets();
        }

        function loadPresets() {
            fetch('/api/presets').then(r=>r.json()).then(d => {
                const div = document.getElementById('preset-buttons');
                div.innerHTML = Object.entries(d.presets).map(([k,v]) =>
                    `<button onclick="selectPreset('${k}')" style="background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:4px;padding:3px 8px;cursor:pointer;font-family:monospace;font-size:10px;">${v.builder.split(' ').pop()} (${v.difficulty})</button>`
                ).join('');
            });
            updateEndingPreview();
        }

        function selectPreset(name) {
            fetch('/api/presets').then(r=>r.json()).then(d => {
                const p = d.presets[name];
                if (!p) return;
                document.getElementById('arc-builder').value = p.builder;
                document.getElementById('arc-goal').value = p.goal;
                document.getElementById('arc-background').value = p.background;
                document.getElementById('arc-difficulty').value = p.difficulty;
                updateEndingPreview();
                creatorStatus.textContent = `Loaded preset: ${name}`;
                creatorStatus.style.color = '#3fb950';
            });
        }

        function updateEndingPreview() {
            const diff = parseInt(document.getElementById('arc-difficulty').value);
            const endings = ['good','bad'];
            if (diff >= 3) endings.push('secret');
            if (diff >= 4) endings.push('true_');
            const div = document.getElementById('ending-preview');
            div.innerHTML = endings.map(e => {
                const b = ENDING_BADGES[e];
                return `<span style="background:${b.color}22;color:${b.color};border:1px solid ${b.color}44;border-radius:3px;padding:1px 6px;font-size:10px;font-family:monospace;">${b.icon} ${b.label}</span>`;
            }).join('');
        }

        function getStoryInput() {
            return {
                builder: document.getElementById('arc-builder').value.trim() || 'Mystery Builder',
                goal: document.getElementById('arc-goal').value.trim() || 'Hidden Treasure',
                background: document.getElementById('arc-background').value.trim() || 'A mysterious place',
                difficulty: parseInt(document.getElementById('arc-difficulty').value),
            };
        }

        function previewMap() {
            const story = getStoryInput();
            creatorStatus.textContent = 'Generating preview...';
            creatorStatus.style.color = '#58a6ff';

            fetch('/api/preview-architect', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify(story),
            }).then(r=>r.json()).then(d => {
                if (d.error) {
                    creatorStatus.textContent = 'Error: ' + d.error;
                    creatorStatus.style.color = '#f85149';
                    return;
                }
                lastPreviewData = d;
                showPreview(d);
                creatorStatus.textContent = `Preview: ${d.stats.total_nodes} puzzles, ${d.stats.endings} endings, ${d.stats.forks} forks`;
                creatorStatus.style.color = '#3fb950';
                document.getElementById('btn-preview').style.display = 'none';
                document.getElementById('btn-regenerate').style.display = 'block';
                document.getElementById('btn-play-map').style.display = 'block';
            }).catch(e => {
                creatorStatus.textContent = 'Error: ' + e;
                creatorStatus.style.color = '#f85149';
            });
        }

        function showPreview(data) {
            const container = document.getElementById('preview-container');
            container.style.display = 'block';

            // Stats
            const s = data.stats;
            document.getElementById('preview-stats').innerHTML =
                `<span style="color:#58a6ff;font-family:monospace;font-size:11px;">${s.total_nodes} nodes</span>` +
                `<span style="color:#3fb950;font-family:monospace;font-size:11px;">${s.total_edges} edges</span>` +
                `<span style="color:#e3b341;font-family:monospace;font-size:11px;">${s.endings} endings</span>` +
                `<span style="color:#d2a8ff;font-family:monospace;font-size:11px;">${s.forks} forks</span>` +
                `<span style="color:#8b949e;font-family:monospace;font-size:11px;">${s.entrances} entrances</span>`;

            // Endings
            document.getElementById('preview-endings').innerHTML = data.endings.map(e => {
                const b = ENDING_BADGES[e.key] || {icon:'?',color:'#8b949e'};
                return `<div style="display:inline-flex;align-items:center;gap:4px;margin-right:10px;font-family:monospace;font-size:11px;">` +
                    `<span style="color:${b.color}">${b.icon} ${e.label}</span>` +
                    `<span style="color:#8b949e">(${e.chain_length} steps)</span></div>`;
            }).join('');

            // SVG Graph
            renderPreviewGraph(data.nodes, data.edges);
        }

        function renderPreviewGraph(nodes, edges) {
            if (!nodes.length) return;
            const xs = nodes.map(n=>n.x), ys = nodes.map(n=>n.y);
            const minX = Math.min(...xs)-40, maxX = Math.max(...xs)+40;
            const minY = Math.min(...ys)-40, maxY = Math.max(...ys)+40;
            const w = maxX-minX, h = maxY-minY;

            let svg = `<svg viewBox="${minX} ${minY} ${w} ${h}" style="width:100%;height:auto;max-height:250px;">`;

            // Edges
            for (const e of edges) {
                const from = nodes.find(n=>n.id===e.from);
                const to = nodes.find(n=>n.id===e.to);
                if (!from || !to) continue;
                const color = e.color || '#30363d';
                const dash = e.is_branch ? '6,3' : '4,3';
                const sw = e.is_branch ? 2.5 : 1.5;
                svg += `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" stroke="${color}" stroke-width="${sw}" stroke-dasharray="${dash}" opacity="0.6"/>`;
            }

            // Nodes
            const typeIcons = {lock:'\\u{1F512}',cipher:'\\u{1F522}',hidden:'\\u{1F50D}',mechanism:'\\u{2699}',riddle:'\\u{1F4AC}',trap:'\\u{26A0}',key:'\\u{1F511}'};
            for (const n of nodes) {
                const r = n.is_goal ? 18 : n.is_fork ? 14 : n.is_entrance ? 12 : 10;
                const fill = n.path_color || '#30363d';
                const stroke = n.is_goal ? '#fff' : n.is_entrance ? '#3fb950' : 'none';
                svg += `<circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${stroke!=='none'?2:0}" opacity="0.8"/>`;
                const icon = n.is_goal ? (ENDING_BADGES[n.ending_type]||{}).icon||'\\u{2B50}' : n.is_fork ? '\\u{1F500}' : typeIcons[n.type] || '\\u{2022}';
                svg += `<text x="${n.x}" y="${n.y+4}" text-anchor="middle" font-size="${r*0.9}" fill="#fff">${icon}</text>`;
                if (n.is_entrance) svg += `<text x="${n.x}" y="${n.y-r-4}" text-anchor="middle" font-size="8" fill="#3fb950">START</text>`;
            }
            svg += '</svg>';
            document.getElementById('preview-graph').innerHTML = svg;
        }

        function playPreviewedMap() {
            if (!lastPreviewData) return;
            const story = lastPreviewData.story;
            creatorStatus.textContent = 'Building playable world...';
            creatorStatus.style.color = '#58a6ff';

            fetch('/api/generate-architect', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify(story),
            }).then(r=>r.json()).then(d => {
                if (d.error) {
                    creatorStatus.textContent = 'Error: ' + d.error;
                    creatorStatus.style.color = '#f85149';
                    return;
                }
                creatorStatus.textContent = `Loaded! ${d.rooms}R ${d.doors}D ${d.endings} endings — press Resume`;
                creatorStatus.style.color = '#3fb950';
                storyCards.length = 0; cardIndex = -1; autoFollow = true;
                currentCard.innerHTML = '<div class="chapter-num">Map loaded — press Resume to play!</div>';
                updateNav(); eventsDiv.innerHTML = ''; tokenDiv.textContent = 'Tokens: 0';
                setButtonState(true);
                statusDiv.textContent = 'New map ready — press Resume or Step';
                statusDiv.style.color = '#e3b341';
                setTimeout(() => { creatorOverlay.style.display = 'none'; }, 1500);
            });
        }

        ws.onopen = () => {
            statusDiv.textContent = 'Paused — press Resume or Step to begin';
            statusDiv.style.color = '#e3b341';
            setButtonState(true);
        };
        ws.onclose = () => {
            statusDiv.textContent = 'Disconnected — game still running. Refresh to reconnect.';
            statusDiv.style.color = '#f85149';
            btnPause.disabled = true;
            btnResume.disabled = true;
            btnStep.disabled = true;
            // Auto-reconnect after 3s
            setTimeout(() => { location.reload(); }, 5000);
        };

        // Escape chain — dynamically set from server
        let escapeChain = [];

        // Puzzle annotations for rooms
        const ROOM_PUZZLES = {
            'start':    'Clues: Note, Book',
            'workshop': 'Puzzles: Lock+Key, Combo Lock',
            'vault':    'Puzzles: Pressure Plate, Levers',
            'sanctum':  'Puzzles: Password, Brazier',
            'hallway':  'Exit: Iron Door',
            'library':  'Clues: Code Note, Hint Book',
            'lab':      'Puzzles: Lock Box, Trial',
        };

        // Agent colors
        const AGENT_COLORS = ['#58a6ff', '#f78166', '#3fb950', '#d2a8ff'];

        function updateMap(ws_data) {
            if (!ws_data) return;
            const rooms = ws_data.rooms || {};
            const agents = ws_data.agents || {};
            const doors = ws_data.doors || {};

            // Auto-layout: assign positions to rooms in a grid
            const roomIds = Object.keys(rooms);
            const positions = autoLayout(roomIds, rooms, doors);

            // Compute SVG bounds
            const allX = Object.values(positions).map(p => p.x);
            const allY = Object.values(positions).map(p => p.y);
            const pad = 80;
            const minX = Math.min(...allX) - pad, maxX = Math.max(...allX) + pad;
            const minY = Math.min(...allY) - pad, maxY = Math.max(...allY) + pad;
            const w = maxX - minX, h = maxY - minY;

            // Agent lookup
            const agentsByRoom = {};
            const agentList = Object.values(agents);
            for (const a of agentList) {
                if (!agentsByRoom[a.room_id]) agentsByRoom[a.room_id] = [];
                agentsByRoom[a.room_id].push(a);
            }

            let svg = `<svg viewBox="${minX - 10} ${minY - 10} ${w + 20} ${h + 20}" xmlns="http://www.w3.org/2000/svg">`;
            svg += `<defs>
                <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
                    <path d="M 0 0 L 10 3 L 0 6 z" fill="#484f58"/>
                </marker>
            </defs>`;

            // Draw edges (doors)
            const drawnDoors = new Set();
            for (const [rid, room] of Object.entries(rooms)) {
                const p1 = positions[rid];
                if (!p1) continue;
                for (const [dir, did] of Object.entries(room.doors || {})) {
                    if (drawnDoors.has(did)) continue;
                    drawnDoors.add(did);
                    const door = doors[did];
                    if (!door) continue;
                    const otherRid = door.room_a === rid ? door.room_b : door.room_a;
                    const p2 = positions[otherRid];
                    if (!p2) continue;

                    const locked = door.locked;
                    const edgeColor = locked ? '#f85149' : '#3fb950';
                    const dashArray = locked ? '6,4' : 'none';
                    const lockIcon = locked ? '\\u{1F512}' : '\\u{1F513}';

                    // Shorten line so it doesn't overlap node
                    const dx = p2.x - p1.x, dy = p2.y - p1.y;
                    const len = Math.sqrt(dx*dx + dy*dy);
                    const nx = dx/len, ny = dy/len;
                    const r = 40;
                    const x1 = p1.x + nx*r, y1 = p1.y + ny*r;
                    const x2 = p2.x - nx*r, y2 = p2.y - ny*r;
                    const mx = (p1.x + p2.x)/2, my = (p1.y + p2.y)/2;

                    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${edgeColor}" stroke-width="2" stroke-dasharray="${dashArray}" opacity="0.7"/>`;
                    svg += `<text x="${mx}" y="${my - 6}" text-anchor="middle" font-size="12" fill="${edgeColor}">${lockIcon}</text>`;
                    svg += `<text x="${mx}" y="${my + 10}" text-anchor="middle" font-size="8" font-family="monospace" fill="#484f58">${door.name}</text>`;
                }
            }

            // Draw room nodes
            for (const [rid, room] of Object.entries(rooms)) {
                const p = positions[rid];
                if (!p) continue;
                const hasAgent = !!agentsByRoom[rid];
                const stroke = hasAgent ? '#58a6ff' : '#30363d';
                const fill = hasAgent ? '#161b22' : '#0d1117';

                svg += `<rect x="${p.x - 55}" y="${p.y - 30}" width="110" height="60" rx="8" fill="${fill}" stroke="${stroke}" stroke-width="${hasAgent ? 2 : 1}"/>`;
                svg += `<text x="${p.x}" y="${p.y - 12}" text-anchor="middle" font-size="11" font-weight="bold" font-family="monospace" fill="#e6edf3">${room.name}</text>`;

                // Puzzle annotation
                const note = ROOM_PUZZLES[rid] || '';
                if (note) {
                    svg += `<text x="${p.x}" y="${p.y + 3}" text-anchor="middle" font-size="8" font-family="monospace" fill="#8b949e">${note}</text>`;
                }

                // Agents in this room
                const roomAgents = agentsByRoom[rid] || [];
                roomAgents.forEach((a, i) => {
                    const color = AGENT_COLORS[agentList.indexOf(a) % AGENT_COLORS.length];
                    const ax = p.x - 20 + i * 25;
                    const ay = p.y + 18;
                    svg += `<circle cx="${ax}" cy="${ay}" r="7" fill="${color}" opacity="0.9"/>`;
                    svg += `<text x="${ax}" y="${ay + 3}" text-anchor="middle" font-size="7" font-weight="bold" fill="#0d1117">${a.name[0]}</text>`;
                });
            }

            svg += '</svg>';
            sceneDiv.innerHTML = svg;
        }

        function autoLayout(roomIds, rooms, doors) {
            // Force-directed layout: repulsion between all nodes, attraction along edges
            const pos = {};
            const n = roomIds.length;
            if (n === 0) return pos;

            // Build adjacency
            const adj = {};
            for (const rid of roomIds) adj[rid] = new Set();
            for (const door of Object.values(doors)) {
                if (adj[door.room_a] && adj[door.room_b]) {
                    adj[door.room_a].add(door.room_b);
                    adj[door.room_b].add(door.room_a);
                }
            }

            // Initialize positions in a circle
            const cx = n * 40, cy = n * 30;
            const radius = Math.max(80, n * 25);
            for (let i = 0; i < n; i++) {
                const angle = (2 * Math.PI * i) / n;
                pos[roomIds[i]] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
            }

            // Force simulation (50 iterations)
            const repulsion = 8000;
            const attraction = 0.02;
            const idealDist = 160;

            for (let iter = 0; iter < 50; iter++) {
                const forces = {};
                for (const rid of roomIds) forces[rid] = { fx: 0, fy: 0 };

                // Repulsion: every pair pushes apart
                for (let i = 0; i < n; i++) {
                    for (let j = i + 1; j < n; j++) {
                        const a = roomIds[i], b = roomIds[j];
                        let dx = pos[a].x - pos[b].x;
                        let dy = pos[a].y - pos[b].y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                        const force = repulsion / (dist * dist);
                        const fx = (dx / dist) * force;
                        const fy = (dy / dist) * force;
                        forces[a].fx += fx; forces[a].fy += fy;
                        forces[b].fx -= fx; forces[b].fy -= fy;
                    }
                }

                // Attraction: connected nodes pull together toward ideal distance
                for (const rid of roomIds) {
                    for (const neighbor of adj[rid]) {
                        let dx = pos[neighbor].x - pos[rid].x;
                        let dy = pos[neighbor].y - pos[rid].y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                        const force = attraction * (dist - idealDist);
                        forces[rid].fx += (dx / dist) * force;
                        forces[rid].fy += (dy / dist) * force;
                    }
                }

                // Apply forces with damping
                const damping = 0.85 - iter * 0.01;
                for (const rid of roomIds) {
                    pos[rid].x += forces[rid].fx * damping;
                    pos[rid].y += forces[rid].fy * damping;
                }
            }

            // Normalize: shift so minimum is at (0, 0)
            let minX = Infinity, minY = Infinity;
            for (const rid of roomIds) {
                if (pos[rid].x < minX) minX = pos[rid].x;
                if (pos[rid].y < minY) minY = pos[rid].y;
            }
            for (const rid of roomIds) {
                pos[rid].x -= minX;
                pos[rid].y -= minY;
            }

            return pos;
        }

        function updatePuzzles(ws_data, chain) {
            // Use escape chain if available
            if (chain && chain.length > 0) {
                escapeChain = chain;
            }
            if (escapeChain.length === 0) {
                puzzleDiv.innerHTML = '<div style="color:#8b949e">No escape chain (use Create to generate one)</div>';
                return;
            }

            const icons = {examine:'\\u{1F50D}', reveal:'\\u{2728}', solve:'\\u{1F9E9}', unlock:'\\u{1F513}', escape:'\\u{1F6AA}'};
            let html = '';
            const completed = escapeChain.filter(s => s.status === 'complete').length;
            const total = escapeChain.length;
            html += `<div style="color:#8b949e;font-size:10px;margin-bottom:6px;">${completed}/${total} steps complete</div>`;

            for (const step of escapeChain) {
                const icon = icons[step.action] || '\\u{2022}';
                const status = step.status === 'complete' ? 'solved' : 'locked';
                const statusText = step.status === 'complete' ? 'DONE' : 'PENDING';
                html += `<div class="puzzle-row">
                    <span class="puzzle-icon">${icon}</span>
                    <span class="puzzle-name" style="font-size:10px">${step.step}. ${step.description}</span>
                    <span class="puzzle-status ${status}">${statusText}</span>
                </div>`;
            }
            puzzleDiv.innerHTML = html;
        }

        function updateAgents(ws_data) {
            if (!ws_data) return;
            const agents = ws_data.agents || {};
            const rooms = ws_data.rooms || {};
            let html = '';
            for (const a of Object.values(agents)) {
                const roomName = rooms[a.room_id] ? rooms[a.room_id].name : a.room_id;
                const inv = (a.inventory || []).map(i => i.name);
                const invStr = inv.length
                    ? `<div class="agent-inv">\\u{1F392} ${inv.join(', ')}</div>`
                    : `<div class="agent-inv-empty">\\u{1F392} empty</div>`;
                html += `<div class="agent-card">
                    <div class="agent-name">\\u{1F464} ${a.name}</div>
                    <div class="agent-location">\\u{1F4CD} ${roomName}</div>
                    ${invStr}
                </div>`;
            }
            agentDiv.innerHTML = html;
        }

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);

            if (msg.type === 'tick' || msg.type === 'snapshot') {
                // Update status panels
                if (msg.world_state) {
                    updateMap(msg.world_state);
                    updatePuzzles(msg.world_state, msg.escape_chain);
                    updateAgents(msg.world_state);
                }
                // Update token counter
                if (msg.token_usage) {
                    updateTokens(msg.token_usage, msg.token_profile);
                }
                // Sync pause state on snapshot (reconnect)
                if (msg.type === 'snapshot' && msg.paused !== undefined) {
                    setButtonState(msg.paused);
                    if (msg.paused) {
                        statusDiv.textContent = `Paused at tick ${msg.tick} — press Resume or Step`;
                        statusDiv.style.color = '#e3b341';
                    }
                }
            }

            if (msg.type === 'tick') {
                // Add story card
                addCard({
                    tick: msg.tick,
                    narrative: msg.narrative || '',
                    events: msg.events || [],
                    agents: msg.world_state ? msg.world_state.agents : {},
                    rooms: msg.world_state ? msg.world_state.rooms : {},
                    finished: false,
                });
                // Event log
                const group = document.createElement('div');
                group.className = 'tick-group';
                group.innerHTML = `<div class="tick-label">Tick ${msg.tick}</div>`;
                msg.events.forEach(ev => {
                    const div = document.createElement('div');
                    div.className = `event ${ev.type}`;
                    div.textContent = ev.description;
                    group.appendChild(div);
                });
                eventsDiv.appendChild(group);
                eventsDiv.scrollTop = eventsDiv.scrollHeight;
            } else if (msg.type === 'processing') {
                statusDiv.textContent = msg.message || 'Processing...';
                statusDiv.style.color = '#58a6ff';
            } else if (msg.type === 'paused') {
                setButtonState(true);
                statusDiv.textContent = `Paused at tick ${msg.tick}`;
                statusDiv.style.color = '#e3b341';
            } else if (msg.type === 'finished') {
                addCard({
                    tick: msg.tick || storyCards.length,
                    narrative: msg.narrative || msg.reason,
                    events: [],
                    agents: {},
                    rooms: {},
                    finished: true,
                });
                const div = document.createElement('div');
                div.className = 'event state_change';
                div.style.fontWeight = 'bold';
                div.textContent = msg.reason;
                eventsDiv.appendChild(div);
                btnPause.disabled = true;
                btnResume.disabled = true;
                btnStep.disabled = true;
                statusDiv.textContent = 'Simulation complete';
                statusDiv.style.color = '#3fb950';
            }
        };
    </script>
</body>
</html>
"""
