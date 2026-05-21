import { useEffect, useRef, useState } from "react"

export type WsStatus = "connecting" | "open" | "reconnecting" | "closed"

interface Options {
  /** Called for each text message. */
  onMessage: (data: string) => void
  /** Backoff schedule (ms). Last value repeats after exhausting. */
  backoffMs?: number[]
  /** Disable reconnect entirely. */
  disabled?: boolean
}

/**
 * WebSocket with exponential backoff reconnect and explicit status.
 *
 * Returns the current status; consumers usually render a small badge.
 * Tears down cleanly on unmount and url change.
 */
export function useReconnectingWs(url: string | null, opts: Options): WsStatus {
  const [status, setStatus] = useState<WsStatus>("closed")
  // Keep onMessage in a ref so changing parent state doesn't reconnect us.
  const onMessageRef = useRef(opts.onMessage)
  onMessageRef.current = opts.onMessage

  const backoff = opts.backoffMs ?? [1000, 2000, 5000, 10000, 30000]

  useEffect(() => {
    if (!url || opts.disabled) {
      setStatus("closed")
      return
    }

    let ws: WebSocket | null = null
    let attempt = 0
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (stopped) return
      setStatus(attempt === 0 ? "connecting" : "reconnecting")
      try {
        ws = new WebSocket(url)
      } catch {
        scheduleReconnect()
        return
      }
      ws.onopen = () => {
        attempt = 0
        setStatus("open")
      }
      ws.onmessage = (ev) => {
        onMessageRef.current(typeof ev.data === "string" ? ev.data : "")
      }
      ws.onclose = () => {
        if (stopped) return
        scheduleReconnect()
      }
      ws.onerror = () => {
        // Let onclose fire and re-schedule.
      }
    }

    const scheduleReconnect = () => {
      if (stopped) return
      const delay = backoff[Math.min(attempt, backoff.length - 1)]
      attempt++
      setStatus("reconnecting")
      timer = setTimeout(connect, delay)
    }

    connect()

    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
      if (ws && ws.readyState <= WebSocket.OPEN) ws.close()
      setStatus("closed")
    }
  }, [url, opts.disabled])

  return status
}
