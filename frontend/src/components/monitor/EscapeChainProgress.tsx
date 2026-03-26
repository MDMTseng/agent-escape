/**
 * EscapeChainProgress -- visual escape chain progress bar and checklist.
 *
 * Shows the escape chain as a horizontal segmented bar with color-coded states:
 *   - Solved: green (#3fb950 / success)
 *   - Active: gold (#e3b341) with pulse animation
 *   - Pending: gray (#30363d / border)
 *
 * Below the bar, an expandable checklist shows step details. Clicking a solved
 * step reveals which agent solved it and at what tick.
 *
 * Mobile-first: compact bar (~56px collapsed), full-width, touch-friendly
 * checklist rows (48px+), inline expand for solved step detail.
 */

import { useState, useCallback } from 'react'
import { useEscapeChain, useSolvedStepCount } from '@/stores/gameStore'
import type { EscapeChainStep } from '@/types/game'
import { cn } from '@/lib/utils'
import {
  ChevronDown,
  CheckCircle2,
  Circle,
  Zap,
  User,
  Clock,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Segment bar -- one colored segment per chain step
// ---------------------------------------------------------------------------

function SegmentBar({ steps }: { steps: EscapeChainStep[] }) {
  if (steps.length === 0) return null

  return (
    <div
      className="flex gap-0.5 w-full h-2.5 md:h-3 rounded-full overflow-hidden"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={steps.length}
      aria-valuenow={steps.filter((s) => s.status === 'solved').length}
      aria-label="Escape chain progress"
    >
      {steps.map((step) => (
        <div
          key={step.step}
          className={cn(
            'flex-1 rounded-sm transition-colors duration-300',
            step.status === 'solved' && 'bg-success',
            step.status === 'active' && 'bg-gold animate-active-pulse',
            step.status === 'pending' && 'bg-border',
          )}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Checklist row -- one row per step, with expandable solved detail
// ---------------------------------------------------------------------------

interface ChecklistRowProps {
  step: EscapeChainStep
  isExpanded: boolean
  onToggle: () => void
}

function ChecklistRow({ step, isExpanded, onToggle }: ChecklistRowProps) {
  const isSolved = step.status === 'solved'
  const isActive = step.status === 'active'

  return (
    <div
      className={cn(
        'border-b border-border/50 last:border-b-0',
        isActive && 'bg-gold/5',
      )}
    >
      {/* Main row -- tappable, 48px min height for touch targets */}
      <button
        type="button"
        onClick={onToggle}
        disabled={!isSolved}
        className={cn(
          'flex items-center gap-3 w-full min-h-[48px] px-3 py-2 text-left',
          'transition-colors duration-150',
          isSolved && 'active:bg-bg-tertiary/50 cursor-pointer',
          !isSolved && 'cursor-default',
        )}
        aria-expanded={isSolved ? isExpanded : undefined}
      >
        {/* Status icon */}
        <span className="shrink-0 flex items-center justify-center w-6 h-6">
          {isSolved && <CheckCircle2 size={18} className="text-success" />}
          {isActive && <Zap size={18} className="text-gold animate-active-pulse" />}
          {step.status === 'pending' && <Circle size={18} className="text-text-muted" />}
        </span>

        {/* Step number + description */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'text-xs font-mono tabular-nums shrink-0',
                isSolved && 'text-success',
                isActive && 'text-gold',
                step.status === 'pending' && 'text-text-muted',
              )}
            >
              #{step.step}
            </span>
            <span
              className={cn(
                'text-sm truncate',
                isSolved && 'text-text-primary',
                isActive && 'text-text-primary',
                step.status === 'pending' && 'text-text-secondary',
              )}
            >
              {step.description}
            </span>
          </div>
          {/* Action badge */}
          <span
            className={cn(
              'inline-block text-xs mt-0.5 px-1.5 py-0.5 rounded',
              isSolved && 'bg-success/10 text-success',
              isActive && 'bg-gold/10 text-gold',
              step.status === 'pending' && 'bg-bg-tertiary text-text-muted',
            )}
          >
            {step.action} {step.target}
          </span>
        </div>

        {/* Expand indicator for solved steps */}
        {isSolved && (
          <ChevronDown
            size={16}
            className={cn(
              'shrink-0 text-text-muted transition-transform duration-200',
              isExpanded && 'rotate-180',
            )}
          />
        )}
      </button>

      {/* Expanded solved detail -- inline, not a tooltip */}
      {isSolved && isExpanded && (
        <div className="px-3 pb-3 pl-12 flex flex-col gap-1 text-sm animate-in slide-in-from-top-1 duration-150">
          {step.solved_by && (
            <div className="flex items-center gap-2 text-text-secondary">
              <User size={14} className="text-success shrink-0" />
              <span>
                Solved by{' '}
                <span className="text-text-primary font-medium">
                  {step.solved_by}
                </span>
              </span>
            </div>
          )}
          {step.solved_at != null && (
            <div className="flex items-center gap-2 text-text-secondary">
              <Clock size={14} className="text-gold shrink-0" />
              <span>
                At tick{' '}
                <span className="text-text-primary font-mono tabular-nums">
                  {step.solved_at}
                </span>
              </span>
            </div>
          )}
          {/* Room info */}
          <div className="flex items-center gap-2 text-text-muted text-xs mt-0.5">
            Room: {step.room}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function EscapeChainProgress() {
  const escapeChain = useEscapeChain()
  const solvedCount = useSolvedStepCount()
  const totalSteps = escapeChain.length

  // Checklist visibility -- collapsed by default on mobile
  const [isChecklistOpen, setIsChecklistOpen] = useState(false)

  // Track which solved step is expanded for detail view
  const [expandedStep, setExpandedStep] = useState<number | null>(null)

  const toggleChecklist = useCallback(() => {
    setIsChecklistOpen((prev) => !prev)
  }, [])

  const toggleStepDetail = useCallback((stepNum: number) => {
    setExpandedStep((prev) => (prev === stepNum ? null : stepNum))
  }, [])

  // Don't render if no chain data yet
  if (totalSteps === 0) return null

  const progressPercent = Math.round((solvedCount / totalSteps) * 100)

  return (
    <section
      className="shrink-0 border-b border-border bg-bg-secondary"
      aria-label="Escape chain progress"
    >
      {/* Compact bar area -- always visible */}
      <button
        type="button"
        onClick={toggleChecklist}
        className={cn(
          'flex items-center gap-3 w-full px-3 py-2.5 md:px-4',
          'active:bg-bg-tertiary/30 transition-colors duration-150',
          'cursor-pointer select-none',
          'min-h-[48px]',
        )}
        aria-expanded={isChecklistOpen}
        aria-controls="escape-chain-checklist"
      >
        {/* Progress counter */}
        <div className="shrink-0 flex items-baseline gap-1">
          <span className="text-lg font-bold tabular-nums text-text-primary">
            {solvedCount}
          </span>
          <span className="text-sm text-text-muted">/</span>
          <span className="text-sm tabular-nums text-text-muted">
            {totalSteps}
          </span>
        </div>

        {/* Segmented bar -- takes remaining width */}
        <div className="flex-1 min-w-0">
          <SegmentBar steps={escapeChain} />
          {/* Percentage label on desktop */}
          <span className="hidden md:block text-xs text-text-muted mt-1">
            {progressPercent}% complete
          </span>
        </div>

        {/* Chevron toggle */}
        <ChevronDown
          size={18}
          className={cn(
            'shrink-0 text-text-muted transition-transform duration-200',
            isChecklistOpen && 'rotate-180',
          )}
        />
      </button>

      {/* Expandable checklist */}
      {isChecklistOpen && (
        <div
          id="escape-chain-checklist"
          className={cn(
            'border-t border-border/50',
            'max-h-[50vh] overflow-y-auto overscroll-contain',
            'animate-in slide-in-from-top-2 duration-200',
          )}
        >
          {escapeChain.map((step) => (
            <ChecklistRow
              key={step.step}
              step={step}
              isExpanded={expandedStep === step.step}
              onToggle={() => toggleStepDetail(step.step)}
            />
          ))}
        </div>
      )}
    </section>
  )
}
