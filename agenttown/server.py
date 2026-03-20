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

from agenttown.main import RandomBrain, run_simulation
from agenttown.scenarios.escape_room import build_escape_room
from agenttown.world.events import Event
from agenttown.world.world import World

logger = logging.getLogger(__name__)

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
        from agenttown.agents.brain import ClaudeBrain
        sim_world = World.from_full_snapshot(latest["world_snapshot"])
        sim_brains = {
            aid: ClaudeBrain.from_snapshot(bdata)
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
            logger.info("Loaded scenario: escape_room")

        if use_claude:
            from agenttown.agents.brain import ClaudeBrain
            sim_brains = {aid: ClaudeBrain() for aid in agent_ids}
            logger.info("Using Claude Haiku brains")
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
        agents = list(sim_world.state.agents.values())
        perceptions = {a.id: sim_world.perceive(a) for a in agents}

        decisions = await asyncio.gather(*[
            sim_brains[a.id].decide(a, perceptions[a.id]) for a in agents
        ])

        tick_events: list[Event] = []
        for agent, action in zip(agents, decisions):
            events = sim_world.process_action(action, agent)
            tick_events.extend(events)

        narrative = ""
        if narrator and tick_events:
            narrative = narrator.narrate(tick_events, sim_world.state, sim_world.tick)

        await broadcast({
            "type": "tick",
            "tick": sim_world.tick,
            "events": [
                {"type": e.event_type, "description": e.description, "room": e.room_id}
                for e in tick_events
            ],
            "narrative": narrative,
            "world_state": sim_world.snapshot(),
        })

        sim_world.advance_tick()

        if sim_world.finished:
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
        """Tick loop with pause/resume/step support. Starts paused."""
        global sim_paused
        sim_paused = True  # start paused — user must press Resume or Step
        while not sim_world.finished and sim_world.tick < 200:
            if sim_paused:
                # Wait for a step signal or unpause
                sim_step_event.clear()
                await broadcast({"type": "paused", "tick": sim_world.tick})
                await sim_step_event.wait()
                if sim_paused:
                    # Single step — run one tick then stay paused
                    await run_one_tick()
                    continue
            await run_one_tick()
            if not sim_world.finished:
                await asyncio.sleep(1.0)

    sim_task = asyncio.create_task(sim_loop())
    yield
    if sim_task and not sim_task.done():
        sim_task.cancel()


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
        _auto_pause_if_no_clients()


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

    from agenttown.agents.brain import ClaudeBrain
    sim_world = World.from_full_snapshot(data["world_snapshot"])
    sim_brains.clear()
    sim_brains.update({
        aid: ClaudeBrain.from_snapshot(bdata)
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


DASHBOARD_HTML = """\
<!DOCTYPE html>
<html>
<head>
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
        #story { flex: 1; overflow-y: auto; }
        .narrative-block {
            margin-bottom: 16px; padding: 12px; background: #161b22;
            border-left: 3px solid #e3b341; border-radius: 0 6px 6px 0;
            line-height: 1.7; font-size: 14px;
        }
        .narrative-block .chapter { color: #8b949e; font-size: 10px; font-family: monospace; margin-bottom: 6px; }
        .narrative-block p { color: #e6edf3; }
        .finished-narrative {
            margin-top: 16px; padding: 16px; background: #0d2818;
            border-left: 3px solid #3fb950; border-radius: 0 6px 6px 0;
            font-size: 16px; color: #3fb950; line-height: 1.7;
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

        /* Event log */
        #log-panel {
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 11px;
        }
        #log-panel h2 { color: #58a6ff; font-size: 13px; margin-bottom: 8px; }
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
            body { flex-direction: column; }
            #story-panel { border-right: none; border-bottom: 1px solid #21262d; max-height: 50vh; }
            #right-panel { max-height: 50vh; }
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
            <span id="status">Connecting...</span>
        </div>
        <div id="save-list" style="display:none; margin-bottom: 12px;"></div>
        <div id="story"></div>
    </div>
    <div id="right-panel">
        <div id="map-panel">
            <h2>SCENE VIEW</h2>
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
            <h2>EVENT LOG</h2>
            <div id="events"></div>
        </div>
    </div>
    <script>
        const storyDiv = document.getElementById('story');
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        const sceneDiv = document.getElementById('scene-graph');
        const puzzleDiv = document.getElementById('puzzle-list');
        const agentDiv = document.getElementById('agent-list');
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

        ws.onopen = () => {
            statusDiv.textContent = 'Paused — press Resume or Step to begin';
            statusDiv.style.color = '#e3b341';
            setButtonState(true);
        };
        ws.onclose = () => {
            statusDiv.textContent = 'Disconnected';
            statusDiv.style.color = '#f85149';
            btnPause.disabled = true;
            btnResume.disabled = true;
            btnStep.disabled = true;
        };

        // Pause when user switches tabs or minimizes
        document.addEventListener('visibilitychange', () => {
            if (document.hidden && !isPaused) {
                simPause();
            }
        });

        // Pause when window loses focus
        window.addEventListener('blur', () => {
            if (!isPaused) {
                simPause();
            }
        });

        // Puzzle definitions — which entities are puzzles and how to label them
        const PUZZLE_DEFS = {
            'brass_key':   { icon: '\\u{1F511}', name: 'Key + Lock (Steel Door)', checkDoor: 'door_workshop_vault' },
            'puzzle_box':  { icon: '\\u{1F4E6}', name: 'Combination Lock (Puzzle Box)', checkState: true },
            'pressure_plate': { icon: '\\u{2B07}', name: 'Pressure Plate (Hidden Panel)', checkDoor: 'door_workshop_sanctum' },
            'archway':     { icon: '\\u{2728}', name: 'Password Door (Archway)', checkDoor: 'door_sanctum_hallway' },
            'lever_controller': { icon: '\\u{1F579}', name: 'Sequential Levers (Gate)', checkDoor: 'door_vault_hallway_secret' },
        };

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
            // Use door connections to build a graph, then do a BFS layout
            const adj = {};
            const dirOffset = {
                east: [160, 0], west: [-160, 0],
                south: [0, 120], north: [0, -120],
            };
            for (const rid of roomIds) adj[rid] = [];
            for (const door of Object.values(doors)) {
                const room = rooms[door.room_a];
                if (!room) continue;
                // Find direction
                for (const [dir, did] of Object.entries(room.doors || {})) {
                    if (did === door.id) {
                        adj[door.room_a].push({ to: door.room_b, dir });
                        const rev = {east:'west',west:'east',north:'south',south:'north'}[dir] || dir;
                        adj[door.room_b].push({ to: door.room_a, dir: rev });
                        break;
                    }
                }
            }

            const positions = {};
            const visited = new Set();
            const queue = [{ id: roomIds[0], x: 0, y: 0 }];
            positions[roomIds[0]] = { x: 0, y: 0 };
            visited.add(roomIds[0]);

            while (queue.length > 0) {
                const cur = queue.shift();
                for (const edge of (adj[cur.id] || [])) {
                    if (visited.has(edge.to)) continue;
                    visited.add(edge.to);
                    const off = dirOffset[edge.dir] || [160, 0];
                    const nx = cur.x + off[0], ny = cur.y + off[1];
                    positions[edge.to] = { x: nx, y: ny };
                    queue.push({ id: edge.to, x: nx, y: ny });
                }
            }

            // Place any unvisited rooms (disconnected)
            let ox = 0;
            for (const rid of roomIds) {
                if (!positions[rid]) {
                    positions[rid] = { x: ox, y: 200 };
                    ox += 160;
                }
            }

            return positions;
        }

        function updatePuzzles(ws_data) {
            if (!ws_data) return;
            const rooms = ws_data.rooms || {};
            const doors = ws_data.doors || {};
            let html = '';

            for (const [eid, def] of Object.entries(PUZZLE_DEFS)) {
                let status = 'locked';
                let statusText = 'UNSOLVED';

                // Find entity across all rooms
                for (const room of Object.values(rooms)) {
                    const entity = (room.entities || {})[eid];
                    if (!entity) continue;

                    if (entity.state === 'solved') {
                        status = 'solved';
                        statusText = 'SOLVED';
                    } else if (entity.state === 'activated') {
                        status = 'partial';
                        statusText = 'IN PROGRESS';
                    }

                    // Check lever progress
                    if (eid === 'lever_controller' && entity.properties) {
                        const progress = entity.properties.progress || [];
                        const sequence = entity.properties.sequence || [];
                        if (progress.length > 0 && entity.state !== 'solved') {
                            status = 'partial';
                            statusText = `${progress.length}/${sequence.length} LEVERS`;
                        }
                    }
                    break;
                }

                // Also check via door state
                if (def.checkDoor && doors[def.checkDoor]) {
                    if (!doors[def.checkDoor].locked) {
                        status = 'solved';
                        statusText = 'SOLVED';
                    }
                }

                // Check if brass_key was picked up (not in room anymore)
                if (eid === 'brass_key') {
                    let found = false;
                    for (const room of Object.values(rooms)) {
                        if ((room.entities || {})[eid]) { found = true; break; }
                    }
                    if (!found && doors['door_workshop_vault'] && !doors['door_workshop_vault'].locked) {
                        status = 'solved';
                        statusText = 'SOLVED';
                    } else if (!found) {
                        status = 'partial';
                        statusText = 'KEY FOUND';
                    }
                }

                html += `<div class="puzzle-row">
                    <span class="puzzle-icon">${def.icon}</span>
                    <span class="puzzle-name">${def.name}</span>
                    <span class="puzzle-status ${status}">${statusText}</span>
                </div>`;
            }

            // Torch combination check
            let torchStatus = 'locked', torchText = 'UNSOLVED';
            for (const a of Object.values(ws_data.agents || {})) {
                for (const item of (a.inventory || [])) {
                    if (item.name === 'Makeshift Torch') { torchStatus = 'solved'; torchText = 'CRAFTED'; }
                    if (item.name === 'Cloth Rag' || item.name === 'Wooden Stick') {
                        if (torchStatus !== 'solved') { torchStatus = 'partial'; torchText = 'PARTS FOUND'; }
                    }
                }
            }
            html += `<div class="puzzle-row">
                <span class="puzzle-icon">\\u{1F525}</span>
                <span class="puzzle-name">Item Combine (Torch)</span>
                <span class="puzzle-status ${torchStatus}">${torchText}</span>
            </div>`;

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
                    updatePuzzles(msg.world_state);
                    updateAgents(msg.world_state);
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
                // Narrative
                if (msg.narrative) {
                    const block = document.createElement('div');
                    block.className = 'narrative-block';
                    block.innerHTML = `<div class="chapter">Chapter ${msg.tick + 1}</div><p>${msg.narrative.replace(/\\n/g, '<br>')}</p>`;
                    storyDiv.appendChild(block);
                    storyDiv.scrollTop = storyDiv.scrollHeight;
                }
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
            } else if (msg.type === 'paused') {
                setButtonState(true);
                statusDiv.textContent = `Paused at tick ${msg.tick}`;
                statusDiv.style.color = '#e3b341';
            } else if (msg.type === 'finished') {
                const block = document.createElement('div');
                block.className = 'finished-narrative';
                block.innerHTML = msg.narrative || msg.reason;
                storyDiv.appendChild(block);
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
