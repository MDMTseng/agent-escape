import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, Trash2, BookOpen, Clock, Save, Star,
  AlertCircle, RefreshCw, Loader2, Play, Sparkles, Zap
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { timeAgo } from '@/lib/timeago'
import { useGameStore } from '@/stores/gameStore'
import { SceneDuplicate } from '@/components/library/SceneDuplicate'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Story {
  id: number
  title: string
  theme: string
  premise: string
  difficulty: number
  created_at: string
  last_played_at: string | null
  save_count: number
  max_tick: number | null
}

/* ------------------------------------------------------------------ */
/*  Theme badge color mapping                                          */
/* ------------------------------------------------------------------ */

const THEME_COLORS: Record<string, { bg: string; text: string }> = {
  gothic_manor:   { bg: 'bg-purple-900/40', text: 'text-purple-300' },
  haunted_house:  { bg: 'bg-violet-900/40', text: 'text-violet-300' },
  space_station:  { bg: 'bg-blue-900/40',   text: 'text-blue-300' },
  pirate_ship:    { bg: 'bg-amber-900/40',  text: 'text-amber-300' },
  ancient_temple: { bg: 'bg-yellow-900/40', text: 'text-yellow-300' },
  cyber_noir:     { bg: 'bg-cyan-900/40',   text: 'text-cyan-300' },
  fairy_tale:     { bg: 'bg-pink-900/40',   text: 'text-pink-300' },
  underwater:     { bg: 'bg-teal-900/40',   text: 'text-teal-300' },
}

function getThemeColor(theme: string) {
  return THEME_COLORS[theme] ?? { bg: 'bg-bg-tertiary', text: 'text-text-secondary' }
}

function formatTheme(theme: string) {
  return theme.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

/* ------------------------------------------------------------------ */
/*  Quick Play — random theme/premise combinations                      */
/* ------------------------------------------------------------------ */

const QUICK_PLAY_OPTIONS = [
  {
    theme: 'gothic_manor',
    premise: 'Lord Ashworth discovered his formula was being stolen and locked down the estate before vanishing.',
  },
  {
    theme: 'gothic_manor',
    premise: 'A mysterious letter summoned everyone to the manor. Now the doors are sealed and the clock is ticking.',
  },
  {
    theme: 'sci_fi_lab',
    premise: 'An unauthorized experiment breached containment. The station locked down automatically.',
  },
  {
    theme: 'sci_fi_lab',
    premise: 'The AI detected an intruder and sealed all bulkheads. But there is no intruder on the sensors.',
  },
  {
    theme: 'ancient_tomb',
    premise: 'The expedition accidentally triggered an ancient mechanism. The entrance sealed behind them.',
  },
  {
    theme: 'ancient_tomb',
    premise: 'The tomb guardians have awakened. The trials must be completed before the sands fill the chamber.',
  },
]

function pickRandomOption() {
  return QUICK_PLAY_OPTIONS[Math.floor(Math.random() * QUICK_PLAY_OPTIONS.length)]
}

/* ------------------------------------------------------------------ */
/*  API helpers for play actions                                        */
/* ------------------------------------------------------------------ */

async function createStory(theme: string, premise: string) {
  const res = await fetch('/api/stories/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme, premise, difficulty: 3, num_characters: 3 }),
  })
  if (!res.ok) throw new Error(`Server error (${res.status})`)
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data
}

async function playStory(storyId: number) {
  const res = await fetch(`/api/stories/${storyId}/play`, { method: 'POST' })
  if (!res.ok) throw new Error(`Server error (${res.status})`)
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data
}

/* ------------------------------------------------------------------ */
/*  Difficulty stars                                                    */
/* ------------------------------------------------------------------ */

function DifficultyStars({ level }: { level: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`Difficulty ${level} of 5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          className={`size-3.5 ${i < level ? 'text-gold fill-gold' : 'text-text-muted'}`}
        />
      ))}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/*  Swipeable card wrapper — reveals delete action on swipe-left       */
/* ------------------------------------------------------------------ */

function SwipeableCard({
  children,
  onDelete,
  onTap,
}: {
  children: React.ReactNode
  onDelete: () => void
  onTap: () => void
}) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [offsetX, setOffsetX] = useState(0)
  const [isSwiping, setIsSwiping] = useState(false)
  const touchStart = useRef<{ x: number; y: number; time: number } | null>(null)
  const revealed = useRef(false)

  // The width of the delete action area
  const DELETE_WIDTH = 80

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY, time: Date.now() }
    setIsSwiping(false)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return
    const touch = e.touches[0]
    const dx = touch.clientX - touchStart.current.x
    const dy = touch.clientY - touchStart.current.y

    // If vertical movement is greater, don't intercept (let scroll happen)
    if (!isSwiping && Math.abs(dy) > Math.abs(dx)) {
      touchStart.current = null
      return
    }

    if (Math.abs(dx) > 10) {
      setIsSwiping(true)
    }

    if (isSwiping) {
      // If already revealed, allow swiping back to right
      const baseOffset = revealed.current ? -DELETE_WIDTH : 0
      const newOffset = Math.min(0, Math.max(-DELETE_WIDTH - 20, baseOffset + dx))
      setOffsetX(newOffset)
    }
  }

  const handleTouchEnd = () => {
    if (!touchStart.current) return

    if (isSwiping) {
      // Snap to revealed or closed
      if (offsetX < -DELETE_WIDTH / 2) {
        setOffsetX(-DELETE_WIDTH)
        revealed.current = true
      } else {
        setOffsetX(0)
        revealed.current = false
      }
    }

    touchStart.current = null
    // Don't reset isSwiping immediately - let click handler check it
    setTimeout(() => setIsSwiping(false), 50)
  }

  const handleClick = () => {
    if (isSwiping) return
    if (revealed.current) {
      // Tap to close revealed delete
      setOffsetX(0)
      revealed.current = false
      return
    }
    onTap()
  }

  // Close swipe when clicking elsewhere (mouse users)
  useEffect(() => {
    const handleDocClick = (e: MouseEvent) => {
      if (revealed.current && cardRef.current && !cardRef.current.contains(e.target as Node)) {
        setOffsetX(0)
        revealed.current = false
      }
    }
    document.addEventListener('click', handleDocClick)
    return () => document.removeEventListener('click', handleDocClick)
  }, [])

  return (
    <div ref={cardRef} className="relative overflow-hidden rounded-xl">
      {/* Delete action behind the card */}
      <div
        className="absolute inset-y-0 right-0 flex items-center justify-center bg-danger"
        style={{ width: DELETE_WIDTH }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="flex flex-col items-center justify-center gap-1 text-white w-full h-full min-h-[44px] min-w-[44px] active:bg-red-700 transition-colors"
          aria-label="Delete scene"
        >
          <Trash2 className="size-5" />
          <span className="text-xs font-medium">Delete</span>
        </button>
      </div>

      {/* Sliding card content */}
      <div
        className="relative bg-bg-secondary border border-border rounded-xl transition-transform duration-200 ease-out cursor-pointer hover:border-gold/30 active:scale-[0.98]"
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isSwiping ? 'none' : 'transform 200ms ease-out',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter') onTap() }}
      >
        {children}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Story card content                                                 */
/* ------------------------------------------------------------------ */

function StoryCard({
  story,
  onDelete,
  onPlay,
  onDuplicate,
  playingId,
}: {
  story: Story
  onDelete: (id: number) => void
  onPlay: (story: Story) => void
  onDuplicate: () => void
  playingId: number | null
}) {
  const isLoading = playingId === story.id

  return (
    <SwipeableCard
      onTap={() => onPlay(story)}
      onDelete={() => onDelete(story.id)}
    >
      <div className="p-4 space-y-3">
        {/* Header: title + action buttons */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-text-primary font-semibold leading-tight line-clamp-2 text-base flex-1">
            {story.title}
          </h3>
          <div className="flex items-center gap-1 shrink-0">
            {/* Play button — always visible, prominent */}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onPlay(story)
              }}
              disabled={isLoading}
              aria-label={`Play ${story.title}`}
              className="flex items-center justify-center size-10 min-h-[44px] min-w-[44px] rounded-lg bg-gold/15 text-gold hover:bg-gold/25 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Play className="size-4 ml-0.5" fill="currentColor" />
              )}
            </button>
            {/* Desktop-only duplicate button (hover reveal) */}
            <div className="hidden md:block opacity-0 group-hover/card:opacity-100 transition-all">
              <SceneDuplicate
                storyId={story.id}
                storyTitle={story.title}
                theme={story.theme}
                premise={story.premise}
                difficulty={story.difficulty}
                onDuplicated={onDuplicate}
              />
            </div>
            {/* Desktop-only delete button (hover reveal) */}
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete(story.id)
              }}
              className="hidden md:flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg text-text-muted hover:text-danger hover:bg-danger/10 opacity-0 group-hover/card:opacity-100 transition-all"
              aria-label={`Delete ${story.title}`}
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>

        {/* Theme badge + difficulty */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getThemeColor(story.theme).bg} ${getThemeColor(story.theme).text}`}>
            {formatTheme(story.theme)}
          </span>
          <DifficultyStars level={story.difficulty} />
        </div>

        {/* Premise (truncated) */}
        {story.premise && (
          <p className="text-text-secondary text-sm leading-relaxed line-clamp-2">
            {story.premise}
          </p>
        )}

        {/* Meta row */}
        <div className="flex items-center gap-3 text-xs text-text-muted pt-1">
          <span className="inline-flex items-center gap-1">
            <Clock className="size-3" />
            {timeAgo(story.created_at)}
          </span>
          <span className="inline-flex items-center gap-1">
            <Save className="size-3" />
            {story.save_count} {story.save_count === 1 ? 'save' : 'saves'}
          </span>
          {story.max_tick != null && (
            <span className="inline-flex items-center gap-1">
              Tick {story.max_tick}
            </span>
          )}
        </div>
      </div>
    </SwipeableCard>
  )
}

/* ------------------------------------------------------------------ */
/*  Skeleton card for loading state                                    */
/* ------------------------------------------------------------------ */

function SkeletonCard() {
  return (
    <div className="bg-bg-secondary border border-border rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-5 w-3/4 bg-bg-tertiary rounded" />
      <div className="flex gap-2">
        <div className="h-5 w-20 bg-bg-tertiary rounded-full" />
        <div className="h-5 w-16 bg-bg-tertiary rounded" />
      </div>
      <div className="h-4 w-full bg-bg-tertiary rounded" />
      <div className="h-4 w-2/3 bg-bg-tertiary rounded" />
      <div className="flex gap-3">
        <div className="h-3 w-16 bg-bg-tertiary rounded" />
        <div className="h-3 w-16 bg-bg-tertiary rounded" />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Empty state                                                        */
/* ------------------------------------------------------------------ */

function EmptyState({ onNewScene }: { onNewScene: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-16 min-h-[50dvh]">
      {/* Atmospheric icon */}
      <div className="relative mb-6">
        <div className="size-24 rounded-full bg-gold/5 flex items-center justify-center">
          <BookOpen className="size-10 text-gold/40" />
        </div>
        {/* Subtle glow */}
        <div className="absolute inset-0 size-24 rounded-full bg-gold/5 blur-xl" />
      </div>

      <h2 className="text-text-primary font-semibold mb-2">No scenes yet</h2>
      <p className="text-text-secondary text-sm max-w-xs mb-8 leading-relaxed">
        Create your first escape room scene. AI agents will explore, solve puzzles,
        and unravel the mystery.
      </p>
      <Button
        onClick={onNewScene}
        className="h-12 px-6 text-base gap-2"
      >
        <Plus className="size-5" />
        Create Your First Scene
      </Button>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Error state                                                        */
/* ------------------------------------------------------------------ */

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center text-center px-6 py-16 min-h-[40dvh]">
      <div className="size-16 rounded-full bg-danger/10 flex items-center justify-center mb-4">
        <AlertCircle className="size-8 text-danger" />
      </div>
      <h2 className="text-text-primary font-semibold mb-2">Failed to load scenes</h2>
      <p className="text-text-secondary text-sm max-w-xs mb-6">{message}</p>
      <Button variant="outline" onClick={onRetry} className="gap-2 h-11">
        <RefreshCw className="size-4" />
        Retry
      </Button>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Delete confirmation bottom sheet                                   */
/* ------------------------------------------------------------------ */

function DeleteConfirmSheet({
  storyTitle,
  onConfirm,
  onCancel,
}: {
  storyTitle: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const sheetRef = useRef<HTMLDivElement>(null)
  const touchStart = useRef<number | null>(null)
  const [dragY, setDragY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  // Swipe down to dismiss
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStart.current = e.touches[0].clientY
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStart.current === null) return
    const dy = e.touches[0].clientY - touchStart.current
    if (dy > 0) {
      setDragY(dy)
      setIsDragging(true)
    }
  }

  const handleTouchEnd = () => {
    if (dragY > 80) {
      onCancel()
    } else {
      setDragY(0)
    }
    setIsDragging(false)
    touchStart.current = null
  }

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-[100] flex items-end justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onCancel}
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        className="relative w-full max-w-lg bg-bg-secondary rounded-t-2xl border-t border-x border-border pb-safe-area safe-area-pb"
        style={{
          transform: `translateY(${dragY}px)`,
          transition: isDragging ? 'none' : 'transform 200ms ease-out',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-2">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        <div className="px-6 pb-6 pt-2 space-y-4">
          <div className="text-center">
            <div className="size-12 rounded-full bg-danger/10 flex items-center justify-center mx-auto mb-3">
              <Trash2 className="size-6 text-danger" />
            </div>
            <h3 className="text-text-primary font-semibold text-lg">Delete Scene?</h3>
            <p className="text-text-secondary text-sm mt-1 line-clamp-2">
              &ldquo;{storyTitle}&rdquo; and all its saves will be permanently deleted.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Button
              variant="destructive"
              onClick={onConfirm}
              className="h-12 w-full text-base font-semibold"
            >
              Delete Scene
            </Button>
            <Button
              variant="outline"
              onClick={onCancel}
              className="h-12 w-full text-base"
            >
              Cancel
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Generation loading overlay — atmospheric, not just a spinner        */
/* ------------------------------------------------------------------ */

const GENERATION_MESSAGES = [
  'Conjuring the mystery...',
  'Building rooms and corridors...',
  'Breathing life into agents...',
  'Hiding clues in the shadows...',
  'Weaving the escape chain...',
  'Setting the stage...',
]

function GenerationOverlay({
  theme,
  onCancel,
}: {
  theme: string
  onCancel?: () => void
}) {
  const [msgIndex, setMsgIndex] = useState(0)

  // Cycle through atmospheric messages
  useEffect(() => {
    const interval = setInterval(() => {
      setMsgIndex(i => (i + 1) % GENERATION_MESSAGES.length)
    }, 2500)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="flex flex-col items-center text-center px-6 max-w-sm">
        {/* Animated glow ring */}
        <div className="relative mb-6">
          <div className="size-20 rounded-full bg-gold/10 flex items-center justify-center animate-pulse">
            <Sparkles className="size-8 text-gold" />
          </div>
          {/* Orbiting ring effect */}
          <div className="absolute inset-[-8px] rounded-full border-2 border-gold/20 animate-spin" style={{ animationDuration: '3s' }} />
          <div className="absolute inset-[-16px] rounded-full border border-gold/10 animate-spin" style={{ animationDuration: '5s', animationDirection: 'reverse' }} />
        </div>

        <h3 className="text-text-primary font-semibold text-lg mb-1">
          Creating Your Escape Room
        </h3>
        <p className="text-gold text-sm font-medium mb-1">
          {formatTheme(theme)}
        </p>

        {/* Rotating message */}
        <p className="text-text-secondary text-sm h-5 transition-opacity duration-300">
          {GENERATION_MESSAGES[msgIndex]}
        </p>

        {/* Subtle progress bar (indeterminate) */}
        <div className="w-48 h-1 bg-bg-tertiary rounded-full mt-6 overflow-hidden">
          <div
            className="h-full bg-gold/60 rounded-full"
            style={{
              animation: 'indeterminate 1.5s ease-in-out infinite',
              width: '40%',
            }}
          />
        </div>

        {onCancel && (
          <button
            onClick={onCancel}
            className="mt-6 text-text-muted text-xs hover:text-text-secondary transition-colors min-h-[44px] px-4"
          >
            Cancel
          </button>
        )}
      </div>

      {/* CSS for indeterminate progress animation */}
      <style>{`
        @keyframes indeterminate {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Library page                                                  */
/* ------------------------------------------------------------------ */

export default function Library() {
  const navigate = useNavigate()
  const [stories, setStories] = useState<Story[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Story | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Quick Play / Play state
  const [generating, setGenerating] = useState(false)
  const [generatingTheme, setGeneratingTheme] = useState('gothic_manor')
  const [playingStoryId, setPlayingStoryId] = useState<number | null>(null)

  const setStoryContext = useGameStore((s) => s.setStoryContext)
  const resetGameStore = useGameStore((s) => s.reset)

  const fetchStories = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/stories')
      if (!res.ok) throw new Error(`Server error (${res.status})`)
      const data = await res.json()
      setStories(data.stories ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStories()
  }, [fetchStories])

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const res = await fetch(`/api/stories/${deleteTarget.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      // Remove from local state with exit effect
      setStories(prev => prev.filter(s => s.id !== deleteTarget.id))
      setDeleteTarget(null)
    } catch {
      // Keep the sheet open, let user retry
      setError('Failed to delete scene. Please try again.')
      setDeleteTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  // --- Quick Play: create a new story with random theme + premise ---
  const handleQuickPlay = useCallback(async () => {
    if (generating) return
    const option = pickRandomOption()
    setGenerating(true)
    setGeneratingTheme(option.theme)
    setError(null)

    try {
      // Reset store before creating so we start fresh
      resetGameStore()

      const data = await createStory(option.theme, option.premise)

      // Set story context in Zustand so the Monitor page knows what is loaded
      setStoryContext(data.story_id, {
        title: data.title,
        theme: data.world_bible?.theme ?? option.theme,
        premise: option.premise,
        difficulty: data.world_bible?.difficulty ?? 3,
      })

      // Navigate to monitor — the WebSocket will receive the snapshot
      navigate('/monitor')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create story')
    } finally {
      setGenerating(false)
    }
  }, [generating, navigate, resetGameStore, setStoryContext])

  // --- Play an existing story from its card ---
  const handlePlayStory = useCallback(async (story: Story) => {
    if (playingStoryId !== null) return
    setPlayingStoryId(story.id)
    setError(null)

    try {
      resetGameStore()

      const data = await playStory(story.id)

      setStoryContext(data.story_id ?? story.id, {
        title: data.title ?? story.title,
        theme: story.theme,
        premise: story.premise,
        difficulty: story.difficulty,
      })

      navigate('/monitor')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load story')
    } finally {
      setPlayingStoryId(null)
    }
  }, [playingStoryId, navigate, resetGameStore, setStoryContext])

  const handleNewScene = () => {
    navigate('/creator')
  }

  return (
    <div className="flex flex-col min-h-full">
      {/* Header — fixed position context for the page */}
      <div className="px-4 pt-4 pb-3 md:px-6 md:pt-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-gold font-bold tracking-tight">Scene Library</h1>
            <p className="text-text-secondary text-sm mt-0.5">
              {!loading && !error && stories.length > 0
                ? `${stories.length} ${stories.length === 1 ? 'scene' : 'scenes'}`
                : 'Your escape room scenes'}
            </p>
          </div>

          {/* Desktop header buttons */}
          <div className="hidden md:flex items-center gap-2">
            <Button
              onClick={handleQuickPlay}
              disabled={generating}
              className="h-10 gap-2 bg-gold hover:bg-gold-bright text-bg-primary font-semibold"
            >
              <Zap className="size-4" />
              Quick Play
            </Button>
            {!loading && !error && stories.length > 0 && (
              <Button
                onClick={handleNewScene}
                variant="outline"
                className="h-10 gap-2"
              >
                <Plus className="size-4" />
                New Scene
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Quick Play banner — mobile only, prominent call-to-action in thumb zone */}
      <div className="px-4 pb-3 md:hidden">
        <button
          onClick={handleQuickPlay}
          disabled={generating}
          className="w-full flex items-center justify-center gap-2.5 h-14 min-h-[56px] rounded-xl bg-gradient-to-r from-gold/20 to-gold/10 border border-gold/30 text-gold font-semibold text-base active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Zap className="size-5" />
          Quick Play
          <span className="text-gold/60 text-sm font-normal">- random escape room</span>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 px-4 pb-24 md:px-6 md:pb-6">
        {loading ? (
          /* Loading skeleton grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }, (_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : error ? (
          <ErrorState message={error} onRetry={fetchStories} />
        ) : stories.length === 0 ? (
          <EmptyState onNewScene={handleNewScene} />
        ) : (
          /* Story cards grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {stories.map(story => (
              <div key={story.id} className="group/card">
                <StoryCard
                  story={story}
                  onDelete={(id) => {
                    const s = stories.find(s => s.id === id)
                    if (s) setDeleteTarget(s)
                  }}
                  onPlay={handlePlayStory}
                  onDuplicate={fetchStories}
                  playingId={playingStoryId}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Mobile FAB — "New Scene" button in thumb zone (bottom-right) */}
      {!loading && !error && (
        <button
          onClick={handleNewScene}
          className="fixed bottom-20 right-4 md:hidden z-50 size-14 rounded-full bg-gold text-bg-primary shadow-lg shadow-gold/20 flex items-center justify-center active:scale-95 transition-transform"
          aria-label="New Scene"
        >
          <Plus className="size-6" strokeWidth={2.5} />
        </button>
      )}

      {/* Delete confirmation bottom sheet */}
      {deleteTarget && (
        <DeleteConfirmSheet
          storyTitle={deleteTarget.title}
          onConfirm={handleDelete}
          onCancel={() => !deleting && setDeleteTarget(null)}
        />
      )}

      {/* Deleting overlay indicator */}
      {deleting && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/40">
          <div className="bg-bg-secondary rounded-xl p-6 flex items-center gap-3">
            <Loader2 className="size-5 text-gold animate-spin" />
            <span className="text-text-primary text-sm">Deleting...</span>
          </div>
        </div>
      )}

      {/* Story generation overlay — atmospheric loading screen */}
      {generating && (
        <GenerationOverlay theme={generatingTheme} />
      )}
    </div>
  )
}
