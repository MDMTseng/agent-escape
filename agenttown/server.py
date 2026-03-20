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
    """Start simulation on server startup."""
    global sim_world, sim_task
    sim_world, agent_ids = build_escape_room()

    use_claude = os.environ.get("AGENTTOWN_CLAUDE", "").lower() in ("1", "true", "yes")
    if use_claude:
        from agenttown.agents.brain import ClaudeBrain
        brains = {aid: ClaudeBrain() for aid in agent_ids}
        logger.info("Using Claude Haiku brains")
    else:
        brains = {aid: RandomBrain() for aid in agent_ids}
        logger.info("Using random brains")

    # Narrator — transforms events into story prose
    narrator = None
    use_narrator = os.environ.get("AGENTTOWN_NARRATOR", "").lower() in ("1", "true", "yes")
    if use_narrator:
        from agenttown.agents.narrator import Narrator
        narrator = Narrator()
        logger.info("Narrator enabled")

    async def sim_loop():
        """Tick loop that broadcasts state to WebSocket clients."""
        while not sim_world.finished and sim_world.tick < 200:
            agents = list(sim_world.state.agents.values())
            perceptions = {a.id: sim_world.perceive(a) for a in agents}

            decisions = await asyncio.gather(*[
                brains[a.id].decide(a, perceptions[a.id]) for a in agents
            ])

            tick_events: list[Event] = []
            for agent, action in zip(agents, decisions):
                events = sim_world.process_action(action, agent)
                tick_events.extend(events)

            # Generate narrative prose
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
                break

            await asyncio.sleep(1.0)

    sim_task = asyncio.create_task(sim_loop())
    yield
    if sim_task and not sim_task.done():
        sim_task.cancel()


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
            "world_state": sim_world.snapshot(),
        }))

    try:
        while True:
            await ws.receive_text()  # keep alive, ignore client messages for now
    except WebSocketDisconnect:
        connected_clients.discard(ws)


@app.get("/")
async def index():
    return HTMLResponse(DASHBOARD_HTML)


@app.get("/api/state")
async def get_state():
    if sim_world:
        return sim_world.snapshot()
    return {"error": "No simulation running"}


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
        #status { color: #3fb950; margin-bottom: 12px; font-family: monospace; font-size: 11px; }
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

        /* Map panel */
        #map-panel {
            padding: 16px;
            border-bottom: 1px solid #21262d;
        }
        #map-panel h2 { color: #e3b341; font-size: 13px; margin-bottom: 10px; font-family: monospace; }
        #map-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .room-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 8px 10px;
            min-width: 120px;
            flex: 1;
            font-family: monospace;
            font-size: 11px;
            transition: border-color 0.3s;
        }
        .room-card.has-agent { border-color: #58a6ff; }
        .room-card .room-name { color: #e6edf3; font-weight: bold; font-size: 12px; margin-bottom: 4px; }
        .room-card .room-agents { color: #58a6ff; margin-bottom: 3px; }
        .room-card .room-agents .agent-icon { margin-right: 2px; }
        .room-card .room-items { color: #8b949e; font-size: 10px; }
        .room-card .room-doors { color: #484f58; font-size: 10px; margin-top: 3px; }
        .door-locked { color: #f85149; }
        .door-open { color: #3fb950; }

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
        <div id="status">Connecting...</div>
        <div id="story"></div>
    </div>
    <div id="right-panel">
        <div id="map-panel">
            <h2>ENVIRONMENT MAP</h2>
            <div id="map-container"></div>
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
        const mapDiv = document.getElementById('map-container');
        const puzzleDiv = document.getElementById('puzzle-list');
        const agentDiv = document.getElementById('agent-list');
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        ws.onopen = () => { statusDiv.textContent = 'Connected — watching simulation...'; };
        ws.onclose = () => { statusDiv.textContent = 'Disconnected'; statusDiv.style.color = '#f85149'; };

        // Puzzle definitions — which entities are puzzles and how to label them
        const PUZZLE_DEFS = {
            'brass_key':   { icon: '\\u{1F511}', name: 'Key + Lock (Steel Door)', checkDoor: 'door_workshop_vault' },
            'puzzle_box':  { icon: '\\u{1F4E6}', name: 'Combination Lock (Puzzle Box)', checkState: true },
            'pressure_plate': { icon: '\\u{2B07}', name: 'Pressure Plate (Hidden Panel)', checkDoor: 'door_workshop_sanctum' },
            'archway':     { icon: '\\u{2728}', name: 'Password Door (Archway)', checkDoor: 'door_sanctum_hallway' },
            'lever_controller': { icon: '\\u{1F579}', name: 'Sequential Levers (Gate)', checkDoor: 'door_vault_hallway_secret' },
        };

        function updateMap(ws_data) {
            if (!ws_data) return;
            const rooms = ws_data.rooms || {};
            const agents = ws_data.agents || {};
            const doors = ws_data.doors || {};

            // Build agent location lookup
            const agentsByRoom = {};
            for (const a of Object.values(agents)) {
                if (!agentsByRoom[a.room_id]) agentsByRoom[a.room_id] = [];
                agentsByRoom[a.room_id].push(a);
            }

            // Room display order
            const roomOrder = ['start', 'workshop', 'vault', 'sanctum', 'hallway'];
            let html = '';
            for (const rid of roomOrder) {
                const room = rooms[rid];
                if (!room) continue;
                const hasAgent = !!agentsByRoom[rid];
                const agentNames = (agentsByRoom[rid] || []).map(a =>
                    `<span class="agent-icon">\\u{1F464}</span>${a.name}`
                ).join(' ');

                // Visible items (skip hidden, skip lever_controller)
                const items = Object.values(room.entities || {})
                    .filter(e => e.state !== 'hidden' && e.id !== 'lever_controller')
                    .map(e => e.name)
                    .slice(0, 5);
                const itemsStr = items.length ? items.join(', ') : 'empty';

                // Doors from this room
                const doorInfo = Object.entries(room.doors || {}).map(([dir, did]) => {
                    const d = doors[did];
                    if (!d) return '';
                    const cls = d.locked ? 'door-locked' : 'door-open';
                    const icon = d.locked ? '\\u{1F512}' : '\\u{1F513}';
                    return `<span class="${cls}">${icon} ${dir}</span>`;
                }).join(' ');

                html += `<div class="room-card ${hasAgent ? 'has-agent' : ''}">
                    <div class="room-name">${room.name}</div>
                    ${agentNames ? `<div class="room-agents">${agentNames}</div>` : ''}
                    <div class="room-items">${itemsStr}</div>
                    <div class="room-doors">${doorInfo}</div>
                </div>`;
            }
            mapDiv.innerHTML = html;
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
            }
        };
    </script>
</body>
</html>
"""
