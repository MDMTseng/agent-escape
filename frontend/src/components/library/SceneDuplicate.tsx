/**
 * SceneDuplicate — duplicate button for scene cards in the Library.
 *
 * Creates a copy of a scene by calling the create API with the same
 * parameters. Shows a brief "cloning" animation.
 *
 * Mobile-first: 44px+ touch target, compact icon button.
 */

import { useState, useCallback } from 'react'
import { Copy, Loader2, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SceneDuplicateProps {
  storyId: number
  storyTitle: string
  theme: string
  premise: string
  difficulty: number
  onDuplicated: () => void
}

export function SceneDuplicate({
  storyId,
  storyTitle,
  theme,
  premise,
  difficulty,
  onDuplicated,
}: SceneDuplicateProps) {
  const [phase, setPhase] = useState<'idle' | 'cloning' | 'done'>('idle')

  const handleDuplicate = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation()
      if (phase !== 'idle') return

      setPhase('cloning')

      try {
        const res = await fetch('/api/stories/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            theme,
            premise: `[Copy] ${premise}`,
            difficulty,
            num_characters: 3,
          }),
        })

        if (res.ok) {
          setPhase('done')
          setTimeout(() => {
            onDuplicated()
            setPhase('idle')
          }, 1000)
        } else {
          setPhase('idle')
        }
      } catch {
        setPhase('idle')
      }
    },
    [phase, theme, premise, difficulty, onDuplicated],
  )

  return (
    <button
      onClick={handleDuplicate}
      disabled={phase !== 'idle'}
      title={`Duplicate "${storyTitle}"`}
      aria-label={`Duplicate ${storyTitle}`}
      className={cn(
        'flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg',
        'transition-all duration-200 active:scale-95',
        phase === 'done'
          ? 'text-success bg-success/10'
          : phase === 'cloning'
          ? 'text-gold bg-gold/10'
          : 'text-text-muted hover:text-gold hover:bg-gold/10',
        phase !== 'idle' && 'cursor-not-allowed',
      )}
    >
      {phase === 'cloning' ? (
        <Loader2 className="size-4 animate-spin" />
      ) : phase === 'done' ? (
        <Check className="size-4" />
      ) : (
        <Copy className="size-4" />
      )}
    </button>
  )
}
