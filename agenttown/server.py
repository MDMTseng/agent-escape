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
        /* Left panel — narrative story */
        #story-panel {
            flex: 3;
            padding: 30px;
            overflow-y: auto;
            border-right: 1px solid #21262d;
        }
        #story-panel h1 {
            font-family: 'Georgia', serif;
            color: #e3b341;
            font-size: 28px;
            margin-bottom: 5px;
        }
        #story-panel .subtitle {
            color: #8b949e;
            font-style: italic;
            margin-bottom: 20px;
        }
        #status { color: #3fb950; margin-bottom: 20px; font-family: monospace; font-size: 12px; }
        .narrative-block {
            margin-bottom: 20px;
            padding: 15px;
            background: #161b22;
            border-left: 3px solid #e3b341;
            border-radius: 0 6px 6px 0;
            line-height: 1.7;
            font-size: 15px;
        }
        .narrative-block .chapter {
            color: #8b949e;
            font-size: 11px;
            font-family: monospace;
            margin-bottom: 8px;
        }
        .narrative-block p {
            color: #e6edf3;
        }
        .finished-narrative {
            margin-top: 20px;
            padding: 20px;
            background: #0d2818;
            border-left: 3px solid #3fb950;
            border-radius: 0 6px 6px 0;
            font-size: 18px;
            color: #3fb950;
            line-height: 1.7;
        }
        /* Right panel — raw event log */
        #log-panel {
            flex: 2;
            padding: 20px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            background: #0a0e14;
        }
        #log-panel h2 {
            color: #58a6ff;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .tick-group { margin-bottom: 10px; border-left: 2px solid #30363d; padding-left: 10px; }
        .tick-label { color: #8b949e; font-size: 11px; margin-bottom: 2px; }
        .event { padding: 1px 0; font-size: 12px; }
        .event.move { color: #79c0ff; }
        .event.pick_up { color: #3fb950; }
        .event.drop { color: #d29922; }
        .event.use { color: #d2a8ff; }
        .event.examine { color: #58a6ff; }
        .event.talk { color: #f0f6fc; }
        .event.fail { color: #f85149; }
        .event.state_change { color: #e3b341; }
        .event.wait { color: #484f58; }
        @media (max-width: 768px) {
            body { flex-direction: column; }
            #story-panel { border-right: none; border-bottom: 1px solid #21262d; flex: 1; }
            #log-panel { flex: 1; }
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
    <div id="log-panel">
        <h2>Event Log</h2>
        <div id="events"></div>
    </div>
    <script>
        const storyDiv = document.getElementById('story');
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws`);

        ws.onopen = () => { statusDiv.textContent = 'Connected — watching simulation...'; };
        ws.onclose = () => { statusDiv.textContent = 'Disconnected'; statusDiv.style.color = '#f85149'; };

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'tick') {
                // Narrative panel
                if (msg.narrative) {
                    const block = document.createElement('div');
                    block.className = 'narrative-block';
                    block.innerHTML = `<div class="chapter">Chapter ${msg.tick + 1}</div><p>${msg.narrative.replace(/\\n/g, '<br>')}</p>`;
                    storyDiv.appendChild(block);
                    storyDiv.scrollTop = storyDiv.scrollHeight;
                }

                // Raw event log
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
                // Narrative ending
                const block = document.createElement('div');
                block.className = 'finished-narrative';
                block.innerHTML = msg.narrative || msg.reason;
                storyDiv.appendChild(block);

                // Log ending
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
