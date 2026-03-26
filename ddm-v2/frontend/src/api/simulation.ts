import { apiClient } from './client'
import type {
  LineBalanceRequest,
  AsyncJobResponse,
  SimProgressEvent,
} from './types'

export async function submitLineBalanceJob(
  payload: LineBalanceRequest,
): Promise<AsyncJobResponse> {
  const { data } = await apiClient.post<AsyncJobResponse>(
    '/simulation/line-balance/async',
    payload,
  )
  return data
}

/**
 * Connect to the simulation WebSocket and yield progress events.
 * The caller provides an `onEvent` callback invoked for every message.
 * Returns a cleanup function that closes the socket.
 */
export function connectSimulationWs(
  jobId: string,
  token: string,
  onEvent: (event: SimProgressEvent) => void,
  onError: (msg: string) => void,
): () => void {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsBase = import.meta.env.VITE_WS_BASE ?? `${wsProtocol}://${window.location.host}`
  const url = `${wsBase}/api/v1/simulation/ws/${jobId}?token=${encodeURIComponent(token)}`

  const ws = new WebSocket(url)

  ws.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data as string) as SimProgressEvent
      onEvent(event)
    } catch {
      // ignore malformed frames
    }
  }

  ws.onerror = () => {
    onError('WebSocket connection error. Simulation may have failed.')
  }

  ws.onclose = (ev) => {
    if (ev.code === 4001) onError('Authentication failed for simulation stream.')
    if (ev.code === 4004) onError('Simulation job not found.')
  }

  return () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close()
    }
  }
}
