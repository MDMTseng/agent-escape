# AgentTown Spectator Experience Design Document

## Overview

This document outlines how AgentTown should adapt AI Dungeon's best interactive patterns for a **spectator mode** where AI agents solve puzzles autonomously while the user watches, reads, and occasionally intervenes—similar to reading an interactive novel with characters who act without player commands.

**Key Paradigm Shift:**
- **AI Dungeon:** User types action → AI narrates response (player-centric)
- **AgentTown Spectator:** AI agents act autonomously → User reads narrative + occasionally guides agents (character-centric, narrative-driven)

---

## 1. The Spectator Engagement Problem

The fundamental challenge: **How do you maintain engagement when the player loses direct control?**

In AI Dungeon, the dopamine hit comes from:
1. **Agency:** "I typed that action, and the world responded"
2. **Control:** "I can do anything I want right now"
3. **Immediate feedback:** Quick turn-based loop (type → result → type)

In AgentTown spectator mode, agency shifts to **narrative investment** and **collaborative observation**. The dopamine replacements are:

### 1.1 Anticipation
The user becomes invested in whether agents will succeed. This mirrors following a TV series' cliffhanger—will Alice find the hidden key?

**Implementation:**
- Show puzzle state visually (what's been solved, what remains)
- Highlight when agents are close to discovering critical clues
- Display agent "goal progress" so user can mentally track what happens next
- Create moments of tension: "Alice is examining the painting... will she notice the loose board?"

**UI Signal:** On the investigation board, show puzzle branches with a "warmth indicator"—glowing sections where agents are actively investigating.

### 1.2 Surprise
When the AI does something unexpected or clever—taking a lateral approach the user didn't anticipate.

**Implementation:**
- Surface agent reasoning: "Alice decided to combine the painting key with the mirror to create a reflective surface"
- Show failed attempts gracefully: failed puzzle attempts should feel like learning moments, not frustration
- Celebrate agent cleverness with narrative flourishes (narrator emphasis)

**UI Signal:** Include a "reasoning bubble" showing the agent's decision-making logic before actions execute.

### 1.3 Dramatic Irony
The user sees information agents don't. This creates tension and desire to help.

**Implementation:**
- Show the user what clues exist and which ones agents have found
- Highlight undiscovered clues with visual markers (subtle glow, different shade)
- Display agent knowledge state: "Alice doesn't know the combination yet, but the player knows it's 1-2-3"
- This is the **justification for the "nudge" system** (see section 2)

**UI Signal:** Investigation board shows two layers:
- Layer 1: "What agents know" (what they've examined)
- Layer 2: "What exists in the world" (all discoverable clues, shown to spectator only)

### 1.4 Rooting for Characters
Agents need personality, goals, and limitations. Users should care whether they succeed.

**Implementation:**
- Show agent personality in dialogue and decisions
- Display agent state (confused, confident, frustrated, making progress)
- Add agent-specific reactions: "Alice hesitates, unsure if the key will fit"
- Include micro-emotions in narrative: "Bob's shoulders slump as the code fails again"

**UI Signal:** Agent cards show not just inventory and location, but also emotional state and current "focus" (what they're trying to solve).

---

## 2. Interaction Points for Spectators

The spectator must remain passive-by-default but active-when-needed. The key is making interventions feel **natural and diegetic** (within the world's logic) rather than meta-mechanical.

### 2.1 The Nudge System (Primary Interaction)

**What it is:** A subtle hint mechanism that influences an agent without breaking immersion.

**How AI Dungeon does it:** You can regenerate the AI's response if you don't like it. But this is overt and breaks the fourth wall.

**How AgentTown should adapt it:**

The user can send a whispered hint to an agent at key moments:
- User sees Alice staring at a blank wall
- User knows there's a clue on the wall Alice hasn't examined
- User clicks the "nudge" button on Alice's card
- Alice receives the hint in her perception: `HINT: The wall deserves a closer look`
- Alice's next action is more likely to examine the wall (nudge goes into her system prompt)
- Narrative frames it naturally: "Something draws Alice's gaze to the wall. She leans closer..."

**Rules for nudges:**
- One nudge per agent per puzzle (limited resource)
- Nudge only affects the agent's next decision, doesn't force action
- Nudge is contextual: can't nudge an agent in the wrong room with a hint about another room
- Visual feedback: nudge button glows/pulses when available

**UI Implementation:**
```
┌─ Agent Card: Alice ──────────────────┐
│ Status: Searching | Inventory: [key] │
│                                      │
│ Current Focus: Find exit code        │
│ Emotional State: ⚠️ Confused         │
│                                      │
│ [← Move] [Examine] [⭘ Nudge] [>]   │
│ "The painting seems important"      │ (narrative suggestion)
└──────────────────────────────────────┘
```

---

### 2.2 Decision Voting at Critical Moments

**When:** At major decision points where agent choices fork the narrative

**How it works:**
1. Agent reaches a major crossroads (which room to explore next)
2. System detects meaningful branches (different puzzle paths)
3. Pause auto-advance, prompt user: "Alice can go north (kitchen) or west (study). Which room should she explore first?"
4. User votes (or auto-resolves if system timeout)
5. Agent's "preference" for that direction gets boosted in the next decision cycle
6. Narrative acknowledges it: "Alice takes a deep breath and heads west, toward the study"

**Voting model:**
- Display 2-3 options (not overwhelming)
- Each option shows expected narrative branch ("Kitchen: Finding food, a locked cabinet")
- User vote contributes to agent perception: agent gets +weight toward voted direction
- Real-time vote counter (how many spectators voted for each)

**When NOT to offer votes:**
- During active puzzle-solving (too disruptive)
- For minor choices (examine vs. pick up the same item)
- When agent is mid-action sequence

**UI Implementation:**
```
┌─── Decision Moment ──────────────────┐
│ Alice is at the hallway junction      │
│ Which path should she explore first?  │
│                                      │
│ [A] Kitchen (food, locked cabinet)   │
│      Votes: ████░░ (6/10)            │
│                                      │
│ [B] Study (books, writing desk)      │
│      Votes: ██████░ (8/10)           │
│                                      │
│ [C] Basement (machinery, stairs)     │
│      Votes: ██░░░░░ (2/10)           │
│                                      │
│ Time remaining: 15s [Auto-resolve]   │
└──────────────────────────────────────┘
```

---

### 2.3 Personality Adjustment Mid-Story

**What it is:** Let the user tweak agent behavior parameters without restarting

**How it works:**
- User can toggle traits: "Make Bob more cautious" / "Make Alice more aggressive"
- This modifies the agent's system prompt weights for risk/reward
- Affects decision-making without forcing specific actions
- Changes persist for the rest of that run

**Implementation:**
- Slider on agent card: "Cautious ↔ Aggressive"
- Slider: "Logical ↔ Intuitive" (how much they rely on reasoning vs. gut feel)
- Slider: "Social ↔ Solo" (tendency to coordinate with other agents)
- Changes take effect next tick

**Narrative framing:** "Alice seems to gain confidence" (when switching to aggressive mode)

---

### 2.4 Speed Control

**The problem:** AgentTown auto-advances ticks. Some moments should slow down, others speed up.

**How it works:**

**Auto-pause at dramatic moments:**
- When a puzzle is solved
- When an agent discovers a major clue
- When agents die/fail irreversibly
- When dialogue reveals critical info

**User manual controls:**
- Play/Pause button (always available)
- Speed slider: 0.5x (slow), 1x (normal), 2x (fast), 4x (very fast)
- Step button (advance one tick manually when paused)

**Smart speed adjustments:**
- Show "pacing suggestion": "Fast-forwarding agent walking (5s)..." auto-advances
- During puzzle-solving: force to 1x or slower (never auto-accelerate during tension)
- During waiting (agent stalled): auto-accelerate to 2x after 10s of inactivity

**UI Implementation:**
```
┌─── Playback Controls ───────────────┐
│ [⏮] [⏯ Pause] [⏭]                   │
│                                    │
│ Speed: [---|•|-----] 1.0x          │
│        0.5x    Normal   4x         │
│                                    │
│ ☐ Auto-pause on discoveries       │
│ ☐ Auto-pause on failures          │
│ ☐ Auto-skip agent walking         │
└────────────────────────────────────┘
```

---

### 2.5 "What If?" Branches and Checkpoints

**What it is:** The ability to rewind and replay from a checkpoint with different choices

**How it works:**
1. System auto-saves every N ticks (default: 10)
2. User can view checkpoint list (like a save game list)
3. Click "Rewind to Tick 23" and choose different agent actions
4. Branch creates an alternate timeline (doesn't overwrite original)
5. Compare outcomes side-by-side

**Use cases:**
- "What if I had told Alice to examine the painting earlier?"
- "Let me see what happens if Bob goes north instead of south"
- "I want to optimize for speed—let me try a different puzzle sequence"

**Technical implementation:**
- Uses AgentTown's existing persistence layer (GameStore)
- Each replay creates a new save branch
- UI shows branch tree: original path highlighted, replays as alternates

**UI Implementation:**
```
┌─── Timeline / Checkpoints ────────────────┐
│ Tick 0 ─→ 10 ─→ 20 ─→ 30 (current)       │
│                ╰─→ 25 [What if? branch]   │
│                    ├─ Faster ending       │
│                    └─ Different puzzle order
│                                           │
│ [Save Checkpoint] [Rewind] [View Branches]│
└───────────────────────────────────────────┘
```

---

## 3. AI Dungeon's "Do/Say/Story" Adapted for Spectators

AI Dungeon offers three action modes:
- **Do:** Force an action (bypasses AI decision)
- **Say:** Force dialogue
- **Story:** Narrator-style input (influences tone/direction)

AgentTown should adapt these for a spectator who doesn't control but influences:

### 3.1 "Do" → Gentle Command

**In AI Dungeon:** User types "pick up the sword" and the character does it.

**In AgentTown:** User right-clicks an agent and selects a subtle command:
- "Have Alice examine the painting"
- "Tell Bob to go north"
- "Make Alice pick up that key"

**Rules:**
- Commands are **suggestions**, not overrides
- If physically impossible (examine something in another room), the agent tries the nearest equivalent
- Frequency-limited: max 1 command per agent per 5 ticks
- Narrative frames it as agent initiative: "Alice decides to examine the painting"

**Implementation:**
- Context menu on agent: "Suggest Action"
- Dropdown of nearby objects: "Examine [painting] [mirror] [desk]"
- Dropdown of nearby exits: "Move [north] [south] [east]"
- Dropdown of inventory: "Use [key on painting]"

---

### 3.2 "Say" → Whisper a Hint

**Already covered in section 2.1 (Nudge System).**

But extended: Instead of vague nudges, user can whisper specific information:
- "Tell Alice: The painting has a loose board"
- "Remind Bob: You already found a key in the desk"
- "Suggest to Alice: The combination might be in the study"

This goes into the agent's hint list in perception, influencing their next decision cycle.

---

### 3.3 "Story" → Narrate a Direction

**What it is:** User writes a short narrative snippet that influences mood/direction without dictating action

**How it works:**
- User clicks "Add Narrative Element"
- Writes: "The room feels colder. Alice shivers as she notices the door is slightly ajar."
- Narrator integrates it into the next story beat
- Affects agent mood in their perception: "There's a chill in the air here"
- Agents react naturally to the framed atmosphere

**Rules:**
- Must be plausible given world state
- System suggests narrative elements automatically (based on what's likely to happen)
- User-written narratives act as "story guidance" not plot commands
- Limited to 1-2 per scene to avoid overriding the narrator

**Implementation:**
- "Story Suggestion" button below main narrative feed
- Text area for user to write atmosphere/mood
- Preview of how it would be integrated
- Narrator processes it in next narration cycle

---

## 4. Memory & Context for Spectators

### 4.1 The Investigation Board (AI Dungeon's World Info adapted)

**What it is:** A visual knowledge graph showing all discoverable information in the scenario

**Structure:**
```
┌─── Investigation Board ───────────────────────────────┐
│                                                       │
│  Legend:  ✓ Discovered   ○ Undiscovered   ✗ Failed   │
│                                                       │
│  CLUES TO FIND:                                       │
│  ├─ Painting [✓ Alice]                               │
│  │  └─ Behind painting: Hidden board [○]             │
│  ├─ Desk drawer [○]                                  │
│  │  └─ Combination lock [○]                          │
│  │     └─ Code: 1-2-3 [✓ Bob found it!]             │
│  └─ Bookshelf [○]                                    │
│     └─ Book "Mysteries of Ravenwood" [○]            │
│                                                       │
│  PUZZLES SOLVED:                                      │
│  ✓ Painting locked chest (key found behind painting) │
│  ✓ Combination lock (code from book)                 │
│  ○ Final exit (need master key)                      │
│                                                       │
│  AGENTS' KNOWLEDGE:                                   │
│  ├─ Alice: Found key, painting, hidden board        │
│  ├─ Bob: Found combination, used lock successfully   │
│  └─ Charlie: Still exploring, found nothing yet      │
└───────────────────────────────────────────────────────┘
```

### 4.2 What Information Should Be Surfaced?

The spectator should see:

**Always visible to spectator:**
1. All discoverable items in each room (what's hidden/visible)
2. All puzzle requirements and solutions
3. Which agent has discovered which clue
4. Puzzle dependency tree (what needs to happen before what)

**Agent-specific (visible to spectator, not agents):**
1. What each agent knows vs. what exists
2. Agent memory/notes: "Alice remembered the code is in the study"
3. Agent goals and sub-goals
4. Agent confidence level (how sure are they about their next move)

**Why this matters:**
- Creates dramatic irony: User sees Alice walking toward a room she's already searched
- Motivates nudging: "She forgot about the basement!"
- Builds anticipation: "They almost have all the pieces..."

### 4.3 The Dramatic Irony Display

A dedicated panel showing:
```
┌─ Dramatic Irony ─────────────────────────┐
│                                         │
│ Agent vs. Reality Gap:                  │
│                                         │
│ Alice is examining the desk.            │
│ She's looking for: A key                │
│ The key is actually: On the painting    │
│    → User knows this, Alice doesn't!    │
│ → Nudge available to help her           │
│                                         │
│ Bob is about to fail the combination    │
│ Correct code: 1-2-3 (in the book)      │
│    → He's going to try: 3-2-1           │
│ → Speech hint available to guide him    │
└─────────────────────────────────────────┘
```

**Triggers:**
- When an agent is about to make a mistake (attempting wrong code, searching wrong place)
- When an agent has been stuck on a puzzle for 5+ ticks
- When an agent is close to discovering a major clue but hasn't examined the right object
- When two agents have complementary information (one has the code, one has the lock)

---

## 5. The "Retry" Problem for Spectators

### 5.1 The Problem

In AI Dungeon: If the AI response is bad, the user just clicks "Regenerate" and gets a new one. Easy.

In AgentTown: If an agent makes a dumb decision (tries the wrong code 3 times in a row), does the spectator:
- A) Accept it as part of the narrative and enjoy the struggle?
- B) Nudge the agent?
- C) Rewind and replay with better choices?

### 5.2 Solution: Graduated Intervention

**Tier 1: Auto-retry with cooldown**
- If an agent fails the same puzzle more than 2 times consecutively, trigger a "reconsideration"
- Agent pauses for 1 tick, reviews what they know, decides differently
- Narrative: "Alice steps back from the lock. She's been trying the wrong approach..."
- This feels natural, not like cheating

**Tier 2: Dramatic Irony + Nudge Suggestion**
- System detects agent is stuck
- Investigation board highlights: "Alice is struggling with the lock. You know the code!"
- Nudge button pulses (visual hint that help is available)
- User can choose to nudge or let agent continue struggling

**Tier 3: Manual Rewind**
- User rewinds to last checkpoint
- Replays with nudges/commands to guide agent better
- Creates a "better timeline" branch
- Original timeline still exists (user can view both outcomes)

### 5.3 Failure as Narrative Feature

**Key insight:** Failed attempts should feel like dramatic tension, not frustration.

**Narrative handling of failures:**
- Agent fails at a lock: "Charlie curses softly. The lock clicks shut again. They're missing something..."
- Agent fails to find a clue: "Bob searches the room methodically but finds nothing. Perhaps it's elsewhere?"
- Agent fails at a puzzle: "Alice realizes her approach won't work. She sits back, thinking..."

**Spectator framing:**
- Show what agent is missing: "Bob doesn't realize the code is reversed"
- Build tension: "This is Charlie's third attempt. Can they figure it out?"
- Enable help: "Nudge button available" or "Consider rewinding from last checkpoint"

**When to auto-intervene:**
- After 5+ failed attempts on same puzzle: auto-suggest rewind
- If agent is physically stuck (can't progress): auto-pause for user review
- If agent has been in one room for 10+ ticks: suggest nudge or rewind

---

## 6. Pacing Control

### 6.1 The Pacing Challenge

**AI Dungeon:** User types → waits for response → reads result. Turn-based, user-paced.

**AgentTown:** Ticks auto-advance. Some moments are boring (walking between rooms), others should be slow-motion dramatic (puzzle solving, big reveals).

### 6.2 Smart Pause System

**Auto-pause triggers:**
- Major discovery: "Alice finds a key!" (pause for 5 sec, let user read)
- Puzzle solved: "The lock clicks open." (pause for 3 sec)
- Critical dialogue: When agents share important information (pause for 3 sec)
- Agent death/failure: Pause indefinitely for user review
- Investigation board update: A new clue is discovered (pause for 2 sec)

**User can override:**
- Click "continue" to resume immediately
- Speed slider to adjust pause duration

### 6.3 Auto-Skip Uninteresting Ticks

**What to auto-speed:**
- Agent walking between rooms (4x speed)
- Agent searching unsuccessfully in room they've already searched (2x speed)
- Waiting (agent can't act) (4x speed)
- Dialogue between agents when user isn't focused (1.5x speed)

**What to slow down or pause:**
- Puzzle solving attempt (1x or slower)
- Discovery of new clues (1x + pause)
- Major revelation (0.5x + pause)
- Failures (1x + optional pause)

### 6.4 Manual Pacing Controls

```
┌─── Playback ─────────────┐
│ [⏮] [⏯] [⏭] [⏩]         │
│                         │
│ Speed: [─────●────]    │
│       0.5x  1x   4x    │
│                         │
│ ☐ Auto-pause majors    │
│ ☐ Auto-skip travel     │
│ ☐ Smart pacing          │
│                         │
│ Status: Playing 1.5x    │
│ Next major event: ~8s   │
└─────────────────────────┘
```

**Breakdown of controls:**
- **[⏮] Rewind to last checkpoint:** Jump to nearest save
- **[⏯] Play/Pause:** Toggle auto-advance
- **[⏭] Next tick:** Manual single-step
- **[⏩] Jump to next major event:** Skip to next auto-pause moment
- **Speed slider:** 0.5x (very slow), 1x (normal), 2x (fast), 4x (very fast)
- **Auto-pause majors:** Pause at discoveries/solves (default: ON)
- **Auto-skip travel:** Speed up boring walking sequences (default: ON)
- **Smart pacing:** System-controlled pacing (default: ON)

---

## 7. Concrete UI Recommendations

### 7.1 Main Screen Layout

The primary interface during gameplay should show **four key areas**:

```
┌──────────────────────────────────────────────────────────┐
│  AgentTown: Ravenwood Manor                       [←] [⚙] │ ← Minimal header
├──────────────────────────────────┬─────────────────────────┤
│                                  │                         │
│  NARRATIVE FEED                  │  AGENT OVERVIEW         │
│  (scrollable story)              │                         │
│                                  │  ┌─ Alice ────────┐    │
│  _The manor is quiet. Dust       │  │ Room: Study    │    │
│  motes drift in stale air. Alice │  │ Inv: [key]     │    │
│  examines the painting on the    │  │ Status: Active │    │
│  wall, running her fingers along │  │ Focus: ???     │    │
│  the frame. There's something    │  │ [Nudge: ON]    │    │
│  behind it._                     │  └────────────────┘    │
│                                  │                         │
│  Alice discovers something       │  ┌─ Bob ──────────┐    │
│  behind the painting. She pulls  │  │ Room: Kitchen  │    │
│  it free: a golden key.          │  │ Inv: []        │    │
│                                  │  │ Status: Stuck  │    │
│                                  │  │ Focus: Lock    │    │
│                                  │  │ [Nudge: OFF]   │    │
│                                  │  └────────────────┘    │
│  _The key is warm to the touch._ │                         │
│                                  │  ┌─ Charlie ──────┐    │
│                                  │  │ Room: Basement │    │
│                                  │  │ Inv: [coin]    │    │
│                                  │  │ Status: Waiting│    │
│                                  │  │ Focus: Explore │    │
│                                  │  │ [Nudge: ON]    │    │
│                                  │  └────────────────┘    │
│                                  │                         │
├──────────────────────────────────┴─────────────────────────┤
│ ┌─ Playback ──────┐  ┌─ Investigation Board (Collapsed) ─┐ │
│ │ [⏯] 1.0x [⏩]    │  │ Clues found: 3/8                 │ │
│ │ Auto-pause: ON  │  │ Puzzles: 2/4                     │ │
│ │ Next event: 5s  │  │ [Expand ↗]                       │ │
│ └─────────────────┘  └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Design principles:**
- **Narrative-centric:** Story feed is the largest, most prominent element
- **Agent state visible:** Quick glance at agents without needing to expand
- **Controls bottom:** Playback and investigation accessible but not intrusive
- **Responsive:** Mobile-friendly (portrait on phone, landscape on tablet)

### 7.2 Agent Card Detail Panel (Expanded)

When clicking on an agent card, expand to show full details:

```
┌─────── Alice (The Scholar) ────────────────────────────────┐
│                                                             │
│ Room: Study                    Goal: Find the exit code    │
│ Inventory: [Golden Key] [Book] [Chalk]                     │
│                                                             │
│ Status: 🟢 Active (Examining desk drawer)                  │
│ Confidence: ████░░░░░ (45% sure about next move)          │
│ Emotional: 🤔 Confused but determined                      │
│                                                             │
│ ─ Recent Actions ─────────────────────────────────────────│
│ • Tick 23: Examined painting (found clue!)                │
│ • Tick 22: Picked up key from behind painting             │
│ • Tick 21: Examined painting closer                       │
│                                                             │
│ ─ Current Focus ───────────────────────────────────────────│
│ "I need to find the exit code. I have a key and a book.  │
│  Maybe the book contains the code?"                       │
│                                                             │
│ ─ Available Actions ────────────────────────────────────────│
│ ┌──────────────────────────────────────────────────────┐  │
│ │ Suggest Action:                                      │  │
│ │ [ Examine ] [ Move ] [ Use ] [ Talk ] [Take Key ]   │  │
│ │            (dropdown selections for nearby objects)  │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐  │
│ │ Send Hint: "The book may have the code you need"     │  │
│ │ [Nudge] (1 available per puzzle)                     │  │
│ └──────────────────────────────────────────────────────┘  │
│                                                             │
│ ─ Personality Sliders ─────────────────────────────────────│
│ Cautious ◄─────●───────► Aggressive                       │
│ Logical  ◄──────────●──► Intuitive                        │
│ Solo     ◄──────────────●► Cooperative                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Sections:**
1. **Status at top:** Room, goal, inventory
2. **Emotional state:** Visual indicator + text
3. **Recent actions:** Last 3-5 ticks (what was Alice doing)
4. **Current focus:** Alice's stated goal (what she's trying to do)
5. **Quick action suggestions:** Nearby objects that can be interacted with
6. **Nudge/hint interface:** Send guidance
7. **Personality sliders:** Adjust behavior mid-story

### 7.3 Investigation Board (Full View)

A detailed knowledge graph of all clues, puzzles, and dependencies:

```
┌────────── Investigation Board ──────────────────────────────────┐
│ Scenario: Escape Ravenwood Manor                   [Close ✕]   │
│                                                                  │
│ Legend: ✓ Discovered  ○ Hidden  ✗ Failed  [⚠] In Progress    │
│                                                                  │
│ ┌─── GOAL ────────────────────────────────────────────────────┐ │
│ │ Exit the manor through the front door                       │ │
│ │ ○ Find master key                                           │ │
│ │    ├─ ✓ Find golden key (Alice)                            │ │
│ │    ├─ ○ Find silver key (Hidden in bookshelf)              │ │
│ │    └─ ○ Combine golden + silver = master key              │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─── CLUES BY LOCATION ───────────────────────────────────────┐ │
│ │ STUDY                                                       │ │
│ │  ├─ Painting [✓ Alice found]                              │ │
│ │  │  └─ Hidden behind: Golden Key [✓ Alice took]           │ │
│ │  ├─ Desk Drawer [○ Not yet examined]                      │ │
│ │  │  └─ Contains: Combination lock [○]                     │ │
│ │  │     └─ Code: "1-2-3" [○]                               │ │
│ │  └─ Bookshelf [⚠ Alice examining now]                     │ │
│ │     └─ Book: "Mysteries of Ravenwood" [○]                │ │
│ │        └─ Contains: Exit code [○]                         │ │
│ │                                                             │ │
│ │ KITCHEN                                                     │ │
│ │  ├─ Table [✓ Bob examined]                                │ │
│ │  │  └─ Item: Rope [✓ Bob took]                            │ │
│ │  ├─ Cabinet [✓ Bob examined]                              │ │
│ │  │  └─ Item: Empty                                         │ │
│ │  └─ Counter [○ Not yet examined]                          │ │
│ │     └─ Item: ??? [○]                                       │ │
│ │                                                             │ │
│ │ BASEMENT                                                    │ │
│ │  ├─ Machinery [⚠ Charlie examining]                       │ │
│ │  │  └─ Item: Silver Key (maybe?) [○]                      │ │
│ │  └─ Stairs [○]                                            │ │
│ │     └─ Leads to: (Unknown area) [○]                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─── PUZZLES & DEPENDENCIES ──────────────────────────────────┐ │
│ │                                                              │ │
│ │ [✓ SOLVED] Golden Key (Found behind painting)              │ │
│ │    ↓                                                         │ │
│ │ [⚠ IN PROGRESS] Combination Lock (Needs code)              │ │
│ │    Requires: Code (not yet found)                          │ │
│ │    Alternative: Brute-force? (Time penalty)                │ │
│ │    ↓                                                         │ │
│ │ [○ LOCKED] Treasure Chest (Has silver key)                 │ │
│ │    Requires: Combination lock solved                       │ │
│ │    ↓                                                         │ │
│ │ [○ LOCKED] Master Lock (Front door)                        │ │
│ │    Requires: Master key (golden + silver combined)         │ │
│ │    ↓                                                         │ │
│ │ [○ GOAL] Escape the manor!                                 │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─── AGENT KNOWLEDGE COMPARISON ──────────────────────────────┐ │
│ │ Alice knows:     ✓ Golden key, ✓ Painting, ○ Combination │ │
│ │ Bob knows:       ✓ Rope, ✓ Kitchen, ○ Combination        │ │
│ │ Charlie knows:   ○ (Nothing yet)                           │ │
│ │                                                              │ │
│ │ Spectator knows: [All of the above + hidden clues]        │ │
│ │                                                              │ │
│ └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ Progress: 3/8 clues found | 1/4 puzzles solved | ETA: 15 mins  │
│                                                                  │
└────────────────────────────────────────────────────────────────────┘
```

**Key features:**
- Hierarchical clue list (by location and type)
- Visual indicators (✓, ○, ✗, ⚠) for state
- Who discovered each clue (agent names)
- Puzzle dependency graph
- Agent knowledge comparison (what each agent knows vs. hidden clues)
- Progress tracking (clues found, puzzles solved, estimated time)

### 7.4 Narrative Feed with Reasoning Bubbles

The main story display should integrate agent decision-making visually:

```
┌────────────────────────────────────────────────────┐
│                                                    │
│  _The study smells of old leather and dust._      │
│                                                    │
│  Alice examines the painting on the wall. Its     │
│  ornate frame catches the light.                  │
│                                                    │
│  ┌─ Alice's Reasoning ──────────────────────────┐ │
│  │ "This painting looks important. I should    │ │
│  │  examine it more closely. Maybe there's     │ │
│  │  something behind it?"                       │ │
│  └───────────────────────────────────────────────┘ │
│                                                    │
│  She runs her fingers along the frame. Something  │
│  catches—a hidden latch. With a soft click, the   │
│  painting swings outward, revealing a small       │
│  alcove.                                          │
│                                                    │
│  ✨ Discovery! Alice found the Golden Key! ✨    │
│  [Investigation Board updated]                   │
│                                                    │
│  [⏸ PAUSED for major discovery]                  │
│  [Continue Reading] [View Investigation Board]   │
│                                                    │
└────────────────────────────────────────────────────┘
```

**Features:**
- **Narrative prose:** 2-4 sentence bursts (from narrator)
- **Reasoning bubbles:** Alice's internal decision logic (from agent's system prompt extraction)
- **Discovery callouts:** Highlight major finds in color/style
- **Pause overlays:** Action buttons when auto-paused
- **Scroll naturally:** Feels like reading a book

### 7.5 Nudge/Hint Interface

When user wants to nudge an agent:

```
┌────────────── Send Hint to Alice ───────────────┐
│                                                 │
│ What should Alice focus on?                    │
│                                                 │
│ Suggested hints (based on world state):        │
│ ◉ "The painting might hide something"         │
│ ○ "Look more carefully at the desk"           │
│ ○ "Someone mentioned seeing a key"            │
│                                                 │
│ Or write your own hint:                        │
│ ┌─────────────────────────────────────────┐   │
│ │ You could try...                        │   │
│ │                                         │   │
│ │                                         │   │
│ └─────────────────────────────────────────┘   │
│ Character limit: 80/140                       │
│                                                 │
│ [Cancel] [Send Nudge]                         │
│                                                 │
│ ⓘ This nudge will influence Alice's next     │
│   decision. It won't force action, just add   │
│   weight to the selected option.              │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Features:**
- System-suggested hints (smart suggestions based on state)
- Free-form hint entry
- Character limit to keep hints concise
- Explanation of how nudges work
- Confirmation before sending

### 7.6 Decision Moment (Voting)

When the system detects a meaningful choice point:

```
┌──────────── Decision Moment ──────────────────┐
│                                               │
│ Alice is at the hallway junction. Which way? │
│                                               │
│ [📊] View reasoning / [👥] View votes         │
│                                               │
│ ┌─ Option A: Go NORTH (Kitchen) ──────────┐  │
│ │                                         │  │
│ │ What Alice might find:                 │  │
│ │ • Food, supplies                       │  │
│ │ • A locked cabinet (needs key)         │  │
│ │ • Rope (utility item)                  │  │
│ │                                         │  │
│ │ Votes: ████░░░░░░ 40% (4 votes)       │  │
│ │ [Cast your vote] [← Prev option]       │  │
│ └─────────────────────────────────────────┘  │
│                                               │
│ ┌─ Option B: Go WEST (Study) ──────────────┐ │
│ │                                          │ │
│ │ What Alice might find:                  │ │
│ │ • Books and writing materials           │ │
│ │ • A locked desk (needs key)             │ │
│ │ • Clues about the mansion's history     │ │
│ │                                          │ │
│ │ Votes: ██████░░░░ 60% (6 votes)        │ │
│ │ [Cast your vote] [Next option →]        │ │
│ └──────────────────────────────────────────┘ │
│                                               │
│ Time remaining: 12s                          │
│ [Auto-resolve if no votes] [Manual: West]   │
│                                               │
└───────────────────────────────────────────────┘
```

**Features:**
- Clear choice presentation (what might be found in each direction)
- Real-time vote tallies
- Time countdown
- Manual resolution option
- Agent reasoning for why they're at this junction

### 7.7 Checkpoint/Rewind Menu

Access past saves and branch timelines:

```
┌────────── Timeline & Checkpoints ─────────────────────┐
│                                                        │
│ Current Branch: Original Run                          │
│ Current Position: Tick 35 (Study, puzzle-solving)    │
│                                                        │
│ ┌─── Auto-saves ──────────────────────────────────┐  │
│ │ [Tick 30] Alice finds golden key     Saved: 2m ago│ │
│ │ [Tick 25] Bob explores kitchen       Saved: 7m ago│ │
│ │ [Tick 20] Charlie starts basement    Saved: 12m ago
│ │ [Tick 10] All agents in separate rooms (start)    │ │
│ │                                                    │ │
│ │ Hover for preview / [Load] to jump               │ │
│ └────────────────────────────────────────────────────┘  │
│                                                        │
│ ┌─── Alternate Branches (What-If Replays) ────────┐  │
│ │ ✕ "Faster route" (Tick 35)                     │  │
│ │   Load from Tick 25, nudged Charlie to basement  │  │
│ │   Result: Found silver key early! (13 mins)     │  │
│ │   [Compare outcomes] [Delete branch]            │  │
│ │                                                   │  │
│ │ ✕ "Alternate puzzle order" (Tick 28)            │  │
│ │   Load from Tick 20, voted for kitchen first     │  │
│ │   Result: Stuck on code (gave up at 25 mins)    │  │
│ │   [Compare outcomes] [Delete branch]            │  │
│ │                                                   │  │
│ │ [+ Create new branch]                           │  │
│ └────────────────────────────────────────────────────┘  │
│                                                        │
│ [Resume Current] [Compare Branches] [Close]         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**Features:**
- Timeline of auto-saves (chronological)
- Quick preview on hover
- One-click load to jump to checkpoint
- Alternate branches from what-if replays
- Outcome comparison (time, clues found, puzzles solved)
- Branch management (delete old experiments)

---

## 8. Implementation Roadmap

### Phase 1: Core Spectator Foundation (Weeks 1-2)
- [ ] Narrative feed UI (scrollable story display)
- [ ] Agent overview cards (status, inventory, location)
- [ ] Playback controls (play/pause/speed)
- [ ] Rename "tick" to "turn" in narrative (human-friendly)
- [ ] Auto-pause at major events
- [ ] Tests: rendering, playback control logic

### Phase 2: Agent Interaction (Weeks 3-4)
- [ ] Nudge system (send hints to agents)
- [ ] Suggest Action interface (right-click agent → action dropdown)
- [ ] Personality sliders (cautious ↔ aggressive, etc.)
- [ ] Tests: nudge persistence, personality weight adjustments, action suggestions

### Phase 3: Knowledge & Investigation (Weeks 5-6)
- [ ] Investigation Board UI (clue graph, puzzle tree)
- [ ] Dramatic Irony panel (what agents don't know)
- [ ] Knowledge comparison (agent vs. world state)
- [ ] Tests: knowledge inference, irony detection, clue tracking

### Phase 4: Decision Moments & Checkpoints (Weeks 7-8)
- [ ] Decision voting system (detect choice points, collect votes)
- [ ] Checkpoint/rewind system (auto-saves, manual loading)
- [ ] Branch timeline UI (compare alternate runs)
- [ ] Tests: choice point detection, branch persistence, outcome comparison

### Phase 5: Polish & Edge Cases (Weeks 9-10)
- [ ] Mobile responsiveness (phone/tablet layouts)
- [ ] Accessibility (screen readers, keyboard nav)
- [ ] Performance optimization (smooth scrolling, 100+ ticks)
- [ ] Error handling (agent failures, network timeouts)
- [ ] Tests: responsiveness, accessibility, load testing

---

## 9. Technical Integration with AgentTown

### 9.1 Changes to Existing Architecture

**In `agenttown/server.py`:**
- Add WebSocket messages for:
  - Nudge sent to agent (adds hint to perception)
  - Personality adjustment (modifies system prompt weights)
  - Suggested actions (provides shortlist to agent decision logic)
  - Investigation board state (what user should see)
  - Dramatic irony data (knowledge gaps)

**In `agenttown/agents/brain.py`:**
- Extract "reasoning" from Claude's response before action (the internal monologue)
- Broadcast agent reasoning to spectators each tick
- Apply nudge weights to next decision cycle (hint in system prompt)
- Apply personality sliders (adjust risk/reward weights)

**In `agenttown/agents/prompts.py`:**
- Add hint instructions to PERCEPTION_TEMPLATE: `{hints}`
- Add reasoning extraction prompt: "Before acting, explain your thinking"
- Add personality modifier template based on slider values

**In `agenttown/world/events.py`:**
- Extend Event to include `discovered_by: [agent_ids]` (for dramatic irony)
- Add event metadata: `world_state_snapshot` for checkpoint restoration

**In `agenttown/persistence.py`:**
- Extend GameStore to track branches (same scenario, different save paths)
- Add branch metadata: which nudges/votes were applied

### 9.2 New Modules

**`agenttown/spectator/knowledge.py`**
- Track what each agent has discovered
- Generate investigation board state
- Compute dramatic irony (knowledge gaps)
- Suggest nudges based on state analysis

**`agenttown/spectator/pacing.py`**
- Detect major events (discoveries, failures, dialogue)
- Calculate pause durations
- Auto-speed suggestions for boring ticks
- Smooth speed transitions

**`agenttown/spectator/decisions.py`**
- Detect choice points (multiple meaningful paths)
- Collect user votes
- Weight agent decisions based on votes
- Explain choice branches to user

**`agenttown/spectator/reasoning.py`**
- Extract agent reasoning from Claude response
- Format for display (convert internal monologue to readable thinking)
- Cache for instant replay

---

## 10. Design Principles Summary

1. **Spectator is the reader, agents are the characters.** Adapt AI Dungeon's control for characters the player doesn't command, but can nudge.

2. **Dramatic irony drives engagement.** Show user what agents don't know. This creates tension and justifies the nudge system.

3. **Intervention should feel natural.** Nudges, suggestions, and votes should integrate into the narrative, not break the fourth wall.

4. **Pacing varies with intensity.** Major moments are slow and pausable. Travel and repetition auto-speed. Smart defaults save user effort.

5. **Checkpoints enable experimentation.** Replay with different nudges/votes without losing the original run. This is the killer feature for a spectator experience.

6. **Agent personality matters.** Sliders for risk/coordination/intuition let user shape character behavior mid-story without dictating action.

7. **Show reasoning, not just results.** Let user see agent thinking ("I should examine the painting because..."). This makes agents feel like real characters, not black boxes.

8. **Investigation board is the "world info."** Instead of AI Dungeon's lore list, show clue locations, puzzle dependencies, and what agents know. This is core to the spectator's understanding.

---

## Appendix: Example Spectator Session

### The Setup
- Scenario: Escape Ravenwood Manor (escape room, 3 agents)
- Agents: Alice (Scholar), Bob (Engineer), Charlie (Explorer)
- User (Spectator): Watching, can nudge/vote/rewind

### The Flow

**Tick 1-10: Exploration**
- Agents spread across three rooms
- Auto-speed set to 2x (nothing major happening)
- Spectator reads Investigation Board, sees it's mostly empty
- User pauses at Tick 5 to read a piece of atmospheric narration

**Tick 15: Alice's Discovery**
- Alice examines painting, finds hidden latch
- **AUTO-PAUSE** at Tick 15 ("Discovery!")
- Narrative: "_The painting swings outward, revealing a golden key._"
- Investigation Board updates (Golden Key discovered)
- Dramatic Irony panel: "Alice has key, but doesn't know what door it opens yet"
- User reads for 10 seconds, clicks "Continue"

**Tick 20-25: Decision Point**
- Bob reaches hallway junction (kitchen vs. study)
- **AUTO-PAUSE** with voting interface
- Spectator votes for "study" (majority vote: 60%)
- Bob's next decision gets +weight toward study
- Narrative frames it: "Bob takes a deep breath and heads west, toward the study"

**Tick 28: Bob Finds Combination Lock**
- Bob discovers locked cabinet in study
- Realizes he needs a code
- Spectator sees in Dramatic Irony: "Code is hidden in bookshelf book (not discovered yet)"
- Nudge button pulses: "You could help Bob find the code!"
- Spectator sends nudge: "That book on the shelf might be important"
- Bob's next action: likely to examine bookshelf

**Tick 30: Code Discovery**
- Bob examines bookshelf, finds book
- Reads code "1-2-3"
- **AUTO-PAUSE** ("Discovery!")
- Investigation Board updates
- Puzzle dependency revealed: "Now Bob can open the combination lock!"

**Tick 32-33: Puzzle Solving**
- Bob opens combination lock
- Inside: treasure chest with silver key
- **AUTO-PAUSE** ("Puzzle Solved!")
- Dramatic Irony: "Two keys exist. Must be combined for master key"
- Spectator reviews progress: 2/4 puzzles solved

**Tick 35: Stuck Agent**
- Charlie has been searching basement for 10+ ticks, found nothing
- System suggests: "Nudge available" / "Consider rewinding"
- Spectator nudges: "The machinery might have something valuable"
- Charlie examines machinery, finds master lock mechanism (new puzzle type)

**Tick 40: Major Realization**
- Agents realize master key = golden + silver combined
- Alice, Bob, and Charlie coordinate (dialogue)
- **AUTO-PAUSE** ("Major Realization")
- Dramatic Irony panel: "All agents now know what to do!"
- Spectator is rooting for them: "Come on team, you've got this!"

**Tick 42-43: Final Puzzle**
- Alice combines keys (uses agent "combine" action)
- Master key created
- Agents proceed to front door
- **AUTO-PAUSE** ("Goal Complete!")
- Narrative: "_The ancient lock groans as the key turns. The front door swings open. Fresh air floods in. They're free._"
- Spectator sees: SUCCESS in 43 ticks (9 minutes)

**Post-Game:**
- Spectator reviews timeline
- Creates "alternate branch": "What if we had prioritized basement first?"
- Rewinds to Tick 20, votes differently
- New run: 38 ticks (slightly faster)
- Compares outcomes in timeline view

---

## Appendix: Mockup Descriptions for Dev Handoff

When handing off to frontend developer:

1. **Narrative Feed:** Rich text display with agent reasoning bubbles inline. Streaming (new lines appear as ticks advance). Auto-pause overlays don't occlude story, appear bottom-right.

2. **Agent Cards:** 4-column grid (4 agents fits mobile width, expand to 6 for larger screens). Cards are 150px × 180px. Show status via color: 🟢 active, 🟡 stalled, 🔴 stuck. Inventory shown as tiny icons (1-3 items).

3. **Investigation Board:** Tree/graph view (Lucidchart-like). Nodes are clues, edges are dependencies. Hover for details. Color: ✓ green, ○ gray, ✗ red, ⚠️ yellow. Responsive: collapses to list view on mobile.

4. **Playback Controls:** Fixed bottom bar, always visible. Play/pause button is 48px. Speed slider can be tapped (mobile-friendly). Status text shows "Playing 1.0x" and "Next event: 5s".

5. **Nudge Interface:** Modal dialog, appears above agents. Suggested hints listed as radio buttons (easy one-tap selection). Free-form text input for custom hints.

6. **Decision Moment:** Full-screen modal, center-aligned. Shows 2-3 options, each with icon + description + vote tally. Vote button is prominent (40px tall). Time countdown visible.

7. **Checkpoint Timeline:** Horizontal scroll list, newest on right. Each checkpoint is a 100px × 60px card showing tick number and event summary. Branches shown as indented sub-list below main timeline.

---

**Document version:** 1.0
**Last updated:** 2025-02-28
**Status:** Ready for design/implementation review
