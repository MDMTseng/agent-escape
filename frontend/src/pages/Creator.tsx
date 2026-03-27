import { useState, useEffect, useCallback, useRef } from 'react'
import {
  BookOpen, Sparkles, Loader2,
  Castle, Rocket, Skull, Users, AlertCircle
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { RoomsTab } from '@/components/creator/RoomsTab'
import { PuzzlesTab } from '@/components/creator/PuzzlesTab'
import { AgentsTab } from '@/components/creator/AgentsTab'
import { ValidateTab } from '@/components/creator/ValidateTab'
import { SceneExportImport } from '@/components/creator/SceneExportImport'
import { VersionHistory } from '@/components/creator/VersionHistory'
import type { AgentItem, AgentRelationship } from '@/components/creator/AgentsTab'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ThemeData {
  rooms: { name: string; desc: string }[]
  characters: { name: string; desc: string; trait: string }[]
}

interface WorldBible {
  theme: string
  premise: string
  difficulty: number
  characters: { name: string; desc: string; trait?: string }[]
  inciting_incident: string
}

/** Shared state for the Scene Creator (passed between tabs) */
export interface SceneCreatorState {
  theme: string
  premise: string
  difficulty: number
  worldBible: WorldBible | null
  rooms: RoomNode[]
  doors: DoorEdge[]
  puzzles: PuzzleItem[]
  agents: AgentItem[]
  relationships: AgentRelationship[]
}

export interface RoomNode {
  id: string
  name: string
  description: string
  entities: string[]
  x: number
  y: number
}

export interface DoorEdge {
  id: string
  sourceRoomId: string
  targetRoomId: string
  locked: boolean
  label: string
}

export interface PuzzleItem {
  id: string
  name: string
  type: string
  roomId: string
  requiredItems: string[]
  dependsOn: string[]
  description: string
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const TABS = ['Story', 'Rooms', 'Puzzles', 'Agents', 'Validate'] as const
type TabName = typeof TABS[number]

const THEME_ICONS: Record<string, React.ReactNode> = {
  gothic_manor: <Castle className="size-6" />,
  sci_fi_lab: <Rocket className="size-6" />,
  ancient_tomb: <Skull className="size-6" />,
}

const THEME_LABELS: Record<string, string> = {
  gothic_manor: 'Gothic Manor',
  sci_fi_lab: 'Sci-Fi Lab',
  ancient_tomb: 'Ancient Tomb',
}

const THEME_DESCRIPTIONS: Record<string, string> = {
  gothic_manor: 'Dark corridors, hidden passages, and aristocratic secrets',
  sci_fi_lab: 'Malfunctioning AI, sealed bulkheads, and cosmic mysteries',
  ancient_tomb: 'Cryptic hieroglyphs, deadly traps, and forgotten treasures',
}

const THEME_ACCENTS: Record<string, string> = {
  gothic_manor: 'border-purple-500/40 bg-purple-500/5',
  sci_fi_lab: 'border-blue-500/40 bg-blue-500/5',
  ancient_tomb: 'border-amber-500/40 bg-amber-500/5',
}

const THEME_ACCENT_SELECTED: Record<string, string> = {
  gothic_manor: 'border-purple-400 bg-purple-500/15 ring-2 ring-purple-500/30',
  sci_fi_lab: 'border-blue-400 bg-blue-500/15 ring-2 ring-blue-500/30',
  ancient_tomb: 'border-amber-400 bg-amber-500/15 ring-2 ring-amber-500/30',
}

const DIFFICULTY_LABELS = ['', 'Easy', 'Normal', 'Hard', 'Expert', 'Nightmare']
const DIFFICULTY_COLORS = ['', 'text-green-400', 'text-blue-400', 'text-gold', 'text-orange-400', 'text-danger']

/* ------------------------------------------------------------------ */
/*  Generation loading messages                                        */
/* ------------------------------------------------------------------ */

const GENERATION_MESSAGES = [
  'Weaving the narrative threads...',
  'Building the world bible...',
  'Crafting character backstories...',
  'Designing the inciting incident...',
  'Connecting plot elements...',
  'Breathing life into the story...',
]

/* ------------------------------------------------------------------ */
/*  Story Tab Component                                                */
/* ------------------------------------------------------------------ */

function StoryTab({
  sceneState,
  setSceneState,
}: {
  sceneState: SceneCreatorState
  setSceneState: React.Dispatch<React.SetStateAction<SceneCreatorState>>
}) {
  const [themes, setThemes] = useState<Record<string, ThemeData>>({})
  const [loadingThemes, setLoadingThemes] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [genMsgIndex, setGenMsgIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // Fetch themes from API
  useEffect(() => {
    async function fetchThemes() {
      try {
        const res = await fetch('/api/themes')
        if (!res.ok) throw new Error(`Server error (${res.status})`)
        const data = await res.json()
        setThemes(data.themes ?? {})
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load themes')
      } finally {
        setLoadingThemes(false)
      }
    }
    fetchThemes()
  }, [])

  // Cycle generation messages
  useEffect(() => {
    if (!generating) return
    const interval = setInterval(() => {
      setGenMsgIndex(i => (i + 1) % GENERATION_MESSAGES.length)
    }, 2200)
    return () => clearInterval(interval)
  }, [generating])

  const handleGenerate = useCallback(async () => {
    if (!sceneState.premise.trim()) {
      setError('Please enter a premise for your story')
      return
    }
    setGenerating(true)
    setError(null)
    setGenMsgIndex(0)

    try {
      const res = await fetch('/api/generate-story', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: sceneState.theme,
          premise: sceneState.premise,
          difficulty: sceneState.difficulty,
          num_characters: 3,
        }),
      })
      if (!res.ok) throw new Error(`Server error (${res.status})`)
      const data = await res.json()
      if (data.error) throw new Error(data.error)

      setSceneState(prev => ({
        ...prev,
        worldBible: {
          theme: data.world_bible?.theme ?? sceneState.theme,
          premise: data.world_bible?.premise ?? sceneState.premise,
          difficulty: data.world_bible?.difficulty ?? sceneState.difficulty,
          characters: data.world_bible?.characters ?? [],
          inciting_incident: data.world_bible?.inciting_incident ?? '',
        },
      }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }, [sceneState.theme, sceneState.premise, sceneState.difficulty, setSceneState])

  const themeKeys = Object.keys(themes).length > 0
    ? Object.keys(themes)
    : ['gothic_manor', 'sci_fi_lab', 'ancient_tomb']

  return (
    <div className="space-y-6">
      {/* --- Theme Selector --- */}
      <section>
        <h3 className="text-text-primary font-semibold text-base mb-3">Choose a Theme</h3>

        {loadingThemes ? (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-28 rounded-xl bg-bg-tertiary animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {themeKeys.map(key => {
              const isSelected = sceneState.theme === key
              const themeData = themes[key]
              return (
                <button
                  key={key}
                  onClick={() => setSceneState(prev => ({ ...prev, theme: key }))}
                  className={cn(
                    'flex flex-col items-start gap-2 p-4 rounded-xl border transition-all text-left',
                    'min-h-[80px] active:scale-[0.98]',
                    isSelected
                      ? THEME_ACCENT_SELECTED[key] ?? 'border-gold bg-gold/10 ring-2 ring-gold/30'
                      : THEME_ACCENTS[key] ?? 'border-border bg-bg-secondary hover:border-text-muted',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className={isSelected ? 'text-text-primary' : 'text-text-secondary'}>
                      {THEME_ICONS[key] ?? <BookOpen className="size-6" />}
                    </span>
                    <span className={cn(
                      'font-semibold text-sm',
                      isSelected ? 'text-text-primary' : 'text-text-secondary',
                    )}>
                      {THEME_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </span>
                  </div>
                  <p className="text-text-muted text-xs leading-relaxed">
                    {THEME_DESCRIPTIONS[key] ?? `${themeData?.rooms?.length ?? '?'} rooms available`}
                  </p>
                  {themeData && (
                    <div className="flex items-center gap-2 text-[10px] text-text-muted mt-auto">
                      <span>{themeData.rooms.length} rooms</span>
                      <span className="text-text-muted/40">|</span>
                      <span>{themeData.characters.length} characters</span>
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* --- Premise Text Area --- */}
      <section>
        <label htmlFor="premise" className="block text-text-primary font-semibold text-base mb-2">
          Story Premise
        </label>
        <p className="text-text-muted text-xs mb-2">
          Describe the backstory seed. What happened? Why are they trapped?
        </p>
        <textarea
          id="premise"
          value={sceneState.premise}
          onChange={e => setSceneState(prev => ({ ...prev, premise: e.target.value }))}
          placeholder="The old lighthouse keeper vanished three days ago. When rescuers arrived, they found the door sealed from the inside and strange symbols carved into the walls..."
          rows={4}
          className={cn(
            'w-full rounded-xl border border-border bg-bg-secondary px-4 py-3',
            'text-text-primary text-sm placeholder:text-text-muted/60',
            'focus:outline-none focus:ring-2 focus:ring-gold/30 focus:border-gold/50',
            'resize-y min-h-[100px]',
          )}
        />
      </section>

      {/* --- Difficulty Slider --- */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <label htmlFor="difficulty" className="text-text-primary font-semibold text-base">
            Difficulty
          </label>
          <span className={cn('text-sm font-medium', DIFFICULTY_COLORS[sceneState.difficulty])}>
            {DIFFICULTY_LABELS[sceneState.difficulty]}
          </span>
        </div>

        {/* Custom slider with visual markers */}
        <div className="relative px-1">
          <input
            id="difficulty"
            type="range"
            min={1}
            max={5}
            step={1}
            value={sceneState.difficulty}
            onChange={e => setSceneState(prev => ({
              ...prev,
              difficulty: Number(e.target.value),
            }))}
            className="w-full h-12 appearance-none bg-transparent cursor-pointer touch-pan-x
              [&::-webkit-slider-runnable-track]:h-2 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-bg-tertiary
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-7 [&::-webkit-slider-thumb]:h-7 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-gold [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-gold-bright [&::-webkit-slider-thumb]:-mt-2.5 [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:shadow-gold/20
              [&::-moz-range-track]:h-2 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-bg-tertiary
              [&::-moz-range-thumb]:w-7 [&::-moz-range-thumb]:h-7 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-gold [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-gold-bright"
          />
          {/* Dot markers under the track */}
          <div className="flex justify-between px-[2px] -mt-1">
            {[1, 2, 3, 4, 5].map(level => (
              <div
                key={level}
                className={cn(
                  'size-2 rounded-full transition-colors',
                  level <= sceneState.difficulty ? 'bg-gold/60' : 'bg-bg-tertiary',
                )}
              />
            ))}
          </div>
        </div>
      </section>

      {/* --- Error display --- */}
      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl bg-danger/10 border border-danger/20">
          <AlertCircle className="size-4 text-danger shrink-0 mt-0.5" />
          <p className="text-danger text-sm">{error}</p>
        </div>
      )}

      {/* --- Generate Button --- */}
      <section>
        <Button
          onClick={handleGenerate}
          disabled={generating || !sceneState.premise.trim()}
          className="w-full h-14 text-base font-semibold gap-2 bg-gold hover:bg-gold-bright text-bg-primary disabled:opacity-40"
        >
          {generating ? (
            <>
              <Loader2 className="size-5 animate-spin" />
              {GENERATION_MESSAGES[genMsgIndex]}
            </>
          ) : (
            <>
              <Sparkles className="size-5" />
              Generate World Bible
            </>
          )}
        </Button>
      </section>

      {/* --- Generated World Bible Display --- */}
      {sceneState.worldBible && !generating && (
        <section className="animate-card-in">
          <WorldBibleCard bible={sceneState.worldBible} />
        </section>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  World Bible result card                                            */
/* ------------------------------------------------------------------ */

function WorldBibleCard({ bible }: { bible: WorldBible }) {
  return (
    <div className="rounded-xl border border-gold/20 bg-gradient-to-b from-gold/5 to-transparent overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gold/10 flex items-center gap-2">
        <BookOpen className="size-5 text-gold" />
        <h3 className="text-gold font-semibold">World Bible</h3>
        <span className="ml-auto text-text-muted text-xs">
          {THEME_LABELS[bible.theme] ?? bible.theme}
        </span>
      </div>

      <div className="p-4 space-y-4">
        {/* Setting / Inciting Incident */}
        {bible.inciting_incident && (
          <div>
            <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-1">
              Inciting Incident
            </h4>
            <p className="text-text-primary text-sm leading-relaxed">
              {bible.inciting_incident}
            </p>
          </div>
        )}

        {/* Characters */}
        {bible.characters && bible.characters.length > 0 && (
          <div>
            <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-2">
              Characters
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {bible.characters.map((char, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 p-3 rounded-lg bg-bg-tertiary/50 border border-border/50"
                >
                  <div className="size-8 rounded-full bg-gold/10 flex items-center justify-center shrink-0 mt-0.5">
                    <Users className="size-4 text-gold/60" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-text-primary text-sm font-medium truncate">
                      {typeof char === 'string' ? char : char.name}
                    </p>
                    {typeof char !== 'string' && char.desc && (
                      <p className="text-text-muted text-xs mt-0.5 line-clamp-2">
                        {char.desc}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Premise recap */}
        <div>
          <h4 className="text-text-secondary text-xs font-semibold uppercase tracking-wider mb-1">
            Premise
          </h4>
          <p className="text-text-muted text-sm leading-relaxed italic">
            &ldquo;{bible.premise}&rdquo;
          </p>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Placeholder tab content                                            */
/* ------------------------------------------------------------------ */

function PlaceholderTab({ name }: { name: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="size-16 rounded-full bg-bg-tertiary flex items-center justify-center mb-4">
        <BookOpen className="size-7 text-text-muted" />
      </div>
      <h3 className="text-text-secondary font-semibold mb-1">{name}</h3>
      <p className="text-text-muted text-sm max-w-xs">
        This tab is coming soon. Complete the Story tab first to unlock world-building tools.
      </p>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main Scene Creator Page                                            */
/* ------------------------------------------------------------------ */

export default function Creator() {
  const [activeTab, setActiveTab] = useState<TabName>('Story')
  const tabsRef = useRef<HTMLDivElement>(null)

  // Shared scene state across tabs
  const [sceneState, setSceneState] = useState<SceneCreatorState>({
    theme: 'gothic_manor',
    premise: '',
    difficulty: 3,
    worldBible: null,
    rooms: [],
    doors: [],
    puzzles: [],
    agents: [],
    relationships: [],
  })

  // Scroll active tab into view on mobile
  useEffect(() => {
    if (!tabsRef.current) return
    const activeBtn = tabsRef.current.querySelector('[data-active="true"]')
    if (activeBtn) {
      activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
    }
  }, [activeTab])

  return (
    <div className="flex flex-col min-h-full">
      {/* Page header */}
      <div className="px-4 pt-4 pb-2 md:px-6 md:pt-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-gold font-bold tracking-tight">Scene Creator</h1>
            <p className="text-text-secondary text-sm mt-0.5">
              Build your escape room step by step
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            {/* Version history controls (P3-004) */}
            <VersionHistory
              sceneState={sceneState}
              onRevert={(version) => setSceneState(version)}
            />
            {/* Export/Import controls (P3-003) */}
            <SceneExportImport
              sceneState={sceneState}
              onImport={(imported) => setSceneState(imported)}
            />
          </div>
        </div>
      </div>

      {/* Tab bar — horizontally scrollable on mobile */}
      <div className="sticky top-0 z-30 bg-bg-primary border-b border-border">
        <div
          ref={tabsRef}
          className="flex overflow-x-auto scrollbar-none px-4 md:px-6 gap-1"
          role="tablist"
        >
          {TABS.map((tab, index) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === tab}
              data-active={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap',
                'border-b-2 transition-colors min-h-[44px]',
                activeTab === tab
                  ? 'border-gold text-gold'
                  : 'border-transparent text-text-muted hover:text-text-secondary',
              )}
            >
              <span className="text-xs text-text-muted/60">{index + 1}.</span>
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 px-4 py-4 pb-20 md:px-6 md:pb-6">
        {activeTab === 'Story' && (
          <StoryTab sceneState={sceneState} setSceneState={setSceneState} />
        )}
        {activeTab === 'Rooms' && (
          <RoomsTab sceneState={sceneState} setSceneState={setSceneState} />
        )}
        {activeTab === 'Puzzles' && (
          <PuzzlesTab sceneState={sceneState} setSceneState={setSceneState} />
        )}
        {activeTab === 'Agents' && (
          <AgentsTab sceneState={sceneState} setSceneState={setSceneState} />
        )}
        {activeTab === 'Validate' && (
          <ValidateTab sceneState={sceneState} setSceneState={setSceneState} />
        )}
      </div>
    </div>
  )
}
