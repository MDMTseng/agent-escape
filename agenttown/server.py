"""AgentTown WebSocket server — streams world state to connected clients."""

from __future__ import annotations

import asyncio
import json
import logging
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
    brains = {aid: RandomBrain() for aid in agent_ids}

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

            await broadcast({
                "type": "tick",
                "tick": sim_world.tick,
                "events": [
                    {"type": e.event_type, "description": e.description, "room": e.room_id}
                    for e in tick_events
                ],
                "world_state": sim_world.snapshot(),
            })

            sim_world.advance_tick()

            if sim_world.finished:
                await broadcast({
                    "type": "finished",
                    "reason": sim_world.state.finish_reason,
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
    <title>AgentTown</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Courier New', monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }
        h1 { color: #58a6ff; margin-bottom: 10px; }
        #status { color: #3fb950; margin-bottom: 20px; }
        #events { max-height: 80vh; overflow-y: auto; }
        .tick-group { margin-bottom: 12px; border-left: 2px solid #30363d; padding-left: 12px; }
        .tick-label { color: #8b949e; font-size: 12px; margin-bottom: 4px; }
        .event { padding: 2px 0; }
        .event.move { color: #79c0ff; }
        .event.pick_up { color: #3fb950; }
        .event.use { color: #d2a8ff; }
        .event.examine { color: #58a6ff; }
        .event.talk { color: #f0f6fc; }
        .event.fail { color: #f85149; }
        .event.state_change { color: #e3b341; }
        .event.wait { color: #484f58; }
        .finished { color: #3fb950; font-size: 18px; font-weight: bold; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>AgentTown</h1>
    <div id="status">Connecting...</div>
    <div id="events"></div>
    <script>
        const eventsDiv = document.getElementById('events');
        const statusDiv = document.getElementById('status');
        const ws = new WebSocket(`ws://${location.host}/ws`);

        ws.onopen = () => { statusDiv.textContent = 'Connected — watching simulation...'; };
        ws.onclose = () => { statusDiv.textContent = 'Disconnected'; statusDiv.style.color = '#f85149'; };

        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'tick') {
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
                const div = document.createElement('div');
                div.className = 'finished';
                div.textContent = msg.reason;
                eventsDiv.appendChild(div);
            }
        };
    </script>
</body>
</html>
"""
