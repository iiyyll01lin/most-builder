/**
 * Factory Manager BI Dashboard — "Chat-to-Chart" Generative BI interface.
 *
 * The user types natural language questions at the bottom. The AI backend
 * translates them into SQL, executes them, and returns a structured payload
 * that is rendered here as dynamic Recharts visualisations.
 */

import { useRef, useState } from 'react'
import { apiClient } from '@/api/client'
import type { BIPayload } from '@/components/bi/DynamicChartRenderer'
import { DynamicChartRenderer } from '@/components/bi/DynamicChartRenderer'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ChatEntry {
  id: number
  kind: 'user' | 'ai'
  text?: string
  payload?: BIPayload
  error?: string
  isLoading?: boolean
}

// ─── Example prompt suggestions ───────────────────────────────────────────────

const SUGGESTIONS = [
  'Show total TMU by station',
  'How many SOP versions does each project have?',
  'What proportion of actions are CTQ?',
  'List all projects with their SKUs',
]

// ─── SQL disclosure toggle ────────────────────────────────────────────────────

function SqlDisclosure({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((p) => !p)}
        className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
      >
        {open ? '▾ Hide SQL' : '▸ Show generated SQL'}
      </button>
      {open && (
        <pre className="mt-1 overflow-x-auto rounded bg-gray-950 p-3 text-xs text-emerald-400 border border-gray-800">
          {sql}
        </pre>
      )}
    </div>
  )
}

// ─── Individual message bubble ────────────────────────────────────────────────

function MessageBubble({ entry }: { entry: ChatEntry }) {
  if (entry.kind === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-2xl rounded-tr-sm bg-cyan-700/30 border border-cyan-700/50 px-4 py-2 text-sm text-cyan-100">
          {entry.text}
        </div>
      </div>
    )
  }

  // AI response
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] w-full">
        {/* Insight text */}
        {entry.isLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-500 italic py-2">
            <span className="inline-block w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
            Analysing your question…
          </div>
        )}
        {entry.error && (
          <div className="rounded-lg border border-red-900/50 bg-red-950/40 px-4 py-3 text-sm text-red-400">
            {entry.error}
          </div>
        )}
        {entry.payload && (
          <div className="space-y-3">
            {/* Insight */}
            <p className="text-sm text-gray-300 leading-relaxed">{entry.payload.insight}</p>
            {/* Chart */}
            <div className="rounded-xl border border-gray-700 bg-gray-900/70 p-4">
              <DynamicChartRenderer payload={entry.payload} />
            </div>
            {/* SQL disclosure */}
            {entry.payload.sql_query && <SqlDisclosure sql={entry.payload.sql_query} />}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function FactoryManagerDashboard() {
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const feedRef = useRef<HTMLDivElement>(null)
  const idRef = useRef(0)

  const nextId = () => ++idRef.current

  const scrollToBottom = () => {
    setTimeout(() => {
      feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
    }, 60)
  }

  const handleSubmit = async (query: string) => {
    const q = query.trim()
    if (!q || busy) return

    setInput('')
    setBusy(true)

    const userId = nextId()
    const aiId = nextId()

    setEntries((prev) => [
      ...prev,
      { id: userId, kind: 'user', text: q },
      { id: aiId, kind: 'ai', isLoading: true },
    ])
    scrollToBottom()

    try {
      const { data } = await apiClient.post<BIPayload>('/bi/query', { query: q })
      setEntries((prev) =>
        prev.map((e) => (e.id === aiId ? { ...e, isLoading: false, payload: data } : e))
      )
    } catch (err: unknown) {
      const message =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
            'An unexpected error occurred.')
          : 'An unexpected error occurred.'
      setEntries((prev) =>
        prev.map((e) => (e.id === aiId ? { ...e, isLoading: false, error: message } : e))
      )
    } finally {
      setBusy(false)
      scrollToBottom()
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-56px)] bg-[#0a0e1a]">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-800 px-6 py-3 bg-gray-900/50">
        <h1 className="text-base font-semibold text-gray-100">
          Factory Manager AI
          <span className="ml-2 text-xs font-normal text-cyan-500 bg-cyan-900/30 rounded-full px-2 py-0.5">
            Chat-to-Chart BI
          </span>
        </h1>
        <p className="text-xs text-gray-600 mt-0.5">
          Ask natural language questions about your manufacturing data.
        </p>
      </div>

      {/* Message feed */}
      <div
        ref={feedRef}
        className="flex-1 overflow-y-auto px-6 py-4 space-y-5 scroll-smooth"
      >
        {entries.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-6 pb-16">
            <p className="text-gray-600 text-sm">Start by asking a question, or try a suggestion:</p>
            <div className="flex flex-wrap justify-center gap-2 max-w-xl">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSubmit(s)}
                  className="rounded-full border border-gray-700 bg-gray-800/60 px-4 py-1.5 text-xs text-gray-300 hover:border-cyan-600 hover:text-cyan-300 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {entries.map((e) => (
          <MessageBubble key={e.id} entry={e} />
        ))}
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 border-t border-gray-800 bg-gray-900/70 px-4 py-3">
        <form
          onSubmit={(ev) => {
            ev.preventDefault()
            handleSubmit(input)
          }}
          className="flex items-center gap-3"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
            placeholder="Ask a question about your factory data…"
            className="flex-1 rounded-xl border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:border-cyan-600 focus:outline-none disabled:opacity-50 transition-colors"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-xl bg-cyan-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-cyan-600 disabled:opacity-50 transition-colors"
          >
            {busy ? '…' : 'Ask'}
          </button>
        </form>
      </div>
    </div>
  )
}
