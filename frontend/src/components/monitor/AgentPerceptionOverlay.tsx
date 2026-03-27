/**
 * AgentPerceptionOverlay — stub for P2-003.
 * Will be fully implemented as a separate feature.
 */

import type { AgentState } from '@/types/game'

interface AgentPerceptionOverlayProps {
  agent: AgentState
  onClose: () => void
}

export function AgentPerceptionOverlay({ agent, onClose }: AgentPerceptionOverlayProps) {
  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/60"
        onClick={onClose}
        aria-hidden
      />
      <div className="fixed z-50 inset-x-0 bottom-0 max-h-[90vh] rounded-t-2xl border-t border-border bg-bg-secondary p-6 md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-[420px] md:rounded-xl md:border">
        <p className="text-text-muted text-sm">Perception overlay for {agent.name} — coming soon.</p>
        <button onClick={onClose} className="mt-4 px-4 py-2 rounded-lg bg-bg-tertiary text-text-primary text-sm">
          Close
        </button>
      </div>
    </>
  )
}
