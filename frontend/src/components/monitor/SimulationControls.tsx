/**
 * SimulationControls -- sticky bottom bar with play/pause/step/quit controls.
 *
 * Mobile-first: 60px sticky bar in the thumb zone, sits above the bottom nav.
 * Desktop: same bar, slightly more spacious, always visible at bottom.
 *
 * API calls:
 *   POST /api/resume  -> start playing
 *   POST /api/pause   -> pause
 *   POST /api/step    -> advance one tick (only when paused)
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Play,
  Pause,
  SkipForward,
  LogOut,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useIsPlaying,
  useTick,
  useIsProcessing,
  useIsFinished,
  useGameStore,
} from '@/stores/gameStore'

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiPost(path: string): Promise<boolean> {
  try {
    const res = await fetch(path, { method: 'POST' })
    return res.ok
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// SimulationControls
// ---------------------------------------------------------------------------

export function SimulationControls() {
  const isPlaying = useIsPlaying()
  const tick = useTick()
  const isProcessing = useIsProcessing()
  const isFinished = useIsFinished()
  const navigate = useNavigate()

  // Local loading states to disable buttons during API calls
  const [playPauseLoading, setPlayPauseLoading] = useState(false)
  const [stepLoading, setStepLoading] = useState(false)
  const [quitLoading, setQuitLoading] = useState(false)

  // --- Play / Pause toggle ---
  const handlePlayPause = useCallback(async () => {
    if (playPauseLoading || isFinished) return
    setPlayPauseLoading(true)
    const endpoint = isPlaying ? '/api/pause' : '/api/resume'
    const ok = await apiPost(endpoint)
    // Optimistically update isPlaying so the UI reflects the new state
    // immediately, rather than waiting for a snapshot WS message.
    if (ok) {
      useGameStore.getState().setIsPlaying(!isPlaying)
    }
    setPlayPauseLoading(false)
  }, [isPlaying, playPauseLoading, isFinished])

  // --- Step (one tick) ---
  const handleStep = useCallback(async () => {
    if (stepLoading || isPlaying || isFinished) return
    setStepLoading(true)
    await apiPost('/api/step')
    setStepLoading(false)
  }, [stepLoading, isPlaying, isFinished])

  // --- Quit to library ---
  const handleQuit = useCallback(async () => {
    if (quitLoading) return
    setQuitLoading(true)
    // Pause first if running, then navigate
    if (isPlaying) {
      const paused = await apiPost('/api/pause')
      if (paused) {
        useGameStore.getState().setIsPlaying(false)
      }
    }
    useGameStore.getState().reset()
    navigate('/library')
  }, [quitLoading, isPlaying, navigate])

  return (
    <div
      className={cn(
        // Mobile-first: sticky bottom bar above the mobile nav (h-14 = 56px nav + pb)
        'shrink-0 z-40',
        'flex items-center gap-2 px-3 py-2',
        'bg-bg-secondary border-t border-border',
        // Mobile: 60px height, compact layout
        'h-[60px]',
        // Desktop: slightly more spacious
        'md:h-16 md:px-6 md:gap-4',
      )}
      role="toolbar"
      aria-label="Simulation controls"
    >
      {/* --- Play / Pause button --- */}
      <button
        onClick={handlePlayPause}
        disabled={playPauseLoading || isFinished}
        aria-label={isPlaying ? 'Pause simulation' : 'Play simulation'}
        className={cn(
          // Base: large touch target, rounded, transition
          'flex items-center justify-center',
          'w-12 h-12 min-w-[48px] min-h-[48px] rounded-full',
          'transition-all duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold',
          // Color: gold when playing, muted when paused
          isPlaying && !isFinished
            ? 'bg-gold text-bg-primary hover:bg-gold-bright active:scale-95'
            : 'bg-bg-tertiary text-text-primary hover:bg-border active:scale-95',
          // Disabled state
          (playPauseLoading || isFinished) && 'opacity-50 cursor-not-allowed active:scale-100',
        )}
      >
        {playPauseLoading ? (
          <Loader2 size={22} className="animate-spin" />
        ) : isPlaying ? (
          <Pause size={22} fill="currentColor" />
        ) : (
          <Play size={22} fill="currentColor" className="ml-0.5" />
        )}
      </button>

      {/* --- Step button --- */}
      <button
        onClick={handleStep}
        disabled={isPlaying || stepLoading || isFinished}
        aria-label="Step one tick"
        title="Advance one tick"
        className={cn(
          'flex items-center justify-center',
          'w-11 h-11 min-w-[44px] min-h-[44px] rounded-lg',
          'transition-all duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold',
          // Enabled: subtle background
          !isPlaying && !isFinished
            ? 'bg-bg-tertiary text-text-primary hover:bg-border active:scale-95'
            : 'bg-bg-tertiary/50 text-text-muted cursor-not-allowed',
          stepLoading && 'opacity-50',
        )}
      >
        {stepLoading ? (
          <Loader2 size={18} className="animate-spin" />
        ) : (
          <SkipForward size={18} />
        )}
      </button>

      {/* --- Tick counter + processing indicator --- */}
      <div className="flex-1 flex items-center gap-2 min-w-0">
        {/* Tick number */}
        <span
          className={cn(
            'text-gold font-mono font-bold tabular-nums',
            'text-base md:text-lg',
          )}
        >
          {tick}
        </span>
        <span className="text-text-muted text-xs hidden xs:inline">
          tick{tick !== 1 ? 's' : ''}
        </span>

        {/* Processing indicator */}
        {isProcessing && (
          <span className="flex items-center gap-1.5 text-gold-dim text-xs">
            <Loader2 size={12} className="animate-spin" />
            <span className="hidden sm:inline truncate max-w-[120px] md:max-w-[200px]">
              Thinking...
            </span>
          </span>
        )}

        {/* Finished badge */}
        {isFinished && (
          <span className="text-xs font-medium text-danger bg-danger/15 px-2 py-0.5 rounded">
            Ended
          </span>
        )}
      </div>

      {/* --- Quit to Library button --- */}
      <button
        onClick={handleQuit}
        disabled={quitLoading}
        aria-label="Quit to library"
        title="Pause and return to library"
        className={cn(
          'flex items-center justify-center gap-1.5',
          'h-11 min-h-[44px] px-3 rounded-lg',
          'transition-all duration-150',
          'text-text-secondary text-xs font-medium',
          'hover:bg-bg-tertiary hover:text-text-primary active:scale-95',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold',
          quitLoading && 'opacity-50 cursor-not-allowed',
        )}
      >
        {quitLoading ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <LogOut size={16} />
        )}
        <span className="hidden sm:inline">Quit</span>
      </button>
    </div>
  )
}
