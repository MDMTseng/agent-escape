/**
 * SaveBranching -- branch tree visualization for the save/load system.
 *
 * Exhibition-grade enhancements (curator feedback):
 *   1. Auto-load on branch switch -- loads latest save from switched branch
 *   2. Tick divergence counts -- "N ticks from fork" per branch
 *   3. Animated vine growth -- stroke-dasharray on new branches (500ms)
 *   4. Save node tooltips -- tick, timestamp, branch name on hover/tap
 *   5. Delete branch -- with confirmation dialog
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
  Trash2,
  AlertTriangle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStoryId, useTick } from '@/stores/gameStore'

// ---------------------------------------------------------------------------
// Types -- branch metadata stored in localStorage
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
// Branch colors -- organic vine palette
// ---------------------------------------------------------------------------

const BRANCH_COLORS = [
  { vine: 'bg-emerald-500', glow: 'shadow-emerald-500/30', text: 'text-emerald-400', border: 'border-emerald-500/40', hex: '#10b981' },
  { vine: 'bg-amber-500', glow: 'shadow-amber-500/30', text: 'text-amber-400', border: 'border-amber-500/40', hex: '#f59e0b' },
  { vine: 'bg-blue-500', glow: 'shadow-blue-500/30', text: 'text-blue-400', border: 'border-blue-500/40', hex: '#3b82f6' },
  { vine: 'bg-purple-500', glow: 'shadow-purple-500/30', text: 'text-purple-400', border: 'border-purple-500/40', hex: '#a855f7' },
  { vine: 'bg-rose-500', glow: 'shadow-rose-500/30', text: 'text-rose-400', border: 'border-rose-500/40', hex: '#f43f5e' },
  { vine: 'bg-cyan-500', glow: 'shadow-cyan-500/30', text: 'text-cyan-400', border: 'border-cyan-500/40', hex: '#06b6d4' },
  { vine: 'bg-orange-500', glow: 'shadow-orange-500/30', text: 'text-orange-400', border: 'border-orange-500/40', hex: '#f97316' },
]

// ---------------------------------------------------------------------------
// Vine growth animation styles (injected once)
// ---------------------------------------------------------------------------

const VINE_STYLE_ID = 'save-branching-vine-styles'

function ensureVineStyles() {
  if (typeof document === 'undefined') return
  if (document.getElementById(VINE_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = VINE_STYLE_ID
  style.textContent = `
    @keyframes vine-grow {
      from { stroke-dashoffset: 100; }
      to { stroke-dashoffset: 0; }
    }
    .vine-grow-anim {
      stroke-dasharray: 100;
      stroke-dashoffset: 100;
      animation: vine-grow 500ms ease-out forwards;
    }
    @media (prefers-reduced-motion: reduce) {
      .vine-grow-anim {
        animation: none;
        stroke-dashoffset: 0;
      }
    }
  `
  document.head.appendChild(style)
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

function formatTimestamp(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}

// ---------------------------------------------------------------------------
// Save node tooltip -- appears on hover/tap
// ---------------------------------------------------------------------------

function SaveNodeTooltip({
  save,
  branchName,
  position,
  onClose,
}: {
  save: SaveEntry
  branchName: string
  position: { x: number; y: number }
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent | TouchEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('touchstart', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      className={cn(
        'absolute z-[70] bg-bg-primary border border-border rounded-lg shadow-xl p-3',
        'text-xs min-w-[160px] pointer-events-auto',
        'animate-in fade-in-0 zoom-in-95 duration-150',
      )}
      style={{
        left: Math.max(8, position.x - 80),
        top: position.y - 80,
      }}
    >
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Circle className="size-2.5 text-gold" />
          <span className="font-semibold text-text-primary">{save.name || 'Unnamed Save'}</span>
        </div>
        <div className="text-text-muted space-y-0.5">
          <div>Tick: <span className="text-text-secondary font-mono">{save.tick}</span></div>
          <div>Time: <span className="text-text-secondary">{formatTimestamp(save.created_at)}</span></div>
          <div>Branch: <span className="text-text-secondary">{branchName}</span></div>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Delete branch confirmation dialog
// ---------------------------------------------------------------------------

function DeleteBranchDialog({
  branchName,
  saveCount,
  onConfirm,
  onCancel,
}: {
  branchName: string
  saveCount: number
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[90] bg-black/60" onClick={onCancel} />
      {/* Dialog */}
      <div
        className={cn(
          'fixed z-[91] bg-bg-secondary border border-border rounded-xl shadow-2xl',
          'inset-x-4 bottom-8 p-5',
          'md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2',
          'md:w-[380px] md:p-6',
          'animate-in fade-in-0 slide-in-from-bottom-4 duration-200',
        )}
      >
        <div className="flex items-start gap-3 mb-4">
          <div className="shrink-0 flex items-center justify-center size-10 rounded-full bg-danger/10">
            <AlertTriangle size={20} className="text-danger" />
          </div>
          <div>
            <h4 className="text-base font-bold text-text-primary m-0">Delete Branch</h4>
            <p className="text-sm text-text-secondary mt-1 m-0">
              Delete <strong className="text-text-primary">{branchName}</strong>?
              {saveCount > 0 && (
                <> This branch has {saveCount} save{saveCount !== 1 ? 's' : ''} associated with it.</>
              )}
            </p>
            <p className="text-xs text-text-muted mt-1.5 m-0">
              Save files on disk will not be deleted, only the branch metadata.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 justify-end">
          <button
            onClick={onCancel}
            className={cn(
              'flex items-center px-4 py-2 rounded-lg text-sm font-medium min-h-[44px]',
              'bg-bg-tertiary text-text-secondary hover:text-text-primary',
              'transition-colors active:scale-95',
            )}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold min-h-[44px]',
              'bg-danger/15 text-danger border border-danger/20',
              'hover:bg-danger/25 active:scale-95 transition-all',
            )}
          >
            <Trash2 size={14} />
            Delete Branch
          </button>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Branch name prompt -- inline input overlay
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
// Branch tree visualization -- organic vine style
// ---------------------------------------------------------------------------

function BranchTree({
  branchStore,
  saves,
  onSwitchBranch,
  onLoadSave,
  onDeleteBranch,
  loadingId,
  newBranchId,
}: {
  branchStore: BranchStore
  saves: SaveEntry[]
  onSwitchBranch: (branchId: string) => void
  onLoadSave: (saveId: number) => void
  onDeleteBranch: (branchId: string) => void
  loadingId: number | null
  /** ID of a recently created branch (for vine animation) */
  newBranchId: string | null
}) {
  const saveMap = useMemo(() => {
    const map = new Map<number, SaveEntry>()
    for (const s of saves) map.set(s.id, s)
    return map
  }, [saves])

  // Tooltip state
  const [tooltip, setTooltip] = useState<{
    save: SaveEntry
    branchName: string
    position: { x: number; y: number }
  } | null>(null)

  // Compute tick divergence: how many ticks each branch has from its fork point
  const tickDivergence = useMemo(() => {
    const divergence = new Map<string, number>()
    for (const branch of branchStore.branches) {
      if (!branch.parentBranchId) {
        // Root has no divergence
        divergence.set(branch.id, 0)
        continue
      }
      // Get the max tick on this branch from its saves
      const branchSaveTicks = branch.saveIds
        .map(id => saveMap.get(id)?.tick ?? 0)
      const maxTick = branchSaveTicks.length > 0 ? Math.max(...branchSaveTicks) : branch.createdAtTick
      const ticksFromFork = maxTick - branch.createdAtTick
      divergence.set(branch.id, Math.max(0, ticksFromFork))
    }
    return divergence
  }, [branchStore.branches, saveMap])

  // Build a layered tree: root at left, branches growing right
  const rootBranch = branchStore.branches.find(b => b.parentBranchId === null)
  if (!rootBranch) return null

  const handleSaveNodeInteraction = (
    e: React.MouseEvent | React.TouchEvent,
    save: SaveEntry,
    branchName: string,
  ) => {
    e.stopPropagation()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const containerRect = (e.currentTarget as HTMLElement).closest('.branch-tree-container')?.getBoundingClientRect()
    if (!containerRect) return
    setTooltip({
      save,
      branchName,
      position: {
        x: rect.left - containerRect.left + rect.width / 2,
        y: rect.top - containerRect.top,
      },
    })
  }

  // Render a single branch row
  const renderBranch = (branch: BranchNode, depth: number) => {
    const color = BRANCH_COLORS[branch.colorIdx % BRANCH_COLORS.length]
    const isActive = branch.id === branchStore.activeBranchId
    const children = branchStore.branches.filter(b => b.parentBranchId === branch.id)
    const isNew = branch.id === newBranchId
    const divergenceTicks = tickDivergence.get(branch.id) ?? 0
    const isRoot = branch.parentBranchId === null

    return (
      <div key={branch.id} className="flex flex-col">
        {/* Branch row */}
        <div className="flex items-center gap-1 min-h-[52px]">
          {/* Depth indent -- vine connectors */}
          {depth > 0 && (
            <div className="flex items-center" style={{ width: depth * 24 }}>
              {Array.from({ length: depth }, (_, i) => (
                <div
                  key={i}
                  className="w-6 h-full flex items-center justify-center"
                >
                  <div className="w-0.5 h-full bg-border/30" />
                </div>
              ))}
            </div>
          )}

          {/* Branch fork indicator with vine growth animation */}
          {depth > 0 && (
            <div className="flex items-center">
              {isNew ? (
                /* Animated vine connector for new branches */
                <svg width="20" height="4" viewBox="0 0 20 4" className="shrink-0">
                  <line
                    x1="0" y1="2" x2="20" y2="2"
                    stroke={color.hex}
                    strokeWidth="2"
                    strokeLinecap="round"
                    className="vine-grow-anim"
                    opacity="0.6"
                  />
                </svg>
              ) : (
                <>
                  <div className={cn('w-4 h-0.5 rounded-full', color.vine, 'opacity-60')} />
                  <ChevronRight className={cn('size-3 -ml-1', color.text, 'opacity-60')} />
                </>
              )}
            </div>
          )}

          {/* Branch node -- tappable */}
          <button
            onClick={() => onSwitchBranch(branch.id)}
            className={cn(
              'flex items-center gap-2 px-3 py-2 rounded-lg text-left min-h-[48px] flex-1',
              'transition-all duration-200 active:scale-[0.98]',
              isActive
                ? `bg-bg-tertiary border ${color.border} ${color.glow} shadow-md`
                : 'bg-bg-secondary/50 border border-border/50 hover:border-border',
              isNew && 'animate-in fade-in-0 slide-in-from-left-2 duration-300',
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
                {/* Tick divergence count */}
                {!isRoot && (
                  <span className={cn('px-1 py-0.5 rounded bg-bg-primary/60', color.text, 'text-[9px] font-medium')}>
                    {divergenceTicks} tick{divergenceTicks !== 1 ? 's' : ''} from fork
                  </span>
                )}
              </div>
            </div>

            {/* Delete branch button (not for root or active branch) */}
            {!isRoot && !isActive && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDeleteBranch(branch.id)
                }}
                className={cn(
                  'shrink-0 flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg',
                  'text-text-muted/40 hover:text-danger hover:bg-danger/10',
                  'transition-colors active:scale-95',
                )}
                aria-label={`Delete branch ${branch.name}`}
              >
                <Trash2 size={14} />
              </button>
            )}
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
                  onContextMenu={(e) => {
                    e.preventDefault()
                    handleSaveNodeInteraction(e, save, branch.name)
                  }}
                  onTouchStart={(e) => {
                    // Long-press for tooltip on mobile
                    const timer = setTimeout(() => {
                      handleSaveNodeInteraction(e, save, branch.name)
                    }, 400)
                    const cleanup = () => clearTimeout(timer)
                    e.currentTarget.addEventListener('touchend', cleanup, { once: true })
                    e.currentTarget.addEventListener('touchmove', cleanup, { once: true })
                  }}
                  disabled={loadingId !== null}
                  title={`${save.name} (Tick ${save.tick})`}
                  className={cn(
                    'shrink-0 flex items-center gap-1 px-2 py-1 rounded text-[10px] min-h-[44px] min-w-[44px]',
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

        {/* Child branches -- recursion */}
        {children.map(child => renderBranch(child, depth + 1))}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto scrollbar-none px-3 py-2 relative branch-tree-container">
      {renderBranch(rootBranch, 0)}
      {/* Tooltip overlay */}
      {tooltip && (
        <SaveNodeTooltip
          save={tooltip.save}
          branchName={tooltip.branchName}
          position={tooltip.position}
          onClose={() => setTooltip(null)}
        />
      )}
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
  /** Track the most recently created branch for vine growth animation */
  const [newBranchId, setNewBranchId] = useState<string | null>(null)
  /** Branch pending deletion (for confirmation dialog) */
  const [deletingBranch, setDeletingBranch] = useState<BranchNode | null>(null)

  // Inject vine growth animation styles
  useEffect(() => {
    ensureVineStyles()
  }, [])

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

    async function fetchSaves() {
      setLoading(true)
      const all = await apiListSaves()
      if (cancelled) return
      const filtered = storyId ? all.filter(s => s.story_id === storyId) : all
      setSaves(filtered)
      setLoading(false)
    }
    fetchSaves()

    return () => { cancelled = true }
  }, [isOpen, storyId])

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

  // Create a new branch from a save point
  const handleCreateBranch = useCallback((name: string) => {
    if (!branchStore) return

    const branchId = `branch_${Date.now()}`
    const newBranch: BranchNode = {
      id: branchId,
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

    // Trigger vine growth animation
    setNewBranchId(branchId)
    setTimeout(() => setNewBranchId(null), 600)

    setShowBranchPrompt(false)
    setBranchFromSaveId(null)

    // If branching from a save, load it
    if (branchFromSaveId) {
      handleLoadSave(branchFromSaveId)
    }
  }, [branchStore, branchFromSaveId, tick, handleLoadSave])

  // Switch active branch + auto-load latest save on that branch
  const handleSwitchBranch = useCallback(async (branchId: string) => {
    if (!branchStore) return
    const targetBranch = branchStore.branches.find(b => b.id === branchId)
    if (!targetBranch || targetBranch.id === branchStore.activeBranchId) return

    setBranchStore(prev => {
      if (!prev) return prev
      return {
        ...prev,
        branches: prev.branches.map(b => ({ ...b, isActive: b.id === branchId })),
        activeBranchId: branchId,
      }
    })

    // Auto-load the latest save from the switched branch
    if (targetBranch.saveIds.length > 0) {
      const latestSaveId = targetBranch.saveIds[targetBranch.saveIds.length - 1]
      await handleLoadSave(latestSaveId)
    }
  }, [branchStore, handleLoadSave])

  // Delete a branch (with children)
  const handleDeleteBranch = useCallback((branchId: string) => {
    if (!branchStore) return
    const branch = branchStore.branches.find(b => b.id === branchId)
    if (!branch || branch.parentBranchId === null) return // Cannot delete root
    if (branch.id === branchStore.activeBranchId) return // Cannot delete active branch
    setDeletingBranch(branch)
  }, [branchStore])

  const confirmDeleteBranch = useCallback(() => {
    if (!deletingBranch || !branchStore) return

    // Collect all descendant branch IDs (recursive)
    const idsToDelete = new Set<string>()
    function collectDescendants(parentId: string) {
      idsToDelete.add(parentId)
      for (const b of branchStore!.branches) {
        if (b.parentBranchId === parentId) {
          collectDescendants(b.id)
        }
      }
    }
    collectDescendants(deletingBranch.id)

    setBranchStore(prev => {
      if (!prev) return prev
      return {
        ...prev,
        branches: prev.branches.filter(b => !idsToDelete.has(b.id)),
      }
    })

    setDeletingBranch(null)
  }, [deletingBranch, branchStore])

  const branchCount = branchStore?.branches.length ?? 0
  const activeBranch = branchStore?.branches.find(b => b.id === branchStore.activeBranchId)

  // Don't render if no story is loaded
  if (!storyId) return null

  return (
    <>
      {/* Branch button -- sits in the controls area */}
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

      {/* Branch panel -- bottom sheet (mobile) / popover (desktop) */}
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
                  onDeleteBranch={handleDeleteBranch}
                  loadingId={loadingId}
                  newBranchId={newBranchId}
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

      {/* Delete branch confirmation dialog */}
      {deletingBranch && (
        <DeleteBranchDialog
          branchName={deletingBranch.name}
          saveCount={deletingBranch.saveIds.length}
          onConfirm={confirmDeleteBranch}
          onCancel={() => setDeletingBranch(null)}
        />
      )}
    </>
  )
}
