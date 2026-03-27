/**
 * Monitor page — the main game viewing page.
 *
 * Connects to the WebSocket on mount and displays the narrative feed
 * as the primary panel. Layout is designed to accommodate future panels:
 * - Agent status strip (top, P0-007)
 * - Escape chain progress (P0-008)
 * - Simulation controls (bottom, P0-009)
 *
 * Mobile-first: single-column, full-width narrative feed.
 * Desktop: narrative feed centered with max-width, room for side panels later.
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
      {/* Monitor header — tick count + connection status */}
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

      {/* Agent status strip — horizontal scrollable agent cards */}
      <AgentStatusStrip />

      {/* Agent thought bubbles — appear after each tick (P2-001) */}
      <ThoughtBubbles />

      {/* Escape chain progress bar — compact bar + expandable checklist */}
      <EscapeChainProgress />

      {/* Puzzle progress dashboard — collapsible panel (P1-006) */}
      <PuzzleProgressDashboard />

      {/* Interactive room map — collapsible panel (desktop) / FAB overlay (mobile) (P1-007) */}
      <InteractiveMap />

      {/* Main content area — narrative feed */}
      <div className="flex-1 min-h-0 relative">
        {/* On desktop, center the feed with a max-width for readability */}
        <div className="h-full w-full max-w-3xl mx-auto">
          <NarrativeFeed />
        </div>
      </div>

      {/* Agent conversation log — collapsible chat panel (P2-005) */}
      <ConversationLog />

      {/* Spectator nudge system — collapsible panel (P2-004) */}
      <NudgeSystem />

      {/* Timeline scrubber — film-strip with event markers (P3-001) */}
      <TimelineScrubber />

      {/* Simulation controls — sticky bottom bar (P0-009) */}
      <SimulationControls />
    </div>
  )
}
