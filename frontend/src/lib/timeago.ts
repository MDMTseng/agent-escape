/**
 * Converts an ISO date string to a human-readable relative time string.
 * e.g. "2 hours ago", "3 days ago", "just now"
 */
export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return 'never'

  const date = new Date(dateStr)
  const now = new Date()
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return 'just now'
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    return `${m}m ago`
  }
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600)
    return `${h}h ago`
  }
  if (seconds < 604800) {
    const d = Math.floor(seconds / 86400)
    return `${d}d ago`
  }
  // Older than a week: show short date
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
