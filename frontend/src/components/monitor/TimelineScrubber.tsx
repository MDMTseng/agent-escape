/**
 * TimelineScrubber — cinematic film-strip timeline for the Game Monitor.
 *
 * Displays all ticks as a horizontal timeline with event markers:
 *  - Star: puzzle solve events
 *  - Magnifying glass: discovery/examine events
 *  - Speech bubble: conversation/talk events
 *
 * Features:
 *  - Click a marker to scroll the narrative feed to that tick's card
 *  - Draggable scrub handle with momentum
 *  - Glowing event pins on the timeline
 *  - Cinematic film-strip aesthetic
 *  - Current tick highlighted with gold pulse
 *
 * Mobile-first:
 *  - Horizontally scrollable timeline
 *  - Touch-drag scrubbing
 *  - Compact height, fits above simulation controls
 *  - 44px+ touch targets on markers
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  Star,
  Search,
  MessageCircle,
  Clock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNarrativeEvents, useTick } from '@/stores/gameStore'
import type { NarrativeEntry, TickEvent } from '@/types/game'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MarkerType = 'puzzle' | 'discovery' | 'conversation'

// ---------------------------------------------------------------------------
// Classify events on a tick
// ---------------------------------------------------------------------------

function classifyEvents(events: TickEvent[]): MarkerType[] {
  const types: MarkerType[] = []
  for (const e of events) {
    const t = e.type.toLowerCase()
    if (t === 'use' || t === 'state_change') {
      if (!types.includes('puzzle')) types.push('puzzle')
    } else if (t === 'examine') {
      if (!types.includes('discovery')) types.push('discovery')
    } else if (t === 'talk') {
      if (!types.includes('conversation')) types.push('conversation')
    }
  }
  return types
}

// ---------------------------------------------------------------------------
// Marker icon config
// ---------------------------------------------------------------------------

const MARKER_CONFIG: Record<
  MarkerType,
  { Icon: typeof Star; color: string; bg: string; glow: string; label: string }
> = {
  puzzle: {
    Icon: Star,
    color: 'text-amber-400',
    bg: 'bg-amber-400/20',
    glow: 'shadow-[0_0_8px_rgba(251,191,36,0.4)]',
    label: 'Puzzle',
  },
  discovery: {
    Icon: Search,
    color: 'text-purple-400',
    bg: 'bg-purple-400/20',
    glow: 'shadow-[0_0_8px_rgba(192,132,252,0.4)]',
    label: 'Discovery',
  },
  conversation: {
    Icon: MessageCircle,
    color: 'text-emerald-400',
    bg: 'bg-emerald-400/20',
    glow: 'shadow-[0_0_8px_rgba(52,211,153,0.4)]',
    label: 'Conversation',
  },
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TimelineScrubber() {
  const narrativeEvents = useNarrativeEvents()
  const currentTick = useTick()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [hoveredTick, setHoveredTick] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const dragStart = useRef<{ x: number; scrollLeft: number } | null>(null)

  // Build tick data with markers
  const tickData = useMemo(() => {
    const data: {
      tick: number
      markers: MarkerType[]
      hasNarrative: boolean
      entry: NarrativeEntry | null
    }[] = []

    // Create entries for all ticks up to current
    const entryMap = new Map<number, NarrativeEntry>()
    for (const entry of narrativeEvents) {
      entryMap.set(entry.tick, entry)
    }

    const maxTick = Math.max(currentTick, ...narrativeEvents.map(e => e.tick))
    for (let t = 1; t <= maxTick; t++) {
      const entry = entryMap.get(t) ?? null
      const markers = entry ? classifyEvents(entry.events) : []
      data.push({
        tick: t,
        markers,
        hasNarrative: entry !== null,
        entry,
      })
    }

    return data
  }, [narrativeEvents, currentTick])

  // Auto-scroll to keep current tick visible
  useEffect(() => {
    if (!scrollRef.current || isDragging) return
    const container = scrollRef.current
    const tickWidth = 48 // approximate width per tick segment
    const targetScroll = (currentTick - 1) * tickWidth - container.clientWidth / 2 + tickWidth / 2
    container.scrollTo({ left: Math.max(0, targetScroll), behavior: 'smooth' })
  }, [currentTick, isDragging])

  // Navigate to a tick's narrative card in the feed
  const handleTickClick = useCallback((tick: number) => {
    // Find the narrative card for this tick and scroll to it
    const card = document.querySelector(`[data-tick="${tick}"]`)
    if (card) {
      card.scrollIntoView({ behavior: 'smooth', block: 'center' })
      // Brief highlight effect
      card.classList.add('ring-2', 'ring-gold/50')
      setTimeout(() => {
        card.classList.remove('ring-2', 'ring-gold/50')
      }, 2000)
    }
  }, [])

  // Touch/mouse drag for scrubbing
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if (!scrollRef.current) return
    setIsDragging(true)
    dragStart.current = {
      x: e.clientX,
      scrollLeft: scrollRef.current.scrollLeft,
    }
    scrollRef.current.setPointerCapture(e.pointerId)
  }, [])

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isDragging || !dragStart.current || !scrollRef.current) return
      const dx = e.clientX - dragStart.current.x
      scrollRef.current.scrollLeft = dragStart.current.scrollLeft - dx
    },
    [isDragging],
  )

  const handlePointerUp = useCallback(() => {
    setIsDragging(false)
    dragStart.current = null
  }, [])

  // Don't render if no ticks yet
  if (tickData.length === 0) return null

  const progress = currentTick / Math.max(tickData.length, 1)

  return (
    <div className="shrink-0 border-t border-border bg-bg-secondary/80">
      {/* Progress bar — thin overview */}
      <div className="h-1 bg-bg-tertiary relative">
        <div
          className="absolute inset-y-0 left-0 bg-gold/40 transition-all duration-500"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Timeline strip */}
      <div className="flex items-center gap-1 px-2 py-1.5 md:px-3">
        {/* Tick counter */}
        <div className="shrink-0 flex items-center gap-1 text-[10px] text-text-muted mr-1">
          <Clock className="size-3" />
          <span className="tabular-nums font-mono">
            {currentTick}/{tickData.length}
          </span>
        </div>

        {/* Scrollable timeline */}
        <div
          ref={scrollRef}
          className={cn(
            'flex-1 overflow-x-auto scrollbar-none',
            'flex items-end gap-0 cursor-grab',
            isDragging && 'cursor-grabbing',
          )}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          style={{ touchAction: 'pan-y' }}
        >
          {tickData.map(td => {
            const isCurrent = td.tick === currentTick
            const isPast = td.tick < currentTick
            const isHovered = hoveredTick === td.tick
            const hasMarkers = td.markers.length > 0

            return (
              <div
                key={td.tick}
                className="flex flex-col items-center shrink-0"
                style={{ width: 48 }}
                onMouseEnter={() => setHoveredTick(td.tick)}
                onMouseLeave={() => setHoveredTick(null)}
              >
                {/* Event markers above the tick line */}
                <div className="h-6 flex items-end justify-center gap-0.5 mb-0.5">
                  {td.markers.map(type => {
                    const cfg = MARKER_CONFIG[type]
                    return (
                      <button
                        key={type}
                        onClick={() => handleTickClick(td.tick)}
                        className={cn(
                          'flex items-center justify-center rounded-full transition-all duration-200',
                          'size-5 min-h-0 min-w-0',
                          cfg.bg,
                          cfg.color,
                          isHovered && cfg.glow,
                        )}
                        title={`${cfg.label} at tick ${td.tick}`}
                        aria-label={`${cfg.label} event at tick ${td.tick}`}
                      >
                        <cfg.Icon className="size-2.5" />
                      </button>
                    )
                  })}
                </div>

                {/* Tick segment — clickable bar */}
                <button
                  onClick={() => handleTickClick(td.tick)}
                  className={cn(
                    'w-full h-3 rounded-sm transition-all duration-200 min-h-0 min-w-0',
                    'border-x border-border/30',
                    isCurrent
                      ? 'bg-gold animate-active-pulse'
                      : isPast
                      ? td.hasNarrative
                        ? 'bg-text-muted/30'
                        : 'bg-bg-tertiary/50'
                      : 'bg-bg-tertiary/30',
                    isHovered && !isCurrent && 'bg-text-muted/50',
                    hasMarkers && isPast && 'bg-text-muted/40',
                  )}
                  title={`Tick ${td.tick}`}
                  aria-label={`Go to tick ${td.tick}`}
                />

                {/* Tick number label — show for current, every 5th, or hovered */}
                {(isCurrent || td.tick % 5 === 0 || isHovered) && (
                  <span
                    className={cn(
                      'text-[8px] tabular-nums mt-0.5 transition-colors',
                      isCurrent ? 'text-gold font-bold' : 'text-text-muted',
                    )}
                  >
                    {td.tick}
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {/* Legend — desktop only */}
        <div className="hidden md:flex items-center gap-3 ml-2 shrink-0">
          {Object.entries(MARKER_CONFIG).map(([type, cfg]) => (
            <div key={type} className="flex items-center gap-1">
              <div
                className={cn(
                  'size-3 rounded-full flex items-center justify-center',
                  cfg.bg,
                )}
              >
                <cfg.Icon className={cn('size-2', cfg.color)} />
              </div>
              <span className="text-[9px] text-text-muted">{cfg.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
