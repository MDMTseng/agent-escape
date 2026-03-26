/**
 * NarrativeFeed — the main narrative feed panel for the game monitor.
 *
 * Features:
 * - Renders NarrativeEntry items from the Zustand store as styled cards
 * - Auto-scroll: follows the latest card by default
 * - Manual scroll: when user scrolls up, auto-scroll is disabled
 * - "Jump to latest" floating button to re-enable auto-scroll
 * - Filter chips to filter by event type (puzzle, movement, dialogue, discovery)
 * - Empty state when no events have arrived yet
 *
 * Mobile-first:
 * - Full-width cards on mobile
 * - Horizontally scrollable filter chips
 * - "Jump to latest" button in the thumb zone (bottom-right)
 * - Readable 16px+ prose text
 */

import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import { ArrowDown, Loader2, BookOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNarrativeEvents, useIsProcessing, useProcessingMessage } from '@/stores/gameStore'
import { NarrativeCard, categorizeEvent, EVENT_CATEGORY_CONFIG } from './NarrativeCard'
import type { EventCategory } from './NarrativeCard'

// ---------------------------------------------------------------------------
// Filter categories available to the user
// ---------------------------------------------------------------------------

const FILTER_OPTIONS: EventCategory[] = ['puzzle', 'movement', 'dialogue', 'discovery']

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function NarrativeFeed() {
  const narrativeEvents = useNarrativeEvents()
  const isProcessing = useIsProcessing()
  const processingMessage = useProcessingMessage()

  // Active filters — empty set means "show all"
  const [activeFilters, setActiveFilters] = useState<Set<EventCategory>>(new Set())
  // Auto-scroll state
  const [autoScroll, setAutoScroll] = useState(true)
  // Track the previous event count to know which cards are "new"
  const prevCountRef = useRef(0)

  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const bottomAnchorRef = useRef<HTMLDivElement>(null)

  // Filtered events based on active filters
  const filteredEvents = useMemo(() => {
    if (activeFilters.size === 0) return narrativeEvents
    return narrativeEvents.filter((entry) =>
      entry.events.some((evt) => activeFilters.has(categorizeEvent(evt)))
    )
  }, [narrativeEvents, activeFilters])

  // Toggle a filter category
  const toggleFilter = useCallback((category: EventCategory) => {
    setActiveFilters((prev) => {
      const next = new Set(prev)
      if (next.has(category)) {
        next.delete(category)
      } else {
        next.add(category)
      }
      return next
    })
  }, [])

  // Clear all filters
  const clearFilters = useCallback(() => {
    setActiveFilters(new Set())
  }, [])

  // -------------------------------------------------------------------------
  // Auto-scroll logic
  // -------------------------------------------------------------------------

  // Scroll to bottom when new events arrive (if auto-scroll is enabled)
  useEffect(() => {
    if (autoScroll && bottomAnchorRef.current) {
      bottomAnchorRef.current.scrollIntoView({ behavior: 'smooth' })
    }
    prevCountRef.current = narrativeEvents.length
  }, [narrativeEvents.length, autoScroll])

  // Detect manual scroll: if user scrolls away from bottom, disable auto-scroll.
  // If user scrolls back to bottom, re-enable.
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return

    const { scrollTop, scrollHeight, clientHeight } = container
    // Consider "at bottom" if within 100px of the bottom
    const atBottom = scrollHeight - scrollTop - clientHeight < 100
    setAutoScroll(atBottom)
  }, [])

  // Jump to latest button handler
  const jumpToLatest = useCallback(() => {
    setAutoScroll(true)
    if (bottomAnchorRef.current) {
      bottomAnchorRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  const hasEvents = filteredEvents.length > 0
  const hasAnyEvents = narrativeEvents.length > 0

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Filter chips — horizontally scrollable on mobile */}
      <div className="shrink-0 border-b border-border bg-bg-primary">
        <div className="flex items-center gap-2 px-3 py-2 overflow-x-auto scrollbar-none">
          {/* "All" chip */}
          <button
            onClick={clearFilters}
            className={cn(
              'shrink-0 inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium',
              'transition-colors whitespace-nowrap',
              'min-h-[36px]',
              activeFilters.size === 0
                ? 'bg-gold/20 text-gold border border-gold/30'
                : 'bg-bg-tertiary text-text-secondary border border-transparent hover:text-text-primary',
            )}
          >
            All
          </button>

          {FILTER_OPTIONS.map((cat) => {
            const config = EVENT_CATEGORY_CONFIG[cat]
            const isActive = activeFilters.has(cat)
            return (
              <button
                key={cat}
                onClick={() => toggleFilter(cat)}
                className={cn(
                  'shrink-0 inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium',
                  'transition-colors whitespace-nowrap',
                  'min-h-[36px]',
                  isActive
                    ? cn(config.bgColor, config.color, 'border', 'border-current/30')
                    : 'bg-bg-tertiary text-text-secondary border border-transparent hover:text-text-primary',
                )}
              >
                {config.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Scrollable feed area */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0 relative"
      >
        {/* Empty state */}
        {!hasAnyEvents && (
          <div className="flex flex-col items-center justify-center h-full px-6 py-12 text-center">
            <BookOpen size={48} className="text-text-muted mb-4" strokeWidth={1.5} />
            <h3 className="text-text-secondary font-medium mb-2">
              Waiting for the story to unfold...
            </h3>
            <p className="text-text-muted text-sm max-w-xs">
              Start or resume a simulation to see the narrative appear here, tick by tick.
            </p>
          </div>
        )}

        {/* Filtered empty state (events exist but none match filter) */}
        {hasAnyEvents && !hasEvents && (
          <div className="flex flex-col items-center justify-center h-full px-6 py-12 text-center">
            <p className="text-text-secondary font-medium mb-2">
              No events match the selected filters.
            </p>
            <button
              onClick={clearFilters}
              className="text-gold text-sm hover:text-gold-bright transition-colors min-h-[44px] px-4"
            >
              Clear filters
            </button>
          </div>
        )}

        {/* Card list */}
        {hasEvents && (
          <div className="flex flex-col gap-3 p-3 md:p-4">
            {filteredEvents.map((entry, idx) => (
              <NarrativeCard
                key={`${entry.tick}-${entry.timestamp}`}
                entry={entry}
                // Animate only newly appended cards (cards added after the component last rendered)
                animate={idx >= prevCountRef.current - 1 && idx === filteredEvents.length - 1}
              />
            ))}

            {/* Processing indicator — shown when agents are thinking */}
            {isProcessing && (
              <div className="flex items-center gap-2 px-4 py-3 rounded-lg border border-border bg-bg-secondary/50">
                <Loader2 size={16} className="text-gold animate-spin" />
                <span className="text-sm text-text-secondary">
                  {processingMessage || 'Agents are thinking...'}
                </span>
              </div>
            )}

            {/* Scroll anchor */}
            <div ref={bottomAnchorRef} className="h-px" />
          </div>
        )}
      </div>

      {/* "Jump to latest" FAB — shown when auto-scroll is off and there are events */}
      {!autoScroll && hasEvents && (
        <button
          onClick={jumpToLatest}
          className={cn(
            'absolute bottom-4 right-4 z-10',
            'flex items-center gap-2 px-4 py-2.5 rounded-full',
            'bg-gold text-bg-primary font-medium text-sm',
            'shadow-lg shadow-black/30',
            'hover:bg-gold-bright active:scale-95',
            'transition-all duration-150',
            'min-h-[44px]',
          )}
          aria-label="Jump to latest event"
        >
          <ArrowDown size={16} />
          <span>Latest</span>
        </button>
      )}
    </div>
  )
}
