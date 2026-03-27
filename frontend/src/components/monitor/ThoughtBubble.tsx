/**
 * ThoughtBubble — shows agent reasoning near their status cards.
 *
 * When a tick arrives with events, each agent's actions are extracted and
 * displayed as a thought bubble. Bubbles animate in, then fade out after
 * ~6 seconds or when the next tick arrives. Per-agent toggle to mute bubbles.
 *
 * Since the backend doesn't send explicit LLM reasoning, we synthesize
 * thought-like summaries from the tick events: what the agent did, and
 * a brief inferred observation.
 *
 * Dark theme: bubble bg #1c2128, gold border for active thinking.
 *
 * Exhibition-grade elevation:
 *  - Typewriter reveal: text appears line-by-line with character-by-character
 *    typing effect and a blinking gold cursor
 *  - Breathing border: gold border pulses on a 3-second cycle
 *  - Exit animation: dissolve with blur + scaleY shrink, border extinguishes
 *    200ms before content
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Brain,
  Eye,
  EyeOff,
  MessageCircle,
  ArrowRight,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useNarrativeEvents,
  useAgents,
  useIsProcessing,
} from '@/stores/gameStore'
import type { TickEvent, NarrativeEntry } from '@/types/game'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ThoughtData {
  agentId: string
  agentName: string
  observation: string
  action: string
  reasoning: string
  tick: number
  timestamp: number
}

// ---------------------------------------------------------------------------
// Helpers — extract agent info from tick events
// ---------------------------------------------------------------------------

/**
 * Parse agent name from an event description. Events typically start with
 * "AgentName does something..." or mention agent names in context.
 */
function extractAgentFromEvent(
  event: TickEvent,
  agentNames: string[],
): string | null {
  for (const name of agentNames) {
    if (event.description.toLowerCase().includes(name.toLowerCase())) {
      return name
    }
  }
  return null
}

/**
 * Synthesize a thought from an event — what was observed, what was done, why.
 */
function synthesizeThought(event: TickEvent): {
  observation: string
  action: string
  reasoning: string
} {
  const desc = event.description

  switch (event.type) {
    case 'move':
      return {
        observation: 'Surveyed the area',
        action: desc,
        reasoning: 'Looking for new clues or paths forward',
      }
    case 'examine':
      return {
        observation: 'Something caught my attention',
        action: desc,
        reasoning: 'Investigating for hidden information',
      }
    case 'pick_up':
      return {
        observation: 'Found something useful',
        action: desc,
        reasoning: 'This might help solve a puzzle',
      }
    case 'use':
      return {
        observation: 'Realized a connection',
        action: desc,
        reasoning: 'Testing if this item works here',
      }
    case 'talk':
      return {
        observation: 'Need to share information',
        action: desc,
        reasoning: 'Coordinating with others might help',
      }
    case 'state_change':
      return {
        observation: 'Something changed!',
        action: desc,
        reasoning: 'Progress is being made',
      }
    case 'fail':
      return {
        observation: 'That did not work',
        action: desc,
        reasoning: 'Need to try a different approach',
      }
    default:
      return {
        observation: 'Assessing the situation',
        action: desc || 'Thinking...',
        reasoning: 'Considering next steps',
      }
  }
}

/**
 * Build thought data from the latest narrative entry's events.
 */
function buildThoughts(
  entry: NarrativeEntry,
  agentNames: string[],
  agentNameToId: Record<string, string>,
): ThoughtData[] {
  const thoughts: ThoughtData[] = []
  // Track one thought per agent per tick (use first meaningful event)
  const seenAgents = new Set<string>()

  for (const event of entry.events) {
    // Skip wait events
    if (event.type === 'wait') continue

    const agentName = extractAgentFromEvent(event, agentNames)
    if (!agentName || seenAgents.has(agentName)) continue
    seenAgents.add(agentName)

    const { observation, action, reasoning } = synthesizeThought(event)
    thoughts.push({
      agentId: agentNameToId[agentName] || agentName,
      agentName,
      observation,
      action,
      reasoning,
      tick: entry.tick,
      timestamp: entry.timestamp,
    })
  }

  return thoughts
}

// ---------------------------------------------------------------------------
// useTypewriter — custom hook for character-by-character text reveal
// ---------------------------------------------------------------------------

function useTypewriter(
  text: string,
  enabled: boolean,
  delay: number, // ms before typing starts
  speed: number = 15, // ms per character
): { displayed: string; isDone: boolean; showCursor: boolean } {
  const [charIndex, setCharIndex] = useState(0)
  const [started, setStarted] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!enabled) {
      setCharIndex(text.length)
      setStarted(true)
      return
    }

    setCharIndex(0)
    setStarted(false)

    // Initial delay before typing starts
    const startTimer = setTimeout(() => {
      setStarted(true)
    }, delay)

    return () => clearTimeout(startTimer)
  }, [text, enabled, delay])

  useEffect(() => {
    if (!started || charIndex >= text.length) return

    timerRef.current = setTimeout(() => {
      setCharIndex((prev) => prev + 1)
    }, speed)

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [started, charIndex, text.length, speed])

  return {
    displayed: text.slice(0, charIndex),
    isDone: charIndex >= text.length,
    showCursor: started && charIndex < text.length,
  }
}

// ---------------------------------------------------------------------------
// Single thought bubble component — with typewriter reveal and breathing border
// ---------------------------------------------------------------------------

function Bubble({
  thought,
  onDismiss,
  isVisible,
}: {
  thought: ThoughtData
  onDismiss: () => void
  isVisible: boolean
}) {
  // Track if we are in the exit phase (border extinguishes before content)
  const [isExiting, setIsExiting] = useState(false)
  const prevVisible = useRef(isVisible)

  useEffect(() => {
    if (prevVisible.current && !isVisible) {
      // Started exiting — border extinguishes first
      setIsExiting(true)
    }
    prevVisible.current = isVisible
  }, [isVisible])

  // Check prefers-reduced-motion
  const prefersReducedMotion = useMemo(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  const enableTypewriter = isVisible && !prefersReducedMotion

  // Typewriter reveals for each line, staggered
  const observation = useTypewriter(
    thought.observation,
    enableTypewriter,
    200, // 200ms delay before observation starts
    20,
  )
  const action = useTypewriter(
    thought.action,
    enableTypewriter,
    200 + thought.observation.length * 20 + 100, // starts after observation + gap
    15, // 15ms per char for action (faster for longer text)
  )
  const reasoning = useTypewriter(
    thought.reasoning,
    enableTypewriter,
    200 + thought.observation.length * 20 + 100 + thought.action.length * 15 + 200, // starts after action + gap
    18,
  )

  // Determine which line the cursor should be on
  const cursorLine = !observation.isDone
    ? 'observation'
    : !action.isDone
    ? 'action'
    : !reasoning.isDone
    ? 'reasoning'
    : null

  return (
    <div
      className={cn(
        'relative max-w-[300px] md:max-w-[340px]',
        'rounded-xl border-2 px-3 py-2.5 shadow-lg',
        // Dark theme bubble styling
        'bg-[#1c2128]',
        // Breathing border when visible (not exiting)
        isVisible && !isExiting && 'animate-breathing-border',
        // Border extinguish when starting to exit
        isExiting && !isVisible && 'animate-border-extinguish',
        // Exit dissolve animation
        isVisible
          ? 'opacity-100 translate-y-0 scale-100'
          : 'animate-thought-dissolve pointer-events-none',
        // Transition for non-animated properties
        'transition-none',
      )}
      style={{
        borderColor: isVisible && !isExiting ? undefined : 'rgba(227, 179, 65, 0.25)',
      }}
    >
      {/* Dismiss button */}
      <button
        onClick={onDismiss}
        className="absolute -top-1.5 -right-1.5 w-6 h-6 min-w-[24px] rounded-full bg-bg-tertiary border border-border flex items-center justify-center text-text-muted hover:text-text-primary transition-colors z-10"
        aria-label="Dismiss thought"
      >
        <X size={10} />
      </button>

      {/* Agent name header */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <Brain size={12} className="text-gold shrink-0" />
        <span className="text-xs font-bold text-gold truncate">
          {thought.agentName}
        </span>
        <span className="text-[9px] text-text-muted ml-auto shrink-0">
          Tick {thought.tick}
        </span>
      </div>

      {/* Observation — first to appear */}
      <div className="flex items-start gap-1.5 mb-1 min-h-[18px]">
        <Eye size={10} className="text-text-muted mt-0.5 shrink-0" />
        <span className="text-[11px] text-text-secondary leading-snug">
          {observation.displayed}
          {cursorLine === 'observation' && (
            <span
              className="inline-block w-[2px] h-[11px] ml-0.5 align-middle animate-cursor-blink"
              style={{ backgroundColor: '#e3b341' }}
            />
          )}
        </span>
      </div>

      {/* Action — types out character-by-character */}
      <div className="flex items-start gap-1.5 mb-1 min-h-[18px]">
        <ArrowRight size={10} className="text-gold-dim mt-0.5 shrink-0" />
        <span className="text-[11px] text-text-primary leading-snug line-clamp-2">
          {action.displayed}
          {cursorLine === 'action' && (
            <span
              className="inline-block w-[2px] h-[11px] ml-0.5 align-middle animate-cursor-blink"
              style={{ backgroundColor: '#e3b341' }}
            />
          )}
        </span>
      </div>

      {/* Reasoning — fades in last */}
      <div className="flex items-start gap-1.5 min-h-[16px]">
        <MessageCircle size={10} className="text-text-muted mt-0.5 shrink-0" />
        <span className="text-[10px] text-text-muted italic leading-snug">
          {reasoning.displayed}
          {cursorLine === 'reasoning' && (
            <span
              className="inline-block w-[2px] h-[10px] ml-0.5 align-middle animate-cursor-blink"
              style={{ backgroundColor: '#e3b341' }}
            />
          )}
        </span>
      </div>

      {/* Speech bubble tail */}
      <div
        className="absolute -bottom-1.5 left-6 w-3 h-3 rotate-45 bg-[#1c2128]"
        style={{
          borderBottom: '2px solid',
          borderRight: '2px solid',
          borderColor: 'inherit',
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ThoughtBubbles component
// ---------------------------------------------------------------------------

export function ThoughtBubbles() {
  const narrativeEvents = useNarrativeEvents()
  const agentsRecord = useAgents()
  const isProcessing = useIsProcessing()

  const agents = useMemo(() => Object.values(agentsRecord), [agentsRecord])
  const agentNames = useMemo(() => agents.map((a) => a.name), [agents])
  const agentNameToId = useMemo(() => {
    const map: Record<string, string> = {}
    for (const a of agents) {
      map[a.name] = a.id
    }
    return map
  }, [agents])

  // Per-agent mute state
  const [mutedAgents, setMutedAgents] = useState<Set<string>>(new Set())

  // Current thoughts (from latest tick)
  const [thoughts, setThoughts] = useState<ThoughtData[]>([])
  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set())

  // Track which tick we last processed
  const lastProcessedTick = useRef(-1)

  // Fade-out timer
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // When new narrative events arrive, extract thoughts
  useEffect(() => {
    if (narrativeEvents.length === 0) return
    const latest = narrativeEvents[narrativeEvents.length - 1]

    // Only process new ticks
    if (latest.tick <= lastProcessedTick.current) return
    lastProcessedTick.current = latest.tick

    const newThoughts = buildThoughts(latest, agentNames, agentNameToId)
      .filter((t) => !mutedAgents.has(t.agentId))

    if (newThoughts.length === 0) return

    setThoughts(newThoughts)
    setVisibleIds(new Set(newThoughts.map((t) => t.agentId)))

    // Clear previous fade timer
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)

    // Start fade-out after 6 seconds
    fadeTimerRef.current = setTimeout(() => {
      setVisibleIds(new Set())
      // Actually remove after dissolve transition completes (500ms for dissolve)
      setTimeout(() => setThoughts([]), 600)
    }, 6000)

    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current)
    }
  }, [narrativeEvents, agentNames, agentNameToId, mutedAgents])

  // Clear thoughts when a new processing cycle starts
  useEffect(() => {
    if (isProcessing) {
      setVisibleIds(new Set())
      setTimeout(() => setThoughts([]), 600)
    }
  }, [isProcessing])

  const toggleMute = useCallback((agentId: string) => {
    setMutedAgents((prev) => {
      const next = new Set(prev)
      if (next.has(agentId)) {
        next.delete(agentId)
      } else {
        next.add(agentId)
      }
      return next
    })
  }, [])

  const dismissThought = useCallback((agentId: string) => {
    setVisibleIds((prev) => {
      const next = new Set(prev)
      next.delete(agentId)
      return next
    })
  }, [])

  // Don't render if no agents
  if (agents.length === 0) return null

  return (
    <div className="shrink-0 border-b border-border bg-bg-primary/50">
      {/* Toggle bar — per-agent mute controls */}
      <div className="flex items-center gap-2 px-3 py-1.5 overflow-x-auto scrollbar-none md:px-4">
        <Brain size={14} className="text-gold shrink-0" />
        <span className="text-[10px] text-text-muted shrink-0 mr-1">Thoughts:</span>
        {agents.map((agent) => (
          <button
            key={agent.id}
            onClick={() => toggleMute(agent.id)}
            className={cn(
              'shrink-0 flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium min-h-[32px]',
              'transition-all duration-150',
              mutedAgents.has(agent.id)
                ? 'bg-bg-tertiary text-text-muted border border-border'
                : 'bg-gold/10 text-gold border border-gold/20',
            )}
            aria-label={mutedAgents.has(agent.id) ? `Show ${agent.name} thoughts` : `Hide ${agent.name} thoughts`}
            title={mutedAgents.has(agent.id) ? 'Click to show thoughts' : 'Click to hide thoughts'}
          >
            {mutedAgents.has(agent.id) ? <EyeOff size={10} /> : <Eye size={10} />}
            {agent.name.length > 10 ? agent.name.slice(0, 9) + '...' : agent.name}
          </button>
        ))}
      </div>

      {/* Thought bubbles area */}
      {thoughts.length > 0 && (
        <div className="flex gap-3 px-3 pb-2 overflow-x-auto scrollbar-none md:px-4 md:flex-wrap">
          {thoughts.map((thought) => (
            <Bubble
              key={`${thought.agentId}-${thought.tick}`}
              thought={thought}
              isVisible={visibleIds.has(thought.agentId)}
              onDismiss={() => dismissThought(thought.agentId)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
