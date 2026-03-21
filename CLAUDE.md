# AgentTown

A virtual world where LLM-powered agents live, interact with each other, and solve puzzles.

## Dev Rules

- **Every feature/milestone must have tests before committing.** No code lands without corresponding test coverage.
- **Only touch files inside this project folder.** Do not modify files outside of `C:\Users\TRS001\Documents\workspace\agenttown\`.
- Run tests with: `python -m pytest tests/ -v`
- Install for development: `pip install -e ".[dev]"`

## Stack

- Python core (simulation, agent logic)
- TypeScript frontend (planned, not yet implemented)
- Pydantic for all data models
- Anthropic Claude API (Haiku 4.5) for agent brains and narrator
- asyncio for tick loop
- rich for CLI output

## Project Structure

- `agenttown/world/` — core simulation (models, actions, events, rules, world)
- `agenttown/agents/` — agent brain, memory, prompts (Claude integration)
- `agenttown/scenarios/` — world-building scenarios (escape room, etc.)
- `tests/` — pytest test suite

## Server Rules

- **Scripts**: `start_qqwweerr.sh` (start/stop/restart) and `run_qqwweerr.py` (server launcher). Token `qqwweerr` is in the filenames so processes are identifiable.
- **Usage**:
  ```bash
  bash start_qqwweerr.sh start          # starts server + Cloudflare tunnel
  bash start_qqwweerr.sh restart        # restarts server ONLY — tunnel stays up
  bash start_qqwweerr.sh stop           # stops server only
  bash start_qqwweerr.sh stop_all       # stops server + tunnel
  bash start_qqwweerr.sh start_tunnel   # starts tunnel only
  bash start_qqwweerr.sh stop_tunnel    # stops tunnel only
  ```
- **Port**: `8741`. Tunnel URL is logged to `/tmp/agenttown_tunnel.log`.
- **Important**: Do NOT kill the Cloudflare tunnel on restart — quick tunnels get a new random URL each time, so the user would lose their link. `restart` only recycles the server; the tunnel keeps proxying to the same port.
