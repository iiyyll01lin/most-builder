import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchDashboard } from '@/api/bff'
import { DashboardSkeleton } from '@/components/ui/Skeleton'
import { PrecedenceGraphViewer } from '@/components/PrecedenceGraphViewer'
import { SimulationPanel } from '@/components/SimulationPanel'
import { SopActionEditor } from '@/components/SopActionEditor'
import type { SOPVersion, SOPVersionSummary } from '@/api/types'
import { useAuthStore } from '@/store/authStore'

// ─── KPI card ─────────────────────────────────────────────────────────────────

function KpiCard({
  label,
  value,
  sub,
}: {
  label: string
  value: string | number
  sub?: string
}) {
  return (
    <div className="rounded-xl border border-gray-700 bg-gray-800/40 p-4 space-y-1">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold text-gray-100">{value}</p>
      {sub && <p className="text-xs text-gray-500">{sub}</p>}
    </div>
  )
}

// ─── Version selector ─────────────────────────────────────────────────────────

function VersionBadge({
  v,
  active,
  onClick,
}: {
  v: SOPVersionSummary
  active: boolean
  onClick: () => void
}) {
  const statusColor = {
    Draft: 'border-gray-600 text-gray-300',
    Reviewed: 'border-blue-600 text-blue-300',
    Published: 'border-green-600 text-green-300',
  }[v.status]

  return (
    <button
      onClick={onClick}
      className={[
        'rounded-lg border px-3 py-1.5 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
        active
          ? 'bg-cyan-900/60 border-cyan-500 text-cyan-200'
          : `bg-gray-800 hover:bg-gray-700 ${statusColor}`,
      ].join(' ')}
    >
      {v.version_no}
      <span className="ml-1.5 opacity-60">{v.status}</span>
    </button>
  )
}

// ─── ProjectDashboard ─────────────────────────────────────────────────────────

interface ProjectDashboardProps {
  projectId: string
}

export function ProjectDashboard({ projectId }: ProjectDashboardProps) {
  const [selectedSopId, setSelectedSopId] = useState<string | undefined>()
  const user = useAuthStore((s) => s.user)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dashboard', projectId, selectedSopId],
    queryFn: () => fetchDashboard(projectId, selectedSopId),
    staleTime: 30_000,
    retry: 1,
  })

  if (isLoading) return <DashboardSkeleton />

  if (isError) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="rounded-xl border border-red-700 bg-red-950/40 p-6 text-center space-y-2">
          <p className="text-red-300 font-semibold">Failed to load dashboard</p>
          <p className="text-xs text-red-500">{(error as Error).message}</p>
        </div>
      </div>
    )
  }

  if (!data) return null

  const { project, sop_versions, workspace, level_system, precedence_graph } = data

  // Reconstruct an active SOPVersion-compatible object for the editor
  const activeSopVersion: SOPVersion | null = data.active_sop_version_id
    ? {
        id: data.active_sop_version_id,
        project_id: projectId,
        version_no:
          sop_versions.find((v) => v.id === data.active_sop_version_id)
            ?.version_no ?? '?',
        status:
          sop_versions.find((v) => v.id === data.active_sop_version_id)
            ?.status ?? 'Draft',
        // The BFF returns actions as workspace.actions — map them to SOPAction[]
        actions: (data.workspace.actions ?? []) as SOPVersion['actions'],
      }
    : null

  // Editable query key matching the full SOP version fetch
  const sopQueryKey = ['dashboard', projectId, selectedSopId]

  return (
    <div className="min-h-screen space-y-6 p-6">
      {/* Header */}
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-gray-100">
            {String(project['name'] ?? project['id'] ?? projectId)}
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Project ID: <span className="text-gray-400">{projectId}</span>
            {user && (
              <span className="ml-3 text-gray-500">
                Logged in as{' '}
                <span className="text-gray-300">{user.name}</span> ·{' '}
                <span className="text-cyan-500">{user.role}</span>
              </span>
            )}
          </p>
        </div>

        {/* SOP version selector */}
        {sop_versions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {sop_versions.map((v) => (
              <VersionBadge
                key={v.id}
                v={v}
                active={
                  (selectedSopId ?? data.active_sop_version_id) === v.id
                }
                onClick={() => setSelectedSopId(v.id)}
              />
            ))}
          </div>
        )}
      </header>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard
          label="Actions"
          value={level_system.total_count}
          sub="in active SOP"
        />
        <KpiCard
          label="Total CT"
          value={`${precedence_graph?.total_effective_ct?.toFixed(1) ?? '—'}s`}
          sub="effective cycle time"
        />
        <KpiCard
          label="MOST Steps"
          value={workspace.summary.step_count}
          sub={`${workspace.summary.total_tmu} TMU`}
        />
        <KpiCard
          label="SOP Versions"
          value={sop_versions.length}
          sub={`${sop_versions.filter((v) => v.status === 'Published').length} published`}
        />
      </div>

      {/* Precedence Graph */}
      {precedence_graph && precedence_graph.nodes.length > 0 && (
        <section className="rounded-2xl border border-gray-700 bg-gray-900/50 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-100">
              Precedence Graph
            </h2>
            {precedence_graph.cycle_errors.length > 0 && (
              <span className="rounded bg-red-800 px-2 py-0.5 text-xs text-red-100">
                ⚠ {precedence_graph.cycle_errors.length} cycle error
                {precedence_graph.cycle_errors.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
          <PrecedenceGraphViewer graph={precedence_graph} />
        </section>
      )}

      {precedence_graph && precedence_graph.nodes.length === 0 && (
        <div className="rounded-xl border border-dashed border-gray-700 p-8 text-center text-sm text-gray-600">
          No precedence data yet. Define Main/Order sequences in the Level System to generate a graph.
        </div>
      )}

      {/* SOP Action Editor */}
      {activeSopVersion && activeSopVersion.actions.length > 0 && (
        <SopActionEditor sop={activeSopVersion} queryKey={sopQueryKey} />
      )}

      {/* Simulation Panel */}
      <SimulationPanel
        projectId={projectId}
        initialRequest={{ takt_time: 60, stations: [] }}
      />
    </div>
  )
}
