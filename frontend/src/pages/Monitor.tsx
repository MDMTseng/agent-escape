/**
 * Monitor page -- the main game viewing page.
 *
 * MOBILE (<640px): Tabbed interface via MobileMonitorTabs.
 *   Only one panel visible at a time (Story / Agents / Progress / Tools).
 *   The narrative feed gets the full content area height.
 *   Simulation controls are always visible at the bottom.
 *
 * TABLET/DESKTOP (>=640px): All panels stacked vertically as before.
 *   Narrative feed is the flex-1 primary content.
 *   Side panels and strips are all visible.
 */

import { useWebSocket } from '@/hooks/useWebSocket'
import { useConnectionStatus, useTick, useIsFinished, useFinishReason } from '@/stores/gameStore'
import { NarrativeFeed } from '@/components/monitor/NarrativeFeed'
import { AgentStatusStrip } from '@/components/monitor/AgentStatusStrip'
import { EscapeChainProgress } from '@/components/monitor/EscapeChainProgress'
import { SimulationControls } from '@/components/monitor/SimulationControls'
import { PuzzleProgressDashboard } from '@/components/monitor/PuzzleProgressDashboard'
import { InteractiveMap } from '@/components/monitor/InteractiveMap'
import { ThoughtBubbles } from '@/components/monitor/ThoughtBubble'
import { NudgeSystem } from '@/components/monitor/NudgeSystem'
import { ConversationLog } from '@/components/monitor/ConversationLog'
import { TimelineScrubber } from '@/components/monitor/TimelineScrubber'
import { MobileMonitorTabs } from '@/components/monitor/MobileMonitorTabs'
import { Wifi, WifiOff, Loader2, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Connection status indicator (inline, for the monitor header)
// ---------------------------------------------------------------------------

function ConnectionBadge() {
  const status = useConnectionStatus()

  const config = {
    connected: { icon: Wifi, label: 'Live', color: 'text-success', bg: 'bg-success/15' },
    connecting: { icon: Loader2, label: 'Connecting', color: 'text-gold', bg: 'bg-gold/15' },
    disconnected: { icon: WifiOff, label: 'Offline', color: 'text-text-muted', bg: 'bg-bg-tertiary' },
    error: { icon: AlertTriangle, label: 'Error', color: 'text-danger', bg: 'bg-danger/15' },
  }[status]

  const Icon = config.icon

  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium', config.bg, config.color)}>
      <Icon size={12} className={status === 'connecting' ? 'animate-spin' : ''} />
      {config.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Monitor page
// ---------------------------------------------------------------------------

export default function Monitor() {
  // Connect WebSocket on mount (auto-reconnect is built in)
  useWebSocket()

  const tick = useTick()
  const isFinished = useIsFinished()
  const finishReason = useFinishReason()

  return (
    <div className="flex flex-col h-full">
      {/* Monitor header -- compact on mobile, slightly more spacious on desktop */}
      <header className="shrink-0 flex items-center justify-between px-3 py-2 md:px-4 border-b border-border bg-bg-primary">
        <div className="flex items-center gap-3">
          <h1 className="text-gold font-bold tracking-tight text-lg m-0">
            Monitor
          </h1>
          {tick > 0 && (
            <span className="text-text-muted text-sm tabular-nums">
              Tick {tick}
            </span>
          )}
          {isFinished && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-danger/15 text-danger">
              Finished{finishReason ? `: ${finishReason}` : ''}
            </span>
          )}
        </div>
        <ConnectionBadge />
      </header>

      {/* ================================================================= */}
      {/* MOBILE LAYOUT (<640px): Tabbed interface                          */}
      {/* Only one panel visible at a time. Narrative feed gets full height. */}
      {/* ================================================================= */}
      <div className="flex flex-col flex-1 min-h-0 sm:hidden">
        <MobileMonitorTabs />
      </div>

      {/* ================================================================= */}
      {/* DESKTOP/TABLET LAYOUT (>=640px): All panels stacked               */}
      {/* This is the existing layout, unchanged.                           */}
      {/* ================================================================= */}
      <div className="hidden sm:flex sm:flex-col sm:flex-1 sm:min-h-0">
        {/* Agent status strip -- horizontal scrollable agent cards */}
        <AgentStatusStrip />

        {/* Agent thought bubbles */}
        <ThoughtBubbles />

        {/* Escape chain progress bar */}
        <EscapeChainProgress />

        {/* Puzzle progress dashboard */}
        <PuzzleProgressDashboard />

        {/* Main content area -- narrative feed */}
        <div className="flex-1 min-h-0 relative">
          <div className="h-full w-full max-w-3xl mx-auto">
            <NarrativeFeed />
          </div>
        </div>

        {/* Agent conversation log */}
        <ConversationLog />

        {/* Spectator nudge system */}
        <NudgeSystem />

        {/* Timeline scrubber */}
        <TimelineScrubber />

        {/* Interactive map -- desktop collapsible panel + FAB (hidden on mobile, Map is a tab there) */}
        <InteractiveMap />
      </div>

      {/* Simulation controls -- always visible at bottom, all viewports */}
      <SimulationControls />
    </div>
  )
}
