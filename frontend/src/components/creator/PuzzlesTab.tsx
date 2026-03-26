/**
 * PuzzlesTab — Puzzle builder for the Scene Creator.
 *
 * List puzzles with name, type, room assignment, required items/clues.
 * Add/remove puzzles. Visual dependency chain. AI-assist button.
 * Mobile: each puzzle is an expandable card (not a table row).
 * Touch-friendly: 44px+ targets, swipe-to-delete on cards.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Plus, X, Trash2, ChevronDown, ChevronRight,
  Sparkles, Loader2, Link2, Wand2,
  Key, Hash, Lock, Footprints, Search, ToggleLeft,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { PuzzleItem, SceneCreatorState } from '@/pages/Creator'

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const PUZZLE_TYPES = [
  { value: 'key_lock', label: 'Key Lock', icon: Key },
  { value: 'combination_lock', label: 'Combination Lock', icon: Hash },
  { value: 'password_door', label: 'Password Door', icon: Lock },
  { value: 'pressure_plate', label: 'Pressure Plate', icon: Footprints },
  { value: 'examine_reveal', label: 'Examine & Reveal', icon: Search },
  { value: 'sequential_levers', label: 'Sequential Levers', icon: ToggleLeft },
] as const

const PUZZLE_TYPE_MAP = Object.fromEntries(
  PUZZLE_TYPES.map(t => [t.value, t])
)

let puzzleIdCounter = 0
function nextPuzzleId() {
  return `puzzle-${++puzzleIdCounter}-${Date.now()}`
}

/* ------------------------------------------------------------------ */
/*  Swipeable puzzle card (mobile) — swipe left to reveal delete       */
/* ------------------------------------------------------------------ */

function SwipeablePuzzleCard({
  children,
  onDelete,
}: {
  children: React.ReactNode
  onDelete: () => void
}) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [offsetX, setOffsetX] = useState(0)
  const [isSwiping, setIsSwiping] = useState(false)
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const revealed = useRef(false)

  const DELETE_WIDTH = 72

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    touchStart.current = { x: touch.clientX, y: touch.clientY }
    setIsSwiping(false)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchStart.current) return
    const touch = e.touches[0]
    const dx = touch.clientX - touchStart.current.x
    const dy = touch.clientY - touchStart.current.y

    if (!isSwiping && Math.abs(dy) > Math.abs(dx)) {
      touchStart.current = null
      return
    }

    if (Math.abs(dx) > 10) setIsSwiping(true)

    if (isSwiping) {
      const baseOffset = revealed.current ? -DELETE_WIDTH : 0
      const newOffset = Math.min(0, Math.max(-DELETE_WIDTH - 20, baseOffset + dx))
      setOffsetX(newOffset)
    }
  }

  const handleTouchEnd = () => {
    if (!touchStart.current && !isSwiping) return

    if (isSwiping) {
      if (offsetX < -DELETE_WIDTH / 2) {
        setOffsetX(-DELETE_WIDTH)
        revealed.current = true
      } else {
        setOffsetX(0)
        revealed.current = false
      }
    }

    touchStart.current = null
    setTimeout(() => setIsSwiping(false), 50)
  }

  // Close when tapping elsewhere
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
    <div ref={cardRef} className="relative overflow-hidden rounded-xl md:overflow-visible">
      {/* Delete action behind the card (mobile only) */}
      <div
        className="absolute inset-y-0 right-0 flex items-center justify-center bg-danger md:hidden"
        style={{ width: DELETE_WIDTH }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="flex flex-col items-center justify-center gap-1 text-white w-full h-full min-h-[44px] min-w-[44px] active:bg-red-700 transition-colors"
          aria-label="Delete puzzle"
        >
          <Trash2 className="size-5" />
          <span className="text-xs font-medium">Delete</span>
        </button>
      </div>

      {/* Sliding content */}
      <div
        className="relative bg-bg-secondary border border-border rounded-xl transition-transform duration-200 ease-out"
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isSwiping ? 'none' : 'transform 200ms ease-out',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {children}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Puzzle card component (expandable on mobile)                       */
/* ------------------------------------------------------------------ */

function PuzzleCard({
  puzzle,
  rooms,
  allPuzzles,
  onUpdate,
  onDelete,
}: {
  puzzle: PuzzleItem
  rooms: { id: string; name: string }[]
  allPuzzles: PuzzleItem[]
  onUpdate: (puzzle: PuzzleItem) => void
  onDelete: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [itemInput, setItemInput] = useState('')

  const typeInfo = PUZZLE_TYPE_MAP[puzzle.type]
  const TypeIcon = typeInfo?.icon ?? Key
  const assignedRoom = rooms.find(r => r.id === puzzle.roomId)

  const addItem = () => {
    const trimmed = itemInput.trim()
    if (trimmed && !puzzle.requiredItems.includes(trimmed)) {
      onUpdate({ ...puzzle, requiredItems: [...puzzle.requiredItems, trimmed] })
      setItemInput('')
    }
  }

  const removeItem = (item: string) => {
    onUpdate({ ...puzzle, requiredItems: puzzle.requiredItems.filter(i => i !== item) })
  }

  const toggleDependency = (depId: string) => {
    const has = puzzle.dependsOn.includes(depId)
    onUpdate({
      ...puzzle,
      dependsOn: has
        ? puzzle.dependsOn.filter(d => d !== depId)
        : [...puzzle.dependsOn, depId],
    })
  }

  return (
    <SwipeablePuzzleCard onDelete={() => onDelete(puzzle.id)}>
      <div className="p-4">
        {/* Header row: always visible */}
        <div className="flex items-center gap-3">
          {/* Type icon */}
          <div className="size-10 rounded-lg bg-gold/10 flex items-center justify-center shrink-0">
            <TypeIcon className="size-5 text-gold" />
          </div>

          {/* Name + type label */}
          <div className="flex-1 min-w-0">
            <input
              type="text"
              value={puzzle.name}
              onChange={e => onUpdate({ ...puzzle, name: e.target.value })}
              className="bg-transparent text-text-primary text-sm font-semibold w-full focus:outline-none focus:text-gold placeholder:text-text-muted"
              placeholder="Puzzle name..."
            />
            <div className="flex items-center gap-2 text-xs text-text-muted mt-0.5">
              <span>{typeInfo?.label ?? puzzle.type}</span>
              {assignedRoom && (
                <>
                  <span className="text-text-muted/40">|</span>
                  <span>{assignedRoom.name}</span>
                </>
              )}
            </div>
          </div>

          {/* Expand toggle + delete (desktop) */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => onDelete(puzzle.id)}
              className="hidden md:flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg text-text-muted hover:text-danger hover:bg-danger/10 transition-colors"
              aria-label="Delete puzzle"
            >
              <Trash2 className="size-4" />
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center justify-center size-10 min-h-[44px] min-w-[44px] rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
              aria-label={expanded ? 'Collapse' : 'Expand'}
            >
              {expanded ? (
                <ChevronDown className="size-5" />
              ) : (
                <ChevronRight className="size-5" />
              )}
            </button>
          </div>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-4 space-y-4 animate-card-in">
            {/* Puzzle type selector */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">Type</label>
              <select
                value={puzzle.type}
                onChange={e => onUpdate({ ...puzzle, type: e.target.value })}
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
              >
                {PUZZLE_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            {/* Room assignment */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">Room</label>
              <select
                value={puzzle.roomId}
                onChange={e => onUpdate({ ...puzzle, roomId: e.target.value })}
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
              >
                <option value="">Unassigned</option>
                {rooms.map(r => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>

            {/* Description */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">Description</label>
              <textarea
                value={puzzle.description}
                onChange={e => onUpdate({ ...puzzle, description: e.target.value })}
                rows={2}
                placeholder="Describe what this puzzle does and how it works..."
                className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 resize-y placeholder:text-text-muted/60"
              />
            </div>

            {/* Required items/clues (tag input) */}
            <div>
              <label className="block text-text-secondary text-xs font-medium mb-1.5">
                Required Items / Clues
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={itemInput}
                  onChange={e => setItemInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addItem() } }}
                  placeholder="Add item or clue..."
                  className="flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50"
                />
                <Button onClick={addItem} variant="outline" className="h-10 px-3">
                  <Plus className="size-4" />
                </Button>
              </div>
              {puzzle.requiredItems.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {puzzle.requiredItems.map(item => (
                    <span
                      key={item}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-gold/10 text-gold text-xs"
                    >
                      {item}
                      <button
                        onClick={() => removeItem(item)}
                        className="size-4 min-h-0 min-w-0 flex items-center justify-center rounded text-gold/60 hover:text-danger transition-colors"
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Dependencies */}
            {allPuzzles.length > 1 && (
              <div>
                <label className="block text-text-secondary text-xs font-medium mb-1.5">
                  Depends On (gates)
                </label>
                <div className="space-y-1.5">
                  {allPuzzles
                    .filter(p => p.id !== puzzle.id)
                    .map(dep => {
                      const isDependent = puzzle.dependsOn.includes(dep.id)
                      return (
                        <button
                          key={dep.id}
                          onClick={() => toggleDependency(dep.id)}
                          className={cn(
                            'flex items-center gap-2 w-full px-3 py-2 rounded-lg text-sm text-left transition-colors min-h-[44px]',
                            isDependent
                              ? 'bg-gold/10 border border-gold/30 text-gold'
                              : 'bg-bg-primary border border-border text-text-secondary hover:border-text-muted',
                          )}
                        >
                          <Link2 className={cn('size-4 shrink-0', isDependent ? 'text-gold' : 'text-text-muted')} />
                          <span className="truncate">{dep.name || 'Untitled'}</span>
                          {isDependent && (
                            <span className="ml-auto text-xs text-gold/60">linked</span>
                          )}
                        </button>
                      )
                    })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </SwipeablePuzzleCard>
  )
}

/* ------------------------------------------------------------------ */
/*  Dependency chain visualization                                     */
/* ------------------------------------------------------------------ */

function DependencyChain({ puzzles }: { puzzles: PuzzleItem[] }) {
  if (puzzles.length === 0) return null

  // Build adjacency: for each puzzle, show what it depends on
  const hasDeps = puzzles.some(p => p.dependsOn.length > 0)
  if (!hasDeps) return null

  // Simple indented list showing dependency tree
  const puzzleMap = Object.fromEntries(puzzles.map(p => [p.id, p]))

  // Find root puzzles (no dependencies)
  const roots = puzzles.filter(p => p.dependsOn.length === 0)
  const nonRoots = puzzles.filter(p => p.dependsOn.length > 0)

  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-4">
      <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2">
        <Link2 className="size-3.5" />
        Dependency Chain
      </h4>
      <div className="space-y-1">
        {roots.map(root => (
          <DependencyNode
            key={root.id}
            puzzle={root}
            allPuzzles={puzzles}
            puzzleMap={puzzleMap}
            depth={0}
          />
        ))}
        {/* Orphan puzzles with unresolved deps */}
        {nonRoots
          .filter(p => !roots.some(r => isReachableFrom(r.id, p.id, puzzles)))
          .map(p => (
            <DependencyNode
              key={p.id}
              puzzle={p}
              allPuzzles={puzzles}
              puzzleMap={puzzleMap}
              depth={0}
            />
          ))}
      </div>
    </div>
  )
}

function isReachableFrom(
  startId: string,
  targetId: string,
  puzzles: PuzzleItem[],
  visited = new Set<string>(),
): boolean {
  if (visited.has(startId)) return false
  visited.add(startId)
  const dependents = puzzles.filter(p => p.dependsOn.includes(startId))
  for (const dep of dependents) {
    if (dep.id === targetId) return true
    if (isReachableFrom(dep.id, targetId, puzzles, visited)) return true
  }
  return false
}

function DependencyNode({
  puzzle,
  allPuzzles,
  puzzleMap,
  depth,
}: {
  puzzle: PuzzleItem
  allPuzzles: PuzzleItem[]
  puzzleMap: Record<string, PuzzleItem>
  depth: number
}) {
  const typeInfo = PUZZLE_TYPE_MAP[puzzle.type]
  const TypeIcon = typeInfo?.icon ?? Key
  const dependents = allPuzzles.filter(p => p.dependsOn.includes(puzzle.id))

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5"
        style={{ paddingLeft: `${depth * 20}px` }}
      >
        {depth > 0 && (
          <span className="text-text-muted/40 text-xs">
            {'-->'}
          </span>
        )}
        <TypeIcon className="size-3.5 text-gold/60 shrink-0" />
        <span className="text-text-primary text-sm truncate">
          {puzzle.name || 'Untitled'}
        </span>
        <span className="text-text-muted text-[10px]">
          {typeInfo?.label}
        </span>
      </div>
      {dependents.map(dep => (
        <DependencyNode
          key={dep.id}
          puzzle={dep}
          allPuzzles={allPuzzles}
          puzzleMap={puzzleMap}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  AI Assist bottom sheet / panel                                     */
/* ------------------------------------------------------------------ */

function AIAssistPanel({
  onGenerate,
  onClose,
}: {
  onGenerate: (description: string) => void
  onClose: () => void
}) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const touchStartY = useRef<number | null>(null)
  const [dragY, setDragY] = useState(0)
  const [isDragging, setIsDragging] = useState(false)

  const handleSubmit = async () => {
    if (!input.trim() || loading) return
    setLoading(true)
    try {
      await onGenerate(input.trim())
    } finally {
      setLoading(false)
    }
  }

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return
    const dy = e.touches[0].clientY - touchStartY.current
    if (dy > 0) {
      setDragY(dy)
      setIsDragging(true)
    }
  }

  const handleTouchEnd = () => {
    if (dragY > 100) onClose()
    setDragY(0)
    setIsDragging(false)
    touchStartY.current = null
  }

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div
        className="absolute bottom-0 left-0 right-0 max-w-lg mx-auto bg-bg-secondary rounded-t-2xl border-t border-x border-border"
        style={{
          transform: `translateY(${dragY}px)`,
          transition: isDragging ? 'none' : 'transform 200ms ease-out',
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        <div className="px-4 pb-6 pt-2 space-y-4">
          <div className="flex items-center gap-2">
            <Wand2 className="size-5 text-gold" />
            <h3 className="text-text-primary font-semibold">AI Puzzle Assistant</h3>
          </div>

          <p className="text-text-muted text-xs">
            Describe what you want the puzzle to do in natural language.
            The AI will generate the mechanics, type, and required items.
          </p>

          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            rows={3}
            placeholder="e.g., A painting that reveals a hidden safe when the eyes are pressed in the right order..."
            className="w-full rounded-xl border border-border bg-bg-primary px-4 py-3 text-text-primary text-sm placeholder:text-text-muted/60 focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 resize-y"
          />

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={onClose}
              className="flex-1 h-12"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!input.trim() || loading}
              className="flex-1 h-12 bg-gold hover:bg-gold-bright text-bg-primary font-semibold gap-2"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              Generate
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main PuzzlesTab Component                                          */
/* ------------------------------------------------------------------ */

export function PuzzlesTab({
  sceneState,
  setSceneState,
}: {
  sceneState: SceneCreatorState
  setSceneState: React.Dispatch<React.SetStateAction<SceneCreatorState>>
}) {
  const [showAIAssist, setShowAIAssist] = useState(false)

  const rooms = sceneState.rooms.map(r => ({ id: r.id, name: r.name }))

  const addPuzzle = useCallback(() => {
    const newPuzzle: PuzzleItem = {
      id: nextPuzzleId(),
      name: `Puzzle ${sceneState.puzzles.length + 1}`,
      type: 'key_lock',
      roomId: '',
      requiredItems: [],
      dependsOn: [],
      description: '',
    }
    setSceneState(prev => ({
      ...prev,
      puzzles: [...prev.puzzles, newPuzzle],
    }))
  }, [sceneState.puzzles.length, setSceneState])

  const updatePuzzle = useCallback(
    (updated: PuzzleItem) => {
      setSceneState(prev => ({
        ...prev,
        puzzles: prev.puzzles.map(p => (p.id === updated.id ? updated : p)),
      }))
    },
    [setSceneState],
  )

  const deletePuzzle = useCallback(
    (id: string) => {
      setSceneState(prev => ({
        ...prev,
        puzzles: prev.puzzles
          .filter(p => p.id !== id)
          .map(p => ({
            ...p,
            dependsOn: p.dependsOn.filter(d => d !== id),
          })),
      }))
    },
    [setSceneState],
  )

  const handleAIGenerate = useCallback(
    async (description: string) => {
      // Mock AI generation since no backend endpoint exists yet.
      // In production, this would call POST /api/generate-puzzle or similar.
      // For now, create a puzzle from the natural language description.
      await new Promise(resolve => setTimeout(resolve, 1200))

      // Simple heuristic to pick a type based on keywords
      let type = 'key_lock'
      const lower = description.toLowerCase()
      if (lower.includes('combination') || lower.includes('code') || lower.includes('number')) {
        type = 'combination_lock'
      } else if (lower.includes('password') || lower.includes('word') || lower.includes('phrase')) {
        type = 'password_door'
      } else if (lower.includes('pressure') || lower.includes('weight') || lower.includes('step')) {
        type = 'pressure_plate'
      } else if (lower.includes('examine') || lower.includes('look') || lower.includes('inspect') || lower.includes('reveal')) {
        type = 'examine_reveal'
      } else if (lower.includes('lever') || lower.includes('sequence') || lower.includes('order') || lower.includes('switch')) {
        type = 'sequential_levers'
      }

      const newPuzzle: PuzzleItem = {
        id: nextPuzzleId(),
        name: description.length > 40 ? description.slice(0, 37) + '...' : description,
        type,
        roomId: rooms.length > 0 ? rooms[Math.floor(Math.random() * rooms.length)].id : '',
        requiredItems: [],
        dependsOn: [],
        description,
      }

      setSceneState(prev => ({
        ...prev,
        puzzles: [...prev.puzzles, newPuzzle],
      }))
      setShowAIAssist(false)
    },
    [rooms, setSceneState],
  )

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <Button onClick={addPuzzle} variant="outline" className="h-10 gap-2 text-sm">
          <Plus className="size-4" />
          Add Puzzle
        </Button>

        <Button
          onClick={() => setShowAIAssist(true)}
          className="h-10 gap-2 text-sm bg-gold hover:bg-gold-bright text-bg-primary"
        >
          <Wand2 className="size-4" />
          AI Assist
        </Button>

        <span className="ml-auto text-text-muted text-xs">
          {sceneState.puzzles.length} {sceneState.puzzles.length === 1 ? 'puzzle' : 'puzzles'}
        </span>
      </div>

      {/* Dependency chain visualization */}
      <DependencyChain puzzles={sceneState.puzzles} />

      {/* Puzzle list */}
      {sceneState.puzzles.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="size-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
            <Key className="size-7 text-text-muted" />
          </div>
          <h3 className="text-text-secondary font-semibold mb-1">No puzzles yet</h3>
          <p className="text-text-muted text-sm max-w-xs mb-4">
            Add puzzles manually or use AI Assist to generate puzzle mechanics
            from a natural language description.
          </p>
          <div className="flex gap-2">
            <Button onClick={addPuzzle} variant="outline" className="h-10 gap-2">
              <Plus className="size-4" />
              Add Manually
            </Button>
            <Button
              onClick={() => setShowAIAssist(true)}
              className="h-10 gap-2 bg-gold hover:bg-gold-bright text-bg-primary"
            >
              <Wand2 className="size-4" />
              AI Assist
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {sceneState.puzzles.map(puzzle => (
            <PuzzleCard
              key={puzzle.id}
              puzzle={puzzle}
              rooms={rooms}
              allPuzzles={sceneState.puzzles}
              onUpdate={updatePuzzle}
              onDelete={deletePuzzle}
            />
          ))}
        </div>
      )}

      {/* AI Assist panel */}
      {showAIAssist && (
        <AIAssistPanel
          onGenerate={handleAIGenerate}
          onClose={() => setShowAIAssist(false)}
        />
      )}
    </div>
  )
}
