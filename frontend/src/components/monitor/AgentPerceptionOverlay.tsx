/**
 * AgentPerceptionOverlay — shows what an agent perceives vs. the full room.
 *
 * Two views:
 *   - Agent View (spotlight): only non-HIDDEN entities, exits, other agents,
 *     and the agent's own inventory. Like looking through the agent's eyes.
 *   - God View (full light): everything in the room including hidden items.
 *     Items the agent CAN'T see appear as ghosted/translucent silhouettes.
 *
 * Visual metaphor: a spotlight illuminating what the agent sees, with fog/shadow
 * over what they're missing. Toggle between views or compare side by side on desktop.
 *
 * Exhibition-grade elevation (curator feedback):
 *  - View transition: staggered entity reveal with scale-pop on hidden items
 *  - Agent view warmth: faint gold left-border on visible entities
 *  - Fog-of-war gradient: bottom edge fade in Agent mode
 *  - Perception diff counter: animated "Missing N items" badge with flash
 *
 * Mobile: bottom sheet (90vh), single view with toggle.
 * Desktop: side panel with optional side-by-side comparison.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import {
  Eye,
  EyeOff,
  X,
  MapPin,
  DoorOpen,
  Lock,
  Unlock,
  Package,
  User,
  Scan,
  Layers,
  Backpack,
  ChevronDown,
  ChevronUp,
  Ghost,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useRooms, useDoors, useAgents } from '@/stores/gameStore'
import type { AgentState, Entity, Door } from '@/types/game'

// ---------------------------------------------------------------------------
// Entity display card — with warmth tint and stagger animation support
// ---------------------------------------------------------------------------

interface EntityCardProps {
  entity: Entity
  isHidden: boolean // Whether this entity is hidden from the agent
  isGodView: boolean // Whether we're in god view mode
  staggerIndex?: number // For stagger animation on view transition
  isTransitioning?: boolean // Whether we're mid-transition
}

function EntityCard({ entity, isHidden, isGodView, staggerIndex = 0, isTransitioning = false }: EntityCardProps) {
  const stateColors: Record<string, string> = {
    default: 'bg-text-muted/15 text-text-muted',
    locked: 'bg-danger/15 text-danger',
    unlocked: 'bg-success/15 text-success',
    open: 'bg-success/15 text-success',
    closed: 'bg-warning/15 text-warning',
    hidden: 'bg-purple-500/15 text-purple-400',
    solved: 'bg-gold/15 text-gold',
    activated: 'bg-blue-500/15 text-blue-400',
  }

  return (
    <div
      className={cn(
        'relative flex items-start gap-2.5 px-3 py-2 rounded-lg border transition-all duration-200',
        isHidden && isGodView
          // Ghost effect for hidden items in god view — with scale-pop on transition
          ? 'border-purple-500/20 bg-purple-500/[0.03] opacity-50'
          : 'border-border/50 bg-bg-primary/40',
        // Agent view warmth: faint gold left-border on visible entities
        !isGodView && !isHidden && 'border-l-2 border-l-[#e3b341]/40 bg-gold/[0.02]',
        // Stagger animation when transitioning to god view
        isTransitioning && isHidden && isGodView && 'animate-entity-reveal',
      )}
      style={
        isTransitioning && isHidden && isGodView
          ? { animationDelay: `${staggerIndex * 60}ms` }
          : undefined
      }
    >
      {/* Ghost indicator for hidden items — with scale-pop on transition */}
      {isHidden && isGodView && (
        <div
          className={cn(
            'absolute -top-1 -right-1',
            isTransitioning && 'animate-scale-pop',
          )}
          style={isTransitioning ? { animationDelay: `${staggerIndex * 60}ms` } : undefined}
        >
          <Ghost size={14} className="text-purple-400 animate-status-pulse" />
        </div>
      )}

      {/* Entity icon */}
      <div className={cn(
        'w-7 h-7 rounded-md flex items-center justify-center shrink-0 mt-0.5',
        isHidden && isGodView ? 'bg-purple-500/10' : 'bg-bg-tertiary',
      )}>
        {entity.portable ? (
          <Package size={14} className={isHidden ? 'text-purple-400/50' : 'text-gold-dim'} />
        ) : (
          <Scan size={14} className={isHidden ? 'text-purple-400/50' : 'text-text-muted'} />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={cn(
            'text-sm font-medium truncate',
            isHidden && isGodView ? 'text-purple-400/60 italic' : 'text-text-primary',
          )}>
            {isHidden && isGodView ? `[${entity.name}]` : entity.name}
          </span>
          <span className={cn(
            'text-[10px] px-1.5 py-0.5 rounded-full shrink-0',
            stateColors[entity.state] ?? stateColors.default,
          )}>
            {entity.state}
          </span>
        </div>
        <p className={cn(
          'text-xs leading-relaxed m-0 mt-0.5',
          isHidden && isGodView ? 'text-purple-400/40' : 'text-text-secondary',
        )}>
          {isHidden && isGodView
            ? 'Hidden from this agent'
            : entity.description.length > 80
              ? entity.description.slice(0, 77) + '...'
              : entity.description}
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Door display
// ---------------------------------------------------------------------------

interface DoorCardProps {
  door: Door
  direction: string
  isGodView: boolean
}

function DoorCard({ door, direction, isGodView }: DoorCardProps) {
  return (
    <div className={cn(
      'flex items-center gap-2.5 px-3 py-2 rounded-lg border border-border/50 bg-bg-primary/40',
      // Agent view warmth on doors too
      !isGodView && 'border-l-2 border-l-[#e3b341]/40 bg-gold/[0.02]',
    )}>
      <div className={cn(
        'w-7 h-7 rounded-md flex items-center justify-center shrink-0',
        door.locked ? 'bg-danger/10' : 'bg-success/10',
      )}>
        {door.locked ? (
          <Lock size={14} className="text-danger" />
        ) : (
          <Unlock size={14} className="text-success" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary truncate">
            {door.name}
          </span>
          <span className="text-[10px] text-text-muted uppercase">{direction}</span>
        </div>
        <span className={cn(
          'text-[10px]',
          door.locked ? 'text-danger' : 'text-success',
        )}>
          {door.locked ? 'Locked' : 'Unlocked'}
          {door.key_id && isGodView && (
            <span className="text-text-muted ml-1">(key: {door.key_id})</span>
          )}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Agent presence card (other agents in the room)
// ---------------------------------------------------------------------------

function AgentPresenceCard({ agent: otherAgent }: { agent: AgentState }) {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-border/50 bg-bg-primary/40">
      <div className="w-7 h-7 rounded-full bg-gold/10 flex items-center justify-center shrink-0">
        <User size={14} className="text-gold" />
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium text-text-primary truncate block">
          {otherAgent.name}
        </span>
        <span className="text-xs text-text-secondary truncate block">
          {otherAgent.description.length > 60
            ? otherAgent.description.slice(0, 57) + '...'
            : otherAgent.description}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// View header with visual metaphor + perception diff counter
// ---------------------------------------------------------------------------

function ViewHeader({ isGodView, entityCount, hiddenCount, showBadgeFlash }: {
  isGodView: boolean
  entityCount: number
  hiddenCount: number
  showBadgeFlash: boolean
}) {
  return (
    <div className={cn(
      'flex items-center gap-2.5 px-4 py-2.5 rounded-lg border mb-3',
      isGodView
        ? 'border-purple-500/20 bg-purple-500/[0.04]'
        : 'border-gold/20 bg-gold/[0.04]',
    )}>
      <div className={cn(
        'w-8 h-8 rounded-full flex items-center justify-center',
        isGodView ? 'bg-purple-500/15' : 'bg-gold/15',
      )}>
        {isGodView ? (
          <Layers size={16} className="text-purple-400" />
        ) : (
          <Eye size={16} className="text-gold" />
        )}
      </div>
      <div className="flex-1">
        <span className={cn(
          'text-sm font-bold',
          isGodView ? 'text-purple-400' : 'text-gold',
        )}>
          {isGodView ? 'God View' : "Agent's View"}
        </span>
        <span className="text-[11px] text-text-muted block">
          {isGodView
            ? `${entityCount} total entities (${hiddenCount} hidden)`
            : `${entityCount - hiddenCount} visible entities`}
        </span>
      </div>
      {/* Perception diff counter — animated badge */}
      {hiddenCount > 0 && (
        <div
          className={cn(
            'flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium transition-all duration-200',
            isGodView
              ? 'bg-purple-500/15 text-purple-400'
              : 'bg-gold/10 text-gold',
            showBadgeFlash && 'animate-badge-flash',
          )}
        >
          <EyeOff size={10} />
          <span>Missing {hiddenCount}</span>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main perception overlay component
// ---------------------------------------------------------------------------

interface AgentPerceptionOverlayProps {
  agent: AgentState
  onClose: () => void
}

export function AgentPerceptionOverlay({ agent, onClose }: AgentPerceptionOverlayProps) {
  const rooms = useRooms()
  const allDoors = useDoors()
  const allAgents = useAgents()
  const [isGodView, setIsGodView] = useState(false)
  const [inventoryExpanded, setInventoryExpanded] = useState(true)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const [showBadgeFlash, setShowBadgeFlash] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const dragStartY = useRef<number | null>(null)
  const currentTranslateY = useRef(0)

  // Get the agent's current room
  const room = rooms[agent.room_id] ?? null
  const roomEntities = useMemo(() => {
    if (!room) return []
    return Object.values(room.entities)
  }, [room])

  // Split entities into visible (non-hidden) and hidden
  const visibleEntities = useMemo(
    () => roomEntities.filter(e => e.state !== 'hidden'),
    [roomEntities],
  )
  const hiddenEntities = useMemo(
    () => roomEntities.filter(e => e.state === 'hidden'),
    [roomEntities],
  )

  // Room doors with their directions
  const roomDoors = useMemo(() => {
    if (!room) return []
    return Object.entries(room.doors).map(([direction, doorId]) => ({
      direction,
      door: allDoors[doorId],
    })).filter(d => d.door)
  }, [room, allDoors])

  // Other agents in the same room
  const otherAgents = useMemo(() => {
    return Object.values(allAgents).filter(
      a => a.room_id === agent.room_id && a.id !== agent.id,
    )
  }, [allAgents, agent.room_id, agent.id])

  // Entities to display based on view mode
  const displayEntities = isGodView ? roomEntities : visibleEntities

  // Track hidden entity index for stagger offset
  let hiddenStaggerIndex = 0

  // Handle view toggle with transition animation
  const handleToggleView = useCallback((godView: boolean) => {
    setIsGodView(godView)
    setIsTransitioning(true)
    setShowBadgeFlash(true)
    // Clear transition state after animations complete
    const maxDelay = (hiddenEntities.length * 60) + 300
    setTimeout(() => setIsTransitioning(false), maxDelay)
    setTimeout(() => setShowBadgeFlash(false), 600)
  }, [hiddenEntities.length])

  // Swipe-to-dismiss
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

  return (
    <>
      {/* Backdrop with fog-of-war effect */}
      <div
        className={cn(
          'fixed inset-0 z-40 animate-gpu transition-colors duration-300',
          isGodView ? 'bg-purple-950/40 backdrop-blur-[2px]' : 'bg-black/60 backdrop-blur-[2px]',
        )}
        onClick={onClose}
        aria-hidden
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-label={`Perception overlay for ${agent.name}`}
        className={cn(
          'fixed z-50 flex flex-col',
          'bg-bg-secondary border-border',
          'transition-transform duration-200 ease-out',
          // Mobile: bottom sheet
          'inset-x-0 bottom-0 max-h-[90vh] rounded-t-2xl border-t',
          // Desktop: right panel
          'md:inset-y-0 md:right-0 md:left-auto md:bottom-auto',
          'md:w-[460px] md:max-h-full md:rounded-t-none md:rounded-l-xl md:border-l md:border-t-0',
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
            <div className={cn(
              'w-9 h-9 rounded-full flex items-center justify-center transition-colors duration-200',
              isGodView ? 'bg-purple-500/15' : 'bg-blue-500/15',
            )}>
              {isGodView ? (
                <Layers size={18} className="text-purple-400" />
              ) : (
                <Eye size={18} className="text-blue-400" />
              )}
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary m-0 leading-tight">
                {agent.name}'s Perception
              </h3>
              <span className="flex items-center gap-1 text-[11px] text-text-muted">
                <MapPin size={10} />
                {room?.name ?? agent.room_id}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary transition-colors"
            aria-label="Close perception overlay"
          >
            <X size={18} />
          </button>
        </div>

        {/* View toggle — Agent View vs God View */}
        <div className="shrink-0 px-4 py-2.5 border-b border-border/50">
          <div className="flex rounded-lg border border-border/50 bg-bg-primary/50 p-0.5">
            <button
              onClick={() => handleToggleView(false)}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all duration-200',
                !isGodView
                  ? 'bg-gold/10 text-gold shadow-[0_0_8px_rgba(227,179,65,0.1)]'
                  : 'text-text-muted hover:text-text-secondary',
              )}
            >
              <Eye size={14} />
              Agent's Eyes
            </button>
            <button
              onClick={() => handleToggleView(true)}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all duration-200',
                isGodView
                  ? 'bg-purple-500/10 text-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.1)]'
                  : 'text-text-muted hover:text-text-secondary',
              )}
            >
              <Layers size={14} />
              God View
              {hiddenEntities.length > 0 && (
                <span className="text-[10px] bg-purple-500/15 text-purple-400 px-1.5 py-0.5 rounded-full">
                  +{hiddenEntities.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Scrollable content — with fog-of-war gradient in Agent mode */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 relative">
          {/* View header banner with diff counter */}
          <ViewHeader
            isGodView={isGodView}
            entityCount={roomEntities.length}
            hiddenCount={hiddenEntities.length}
            showBadgeFlash={showBadgeFlash}
          />

          {/* Room description */}
          {room && (
            <div className="mb-4">
              <p className="text-sm text-text-secondary leading-relaxed m-0 italic">
                {room.description}
              </p>
            </div>
          )}

          {/* Entities section */}
          <div className="mb-4">
            <h4 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              <Scan size={12} />
              Entities ({isGodView ? roomEntities.length : visibleEntities.length})
              {isGodView && hiddenEntities.length > 0 && (
                <span className="text-purple-400 normal-case font-normal">
                  ({hiddenEntities.length} hidden)
                </span>
              )}
            </h4>
            {displayEntities.length === 0 ? (
              <p className="text-sm text-text-muted italic py-2">No entities visible</p>
            ) : (
              <div className="grid gap-1.5">
                {displayEntities.map((entity) => {
                  const isHidden = entity.state === 'hidden'
                  const currentStagger = isHidden ? hiddenStaggerIndex++ : 0
                  return (
                    <EntityCard
                      key={entity.id}
                      entity={entity}
                      isHidden={isHidden}
                      isGodView={isGodView}
                      staggerIndex={currentStagger}
                      isTransitioning={isTransitioning}
                    />
                  )
                })}
              </div>
            )}
          </div>

          {/* Exits / Doors section */}
          <div className="mb-4">
            <h4 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              <DoorOpen size={12} />
              Exits ({roomDoors.length})
            </h4>
            {roomDoors.length === 0 ? (
              <p className="text-sm text-text-muted italic py-2">No exits</p>
            ) : (
              <div className="grid gap-1.5">
                {roomDoors.map(({ direction, door }) => (
                  <DoorCard
                    key={door.id}
                    door={door}
                    direction={direction}
                    isGodView={isGodView}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Other agents present */}
          <div className="mb-4">
            <h4 className="flex items-center gap-2 text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              <User size={12} />
              Others Present ({otherAgents.length})
            </h4>
            {otherAgents.length === 0 ? (
              <p className="text-sm text-text-muted italic py-2">Alone in this room</p>
            ) : (
              <div className="grid gap-1.5">
                {otherAgents.map((a) => (
                  <AgentPresenceCard key={a.id} agent={a} />
                ))}
              </div>
            )}
          </div>

          {/* Agent's inventory */}
          <div>
            <button
              onClick={() => setInventoryExpanded(!inventoryExpanded)}
              className="flex items-center gap-2 w-full text-left min-h-0 mb-2"
            >
              <Backpack size={12} className="text-gold-dim" />
              <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                Inventory ({agent.inventory.length})
              </span>
              <span className="ml-auto text-text-muted">
                {inventoryExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </span>
            </button>
            {inventoryExpanded && (
              agent.inventory.length === 0 ? (
                <p className="text-sm text-text-muted italic py-2">Carrying nothing</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {agent.inventory.map((item) => (
                    <span
                      key={item.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-gold/[0.06] border border-gold/15 text-sm text-text-primary"
                      title={item.description}
                    >
                      <Package size={12} className="text-gold-dim shrink-0" />
                      {item.name}
                    </span>
                  ))}
                </div>
              )
            )}
          </div>

          {/* Fog-of-war gradient — bottom edge fade in Agent mode only */}
          {!isGodView && (
            <div
              className="pointer-events-none sticky bottom-0 left-0 right-0 h-5"
              style={{
                background: 'linear-gradient(to bottom, transparent, var(--color-bg-secondary))',
              }}
            />
          )}
        </div>

        {/* Footer — perception stats */}
        <div className="shrink-0 px-4 py-2 border-t border-border/50 bg-bg-primary/50">
          <div className="flex items-center justify-between text-[10px] text-text-muted">
            <span>
              {isGodView ? 'Showing all entities' : 'Agent perspective'}
            </span>
            <span>
              {visibleEntities.length} visible / {hiddenEntities.length} hidden
            </span>
          </div>
        </div>
      </div>
    </>
  )
}
