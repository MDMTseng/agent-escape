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
  Footprints,
  Zap,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNarrativeEvents, useTick } from '@/stores/gameStore'
import type { AgentState, NarrativeEntry, TickEvent } from '@/types/game'

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
      } else if (event.type === 'examine') {
        category = 'observation'
        importance = 3
        // Extract discoveries from examine events
        const quotedMatch = event.description.match(/"([^"]{5,})"/)
        if (quotedMatch) {
          facts.add(quotedMatch[1].slice(0, 60))
          importance = 4
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
        importance = 3
        const speechMatch = event.description.match(/says?\s*:?\s*"?([^"]{5,60})"?/i)
        if (speechMatch) facts.add(`Heard: "${speechMatch[1].slice(0, 50)}"`)
      } else if (event.type === 'fail') {
        category = 'failure'
        importance = 3
        const failMatch = event.description.match(/(?:can't|tries to|fails to)\s+(.+)/i)
        if (failMatch) facts.add(`FAILED: ${failMatch[1].slice(0, 40)}`)
      }

      // Extract number codes
      const codes = event.description.match(/\b(\d{3,})\b/g)
      if (codes) {
        codes.forEach(c => facts.add(`Code: ${c}`))
        importance = Math.max(importance, 4)
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

  // Mark last 3 memories as "retrieved" for latest decision highlight
  const lastTick = stream.length > 0 ? stream[stream.length - 1].tick : 0
  const latestMems = stream.filter(m => m.tick === lastTick)
  latestMems.forEach(m => { m.isRetrieved = true })

  return {
    workingMemory: Array.from(facts).slice(-10),
    stream: stream.reverse(), // Most recent first
    reflections: reflections.reverse(),
  }
}

// ---------------------------------------------------------------------------
// Importance badge — color-coded score
// ---------------------------------------------------------------------------

function ImportanceBadge({ score }: { score: number }) {
  const config = {
    1: { label: '1', bg: 'bg-text-muted/20', text: 'text-text-muted', glow: '' },
    2: { label: '2', bg: 'bg-blue-500/15', text: 'text-blue-400', glow: '' },
    3: { label: '3', bg: 'bg-green-500/15', text: 'text-green-400', glow: '' },
    4: { label: '4', bg: 'bg-gold/15', text: 'text-gold', glow: 'shadow-[0_0_4px_rgba(227,179,65,0.2)]' },
    5: { label: '5', bg: 'bg-danger/15', text: 'text-danger', glow: 'shadow-[0_0_6px_rgba(248,81,73,0.25)]' },
  }[Math.min(Math.max(score, 1), 5)] ?? { label: '?', bg: 'bg-text-muted/20', text: 'text-text-muted', glow: '' }

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold shrink-0',
        config.bg, config.text, config.glow,
      )}
      title={`Importance: ${score}/5`}
    >
      {config.label}
    </span>
  )
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
// Memory stream entry card
// ---------------------------------------------------------------------------

function MemoryCard({ memory }: { memory: SynthMemory }) {
  return (
    <div
      className={cn(
        'group relative px-3 py-2.5 rounded-lg border transition-all duration-200',
        'bg-bg-primary/50',
        memory.isRetrieved
          ? 'border-gold/40 shadow-[0_0_12px_rgba(227,179,65,0.15)] bg-gold/[0.03]'
          : 'border-border/50 hover:border-border',
      )}
    >
      {/* Retrieved indicator — gold glow marker */}
      {memory.isRetrieved && (
        <div className="absolute -left-px top-2 bottom-2 w-[2px] rounded-full bg-gold shadow-[0_0_6px_rgba(227,179,65,0.4)]" />
      )}

      {/* Top row: category icon + tick + importance */}
      <div className="flex items-center gap-2 mb-1">
        <CategoryIcon category={memory.category} />
        <span className="text-[10px] text-text-muted tabular-nums">T{memory.tick}</span>
        <span className="text-[10px] text-text-muted capitalize opacity-60">{memory.category}</span>
        <span className="ml-auto">
          <ImportanceBadge score={memory.importance} />
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
// Reflections section — distinct visual (italic, muted, thoughtful)
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
          {reflections.map((ref) => (
            <div
              key={ref.id}
              className={cn(
                'px-3 py-2.5 rounded-lg border border-purple-500/15',
                'bg-purple-500/[0.04]',
              )}
            >
              <span className="text-[10px] text-text-muted tabular-nums block mb-1">
                Tick {ref.tick}
              </span>
              <p className="text-sm text-text-secondary italic leading-relaxed m-0">
                {ref.content}
              </p>
            </div>
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

  // Synthesize memories from narrative events
  const { workingMemory, stream, reflections } = useMemo(
    () => synthesizeMemories(agent.name, narrativeEvents),
    [agent.name, narrativeEvents],
  )

  // Filter stream by search query
  const filteredStream = useMemo(() => {
    if (!searchQuery.trim()) return stream
    const q = searchQuery.toLowerCase()
    return stream.filter(m =>
      m.content.toLowerCase().includes(q) ||
      m.category.includes(q),
    )
  }, [stream, searchQuery])

  // Filtered working memory
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
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] animate-gpu"
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
          'transition-transform duration-200 ease-out',
          // Mobile: full-height bottom sheet
          'inset-x-0 bottom-0 max-h-[90vh] rounded-t-2xl border-t',
          // Desktop: right-side panel
          'md:inset-y-0 md:right-0 md:left-auto md:bottom-auto',
          'md:w-[420px] md:max-h-full md:rounded-t-none md:rounded-l-xl md:border-l md:border-t-0',
          // Slide-in animation
          'animate-card-in',
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
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
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
              {filteredStream.length === 0 ? (
                <div className="text-center py-8">
                  <Brain size={32} className="mx-auto text-text-muted/30 mb-3" />
                  <p className="text-sm text-text-muted">
                    {searchQuery
                      ? 'No memories match your search.'
                      : 'No memories recorded yet. Start the simulation to observe this agent\'s experiences.'}
                  </p>
                </div>
              ) : (
                <div className="grid gap-2">
                  {filteredStream.map((memory) => (
                    <MemoryCard key={memory.id} memory={memory} />
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
