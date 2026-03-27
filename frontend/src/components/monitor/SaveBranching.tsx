/**
 * SaveBranching — branch tree visualization for the save/load system.
 *
 * When loading a mid-game save, create a named branch. Show a branch tree
 * visualization. Each branch tracks its own escape chain progress
 * independently. Allow switching between branches.
 *
 * Since the backend doesn't have native branch support, branches are tracked
 * in client-side state (localStorage) as metadata overlaying existing saves.
 *
 * Visual aesthetic: organic vine/root tree growing from left to right,
 * with save nodes as glowing orbs at branch points.
 *
 * Mobile-first: bottom sheet with horizontal scroll for the tree.
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import {
  GitBranch,
  X,
  Plus,
  Loader2,
  Circle,
  ChevronRight,
  Sprout,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStoryId, useTick } from '@/stores/gameStore'

// ---------------------------------------------------------------------------
// Types — branch metadata stored in localStorage
// ---------------------------------------------------------------------------

interface BranchNode {
  id: string
  name: string
  /** Save ID this branch was created from (null = root) */
  parentSaveId: number | null
  /** Parent branch ID */
  parentBranchId: string | null
  /** Save IDs on this branch */
  saveIds: number[]
  /** When this branch was created */
  createdAt: number
  /** Tick when branch was created */
  createdAtTick: number
  /** Whether this is the currently active branch */
  isActive: boolean
  /** Color index for visualization */
  colorIdx: number
}

interface BranchStore {
  storyId: number
  branches: BranchNode[]
  activeBranchId: string
}

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'agenttown_branches'

function loadBranchStore(storyId: number): BranchStore {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}_${storyId}`)
    if (raw) {
      const parsed = JSON.parse(raw) as BranchStore
      if (parsed.storyId === storyId) return parsed
    }
  } catch { /* ignore */ }

  // Default: single "main" branch
  const defaultBranch: BranchNode = {
    id: 'main',
    name: 'Main Timeline',
    parentSaveId: null,
    parentBranchId: null,
    saveIds: [],
    createdAt: Date.now(),
    createdAtTick: 0,
    isActive: true,
    colorIdx: 0,
  }
  return {
    storyId,
    branches: [defaultBranch],
    activeBranchId: 'main',
  }
}

function saveBranchStore(store: BranchStore) {
  try {
    localStorage.setItem(`${STORAGE_KEY}_${store.storyId}`, JSON.stringify(store))
  } catch { /* localStorage full or unavailable */ }
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

interface SaveEntry {
  id: number
  story_id: number | null
  name: string
  created_at: string
  tick: number
  scenario: string
}

async function apiListSaves(): Promise<SaveEntry[]> {
  try {
    const res = await fetch('/api/saves')
    if (!res.ok) return []
    const data = await res.json()
    return data.saves || []
  } catch {
    return []
  }
}

async function apiLoad(saveId: number): Promise<boolean> {
  try {
    const res = await fetch(`/api/load/${saveId}`, { method: 'POST' })
    return res.ok
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Branch colors — organic vine palette
// ---------------------------------------------------------------------------

const BRANCH_COLORS = [
  { vine: 'bg-emerald-500', glow: 'shadow-emerald-500/30', text: 'text-emerald-400', border: 'border-emerald-500/40' },
  { vine: 'bg-amber-500', glow: 'shadow-amber-500/30', text: 'text-amber-400', border: 'border-amber-500/40' },
  { vine: 'bg-blue-500', glow: 'shadow-blue-500/30', text: 'text-blue-400', border: 'border-blue-500/40' },
  { vine: 'bg-purple-500', glow: 'shadow-purple-500/30', text: 'text-purple-400', border: 'border-purple-500/40' },
  { vine: 'bg-rose-500', glow: 'shadow-rose-500/30', text: 'text-rose-400', border: 'border-rose-500/40' },
  { vine: 'bg-cyan-500', glow: 'shadow-cyan-500/30', text: 'text-cyan-400', border: 'border-cyan-500/40' },
  { vine: 'bg-orange-500', glow: 'shadow-orange-500/30', text: 'text-orange-400', border: 'border-orange-500/40' },
]

// ---------------------------------------------------------------------------
// Branch name prompt — inline input overlay
// ---------------------------------------------------------------------------

function BranchNamePrompt({
  onConfirm,
  onCancel,
  defaultName,
}: {
  onConfirm: (name: string) => void
  onCancel: () => void
  defaultName: string
}) {
  const [name, setName] = useState(defaultName)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  return (
    <div className="p-3 border-t border-border bg-bg-tertiary/50">
      <label className="block text-xs text-text-secondary font-medium mb-1.5">
        Name this branch
      </label>
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && name.trim()) onConfirm(name.trim())
            if (e.key === 'Escape') onCancel()
          }}
          placeholder="e.g., What if we try the west door..."
          className="flex-1 rounded-lg border border-border bg-bg-primary px-3 py-2 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 min-h-[44px]"
        />
        <button
          onClick={() => name.trim() && onConfirm(name.trim())}
          disabled={!name.trim()}
          className={cn(
            'shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold min-h-[44px]',
            'bg-gold text-bg-primary hover:bg-gold-bright active:scale-95',
            'transition-all disabled:opacity-40 disabled:cursor-not-allowed',
          )}
        >
          <Sprout className="size-4" />
          Branch
        </button>
        <button
          onClick={onCancel}
          className="shrink-0 flex items-center justify-center size-11 min-h-[44px] min-w-[44px] rounded-lg bg-bg-tertiary text-text-muted hover:text-text-secondary transition-colors"
          aria-label="Cancel"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Branch tree visualization — organic vine style
// ---------------------------------------------------------------------------

function BranchTree({
  branchStore,
  saves,
  onSwitchBranch,
  onLoadSave,
  loadingId,
}: {
  branchStore: BranchStore
  saves: SaveEntry[]
  onSwitchBranch: (branchId: string) => void
  onLoadSave: (saveId: number) => void
  loadingId: number | null
}) {
  const saveMap = useMemo(() => {
    const map = new Map<number, SaveEntry>()
    for (const s of saves) map.set(s.id, s)
    return map
  }, [saves])

  // Build a layered tree: root at left, branches growing right
  const rootBranch = branchStore.branches.find(b => b.parentBranchId === null)
  if (!rootBranch) return null

  // Render a single branch row
  const renderBranch = (branch: BranchNode, depth: number) => {
    const color = BRANCH_COLORS[branch.colorIdx % BRANCH_COLORS.length]
    const isActive = branch.id === branchStore.activeBranchId
    const children = branchStore.branches.filter(b => b.parentBranchId === branch.id)

    return (
      <div key={branch.id} className="flex flex-col">
        {/* Branch row */}
        <div className="flex items-center gap-1 min-h-[52px]">
          {/* Depth indent — vine connectors */}
          {depth > 0 && (
            <div className="flex items-center" style={{ width: depth * 24 }}>
              {Array.from({ length: depth }, (_, i) => (
                <div
                  key={i}
                  className={cn(
                    'w-6 h-full flex items-center justify-center',
                  )}
                >
                  <div className="w-0.5 h-full bg-border/30" />
                </div>
              ))}
            </div>
          )}

          {/* Branch fork indicator */}
          {depth > 0 && (
            <div className="flex items-center">
              <div className={cn('w-4 h-0.5 rounded-full', color.vine, 'opacity-60')} />
              <ChevronRight className={cn('size-3 -ml-1', color.text, 'opacity-60')} />
            </div>
          )}

          {/* Branch node — tappable */}
          <button
            onClick={() => onSwitchBranch(branch.id)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-left min-h-[48px] flex-1',
              'transition-all duration-200 active:scale-[0.98]',
              isActive
                ? `bg-bg-tertiary border ${color.border} ${color.glow} shadow-md`
                : 'bg-bg-secondary/50 border border-border/50 hover:border-border',
            )}
          >
            {/* Branch orb */}
            <div className="relative shrink-0">
              <div
                className={cn(
                  'size-4 rounded-full',
                  color.vine,
                  isActive && 'animate-active-pulse',
                )}
              />
              {isActive && (
                <div className={cn('absolute inset-0 size-4 rounded-full', color.vine, 'opacity-30 blur-sm')} />
              )}
            </div>

            {/* Branch info */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className={cn('text-sm font-semibold truncate', isActive ? color.text : 'text-text-primary')}>
                  {branch.name}
                </span>
                {isActive && (
                  <span className="shrink-0 text-[9px] uppercase tracking-wider font-bold text-gold bg-gold/10 px-1.5 py-0.5 rounded">
                    Active
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[10px] text-text-muted mt-0.5">
                <span>T{branch.createdAtTick}</span>
                <span>{branch.saveIds.length} save{branch.saveIds.length !== 1 ? 's' : ''}</span>
              </div>
            </div>
          </button>

          {/* Save nodes on this branch */}
          <div className="flex items-center gap-1 ml-1 overflow-x-auto scrollbar-none">
            {branch.saveIds.slice(-5).map(saveId => {
              const save = saveMap.get(saveId)
              if (!save) return null
              return (
                <button
                  key={saveId}
                  onClick={() => onLoadSave(saveId)}
                  disabled={loadingId !== null}
                  title={`${save.name} (Tick ${save.tick})`}
                  className={cn(
                    'shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] min-h-[36px]',
                    'border border-border/50 bg-bg-tertiary/50',
                    'hover:border-gold/30 hover:bg-gold/5 active:scale-95',
                    'transition-all',
                    loadingId === saveId && 'opacity-50',
                  )}
                >
                  {loadingId === saveId ? (
                    <Loader2 className="size-3 animate-spin" />
                  ) : (
                    <Circle className="size-2.5 text-text-muted" />
                  )}
                  <span className="text-text-secondary font-mono">T{save.tick}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Child branches — recursion */}
        {children.map(child => renderBranch(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto scrollbar-none px-3 py-2">
      {renderBranch(rootBranch, 0)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main SaveBranching component
// ---------------------------------------------------------------------------

export function SaveBranching() {
  const storyId = useStoryId()
  const tick = useTick()
  const [isOpen, setIsOpen] = useState(false)
  const [branchStore, setBranchStore] = useState<BranchStore | null>(null)
  const [saves, setSaves] = useState<SaveEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingId, setLoadingId] = useState<number | null>(null)
  const [showBranchPrompt, setShowBranchPrompt] = useState(false)
  const [branchFromSaveId, setBranchFromSaveId] = useState<number | null>(null)

  // Initialize branch store from localStorage
  useEffect(() => {
    if (storyId) {
      setBranchStore(loadBranchStore(storyId))
    }
  }, [storyId])

  // Persist on changes
  useEffect(() => {
    if (branchStore) {
      saveBranchStore(branchStore)
    }
  }, [branchStore])

  // Fetch saves when panel opens
  useEffect(() => {
    if (!isOpen || !storyId) return
    let cancelled = false

    async function fetch() {
      setLoading(true)
      const all = await apiListSaves()
      if (cancelled) return
      const filtered = storyId ? all.filter(s => s.story_id === storyId) : all
      setSaves(filtered)
      setLoading(false)
    }
    fetch()

    return () => { cancelled = true }
  }, [isOpen, storyId])

  // Create a new branch from a save point
  const handleCreateBranch = useCallback((name: string) => {
    if (!branchStore) return

    const newBranch: BranchNode = {
      id: `branch_${Date.now()}`,
      name,
      parentSaveId: branchFromSaveId,
      parentBranchId: branchStore.activeBranchId,
      saveIds: [],
      createdAt: Date.now(),
      createdAtTick: tick,
      isActive: true,
      colorIdx: branchStore.branches.length,
    }

    setBranchStore(prev => {
      if (!prev) return prev
      return {
        ...prev,
        branches: prev.branches.map(b => ({ ...b, isActive: false })).concat(newBranch),
        activeBranchId: newBranch.id,
      }
    })

    setShowBranchPrompt(false)
    setBranchFromSaveId(null)

    // If branching from a save, load it
    if (branchFromSaveId) {
      handleLoadSave(branchFromSaveId)
    }
  }, [branchStore, branchFromSaveId, tick])

  // Switch active branch
  const handleSwitchBranch = useCallback((branchId: string) => {
    setBranchStore(prev => {
      if (!prev) return prev
      return {
        ...prev,
        branches: prev.branches.map(b => ({ ...b, isActive: b.id === branchId })),
        activeBranchId: branchId,
      }
    })
  }, [])

  // Load a save (with branch tracking)
  const handleLoadSave = useCallback(async (saveId: number) => {
    if (loadingId !== null) return
    setLoadingId(saveId)
    const ok = await apiLoad(saveId)
    setLoadingId(null)
    if (ok) {
      // Offer to branch if loading from a different branch's save
      // For now, just load
    }
  }, [loadingId])

  // Register a new save on the active branch
  const registerSaveOnBranch = useCallback((saveId: number) => {
    setBranchStore(prev => {
      if (!prev) return prev
      return {
        ...prev,
        branches: prev.branches.map(b =>
          b.id === prev.activeBranchId
            ? { ...b, saveIds: [...b.saveIds, saveId] }
            : b,
        ),
      }
    })
  }, [])

  const branchCount = branchStore?.branches.length ?? 0
  const activeBranch = branchStore?.branches.find(b => b.id === branchStore.activeBranchId)

  // Don't render if no story is loaded
  if (!storyId) return null

  return (
    <>
      {/* Branch button — sits in the controls area */}
      <button
        onClick={() => setIsOpen(true)}
        className={cn(
          'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
          'bg-bg-tertiary text-text-secondary',
          'hover:bg-border hover:text-text-primary active:scale-95',
          'transition-all duration-150',
        )}
        aria-label="Branch timeline"
      >
        <GitBranch size={15} />
        <span className="hidden sm:inline">
          {activeBranch?.name === 'Main Timeline' ? 'Branches' : activeBranch?.name}
        </span>
        {branchCount > 1 && (
          <span className="inline-flex items-center justify-center size-4 rounded-full bg-gold/15 text-gold text-[9px] font-bold min-h-0 min-w-0">
            {branchCount}
          </span>
        )}
      </button>

      {/* Branch panel — bottom sheet (mobile) / popover (desktop) */}
      {isOpen && branchStore && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-[60] bg-black/40" onClick={() => setIsOpen(false)} />

          {/* Panel */}
          <div
            className={cn(
              'fixed z-[61] bg-bg-secondary border border-border shadow-xl',
              // Mobile: bottom sheet
              'inset-x-0 bottom-0 rounded-t-2xl max-h-[75vh]',
              // Desktop: popover
              'md:inset-auto md:bottom-20 md:left-4 md:w-[440px] md:max-h-[65vh] md:rounded-xl',
            )}
          >
            {/* Drag handle (mobile) */}
            <div className="flex justify-center pt-3 pb-1 md:hidden">
              <div className="w-10 h-1 rounded-full bg-text-muted" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 className="text-base font-bold text-text-primary m-0 flex items-center gap-2">
                <GitBranch size={16} className="text-emerald-400" />
                Timeline Branches
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setBranchFromSaveId(null)
                    setShowBranchPrompt(true)
                  }}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium min-h-[44px]',
                    'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
                    'hover:bg-emerald-500/20 active:scale-95 transition-all',
                  )}
                >
                  <Plus size={14} />
                  New Branch
                </button>
                <button
                  onClick={() => setIsOpen(false)}
                  className="size-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
                  aria-label="Close"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Branch name prompt */}
            {showBranchPrompt && (
              <BranchNamePrompt
                defaultName={`Branch ${branchCount}`}
                onConfirm={handleCreateBranch}
                onCancel={() => {
                  setShowBranchPrompt(false)
                  setBranchFromSaveId(null)
                }}
              />
            )}

            {/* Branch tree */}
            <div className="overflow-y-auto max-h-[calc(75vh-140px)] md:max-h-[calc(65vh-140px)]">
              {loading ? (
                <div className="flex items-center justify-center py-10 text-text-muted">
                  <Loader2 size={20} className="animate-spin mr-2" />
                  Loading branches...
                </div>
              ) : (
                <BranchTree
                  branchStore={branchStore}
                  saves={saves}
                  onSwitchBranch={handleSwitchBranch}
                  onLoadSave={(saveId) => {
                    // Show branch prompt when loading a save from a different branch
                    const currentBranch = branchStore.branches.find(b => b.id === branchStore.activeBranchId)
                    const isOnCurrentBranch = currentBranch?.saveIds.includes(saveId)

                    if (!isOnCurrentBranch && branchStore.branches.length > 0) {
                      setBranchFromSaveId(saveId)
                      setShowBranchPrompt(true)
                    } else {
                      handleLoadSave(saveId)
                    }
                  }}
                  loadingId={loadingId}
                />
              )}
            </div>

            {/* Footer info */}
            <div className="px-4 py-2 border-t border-border/50 text-[10px] text-text-muted flex items-center justify-between">
              <span>
                {branchCount} branch{branchCount !== 1 ? 'es' : ''}
                {activeBranch && (
                  <> | Active: <span className="text-emerald-400">{activeBranch.name}</span></>
                )}
              </span>
              <span className="text-text-muted/50">Branches stored locally</span>
            </div>
          </div>
        </>
      )}
    </>
  )
}
