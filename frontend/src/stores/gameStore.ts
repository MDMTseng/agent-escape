/**
 * Zustand store for all game state.
 *
 * State is populated by incoming WebSocket messages (dispatched through
 * `updateFromMessage`). The store is the single source of truth for the
 * entire game UI -- components read slices via typed selectors exported
 * at the bottom of this file.
 */

import { create } from 'zustand';
import type {
  AgentState,
  ConnectionStatus,
  Door,
  EscapeChainStep,
  NarrativeEntry,
  Room,
  ServerMessage,
  TokenUsage,
  WorldState,
} from '@/types/game';

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

export interface GameState {
  // Connection
  connectionStatus: ConnectionStatus;

  // World state (mirrors WorldState from backend)
  worldState: WorldState | null;

  // Convenience slices derived on write from worldState
  rooms: Record<string, Room>;
  agents: Record<string, AgentState>;
  doors: Record<string, Door>;

  // Escape chain progress
  escapeChain: EscapeChainStep[];

  // Narrative feed -- accumulated across ticks
  narrativeEvents: NarrativeEntry[];

  // Current tick
  tick: number;

  // Simulation control state
  isPlaying: boolean;
  isProcessing: boolean;
  processingMessage: string;

  // Game finish state
  isFinished: boolean;
  finishReason: string;

  // Story context (set when loading/creating a story via API, not from WS)
  storyId: number | null;
  storyContext: {
    title: string;
    theme: string;
    premise: string;
    difficulty: number;
  } | null;

  // Token usage (dev/debug)
  tokenUsage: TokenUsage;

  // -----------------------------------------------------------------------
  // Actions
  // -----------------------------------------------------------------------

  /** Update connection status. Called by the WebSocket hook. */
  setConnectionStatus: (status: ConnectionStatus) => void;

  /** Dispatch an incoming WebSocket message to the correct state slices. */
  updateFromMessage: (msg: ServerMessage) => void;

  /** Set story metadata (called after API responses, not from WS). */
  setStoryContext: (
    storyId: number | null,
    context: GameState['storyContext'],
  ) => void;

  /** Reset all state to initial values. */
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Initial / default values
// ---------------------------------------------------------------------------

const INITIAL_TOKEN_USAGE: TokenUsage = {
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
};

const initialState = {
  connectionStatus: 'disconnected' as ConnectionStatus,
  worldState: null as WorldState | null,
  rooms: {} as Record<string, Room>,
  agents: {} as Record<string, AgentState>,
  doors: {} as Record<string, Door>,
  escapeChain: [] as EscapeChainStep[],
  narrativeEvents: [] as NarrativeEntry[],
  tick: 0,
  isPlaying: false,
  isProcessing: false,
  processingMessage: '',
  isFinished: false,
  finishReason: '',
  storyId: null as number | null,
  storyContext: null as GameState['storyContext'],
  tokenUsage: { ...INITIAL_TOKEN_USAGE },
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useGameStore = create<GameState>()((set, get) => ({
  ...initialState,

  // -- Connection -----------------------------------------------------------

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  // -- Message dispatcher ---------------------------------------------------

  updateFromMessage: (msg) => {
    switch (msg.type) {
      // Full state snapshot (on connect, after reset, after load, after generate)
      case 'snapshot': {
        const ws = msg.world_state;
        set({
          worldState: ws,
          rooms: ws.rooms,
          agents: ws.agents,
          doors: ws.doors,
          tick: msg.tick,
          isPlaying: !msg.paused,
          isFinished: ws.finished,
          finishReason: ws.finish_reason,
          isProcessing: false,
          processingMessage: '',
          // Replace escape chain if provided, otherwise keep existing
          ...(msg.escape_chain ? { escapeChain: msg.escape_chain } : {}),
        });
        break;
      }

      // Per-tick update with events and narrative
      case 'tick': {
        const ws = msg.world_state;
        const newEntry: NarrativeEntry = {
          tick: msg.tick,
          text: msg.narrative,
          events: msg.events,
          timestamp: Date.now(),
        };
        set((state) => ({
          worldState: ws,
          rooms: ws.rooms,
          agents: ws.agents,
          doors: ws.doors,
          tick: msg.tick,
          escapeChain: msg.escape_chain,
          // Append narrative (cap at 500 entries to bound memory)
          narrativeEvents: [...state.narrativeEvents, newEntry].slice(-500),
          tokenUsage: msg.token_usage,
          isFinished: ws.finished,
          finishReason: ws.finish_reason,
          isProcessing: false,
          processingMessage: '',
        }));
        break;
      }

      // Agents are thinking
      case 'processing': {
        set({
          isProcessing: true,
          processingMessage: msg.message,
        });
        break;
      }

      // Game finished
      case 'finished': {
        const finishEntry: NarrativeEntry = {
          tick: get().tick,
          text: msg.narrative || `Game Over: ${msg.reason}`,
          events: [],
          timestamp: Date.now(),
        };
        set((state) => ({
          isFinished: true,
          finishReason: msg.reason,
          isPlaying: false,
          isProcessing: false,
          narrativeEvents: [...state.narrativeEvents, finishEntry].slice(-500),
        }));
        break;
      }

      // Game already finished (idle)
      case 'finished_idle': {
        set({
          isFinished: true,
          isPlaying: false,
          isProcessing: false,
          tick: msg.tick,
        });
        break;
      }

      // Game paused
      case 'paused': {
        set({
          isPlaying: false,
          isProcessing: false,
          tick: msg.tick,
        });
        break;
      }
    }
  },

  // -- Story context --------------------------------------------------------

  setStoryContext: (storyId, context) =>
    set({ storyId, storyContext: context }),

  // -- Reset ----------------------------------------------------------------

  reset: () => set({ ...initialState }),
}));

// ---------------------------------------------------------------------------
// Typed selectors -- convenience hooks for components
// ---------------------------------------------------------------------------

/** All rooms as a record. */
export const useRooms = () => useGameStore((s) => s.rooms);

/** All rooms as an array. */
export const useRoomList = () =>
  useGameStore((s) => Object.values(s.rooms));

/** All agents as a record. */
export const useAgents = () => useGameStore((s) => s.agents);

/** All agents as an array. */
export const useAgentList = () =>
  useGameStore((s) => Object.values(s.agents));

/** All doors as a record. */
export const useDoors = () => useGameStore((s) => s.doors);

/** Escape chain steps. */
export const useEscapeChain = () => useGameStore((s) => s.escapeChain);

/** Number of solved escape chain steps. */
export const useSolvedStepCount = () =>
  useGameStore((s) => s.escapeChain.filter((step) => step.status === 'solved').length);

/** Narrative events feed. */
export const useNarrativeEvents = () => useGameStore((s) => s.narrativeEvents);

/** Current tick number. */
export const useTick = () => useGameStore((s) => s.tick);

/** WebSocket connection status. */
export const useConnectionStatus = () => useGameStore((s) => s.connectionStatus);

/** Whether the simulation is running (not paused). */
export const useIsPlaying = () => useGameStore((s) => s.isPlaying);

/** Whether agents are currently thinking. */
export const useIsProcessing = () => useGameStore((s) => s.isProcessing);

/** Processing status message. */
export const useProcessingMessage = () => useGameStore((s) => s.processingMessage);

/** Whether the game has ended. */
export const useIsFinished = () => useGameStore((s) => s.isFinished);

/** Reason the game finished. */
export const useFinishReason = () => useGameStore((s) => s.finishReason);

/** Full world state object (or null if not loaded). */
export const useWorldState = () => useGameStore((s) => s.worldState);

/** Story ID. */
export const useStoryId = () => useGameStore((s) => s.storyId);

/** Story context metadata. */
export const useStoryContext = () => useGameStore((s) => s.storyContext);

/** Token usage stats. */
export const useTokenUsage = () => useGameStore((s) => s.tokenUsage);

/** Selector for a single agent by ID. */
export const useAgent = (agentId: string) =>
  useGameStore((s) => s.agents[agentId] ?? null);

/** Selector for a single room by ID. */
export const useRoom = (roomId: string) =>
  useGameStore((s) => s.rooms[roomId] ?? null);

/** Agents in a specific room. */
export const useAgentsInRoom = (roomId: string) =>
  useGameStore((s) =>
    Object.values(s.agents).filter((a) => a.room_id === roomId),
  );
