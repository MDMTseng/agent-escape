/**
 * SceneExportImport — export and import scene definitions as JSON files.
 *
 * Export: serialize scene data to JSON, trigger browser download.
 * Import: file upload, validate JSON schema, preview contents, create story.
 *
 * Visual aesthetic: "sealed case file" for export, "breaking the seal" for import.
 *
 * Mobile-first: bottom sheet for import preview, full-width buttons.
 */

import { useState, useCallback, useRef } from 'react'
import {
  Download,
  Upload,
  FileJson,
  X,
  Check,
  AlertCircle,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  Lock,
  Unlock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type {
  SceneCreatorState,
} from '@/pages/Creator'
// ---------------------------------------------------------------------------
// Export format — versioned envelope
// ---------------------------------------------------------------------------

interface SceneExportEnvelope {
  /** Format identifier */
  _format: 'agenttown_scene_v1'
  /** Export timestamp */
  exportedAt: string
  /** Scene data */
  scene: SceneCreatorState
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  summary: {
    theme: string
    premise: string
    roomCount: number
    doorCount: number
    puzzleCount: number
    agentCount: number
    hasWorldBible: boolean
  } | null
}

function validateSceneJSON(data: unknown): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!data || typeof data !== 'object') {
    return { valid: false, errors: ['File does not contain a valid JSON object'], warnings, summary: null }
  }

  const envelope = data as Record<string, unknown>

  // Check format identifier
  if (envelope._format !== 'agenttown_scene_v1') {
    errors.push('Missing or invalid format identifier (_format must be "agenttown_scene_v1")')
  }

  const scene = envelope.scene as Record<string, unknown> | undefined
  if (!scene || typeof scene !== 'object') {
    errors.push('Missing "scene" property in the export file')
    return { valid: false, errors, warnings, summary: null }
  }

  // Validate required fields
  if (typeof scene.theme !== 'string' || !scene.theme) {
    errors.push('Missing or invalid "theme" (must be a non-empty string)')
  }

  if (typeof scene.premise !== 'string') {
    warnings.push('Missing "premise" field')
  }

  if (typeof scene.difficulty !== 'number' || scene.difficulty < 1 || scene.difficulty > 5) {
    warnings.push('Difficulty should be a number between 1 and 5')
  }

  // Validate rooms
  const rooms = scene.rooms as unknown[]
  if (!Array.isArray(rooms)) {
    errors.push('Missing or invalid "rooms" (must be an array)')
  } else {
    for (let i = 0; i < rooms.length; i++) {
      const room = rooms[i] as Record<string, unknown>
      if (!room.id || !room.name) {
        errors.push(`Room at index ${i} is missing id or name`)
      }
    }
  }

  // Validate doors
  const doors = scene.doors as unknown[]
  if (!Array.isArray(doors)) {
    warnings.push('Missing "doors" array — no connections between rooms')
  }

  // Validate puzzles
  const puzzles = scene.puzzles as unknown[]
  if (!Array.isArray(puzzles)) {
    warnings.push('Missing "puzzles" array — no puzzles in the scene')
  }

  // Validate agents
  const agents = scene.agents as unknown[]
  if (!Array.isArray(agents)) {
    warnings.push('Missing "agents" array — no agents in the scene')
  }

  const summary = {
    theme: (scene.theme as string) || 'Unknown',
    premise: (scene.premise as string) || '',
    roomCount: Array.isArray(rooms) ? rooms.length : 0,
    doorCount: Array.isArray(doors) ? doors.length : 0,
    puzzleCount: Array.isArray(puzzles) ? puzzles.length : 0,
    agentCount: Array.isArray(agents) ? agents.length : 0,
    hasWorldBible: !!scene.worldBible,
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    summary,
  }
}

// ---------------------------------------------------------------------------
// Export handler
// ---------------------------------------------------------------------------

function exportScene(sceneState: SceneCreatorState) {
  const envelope: SceneExportEnvelope = {
    _format: 'agenttown_scene_v1',
    exportedAt: new Date().toISOString(),
    scene: sceneState,
  }

  const json = JSON.stringify(envelope, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)

  const safeName = (sceneState.worldBible?.theme || sceneState.theme || 'scene')
    .replace(/[^a-z0-9_-]/gi, '_')
    .toLowerCase()

  const a = document.createElement('a')
  a.href = url
  a.download = `agenttown_${safeName}_${Date.now()}.json`
  a.click()

  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Seal animation component
// ---------------------------------------------------------------------------

function SealAnimation({ phase }: { phase: 'sealing' | 'sealed' | 'breaking' }) {
  return (
    <div className="flex items-center justify-center py-4">
      <div
        className={cn(
          'relative size-16 rounded-full flex items-center justify-center',
          'transition-all duration-500',
          phase === 'sealing' && 'bg-gold/20 animate-seal-reveal',
          phase === 'sealed' && 'bg-gold/10 border-2 border-gold/40',
          phase === 'breaking' && 'bg-danger/10 border-2 border-danger/30',
        )}
      >
        {phase === 'sealing' && (
          <Lock className="size-6 text-gold animate-pulse" />
        )}
        {phase === 'sealed' && (
          <Check className="size-6 text-gold" />
        )}
        {phase === 'breaking' && (
          <Unlock className="size-6 text-amber-400" />
        )}
        {/* Glow ring */}
        <div
          className={cn(
            'absolute inset-[-4px] rounded-full border',
            phase === 'breaking' ? 'border-amber-400/30' : 'border-gold/20',
            (phase === 'sealing' || phase === 'breaking') && 'animate-active-pulse',
          )}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Import preview panel
// ---------------------------------------------------------------------------

function ImportPreview({
  validation,
  onConfirm,
  onCancel,
  importing,
}: {
  validation: ValidationResult
  onConfirm: () => void
  onCancel: () => void
  importing: boolean
}) {
  const { valid, errors, warnings, summary } = validation

  return (
    <div className="space-y-4">
      {/* Seal breaking animation */}
      <SealAnimation phase="breaking" />

      {/* Status header */}
      <div className="flex items-center gap-2 justify-center">
        {valid ? (
          <>
            <ShieldCheck className="size-5 text-success" />
            <span className="text-sm font-semibold text-success">Valid scene file</span>
          </>
        ) : (
          <>
            <ShieldAlert className="size-5 text-danger" />
            <span className="text-sm font-semibold text-danger">Invalid scene file</span>
          </>
        )}
      </div>

      {/* Summary card */}
      {summary && (
        <div className="bg-bg-tertiary/50 border border-border rounded-lg p-3 space-y-2">
          <div className="text-sm font-semibold text-text-primary">
            {summary.theme.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
          </div>
          {summary.premise && (
            <p className="text-xs text-text-secondary line-clamp-2 m-0">
              {summary.premise}
            </p>
          )}
          <div className="flex items-center gap-3 text-[11px] text-text-muted flex-wrap">
            <span>{summary.roomCount} room{summary.roomCount !== 1 ? 's' : ''}</span>
            <span>{summary.doorCount} door{summary.doorCount !== 1 ? 's' : ''}</span>
            <span>{summary.puzzleCount} puzzle{summary.puzzleCount !== 1 ? 's' : ''}</span>
            <span>{summary.agentCount} agent{summary.agentCount !== 1 ? 's' : ''}</span>
            {summary.hasWorldBible && (
              <span className="text-gold">World Bible included</span>
            )}
          </div>
        </div>
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <div className="space-y-1">
          {errors.map((err, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-danger">
              <AlertCircle className="size-3.5 mt-0.5 shrink-0" />
              <span>{err}</span>
            </div>
          ))}
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="space-y-1">
          {warnings.map((warn, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-warning">
              <AlertCircle className="size-3.5 mt-0.5 shrink-0" />
              <span>{warn}</span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2 pt-2">
        <button
          onClick={onConfirm}
          disabled={!valid || importing}
          className={cn(
            'w-full flex items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-semibold min-h-[48px]',
            'transition-all',
            valid
              ? 'bg-gold text-bg-primary hover:bg-gold-bright active:scale-[0.98]'
              : 'bg-bg-tertiary text-text-muted cursor-not-allowed',
            importing && 'opacity-60 cursor-not-allowed',
          )}
        >
          {importing ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Importing...
            </>
          ) : (
            <>
              <Upload className="size-4" />
              Import Scene
            </>
          )}
        </button>
        <button
          onClick={onCancel}
          disabled={importing}
          className="w-full flex items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-medium min-h-[48px] bg-bg-tertiary text-text-secondary hover:bg-border transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main SceneExportImport component
// ---------------------------------------------------------------------------

export function SceneExportImport({
  sceneState,
  onImport,
}: {
  sceneState: SceneCreatorState
  onImport: (imported: SceneCreatorState) => void
}) {
  const [showImportPanel, setShowImportPanel] = useState(false)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [parsedScene, setParsedScene] = useState<SceneCreatorState | null>(null)
  const [importing, setImporting] = useState(false)
  const [exportPhase, setExportPhase] = useState<'idle' | 'sealing' | 'sealed'>('idle')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Handle export with seal animation
  const handleExport = useCallback(() => {
    setExportPhase('sealing')
    setTimeout(() => {
      exportScene(sceneState)
      setExportPhase('sealed')
      setTimeout(() => setExportPhase('idle'), 1500)
    }, 700)
  }, [sceneState])

  // Handle file selection
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      try {
        const parsed = JSON.parse(event.target?.result as string)
        const result = validateSceneJSON(parsed)
        setValidation(result)
        if (result.valid && parsed.scene) {
          setParsedScene(parsed.scene as SceneCreatorState)
        }
        setShowImportPanel(true)
      } catch {
        setValidation({
          valid: false,
          errors: ['Failed to parse JSON — file may be corrupted or not valid JSON'],
          warnings: [],
          summary: null,
        })
        setShowImportPanel(true)
      }
    }
    reader.readAsText(file)

    // Reset input so same file can be selected again
    e.target.value = ''
  }, [])

  // Confirm import
  const handleConfirmImport = useCallback(() => {
    if (!parsedScene) return
    setImporting(true)
    // Brief delay for visual feedback
    setTimeout(() => {
      onImport(parsedScene)
      setImporting(false)
      setShowImportPanel(false)
      setValidation(null)
      setParsedScene(null)
    }, 500)
  }, [parsedScene, onImport])

  const handleCancelImport = useCallback(() => {
    setShowImportPanel(false)
    setValidation(null)
    setParsedScene(null)
  }, [])

  // Check if scene has enough data to be worth exporting
  const hasContent = sceneState.rooms.length > 0 || sceneState.theme !== ''

  return (
    <>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        onChange={handleFileSelect}
        className="hidden"
        aria-hidden="true"
      />

      {/* Export/Import buttons */}
      <div className="flex items-center gap-2">
        {/* Export button */}
        <button
          onClick={handleExport}
          disabled={!hasContent || exportPhase !== 'idle'}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'transition-all duration-200',
            exportPhase === 'sealed'
              ? 'bg-gold/10 text-gold border border-gold/30'
              : exportPhase === 'sealing'
              ? 'bg-gold/15 text-gold border border-gold/25'
              : hasContent
              ? 'bg-bg-tertiary text-text-secondary hover:bg-border hover:text-text-primary active:scale-95'
              : 'bg-bg-tertiary/50 text-text-muted cursor-not-allowed',
          )}
          title="Export scene as JSON"
        >
          {exportPhase === 'sealed' ? (
            <>
              <Check className="size-4" />
              <span className="hidden sm:inline">Exported</span>
            </>
          ) : exportPhase === 'sealing' ? (
            <>
              <Lock className="size-4 animate-pulse" />
              <span className="hidden sm:inline">Sealing...</span>
            </>
          ) : (
            <>
              <Download className="size-4" />
              <span className="hidden sm:inline">Export</span>
            </>
          )}
        </button>

        {/* Import button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium min-h-[44px]',
            'bg-bg-tertiary text-text-secondary',
            'hover:bg-border hover:text-text-primary active:scale-95',
            'transition-all duration-150',
          )}
          title="Import scene from JSON"
        >
          <Upload className="size-4" />
          <span className="hidden sm:inline">Import</span>
        </button>
      </div>

      {/* Import preview panel — bottom sheet (mobile) / centered dialog (desktop) */}
      {showImportPanel && validation && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-[80] bg-black/50"
            onClick={handleCancelImport}
          />

          {/* Panel */}
          <div
            className={cn(
              'fixed z-[81] bg-bg-secondary border border-border shadow-xl',
              // Mobile: bottom sheet
              'inset-x-0 bottom-0 rounded-t-2xl max-h-[80vh]',
              // Desktop: centered dialog
              'md:inset-auto md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2',
              'md:w-[420px] md:max-h-[70vh] md:rounded-xl',
            )}
          >
            {/* Drag handle (mobile) */}
            <div className="flex justify-center pt-3 pb-1 md:hidden">
              <div className="w-10 h-1 rounded-full bg-text-muted" />
            </div>

            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h3 className="text-base font-bold text-text-primary m-0 flex items-center gap-2">
                <FileJson size={16} className="text-gold" />
                Import Scene
              </h3>
              <button
                onClick={handleCancelImport}
                className="size-9 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full hover:bg-bg-tertiary text-text-secondary"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-4 py-4 overflow-y-auto max-h-[calc(80vh-80px)] md:max-h-[calc(70vh-80px)]">
              <ImportPreview
                validation={validation}
                onConfirm={handleConfirmImport}
                onCancel={handleCancelImport}
                importing={importing}
              />
            </div>
          </div>
        </>
      )}
    </>
  )
}
