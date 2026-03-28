/**
 * MobileMonitorTabs -- tabbed interface for the Monitor page on mobile (<640px).
 *
 * Layout (top to bottom, fixed heights):
 *   Agent Cards (compact)     ~70px - always visible, horizontal scroll
 *   Tab Bar                   ~44px - Story | Puzzles | Chat | Map | Nudge
 *   ACTIVE TAB CONTENT        flex-1 (all remaining space, scrolls internally)
 *
 * SimulationControls and BottomNav are rendered by the parent (Monitor.tsx)
 * below this component, so they are always visible.
 *
 * Tab definitions:
 *   1. Story (default) - Compact escape chain summary + narrative feed + filter chips
 *   2. Puzzles - Puzzle Progress Dashboard (full height)
 *   3. Chat - Conversation Log (full height)
 *   4. Map - Interactive Map (full height, replaces FAB overlay)
 *   5. Nudge - Spectator Nudge controls + Timeline scrubber
 *
 * Agent cards stay ABOVE the tabs, always visible.
 * Thought bubble toggles are removed from mobile (accessible via agent detail sheet).
 *
 * Gesture support:
 *   - Swipe left/right to switch tabs
 *   - Each tab scrolls independently
 *   - Agent cards have snap scrolling
 */

import { useState, useCallback, useRef } from 'react'
import {
  BookOpen,
  Trophy,
  MessageCircle,
  Map,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'

import { NarrativeFeed } from '@/components/monitor/NarrativeFeed'
import { AgentStatusStrip } from '@/components/monitor/AgentStatusStrip'
import { EscapeChainProgress } from '@/components/monitor/EscapeChainProgress'
import { PuzzleProgressDashboard } from '@/components/monitor/PuzzleProgressDashboard'
import { ConversationLog } from '@/components/monitor/ConversationLog'
import { NudgeSystem } from '@/components/monitor/NudgeSystem'
import { TimelineScrubber } from '@/components/monitor/TimelineScrubber'
import { InteractiveMapInline } from '@/components/monitor/InteractiveMap'
import { useSolvedStepCount, useEscapeChain } from '@/stores/gameStore'

// ---------------------------------------------------------------------------
// Tab definitions -- 5 tabs for mobile
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'story', label: 'Story', icon: BookOpen },
  { id: 'puzzles', label: 'Puzzles', icon: Trophy },
  { id: 'chat', label: 'Chat', icon: MessageCircle },
  { id: 'map', label: 'Map', icon: Map },
  { id: 'nudge', label: 'Nudge', icon: Zap },
] as const

type TabId = (typeof TABS)[number]['id']

// ---------------------------------------------------------------------------
// Compact escape chain summary -- single line, expandable on tap
// Shows "3/8 solved" with a mini progress bar
// ---------------------------------------------------------------------------

function CompactEscapeChain() {
  const solvedCount = useSolvedStepCount()
  const escapeChain = useEscapeChain()
  const totalSteps = escapeChain.length
  const [expanded, setExpanded] = useState(false)

  if (totalSteps === 0) return null

  if (expanded) {
    return (
      <div className="shrink-0 border-b border-border/50">
        <EscapeChainProgress />
        <button
          onClick={() => setExpanded(false)}
          className="w-full text-center py-1.5 text-xs text-text-muted active:bg-bg-tertiary/30"
        >
          Collapse
        </button>
      </div>
    )
  }

  const progressPercent = totalSteps > 0 ? (solvedCount / totalSteps) * 100 : 0

  return (
    <button
      onClick={() => setExpanded(true)}
      className={cn(
        'shrink-0 flex items-center gap-3 w-full px-3 py-2',
        'border-b border-border/50 bg-bg-secondary/50',
        'active:bg-bg-tertiary/30 transition-colors',
        'min-h-[40px]',
      )}
    >
      {/* Progress counter */}
      <span className="text-sm font-bold tabular-nums text-gold">
        {solvedCount}/{totalSteps}
      </span>
      <span className="text-xs text-text-muted">solved</span>

      {/* Mini progress bar */}
      <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full bg-success transition-all duration-500"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Tap hint */}
      <span className="text-[10px] text-text-muted">Details</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MobileMonitorTabs() {
  const [activeTab, setActiveTab] = useState<TabId>('story')

  // Swipe support for switching tabs
  const touchStartX = useRef<number | null>(null)
  const touchStartY = useRef<number | null>(null)

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (touchStartX.current === null || touchStartY.current === null) return

    const deltaX = e.changedTouches[0].clientX - touchStartX.current
    const deltaY = e.changedTouches[0].clientY - touchStartY.current

    // Only trigger tab switch on horizontal swipes (not vertical scrolling)
    // Require at least 60px horizontal and less than 40px vertical
    if (Math.abs(deltaX) > 60 && Math.abs(deltaY) < 40) {
      const tabIds = TABS.map((t) => t.id)
      const currentIndex = tabIds.indexOf(activeTab)

      if (deltaX < 0 && currentIndex < tabIds.length - 1) {
        // Swipe left -> next tab
        setActiveTab(tabIds[currentIndex + 1])
      } else if (deltaX > 0 && currentIndex > 0) {
        // Swipe right -> previous tab
        setActiveTab(tabIds[currentIndex - 1])
      }
    }

    touchStartX.current = null
    touchStartY.current = null
  }, [activeTab])

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Agent cards -- always visible above tabs, compact ~70px */}
      <div className="shrink-0">
        <AgentStatusStrip />
      </div>

      {/* Tab bar -- 44px height, icons + short labels, gold active indicator */}
      <div
        className="shrink-0 flex border-b border-border bg-bg-primary"
        role="tablist"
        aria-label="Monitor tabs"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex-1 flex flex-col items-center justify-center gap-0.5',
                'py-2 min-h-[44px] relative',
                'transition-colors duration-150',
                'text-[11px] font-medium',
                isActive
                  ? 'text-gold'
                  : 'text-text-muted active:text-text-secondary',
              )}
              aria-selected={isActive}
              role="tab"
              aria-controls={`tab-panel-${tab.id}`}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
              {/* Active indicator: gold underline */}
              {isActive && (
                <span
                  className="absolute bottom-0 left-2 right-2 h-0.5 bg-gold rounded-full"
                  aria-hidden="true"
                />
              )}
            </button>
          )
        })}
      </div>

      {/* Tab content -- fills all remaining space between tab bar and sim controls */}
      <div
        className="flex-1 min-h-0 relative"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {/* Story tab: compact escape chain + narrative feed (gets most space) */}
        {activeTab === 'story' && (
          <div
            id="tab-panel-story"
            role="tabpanel"
            className="h-full w-full flex flex-col"
          >
            <CompactEscapeChain />
            <div className="flex-1 min-h-0">
              <NarrativeFeed />
            </div>
          </div>
        )}

        {/* Puzzles tab: full-height puzzle progress dashboard */}
        {activeTab === 'puzzles' && (
          <div
            id="tab-panel-puzzles"
            role="tabpanel"
            className="h-full w-full overflow-y-auto overscroll-contain"
          >
            <EscapeChainProgress />
            <PuzzleProgressDashboard />
          </div>
        )}

        {/* Chat tab: full-height conversation log */}
        {activeTab === 'chat' && (
          <div
            id="tab-panel-chat"
            role="tabpanel"
            className="h-full w-full overflow-y-auto overscroll-contain"
          >
            <ConversationLog />
          </div>
        )}

        {/* Map tab: interactive map (replaces FAB overlay) */}
        {activeTab === 'map' && (
          <div
            id="tab-panel-map"
            role="tabpanel"
            className="h-full w-full"
          >
            <InteractiveMapInline />
          </div>
        )}

        {/* Nudge tab: spectator nudge + timeline scrubber */}
        {activeTab === 'nudge' && (
          <div
            id="tab-panel-nudge"
            role="tabpanel"
            className="h-full w-full overflow-y-auto overscroll-contain"
          >
            <NudgeSystem />
            <TimelineScrubber />
          </div>
        )}
      </div>
    </div>
  )
}
