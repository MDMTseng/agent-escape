import { useState, useEffect, useCallback } from "react"

type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error"

interface HealthCheckResult {
  status: ConnectionStatus
  lastChecked: Date | null
  data: Record<string, unknown> | null
  error: string | null
  retry: () => void
}

export function useHealthCheck(intervalMs = 10000): HealthCheckResult {
  const [status, setStatus] = useState<ConnectionStatus>("connecting")
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const check = useCallback(async () => {
    try {
      setStatus((prev) => (prev === "disconnected" || prev === "error" ? "connecting" : prev))
      const res = await fetch("/api/state", { signal: AbortSignal.timeout(5000) })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setStatus("connected")
      setError(null)
    } catch (err) {
      setStatus("error")
      setError(err instanceof Error ? err.message : "Unknown error")
      setData(null)
    } finally {
      setLastChecked(new Date())
    }
  }, [])

  useEffect(() => {
    check()
    const id = setInterval(check, intervalMs)
    return () => clearInterval(id)
  }, [check, intervalMs])

  return { status, lastChecked, data, error, retry: check }
}
