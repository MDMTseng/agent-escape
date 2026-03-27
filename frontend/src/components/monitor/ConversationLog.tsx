/**
 * ConversationLog — dedicated panel showing all agent-to-agent conversations.
 *
 * Displays talk actions as a chat-style UI with speech bubbles.
 * Features:
 *  - Film-noir interrogation room aesthetic
 *  - Chat bubbles with agent name, alternating left/right alignment
 *  - Filter by agent pair (toggle chips)
 *  - Highlight conversations where clues or puzzle information were shared
 *  - Typewriter-style message reveal animation
 *  - Collapsible panel in the monitor page
 *
 * Mobile-first:
 *  - Full-width bubbles on mobile
 *  - Horizontally scrollable filter chips
 *  - Bottom sheet expansion on tap
 *  - 44px+ touch targets
 */

import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import {
  MessageCircle,
  ChevronDown,
  ChevronUp,
  Sparkles,
  X,
  Users,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useNarrativeEvents } from '@/stores/gameStore'
import type { NarrativeEntry } from '@/types/game'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConversationMessage {
  /** Unique key for React */
  id: string
  /** Tick this message occurred on */
  tick: number
  /** Client timestamp from the narrative entry */
  timestamp: number
  /** Speaker agent name */
  speaker: string
  /** Recipient agent name, or null if broadcast */
  recipient: string | null
  /** The spoken message content */
  message: string
  /** The room where the conversation took place */
  room: string
  /** Whether this message likely contains clue/puzzle info */
  containsClue: boolean
  /** Raw event description for fallback display */
  rawDescription: string
}

// ---------------------------------------------------------------------------
// Clue detection — keywords that suggest puzzle/clue exchange
// ---------------------------------------------------------------------------

const CLUE_KEYWORDS = [
  'key', 'lock', 'code', 'password', 'combination', 'clue', 'hint',
  'secret', 'hidden', 'found', 'discovered', 'lever', 'puzzle',
  'solved', 'open', 'unlock', 'examine', 'inspect', 'notice',
  'mechanism', 'switch', 'button', 'pattern', 'sequence', 'symbol',
  'inscription', 'note', 'document', 'map', 'safe', 'chest',
  'portal', 'passage', 'door', 'gate', 'chamber',
]

function detectClue(message: string): boolean {
  const lower = message.toLowerCase()
  return CLUE_KEYWORDS.some(kw => lower.includes(kw))
}

// ---------------------------------------------------------------------------
// Parse talk events from narrative entries
// ---------------------------------------------------------------------------

function parseTalkEvents(narrativeEvents: NarrativeEntry[]): ConversationMessage[] {
  const messages: ConversationMessage[] = []

  for (const entry of narrativeEvents) {
    for (const event of entry.events) {
      if (event.type !== 'talk') continue

      const desc = event.description
      let speaker = ''
      let recipient: string | null = null
      let message = ''

      // Format: 'Agent says to Target: "message"'
      const directedMatch = desc.match(/^(.+?) says to (.+?):\s*"(.+)"$/s)
      if (directedMatch) {
        speaker = directedMatch[1]
        recipient = directedMatch[2]
        message = directedMatch[3]
      } else {
        // Format: 'Agent says: "message"'
        const broadcastMatch = desc.match(/^(.+?) says:\s*"(.+)"$/s)
        if (broadcastMatch) {
          speaker = broadcastMatch[1]
          message = broadcastMatch[2]
        } else {
          // Fallback: show the whole description
          speaker = 'Unknown'
          message = desc
        }
      }

      messages.push({
        id: `${entry.tick}-${event.type}-${messages.length}`,
        tick: entry.tick,
        timestamp: entry.timestamp,
        speaker,
        recipient,
        message,
        room: event.room,
        containsClue: detectClue(message),
        rawDescription: desc,
      })
    }
  }

  return messages
}

// ---------------------------------------------------------------------------
// Agent avatar — deterministic color from name hash
// ---------------------------------------------------------------------------

const AVATAR_COLORS = [
  'from-amber-600 to-amber-800',
  'from-blue-600 to-blue-800',
  'from-emerald-600 to-emerald-800',
  'from-purple-600 to-purple-800',
  'from-rose-600 to-rose-800',
  'from-cyan-600 to-cyan-800',
  'from-orange-600 to-orange-800',
  'from-teal-600 to-teal-800',
]

function hashName(name: string): number {
  let h = 0
  for (let i = 0; i < name.length; i++) {
    h = ((h << 5) - h + name.charCodeAt(i)) | 0
  }
  return Math.abs(h)
}

function AgentAvatar({ name, size = 'md' }: { name: string; size?: 'sm' | 'md' }) {
  const colorIdx = hashName(name) % AVATAR_COLORS.length
  const initials = name
    .split(/\s+/)
    .map(w => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  const sizeClass = size === 'sm' ? 'size-7 text-[10px]' : 'size-9 text-xs'

  return (
    <div
      className={cn(
        'shrink-0 rounded-full bg-gradient-to-br flex items-center justify-center font-bold text-white/90',
        AVATAR_COLORS[colorIdx],
        sizeClass,
      )}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chat bubble — speech bubble with typewriter reveal
// ---------------------------------------------------------------------------

function ChatBubble({
  msg,
  isLeft,
  showTypewriter,
}: {
  msg: ConversationMessage
  isLeft: boolean
  showTypewriter: boolean
}) {
  const [revealed, setRevealed] = useState(!showTypewriter)
  const [charCount, setCharCount] = useState(showTypewriter ? 0 : msg.message.length)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Typewriter effect for newly appearing messages
  useEffect(() => {
    if (!showTypewriter || revealed) return

    const totalChars = msg.message.length
    const speed = Math.max(8, Math.min(30, 800 / totalChars)) // adaptive speed
    timerRef.current = setInterval(() => {
      setCharCount(prev => {
        if (prev >= totalChars) {
          if (timerRef.current) clearInterval(timerRef.current)
          setRevealed(true)
          return totalChars
        }
        return prev + 1
      })
    }, speed)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [showTypewriter, revealed, msg.message.length])

  const displayText = revealed ? msg.message : msg.message.slice(0, charCount)

  return (
    <div
      className={cn(
        'flex gap-2 max-w-[85%] md:max-w-[70%] animate-card-in',
        isLeft ? 'self-start' : 'self-end flex-row-reverse',
      )}
    >
      <AgentAvatar name={msg.speaker} />
      <div className="min-w-0 flex-1">
        {/* Speaker name + tick badge */}
        <div
          className={cn(
            'flex items-center gap-2 mb-1',
            isLeft ? '' : 'justify-end',
          )}
        >
          <span className="text-xs font-semibold text-text-secondary truncate">
            {msg.speaker}
          </span>
          {msg.recipient && (
            <>
              <span className="text-[10px] text-text-muted">to</span>
              <span className="text-xs font-medium text-text-muted truncate">
                {msg.recipient}
              </span>
            </>
          )}
          <span className="text-[10px] text-text-muted tabular-nums shrink-0">
            T{msg.tick}
          </span>
        </div>

        {/* Speech bubble */}
        <div
          className={cn(
            'relative rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed',
            'border',
            // Left bubbles: darker, incoming
            isLeft
              ? 'bg-bg-tertiary/80 border-border text-text-primary rounded-tl-sm'
              : 'bg-gold/[0.07] border-gold/20 text-text-primary rounded-tr-sm',
            // Clue highlight
            msg.containsClue && 'ring-1 ring-gold/30',
          )}
        >
          {/* Clue badge */}
          {msg.containsClue && (
            <span
              className={cn(
                'absolute -top-2 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider',
                'bg-gold/15 text-gold border border-gold/25',
                isLeft ? '-right-1' : '-left-1',
              )}
            >
              <Sparkles className="size-2.5 inline mr-0.5" />
              Clue
            </span>
          )}

          <span className="whitespace-pre-wrap break-words">
            &ldquo;{displayText}&rdquo;
          </span>
          {!revealed && (
            <span className="inline-block w-0.5 h-3.5 bg-gold/60 ml-0.5 animate-cursor-blink align-text-bottom" />
          )}
        </div>

        {/* Room label */}
        <div
          className={cn(
            'text-[10px] text-text-muted mt-1',
            isLeft ? '' : 'text-right',
          )}
        >
          {msg.room}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Agent pair filter chip
// ---------------------------------------------------------------------------

function FilterChip({
  label,
  active,
  onToggle,
}: {
  label: string
  active: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium',
        'transition-all duration-150 min-h-[36px]',
        'active:scale-95',
        active
          ? 'bg-gold/15 text-gold border border-gold/30'
          : 'bg-bg-tertiary text-text-muted border border-border hover:border-text-muted/30',
      )}
    >
      {label}
      {active && <X className="size-3" />}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyConversations() {
  return (
    <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
      <div className="size-14 rounded-full bg-emerald-500/10 flex items-center justify-center mb-3">
        <MessageCircle className="size-6 text-emerald-400/50" />
      </div>
      <p className="text-sm text-text-muted m-0">
        No conversations yet
      </p>
      <p className="text-xs text-text-muted/60 m-0 mt-1">
        Agent dialogue will appear here as they talk to each other
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main ConversationLog component
// ---------------------------------------------------------------------------

export function ConversationLog() {
  const narrativeEvents = useNarrativeEvents()
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedPair, setSelectedPair] = useState<string | null>(null)
  const [showCluesOnly, setShowCluesOnly] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const prevCountRef = useRef(0)

  // Parse all talk events from narrative history
  const allMessages = useMemo(
    () => parseTalkEvents(narrativeEvents),
    [narrativeEvents],
  )

  // Build unique agent pairs for filter chips
  const agentPairs = useMemo(() => {
    const pairSet = new Set<string>()
    for (const msg of allMessages) {
      if (msg.recipient) {
        // Normalize pair order alphabetically
        const pair = [msg.speaker, msg.recipient].sort().join(' & ')
        pairSet.add(pair)
      }
    }
    return Array.from(pairSet).sort()
  }, [allMessages])

  // Unique speakers for "all messages from agent" filter
  const speakers = useMemo(() => {
    const set = new Set<string>()
    for (const msg of allMessages) {
      set.add(msg.speaker)
    }
    return Array.from(set).sort()
  }, [allMessages])

  // Filter messages
  const filteredMessages = useMemo(() => {
    let msgs = allMessages

    if (selectedPair) {
      const pairAgents = selectedPair.split(' & ')
      if (pairAgents.length === 2) {
        msgs = msgs.filter(
          m =>
            (m.speaker === pairAgents[0] && m.recipient === pairAgents[1]) ||
            (m.speaker === pairAgents[1] && m.recipient === pairAgents[0]),
        )
      } else {
        // Single agent filter
        msgs = msgs.filter(m => m.speaker === selectedPair || m.recipient === selectedPair)
      }
    }

    if (showCluesOnly) {
      msgs = msgs.filter(m => m.containsClue)
    }

    return msgs
  }, [allMessages, selectedPair, showCluesOnly])

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (filteredMessages.length > prevCountRef.current && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
    prevCountRef.current = filteredMessages.length
  }, [filteredMessages.length])

  // Track which messages are "new" for typewriter effect
  const newMessageThreshold = useRef(allMessages.length)
  useEffect(() => {
    // Update threshold after a brief delay so current render sees them as new
    const timer = setTimeout(() => {
      newMessageThreshold.current = allMessages.length
    }, 2000)
    return () => clearTimeout(timer)
  }, [allMessages.length])

  // Build a set of known agent names for left/right alignment
  // First speaker encountered gets left alignment, alternating thereafter
  const agentSideMap = useMemo(() => {
    const map = new Map<string, 'left' | 'right'>()
    let nextSide: 'left' | 'right' = 'left'
    for (const msg of allMessages) {
      if (!map.has(msg.speaker)) {
        map.set(msg.speaker, nextSide)
        nextSide = nextSide === 'left' ? 'right' : 'left'
      }
    }
    return map
  }, [allMessages])

  const toggleExpanded = useCallback(() => setIsExpanded(v => !v), [])

  const messageCount = allMessages.length
  const clueCount = allMessages.filter(m => m.containsClue).length

  // If no talk events and not expanded, show a compact placeholder
  if (messageCount === 0 && !isExpanded) {
    return null // Don't render at all if there's nothing to show
  }

  return (
    <div className="shrink-0 border-t border-border bg-bg-primary">
      {/* Collapsed header bar — always visible, tappable */}
      <button
        onClick={toggleExpanded}
        className={cn(
          'w-full flex items-center justify-between px-3 py-2.5 md:px-4',
          'text-left transition-colors duration-150 min-h-[48px]',
          'hover:bg-bg-secondary/50 active:bg-bg-secondary',
        )}
      >
        <div className="flex items-center gap-2.5">
          <MessageCircle className="size-4 text-emerald-400" />
          <span className="text-sm font-semibold text-text-primary">
            Conversations
          </span>
          {messageCount > 0 && (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-400/15 text-emerald-400 tabular-nums">
              {messageCount}
            </span>
          )}
          {clueCount > 0 && (
            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-gold/15 text-gold tabular-nums">
              <Sparkles className="size-2.5" />
              {clueCount}
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronDown className="size-4 text-text-muted" />
        ) : (
          <ChevronUp className="size-4 text-text-muted" />
        )}
      </button>

      {/* Expanded panel */}
      {isExpanded && (
        <div
          className={cn(
            'border-t border-border',
            // Mobile: fixed height with scroll
            'h-[50vh] md:h-[40vh]',
            'flex flex-col',
          )}
        >
          {/* Filter bar — horizontally scrollable chips */}
          {(agentPairs.length > 0 || speakers.length > 0) && (
            <div className="shrink-0 px-3 py-2 border-b border-border/50 flex items-center gap-2 overflow-x-auto scrollbar-none">
              <Users className="size-3.5 text-text-muted shrink-0" />

              {/* "All" chip */}
              <FilterChip
                label="All"
                active={selectedPair === null && !showCluesOnly}
                onToggle={() => {
                  setSelectedPair(null)
                  setShowCluesOnly(false)
                }}
              />

              {/* Clues only */}
              <FilterChip
                label="Clues only"
                active={showCluesOnly}
                onToggle={() => setShowCluesOnly(v => !v)}
              />

              {/* Agent pair chips */}
              {agentPairs.map(pair => (
                <FilterChip
                  key={pair}
                  label={pair}
                  active={selectedPair === pair}
                  onToggle={() =>
                    setSelectedPair(prev => (prev === pair ? null : pair))
                  }
                />
              ))}

              {/* Individual agent chips (only if no pairs exist yet) */}
              {agentPairs.length === 0 &&
                speakers.map(name => (
                  <FilterChip
                    key={name}
                    label={name}
                    active={selectedPair === name}
                    onToggle={() =>
                      setSelectedPair(prev => (prev === name ? null : name))
                    }
                  />
                ))}
            </div>
          )}

          {/* Conversation feed */}
          <div
            ref={scrollRef}
            className="flex-1 min-h-0 overflow-y-auto px-3 py-3 md:px-4 space-y-3"
            style={{
              // Film-noir interrogation room vibe: subtle vignette
              background:
                'radial-gradient(ellipse at center, transparent 60%, rgba(0,0,0,0.15) 100%)',
            }}
          >
            {filteredMessages.length === 0 ? (
              <EmptyConversations />
            ) : (
              <>
                {filteredMessages.map((msg, idx) => {
                  const isLeft = agentSideMap.get(msg.speaker) === 'left'
                  const isNew = idx >= newMessageThreshold.current
                  return (
                    <ChatBubble
                      key={msg.id}
                      msg={msg}
                      isLeft={isLeft}
                      showTypewriter={isNew}
                    />
                  )
                })}
              </>
            )}
          </div>

          {/* Summary footer */}
          {filteredMessages.length > 0 && (
            <div className="shrink-0 px-3 py-1.5 border-t border-border/50 text-[10px] text-text-muted flex items-center justify-between">
              <span>
                {filteredMessages.length} message{filteredMessages.length !== 1 ? 's' : ''}
                {selectedPair ? ` (${selectedPair})` : ''}
              </span>
              {clueCount > 0 && (
                <span className="text-gold/70">
                  {clueCount} potential clue{clueCount !== 1 ? 's' : ''} exchanged
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
