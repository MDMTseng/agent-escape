/**
 * SaveLoadControls — save/load UI for the Game Monitor.
 *
 * Save button: opens a dialog with optional name input, calls POST /api/save.
 * Load panel: lists all saves for the current story (tick, timestamp, name).
 * Load action: POST /api/load/{save_id}, backend broadcasts snapshot to refresh store.
 * Auto-save indicator: shows when last auto-save occurred.
 *
 * Mobile: bottom sheet for both save dialog and load list.
 * Desktop: popover/dropdown inline in the controls area.
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import {
  Save,
  FolderOpen,
  X,
  Clock,
  Loader2,
  Check,
  Trash2,
  Download,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useStoryId, useTick } from '@/stores/gameStore'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SaveEntry {
  id: number
  story_id: number | null
  name: string
  created_at: string
  tick: number
  scenario: string
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiSave(name?: string): Promise<{ save_id: number; name: string } | null> {
  try {
    const params = name ? `?name=${encodeURIComponent(name)}` : ''
    const res = await fetch(`/api/save${params}`, { method: 'POST' })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
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

async function apiDeleteSave(saveId: number): Promise<boolean> {
  try {
    const res = await fetch(`/api/saves/${saveId}`, { method: 'DELETE' })
    return res.ok
  } catch {
    return false
  }
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

function formatTimestamp(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return isoStr
  }
}

// ---------------------------------------------------------------------------
// Save Dialog — inline popover (desktop) / bottom sheet (mobile)
// ---------------------------------------------------------------------------

function SaveDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved: () => void
}) {
  const tick = useTick()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSave = useCallback(async () => {
    if (saving) return
    setSaving(true)
    const result = await apiSave(name.trim() || undefined)
    setSaving(false)
    if (result) {
      setSaved(true)
      setTimeout(() => {
        onSaved()
        onClose()
      }, 600)
    }
  }, [name, saving, onSaved, onClose])

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[60] bg-black/40" onClick={onClose} />

      {/* Dialog */}
      <div
        className={cn(
          'fixed z-[61] bg-bg-secondary border border-border shadow-xl',
          // Mobile: bottom sheet
          'inset-x-0 bottom-0 rounded-t-2xl',
          // Desktop: centered popover
          'md:inset-auto md:bottom-20 md:right-4 md:w-[340px] md:rounded-xl',
        )}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-base font-bold text-text-primary m-0 flex items-center gap-2">
            <Save size={16} className="text-gold" />
            Save Game
          </h3>
          <button
            onClick={onClose}
            className="w-9 h-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-4 space-y-3">
          <div>
            <label className="block text-text-secondary text-xs font-medium mb-1">
              Save name (optional)
            </label>
            <input
              ref={inputRef}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleSave() }}
              placeholder={`Tick ${tick}`}
              className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px]"
            />
          </div>

          <div className="text-xs text-text-muted">
            Current tick: <span className="text-gold font-mono">{tick}</span>
          </div>

          <button
            onClick={handleSave}
            disabled={saving || saved}
            className={cn(
              'w-full flex items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold min-h-[48px]',
              'transition-all duration-200',
              saved
                ? 'bg-success/15 text-success border border-success/30'
                : 'bg-gold hover:bg-gold-bright text-bg-primary active:scale-[0.98]',
              (saving || saved) && 'cursor-not-allowed',
            )}
          >
            {saving ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Saving...
              </>
            ) : saved ? (
              <>
                <Check size={16} />
                Saved!
              </>
            ) : (
              <>
                <Save size={16} />
                Save
              </>
            )}
          </button>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Load Panel — list of saves
// ---------------------------------------------------------------------------

function LoadPanel({
  onClose,
}: {
  onClose: () => void
}) {
  const [saves, setSaves] = useState<SaveEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingId, setLoadingId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const storyId = useStoryId()

  const fetchSaves = useCallback(async () => {
    setLoading(true)
    const all = await apiListSaves()
    // Filter by current story if we have one
    const filtered = storyId
      ? all.filter((s) => s.story_id === storyId)
      : all
    setSaves(filtered)
    setLoading(false)
  }, [storyId])

  useEffect(() => {
    fetchSaves()
  }, [fetchSaves])

  const handleLoad = useCallback(async (saveId: number) => {
    if (loadingId !== null) return
    setLoadingId(saveId)
    const ok = await apiLoad(saveId)
    setLoadingId(null)
    if (ok) {
      onClose()
    }
  }, [loadingId, onClose])

  const handleDelete = useCallback(async (saveId: number) => {
    if (deletingId !== null) return
    setDeletingId(saveId)
    const ok = await apiDeleteSave(saveId)
    if (ok) {
      setSaves((prev) => prev.filter((s) => s.id !== saveId))
    }
    setDeletingId(null)
  }, [deletingId])

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[60] bg-black/40" onClick={onClose} />

      {/* Panel */}
      <div
        className={cn(
          'fixed z-[61] bg-bg-secondary border border-border shadow-xl',
          // Mobile: bottom sheet, taller
          'inset-x-0 bottom-0 rounded-t-2xl max-h-[70vh]',
          // Desktop: popover
          'md:inset-auto md:bottom-20 md:right-4 md:w-[380px] md:max-h-[60vh] md:rounded-xl',
        )}
      >
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 md:hidden">
          <div className="w-10 h-1 rounded-full bg-text-muted" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-base font-bold text-text-primary m-0 flex items-center gap-2">
            <FolderOpen size={16} className="text-gold" />
            Load Save
          </h3>
          <button
            onClick={onClose}
            className="w-9 h-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Save list */}
        <div className="overflow-y-auto max-h-[calc(70vh-80px)] md:max-h-[calc(60vh-80px)]">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-text-muted">
              <Loader2 size={20} className="animate-spin mr-2" />
              Loading saves...
            </div>
          ) : saves.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
              <FolderOpen size={32} className="text-text-muted/30 mb-2" />
              <p className="text-sm text-text-muted m-0">No saves found</p>
              <p className="text-xs text-text-muted/60 m-0 mt-1">
                Save your game first to see saves here
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {saves.map((save) => (
                <div
                  key={save.id}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-bg-tertiary/50 transition-colors"
                >
                  {/* Save info */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text-primary truncate">
                      {save.name}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-xs text-text-muted">
                      <span className="font-mono text-gold-dim">
                        Tick {save.tick}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock size={10} />
                        {formatTimestamp(save.created_at)}
                      </span>
                    </div>
                  </div>

                  {/* Load button */}
                  <button
                    onClick={() => handleLoad(save.id)}
                    disabled={loadingId !== null}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
                      'bg-gold/10 text-gold border border-gold/20',
                      'hover:bg-gold/20 active:scale-95 transition-all',
                      loadingId !== null && 'opacity-50 cursor-not-allowed',
                    )}
                  >
                    {loadingId === save.id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Download size={14} />
                    )}
                    Load
                  </button>

                  {/* Delete button */}
                  <button
                    onClick={() => handleDelete(save.id)}
                    disabled={deletingId !== null}
                    className={cn(
                      'flex items-center justify-center w-9 h-9 min-w-[44px] min-h-[44px] rounded-lg',
                      'text-text-muted hover:text-danger hover:bg-danger/10',
                      'transition-colors active:scale-95',
                      deletingId === save.id && 'opacity-50',
                    )}
                    aria-label={`Delete save ${save.name}`}
                  >
                    {deletingId === save.id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Main SaveLoadControls — buttons that open save/load panels
// ---------------------------------------------------------------------------

export function SaveLoadControls() {
  const [showSave, setShowSave] = useState(false)
  const [showLoad, setShowLoad] = useState(false)
  const [lastSaveTime, setLastSaveTime] = useState<number | null>(null)

  // Format last save time as relative
  const lastSaveLabel = useMemo(() => {
    if (!lastSaveTime) return null
    const diffMs = Date.now() - lastSaveTime
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return 'Saved just now'
    if (diffMins < 60) return `Saved ${diffMins}m ago`
    return `Saved ${Math.floor(diffMins / 60)}h ago`
  }, [lastSaveTime])

  // Re-render every minute to keep "saved X ago" fresh
  const [, setRefresh] = useState(0)
  useEffect(() => {
    if (!lastSaveTime) return
    const timer = setInterval(() => setRefresh((r) => r + 1), 60000)
    return () => clearInterval(timer)
  }, [lastSaveTime])

  const handleSaved = useCallback(() => {
    setLastSaveTime(Date.now())
  }, [])

  return (
    <>
      {/* Control buttons — rendered in the simulation controls bar area */}
      <div className="flex items-center gap-1.5">
        {/* Auto-save / last-save indicator */}
        {lastSaveLabel && (
          <span className="text-[10px] text-text-muted hidden sm:inline mr-1">
            {lastSaveLabel}
          </span>
        )}

        {/* Save button */}
        <button
          onClick={() => { setShowSave(true); setShowLoad(false) }}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-border hover:text-text-primary active:scale-95',
            'transition-all duration-150',
          )}
          aria-label="Save game"
        >
          <Save size={15} />
          <span className="hidden xs:inline">Save</span>
        </button>

        {/* Load button */}
        <button
          onClick={() => { setShowLoad(true); setShowSave(false) }}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-border hover:text-text-primary active:scale-95',
            'transition-all duration-150',
          )}
          aria-label="Load game"
        >
          <FolderOpen size={15} />
          <span className="hidden xs:inline">Load</span>
        </button>
      </div>

      {/* Dialogs */}
      {showSave && (
        <SaveDialog
          onClose={() => setShowSave(false)}
          onSaved={handleSaved}
        />
      )}
      {showLoad && (
        <LoadPanel
          onClose={() => setShowLoad(false)}
        />
      )}
    </>
  )
}
