import { useState, useCallback, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { updateSopActions } from '@/api/sop'
import { generateSopActions } from '@/api/ai'
import type { SOPAction, SOPVersion } from '@/api/types'

// ─── Drag-and-drop reorder helpers ───────────────────────────────────────────

function reorder<T>(list: T[], from: number, to: number): T[] {
  const result = [...list]
  const [moved] = result.splice(from, 1)
  result.splice(to, 0, moved)
  return result
}

// ─── Equipment-parameter tools (spec §工作表5) ────────────────────────────────
// These tools require the operator to record air pressure & force before use.
const EQUIPMENT_PARAM_TOOLS = new Set(['TP压合治具', '开机键锁附治具'])

const EQUIPMENT_PARAM_FIELDS: Array<{ key: string; label: string; placeholder: string }> = [
  { key: 'air_pressure_mpa', label: '气压值 (Mpa)', placeholder: 'e.g. 0.4' },
  { key: 'force_n_cm2', label: '压强值 (N/cm²)', placeholder: 'e.g. 50' },
]

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_STYLES = {
  Draft: 'bg-gray-700 text-gray-300',
  Reviewed: 'bg-blue-900 text-blue-300',
  Published: 'bg-green-900 text-green-300',
} as const

// ─── Action row ───────────────────────────────────────────────────────────────

interface ActionRowProps {
  action: SOPAction
  index: number
  isDragging: boolean
  canEdit: boolean
  onDragStart: (i: number) => void
  onDragOver: (i: number) => void
  onDrop: () => void
  onEquipmentParamsChange: (index: number, params: Record<string, string> | null) => void
}

function ActionRow({
  action,
  index,
  isDragging,
  canEdit,
  onDragStart,
  onDragOver,
  onDrop,
  onEquipmentParamsChange,
}: ActionRowProps) {
  const [showParams, setShowParams] = useState(false)
  const hasPrecautions = (action.precautions?.length ?? 0) > 0
  const needsEquipParams =
    canEdit && action.tool != null && EQUIPMENT_PARAM_TOOLS.has(action.tool)

  const currentParams: Record<string, string> = action.equipment_params ?? {}

  const handleParamChange = (key: string, val: string) => {
    const next = { ...currentParams, [key]: val }
    onEquipmentParamsChange(index, Object.values(next).some(Boolean) ? next : null)
  }

  return (
    <>
      <tr
        draggable
        onDragStart={() => onDragStart(index)}
        onDragOver={(e) => {
          e.preventDefault()
          onDragOver(index)
        }}
        onDrop={onDrop}
        className={[
          'group cursor-grab border-b border-gray-700/50 transition-colors active:cursor-grabbing',
          isDragging ? 'opacity-50 bg-cyan-900/20' : 'hover:bg-gray-800/50',
        ].join(' ')}
      >
        <td className="w-8 px-2 py-2 text-center text-xs text-gray-600 group-hover:text-gray-400 select-none">
          ⠿
        </td>
        <td className="px-3 py-2 text-xs text-gray-400">{index + 1}</td>
        <td className="px-3 py-2 text-xs font-mono text-cyan-300">{action.seq_type}</td>
        <td className="px-3 py-2 text-sm text-gray-100 max-w-[280px] break-words whitespace-normal">
          <div>{action.description}</div>
          {/* Precaution warnings — yellow inline alert per text */}
          {hasPrecautions && (
            <div className="mt-1 space-y-0.5">
              {action.precautions!.map((p, pi) => (
                <div
                  key={pi}
                  className="flex items-start gap-1 rounded bg-yellow-900/30 border border-yellow-700/40 px-1.5 py-0.5 text-[10px] text-yellow-300 leading-tight"
                  title="Auto-binding precaution"
                >
                  <span className="shrink-0 mt-px">⚠</span>
                  <span>{p}</span>
                </div>
              ))}
            </div>
          )}
        </td>
        <td className="px-3 py-2 text-xs text-amber-300 text-right">
          {action.seconds.toFixed(2)}s
        </td>
        <td className="px-3 py-2 text-xs text-gray-400 text-center">{action.tmu}</td>
        <td className="px-3 py-2">
          <div className="flex flex-wrap gap-1">
            {action.is_ctq && (
              <span className="rounded bg-red-900/60 px-1.5 py-0.5 text-[10px] text-red-300">CTQ</span>
            )}
            {action.is_simo && (
              <span
                className="rounded bg-purple-900/60 px-1.5 py-0.5 text-[10px] text-purple-300 cursor-help"
                title="SIMO (Simultaneous Motion) — time is parallelized; only the longest hand counts toward CT"
              >
                SIMO
              </span>
            )}
            {action.glove_type && (
              <span className="rounded bg-blue-900/60 px-1.5 py-0.5 text-[10px] text-blue-300">
                {action.glove_type}
              </span>
            )}
            {/* Equipment params toggle button */}
            {(needsEquipParams || action.equipment_params) && (
              <button
                onClick={(e) => { e.stopPropagation(); setShowParams((v) => !v) }}
                className={[
                  'rounded px-1.5 py-0.5 text-[10px] transition-colors',
                  showParams
                    ? 'bg-orange-700/80 text-orange-100'
                    : 'bg-orange-900/50 text-orange-300 hover:bg-orange-700/60',
                ].join(' ')}
                title="Equipment parameters (气压值 / 压强值)"
              >
                ⚙ Params
              </button>
            )}
          </div>
        </td>
      </tr>
      {/* Expandable equipment parameters editor row */}
      {showParams && (
        <tr className="border-b border-gray-700/30 bg-orange-950/10">
          <td colSpan={7} className="px-5 py-2">
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold text-orange-300 uppercase tracking-wide">
                Equipment Parameters — {action.tool}
              </p>
              <div className="flex flex-wrap gap-3">
                {EQUIPMENT_PARAM_FIELDS.map(({ key, label, placeholder }) => (
                  <label key={key} className="flex items-center gap-1.5 text-[11px] text-gray-300">
                    <span className="text-gray-400 whitespace-nowrap">{label}</span>
                    {canEdit ? (
                      <input
                        type="text"
                        value={currentParams[key] ?? ''}
                        placeholder={placeholder}
                        onChange={(e) => handleParamChange(key, e.target.value)}
                        className="w-24 rounded border border-gray-600 bg-gray-800 px-2 py-0.5 text-xs text-gray-100 focus:border-orange-500 focus:outline-none"
                      />
                    ) : (
                      <span className="rounded border border-gray-700 bg-gray-800/50 px-2 py-0.5 text-xs text-gray-200">
                        {currentParams[key] || '—'}
                      </span>
                    )}
                  </label>
                ))}
              </div>
              {canEdit && (
                <p className="text-[10px] text-gray-600">
                  Values saved automatically with the next "Save" operation.
                </p>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface SopActionEditorProps {
  sop: SOPVersion
  /** React Query cache key — used to write optimistic updates */
  queryKey: unknown[]
}

export function SopActionEditor({ sop, queryKey }: SopActionEditorProps) {
  const queryClient = useQueryClient()
  const [localActions, setLocalActions] = useState<SOPAction[]>(sop.actions)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const [showAiModal, setShowAiModal] = useState(false)
  const [aiInstruction, setAiInstruction] = useState('')

  const canEdit = sop.status === 'Draft'

  // ── AI Copilot mutation ────────────────────────────────────────────────────
  const aiMutation = useMutation({
    mutationFn: (instruction: string) =>
      generateSopActions({ instruction, project_id: sop.project_id }),
    onSuccess: (response) => {
      setLocalActions((prev) => [...prev, ...response.actions])
      setIsDirty(true)
      setShowAiModal(false)
      setAiInstruction('')
      toast.success(
        `✨ AI generated ${response.actions.length} action(s) — review and save when ready.`,
      )
    },
    onError: () => {
      toast.error('AI generation failed. Check your instruction and try again.')
    },
  })

  // ── Optimistic save mutation ───────────────────────────────────────────────
  const mutation = useMutation({
    mutationFn: (actions: SOPAction[]) =>
      updateSopActions(sop.id!, actions),

    onMutate: async (newActions) => {
      // Cancel in-flight refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey })

      // Snapshot previous value for rollback
      const previous = queryClient.getQueryData(queryKey)

      // Optimistically update the cache
      queryClient.setQueryData(queryKey, (old: unknown) => {
        if (!old || typeof old !== 'object') return old
        // If the cached value is the SOP version directly
        const snap = old as SOPVersion
        return { ...snap, actions: newActions }
      })

      setIsDirty(false)
      return { previous }
    },

    onError: (_err, _newActions, context) => {
      // Roll back to snapshot
      if (context?.previous !== undefined) {
        queryClient.setQueryData(queryKey, context.previous)
        const prev = context.previous as { actions?: SOPAction[] }
        if (prev?.actions) setLocalActions(prev.actions)
      }
      setIsDirty(true)
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },

    onSuccess: (updated) => {
      setLocalActions(updated.actions)
      toast.success('SOP actions saved successfully')
    },
  })

  const handleDragStart = useCallback((i: number) => setDragIndex(i), [])
  const handleDragOver = useCallback((i: number) => setOverIndex(i), [])

  const handleDrop = useCallback(() => {
    if (dragIndex === null || overIndex === null || dragIndex === overIndex) {
      setDragIndex(null)
      setOverIndex(null)
      return
    }
    const reordered = reorder(localActions, dragIndex, overIndex)
    setLocalActions(reordered)
    setIsDirty(true)
    setDragIndex(null)
    setOverIndex(null)
  }, [dragIndex, overIndex, localActions])

  const handleEquipmentParamsChange = useCallback(
    (index: number, params: Record<string, string> | null) => {
      setLocalActions((prev) =>
        prev.map((a, i) => (i === index ? { ...a, equipment_params: params } : a)),
      )
      setIsDirty(true)
    },
    [],
  )

  const handleSave = useCallback(() => {
    if (!sop.id) return
    mutation.mutate(localActions)
  }, [mutation, localActions, sop.id])

  const handleDiscard = useCallback(() => {
    setLocalActions(sop.actions)
    setIsDirty(false)
  }, [sop.actions])

  // ── Data-loss prevention: warn before tab/window close with unsaved changes ─
  // This is a safety net for the "forgot to click Save" scenario described in
  // the Excel spec.  The browser's native confirm dialog is the only mechanism
  // that works reliably across all browsers for beforeunload events.
  useEffect(() => {
    if (!isDirty) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      // returnValue is required for legacy browser compatibility
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  return (
    <section className="space-y-3 rounded-2xl border border-gray-700 bg-gray-900/50 p-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-gray-100">
            SOP Actions
          </h2>
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              STATUS_STYLES[sop.status] ?? 'bg-gray-700 text-gray-300'
            }`}
          >
            {sop.status}
          </span>
          <span className="text-xs text-gray-500">v{sop.version_no}</span>
        </div>

        {canEdit && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowAiModal(true)}
              disabled={aiMutation.isPending}
              title="AI Auto-Generate SOP actions from natural language"
              className="rounded-lg border border-purple-700/60 bg-purple-900/30 px-3 py-1.5 text-xs text-purple-300 hover:bg-purple-800/40 transition-colors disabled:opacity-40"
            >
              ✨ AI
            </button>
            {isDirty && (
              <button
                onClick={handleDiscard}
                disabled={mutation.isPending}
                className="rounded-lg border border-gray-600 px-3 py-1.5 text-xs text-gray-400 hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                Discard
              </button>
            )}
            <button
              onClick={handleSave}
              disabled={!isDirty || mutation.isPending}
              className={[
                'rounded-lg px-4 py-1.5 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
                isDirty && !mutation.isPending
                  ? 'bg-cyan-600 text-white hover:bg-cyan-500'
                  : 'cursor-not-allowed bg-gray-700 text-gray-500',
              ].join(' ')}
            >
              {mutation.isPending ? 'Saving…' : `Save${isDirty ? ' *' : ''}`}
            </button>
          </div>
        )}
        {!canEdit && (
          <span className="text-xs text-gray-500">Read-only (not Draft)</span>
        )}
      </div>

      {isDirty && (
        <div className="rounded bg-amber-950/30 border border-amber-700/40 px-3 py-1.5 text-xs text-amber-300">
          Unsaved reorder — click Save to persist. UI already reflects new order (Optimistic UI).
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-700">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-gray-700 bg-gray-800/60 text-xs text-gray-400 uppercase tracking-wide">
              <th className="w-8 px-2 py-2" />
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2 text-right">Seconds</th>
              <th className="px-3 py-2 text-center">TMU</th>
              <th className="px-3 py-2">Flags</th>
            </tr>
          </thead>
          <tbody>
            {localActions.map((action, i) => (
              <ActionRow
                key={action.id ?? i}
                action={action}
                index={i}
                isDragging={dragIndex === i}
                canEdit={canEdit}
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onEquipmentParamsChange={handleEquipmentParamsChange}
              />
            ))}
            {localActions.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-xs text-gray-600">
                  No actions defined for this SOP version.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="text-right text-xs text-gray-600">
        {localActions.length} action{localActions.length !== 1 ? 's' : ''} ·{' '}
        Total CT:{' '}
        <span className="text-amber-300">
          {localActions.reduce((s, a) => s + a.seconds, 0).toFixed(2)}s
        </span>
      </p>

      {/* ── AI Copilot Modal ─────────────────────────────────────────────── */}
      {showAiModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ai-modal-title"
        >
          <div className="w-full max-w-lg rounded-2xl border border-purple-700/50 bg-gray-900 p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 id="ai-modal-title" className="text-base font-semibold text-purple-200">
                ✨ AI Auto-Generate SOP Actions
              </h3>
              <button
                onClick={() => { setShowAiModal(false); setAiInstruction('') }}
                disabled={aiMutation.isPending}
                aria-label="Close AI modal"
                className="text-lg text-gray-500 transition-colors hover:text-gray-300 disabled:opacity-40"
              >
                ✕
              </button>
            </div>

            <p className="mb-3 text-xs text-gray-400">
              Describe the manufacturing operation in plain language. The AI will convert it into
              structured MOST SOP actions with correct CTQ flags, required skills, and glove types.
              Generated actions will be appended for your review — save when satisfied.
            </p>

            <textarea
              value={aiInstruction}
              onChange={(e) => setAiInstruction(e.target.value)}
              disabled={aiMutation.isPending}
              placeholder="e.g. Assemble motherboard with 4 screws, then scan the barcode label"
              rows={4}
              className="mb-4 w-full resize-none rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-purple-500 focus:outline-none disabled:opacity-50"
            />

            {aiMutation.isPending && (
              <div className="mb-3 flex items-center gap-2 rounded border border-purple-700/30 bg-purple-900/30 px-3 py-2 text-xs text-purple-300">
                <span className="animate-spin inline-block">⟳</span>
                AI is analyzing SOP…
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setShowAiModal(false); setAiInstruction('') }}
                disabled={aiMutation.isPending}
                className="rounded-lg border border-gray-600 px-3 py-1.5 text-xs text-gray-400 transition-colors hover:bg-gray-800 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                onClick={() => aiMutation.mutate(aiInstruction)}
                disabled={!aiInstruction.trim() || aiMutation.isPending}
                className="rounded-lg bg-purple-700 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {aiMutation.isPending ? 'Generating…' : 'Generate Actions'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
