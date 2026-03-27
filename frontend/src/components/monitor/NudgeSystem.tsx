/**
 * NudgeSystem — spectator controls to whisper instructions into the escape room.
 *
 * Three nudge types:
 *   - Hint: suggest an agent examine a specific entity
 *   - Focus: redirect an agent to a specific puzzle/room
 *   - Talk: prompt two agents to discuss a topic
 *
 * Since the backend has no /api/nudge endpoint yet, nudges are stored in a
 * local Zustand store with optimistic UI. When the backend adds support,
 * swap the local store for API calls.
 *
 * Cooldown timer: 30 seconds between nudges.
 * Nudge history: collapsible log of all past nudges.
 *
 * Visual metaphor: whispering into the room — not clicking admin buttons.
 * Uses a speech-bubble / whisper aesthetic.
 *
 * Mobile: collapsible panel above simulation controls, expandable as bottom sheet.
 * Desktop: collapsible panel in the monitor layout.
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import {
  MessageCircle,
  Search,
  Target,
  Users,
  X,
  ChevronDown,
  ChevronUp,
  Clock,
  Send,
  Lightbulb,
  Focus,
  History,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAgents, useRooms, useEscapeChain } from '@/stores/gameStore'
import type { AgentState, Room, EscapeChainStep } from '@/types/game'

// ---------------------------------------------------------------------------
// Nudge types and store
// ---------------------------------------------------------------------------

type NudgeType = 'hint' | 'focus' | 'talk'

interface Nudge {
  id: string
  type: NudgeType
  timestamp: number
  agentId: string
  agentName: string
  // For hint: entityName
  entityName?: string
  // For focus: puzzleStep description
  puzzleDescription?: string
  // For talk: second agent + topic
  targetAgentId?: string
  targetAgentName?: string
  topic?: string
  // Status
  status: 'sent' | 'acknowledged'
}

// Simple in-memory store (no Zustand dependency — keep it self-contained)
let nudgeHistory: Nudge[] = []
let nudgeListeners: Array<() => void> = []

function addNudge(nudge: Nudge) {
  nudgeHistory = [nudge, ...nudgeHistory].slice(0, 50)
  nudgeListeners.forEach(fn => fn())
}

function useNudgeHistory() {
  const [, forceUpdate] = useState(0)
  useEffect(() => {
    const listener = () => forceUpdate(n => n + 1)
    nudgeListeners.push(listener)
    return () => {
      nudgeListeners = nudgeListeners.filter(l => l !== listener)
    }
  }, [])
  return nudgeHistory
}

// ---------------------------------------------------------------------------
// Cooldown timer hook
// ---------------------------------------------------------------------------

const COOLDOWN_MS = 30_000

function useCooldown() {
  const [lastNudgeTime, setLastNudgeTime] = useState(0)
  const [remainingMs, setRemainingMs] = useState(0)

  useEffect(() => {
    if (lastNudgeTime === 0) return
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastNudgeTime
      const remaining = Math.max(COOLDOWN_MS - elapsed, 0)
      setRemainingMs(remaining)
      if (remaining === 0) clearInterval(interval)
    }, 100)
    return () => clearInterval(interval)
  }, [lastNudgeTime])

  const triggerCooldown = useCallback(() => {
    setLastNudgeTime(Date.now())
    setRemainingMs(COOLDOWN_MS)
  }, [])

  return {
    isOnCooldown: remainingMs > 0,
    remainingMs,
    remainingSeconds: Math.ceil(remainingMs / 1000),
    triggerCooldown,
  }
}

// ---------------------------------------------------------------------------
// Agent selector dropdown
// ---------------------------------------------------------------------------

function AgentSelector({
  agents,
  selectedId,
  onSelect,
  label,
  excludeId,
}: {
  agents: AgentState[]
  selectedId: string
  onSelect: (id: string) => void
  label: string
  excludeId?: string
}) {
  const filtered = excludeId ? agents.filter(a => a.id !== excludeId) : agents

  return (
    <div>
      <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
        {label}
      </label>
      <div className="grid gap-1">
        {filtered.map((agent) => (
          <button
            key={agent.id}
            onClick={() => onSelect(agent.id)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg border text-left transition-all duration-150',
              'text-sm',
              selectedId === agent.id
                ? 'border-gold/40 bg-gold/[0.06] text-gold'
                : 'border-border/50 bg-bg-primary/40 text-text-secondary hover:border-border hover:text-text-primary',
            )}
          >
            <div className={cn(
              'w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-[10px] font-bold',
              selectedId === agent.id ? 'bg-gold/15 text-gold' : 'bg-bg-tertiary text-text-muted',
            )}>
              {agent.name.charAt(0)}
            </div>
            {agent.name}
          </button>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Entity selector for hints
// ---------------------------------------------------------------------------

function EntitySelector({
  room,
  selectedEntity,
  onSelect,
}: {
  room: Room | null
  selectedEntity: string
  onSelect: (name: string) => void
}) {
  const entities = useMemo(() => {
    if (!room) return []
    return Object.values(room.entities)
  }, [room])

  if (!room || entities.length === 0) {
    return (
      <div>
        <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
          Entity to examine
        </label>
        <p className="text-sm text-text-muted italic">No entities in this room</p>
      </div>
    )
  }

  return (
    <div>
      <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
        Entity to examine
      </label>
      <div className="flex flex-wrap gap-1.5">
        {entities.map((entity) => (
          <button
            key={entity.id}
            onClick={() => onSelect(entity.name)}
            className={cn(
              'px-2.5 py-1.5 rounded-md border text-sm transition-all duration-150',
              selectedEntity === entity.name
                ? 'border-gold/40 bg-gold/[0.06] text-gold'
                : 'border-border/50 bg-bg-primary/40 text-text-secondary hover:border-border',
            )}
          >
            {entity.name}
          </button>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Puzzle selector for focus nudges
// ---------------------------------------------------------------------------

function PuzzleSelector({
  escapeChain,
  selectedStep,
  onSelect,
}: {
  escapeChain: EscapeChainStep[]
  selectedStep: string
  onSelect: (desc: string) => void
}) {
  const activePuzzles = escapeChain.filter(s => s.status !== 'solved')

  if (activePuzzles.length === 0) {
    return (
      <div>
        <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
          Puzzle to focus on
        </label>
        <p className="text-sm text-text-muted italic">All puzzles solved</p>
      </div>
    )
  }

  return (
    <div>
      <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
        Puzzle to focus on
      </label>
      <div className="grid gap-1">
        {activePuzzles.map((step) => (
          <button
            key={step.step}
            onClick={() => onSelect(step.description)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg border text-left text-sm transition-all duration-150',
              selectedStep === step.description
                ? 'border-gold/40 bg-gold/[0.06] text-gold'
                : 'border-border/50 bg-bg-primary/40 text-text-secondary hover:border-border',
            )}
          >
            <span className={cn(
              'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0',
              step.status === 'active' ? 'bg-gold/15 text-gold' : 'bg-bg-tertiary text-text-muted',
            )}>
              {step.step}
            </span>
            <span className="truncate">{step.description}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Nudge history log entry
// ---------------------------------------------------------------------------

function NudgeLogEntry({ nudge }: { nudge: Nudge }) {
  const icons = {
    hint: Lightbulb,
    focus: Focus,
    talk: MessageCircle,
  }
  const colors = {
    hint: 'text-gold',
    focus: 'text-blue-400',
    talk: 'text-purple-400',
  }
  const Icon = icons[nudge.type]
  const timeAgo = formatTimeAgo(nudge.timestamp)

  let description = ''
  if (nudge.type === 'hint') {
    description = `Whispered to ${nudge.agentName}: examine the ${nudge.entityName}`
  } else if (nudge.type === 'focus') {
    description = `Directed ${nudge.agentName} toward: ${nudge.puzzleDescription}`
  } else if (nudge.type === 'talk') {
    description = `Prompted ${nudge.agentName} and ${nudge.targetAgentName} to discuss: ${nudge.topic}`
  }

  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-bg-primary/30 border border-border/30">
      <Icon size={14} className={cn('shrink-0 mt-0.5', colors[nudge.type])} />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-text-secondary leading-relaxed m-0">{description}</p>
        <span className="text-[10px] text-text-muted">{timeAgo}</span>
      </div>
    </div>
  )
}

function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  return `${Math.floor(minutes / 60)}h ago`
}

// ---------------------------------------------------------------------------
// Nudge type tab selector
// ---------------------------------------------------------------------------

function NudgeTypeSelector({
  activeType,
  onSelect,
}: {
  activeType: NudgeType
  onSelect: (type: NudgeType) => void
}) {
  const types: Array<{ key: NudgeType; label: string; Icon: typeof Lightbulb; color: string }> = [
    { key: 'hint', label: 'Hint', Icon: Lightbulb, color: 'text-gold' },
    { key: 'focus', label: 'Focus', Icon: Focus, color: 'text-blue-400' },
    { key: 'talk', label: 'Talk', Icon: MessageCircle, color: 'text-purple-400' },
  ]

  return (
    <div className="flex gap-1 p-0.5 rounded-lg border border-border/50 bg-bg-primary/50">
      {types.map(({ key, label, Icon, color }) => (
        <button
          key={key}
          onClick={() => onSelect(key)}
          className={cn(
            'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-xs font-medium transition-all duration-150',
            activeType === key
              ? cn('bg-bg-tertiary', color, 'shadow-sm')
              : 'text-text-muted hover:text-text-secondary',
          )}
        >
          <Icon size={13} />
          {label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cooldown bar
// ---------------------------------------------------------------------------

function CooldownBar({ remainingSeconds, remainingMs }: { remainingSeconds: number; remainingMs: number }) {
  const progress = 1 - (remainingMs / COOLDOWN_MS)

  return (
    <div className="px-4 py-2 border-t border-border/50">
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Clock size={12} className="animate-status-pulse" />
        <span>Cooldown: {remainingSeconds}s</span>
        <div className="flex-1 h-1 rounded-full bg-bg-tertiary overflow-hidden">
          <div
            className="h-full bg-gold/40 rounded-full transition-all duration-100"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main NudgeSystem component
// ---------------------------------------------------------------------------

export function NudgeSystem() {
  const agentsRecord = useAgents()
  const agents = useMemo(() => Object.values(agentsRecord), [agentsRecord])
  const rooms = useRooms()
  const escapeChain = useEscapeChain()
  const history = useNudgeHistory()

  const [isExpanded, setIsExpanded] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [nudgeType, setNudgeType] = useState<NudgeType>('hint')
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [selectedEntity, setSelectedEntity] = useState('')
  const [selectedPuzzle, setSelectedPuzzle] = useState('')
  const [targetAgentId, setTargetAgentId] = useState('')
  const [topic, setTopic] = useState('')
  const [isSending, setIsSending] = useState(false)

  const { isOnCooldown, remainingMs, remainingSeconds, triggerCooldown } = useCooldown()

  // Get the selected agent's room for entity selection
  const selectedAgent = agents.find(a => a.id === selectedAgentId)
  const selectedRoom = selectedAgent ? rooms[selectedAgent.room_id] ?? null : null
  const targetAgent = agents.find(a => a.id === targetAgentId)

  // Reset selections when nudge type changes
  useEffect(() => {
    setSelectedEntity('')
    setSelectedPuzzle('')
    setTargetAgentId('')
    setTopic('')
  }, [nudgeType])

  // Can we send this nudge?
  const canSend = useMemo(() => {
    if (isOnCooldown || isSending || !selectedAgentId) return false
    if (nudgeType === 'hint') return !!selectedEntity
    if (nudgeType === 'focus') return !!selectedPuzzle
    if (nudgeType === 'talk') return !!targetAgentId && topic.trim().length > 0
    return false
  }, [isOnCooldown, isSending, selectedAgentId, nudgeType, selectedEntity, selectedPuzzle, targetAgentId, topic])

  const handleSend = useCallback(async () => {
    if (!canSend || !selectedAgent) return
    setIsSending(true)

    // Simulate API call (replace with real POST /api/nudge when backend supports it)
    await new Promise(resolve => setTimeout(resolve, 400))

    const nudge: Nudge = {
      id: `nudge-${Date.now()}`,
      type: nudgeType,
      timestamp: Date.now(),
      agentId: selectedAgentId,
      agentName: selectedAgent.name,
      entityName: selectedEntity || undefined,
      puzzleDescription: selectedPuzzle || undefined,
      targetAgentId: targetAgentId || undefined,
      targetAgentName: targetAgent?.name || undefined,
      topic: topic || undefined,
      status: 'sent',
    }

    addNudge(nudge)
    triggerCooldown()
    setIsSending(false)

    // Reset form
    setSelectedEntity('')
    setSelectedPuzzle('')
    setTargetAgentId('')
    setTopic('')
  }, [canSend, nudgeType, selectedAgentId, selectedAgent, selectedEntity, selectedPuzzle, targetAgentId, targetAgent, topic, triggerCooldown])

  // Don't render anything if no agents exist
  if (agents.length === 0) return null

  return (
    <div className="border-t border-border/50 bg-bg-secondary">
      {/* Collapsed header — tap to expand */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          'w-full flex items-center justify-between px-4 py-2.5 text-left transition-all duration-150',
          'hover:bg-bg-tertiary/50',
        )}
      >
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-gold/10 flex items-center justify-center">
            <MessageCircle size={14} className="text-gold" />
          </div>
          <span className="text-sm font-medium text-text-primary">Spectator Nudge</span>
          {history.length > 0 && (
            <span className="text-[10px] bg-gold/10 text-gold px-1.5 py-0.5 rounded-full">
              {history.length}
            </span>
          )}
          {isOnCooldown && (
            <span className="text-[10px] text-text-muted flex items-center gap-1">
              <Clock size={10} className="animate-status-pulse" />
              {remainingSeconds}s
            </span>
          )}
        </div>
        <span className="text-text-muted">
          {isExpanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </span>
      </button>

      {/* Expanded panel */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-3 animate-card-in">
          {/* Nudge type selector */}
          <NudgeTypeSelector activeType={nudgeType} onSelect={setNudgeType} />

          {/* Whisper instruction text */}
          <p className="text-[11px] text-text-muted italic leading-relaxed">
            {nudgeType === 'hint' && 'Whisper to an agent to examine something specific...'}
            {nudgeType === 'focus' && 'Redirect an agent toward an unsolved puzzle...'}
            {nudgeType === 'talk' && 'Prompt two agents to discuss a topic together...'}
          </p>

          {/* Agent selector (always shown) */}
          <AgentSelector
            agents={agents}
            selectedId={selectedAgentId}
            onSelect={setSelectedAgentId}
            label={nudgeType === 'talk' ? 'First agent' : 'Select agent'}
          />

          {/* Type-specific controls */}
          {nudgeType === 'hint' && selectedAgentId && (
            <EntitySelector
              room={selectedRoom}
              selectedEntity={selectedEntity}
              onSelect={setSelectedEntity}
            />
          )}

          {nudgeType === 'focus' && selectedAgentId && (
            <PuzzleSelector
              escapeChain={escapeChain}
              selectedStep={selectedPuzzle}
              onSelect={setSelectedPuzzle}
            />
          )}

          {nudgeType === 'talk' && selectedAgentId && (
            <>
              <AgentSelector
                agents={agents}
                selectedId={targetAgentId}
                onSelect={setTargetAgentId}
                label="Second agent"
                excludeId={selectedAgentId}
              />
              {targetAgentId && (
                <div>
                  <label className="text-[11px] text-text-muted uppercase tracking-wider font-semibold block mb-1.5">
                    Topic to discuss
                  </label>
                  <input
                    type="text"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="e.g., the combination to the safe..."
                    className={cn(
                      'w-full px-3 py-2 rounded-lg text-sm',
                      'bg-bg-primary border border-border/50',
                      'text-text-primary placeholder:text-text-muted/50',
                      'focus:outline-none focus:border-gold/40 focus:shadow-[0_0_8px_rgba(227,179,65,0.1)]',
                      'transition-all duration-150',
                    )}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && canSend) handleSend()
                    }}
                  />
                </div>
              )}
            </>
          )}

          {/* Send button */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className={cn(
              'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg',
              'text-sm font-medium transition-all duration-200',
              canSend
                ? 'bg-gold/10 border border-gold/30 text-gold hover:bg-gold/15 active:scale-[0.98] shadow-[0_0_12px_rgba(227,179,65,0.08)]'
                : 'bg-bg-tertiary border border-border/50 text-text-muted cursor-not-allowed',
            )}
          >
            {isSending ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Sending...
              </>
            ) : isOnCooldown ? (
              <>
                <Clock size={15} />
                Cooldown ({remainingSeconds}s)
              </>
            ) : (
              <>
                <Send size={15} />
                Send Nudge
              </>
            )}
          </button>

          {/* Cooldown progress bar */}
          {isOnCooldown && (
            <CooldownBar remainingSeconds={remainingSeconds} remainingMs={remainingMs} />
          )}

          {/* History toggle */}
          {history.length > 0 && (
            <div>
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="flex items-center gap-2 text-xs text-text-muted hover:text-text-secondary transition-colors min-h-0 w-full text-left"
              >
                <History size={12} />
                Nudge History ({history.length})
                <span className="ml-auto">
                  {showHistory ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </span>
              </button>

              {showHistory && (
                <div className="mt-2 grid gap-1.5 max-h-[200px] overflow-y-auto">
                  {history.map((nudge) => (
                    <NudgeLogEntry key={nudge.id} nudge={nudge} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
