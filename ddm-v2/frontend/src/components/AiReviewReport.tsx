/**
 * AiReviewReport — side-drawer displaying the structured conflict audit
 * produced by the SOP Conflict Resolution Copilot backend.
 *
 * Props:
 *   isOpen            — controls drawer visibility
 *   onClose           — callback to close the drawer
 *   isLoading         — shows a skeleton while the AI call is in-flight
 *   summary           — one-line banner text (e.g. "3 conflicts detected")
 *   conflicts         — the Conflict[] list from SopReviewResponse
 *   highlightedIds    — set of action IDs currently highlighted in the parent
 *   onHoverConflict   — called with a Set<string> of action IDs on mouse-enter
 *   onLeaveConflict   — called on mouse-leave to clear highlights
 */

import type { SopConflict, ConflictSeverity } from '@/api/ai'

interface AiReviewReportProps {
  isOpen: boolean
  onClose: () => void
  isLoading: boolean
  summary?: string
  conflicts: SopConflict[]
  onHoverConflict?: (ids: Set<string>) => void
  onLeaveConflict?: () => void
}

// ─── Severity styling helpers ─────────────────────────────────────────────────

function severityBadge(s: ConflictSeverity) {
  switch (s) {
    case 'High':
      return 'bg-red-900/70 text-red-200 border-red-700'
    case 'Medium':
      return 'bg-amber-900/70 text-amber-200 border-amber-700'
    case 'Low':
      return 'bg-blue-900/60 text-blue-200 border-blue-700'
  }
}

function severityCard(s: ConflictSeverity) {
  switch (s) {
    case 'High':
      return 'border-red-700/60 bg-red-950/30'
    case 'Medium':
      return 'border-amber-600/50 bg-amber-950/25'
    case 'Low':
      return 'border-blue-700/40 bg-blue-950/20'
  }
}

function severityIcon(s: ConflictSeverity) {
  switch (s) {
    case 'High':
      return '🔴'
    case 'Medium':
      return '🟡'
    case 'Low':
      return '🔵'
  }
}

// ─── Skeleton loader ──────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-xl border border-gray-700 bg-gray-800/40 p-4 space-y-2">
          <div className="h-3 w-24 rounded bg-gray-700" />
          <div className="h-3 w-full rounded bg-gray-700" />
          <div className="h-3 w-5/6 rounded bg-gray-700" />
          <div className="h-3 w-3/4 rounded bg-gray-700 mt-2" />
        </div>
      ))}
    </div>
  )
}

// ─── Conflict card ────────────────────────────────────────────────────────────

function ConflictCard({
  conflict,
  index,
  onMouseEnter,
  onMouseLeave,
}: {
  conflict: SopConflict
  index: number
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  return (
    <div
      className={[
        'rounded-xl border p-4 space-y-2 transition-all duration-150',
        severityCard(conflict.severity),
        'hover:ring-1 hover:ring-white/10 cursor-default',
      ].join(' ')}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span className="text-base leading-none">{severityIcon(conflict.severity)}</span>
        <span
          className={[
            'rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
            severityBadge(conflict.severity),
          ].join(' ')}
        >
          {conflict.severity}
        </span>
        <span className="text-xs text-gray-500">Conflict #{index + 1}</span>
      </div>

      {/* Description */}
      <p className="text-xs text-gray-200 leading-relaxed">{conflict.description}</p>

      {/* Related action IDs */}
      {conflict.related_action_ids.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {conflict.related_action_ids.map((id) => (
            <span
              key={id}
              className="rounded bg-gray-700/70 px-1.5 py-0.5 font-mono text-[9px] text-gray-300"
            >
              {id}
            </span>
          ))}
        </div>
      )}

      {/* Suggestion */}
      <div className="rounded-lg bg-gray-800/60 border border-gray-600/40 p-2.5">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">
          💡 Suggestion
        </p>
        <p className="text-xs text-gray-300 leading-relaxed">{conflict.suggestion}</p>
      </div>
    </div>
  )
}

// ─── Main drawer component ────────────────────────────────────────────────────

export function AiReviewReport({
  isOpen,
  onClose,
  isLoading,
  summary,
  conflicts,
  onHoverConflict,
  onLeaveConflict,
}: AiReviewReportProps) {
  if (!isOpen) return null

  const highCount = conflicts.filter((c) => c.severity === 'High').length
  const medCount = conflicts.filter((c) => c.severity === 'Medium').length
  const lowCount = conflicts.filter((c) => c.severity === 'Low').length

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="AI Audit Report"
        className={[
          'fixed right-0 top-0 z-50 h-full w-full max-w-md',
          'flex flex-col bg-gray-900 border-l border-gray-700 shadow-2xl',
          'transition-transform duration-300',
        ].join(' ')}
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-gray-700 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🤖</span>
            <div>
              <h2 className="text-sm font-semibold text-gray-100">AI Audit Report</h2>
              <p className="text-[10px] text-gray-500">SOP Conflict Resolution Copilot</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-gray-500 hover:bg-gray-700 hover:text-gray-200 transition-colors"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {/* Summary bar */}
        {!isLoading && summary && (
          <div
            className={[
              'mx-4 mt-4 rounded-lg border px-3 py-2 text-xs font-medium',
              conflicts.length === 0
                ? 'border-green-700/50 bg-green-950/30 text-green-300'
                : highCount > 0
                  ? 'border-red-700/50 bg-red-950/30 text-red-300'
                  : 'border-amber-700/50 bg-amber-950/30 text-amber-300',
            ].join(' ')}
          >
            {summary}
          </div>
        )}

        {/* Severity counts */}
        {!isLoading && conflicts.length > 0 && (
          <div className="mx-4 mt-2 flex gap-2">
            {highCount > 0 && (
              <span className="rounded border border-red-700 bg-red-900/40 px-2 py-0.5 text-[10px] text-red-200">
                {highCount} High
              </span>
            )}
            {medCount > 0 && (
              <span className="rounded border border-amber-700 bg-amber-900/40 px-2 py-0.5 text-[10px] text-amber-200">
                {medCount} Medium
              </span>
            )}
            {lowCount > 0 && (
              <span className="rounded border border-blue-700 bg-blue-900/40 px-2 py-0.5 text-[10px] text-blue-200">
                {lowCount} Low
              </span>
            )}
          </div>
        )}

        {/* Hover hint */}
        {!isLoading && conflicts.length > 0 && onHoverConflict && (
          <p className="mx-4 mt-2 text-[10px] text-gray-600 italic">
            Hover a card to highlight related actions in the SOP table.
          </p>
        )}

        {/* Scrollable conflict list */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {isLoading ? (
            <Skeleton />
          ) : conflicts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <span className="text-4xl">✅</span>
              <p className="text-sm font-medium text-green-400">No conflicts detected</p>
              <p className="text-xs text-gray-500 max-w-xs">
                The SOP sequence appears logically consistent. All physical
                prerequisites were satisfied in the correct order.
              </p>
            </div>
          ) : (
            conflicts.map((conflict, i) => (
              <ConflictCard
                key={i}
                conflict={conflict}
                index={i}
                onMouseEnter={() => onHoverConflict?.(new Set(conflict.related_action_ids))}
                onMouseLeave={() => onLeaveConflict?.()}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-700 px-5 py-3 text-[10px] text-gray-600">
          Findings are AI-generated. Always verify before modifying production SOPs.
        </div>
      </aside>
    </>
  )
}
