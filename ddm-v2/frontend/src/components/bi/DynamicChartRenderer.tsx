/**
 * DynamicChartRenderer — Generative UI factory component.
 *
 * Reads the AI backend's structured JSON payload and mounts the appropriate
 * Recharts visualisation (BarChart, LineChart, PieChart) or a plain DataGrid
 * table, or a MetricCard for single KPI values.
 *
 * Expected payload shape (mirrors bi_service.py `generate_bi_report` output):
 * {
 *   type:    "BarChart" | "LineChart" | "PieChart" | "Table" | "MetricCard"
 *   data:    Array<Record<string, unknown>>
 *   columns: string[]
 *   xAxis?:  string   — column name for the categorical axis
 *   yAxis?:  string   — column name for the value axis
 *   insight: string
 *   sql_query: string
 * }
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

// ─── Payload type ─────────────────────────────────────────────────────────────

export type ChartType = 'BarChart' | 'LineChart' | 'PieChart' | 'Table' | 'MetricCard'

export interface BIPayload {
  type: ChartType
  data: Record<string, unknown>[]
  columns: string[]
  xAxis?: string | null
  yAxis?: string | null
  insight: string
  sql_query: string
}

// ─── Colour palette ───────────────────────────────────────────────────────────

const PALETTE = [
  '#22d3ee', '#818cf8', '#34d399', '#fb923c', '#f472b6',
  '#a78bfa', '#facc15', '#60a5fa', '#4ade80', '#f87171',
]

// ─── Sub-renderers ────────────────────────────────────────────────────────────

function RenderBarChart({ data, xAxis, yAxis }: Pick<BIPayload, 'data' | 'xAxis' | 'yAxis'>) {
  const x = xAxis ?? (Object.keys(data[0] ?? {})[0] || 'x')
  const y = yAxis ?? (Object.keys(data[0] ?? {})[1] || 'y')
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey={x} tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 12 }}
          labelStyle={{ color: '#e5e7eb' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
        <Bar dataKey={y} fill={PALETTE[0]} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function RenderLineChart({ data, xAxis, yAxis }: Pick<BIPayload, 'data' | 'xAxis' | 'yAxis'>) {
  const x = xAxis ?? (Object.keys(data[0] ?? {})[0] || 'x')
  const y = yAxis ?? (Object.keys(data[0] ?? {})[1] || 'y')
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey={x} tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 12 }}
          labelStyle={{ color: '#e5e7eb' }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
        <Line type="monotone" dataKey={y} stroke={PALETTE[0]} dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function RenderPieChart({ data, xAxis, yAxis }: Pick<BIPayload, 'data' | 'xAxis' | 'yAxis'>) {
  const nameKey = xAxis ?? (Object.keys(data[0] ?? {})[0] || 'name')
  const valueKey = yAxis ?? (Object.keys(data[0] ?? {})[1] || 'value')
  return (
    <ResponsiveContainer width="100%" height={320}>
      <PieChart>
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={nameKey}
          cx="50%"
          cy="50%"
          outerRadius={120}
          label={({ name, percent }: { name?: string; percent?: number }) =>
            `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
          labelLine={{ stroke: '#6b7280' }}
        >
          {data.map((_entry, idx) => (
            <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

function RenderTable({ data, columns }: Pick<BIPayload, 'data' | 'columns'>) {
  if (!data.length) return <p className="text-gray-500 text-sm">No rows returned.</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-700">
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-800 text-gray-400 uppercase text-xs">
          <tr>
            {columns.map((col) => (
              <th key={col} className="px-4 py-2 whitespace-nowrap">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, ri) => (
            <tr
              key={ri}
              className={ri % 2 === 0 ? 'bg-gray-900 text-gray-200' : 'bg-gray-850 text-gray-300'}
            >
              {columns.map((col) => (
                <td key={col} className="px-4 py-2 whitespace-nowrap">
                  {row[col] == null ? '—' : String(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RenderMetricCard({ data, columns }: Pick<BIPayload, 'data' | 'columns'>) {
  const firstRow = data[0] ?? {}
  const entries = columns.map((c) => ({ label: c, value: firstRow[c] }))
  return (
    <div className="flex flex-wrap gap-4">
      {entries.map(({ label, value }) => (
        <div
          key={label}
          className="flex-1 min-w-[140px] rounded-xl border border-cyan-800/50 bg-gray-800/60 px-6 py-4 text-center"
        >
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-1">{label}</p>
          <p className="text-3xl font-bold text-cyan-400">
            {value == null ? '—' : String(value)}
          </p>
        </div>
      ))}
    </div>
  )
}

// ─── Main factory component ───────────────────────────────────────────────────

interface DynamicChartRendererProps {
  payload: BIPayload
}

export function DynamicChartRenderer({ payload }: DynamicChartRendererProps) {
  const { type, data, columns, xAxis, yAxis } = payload

  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg border border-gray-700 bg-gray-900/60 px-4 py-3 text-sm text-gray-500 italic">
        The query returned no data.
      </div>
    )
  }

  return (
    <div className="w-full">
      {type === 'BarChart' && <RenderBarChart data={data} xAxis={xAxis} yAxis={yAxis} />}
      {type === 'LineChart' && <RenderLineChart data={data} xAxis={xAxis} yAxis={yAxis} />}
      {type === 'PieChart' && <RenderPieChart data={data} xAxis={xAxis} yAxis={yAxis} />}
      {type === 'Table' && <RenderTable data={data} columns={columns} />}
      {type === 'MetricCard' && <RenderMetricCard data={data} columns={columns} />}
    </div>
  )
}
