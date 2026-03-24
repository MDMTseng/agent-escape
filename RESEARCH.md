# AgentTown Research — Complete Reference

> Generated 2026-03-25 from ~35 parallel research agents

## Table of Contents
1. Project Architecture
2. SOTA Agent Techniques
3. Escape Room Design
4. Story-Driven Puzzle Design
5. UI/UX Redesign Vision

---

## 1. Key Insight Summary

### The Three Transformations Needed

**Transform 1: Puzzle Generation**
- FROM: Random puzzles placed in rooms
- TO: Characters create puzzles (paranoid scientist → security locks, artist → visual codes)
- Pipeline: World Bible → Characters → Motivations → Puzzles → Clues (intentional + accidental)

**Transform 2: Map Structure**
- FROM: Linear room chains
- TO: Hybrid flow (parallel clusters converging at forks, 5-room dungeon model)
- Pipeline: Build backward from exit → parallel puzzle clusters → difficulty curve → validate solvability

**Transform 3: User Experience**
- FROM: Developer simulation dashboard
- TO: Interactive detective novel generator
- Pipeline: Story seed → world construction reveal → narrative feed → investigation board → shareable stories

### The Core Formula
```
Character TRAIT → BEHAVIOR → ARTIFACT → PUZZLE → ACCIDENTAL CLUE
```

### The Generation Pipeline
```
Phase 1: AI generates WORLD BIBLE (setting, characters, relationships, inciting incident)
Phase 2: AI generates CHARACTER → PUZZLE mappings (trait → lock type, motivation → clue style)
Phase 3: CODE builds room structure (DAG, parallel clusters, difficulty curve, solvability)
Phase 4: AI fills atmospheric content (room descriptions, diary entries, inscriptions)
Phase 5: CODE validates (clue reachability BFS, puzzle type diversity, cooperation requirements)
Phase 6: AI adds polish (red herrings, environmental storytelling, multi-ending narrative)
```

### UI Vision: Three Modes
1. **The Reader** — Pure spectator, story auto-advances like a novel
2. **The Detective** — Investigation board, clue connections, agent memory search
3. **The Director** — Full control, debug view (current dashboard, enhanced)

### Reference Games to Learn From
- **Disco Elysium** — Theory/thought cabinet, stat transparency, skill checks
- **Return of the Obra Dinn** — Investigation board, non-linear scene replay
- **Her Story** — Search-based investigation, minimal UI, pattern recognition
- **80 Days** — Map as narrative, story cards with mechanical consequences
- **Papers Please** — Document examination as puzzle, desk metaphor
- **Reigns** — Swipe decisions, delayed consequences, endless feel

---

## 2. Detailed Research Available

Full agent outputs stored in temp directory during this session.
Key topics covered across ~35 research agents:

### Project Architecture (8 agents)
- Complete module map and file structure
- World engine: models, actions, events, rules, world
- Agent brain: LLMBrain, tool calling, up to 5 actions/tick
- Memory: 3-tier (working/stream/reflections), embeddings, keyword fallback
- Scenarios: escape_room, architect (reverse-chain), builder, generator
- Server: FastAPI + WebSocket, 15+ API endpoints
- Persistence: SQLite save/load with brain snapshots

### SOTA Techniques (4 agents)
- Generative Agents, ReAct, Reflexion, Voyager, SPRING, MemGPT
- Memory architectures for limited context windows
- Multi-agent coordination (CAMEL, AutoGen, CrewAI, MetaGPT)
- Puzzle representation and solving (ToT, planning, benchmarks)

### Escape Room Design (8 agents)
- Professional design principles and 3-act structure
- Puzzle flow graphs (linear vs parallel vs hybrid)
- Lock-and-key pattern (Mark Brown / GMTK)
- 5-room dungeon model
- Comprehensive puzzle type taxonomy (15+ categories)
- Spatial layout patterns (hub-spoke, linear, maze)
- AI procedural puzzle generation
- Multi-agent cooperative puzzle design

### Story-Driven Design (6 agents)
- Narrative-driven puzzle design (lore bibles, character archetypes)
- Character trait → puzzle type mapping
- Intentional vs accidental clues
- Clue trail architecture (breadcrumb chains, fair play rules)
- World-building for puzzle games (Myst, Witness, Outer Wilds approach)
- Story generation frameworks with AI prompts

### UI/UX Redesign (5 agents)
- Current dashboard analysis
- Detective novel game UX patterns
- Narrative game UI design (typography, color, atmosphere, maps)
- World construction UX (story seed → reveal sequence)
- Reference game UI analysis (7 games dissected)
