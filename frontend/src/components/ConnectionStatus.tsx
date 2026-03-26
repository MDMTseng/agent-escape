import { useHealthCheck } from '@/hooks/useHealthCheck'
import { cn } from '@/lib/utils'

const statusConfig = {
  connecting: { label: 'Connecting...', dotClass: 'bg-warning animate-status-pulse' },
  connected: { label: 'Connected', dotClass: 'bg-success' },
  disconnected: { label: 'Disconnected', dotClass: 'bg-text-muted' },
  error: { label: 'Connection Error', dotClass: 'bg-danger' },
} as const

export function ConnectionStatus() {
  const { status, error, retry } = useHealthCheck()
  const config = statusConfig[status]

  return (
    <button
      onClick={retry}
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-lg',
        'bg-bg-secondary border border-border',
        'text-sm text-text-secondary hover:text-text-primary',
        'transition-colors cursor-pointer',
      )}
      title={error ? `Error: ${error}. Tap to retry.` : 'Tap to refresh connection status'}
    >
      <span
        className={cn('inline-block w-2.5 h-2.5 rounded-full', config.dotClass)}
        aria-hidden="true"
      />
      <span>{config.label}</span>
    </button>
  )
}
