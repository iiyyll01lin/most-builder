/**
 * useTelemetry.ts — Phase 7: IoT WebSocket telemetry hook + event bus
 *
 * Architecture (zero-re-render design):
 *
 *   ┌─────────────────────────────────────────────────────────────────────┐
 *   │  WebSocket  →  _telemetryBus.emit(stationId, event)                 │
 *   │                        │                                            │
 *   │  WorkstationNode.useEffect subscribes once on mount                 │
 *   │    → writes flashRef.current = { startMs, colorHex }               │
 *   │    → NO setState, NO React render                                   │
 *   │                        │                                            │
 *   │  WorkstationNode.useFrame reads flashRef every RAF tick             │
 *   │    → mutates mat.emissive / mat.emissiveIntensity directly          │
 *   │    → GPU sees it; React reconciler never does                       │
 *   └─────────────────────────────────────────────────────────────────────┘
 *
 * Public API:
 *   - `telemetryBus`      — module-level EventEmitter: subscribe/unsubscribe/emit
 *   - `useTelemetry()`    — React hook that opens the WebSocket and pumps events
 *                           into the bus.  Call once at the top of the Digital
 *                           Twin tree.  Returns connection status for the UI.
 */

import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '@/store/authStore'

// ─── Telemetry event shape (matches backend JSON) ────────────────────────────

export interface TelemetryEvent {
  station_id: string
  line_id: string
  event_type: string
  timestamp: string
  [key: string]: unknown
}

// ─── Micro event-bus (no external library needed) ────────────────────────────

type TelemetryListener = (event: TelemetryEvent) => void

class TelemetryBus {
  private readonly _listeners = new Map<string, Set<TelemetryListener>>()

  /** Subscribe to events for a specific station_id.  Returns an unsubscribe fn. */
  subscribe(stationId: string, fn: TelemetryListener): () => void {
    if (!this._listeners.has(stationId)) {
      this._listeners.set(stationId, new Set())
    }
    this._listeners.get(stationId)!.add(fn)
    return () => this._listeners.get(stationId)?.delete(fn)
  }

  /** Broadcast an event to all subscribers of that stationId. */
  emit(event: TelemetryEvent): void {
    this._listeners.get(event.station_id)?.forEach((fn) => fn(event))
  }
}

/** Singleton event bus — import this in WorkstationNode to subscribe. */
export const telemetryBus = new TelemetryBus()

// ─── Connection status ────────────────────────────────────────────────────────

export type TelemetryStatus = 'connecting' | 'connected' | 'disconnected' | 'disabled'

// ─── useTelemetry hook ────────────────────────────────────────────────────────

const WS_RECONNECT_MS = 4_000

/**
 * Opens a WebSocket connection to `/api/v1/telemetry/stream?token=<jwt>` and
 * forwards each JSON message to `telemetryBus`.
 *
 * Re-renders are limited to connection status transitions only — not per-message.
 */
export function useTelemetry(): TelemetryStatus {
  const token = useAuthStore((s) => s.token)
  const [status, setStatus] = useState<TelemetryStatus>(token ? 'connecting' : 'disabled')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    if (!token) {
      setStatus('disabled')
      return
    }

    const connect = () => {
      if (!mountedRef.current) return

      // Build WebSocket URL — same host, ws(s) scheme, token as query param.
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${window.location.host}/api/v1/telemetry/stream?token=${encodeURIComponent(token)}`

      setStatus('connecting')
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        if (mountedRef.current) setStatus('connected')
      }

      ws.onmessage = (evt) => {
        try {
          const event: TelemetryEvent = JSON.parse(evt.data as string)
          // Skip pong frames (no station_id)
          if (event.station_id) {
            telemetryBus.emit(event)
          }
        } catch {
          // Malformed message — silently drop
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setStatus('disconnected')
        // Auto-reconnect with fixed back-off
        reconnectTimerRef.current = setTimeout(connect, WS_RECONNECT_MS)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.onclose = null  // prevent reconnect on intentional close
        wsRef.current.close()
      }
    }
  }, [token])

  return status
}
