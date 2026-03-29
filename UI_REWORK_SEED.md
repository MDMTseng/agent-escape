# UI Rework Seed Document

> **Branch**: `uirework`
> **Date**: 2026-03-26
> **Status**: Planning

---

## Vision

AgentTown is an AI-agent experimental escape room game. The UI rework replaces the current embedded HTML/JS interface with a modern, component-driven frontend that serves three core experiences:

1. **Interactive Scene Creator** - Design escape rooms and configure player agents
2. **Live Game Monitor** - Visualize agent behavior, puzzle progress, and scene state in real-time
3. **Persistence Hub** - Save, load, branch, and share created scenes and game progress

---

## 1. Interactive Escape Room Scene Creator & Agent Designer

### 1.1 Scene Builder

**Story Foundation**
- Theme selection with rich preview cards (Gothic Manor, Sci-Fi Lab, Ancient Tomb, + custom)
- Backstory editor: free-text premise with AI-assisted expansion (Claude generates world bible from a seed paragraph)
- Difficulty slider (1-5) that controls puzzle density, clue obscurity, and room count
- AI-generated world bible preview: setting, timeline, inciting incident, character relationships

**Room Designer**
- Visual room graph editor: drag-to-create rooms, drag edges to connect with doors
- Per-room configuration: name, description, atmosphere tags, entity list
- Door properties: locked/unlocked, required key/password/combo, one-way vs bidirectional
- Entity palette: drag-and-drop furniture, clues, puzzle mechanisms, decorative items
- Entity states: DEFAULT, HIDDEN, LOCKED, SOLVED, ACTIVATED (configurable per entity)

**Puzzle Builder**
- Puzzle type picker: key_lock, combination_lock, password_door, pressure_plate, examine_reveal, sequential_levers
- Puzzle chain editor: visual DAG (directed acyclic graph) showing solve dependencies
- Clue placement: assign clues to rooms/entities, set discovery method (examine, use, talk)
- Solvability validator: real-time BFS check that all puzzles are reachable and solvable
- AI-assisted puzzle generation: describe intent ("a puzzle that reveals the victim's last words"), Claude generates the mechanics

**Escape Chain**
- Visual 12-step escape chain editor
- Each step: action type, target entity, room, description
- Drag-to-reorder steps
- Auto-validate chain integrity on edit

### 1.2 Agent Designer

**Character Creator**
- Agent profile: name, role, backstory, personality traits (from archetype library or free-text)
- Portrait/avatar: select from preset icons or generate description for visual identity
- Trait-to-behavior mapping preview: show how traits influence puzzle-solving style
- Starting conditions: spawn room, initial inventory, initial knowledge/memories

**Agent Configuration**
- Goal assignment: primary goal, secondary goals, secret motivations
- Knowledge seeding: what the agent knows at game start (working memory entries)
- Relationship matrix: define trust/suspicion/alliance between agents
- Behavioral tuning: curiosity level, cooperation tendency, communication frequency

**Templates & Presets**
- Quick-start character archetypes: The Detective, The Scholar, The Skeptic, The Helper
- Theme-matched character suggestions: auto-generate agents that fit the story's world bible
- Save custom agent templates for reuse across scenes

---

## 2. Live Game Monitor

### 2.1 Agent Visualization

**Agent Dashboard Panel**
- Per-agent cards showing: current location, inventory, emotional state, current goal
- Real-time action feed: what each agent is doing this tick (examine, move, talk, use)
- Agent thought bubbles: show the reasoning/decision process from LLMBrain (summarized)
- Memory inspector: browse agent's memory stream, working memory, and reflections
- Perception overlay: what the agent currently "sees" (room entities, exits, other agents)

**Agent Interaction Monitor**
- Conversation log: full dialogue history between agents (talk actions)
- Collaboration tracker: when agents share clues or work together on puzzles
- Trust/relationship evolution: visual indicator of how agent relationships change over time

### 2.2 Puzzle Progress Dashboard

**Escape Chain Progress Bar**
- Visual progress indicator: 12-step chain with solved/pending/active states
- Click any step to see: which agent solved it, what tick, what actions led to the solve
- Estimated completion: based on discovery rate and remaining puzzle complexity

**Puzzle State Grid**
- All puzzles in a grid/table: puzzle name, type, room, status (unsolved/in-progress/solved)
- Clue discovery tracker: which clues have been found, by whom, and where
- Puzzle dependency visualization: which puzzles unlock which other puzzles
- "Warmth" indicator: how close agents are to solving each active puzzle (based on clues found vs required)

### 2.3 Scene Status & World View

**Interactive Map**
- Real-time room graph: rooms as nodes, doors as edges, agent positions as moving markers
- Room inspection: click a room to see its entities, current occupants, state changes
- Door status overlay: locked (red), unlocked (green), requires key (yellow)
- Heat map mode: color rooms by activity level (how often agents visit)
- Entity state changes: visual highlight when entities change state (LOCKED -> UNLOCKED)

**Narrative Feed**
- Prose-style event stream: narrator-generated descriptions of agent actions
- Filterable by: agent, room, event type (puzzle, movement, dialogue, discovery)
- Card-based layout with pagination and auto-scroll toggle
- Tick counter and simulation speed indicator

**Timeline / Replay**
- Tick-by-tick timeline scrubber: review what happened at any tick
- Event markers on timeline: puzzle solves, key discoveries, agent conversations
- Rewind capability: load a previous auto-save to replay from a specific point

### 2.4 Spectator Controls

**Simulation Controls**
- Play / Pause / Step (advance one tick)
- Speed control: slow (1 tick/5s), normal (1 tick/2s), fast (1 tick/0.5s)
- Skip to next event: fast-forward until something interesting happens

**Nudge System** (spectator influence)
- Hint suggestions: prompt an agent to look at a specific entity or visit a room
- Focus mode: make an agent prioritize a particular puzzle
- Communication prompt: suggest agents talk to each other about a topic
- Nudge history: log of all spectator interventions

**Director Mode** (debug/admin)
- Raw event log with JSON expand
- Server log stream (memory updates, token usage, Claude API calls)
- Force-trigger actions: manually execute agent actions for testing
- World state JSON inspector

---

## 3. Save, Load & Persistence

### 3.1 Scene Persistence

**Scene Library**
- Grid/list view of all created scenes with: title, theme badge, room count, agent count, difficulty, creation date
- Scene preview: thumbnail-style view showing room graph and character list
- Search and filter: by theme, difficulty, creation date
- Duplicate scene: clone an existing scene as starting point for a new one

**Scene Export/Import**
- Export scene as JSON file (world definition, agents, puzzles, escape chain)
- Import scene from JSON file
- Scene versioning: track edits with version history, revert to previous versions

### 3.2 Game Progress Persistence

**Save System**
- Manual save: save current game state at any tick with custom name
- Auto-save: periodic saves (configurable interval, e.g., every 10 ticks)
- Save slots: multiple saves per scene, with tick number and timestamp
- Save preview: summary of progress (escape chain status, agent locations, ticks elapsed)

**Load System**
- Load from save: restore full game state (world state, agent memories, escape chain progress)
- Resume latest: one-click resume from most recent save
- Save branching: load a mid-game save and play forward from that point (creates a branch)
- Compare saves: side-by-side view of two saves showing what changed

### 3.3 Storage Backend

- SQLite database (`agenttown_saves.db`) with stories + saves tables (existing)
- Full state serialization: world snapshot, brain snapshots, escape chain, narrator context
- Cascade delete: removing a story removes all its saves
- Future: cloud sync / multi-device support (optional)

---

## 4. Technical Direction

### 4.1 Frontend Stack (New)

- **Framework**: React with TypeScript
- **Styling**: Tailwind CSS + shadcn/ui components
- **State Management**: Zustand (lightweight, fits the real-time update pattern)
- **Real-time**: WebSocket client (existing `/ws` endpoint)
- **Visualization**: React Flow (room graph editor), Recharts (progress charts)
- **Build**: Vite (fast dev server, optimized builds)
- **Deployment**: Static build served by FastAPI (replaces embedded HTML)

### 4.2 Backend Changes

- Existing FastAPI server and API endpoints remain
- New endpoints for scene CRUD (create/read/update/delete room graphs, agents, puzzles)
- New endpoints for nudge system (hint, focus, communicate)
- WebSocket protocol extension: add message types for scene editor events, nudge commands
- Scene validation endpoint: check solvability before play

### 4.3 Migration Path

1. Scaffold React+TypeScript+Vite project in `frontend/`
2. Build Scene Creator (connects to existing `/api/themes`, `/api/generate-story`)
3. Build Live Monitor (connects to existing `/ws`, `/api/state`, `/api/saves`)
4. Build Persistence Hub (connects to existing `/api/stories`, `/api/saves`)
5. Replace embedded NARRATIVE_HTML with `GET /` serving built React app
6. Deprecate `ui_narrative.py` after full feature parity

---

## 5. Design Principles

- **Mobile & gesture first**: Every component is designed for a 375px screen held in one hand. Touch targets 44px+. Swipe to act, long-press for context, pinch to zoom maps. Primary actions in the thumb zone (bottom third). Desktop is the progressive enhancement, not the default.
- **Spectator-first**: The user watches agents play, not plays directly. UI should make observation engaging and informative.
- **Information density without clutter**: Show a lot of data (agent state, puzzle progress, room status) without overwhelming. Progressive disclosure - summary first, detail on tap. Bottom sheets for detail panels on mobile, side panels on desktop.
- **Dark theme, atmospheric**: Maintain the existing moody aesthetic (dark backgrounds, gold accents, atmospheric effects). The UI should feel like part of the escape room experience.
- **Real-time by default**: Everything updates live via WebSocket. No manual refresh needed.
- **Native-app feel on mobile**: Sticky bottom nav, swipe-dismissible sheets, smooth GPU-accelerated animations, instant touch feedback (<100ms).

---

## 6. Screen Flow

```
[Scene Library] -----> [Scene Creator] -----> [Play / Monitor]
      |                    |                        |
      |                    v                        v
      |              [Agent Designer]         [Nudge Controls]
      |                                            |
      v                                            v
[Load Save] --------------------------> [Resume Game Monitor]
```

### Pages / Views
1. **Home / Scene Library** - Browse, search, create, delete scenes
2. **Scene Creator** - Tabbed editor: Story, Rooms, Puzzles, Agents, Validate
3. **Game Monitor** - Main play screen: Map + Narrative + Agent Cards + Progress + Controls
4. **Save/Load Manager** - Within game monitor: save, load, branch, compare
5. **Settings** - API key config, simulation speed defaults, auto-save preferences

---

## 7. Priority Order

| Phase | Scope | Goal |
|-------|-------|------|
| **P0** | React scaffold + Scene Library + basic Game Monitor | Functional replacement of current UI |
| **P1** | Scene Creator (rooms, puzzles, agents) + Puzzle Progress Dashboard | Interactive scene building |
| **P2** | Agent visualization (thoughts, memory, perception) + Nudge system | Deep agent observability |
| **P3** | Timeline/replay, save branching, scene export/import | Power user features |
