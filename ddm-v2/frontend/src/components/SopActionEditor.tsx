import { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { updateSopActions } from '@/api/sop'
import type { SOPAction, SOPVersion } from '@/api/types'

// ─── Drag-and-drop reorder helpers ───────────────────────────────────────────

function reorder<T>(list: T[], from: number, to: number): T[] {
  const result = [...list]
  const [moved] = result.splice(from, 1)
  result.splice(to, 0, moved)
  return result
}

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
  onDragStart: (i: number) => void
  onDragOver: (i: number) => void
  onDrop: () => void
}

function ActionRow({
  action,
  index,
  isDragging,
  onDragStart,
  onDragOver,
  onDrop,
}: ActionRowProps) {
  return (
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
      <td className="px-3 py-2 text-sm text-gray-100 max-w-[280px] truncate">
        {action.description}
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
            <span className="rounded bg-purple-900/60 px-1.5 py-0.5 text-[10px] text-purple-300">SIMO</span>
          )}
          {action.glove_type && (
            <span className="rounded bg-blue-900/60 px-1.5 py-0.5 text-[10px] text-blue-300">
              {action.glove_type}
            </span>
          )}
        </div>
      </td>
    </tr>
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

  const canEdit = sop.status === 'Draft'

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

  const handleSave = useCallback(() => {
    if (!sop.id) return
    mutation.mutate(localActions)
  }, [mutation, localActions, sop.id])

  const handleDiscard = useCallback(() => {
    setLocalActions(sop.actions)
    setIsDirty(false)
  }, [sop.actions])

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
                onDragStart={handleDragStart}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
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
    </section>
  )
}
