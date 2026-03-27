/**
 * AgentStatusStrip — horizontal scrollable strip of agent cards.
 *
 * Sits at the top of the Monitor page (below header, above narrative feed).
 * Each card shows: agent name, current room, inventory count/icons, and goal.
 * Tapping a card opens a detail view — bottom sheet on mobile, expanded
 * inline panel on desktop.
 *
 * Mobile-first: horizontal scroll, touch-friendly 44px+ targets, compact height.
 */

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { useAgents, useRooms, useIsProcessing } from '@/stores/gameStore'
import type { AgentState } from '@/types/game'
import { cn } from '@/lib/utils'
import {
  Package,
  MapPin,
  Target,
  X,
  User,
  Backpack,
  Brain,
  Eye,
} from 'lucide-react'
import { AgentMemoryInspector } from './AgentMemoryInspector'
import { AgentPerceptionOverlay } from './AgentPerceptionOverlay'

// ---------------------------------------------------------------------------
// Agent card — compact representation in the strip
// ---------------------------------------------------------------------------

interface AgentCardProps {
  agent: AgentState
  roomName: string
  isActive: boolean
  actionText: string | null
  isSelected: boolean
  onSelect: () => void
}

function AgentCard({ agent, roomName, isActive, actionText, isSelected, onSelect }: AgentCardProps) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        // Base — mobile first, compact card
        'relative shrink-0 flex flex-col gap-1 rounded-lg border px-3 py-2',
        'w-[140px] min-h-[72px] text-left transition-all duration-150',
        'bg-bg-secondary hover:bg-bg-tertiary active:scale-[0.97]',
        // Border and glow states
        isSelected
          ? 'border-gold shadow-[0_0_8px_rgba(227,179,65,0.25)]'
          : isActive
            ? 'border-gold/50 shadow-[0_0_4px_rgba(227,179,65,0.15)]'
            : 'border-border',
      )}
      aria-label={`Agent ${agent.name}, in ${roomName}`}
      aria-expanded={isSelected}
    >
      {/* Active indicator dot */}
      {isActive && (
        <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-gold animate-status-pulse" />
      )}

      {/* Agent name */}
      <span className={cn(
        'text-sm font-bold truncate pr-4',
        isActive ? 'text-gold' : 'text-text-primary',
      )}>
        {agent.name}
      </span>

      {/* Room name */}
      <span className="flex items-center gap-1 text-xs text-text-secondary truncate">
        <MapPin size={10} className="shrink-0" />
        {roomName}
      </span>

      {/* Bottom row: inventory count + action hint */}
      <div className="flex items-center gap-2 mt-auto">
        {agent.inventory.length > 0 && (
          <span className="inline-flex items-center gap-0.5 text-xs text-text-muted">
            <Backpack size={10} />
            {agent.inventory.length}
          </span>
        )}
        {actionText && (
          <span className="text-[10px] text-gold-dim truncate max-w-[80px]">
            {actionText}
          </span>
        )}
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Agent detail bottom sheet (mobile) / panel (desktop)
// ---------------------------------------------------------------------------

interface AgentDetailProps {
  agent: AgentState
  roomName: string
  onClose: () => void
  onOpenMemory: () => void
  onOpenPerception: () => void
}

function AgentDetail({ agent, roomName, onClose, onOpenMemory, onOpenPerception }: AgentDetailProps) {
  const sheetRef = useRef<HTMLDivElement>(null)
  const dragStartY = useRef<number | null>(null)
  const currentTranslateY = useRef(0)

  // Swipe-to-dismiss for mobile bottom sheet
  const onTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartY.current = e.touches[0].clientY
    currentTranslateY.current = 0
  }, [])

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (dragStartY.current === null || !sheetRef.current) return
    const deltaY = e.touches[0].clientY - dragStartY.current
    // Only allow dragging downward
    if (deltaY > 0) {
      currentTranslateY.current = deltaY
      sheetRef.current.style.transform = `translateY(${deltaY}px)`
    }
  }, [])

  const onTouchEnd = useCallback(() => {
    if (dragStartY.current === null || !sheetRef.current) return
    // Dismiss if dragged more than 80px down
    if (currentTranslateY.current > 80) {
      onClose()
    } else {
      // Snap back
      sheetRef.current.style.transform = 'translateY(0)'
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
      {/* Backdrop — click to dismiss */}
      <div
        className="fixed inset-0 z-40 bg-black/50 animate-gpu"
        onClick={onClose}
        aria-hidden
      />

      {/* Sheet/panel */}
      <div
        ref={sheetRef}
        role="dialog"
        aria-label={`Details for agent ${agent.name}`}
        className={cn(
          'fixed z-50 bg-bg-secondary border-t border-border rounded-t-2xl',
          'transition-transform duration-200 ease-out',
          // Mobile: bottom sheet, 50% viewport height
          'inset-x-0 bottom-0 max-h-[50vh] overflow-y-auto',
          // Desktop: centered panel instead
          'md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2',
          'md:w-[420px] md:max-h-[60vh] md:rounded-xl md:border',
        )}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-full bg-gold/15 flex items-center justify-center">
              <User size={18} className="text-gold" />
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary m-0 leading-tight">
                {agent.name}
              </h3>
              <span className="flex items-center gap-1 text-xs text-text-secondary">
                <MapPin size={10} />
                {roomName}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body content */}
        <div className="px-4 py-3 space-y-4">
          {/* Description */}
          {agent.description && (
            <div>
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">
                Description
              </h4>
              <p className="text-sm text-text-secondary leading-relaxed m-0">
                {agent.description}
              </p>
            </div>
          )}

          {/* Goal */}
          {agent.goal && (
            <div>
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1 flex items-center gap-1">
                <Target size={12} />
                Goal
              </h4>
              <p className="text-sm text-text-primary leading-relaxed m-0">
                {agent.goal}
              </p>
            </div>
          )}

          {/* Inventory */}
          <div>
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2 flex items-center gap-1">
              <Package size={12} />
              Inventory ({agent.inventory.length})
            </h4>
            {agent.inventory.length === 0 ? (
              <p className="text-sm text-text-muted italic m-0">Empty</p>
            ) : (
              <ul className="flex flex-wrap gap-2 list-none m-0 p-0">
                {agent.inventory.map((item) => (
                  <li
                    key={item.id}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-bg-tertiary border border-border text-sm text-text-primary"
                    title={item.description}
                  >
                    <Package size={12} className="text-gold-dim shrink-0" />
                    {item.name}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Deep inspection buttons — Memory and Perception (P2-002, P2-003) */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={onOpenMemory}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg',
                'bg-gold/[0.06] border border-gold/20 text-gold',
                'hover:bg-gold/10 active:scale-[0.97] transition-all duration-150',
                'text-sm font-medium',
              )}
            >
              <Brain size={15} />
              Memory
            </button>
            <button
              onClick={onOpenPerception}
              className={cn(
                'flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg',
                'bg-blue-500/[0.06] border border-blue-500/20 text-blue-400',
                'hover:bg-blue-500/10 active:scale-[0.97] transition-all duration-150',
                'text-sm font-medium',
              )}
            >
              <Eye size={15} />
              Perception
            </button>
          </div>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyStrip() {
  return (
    <div className="flex items-center justify-center h-[72px] px-4 text-sm text-text-muted">
      No agents in the world yet
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main strip component
// ---------------------------------------------------------------------------

export function AgentStatusStrip() {
  // Use the record selector (stable reference) and derive array via useMemo
  // to avoid React 19 infinite-loop from Object.values() in a selector.
  const agentsRecord = useAgents()
  const agents = useMemo(() => Object.values(agentsRecord), [agentsRecord])

  const rooms = useRooms()
  const isProcessing = useIsProcessing()
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [memoryAgentId, setMemoryAgentId] = useState<string | null>(null)
  const [perceptionAgentId, setPerceptionAgentId] = useState<string | null>(null)

  const getRoomName = useCallback((roomId: string) => {
    return rooms[roomId]?.name ?? roomId
  }, [rooms])

  const selectedAgent = selectedAgentId
    ? agents.find((a) => a.id === selectedAgentId) ?? null
    : null

  const memoryAgent = memoryAgentId
    ? agents.find((a) => a.id === memoryAgentId) ?? null
    : null

  const perceptionAgent = perceptionAgentId
    ? agents.find((a) => a.id === perceptionAgentId) ?? null
    : null

  const handleSelect = useCallback((agentId: string) => {
    setSelectedAgentId((prev) => (prev === agentId ? null : agentId))
  }, [])

  const handleCloseDetail = useCallback(() => {
    setSelectedAgentId(null)
  }, [])

  const handleOpenMemory = useCallback(() => {
    if (selectedAgentId) {
      setMemoryAgentId(selectedAgentId)
      setSelectedAgentId(null) // Close detail panel
    }
  }, [selectedAgentId])

  const handleOpenPerception = useCallback(() => {
    if (selectedAgentId) {
      setPerceptionAgentId(selectedAgentId)
      setSelectedAgentId(null) // Close detail panel
    }
  }, [selectedAgentId])

  if (agents.length === 0) {
    return <EmptyStrip />
  }

  return (
    <>
      {/* Strip container — fixed height, horizontal scroll on mobile */}
      <div
        className={cn(
          'shrink-0 border-b border-border bg-bg-primary',
          'px-3 py-2 md:px-4',
        )}
      >
        <div
          className={cn(
            'flex gap-2 overflow-x-auto scrollbar-none',
            // Snap scrolling for touch
            'snap-x snap-mandatory',
            // On larger screens, allow wrapping if space permits
            'md:flex-wrap md:overflow-x-visible md:snap-none',
          )}
        >
          {agents.map((agent) => (
            <div key={agent.id} className="snap-start">
              <AgentCard
                agent={agent}
                roomName={getRoomName(agent.room_id)}
                isActive={isProcessing}
                actionText={isProcessing ? 'Thinking...' : null}
                isSelected={selectedAgentId === agent.id}
                onSelect={() => handleSelect(agent.id)}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Detail panel (bottom sheet on mobile, dialog on desktop) */}
      {selectedAgent && (
        <AgentDetail
          agent={selectedAgent}
          roomName={getRoomName(selectedAgent.room_id)}
          onClose={handleCloseDetail}
          onOpenMemory={handleOpenMemory}
          onOpenPerception={handleOpenPerception}
        />
      )}

      {/* Memory inspector panel (P2-002) */}
      {memoryAgent && (
        <AgentMemoryInspector
          agent={memoryAgent}
          onClose={() => setMemoryAgentId(null)}
        />
      )}

      {/* Perception overlay panel (P2-003) */}
      {perceptionAgent && (
        <AgentPerceptionOverlay
          agent={perceptionAgent}
          onClose={() => setPerceptionAgentId(null)}
        />
      )}
    </>
  )
}
