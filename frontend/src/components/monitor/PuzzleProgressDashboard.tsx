/**
 * PuzzleProgressDashboard — Collapsible panel for the Game Monitor.
 *
 * Shows all escape chain steps (which represent puzzles) in a grid:
 * - Puzzle name, type icon, room, status badge (unsolved/in-progress/solved)
 * - Clues found vs required (based on entity discovery in the room)
 * - Warmth indicator (cold/warm/hot) based on clue discovery ratio
 * - Click a puzzle to expand and see entity details and solver info
 *
 * Data comes from the Zustand store: escape chain steps + world state entities.
 * Mobile: single column list with expandable cards, collapsed by default.
 */

import { useState, useMemo } from 'react'
import {
  ChevronDown, ChevronRight, ChevronUp,
  Key, Hash, Lock, Footprints, Search, ToggleLeft,
  Flame, Snowflake, Thermometer,
  CheckCircle2, Clock, Circle,
  MapPin, User, Package,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useEscapeChain,
  useRooms,
  useAgents,
} from '@/stores/gameStore'
import type { EscapeChainStep } from '@/types/game'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

/** Map escape chain check_type / action to icons (matching P1-003 puzzle types) */
const PUZZLE_TYPE_ICONS: Record<string, React.ElementType> = {
  use: Key,
  examine: Search,
  unlock: Lock,
  activate: ToggleLeft,
  solve: Hash,
  open: Lock,
  push: Footprints,
  pull: ToggleLeft,
  // Fallbacks for check_type values
  entity_state: Key,
  entity_in_room: MapPin,
  inventory_has: Package,
}

function getPuzzleIcon(step: EscapeChainStep): React.ElementType {
  return PUZZLE_TYPE_ICONS[step.action] ?? PUZZLE_TYPE_ICONS[step.check_type] ?? Key
}

/* ------------------------------------------------------------------ */
/*  Status badge                                                       */
/* ------------------------------------------------------------------ */

function StatusBadge({ status }: { status: EscapeChainStep['status'] }) {
  const config = {
    solved: {
      icon: CheckCircle2,
      label: 'Solved',
      classes: 'bg-success/15 text-success border-success/20',
    },
    active: {
      icon: Clock,
      label: 'In Progress',
      classes: 'bg-gold/15 text-gold border-gold/20',
    },
    pending: {
      icon: Circle,
      label: 'Unsolved',
      classes: 'bg-bg-tertiary text-text-muted border-border',
    },
  }[status]

  const Icon = config.icon

  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border',
      config.classes,
    )}>
      <Icon className="size-3" />
      {config.label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Warmth indicator                                                   */
/* ------------------------------------------------------------------ */

function WarmthIndicator({ ratio }: { ratio: number }) {
  // ratio: 0 = cold, 0.5 = warm, 1.0 = hot
  let config: { icon: React.ElementType; label: string; color: string }

  if (ratio >= 0.7) {
    config = { icon: Flame, label: 'Hot', color: 'text-danger' }
  } else if (ratio >= 0.3) {
    config = { icon: Thermometer, label: 'Warm', color: 'text-warning' }
  } else {
    config = { icon: Snowflake, label: 'Cold', color: 'text-blue-400' }
  }

  const Icon = config.icon

  return (
    <span className={cn('inline-flex items-center gap-1 text-[11px] font-medium', config.color)}>
      <Icon className="size-3" />
      {config.label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Individual puzzle card (expandable)                                 */
/* ------------------------------------------------------------------ */

function PuzzleCard({ step, index }: { step: EscapeChainStep; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const rooms = useRooms()
  const agents = useAgents()

  const PuzzleIcon = getPuzzleIcon(step)
  const room = rooms[step.room_id]

  // Calculate warmth based on step position relative to solved steps
  // Steps closer to being solved (active) are warmer
  const warmthRatio = step.status === 'solved' ? 1.0
    : step.status === 'active' ? 0.5
    : 0.0

  // Count entities in the room that could be clues (non-default state)
  const roomEntities = room ? Object.values(room.entities) : []
  const discoveredEntities = roomEntities.filter(
    e => e.state !== 'hidden' && e.state !== 'default'
  )
  const totalClues = Math.max(roomEntities.length, 1)
  const foundClues = discoveredEntities.length
  const clueRatio = totalClues > 0 ? foundClues / totalClues : 0

  // Solver info
  const solverName = step.solved_by ? (agents[step.solved_by]?.name ?? step.solved_by) : null

  return (
    <div className={cn(
      'rounded-xl border transition-colors',
      step.status === 'solved' ? 'border-success/20 bg-success/5' :
      step.status === 'active' ? 'border-gold/20 bg-gold/5' :
      'border-border bg-bg-secondary',
    )}>
      {/* Header — always visible, tappable */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-3 text-left min-h-[56px]"
      >
        {/* Step number + icon */}
        <div className={cn(
          'size-10 rounded-lg flex items-center justify-center shrink-0',
          step.status === 'solved' ? 'bg-success/15' :
          step.status === 'active' ? 'bg-gold/15' :
          'bg-bg-tertiary',
        )}>
          <PuzzleIcon className={cn(
            'size-5',
            step.status === 'solved' ? 'text-success' :
            step.status === 'active' ? 'text-gold' :
            'text-text-muted',
          )} />
        </div>

        {/* Name + room */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-text-primary text-sm font-medium truncate">
              {step.description || step.target || `Step ${step.step}`}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
            <span className="flex items-center gap-1">
              <MapPin className="size-3" />
              {step.room || 'Unknown'}
            </span>
            <span className="text-text-muted/40">|</span>
            <span>{foundClues}/{totalClues} clues</span>
          </div>
        </div>

        {/* Right side: status + warmth + expand */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="hidden sm:flex flex-col items-end gap-1">
            <StatusBadge status={step.status} />
            {step.status !== 'solved' && <WarmthIndicator ratio={clueRatio} />}
          </div>
          <div className="flex items-center justify-center size-8 min-h-[44px] min-w-[44px]">
            {expanded ? (
              <ChevronDown className="size-4 text-text-muted" />
            ) : (
              <ChevronRight className="size-4 text-text-muted" />
            )}
          </div>
        </div>
      </button>

      {/* Mobile-only badges (below header, above expanded) */}
      <div className="sm:hidden flex items-center gap-2 px-3 pb-2 -mt-1">
        <StatusBadge status={step.status} />
        {step.status !== 'solved' && <WarmthIndicator ratio={clueRatio} />}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-border/50 pt-3 animate-card-in">
          {/* Solver info */}
          {step.solved_by && (
            <div className="flex items-center gap-2 p-2 rounded-lg bg-success/10 border border-success/20">
              <User className="size-4 text-success" />
              <span className="text-sm text-success">
                Solved by <span className="font-medium">{solverName}</span>
                {step.solved_at != null && (
                  <span className="text-success/70"> at tick {step.solved_at}</span>
                )}
              </span>
            </div>
          )}

          {/* Step details */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="text-text-secondary font-medium w-20 shrink-0">Action:</span>
              <span className="text-text-primary">{step.action}</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-text-secondary font-medium w-20 shrink-0">Target:</span>
              <span className="text-text-primary">{step.target}</span>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-text-secondary font-medium w-20 shrink-0">Check type:</span>
              <span className="text-text-primary">{step.check_type}</span>
            </div>
          </div>

          {/* Room entities (clue list) */}
          {roomEntities.length > 0 && (
            <div>
              <h5 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-1.5">
                Room Entities ({room?.name})
              </h5>
              <div className="space-y-1">
                {roomEntities.map(entity => (
                  <div
                    key={entity.id}
                    className={cn(
                      'flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs',
                      entity.state === 'hidden' ? 'bg-bg-tertiary/50 text-text-muted' :
                      entity.state === 'solved' || entity.state === 'unlocked' || entity.state === 'activated'
                        ? 'bg-success/10 text-success'
                        : 'bg-bg-primary text-text-secondary',
                    )}
                  >
                    <span className={cn(
                      'size-2 rounded-full shrink-0',
                      entity.state === 'hidden' ? 'bg-text-muted/40' :
                      entity.state === 'solved' || entity.state === 'unlocked' || entity.state === 'activated'
                        ? 'bg-success'
                        : 'bg-text-secondary/40',
                    )} />
                    <span className="truncate font-medium">{entity.name}</span>
                    <span className="ml-auto text-[10px] opacity-70">{entity.state}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main PuzzleProgressDashboard Component                             */
/* ------------------------------------------------------------------ */

export function PuzzleProgressDashboard() {
  const [collapsed, setCollapsed] = useState(true)
  const escapeChain = useEscapeChain()

  // Summary stats
  const stats = useMemo(() => {
    const solved = escapeChain.filter(s => s.status === 'solved').length
    const active = escapeChain.filter(s => s.status === 'active').length
    const pending = escapeChain.filter(s => s.status === 'pending').length
    return { solved, active, pending, total: escapeChain.length }
  }, [escapeChain])

  // Don't render if no escape chain data
  if (escapeChain.length === 0) return null

  return (
    <div className="border-b border-border bg-bg-primary">
      {/* Toggle header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-3 px-3 py-2.5 md:px-4 text-left min-h-[44px]"
      >
        <Key className="size-4 text-gold shrink-0" />
        <span className="text-text-primary text-sm font-semibold">
          Puzzle Progress
        </span>

        {/* Summary badges */}
        <div className="flex items-center gap-2 ml-auto">
          {stats.solved > 0 && (
            <span className="text-[11px] font-medium text-success bg-success/10 px-1.5 py-0.5 rounded">
              {stats.solved} solved
            </span>
          )}
          {stats.active > 0 && (
            <span className="text-[11px] font-medium text-gold bg-gold/10 px-1.5 py-0.5 rounded">
              {stats.active} active
            </span>
          )}
          <span className="text-text-muted text-xs">
            {stats.solved}/{stats.total}
          </span>
          {collapsed ? (
            <ChevronDown className="size-4 text-text-muted" />
          ) : (
            <ChevronUp className="size-4 text-text-muted" />
          )}
        </div>
      </button>

      {/* Expanded panel */}
      {!collapsed && (
        <div className="px-3 pb-3 md:px-4 md:pb-4 space-y-2 animate-card-in">
          {/* Grid on desktop, single column on mobile */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {escapeChain.map((step, index) => (
              <PuzzleCard key={step.entity_id || index} step={step} index={index} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
