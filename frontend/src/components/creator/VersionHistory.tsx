/**
 * VersionHistory -- track scene edits as versions with revert capability.
 *
 * Exhibition-grade enhancements (curator feedback):
 *   1. Auto-snapshot on tab navigation -- saves a version when switching tabs
 *   2. Revert confirmation dialog -- warns about unsaved changes before reverting
 *   3. Snapshot success animation -- camera flash/shutter effect on save
 *
 * Visual aesthetic: film-strip timeline with numbered frames.
 * Mobile-first: bottom sheet for history list, 44px+ touch targets.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import {
  History,
  X,
  RotateCcw,
  Film,
  Loader2,
  Trash2,
  AlertTriangle,
  Camera,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SceneCreatorState } from '@/pages/Creator'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VersionEntry {
  id: string
  /** Human-readable version label */
  label: string
  /** ISO timestamp */
  createdAt: string
  /** What changed -- auto-generated summary */
  summary: string
  /** Serialized scene snapshot */
  snapshot: SceneCreatorState
}

interface VersionStore {
  versions: VersionEntry[]
  maxVersions: number
}

// ---------------------------------------------------------------------------
// localStorage persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'agenttown_version_history'

function loadVersionStore(): VersionStore {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      return JSON.parse(raw) as VersionStore
    }
  } catch { /* ignore */ }
  return { versions: [], maxVersions: 20 }
}

function saveVersionStore(store: VersionStore) {
  try {
    // Trim to max versions
    const trimmed = {
      ...store,
      versions: store.versions.slice(-store.maxVersions),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  } catch { /* localStorage full */ }
}

// ---------------------------------------------------------------------------
// Auto-summarize changes between versions
// ---------------------------------------------------------------------------

function summarizeChanges(prev: SceneCreatorState | null, current: SceneCreatorState): string {
  if (!prev) return 'Initial version'

  const changes: string[] = []

  if (prev.theme !== current.theme) changes.push(`Theme: ${current.theme}`)
  if (prev.premise !== current.premise) changes.push('Premise updated')
  if (prev.difficulty !== current.difficulty) changes.push(`Difficulty: ${current.difficulty}`)

  const roomDiff = current.rooms.length - prev.rooms.length
  if (roomDiff > 0) changes.push(`+${roomDiff} room${roomDiff > 1 ? 's' : ''}`)
  if (roomDiff < 0) changes.push(`${roomDiff} room${Math.abs(roomDiff) > 1 ? 's' : ''}`)

  const doorDiff = current.doors.length - prev.doors.length
  if (doorDiff > 0) changes.push(`+${doorDiff} door${doorDiff > 1 ? 's' : ''}`)
  if (doorDiff < 0) changes.push(`${doorDiff} door${Math.abs(doorDiff) > 1 ? 's' : ''}`)

  const puzzleDiff = current.puzzles.length - prev.puzzles.length
  if (puzzleDiff > 0) changes.push(`+${puzzleDiff} puzzle${puzzleDiff > 1 ? 's' : ''}`)
  if (puzzleDiff < 0) changes.push(`${puzzleDiff} puzzle${Math.abs(puzzleDiff) > 1 ? 's' : ''}`)

  const agentDiff = current.agents.length - prev.agents.length
  if (agentDiff > 0) changes.push(`+${agentDiff} agent${agentDiff > 1 ? 's' : ''}`)
  if (agentDiff < 0) changes.push(`${agentDiff} agent${Math.abs(agentDiff) > 1 ? 's' : ''}`)

  if (!prev.worldBible && current.worldBible) changes.push('World Bible generated')

  return changes.length > 0 ? changes.join(', ') : 'Minor edits'
}

// ---------------------------------------------------------------------------
// Format timestamp
// ---------------------------------------------------------------------------

function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    return d.toLocaleDateString(undefined, {
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
// Snapshot flash styles (injected once)
// ---------------------------------------------------------------------------

const FLASH_STYLE_ID = 'version-history-flash-styles'

function ensureFlashStyles() {
  if (typeof document === 'undefined') return
  if (document.getElementById(FLASH_STYLE_ID)) return
  const style = document.createElement('style')
  style.id = FLASH_STYLE_ID
  style.textContent = `
    @keyframes snapshot-flash {
      0% { opacity: 0; }
      15% { opacity: 0.7; }
      100% { opacity: 0; }
    }
    .snapshot-flash-anim {
      animation: snapshot-flash 250ms ease-out forwards;
    }
    @media (prefers-reduced-motion: reduce) {
      .snapshot-flash-anim {
        animation: none;
      }
    }
  `
  document.head.appendChild(style)
}

// ---------------------------------------------------------------------------
// Revert Confirmation Dialog
// ---------------------------------------------------------------------------

function RevertConfirmDialog({
  versionLabel,
  onConfirm,
  onCancel,
}: {
  versionLabel: string
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
          <div className="shrink-0 flex items-center justify-center size-10 rounded-full bg-gold/10">
            <AlertTriangle size={20} className="text-gold" />
          </div>
          <div>
            <h4 className="text-base font-bold text-text-primary m-0">Revert to Previous Version?</h4>
            <p className="text-sm text-text-secondary mt-1 m-0">
              Reverting to <strong className="text-text-primary">{versionLabel}</strong> will
              replace your current scene state. Any unsaved changes will be lost.
            </p>
            <p className="text-xs text-text-muted mt-1.5 m-0">
              Tip: Take a snapshot first to preserve your current state.
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
              'bg-gold/15 text-gold border border-gold/20',
              'hover:bg-gold/25 active:scale-95 transition-all',
            )}
          >
            <RotateCcw size={14} />
            Revert
          </button>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Main VersionHistory component
// ---------------------------------------------------------------------------

export function VersionHistory({
  sceneState,
  onRevert,
  activeTab,
}: {
  sceneState: SceneCreatorState
  onRevert: (version: SceneCreatorState) => void
  /** Current active tab name -- used for auto-snapshot on tab navigation */
  activeTab?: string
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [store, setStore] = useState<VersionStore>(loadVersionStore)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  /** Entry pending revert confirmation */
  const [pendingRevert, setPendingRevert] = useState<VersionEntry | null>(null)
  /** Show camera flash animation overlay */
  const [showFlash, setShowFlash] = useState(false)
  /** Track the previous tab for auto-snapshot */
  const prevTabRef = useRef<string | undefined>(activeTab)
  /** Track whether scene has any meaningful data (avoid empty snapshots) */
  const hasData = sceneState.rooms.length > 0 || sceneState.agents.length > 0 || sceneState.puzzles.length > 0 || !!sceneState.worldBible

  // Inject flash animation styles
  useEffect(() => {
    ensureFlashStyles()
  }, [])

  // Persist on changes
  useEffect(() => {
    saveVersionStore(store)
  }, [store])

  // Save a version snapshot
  const saveVersion = useCallback(
    (label?: string) => {
      const prevSnapshot = store.versions.length > 0
        ? store.versions[store.versions.length - 1].snapshot
        : null

      const newEntry: VersionEntry = {
        id: `v_${Date.now()}`,
        label: label || `Version ${store.versions.length + 1}`,
        createdAt: new Date().toISOString(),
        summary: summarizeChanges(prevSnapshot, sceneState),
        snapshot: JSON.parse(JSON.stringify(sceneState)), // deep clone
      }

      setStore(prev => ({
        ...prev,
        versions: [...prev.versions, newEntry].slice(-prev.maxVersions),
      }))

      return newEntry
    },
    [sceneState, store.versions],
  )

  // Save with flash animation
  const saveWithFlash = useCallback(
    (label?: string) => {
      const entry = saveVersion(label)
      // Trigger camera flash
      setShowFlash(true)
      setTimeout(() => setShowFlash(false), 300)
      return entry
    },
    [saveVersion],
  )

  // Auto-snapshot on tab navigation
  useEffect(() => {
    if (!activeTab || !prevTabRef.current) {
      prevTabRef.current = activeTab
      return
    }
    if (activeTab !== prevTabRef.current && hasData) {
      // Auto-snapshot with tab context label
      saveVersion(`Auto: ${prevTabRef.current} tab`)
    }
    prevTabRef.current = activeTab
    // Only trigger on activeTab change, not on saveVersion reference changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, hasData])

  // Revert to a version (with confirmation dialog)
  const handleRevertRequest = useCallback(
    (entry: VersionEntry) => {
      setPendingRevert(entry)
    },
    [],
  )

  const confirmRevert = useCallback(() => {
    if (!pendingRevert) return
    setRevertingId(pendingRevert.id)
    const entry = pendingRevert
    setPendingRevert(null)
    // Brief delay for visual feedback
    setTimeout(() => {
      onRevert(entry.snapshot)
      setRevertingId(null)
      setIsOpen(false)
    }, 400)
  }, [pendingRevert, onRevert])

  // Delete a version
  const handleDelete = useCallback((id: string) => {
    setStore(prev => ({
      ...prev,
      versions: prev.versions.filter(v => v.id !== id),
    }))
  }, [])

  const versionCount = store.versions.length

  return (
    <>
      {/* Snapshot flash overlay -- brief white flash for camera effect */}
      {showFlash && (
        <div
          className="fixed inset-0 z-[100] bg-white pointer-events-none snapshot-flash-anim"
          aria-hidden="true"
        />
      )}

      {/* History + Save buttons */}
      <div className="flex items-center gap-1.5">
        {/* Save version button */}
        <button
          onClick={() => saveWithFlash()}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-border hover:text-text-primary active:scale-95',
            'transition-all duration-150',
          )}
          title="Save current state as version"
        >
          <Camera className="size-4" />
          <span className="hidden sm:inline">Snapshot</span>
        </button>

        {/* History button */}
        <button
          onClick={() => setIsOpen(true)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-border hover:text-text-primary active:scale-95',
            'transition-all duration-150',
          )}
          title="View version history"
        >
          <History className="size-4" />
          {versionCount > 0 && (
            <span className="inline-flex items-center justify-center size-4 rounded-full bg-gold/15 text-gold text-[9px] font-bold min-h-0 min-w-0">
              {versionCount}
            </span>
          )}
        </button>
      </div>

      {/* Version history panel */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-[80] bg-black/50"
            onClick={() => setIsOpen(false)}
          />

          {/* Panel */}
          <div
            className={cn(
              'fixed z-[81] bg-bg-secondary border border-border shadow-xl',
              // Mobile: bottom sheet
              'inset-x-0 bottom-0 rounded-t-2xl max-h-[75vh]',
              // Desktop: side panel
              'md:inset-auto md:top-16 md:right-4 md:w-[380px] md:max-h-[calc(100vh-100px)] md:rounded-xl',
            )}
          >
            {/* Drag handle (mobile) */}
            <div className="flex justify-center pt-3 pb-1 md:hidden">
              <div className="w-10 h-1 rounded-full bg-text-muted" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 className="text-base font-bold text-text-primary m-0 flex items-center gap-2">
                <Film size={16} className="text-gold" />
                Version History
              </h3>
              <button
                onClick={() => setIsOpen(false)}
                className="size-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Version list -- film strip style */}
            <div className="overflow-y-auto max-h-[calc(75vh-80px)] md:max-h-[calc(100vh-180px)] p-3 space-y-2">
              {versionCount === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <Film size={32} className="text-text-muted/30 mb-2" />
                  <p className="text-sm text-text-muted m-0">No versions saved</p>
                  <p className="text-xs text-text-muted/60 m-0 mt-1">
                    Click &ldquo;Snapshot&rdquo; to save the current state.
                    Versions are also created automatically when you switch tabs.
                  </p>
                </div>
              ) : (
                /* Reverse order: latest first */
                [...store.versions].reverse().map((entry, index) => {
                  const isLatest = index === 0
                  const isReverting = revertingId === entry.id
                  const isAutoSnapshot = entry.label.startsWith('Auto:')

                  return (
                    <div
                      key={entry.id}
                      className={cn(
                        'relative rounded-lg border bg-bg-tertiary/50 overflow-hidden',
                        'transition-all duration-200',
                        isLatest ? 'border-gold/30' : 'border-border/50',
                        isReverting && 'opacity-60 scale-[0.98]',
                      )}
                    >
                      {/* Film frame number */}
                      <div className="absolute top-0 left-0 px-1.5 py-0.5 text-[8px] font-mono font-bold text-text-muted/40 bg-bg-primary/50 rounded-br flex items-center gap-1">
                        #{store.versions.length - index}
                        {isAutoSnapshot && (
                          <span className="text-text-muted/30">auto</span>
                        )}
                      </div>

                      <div className="px-4 py-3 pt-5">
                        {/* Header row */}
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-text-primary truncate">
                                {entry.label}
                              </span>
                              {isLatest && (
                                <span className="shrink-0 text-[8px] uppercase tracking-wider font-bold text-gold bg-gold/10 px-1.5 py-0.5 rounded">
                                  Latest
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-text-muted mt-0.5 m-0">
                              {entry.summary}
                            </p>
                          </div>

                          <div className="flex items-center gap-1 shrink-0">
                            {/* Revert button */}
                            {!isLatest && (
                              <button
                                onClick={() => handleRevertRequest(entry)}
                                disabled={revertingId !== null}
                                className={cn(
                                  'flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium min-h-[44px]',
                                  'bg-gold/10 text-gold border border-gold/20',
                                  'hover:bg-gold/20 active:scale-95 transition-all',
                                  revertingId !== null && 'opacity-50 cursor-not-allowed',
                                )}
                              >
                                {isReverting ? (
                                  <Loader2 size={12} className="animate-spin" />
                                ) : (
                                  <RotateCcw size={12} />
                                )}
                                Revert
                              </button>
                            )}

                            {/* Delete button -- 44px min touch target */}
                            <button
                              onClick={() => handleDelete(entry.id)}
                              className={cn(
                                'flex items-center justify-center size-9 min-h-[44px] min-w-[44px] rounded-lg',
                                'text-text-muted/50 hover:text-danger hover:bg-danger/10',
                                'transition-colors active:scale-95',
                              )}
                              aria-label="Delete version"
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>

                        {/* Meta row */}
                        <div className="flex items-center gap-3 mt-2 text-[10px] text-text-muted">
                          <span>{formatTime(entry.createdAt)}</span>
                          <span>{entry.snapshot.rooms.length} rooms</span>
                          <span>{entry.snapshot.puzzles.length} puzzles</span>
                          <span>{entry.snapshot.agents.length} agents</span>
                        </div>
                      </div>
                    </div>
                  )
                })
              )}
            </div>

            {/* Footer */}
            {versionCount > 0 && (
              <div className="px-4 py-2 border-t border-border/50 text-[10px] text-text-muted flex items-center justify-between">
                <span>
                  {versionCount} version{versionCount !== 1 ? 's' : ''} (max {store.maxVersions})
                </span>
                <span className="text-text-muted/50">Stored locally</span>
              </div>
            )}
          </div>
        </>
      )}

      {/* Revert confirmation dialog */}
      {pendingRevert && (
        <RevertConfirmDialog
          versionLabel={pendingRevert.label}
          onConfirm={confirmRevert}
          onCancel={() => setPendingRevert(null)}
        />
      )}
    </>
  )
}
