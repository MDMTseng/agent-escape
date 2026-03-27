/**
 * AgentsTab — Agent designer for the Scene Creator.
 *
 * Add/remove agents with: name, role, backstory, personality traits (tag input),
 * spawn room (dropdown from rooms), initial inventory (tag input), goal,
 * secret motivation. Archetype presets for quick fill. Relationship matrix
 * between agents (trust slider per pair). Trait-to-behavior preview.
 *
 * Mobile: agent cards as expandable sections. Relationship matrix as list of pairs.
 * Touch-friendly: 44px+ targets, swipe-to-delete on cards.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Plus, X, Trash2, ChevronDown, ChevronRight,
  Users, Shield, BookOpen, Brain, Eye, Heart,
  Sparkles, Target, MapPin, Package,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { SceneCreatorState, RoomNode } from '@/pages/Creator'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface AgentItem {
  id: string
  name: string
  role: string
  backstory: string
  traits: string[]
  spawnRoomId: string
  inventory: string[]
  goal: string
  secretMotivation: string
}

export interface AgentRelationship {
  agentA: string
  agentB: string
  trust: number // -1 to 1 scale, 0 = neutral
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const ARCHETYPE_PRESETS: {
  label: string
  icon: React.ElementType
  data: Partial<AgentItem>
}[] = [
  {
    label: 'The Detective',
    icon: Eye,
    data: {
      role: 'Investigator',
      traits: ['observant', 'analytical', 'persistent', 'skeptical'],
      goal: 'Uncover the truth behind the mystery',
      backstory: 'A seasoned investigator who trusts evidence over intuition. Has solved countless cases but this one feels personal.',
    },
  },
  {
    label: 'The Scholar',
    icon: BookOpen,
    data: {
      role: 'Researcher',
      traits: ['curious', 'methodical', 'bookish', 'patient'],
      goal: 'Decode the ancient knowledge hidden in this place',
      backstory: 'An academic who has spent years studying obscure texts. This location matches descriptions from a forbidden manuscript.',
    },
  },
  {
    label: 'The Skeptic',
    icon: Shield,
    data: {
      role: 'Critic',
      traits: ['cautious', 'logical', 'distrustful', 'direct'],
      goal: 'Find a rational explanation and escape safely',
      backstory: 'Doesn\'t believe in mysteries or magic. Everything has a logical explanation, and they intend to prove it.',
    },
  },
  {
    label: 'The Helper',
    icon: Heart,
    data: {
      role: 'Mediator',
      traits: ['empathetic', 'cooperative', 'optimistic', 'perceptive'],
      goal: 'Ensure everyone escapes together safely',
      backstory: 'A natural peacemaker who believes the group\'s survival depends on trust and communication.',
    },
  },
]

const TRAIT_LIBRARY = [
  'observant', 'analytical', 'persistent', 'skeptical', 'curious',
  'methodical', 'bookish', 'patient', 'cautious', 'logical',
  'distrustful', 'direct', 'empathetic', 'cooperative', 'optimistic',
  'perceptive', 'impulsive', 'brave', 'resourceful', 'secretive',
  'charismatic', 'stubborn', 'creative', 'paranoid',
]

/** Maps traits to behavioral descriptions for the preview */
const TRAIT_BEHAVIORS: Record<string, string> = {
  observant: 'Notices hidden details and environmental clues others miss',
  analytical: 'Approaches puzzles systematically, breaking them into steps',
  persistent: 'Won\'t give up easily; retries failed approaches',
  skeptical: 'Questions other agents\' theories and looks for counter-evidence',
  curious: 'Actively examines everything in a room; explores eagerly',
  methodical: 'Searches rooms systematically instead of at random',
  bookish: 'Prioritizes reading documents, inscriptions, and written clues',
  patient: 'Takes time to think before acting; rarely rushes',
  cautious: 'Avoids risky actions; checks for traps before interacting',
  logical: 'Uses deduction to eliminate impossible solutions',
  distrustful: 'Reluctant to share information with other agents',
  direct: 'States opinions bluntly; confrontational in conversations',
  empathetic: 'Picks up on other agents\' emotional states and responds',
  cooperative: 'Shares items and clues freely; suggests teamwork',
  optimistic: 'Maintains morale; encourages the group when stuck',
  perceptive: 'Notices when other agents are hiding something',
  impulsive: 'Acts on first instinct; may trigger puzzles prematurely',
  brave: 'Willing to take risks; volunteers for dangerous tasks',
  resourceful: 'Finds creative uses for inventory items',
  secretive: 'Hoards information; may lie about discoveries',
  charismatic: 'Persuasive in conversations; can extract info from others',
  stubborn: 'Refuses to abandon a theory even when evidence contradicts it',
  creative: 'Thinks outside the box; tries unusual item combinations',
  paranoid: 'Suspects traps everywhere; over-examines safe objects',
}

let agentIdCounter = 0
function nextAgentId() {
  return `agent-${++agentIdCounter}-${Date.now()}`
}

/* ------------------------------------------------------------------ */
/*  Swipeable agent card (mobile) — swipe left to reveal delete        */
/* ------------------------------------------------------------------ */

function SwipeableAgentCard({
  children,
  onDelete,
}: {
  children: React.ReactNode
  onDelete: () => void
}) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [offsetX, setOffsetX] = useState(0)
  const [isSwiping, setIsSwiping] = useState(false)
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const revealed = useRef(false)

  const DELETE_WIDTH = 72

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY }
    setIsSwiping(false)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return
    const touch = e.touches[0]
    const dx = touch.clientX - touchStart.current.x
    const dy = touch.clientY - touchStart.current.y

    if (!isSwiping && Math.abs(dy) > Math.abs(dx)) {
      touchStart.current = null
      return
    }

    if (Math.abs(dx) > 10) setIsSwiping(true)

    if (isSwiping) {
      const baseOffset = revealed.current ? -DELETE_WIDTH : 0
      const newOffset = Math.min(0, Math.max(-DELETE_WIDTH - 20, baseOffset + dx))
      setOffsetX(newOffset)
    }
  }

  const handleTouchEnd = () => {
    if (!touchStart.current && !isSwiping) return

    if (isSwiping) {
      if (offsetX < -DELETE_WIDTH / 2) {
        setOffsetX(-DELETE_WIDTH)
        revealed.current = true
      } else {
        setOffsetX(0)
        revealed.current = false
      }
    }

    touchStart.current = null
    setTimeout(() => setIsSwiping(false), 50)
  }

  useEffect(() => {
    const handleDocClick = (e: MouseEvent) => {
      if (revealed.current && cardRef.current && !cardRef.current.contains(e.target as Node)) {
        setOffsetX(0)
        revealed.current = false
      }
    }
    document.addEventListener('click', handleDocClick)
    return () => document.removeEventListener('click', handleDocClick)
  }, [])

  return (
    <div ref={cardRef} className="relative overflow-hidden rounded-xl md:overflow-visible">
      {/* Delete action behind the card (mobile only) */}
      <div
        className="absolute inset-y-0 right-0 flex items-center justify-center bg-danger md:hidden"
        style={{ width: DELETE_WIDTH }}
      >
        <button
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="flex flex-col items-center justify-center gap-1 text-white w-full h-full min-h-[44px] min-w-[44px] active:bg-red-700 transition-colors"
          aria-label="Delete agent"
        >
          <Trash2 className="size-5" />
          <span className="text-xs font-medium">Delete</span>
        </button>
      </div>

      {/* Sliding content */}
      <div
        className="relative bg-bg-secondary border border-border rounded-xl transition-transform duration-200 ease-out"
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isSwiping ? 'none' : 'transform 200ms ease-out',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {children}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Tag Input component (reusable for traits + inventory)              */
/* ------------------------------------------------------------------ */

function TagInput({
  tags,
  onAdd,
  onRemove,
  placeholder,
  suggestions,
  accentColor = 'gold',
}: {
  tags: string[]
  onAdd: (tag: string) => void
  onRemove: (tag: string) => void
  placeholder: string
  suggestions?: string[]
  accentColor?: 'gold' | 'blue' | 'purple'
}) {
  const [input, setInput] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const colorMap = {
    gold: { tag: 'bg-gold/10 text-gold', remove: 'text-gold/60 hover:text-danger' },
    blue: { tag: 'bg-blue-500/10 text-blue-400', remove: 'text-blue-400/60 hover:text-danger' },
    purple: { tag: 'bg-purple-500/10 text-purple-400', remove: 'text-purple-400/60 hover:text-danger' },
  }

  const colors = colorMap[accentColor]

  const filtered = suggestions?.filter(
    s => s.toLowerCase().includes(input.toLowerCase()) && !tags.includes(s)
  ) ?? []

  const handleAdd = (value?: string) => {
    const trimmed = (value ?? input).trim().toLowerCase()
    if (trimmed && !tags.includes(trimmed)) {
      onAdd(trimmed)
      setInput('')
      setShowSuggestions(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => { setInput(e.target.value); setShowSuggestions(true) }}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleAdd() } }}
            placeholder={placeholder}
            className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
          />
          {/* Autocomplete dropdown */}
          {showSuggestions && input.length > 0 && filtered.length > 0 && (
            <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-bg-secondary border border-border rounded-lg shadow-lg max-h-40 overflow-y-auto">
              {filtered.slice(0, 8).map(suggestion => (
                <button
                  key={suggestion}
                  onMouseDown={(e) => { e.preventDefault(); handleAdd(suggestion) }}
                  className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:bg-bg-tertiary hover:text-text-primary transition-colors min-h-[40px]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
        <Button onClick={() => handleAdd()} variant="outline" className="h-11 px-3 shrink-0">
          <Plus className="size-4" />
        </Button>
      </div>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map(tag => (
            <span
              key={tag}
              className={cn('inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium', colors.tag)}
            >
              {tag}
              <button
                onClick={() => onRemove(tag)}
                className={cn('size-4 min-h-0 min-w-0 flex items-center justify-center rounded transition-colors', colors.remove)}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Trait-to-behavior preview                                          */
/* ------------------------------------------------------------------ */

function TraitBehaviorPreview({ traits }: { traits: string[] }) {
  const matched = traits.filter(t => TRAIT_BEHAVIORS[t])
  if (matched.length === 0) return null

  return (
    <div className="rounded-lg border border-border/50 bg-bg-primary/50 p-3">
      <h5 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5">
        <Brain className="size-3.5" />
        Behavior Preview
      </h5>
      <ul className="space-y-1.5">
        {matched.map(trait => (
          <li key={trait} className="flex items-start gap-2 text-xs">
            <span className="text-gold font-medium shrink-0 min-w-[80px]">{trait}</span>
            <span className="text-text-muted">{TRAIT_BEHAVIORS[trait]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Agent card component (expandable)                                  */
/* ------------------------------------------------------------------ */

function AgentCard({
  agent,
  rooms,
  onUpdate,
  onDelete,
}: {
  agent: AgentItem
  rooms: RoomNode[]
  onUpdate: (agent: AgentItem) => void
  onDelete: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)

  const spawnRoom = rooms.find(r => r.id === agent.spawnRoomId)
  const traitCount = agent.traits.length

  return (
    <SwipeableAgentCard onDelete={() => onDelete(agent.id)}>
      <div className="p-4">
        {/* Header row: always visible */}
        <div className="flex items-center gap-3">
          {/* Avatar */}
          <div className="size-10 rounded-full bg-gold/10 flex items-center justify-center shrink-0">
            <Users className="size-5 text-gold" />
          </div>

          {/* Name + role */}
          <div className="flex-1 min-w-0">
            <input
              type="text"
              value={agent.name}
              onChange={e => onUpdate({ ...agent, name: e.target.value })}
              className="bg-transparent text-text-primary text-sm font-semibold w-full focus:outline-none focus:text-gold placeholder:text-text-muted"
              placeholder="Agent name..."
            />
            <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
              <span>{agent.role || 'No role'}</span>
              {traitCount > 0 && (
                <>
                  <span className="text-text-muted/40">|</span>
                  <span>{traitCount} trait{traitCount !== 1 ? 's' : ''}</span>
                </>
              )}
              {spawnRoom && (
                <>
                  <span className="text-text-muted/40">|</span>
                  <span>{spawnRoom.name}</span>
                </>
              )}
            </div>
          </div>

          {/* Expand toggle + delete (desktop) */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => onDelete(agent.id)}
              className="hidden md:flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
              aria-label="Delete agent"
            >
              <Trash2 className="size-4" />
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center justify-center size-10 min-h-[44px] min-w-[44px] rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              aria-label={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? (
                <ChevronDown className="size-5" />
              ) : (
                <ChevronRight className="size-5" />
              )}
            </button>
          </div>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-4 space-y-4 animate-card-in">
            {/* Role */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">Role</label>
              <input
                type="text"
                value={agent.role}
                onChange={e => onUpdate({ ...agent, role: e.target.value })}
                placeholder="e.g., Investigator, Scholar, Guard..."
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
              />
            </div>

            {/* Backstory */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">Backstory</label>
              <textarea
                value={agent.backstory}
                onChange={e => onUpdate({ ...agent, backstory: e.target.value })}
                rows={3}
                placeholder="What brought this character here? What drives them?"
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 resize-y placeholder:text-text-muted/60"
              />
            </div>

            {/* Personality traits (tag input with suggestions) */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">
                Personality Traits
              </label>
              <TagInput
                tags={agent.traits}
                onAdd={tag => onUpdate({ ...agent, traits: [...agent.traits, tag] })}
                onRemove={tag => onUpdate({ ...agent, traits: agent.traits.filter(t => t !== tag) })}
                placeholder="Type a trait or pick from suggestions..."
                suggestions={TRAIT_LIBRARY}
                accentColor="gold"
              />
            </div>

            {/* Trait behavior preview */}
            <TraitBehaviorPreview traits={agent.traits} />

            {/* Spawn room */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5 flex items-center gap-1.5">
                <MapPin className="size-3.5" />
                Spawn Room
              </label>
              <select
                value={agent.spawnRoomId}
                onChange={e => onUpdate({ ...agent, spawnRoomId: e.target.value })}
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
              >
                <option value="">Unassigned</option>
                {rooms.map(r => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
              {rooms.length === 0 && (
                <p className="text-text-muted text-xs mt-1">
                  No rooms yet. Add rooms in the Rooms tab first.
                </p>
              )}
            </div>

            {/* Initial inventory */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5 flex items-center gap-1.5">
                <Package className="size-3.5" />
                Initial Inventory
              </label>
              <TagInput
                tags={agent.inventory}
                onAdd={item => onUpdate({ ...agent, inventory: [...agent.inventory, item] })}
                onRemove={item => onUpdate({ ...agent, inventory: agent.inventory.filter(i => i !== item) })}
                placeholder="Add starting item..."
                accentColor="blue"
              />
            </div>

            {/* Goal */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5 flex items-center gap-1.5">
                <Target className="size-3.5" />
                Goal
              </label>
              <input
                type="text"
                value={agent.goal}
                onChange={e => onUpdate({ ...agent, goal: e.target.value })}
                placeholder="What is this agent trying to accomplish?"
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
              />
            </div>

            {/* Secret motivation */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5 flex items-center gap-1.5">
                <Eye className="size-3.5" />
                Secret Motivation
              </label>
              <textarea
                value={agent.secretMotivation}
                onChange={e => onUpdate({ ...agent, secretMotivation: e.target.value })}
                rows={2}
                placeholder="Hidden agenda or secret reason for being here (not shared with other agents)..."
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 resize-y placeholder:text-text-muted/60"
              />
            </div>
          </div>
        )}
      </div>
    </SwipeableAgentCard>
  )
}

/* ------------------------------------------------------------------ */
/*  Relationship matrix — trust sliders between agent pairs            */
/* ------------------------------------------------------------------ */

function RelationshipMatrix({
  agents,
  relationships,
  onUpdateRelationship,
}: {
  agents: AgentItem[]
  relationships: AgentRelationship[]
  onUpdateRelationship: (agentA: string, agentB: string, trust: number) => void
}) {
  if (agents.length < 2) return null

  // Generate all unique pairs
  const pairs: { a: AgentItem; b: AgentItem }[] = []
  for (let i = 0; i < agents.length; i++) {
    for (let j = i + 1; j < agents.length; j++) {
      pairs.push({ a: agents[i], b: agents[j] })
    }
  }

  const getTrust = (aId: string, bId: string): number => {
    const rel = relationships.find(
      r => (r.agentA === aId && r.agentB === bId) || (r.agentA === bId && r.agentB === aId)
    )
    return rel?.trust ?? 0
  }

  const trustLabel = (trust: number): string => {
    if (trust <= -0.6) return 'Hostile'
    if (trust <= -0.2) return 'Distrustful'
    if (trust < 0.2) return 'Neutral'
    if (trust < 0.6) return 'Friendly'
    return 'Allied'
  }

  const trustColor = (trust: number): string => {
    if (trust <= -0.6) return 'text-danger'
    if (trust <= -0.2) return 'text-orange-400'
    if (trust < 0.2) return 'text-text-muted'
    if (trust < 0.6) return 'text-blue-400'
    return 'text-success'
  }

  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-4">
      <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2">
        <Heart className="size-3.5" />
        Relationship Matrix
      </h4>
      <p className="text-text-muted text-xs mb-4">
        Set initial trust levels between agents. This affects how willing they are to cooperate.
      </p>
      <div className="space-y-4">
        {pairs.map(({ a, b }) => {
          const trust = getTrust(a.id, b.id)
          return (
            <div key={`${a.id}-${b.id}`} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm min-w-0">
                  <span className="text-text-primary font-medium truncate max-w-[100px]">
                    {a.name || 'Agent'}
                  </span>
                  <span className="text-text-muted/40">&harr;</span>
                  <span className="text-text-primary font-medium truncate max-w-[100px]">
                    {b.name || 'Agent'}
                  </span>
                </div>
                <span className={cn('text-xs font-medium', trustColor(trust))}>
                  {trustLabel(trust)}
                </span>
              </div>
              <input
                type="range"
                min={-100}
                max={100}
                step={10}
                value={Math.round(trust * 100)}
                onChange={e => onUpdateRelationship(a.id, b.id, Number(e.target.value) / 100)}
                className="w-full h-10 appearance-none bg-transparent cursor-pointer touch-pan-x
                  [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-bg-tertiary
                  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-6 [&::-webkit-slider-thumb]:h-6 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gold [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-gold-bright [&::-webkit-slider-thumb]:-mt-[9px] [&::-webkit-slider-thumb]:shadow-md
                  [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-bg-tertiary
                  [&::-moz-range-thumb]:w-6 [&::-moz-range-thumb]:h-6 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-gold [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-gold-bright"
              />
              <div className="flex justify-between text-[10px] text-text-muted/60 -mt-1 px-0.5">
                <span>Hostile</span>
                <span>Neutral</span>
                <span>Allied</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Archetype preset buttons                                           */
/* ------------------------------------------------------------------ */

function ArchetypePresets({
  onApply,
}: {
  onApply: (preset: Partial<AgentItem>) => void
}) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {ARCHETYPE_PRESETS.map(preset => {
        const Icon = preset.icon
        return (
          <button
            key={preset.label}
            onClick={() => onApply(preset.data)}
            className={cn(
              'flex flex-col items-center gap-1.5 p-3 rounded-xl border border-border',
              'bg-bg-secondary hover:border-gold/40 hover:bg-gold/5',
              'transition-all min-h-[44px] active:scale-[0.97]',
              'text-center',
            )}
          >
            <Icon className="size-5 text-gold/70" />
            <span className="text-text-secondary text-xs font-medium">{preset.label}</span>
          </button>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main AgentsTab Component                                           */
/* ------------------------------------------------------------------ */

export function AgentsTab({
  sceneState,
  setSceneState,
}: {
  sceneState: SceneCreatorState
  setSceneState: React.Dispatch<React.SetStateAction<SceneCreatorState>>
}) {
  const agents: AgentItem[] = sceneState.agents ?? []
  const relationships: AgentRelationship[] = (sceneState as any).relationships ?? []

  const setAgents = useCallback((updater: (prev: AgentItem[]) => AgentItem[]) => {
    setSceneState(prev => ({
      ...prev,
      agents: updater((prev as any).agents ?? []),
    } as any))
  }, [setSceneState])

  const setRelationships = useCallback((updater: (prev: AgentRelationship[]) => AgentRelationship[]) => {
    setSceneState(prev => ({
      ...prev,
      relationships: updater((prev as any).relationships ?? []),
    } as any))
  }, [setSceneState])

  const addAgent = useCallback((preset?: Partial<AgentItem>) => {
    const newAgent: AgentItem = {
      id: nextAgentId(),
      name: preset?.role ? `${preset.role} ${agents.length + 1}` : `Agent ${agents.length + 1}`,
      role: preset?.role ?? '',
      backstory: preset?.backstory ?? '',
      traits: preset?.traits ? [...preset.traits] : [],
      spawnRoomId: '',
      inventory: [],
      goal: preset?.goal ?? '',
      secretMotivation: '',
    }
    setAgents(prev => [...prev, newAgent])
  }, [agents.length, setAgents])

  const updateAgent = useCallback((updated: AgentItem) => {
    setAgents(prev => prev.map(a => a.id === updated.id ? updated : a))
  }, [setAgents])

  const deleteAgent = useCallback((id: string) => {
    setAgents(prev => prev.filter(a => a.id !== id))
    // Also clean up relationships involving this agent
    setRelationships(prev => prev.filter(r => r.agentA !== id && r.agentB !== id))
  }, [setAgents, setRelationships])

  const updateRelationship = useCallback((agentA: string, agentB: string, trust: number) => {
    setRelationships(prev => {
      const existing = prev.findIndex(
        r => (r.agentA === agentA && r.agentB === agentB) || (r.agentA === agentB && r.agentB === agentA)
      )
      if (existing >= 0) {
        const updated = [...prev]
        updated[existing] = { ...updated[existing], trust }
        return updated
      }
      return [...prev, { agentA, agentB, trust }]
    })
  }, [setRelationships])

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button onClick={() => addAgent()} variant="outline" className="h-10 gap-2 text-sm">
          <Plus className="size-4" />
          Add Agent
        </Button>
        <span className="ml-auto text-text-muted text-xs">
          {agents.length} {agents.length === 1 ? 'agent' : 'agents'}
        </span>
      </div>

      {/* Archetype presets */}
      <div>
        <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-2">
          <Sparkles className="size-3.5" />
          Quick Archetypes
        </h4>
        <ArchetypePresets onApply={preset => addAgent(preset)} />
      </div>

      {/* Agent list */}
      {agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="size-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
            <Users className="size-7 text-text-muted" />
          </div>
          <h3 className="text-text-secondary font-semibold mb-1">No agents yet</h3>
          <p className="text-text-muted text-sm max-w-xs mb-4">
            Add agents manually or use an archetype preset to quickly create
            characters with pre-filled traits and backstories.
          </p>
          <Button onClick={() => addAgent()} variant="outline" className="h-10 gap-2">
            <Plus className="size-4" />
            Add Agent
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              rooms={sceneState.rooms}
              onUpdate={updateAgent}
              onDelete={deleteAgent}
            />
          ))}
        </div>
      )}

      {/* Relationship matrix */}
      <RelationshipMatrix
        agents={agents}
        relationships={relationships}
        onUpdateRelationship={updateRelationship}
      />
    </div>
  )
}
