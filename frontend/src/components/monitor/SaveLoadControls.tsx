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
 *
 * Exhibition-grade elevation:
 *  - Save ceremony: wax-seal circular reveal wipe in gold, shrinks to "Saved at Tick N" badge
 *  - Load list as dossier/case files: rotated cards, paper-fold corners, classified stamp
 *  - Load transition: glitch/dissolve effect when loading a save
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
  Stamp,
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
// Save Dialog — wax-seal ceremony with circular reveal animation
// ---------------------------------------------------------------------------

function SaveDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void
  onSaved: (tick: number) => void
}) {
  const tick = useTick()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [savePhase, setSavePhase] = useState<'idle' | 'sealing' | 'sealed'>('idle')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSave = useCallback(async () => {
    if (saving || savePhase !== 'idle') return
    setSaving(true)
    const result = await apiSave(name.trim() || undefined)
    setSaving(false)
    if (result) {
      // Start the sealing ceremony
      setSavePhase('sealing')
      // After the seal animation completes, transition to sealed badge
      setTimeout(() => {
        setSavePhase('sealed')
        onSaved(tick)
        // Close after showing the sealed state briefly
        setTimeout(() => {
          onClose()
        }, 800)
      }, 700)
    }
  }, [name, saving, savePhase, onSaved, onClose, tick])

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
              disabled={savePhase !== 'idle'}
              className="w-full rounded-lg border border-border bg-bg-primary px-3 py-2.5 text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50 min-h-[44px] disabled:opacity-50"
            />
          </div>

          <div className="text-xs text-text-muted">
            Current tick: <span className="text-gold font-mono">{tick}</span>
          </div>

          {/* Save button with wax-seal ceremony */}
          <div className="relative overflow-hidden rounded-lg">
            {/* Seal reveal overlay — appears during sealing animation */}
            {savePhase === 'sealing' && (
              <div
                className="absolute inset-0 z-10 animate-seal-reveal rounded-lg"
                style={{
                  background: 'rgba(227, 179, 65, 0.2)',
                }}
              />
            )}

            <button
              onClick={handleSave}
              disabled={saving || savePhase !== 'idle'}
              className={cn(
                'w-full flex items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold min-h-[48px]',
                'transition-all duration-300',
                savePhase === 'sealed'
                  ? 'bg-gold/10 text-gold border border-gold/30'
                  : savePhase === 'sealing'
                  ? 'bg-gold/20 text-gold border border-gold/40'
                  : 'bg-gold hover:bg-gold-bright text-bg-primary active:scale-[0.98]',
                (saving || savePhase !== 'idle') && 'cursor-not-allowed',
              )}
            >
              {saving ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Saving...
                </>
              ) : savePhase === 'sealing' ? (
                <>
                  <span
                    className="w-5 h-5 rounded-full border-2 border-gold"
                    style={{
                      background: 'radial-gradient(circle, #f0c95c 0%, #b8902e 100%)',
                      boxShadow: '0 0 8px rgba(227, 179, 65, 0.4)',
                    }}
                  />
                  Sealing...
                </>
              ) : savePhase === 'sealed' ? (
                <>
                  <Check size={16} />
                  Saved at Tick {tick}
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
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Load Panel — dossier-style case file cards
// ---------------------------------------------------------------------------

function LoadPanel({
  onClose,
  onLoadStart,
}: {
  onClose: () => void
  onLoadStart: () => void
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
    onLoadStart() // trigger glitch effect on monitor
    const ok = await apiLoad(saveId)
    setLoadingId(null)
    if (ok) {
      onClose()
    }
  }, [loadingId, onClose, onLoadStart])

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
            Case Files
          </h3>
          <button
            onClick={onClose}
            className="w-9 h-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Save list — dossier style */}
        <div className="overflow-y-auto max-h-[calc(70vh-80px)] md:max-h-[calc(60vh-80px)] p-3 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-text-muted">
              <Loader2 size={20} className="animate-spin mr-2" />
              Loading case files...
            </div>
          ) : saves.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
              <FolderOpen size={32} className="text-text-muted/30 mb-2" />
              <p className="text-sm text-text-muted m-0">No case files found</p>
              <p className="text-xs text-text-muted/60 m-0 mt-1">
                Save your game first to create case files
              </p>
            </div>
          ) : (
            saves.map((save, index) => (
              <div
                key={save.id}
                className="dossier-card rounded-lg border border-border bg-bg-tertiary/70 px-4 py-3"
                style={{
                  // Alternating slight rotation for dossier feel
                  transform: `rotate(${index % 2 === 0 ? -0.8 : 0.6}deg)`,
                }}
              >
                {/* CLASSIFIED stamp on most recent save */}
                {index === 0 && (
                  <div
                    className="absolute -top-1 -right-1 z-10 flex items-center gap-1 px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-widest"
                    style={{
                      background: 'rgba(248, 81, 73, 0.15)',
                      color: '#f85149',
                      border: '1px solid rgba(248, 81, 73, 0.3)',
                      transform: 'rotate(3deg)',
                    }}
                  >
                    <Stamp size={8} />
                    Latest
                  </div>
                )}

                <div className="flex items-center gap-3">
                  {/* Save info */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text-primary truncate">
                      {save.name}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-xs text-text-muted">
                      {/* Tick in typewriter-style mono font */}
                      <span
                        className="font-mono tracking-wider"
                        style={{ color: '#e3b341', letterSpacing: '0.1em' }}
                      >
                        TICK {String(save.tick).padStart(3, '0')}
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
              </div>
            ))
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
  const [lastSaveTick, setLastSaveTick] = useState<number | null>(null)
  const [lastSaveTime, setLastSaveTime] = useState<number | null>(null)
  // Glitch effect state — triggered when a save is being loaded
  const [isGlitching, setIsGlitching] = useState(false)

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

  const handleSaved = useCallback((savedTick: number) => {
    setLastSaveTime(Date.now())
    setLastSaveTick(savedTick)
  }, [])

  const handleLoadStart = useCallback(() => {
    // Trigger glitch/dissolve effect
    setIsGlitching(true)
    setTimeout(() => setIsGlitching(false), 800)
  }, [])

  return (
    <>
      {/* Glitch overlay — covers the parent monitor when loading a save */}
      {isGlitching && (
        <div className="fixed inset-0 z-[55] pointer-events-none animate-load-glitch">
          <div className="w-full h-full bg-bg-primary/30" />
        </div>
      )}

      {/* Control buttons — rendered in the simulation controls bar area */}
      <div className="flex items-center gap-1.5">
        {/* Sealed save badge — shows after save ceremony */}
        {lastSaveTick !== null && (
          <span
            className="hidden sm:inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-medium mr-1"
            style={{
              background: 'rgba(227, 179, 65, 0.08)',
              color: '#b8902e',
              border: '1px solid rgba(227, 179, 65, 0.15)',
            }}
          >
            <Check size={10} />
            Tick {lastSaveTick}
          </span>
        )}

        {/* Auto-save / last-save indicator (fallback if no tick badge) */}
        {lastSaveLabel && !lastSaveTick && (
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
          onLoadStart={handleLoadStart}
        />
      )}
    </>
  )
}
