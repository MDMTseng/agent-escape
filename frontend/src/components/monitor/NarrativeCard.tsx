/**
 * NarrativeCard — a single card in the narrative feed.
 *
 * Displays the narrator's prose for one tick, with:
 * - Tick number badge (gold accent)
 * - Event type indicators (colored dots/labels)
 * - Narrative prose text
 * - Relative timestamp
 *
 * Uses a fade-in + slide-up entrance animation on mount.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { NarrativeEntry, TickEvent } from '@/types/game'

// ---------------------------------------------------------------------------
// Event type config — colors and labels for filtering/display
// ---------------------------------------------------------------------------

export type EventCategory = 'puzzle' | 'movement' | 'dialogue' | 'discovery' | 'other'

/** Map raw backend event types to display categories. */
export function categorizeEvent(event: TickEvent): EventCategory {
  const t = event.type.toLowerCase()
  if (t === 'use' || t === 'state_change') return 'puzzle'
  if (t === 'move') return 'movement'
  if (t === 'talk') return 'dialogue'
  if (t === 'examine') return 'discovery'
  return 'other'
}

/** Visual config for each event category. */
export const EVENT_CATEGORY_CONFIG: Record<EventCategory, { label: string; color: string; bgColor: string }> = {
  puzzle: { label: 'Puzzle', color: 'text-amber-400', bgColor: 'bg-amber-400/15' },
  movement: { label: 'Movement', color: 'text-blue-400', bgColor: 'bg-blue-400/15' },
  dialogue: { label: 'Dialogue', color: 'text-emerald-400', bgColor: 'bg-emerald-400/15' },
  discovery: { label: 'Discovery', color: 'text-purple-400', bgColor: 'bg-purple-400/15' },
  other: { label: 'Event', color: 'text-text-secondary', bgColor: 'bg-bg-tertiary' },
}

// ---------------------------------------------------------------------------
// Relative time helper
// ---------------------------------------------------------------------------

function relativeTime(timestamp: number): string {
  const diff = Date.now() - timestamp
  if (diff < 5_000) return 'just now'
  if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  return `${Math.floor(diff / 3_600_000)}h ago`
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface NarrativeCardProps {
  entry: NarrativeEntry
  /** Whether this card should animate in (typically only for newly appended cards). */
  animate?: boolean
}

export function NarrativeCard({ entry, animate = false }: NarrativeCardProps) {
  // Deduplicate event categories present in this tick
  const categories = useMemo(() => {
    const seen = new Set<EventCategory>()
    for (const evt of entry.events) {
      seen.add(categorizeEvent(evt))
    }
    return Array.from(seen)
  }, [entry.events])

  return (
    <article
      data-tick={entry.tick}
      className={cn(
        // Card base — mobile first
        'relative rounded-lg border border-border bg-bg-secondary',
        'px-4 py-3',
        // Transition for timeline scrubber highlight
        'transition-[ring,ring-color] duration-300',
        // Entrance animation
        animate && 'animate-card-in',
      )}
    >
      {/* Top row: tick badge + event categories + timestamp */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        {/* Tick badge */}
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-gold/15 text-gold tabular-nums">
          Tick {entry.tick}
        </span>

        {/* Event category pills */}
        {categories.map((cat) => {
          const config = EVENT_CATEGORY_CONFIG[cat]
          return (
            <span
              key={cat}
              className={cn(
                'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
                config.bgColor,
                config.color,
              )}
            >
              {config.label}
            </span>
          )
        })}

        {/* Timestamp — pushed to the right */}
        <span className="ml-auto text-xs text-text-muted tabular-nums shrink-0">
          {relativeTime(entry.timestamp)}
        </span>
      </div>

      {/* Narrative prose */}
      <p className="text-text-primary leading-relaxed text-base whitespace-pre-line m-0">
        {entry.text}
      </p>

      {/* Event details — collapsed summary of raw events */}
      {entry.events.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border">
          <ul className="flex flex-col gap-1 text-sm text-text-secondary list-none m-0 p-0">
            {entry.events.map((evt, i) => {
              const cat = categorizeEvent(evt)
              const config = EVENT_CATEGORY_CONFIG[cat]
              return (
                <li key={i} className="flex items-start gap-2">
                  <span className={cn('inline-block w-1.5 h-1.5 rounded-full mt-1.5 shrink-0', config.color.replace('text-', 'bg-'))} />
                  <span>{evt.description}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </article>
  )
}
