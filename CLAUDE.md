# AgentTown

A virtual world where LLM-powered agents live, interact with each other, and solve puzzles.

## Dev Rules

- **Every feature/milestone must have tests before committing.** No code lands without corresponding test coverage.
- **Only touch files inside this project folder.** Do not modify files outside of `C:\Users\TRS001\Documents\workspace\agenttown\`.
- Run tests with: `python -m pytest tests/ -v`
- Install for development: `pip install -e ".[dev]"`

## Stack

- Python core (simulation, agent logic)
- TypeScript frontend (React + Vite + Tailwind + shadcn/ui in `frontend/`)
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
  bash start_qqwweerr.sh start          # starts server
  bash start_qqwweerr.sh restart        # restarts server
  bash start_qqwweerr.sh stop           # stops server
  ```
- **Port**: `8741`.
- **Tunnels**: Use the `/tunnel` skill or WebTunnelHub directly (not this script).

## Frontend Dev Servers

The UI lives in `frontend/`. There are two ways to run it:

**Production mode (single server):**
FastAPI serves the Vite-built frontend from `frontend/dist/`. Build first, then start the backend:
```bash
cd frontend && npm run build       # creates frontend/dist/
cd .. && bash start_qqwweerr.sh start   # serves UI at http://localhost:8741/
```
The old embedded UIs remain available at `/dashboard` and `/narrative`.

**Development mode (two servers, hot reload):**
Run both the Vite dev server and the FastAPI backend simultaneously. Vite proxies API/WS requests to the backend:
```bash
# Terminal 1: backend
bash start_qqwweerr.sh start       # FastAPI on :8741

# Terminal 2: frontend dev server
cd frontend && npm run dev         # Vite on :5173, proxies /api and /ws to :8741
```
In dev mode, open `http://localhost:5173` for hot-reloading React. The Vite proxy config in `frontend/vite.config.ts` forwards `/api/*` and `/ws` to the backend on port 8741.

## Escape Room UI rebuild (Cursor)

- **Subagents** (versioned under `.cursor/agents/`): `ui-builder` implements one feature per session from `ui-feature-list.json` and updates `ui-progress.txt`; `ui-reviewer` independently verifies and may set `passes` in the feature list. Invoke with `/ui-builder` or `/ui-reviewer`.
- **Tracking files** (at repo root when UI work is active): `ui-feature-list.json`, `ui-progress.txt`.
- **Loop**: pick highest-priority failing feature → `/ui-builder` → `/ui-reviewer`; on FAIL, iterate with builder until PASS. (Claude Code users may mirror agents under `.claude/agents/` locally; Cursor uses `.cursor/agents/` only.)

## Notifications

Send progress updates via ntfy.sh during dev loops:
```bash
curl -d "your message here" ntfy.sh/mdm_dev_notify
```
