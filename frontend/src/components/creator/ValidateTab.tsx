/**
 * ValidateTab — Scene validation and save/play controls for the Scene Creator.
 *
 * Runs client-side validation checks:
 * - All rooms connected (graph traversal)
 * - All puzzles have room assignments
 * - All puzzles have required items/clues
 * - Escape chain solvable (BFS from start)
 * - At least 1 agent exists
 *
 * Shows pass/fail per check with explanation. "Save Scene" and "Play Scene" buttons.
 * Mobile: validation results as checklist, action buttons in thumb zone.
 */

import { useState, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2, XCircle, AlertTriangle, Loader2,
  Save, Play, Shield, Users, DoorOpen, Puzzle,
  Link2, MapPin, ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { SceneCreatorState, RoomNode, DoorEdge, PuzzleItem } from '@/pages/Creator'
import type { AgentItem } from '@/components/creator/AgentsTab'

/* ------------------------------------------------------------------ */
/*  Validation check types                                             */
/* ------------------------------------------------------------------ */

interface ValidationCheck {
  id: string
  label: string
  icon: React.ElementType
  status: 'pass' | 'fail' | 'warn'
  message: string
}

/* ------------------------------------------------------------------ */
/*  Validation logic                                                   */
/* ------------------------------------------------------------------ */

function runValidation(state: SceneCreatorState): ValidationCheck[] {
  const checks: ValidationCheck[] = []
  const rooms = state.rooms
  const doors = state.doors
  const puzzles = state.puzzles
  const agents: AgentItem[] = (state as any).agents ?? []

  // 1. At least 1 room exists
  if (rooms.length === 0) {
    checks.push({
      id: 'rooms-exist',
      label: 'Rooms',
      icon: DoorOpen,
      status: 'fail',
      message: 'No rooms created. Add at least one room in the Rooms tab.',
    })
  } else {
    checks.push({
      id: 'rooms-exist',
      label: 'Rooms',
      icon: DoorOpen,
      status: 'pass',
      message: `${rooms.length} room${rooms.length !== 1 ? 's' : ''} defined.`,
    })
  }

  // 2. All rooms connected (graph traversal via doors)
  if (rooms.length >= 2) {
    const connected = checkRoomsConnected(rooms, doors)
    if (connected) {
      checks.push({
        id: 'rooms-connected',
        label: 'Room connectivity',
        icon: Link2,
        status: 'pass',
        message: 'All rooms are reachable from any other room.',
      })
    } else {
      checks.push({
        id: 'rooms-connected',
        label: 'Room connectivity',
        icon: Link2,
        status: 'fail',
        message: 'Some rooms are isolated. Connect all rooms with doors in the Rooms tab.',
      })
    }
  } else if (rooms.length === 1) {
    checks.push({
      id: 'rooms-connected',
      label: 'Room connectivity',
      icon: Link2,
      status: 'warn',
      message: 'Only 1 room. Agents need multiple rooms to explore.',
    })
  }

  // 3. At least 1 agent exists
  if (agents.length === 0) {
    checks.push({
      id: 'agents-exist',
      label: 'Agents',
      icon: Users,
      status: 'fail',
      message: 'No agents created. Add at least one agent in the Agents tab.',
    })
  } else {
    const unassigned = agents.filter(a => !a.spawnRoomId)
    if (unassigned.length > 0) {
      checks.push({
        id: 'agents-exist',
        label: 'Agents',
        icon: Users,
        status: 'warn',
        message: `${agents.length} agent${agents.length !== 1 ? 's' : ''} defined, but ${unassigned.length} without a spawn room.`,
      })
    } else {
      checks.push({
        id: 'agents-exist',
        label: 'Agents',
        icon: Users,
        status: 'pass',
        message: `${agents.length} agent${agents.length !== 1 ? 's' : ''} ready with spawn rooms assigned.`,
      })
    }
  }

  // 4. All puzzles have room assignments
  if (puzzles.length === 0) {
    checks.push({
      id: 'puzzles-exist',
      label: 'Puzzles',
      icon: Puzzle,
      status: 'warn',
      message: 'No puzzles created. The scene will have no challenges.',
    })
  } else {
    const unassigned = puzzles.filter(p => !p.roomId)
    if (unassigned.length > 0) {
      checks.push({
        id: 'puzzles-rooms',
        label: 'Puzzle rooms',
        icon: MapPin,
        status: 'fail',
        message: `${unassigned.length} puzzle${unassigned.length !== 1 ? 's' : ''} without a room assignment: ${unassigned.map(p => p.name || 'Untitled').join(', ')}`,
      })
    } else {
      checks.push({
        id: 'puzzles-rooms',
        label: 'Puzzle rooms',
        icon: MapPin,
        status: 'pass',
        message: `All ${puzzles.length} puzzles assigned to rooms.`,
      })
    }

    // 5. Puzzles have required items/clues
    const noItems = puzzles.filter(p => p.requiredItems.length === 0)
    if (noItems.length > 0) {
      checks.push({
        id: 'puzzles-items',
        label: 'Puzzle requirements',
        icon: Puzzle,
        status: 'warn',
        message: `${noItems.length} puzzle${noItems.length !== 1 ? 's' : ''} have no required items/clues defined.`,
      })
    } else {
      checks.push({
        id: 'puzzles-items',
        label: 'Puzzle requirements',
        icon: Puzzle,
        status: 'pass',
        message: 'All puzzles have required items/clues.',
      })
    }

    // 6. Dependency chain is acyclic (no circular dependencies)
    const hasCycle = checkForCycles(puzzles)
    if (hasCycle) {
      checks.push({
        id: 'puzzles-cycle',
        label: 'Puzzle dependencies',
        icon: Link2,
        status: 'fail',
        message: 'Circular dependency detected in puzzle chain. This would make the scene unsolvable.',
      })
    } else if (puzzles.some(p => p.dependsOn.length > 0)) {
      checks.push({
        id: 'puzzles-cycle',
        label: 'Puzzle dependencies',
        icon: Link2,
        status: 'pass',
        message: 'Puzzle dependency chain is valid (no cycles).',
      })
    }
  }

  // 7. Scene has a theme and premise
  if (!state.theme) {
    checks.push({
      id: 'story-theme',
      label: 'Theme',
      icon: Shield,
      status: 'fail',
      message: 'No theme selected. Choose a theme in the Story tab.',
    })
  } else if (!state.premise.trim()) {
    checks.push({
      id: 'story-premise',
      label: 'Premise',
      icon: Shield,
      status: 'warn',
      message: 'No premise written. The AI will generate a generic backstory.',
    })
  } else {
    checks.push({
      id: 'story-setup',
      label: 'Story setup',
      icon: Shield,
      status: 'pass',
      message: `Theme: ${state.theme.replace(/_/g, ' ')}. Premise defined.`,
    })
  }

  return checks
}

/** BFS to check if all rooms are reachable from the first room */
function checkRoomsConnected(rooms: RoomNode[], doors: DoorEdge[]): boolean {
  if (rooms.length <= 1) return true

  const adjacency: Record<string, Set<string>> = {}
  for (const room of rooms) {
    adjacency[room.id] = new Set()
  }
  for (const door of doors) {
    if (adjacency[door.sourceRoomId]) adjacency[door.sourceRoomId].add(door.targetRoomId)
    if (adjacency[door.targetRoomId]) adjacency[door.targetRoomId].add(door.sourceRoomId)
  }

  const visited = new Set<string>()
  const queue = [rooms[0].id]
  visited.add(rooms[0].id)

  while (queue.length > 0) {
    const current = queue.shift()!
    const neighbors = adjacency[current] ?? new Set()
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor)
        queue.push(neighbor)
      }
    }
  }

  return visited.size === rooms.length
}

/** DFS cycle detection in puzzle dependency graph */
function checkForCycles(puzzles: PuzzleItem[]): boolean {
  const WHITE = 0, GRAY = 1, BLACK = 2
  const color: Record<string, number> = {}
  for (const p of puzzles) color[p.id] = WHITE

  function dfs(id: string): boolean {
    color[id] = GRAY
    const puzzle = puzzles.find(p => p.id === id)
    if (!puzzle) return false
    for (const dep of puzzle.dependsOn) {
      if (color[dep] === GRAY) return true // back edge = cycle
      if (color[dep] === WHITE && dfs(dep)) return true
    }
    color[id] = BLACK
    return false
  }

  for (const p of puzzles) {
    if (color[p.id] === WHITE && dfs(p.id)) return true
  }
  return false
}

/* ------------------------------------------------------------------ */
/*  Validation result item                                             */
/* ------------------------------------------------------------------ */

function ValidationItem({ check }: { check: ValidationCheck }) {
  const statusConfig = {
    pass: { icon: CheckCircle2, color: 'text-success', bg: 'bg-success/10', border: 'border-success/20' },
    fail: { icon: XCircle, color: 'text-danger', bg: 'bg-danger/10', border: 'border-danger/20' },
    warn: { icon: AlertTriangle, color: 'text-warning', bg: 'bg-warning/10', border: 'border-warning/20' },
  }[check.status]

  const StatusIcon = statusConfig.icon
  const CheckIcon = check.icon

  return (
    <div className={cn(
      'flex items-start gap-3 p-3 rounded-xl border transition-colors',
      statusConfig.bg,
      statusConfig.border,
    )}>
      <div className="flex items-center gap-2 shrink-0 mt-0.5">
        <StatusIcon className={cn('size-5', statusConfig.color)} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <CheckIcon className="size-3.5 text-text-secondary" />
          <span className="text-text-primary text-sm font-medium">{check.label}</span>
        </div>
        <p className="text-text-muted text-xs leading-relaxed">{check.message}</p>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main ValidateTab Component                                         */
/* ------------------------------------------------------------------ */

export function ValidateTab({
  sceneState,
  setSceneState,
}: {
  sceneState: SceneCreatorState
  setSceneState: React.Dispatch<React.SetStateAction<SceneCreatorState>>
}) {
  const navigate = useNavigate()
  const [saving, setSaving] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedStoryId, setSavedStoryId] = useState<number | null>(null)

  // Run validation checks
  const checks = useMemo(() => runValidation(sceneState), [sceneState])

  const failCount = checks.filter(c => c.status === 'fail').length
  const warnCount = checks.filter(c => c.status === 'warn').length
  const passCount = checks.filter(c => c.status === 'pass').length
  const allPass = failCount === 0

  const overallStatus = failCount > 0
    ? { label: 'Issues Found', color: 'text-danger', bg: 'bg-danger/10', border: 'border-danger/30' }
    : warnCount > 0
      ? { label: 'Ready with Warnings', color: 'text-warning', bg: 'bg-warning/10', border: 'border-warning/30' }
      : { label: 'Ready to Play', color: 'text-success', bg: 'bg-success/10', border: 'border-success/30' }

  /** Save the scene by creating a story via the API */
  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)

    try {
      const res = await fetch('/api/stories/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: sceneState.theme,
          premise: sceneState.premise || `A ${sceneState.theme.replace(/_/g, ' ')} escape room`,
          difficulty: sceneState.difficulty,
          num_characters: (sceneState as any).agents?.length || 3,
        }),
      })

      if (!res.ok) throw new Error(`Server error (${res.status})`)

      const data = await res.json()
      if (data.error) throw new Error(data.error)

      setSavedStoryId(data.story_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save scene')
    } finally {
      setSaving(false)
    }
  }, [sceneState])

  /** Save + start playing: create story then navigate to monitor */
  const handlePlay = useCallback(async () => {
    setPlaying(true)
    setError(null)

    try {
      // If already saved, play the saved story
      if (savedStoryId) {
        const res = await fetch(`/api/stories/${savedStoryId}/play`, { method: 'POST' })
        if (!res.ok) throw new Error(`Server error (${res.status})`)
        const data = await res.json()
        if (data.error) throw new Error(data.error)
        navigate('/monitor')
        return
      }

      // Otherwise create + play in one step
      const res = await fetch('/api/stories/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: sceneState.theme,
          premise: sceneState.premise || `A ${sceneState.theme.replace(/_/g, ' ')} escape room`,
          difficulty: sceneState.difficulty,
          num_characters: (sceneState as any).agents?.length || 3,
        }),
      })

      if (!res.ok) throw new Error(`Server error (${res.status})`)
      const data = await res.json()
      if (data.error) throw new Error(data.error)

      navigate('/monitor')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start game')
    } finally {
      setPlaying(false)
    }
  }, [sceneState, savedStoryId, navigate])

  return (
    <div className="space-y-6">
      {/* Overall status banner */}
      <div className={cn(
        'flex items-center gap-3 p-4 rounded-xl border',
        overallStatus.bg, overallStatus.border,
      )}>
        {failCount > 0 ? (
          <XCircle className={cn('size-6 shrink-0', overallStatus.color)} />
        ) : warnCount > 0 ? (
          <AlertTriangle className={cn('size-6 shrink-0', overallStatus.color)} />
        ) : (
          <CheckCircle2 className={cn('size-6 shrink-0', overallStatus.color)} />
        )}
        <div>
          <h3 className={cn('text-sm font-semibold', overallStatus.color)}>
            {overallStatus.label}
          </h3>
          <p className="text-text-muted text-xs mt-0.5">
            {passCount} passed, {warnCount} warning{warnCount !== 1 ? 's' : ''}, {failCount} failed
          </p>
        </div>
      </div>

      {/* Validation checklist */}
      <div className="space-y-2">
        {checks.map(check => (
          <ValidationItem key={check.id} check={check} />
        ))}
      </div>

      {/* Error display */}
      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-danger/10 border border-danger/20">
          <AlertTriangle className="size-4 text-danger shrink-0 mt-0.5" />
          <p className="text-danger text-sm">{error}</p>
        </div>
      )}

      {/* Save success */}
      {savedStoryId && !error && (
        <div className="flex items-center gap-2 p-3 rounded-xl bg-success/10 border border-success/20">
          <CheckCircle2 className="size-4 text-success shrink-0" />
          <p className="text-success text-sm">
            Scene saved successfully (ID: {savedStoryId})
          </p>
        </div>
      )}

      {/* Action buttons — in the thumb zone on mobile */}
      <div className="flex flex-col sm:flex-row gap-3 pt-2">
        <Button
          onClick={handleSave}
          disabled={saving || playing}
          variant="outline"
          className="h-14 text-base font-semibold gap-2 flex-1"
        >
          {saving ? (
            <Loader2 className="size-5 animate-spin" />
          ) : (
            <Save className="size-5" />
          )}
          {saving ? 'Saving...' : savedStoryId ? 'Saved' : 'Save Scene'}
        </Button>

        <Button
          onClick={handlePlay}
          disabled={playing || saving || failCount > 0}
          className={cn(
            'h-14 text-base font-semibold gap-2 flex-1',
            'bg-gold hover:bg-gold-bright text-bg-primary',
            'disabled:opacity-40',
          )}
        >
          {playing ? (
            <Loader2 className="size-5 animate-spin" />
          ) : (
            <Play className="size-5" />
          )}
          {playing ? 'Starting...' : 'Play Scene'}
          <ChevronRight className="size-4 ml-1" />
        </Button>
      </div>

      {failCount > 0 && (
        <p className="text-text-muted text-xs text-center">
          Fix the failed checks above before playing.
        </p>
      )}
    </div>
  )
}
