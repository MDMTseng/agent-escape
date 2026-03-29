/**
 * AgentMemoryInspector — slide-out panel showing an agent's memory architecture.
 *
 * Since the backend doesn't expose LLMBrain memory over WebSocket, we synthesize
 * a rich memory model from tick events and narrative data on the client side.
 * This mirrors the three-tier architecture from agenttown/agents/memory.py:
 *   - Working Memory: key facts the agent has discovered (pinned notes)
 *   - Memory Stream: chronological log of observations with importance scores
 *   - Reflections: periodic higher-level summaries
 *
 * Visual metaphor: a detective's case notebook — handwritten feel, pinned notes,
 * worn paper textures through color and shadow.
 *
 * Exhibition-grade elevation (curator feedback):
 *  - Entrance ritual: radial gold spotlight expand + scale(0.97)->1 + blur->focus
 *  - Importance as heat: card-level thermal glow replaces numbered badges
 *  - Memory decay: opacity gradient on older stream entries
 *  - Reflection ceremony: typewriter text reveal + breathing purple border
 *  - Search as spotlight: non-matching memories dim instead of being removed
 *
 * Mobile: bottom sheet (90vh, swipe to dismiss)
 * Desktop: side panel sliding in from right
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  Brain,
  Pin,
  Clock,
  Search,
  X,
  Sparkles,
  BookOpen,
  Eye,
  MessageCircle,
  Zap,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNarrativeEvents, useTick } from '@/stores/gameStore'
import type { AgentState, NarrativeEntry } from '@/types/game'

// ---------------------------------------------------------------------------
// Synthesized memory types (mirrors backend memory.py MemoryEntry)
// ---------------------------------------------------------------------------

interface SynthMemory {
  id: string
  tick: number
  content: string
  category: 'observation' | 'action' | 'discovery' | 'conversation' | 'failure'
  importance: number // 1-5
  isRetrieved: boolean // highlighted as used for latest decision
}

interface SynthReflection {
  id: string
  tick: number
  content: string
}

// ---------------------------------------------------------------------------
// Memory synthesis — extract structured memories from tick events
// ---------------------------------------------------------------------------

function synthesizeMemories(
  agentName: string,
  narrativeEvents: NarrativeEntry[],
): { workingMemory: string[]; stream: SynthMemory[]; reflections: SynthReflection[] } {
  const stream: SynthMemory[] = []
  const facts = new Set<string>()
  const reflections: SynthReflection[] = []
  let memoryIdCounter = 0

  const roomsVisited = new Set<string>()
  const objectsExamined = new Set<string>()

  for (const entry of narrativeEvents) {
    for (const event of entry.events) {
      const desc = event.description.toLowerCase()
      const agentLower = agentName.toLowerCase()

      // Only process events involving this agent
      if (!desc.includes(agentLower)) continue

      const id = `mem-${memoryIdCounter++}`
      let category: SynthMemory['category'] = 'observation'
      let importance = 2

      // Categorize and score importance
      if (event.type === 'move') {
        category = 'observation'
        importance = 1
        // Track rooms visited
        const enterMatch = event.description.match(/enters?\s+(.+)/i)
        if (enterMatch) roomsVisited.add(enterMatch[1].slice(0, 30))
      } else if (event.type === 'examine') {
        category = 'observation'
        importance = 3

        // "X examines ObjName: description" — extract object name
        const examineMatch = event.description.match(/examines?\s+(.+?):/i)
        if (examineMatch) {
          objectsExamined.add(examineMatch[1].slice(0, 40))
        }

        // Extract quoted clues/inscriptions
        const quotedMatch = event.description.match(/"([^"]{5,})"/)
        if (quotedMatch) {
          facts.add(`Clue: "${quotedMatch[1].slice(0, 55)}"`)
          importance = 4
        }

        // Extract single-quoted passwords/keywords
        const singleQuoted = event.description.match(/'([^']{3,30})'/g)
        if (singleQuoted) {
          singleQuoted.forEach(q => {
            const word = q.replace(/'/g, '')
            facts.add(`Keyword: "${word}"`)
          })
          importance = Math.max(importance, 4)
        }

        // Extract object state info ("It is unlocked", "It is locked")
        const stateMatch = event.description.match(/It is (unlocked|locked|open|closed|broken|sealed)/i)
        if (stateMatch && examineMatch) {
          facts.add(`${examineMatch[1].slice(0, 25)}: ${stateMatch[1]}`)
          importance = Math.max(importance, 3)
        }

        // Extract "reads:" clue text
        const readsMatch = event.description.match(/reads?:\s*"?([^"]{5,80})"?/i)
        if (readsMatch) {
          facts.add(`Inscription: "${readsMatch[1].slice(0, 55)}"`)
          importance = 4
        }

        // Discover/reveal events within examine
        if (desc.includes('reveal') || desc.includes('hidden') || desc.includes('secret')) {
          const revealMatch = event.description.match(/(?:reveals?|hidden|secret)\s+(.{5,50})/i)
          if (revealMatch) {
            facts.add(`Found: ${revealMatch[1].slice(0, 45)}`)
            importance = 5
          }
        }
      } else if (event.type === 'pick_up') {
        category = 'discovery'
        importance = 3
        const itemMatch = event.description.match(/picks?\s+up\s+(?:the\s+)?(.+)/i)
        if (itemMatch) facts.add(`Has: ${itemMatch[1].slice(0, 40)}`)
      } else if (event.type === 'use' || event.type === 'state_change') {
        category = 'action'
        importance = 4
        if (desc.includes('unlock') || desc.includes('solved') || desc.includes('open')) {
          importance = 5
          const target = event.description.match(/(?:unlocks?|solves?|opens?)\s+(?:the\s+)?(.+)/i)
          if (target) facts.add(`SOLVED: ${target[1].slice(0, 40)}`)
        }
      } else if (event.type === 'talk') {
        category = 'conversation'
        importance = 2
        // Don't extract speech fragments as facts — they pollute working memory.
        // Real clues come from examine/interact results.
      } else if (event.type === 'fail') {
        category = 'failure'
        importance = 3
        const failMatch = event.description.match(/(?:can't|tries to|fails to)\s+(.+)/i)
        if (failMatch) facts.add(`FAILED: ${failMatch[1].slice(0, 40)}`)
      }

      // Extract number codes from non-talk events
      if (event.type !== 'talk') {
        const codes = event.description.match(/\b(\d{3,})\b/g)
        if (codes) {
          codes.forEach(c => facts.add(`Code: ${c}`))
          importance = Math.max(importance, 4)
        }
      }

      stream.push({
        id,
        tick: entry.tick,
        content: event.description,
        category,
        importance,
        isRetrieved: false,
      })
    }

    // Generate reflections every 5 ticks
    if (entry.tick > 0 && entry.tick % 5 === 0 && stream.length > 0) {
      const recentActions = stream
        .filter(m => m.tick >= entry.tick - 5 && m.tick <= entry.tick)
        .slice(-3)
      if (recentActions.length > 0) {
        const actionSummary = recentActions.map(m => {
          if (m.category === 'discovery') return 'made a discovery'
          if (m.category === 'failure') return 'encountered a setback'
          if (m.category === 'conversation') return 'exchanged information'
          if (m.importance >= 4) return 'made progress on a puzzle'
          return 'explored the environment'
        })
        const uniqueActions = [...new Set(actionSummary)]
        reflections.push({
          id: `ref-${entry.tick}`,
          tick: entry.tick,
          content: `Over the last few ticks, ${agentName} ${uniqueActions.join(' and ')}. ${
            facts.size > 0
              ? `Key knowledge includes ${Math.min(facts.size, 3)} discovered facts.`
              : 'Still gathering information.'
          }`,
        })
      }
    }
  }

  // Add exploration summary facts
  if (roomsVisited.size > 0) {
    facts.add(`Visited: ${Array.from(roomsVisited).join(', ')}`)
  }
  if (objectsExamined.size > 0) {
    facts.add(`Examined: ${Array.from(objectsExamined).slice(-6).join(', ')}`)
  }

  // Prioritize: codes & keywords first, then clues, then solved, then explored, then failures last
  const prioritized = Array.from(facts).sort((a, b) => {
    const rank = (f: string) => {
      if (f.startsWith('Code:') || f.startsWith('Keyword:')) return 0
      if (f.startsWith('Clue:') || f.startsWith('Inscription:')) return 1
      if (f.startsWith('Found:') || f.startsWith('Has:')) return 2
      if (f.startsWith('SOLVED:')) return 3
      if (f.startsWith('Visited:') || f.startsWith('Examined:')) return 4
      if (f.startsWith('FAILED:')) return 5
      return 3
    }
    return rank(a) - rank(b)
  })

  // Mark last 3 memories as "retrieved" for latest decision highlight
  const lastTick = stream.length > 0 ? stream[stream.length - 1].tick : 0
  const latestMems = stream.filter(m => m.tick === lastTick)
  latestMems.forEach(m => { m.isRetrieved = true })

  return {
    workingMemory: prioritized.slice(0, 12),
    stream: stream.reverse(), // Most recent first
    reflections: reflections.reverse(),
  }
}

// ---------------------------------------------------------------------------
// useTypewriter — reused from ThoughtBubble pattern
// ---------------------------------------------------------------------------

function useTypewriter(
  text: string,
  enabled: boolean,
  delay: number,
  speed: number = 18,
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
    const startTimer = setTimeout(() => setStarted(true), delay)
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
// Reduced motion check hook
// ---------------------------------------------------------------------------

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return reduced
}

// ---------------------------------------------------------------------------
// Importance heat glow — replaces numbered badges with thermal card glow
// ---------------------------------------------------------------------------

function getHeatStyles(importance: number): { border: string; shadow: string; bg: string } {
  switch (Math.min(Math.max(importance, 1), 5)) {
    case 5:
      return {
        border: 'border-gold/50',
        shadow: 'shadow-[0_0_16px_rgba(227,179,65,0.25)]',
        bg: 'bg-gold/[0.05]',
      }
    case 4:
      return {
        border: 'border-amber-500/30',
        shadow: 'shadow-[0_0_8px_rgba(245,158,11,0.15)]',
        bg: 'bg-amber-500/[0.03]',
      }
    case 3:
      return {
        border: 'border-border/60',
        shadow: '',
        bg: 'bg-bg-primary/50',
      }
    case 2:
      return {
        border: 'border-border/40',
        shadow: '',
        bg: 'bg-bg-primary/40',
      }
    default: // 1
      return {
        border: 'border-border/30',
        shadow: '',
        bg: 'bg-bg-primary/30',
      }
  }
}

// ---------------------------------------------------------------------------
// Category icon
// ---------------------------------------------------------------------------

function CategoryIcon({ category }: { category: SynthMemory['category'] }) {
  const config = {
    observation: { Icon: Eye, color: 'text-blue-400' },
    action: { Icon: Zap, color: 'text-gold' },
    discovery: { Icon: Sparkles, color: 'text-green-400' },
    conversation: { Icon: MessageCircle, color: 'text-purple-400' },
    failure: { Icon: AlertTriangle, color: 'text-danger' },
  }[category]

  const { Icon, color } = config
  return <Icon size={12} className={cn('shrink-0', color)} />
}

// ---------------------------------------------------------------------------
// Memory stream entry card — with thermal glow and decay opacity
// ---------------------------------------------------------------------------

function MemoryCard({
  memory,
  index,
  totalCount,
  isSearchMatch,
  isSearchActive,
}: {
  memory: SynthMemory
  index: number
  totalCount: number
  isSearchMatch: boolean
  isSearchActive: boolean
}) {
  const heat = getHeatStyles(memory.importance)

  // Memory decay: most recent = 1.0, fades to 0.7 at the bottom
  const decayOpacity = totalCount <= 1
    ? 1.0
    : 1.0 - (index / (totalCount - 1)) * 0.3

  // Search spotlight: non-matching dim to 0.2, matching glow brighter
  const searchOpacity = isSearchActive
    ? (isSearchMatch ? 1.0 : 0.2)
    : decayOpacity

  return (
    <div
      className={cn(
        'group relative px-3 py-2.5 rounded-lg border transition-all duration-300',
        heat.bg,
        heat.border,
        heat.shadow,
        // Importance 5 gets pulsing gold glow
        memory.importance === 5 && 'animate-heat-pulse-gold',
        // Retrieved indicator override
        memory.isRetrieved && 'border-gold/40 shadow-[0_0_12px_rgba(227,179,65,0.15)] bg-gold/[0.03]',
        // Search spotlight glow on match
        isSearchActive && isSearchMatch && 'shadow-[0_0_16px_rgba(227,179,65,0.3)] border-gold/50',
      )}
      style={{ opacity: searchOpacity }}
    >
      {/* Retrieved indicator — gold glow marker */}
      {memory.isRetrieved && (
        <div className="absolute -left-px top-2 bottom-2 w-[2px] rounded-full bg-gold shadow-[0_0_6px_rgba(227,179,65,0.4)]" />
      )}

      {/* Top row: category icon + tick + heat indicator dot */}
      <div className="flex items-center gap-2 mb-1">
        <CategoryIcon category={memory.category} />
        <span className="text-[10px] text-text-muted tabular-nums">T{memory.tick}</span>
        <span className="text-[10px] text-text-muted capitalize opacity-60">{memory.category}</span>
        {/* Heat indicator dot instead of numbered badge */}
        <span className="ml-auto">
          <span
            className={cn(
              'inline-block w-2 h-2 rounded-full',
              memory.importance >= 5 && 'bg-gold shadow-[0_0_6px_rgba(227,179,65,0.5)]',
              memory.importance === 4 && 'bg-amber-400/80 shadow-[0_0_4px_rgba(245,158,11,0.3)]',
              memory.importance === 3 && 'bg-text-secondary/50',
              memory.importance === 2 && 'bg-text-muted/40',
              memory.importance <= 1 && 'bg-text-muted/20',
            )}
            title={`Importance: ${memory.importance}/5`}
          />
        </span>
      </div>

      {/* Memory content */}
      <p className="text-sm text-text-secondary leading-relaxed m-0">
        {memory.content}
      </p>

      {/* Retrieved tag */}
      {memory.isRetrieved && (
        <span className="inline-flex items-center gap-1 mt-1.5 text-[10px] text-gold font-medium">
          <Brain size={10} />
          Used in latest decision
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Working memory — pinned facts (detective's notebook style)
// ---------------------------------------------------------------------------

function WorkingMemorySection({ facts }: { facts: string[] }) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (facts.length === 0) {
    return (
      <div className="px-4 py-3">
        <h4 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
          <Pin size={12} className="text-gold" />
          Working Memory
        </h4>
        <p className="text-sm text-text-muted italic">No key facts discovered yet...</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full text-left min-h-0 mb-2"
      >
        <Pin size={12} className="text-gold" />
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Working Memory
        </span>
        <span className="text-[10px] text-gold bg-gold/10 px-1.5 py-0.5 rounded-full">
          {facts.length}
        </span>
        <span className="ml-auto text-text-muted">
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {isExpanded && (
        <div className="grid gap-1.5">
          {facts.map((fact, i) => (
            <div
              key={i}
              className={cn(
                'relative px-3 py-2 rounded-md text-sm leading-snug',
                'bg-gold/[0.04] border border-gold/10',
                'text-text-primary',
                // Stagger fade-in for exhibition effect
                'animate-card-in',
              )}
              style={{ animationDelay: `${i * 40}ms` }}
            >
              {/* Pin accent */}
              <span className="absolute top-0 left-2 w-1.5 h-1.5 -translate-y-1/2 rounded-full bg-gold shadow-[0_0_4px_rgba(227,179,65,0.5)]" />
              {fact}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reflection card — with typewriter reveal and breathing purple border
// ---------------------------------------------------------------------------

function ReflectionCard({ reflection, index }: { reflection: SynthReflection; index: number }) {
  const prefersReducedMotion = usePrefersReducedMotion()
  const enableTypewriter = !prefersReducedMotion

  const typewriter = useTypewriter(
    reflection.content,
    enableTypewriter,
    300 + index * 200, // stagger delay per card
    12, // slower than thought bubble for contemplative feel
  )

  return (
    <div
      className={cn(
        'px-3 py-2.5 rounded-lg border-2',
        'bg-purple-500/[0.04]',
        // Breathing purple border (like gold breathing border but purple)
        'animate-breathing-border-purple',
      )}
    >
      <span className="text-[10px] text-text-muted tabular-nums block mb-1">
        Tick {reflection.tick}
      </span>
      <p className="text-sm text-text-secondary italic leading-relaxed m-0">
        {typewriter.displayed}
        {typewriter.showCursor && (
          <span
            className="inline-block w-[2px] h-[12px] ml-0.5 align-middle animate-cursor-blink"
            style={{ backgroundColor: '#7c3aed' }}
          />
        )}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Reflections section
// ---------------------------------------------------------------------------

function ReflectionsSection({ reflections }: { reflections: SynthReflection[] }) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (reflections.length === 0) {
    return (
      <div className="px-4 py-3">
        <h4 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
          <BookOpen size={12} className="text-purple-400" />
          Reflections
        </h4>
        <p className="text-sm text-text-muted italic">No reflections yet. Agents reflect every 5 ticks...</p>
      </div>
    )
  }

  return (
    <div className="px-4 py-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full text-left min-h-0 mb-2"
      >
        <BookOpen size={12} className="text-purple-400" />
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Reflections
        </span>
        <span className="text-[10px] text-purple-400 bg-purple-400/10 px-1.5 py-0.5 rounded-full">
          {reflections.length}
        </span>
        <span className="ml-auto text-text-muted">
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {isExpanded && (
        <div className="grid gap-2">
          {reflections.map((ref, index) => (
            <ReflectionCard key={ref.id} reflection={ref} index={index} />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main inspector panel
// ---------------------------------------------------------------------------

interface AgentMemoryInspectorProps {
  agent: AgentState
  onClose: () => void
}

export function AgentMemoryInspector({ agent, onClose }: AgentMemoryInspectorProps) {
  const narrativeEvents = useNarrativeEvents()
  const currentTick = useTick()
  const [searchQuery, setSearchQuery] = useState('')
  const [activeTab, setActiveTab] = useState<'stream' | 'working' | 'reflections'>('stream')
  const panelRef = useRef<HTMLDivElement>(null)
  const dragStartY = useRef<number | null>(null)
  const currentTranslateY = useRef(0)
  const [isEntering, setIsEntering] = useState(true)

  // Entrance ritual: remove entering state after animation completes
  useEffect(() => {
    const timer = setTimeout(() => setIsEntering(false), 350)
    return () => clearTimeout(timer)
  }, [])

  // Synthesize memories from narrative events
  const { workingMemory, stream, reflections } = useMemo(
    () => synthesizeMemories(agent.name, narrativeEvents),
    [agent.name, narrativeEvents],
  )

  // Search matching set (for spotlight effect)
  const searchMatchIds = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>()
    const q = searchQuery.toLowerCase()
    const matches = new Set<string>()
    stream.forEach(m => {
      if (m.content.toLowerCase().includes(q) || m.category.includes(q)) {
        matches.add(m.id)
      }
    })
    return matches
  }, [stream, searchQuery])

  const isSearchActive = searchQuery.trim().length > 0

  // Filtered working memory (still filter these since they're short labels)
  const filteredFacts = useMemo(() => {
    if (!searchQuery.trim()) return workingMemory
    const q = searchQuery.toLowerCase()
    return workingMemory.filter(f => f.toLowerCase().includes(q))
  }, [workingMemory, searchQuery])

  // Swipe-to-dismiss (mobile bottom sheet)
  const onTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartY.current = e.touches[0].clientY
    currentTranslateY.current = 0
  }, [])

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (dragStartY.current === null || !panelRef.current) return
    const deltaY = e.touches[0].clientY - dragStartY.current
    if (deltaY > 0) {
      currentTranslateY.current = deltaY
      panelRef.current.style.transform = `translateY(${deltaY}px)`
    }
  }, [])

  const onTouchEnd = useCallback(() => {
    if (dragStartY.current === null || !panelRef.current) return
    if (currentTranslateY.current > 100) {
      onClose()
    } else {
      panelRef.current.style.transform = 'translateY(0)'
    }
    dragStartY.current = null
    currentTranslateY.current = 0
  }, [onClose])

  // Keyboard dismiss
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const tabs = [
    { key: 'stream' as const, label: 'Stream', count: stream.length, Icon: Clock },
    { key: 'working' as const, label: 'Facts', count: workingMemory.length, Icon: Pin },
    { key: 'reflections' as const, label: 'Reflect', count: reflections.length, Icon: BookOpen },
  ]

  return (
    <>
      {/* Backdrop — entrance ritual: radial gold spotlight expanding */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]',
          isEntering ? 'animate-mind-dive-backdrop' : 'animate-gpu',
        )}
        onClick={onClose}
        aria-hidden
      />

      {/* Panel — bottom sheet on mobile, right panel on desktop */}
      <div
        ref={panelRef}
        role="dialog"
        aria-label={`Memory inspector for ${agent.name}`}
        className={cn(
          'fixed z-50 flex flex-col',
          'bg-bg-secondary border-border',
          // Mobile: full-height bottom sheet
          'inset-x-0 bottom-0 max-h-[90vh] rounded-t-2xl border-t',
          // Desktop: right-side panel
          'md:inset-y-0 md:right-0 md:left-auto md:bottom-auto',
          'md:w-[420px] md:max-h-full md:rounded-t-none md:rounded-l-xl md:border-l md:border-t-0',
          // Entrance ritual: scale + blur -> focus
          isEntering ? 'animate-mind-dive-panel' : 'transition-transform duration-200 ease-out',
        )}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden shrink-0">
          <div className="w-10 h-1 rounded-full bg-text-muted/40" />
        </div>

        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-gold/10 flex items-center justify-center shadow-[0_0_12px_rgba(227,179,65,0.1)]">
              <Brain size={18} className="text-gold" />
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary m-0 leading-tight">
                {agent.name}'s Mind
              </h3>
              <span className="text-[11px] text-text-muted">
                {stream.length} memories &middot; Tick {currentTick}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary transition-colors"
            aria-label="Close memory inspector"
          >
            <X size={18} />
          </button>
        </div>

        {/* Search bar */}
        <div className="shrink-0 px-4 py-2 border-b border-border/50">
          <div className="relative">
            <Search size={14} className={cn(
              'absolute left-3 top-1/2 -translate-y-1/2 transition-colors duration-200',
              isSearchActive ? 'text-gold' : 'text-text-muted',
            )} />
            <input
              type="text"
              placeholder="Search memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className={cn(
                'w-full pl-9 pr-3 py-2 rounded-lg text-sm',
                'bg-bg-primary border border-border/50',
                'text-text-primary placeholder:text-text-muted/50',
                'focus:outline-none focus:border-gold/40 focus:shadow-[0_0_8px_rgba(227,179,65,0.1)]',
                'transition-all duration-150',
                // Spotlight mode indicator
                isSearchActive && 'border-gold/30 shadow-[0_0_12px_rgba(227,179,65,0.08)]',
              )}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 min-h-0 min-w-0 flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-muted"
              >
                <X size={12} />
              </button>
            )}
          </div>
          {/* Search spotlight status */}
          {isSearchActive && (
            <span className="text-[10px] text-gold mt-1 block">
              {searchMatchIds.size} of {stream.length} memories illuminated
            </span>
          )}
        </div>

        {/* Tab bar */}
        <div className="shrink-0 flex border-b border-border/50">
          {tabs.map(({ key, label, count, Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 px-2 py-2.5 min-h-[44px]',
                'text-xs font-medium transition-all duration-150',
                activeTab === key
                  ? 'text-gold border-b-2 border-gold bg-gold/[0.03]'
                  : 'text-text-muted hover:text-text-secondary border-b-2 border-transparent',
              )}
            >
              <Icon size={13} />
              {label}
              <span className={cn(
                'text-[10px] px-1.5 py-0.5 rounded-full',
                activeTab === key ? 'bg-gold/15 text-gold' : 'bg-bg-tertiary text-text-muted',
              )}>
                {count}
              </span>
            </button>
          ))}
        </div>

        {/* Content — scrollable */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {activeTab === 'working' && (
            <WorkingMemorySection facts={filteredFacts} />
          )}

          {activeTab === 'reflections' && (
            <ReflectionsSection reflections={reflections} />
          )}

          {activeTab === 'stream' && (
            <div className="px-4 py-3">
              {stream.length === 0 ? (
                <div className="text-center py-8">
                  <Brain size={32} className="mx-auto text-text-muted/30 mb-3" />
                  <p className="text-sm text-text-muted">
                    No memories recorded yet. Start the simulation to observe this agent's experiences.
                  </p>
                </div>
              ) : (
                <div className="grid gap-2">
                  {stream.map((memory, index) => (
                    <MemoryCard
                      key={memory.id}
                      memory={memory}
                      index={index}
                      totalCount={stream.length}
                      isSearchMatch={searchMatchIds.has(memory.id)}
                      isSearchActive={isSearchActive}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer — memory stats */}
        <div className="shrink-0 px-4 py-2 border-t border-border/50 bg-bg-primary/50">
          <div className="flex items-center justify-between text-[10px] text-text-muted">
            <span>{stream.length} total memories</span>
            <span>{workingMemory.length} working facts</span>
            <span>{reflections.length} reflections</span>
          </div>
        </div>
      </div>
    </>
  )
}
