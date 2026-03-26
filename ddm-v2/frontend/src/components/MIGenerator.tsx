import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { validateMiNaming } from '@/api/most'

// ─── Field definitions (order matches the backend position field) ─────────────

const MI_FIELDS = [
  {
    key: 'model5',
    label: 'Model5',
    required: true,
    placeholder: 'HDL50',
    description: '5-digit model code',
  },
  {
    key: 'status',
    label: 'Status',
    required: true,
    placeholder: 'ASSY',
    description: 'SOP status (ASSY / PACK)',
  },
  {
    key: 'pick_type',
    label: 'PickType',
    required: true,
    placeholder: 'FPT',
    description: 'Pick type (FPT / MPT)',
  },
  {
    key: 'process',
    label: 'Process',
    required: true,
    placeholder: 'ASSY',
    description: 'Process (ASSY/PACK/SUB/SMT)',
  },
  {
    key: 'cfi',
    label: 'CFI',
    required: false,
    placeholder: '',
    description: 'CFI code (optional)',
  },
  {
    key: 'line',
    label: 'Line',
    required: true,
    placeholder: 'L1',
    description: 'Production line',
  },
  {
    key: 'area',
    label: 'Area',
    required: true,
    placeholder: 'A1',
    description: 'Area / station zone',
  },
  {
    key: 'ct',
    label: 'CT',
    required: true,
    placeholder: '45',
    description: 'Cycle time (seconds)',
  },
] as const

type FieldKey = (typeof MI_FIELDS)[number]['key']

// ─── MIGenerator ──────────────────────────────────────────────────────────────

export function MIGenerator() {
  const [fields, setFields] = useState<Record<FieldKey, string>>(
    () => Object.fromEntries(MI_FIELDS.map((f) => [f.key, ''])) as Record<FieldKey, string>,
  )

  const mutation = useMutation({
    mutationFn: () => validateMiNaming({ fields }),
  })

  const handleChange = (key: FieldKey, value: string) => {
    setFields((prev) => ({ ...prev, [key]: value }))
    // Clear previous result when user edits
    mutation.reset()
  }

  // Live preview — non-empty segments joined by '_', no backend call needed
  const preview = MI_FIELDS.filter((f) => fields[f.key])
    .map((f) => fields[f.key])
    .join('_') || null

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {/* ignore in environments without clipboard API */})
  }

  return (
    <section className="space-y-4 rounded-2xl border border-gray-700 bg-gray-900/50 p-5">
      <div>
        <h2 className="text-base font-semibold text-gray-100">MI Naming Generator</h2>
        <p className="text-xs text-gray-400 font-mono mt-0.5">
          [Model5]_[Status]_[PickType]_[Process]_[CFI]_[Line]_[Area]_[CT]
        </p>
      </div>

      {/* 8-field form */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {MI_FIELDS.map((f) => (
          <div key={f.key} className="space-y-1">
            <label className="flex items-center gap-1 text-xs text-gray-400">
              {f.label}
              {f.required && <span className="text-red-400">*</span>}
            </label>
            <input
              type="text"
              value={fields[f.key]}
              onChange={(e) => handleChange(f.key, e.target.value)}
              placeholder={f.placeholder || f.description}
              className="w-full rounded bg-gray-800 border border-gray-600 px-2 py-1.5 text-gray-100 text-xs focus:border-cyan-500 focus:outline-none"
            />
            <p className="text-[10px] text-gray-600 leading-tight">{f.description}</p>
          </div>
        ))}
      </div>

      {/* Live preview (client-side) */}
      {preview && (
        <div className="flex items-center gap-3 rounded-lg border border-gray-700 bg-gray-800/50 px-4 py-2.5">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-gray-500 mb-0.5">Preview</p>
            <p className="font-mono text-sm text-cyan-300 break-all">{preview}</p>
          </div>
          <button
            onClick={() => copyToClipboard(preview)}
            className="shrink-0 rounded border border-gray-600 px-2 py-0.5 text-[10px] text-gray-400 hover:bg-gray-700 transition-colors"
          >
            Copy
          </button>
        </div>
      )}

      {/* Validate button */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="rounded-lg px-4 py-2 text-sm font-medium bg-cyan-600 text-white hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
        >
          {mutation.isPending ? 'Validating…' : 'Validate & Generate'}
        </button>
        {mutation.data && (
          <span className={mutation.data.is_valid ? 'text-green-400 text-xs' : 'text-red-400 text-xs'}>
            {mutation.data.is_valid ? '✓ Valid' : '✗ Invalid'}
          </span>
        )}
      </div>

      {/* Validation result */}
      {mutation.data && (
        <div
          className={[
            'rounded-lg border p-3 space-y-2',
            mutation.data.is_valid
              ? 'border-green-700/50 bg-green-950/30'
              : 'border-red-700/50 bg-red-950/30',
          ].join(' ')}
        >
          {mutation.data.is_valid ? (
            <>
              <p className="text-xs font-semibold text-green-400">✓ MI name is valid</p>
              {mutation.data.suggested_name && (
                <div className="flex items-center gap-3">
                  <p className="font-mono text-sm text-green-300 break-all flex-1">
                    {mutation.data.suggested_name}
                  </p>
                  <button
                    onClick={() => copyToClipboard(mutation.data!.suggested_name!)}
                    className="shrink-0 rounded border border-gray-600 px-2 py-0.5 text-[10px] text-gray-400 hover:bg-gray-700 transition-colors"
                  >
                    Copy
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <p className="text-xs font-semibold text-red-400">✗ Validation failed</p>
              {mutation.data.errors.map((e, i) => (
                <p key={i} className="text-xs text-red-300">· {e}</p>
              ))}
            </>
          )}
        </div>
      )}
    </section>
  )
}
