# AgentTown

A virtual world where LLM-powered agents live, interact with each other, and solve puzzles.

## Dev Rules

- **Every feature/milestone must have tests before committing.** No code lands without corresponding test coverage.
- Run tests with: `python -m pytest tests/ -v`
- Install for development: `pip install -e ".[dev]"`

## Stack

- Python core (simulation, agent logic)
- TypeScript frontend (planned, not yet implemented)
- Pydantic for all data models
- Claude API (Anthropic SDK) for agent brains
- asyncio for tick loop
- rich for CLI output

## Project Structure

- `agenttown/world/` — core simulation (models, actions, events, rules, world)
- `agenttown/agents/` — agent brain, memory, prompts (Claude integration)
- `agenttown/scenarios/` — world-building scenarios (escape room, etc.)
- `tests/` — pytest test suite
