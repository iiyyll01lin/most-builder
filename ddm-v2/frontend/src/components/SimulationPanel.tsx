import { useState, useCallback, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { submitLineBalanceJob, connectSimulationWs } from '@/api/simulation'
import { fetchStations, fetchEmployees } from '@/api/master'
import { useAuthStore } from '@/store/authStore'
import { ProgressBar } from './ui/ProgressBar'
import { Combobox } from './ui/Combobox'
import type {
  LineBalanceRequest,
  LineBalanceResponse,
  SimProgressEvent,
  StationResult,
} from '@/api/types'

// ─── Local station config ──────────────────────────────────────────────────────

interface StationConfig {
  stationId: string
  employeeId: string
  machineCount: number
}

// ─── Station result card ──────────────────────────────────────────────────────

function StationCard({
  station,
  taktTime,
  isBottleneck,
}: {
  station: StationResult
  taktTime: number
  isBottleneck?: boolean
}) {
  const pct = Math.min(100, (station.actual_time / taktTime) * 100)
  const hasSkillAlerts = (station.skill_alerts?.length ?? 0) > 0
  const is1p2m = (station.machine_count ?? 1) > 1
  const [showActions, setShowActions] = useState(false)

  return (
    <div
      className={[
        'rounded-xl border p-4 space-y-2 transition-colors',
        station.is_overloaded
          ? 'border-red-600/60 bg-red-950/30'
          : isBottleneck
            ? 'border-amber-500/70 bg-amber-950/20'
            : 'border-gray-700 bg-gray-800/40',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <div className="min-w-0 flex-1">
          {/* break-words: prevents long station descriptions from overflowing the card (Yamazumi 山積圖 fix) */}
          <p className="text-sm font-semibold text-gray-100 break-words whitespace-normal">{station.name}</p>
          <p className="text-xs text-gray-400">{station.operator} · {station.skill_level}</p>
        </div>
        <div className="flex flex-wrap gap-1">
          {station.is_overloaded && (
            <span className="shrink-0 rounded bg-red-800 px-2 py-0.5 text-xs text-red-100">
              OVERLOADED
            </span>
          )}
          {isBottleneck && (
            <span className="shrink-0 rounded bg-amber-700/80 px-2 py-0.5 text-xs text-amber-100 font-semibold">
              BOTTLENECK
            </span>
          )}
          {hasSkillAlerts && (
            <span className="shrink-0 rounded bg-red-900 px-2 py-0.5 text-xs text-red-200 font-semibold">
              ⚠ SKILL ALERT
            </span>
          )}
          {is1p2m && (
            <span className="shrink-0 rounded bg-orange-900/70 px-2 py-0.5 text-xs text-orange-200">
              1P{station.machine_count}M
            </span>
          )}
          {station.ion_fan_required && (
            <span className="shrink-0 rounded bg-blue-800 px-2 py-0.5 text-xs text-blue-100">
              ION FAN
            </span>
          )}
        </div>
      </div>

      {/* Utilization bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Utilisation</span>
          <span className={station.is_overloaded ? 'text-red-400' : 'text-green-400'}>
            {pct.toFixed(1)}%
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-gray-700">
          <div
            className={[
              'h-full rounded-full transition-all duration-700',
              station.is_overloaded
                ? 'bg-red-500'
                : pct > 85
                  ? 'bg-amber-400'
                  : 'bg-green-500',
            ].join(' ')}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 text-xs">
        <div>
          <span className="text-gray-500">STD CT: </span>
          <span className="text-amber-300">{station.standard_time.toFixed(2)}s</span>
        </div>
        <div>
          <span className="text-gray-500">ACT CT: </span>
          <span className={station.is_overloaded ? 'text-red-300' : 'text-cyan-300'}>
            {station.actual_time.toFixed(2)}s
          </span>
        </div>
        {is1p2m && station.machine_effective_time != null && (
          <div>
            <span className="text-gray-500">EFF CT: </span>
            <span className="text-orange-300">{station.machine_effective_time.toFixed(2)}s</span>
          </div>
        )}
        <div>
          <span className="text-gray-500">Actions: </span>
          <span className="text-gray-200">{station.actions.length}</span>
        </div>
        <div>
          <span className="text-gray-500">Eff: </span>
          <span className="text-gray-200">{(station.efficiency_factor * 100).toFixed(0)}%</span>
        </div>
      </div>

      {station.required_gloves.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {station.required_gloves.map((g) => (
            <span key={g} className="rounded bg-purple-900/60 px-1.5 py-0.5 text-[10px] text-purple-300">
              {g}
            </span>
          ))}
        </div>
      )}

      {/* Skill alerts */}
      {hasSkillAlerts && (
        <div className="space-y-1 rounded bg-red-950/40 border border-red-800/40 p-2">
          {station.skill_alerts!.map((alert, i) => (
            <p key={i} className="text-[10px] text-red-300 leading-tight">⚠ {alert}</p>
          ))}
        </div>
      )}

      {/* Yamazumi action list — collapsible, text wrapping enabled */}
      {station.actions.length > 0 && (
        <div>
          <button
            onClick={() => setShowActions((v) => !v)}
            className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
          >
            <span>{showActions ? '▼' : '▶'}</span>
            <span>{showActions ? 'Hide' : 'Show'} {station.actions.length} action{station.actions.length !== 1 ? 's' : ''}</span>
          </button>
          {showActions && (
            <ol className="mt-1.5 space-y-0.5">
              {(station.actions as Array<{ id: string; description: string; seconds: number; is_simo?: boolean; simo_group_id?: string | null }>).map((a, idx) => (
                <li key={a.id ?? idx} className="flex items-start gap-1.5 text-[10px] text-gray-400">
                  <span className="shrink-0 text-gray-600">{idx + 1}.</span>
                  {/* break-words + whitespace-normal prevents Yamazumi text overflow */}
                  <span className="break-words whitespace-normal min-w-0 flex-1">{a.description}</span>
                  <span className="shrink-0 text-gray-600">{a.seconds.toFixed(2)}s</span>
                  {a.is_simo && (
                    <span
                      className="shrink-0 rounded bg-purple-900/60 px-1 py-0.5 text-[9px] text-purple-300 cursor-help"
                      title="SIMO — time parallelized; only bottleneck hand counted"
                    >
                      SIMO
                    </span>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

// ─── SimulationPanel ──────────────────────────────────────────────────────────

interface SimulationPanelProps {
  projectId: string
  initialRequest?: Omit<LineBalanceRequest, 'project_id'>
  /** Active SOP version ID — assigned to every station's sop_ids */
  activeSopVersionId?: string
}

type SimState = 'idle' | 'running' | 'complete' | 'error'

interface ProgressState {
  pct: number
  status: string
}

export function SimulationPanel({ projectId, initialRequest, activeSopVersionId }: SimulationPanelProps) {
  const token = useAuthStore((s) => s.token)

  const [simState, setSimState] = useState<SimState>('idle')
  const [progress, setProgress] = useState<ProgressState>({ pct: 0, status: '' })
  const [result, setResult] = useState<
    (LineBalanceResponse & { id: string; timestamp: string; project_id: string; created_by: string }) | null
  >(null)
  const [taktTime, setTaktTime] = useState(initialRequest?.takt_time ?? 60)

  // Station configuration rows
  const [stationConfigs, setStationConfigs] = useState<StationConfig[]>(
    () =>
      (initialRequest?.stations ?? []).map((s) => ({
        stationId: s.id,
        employeeId: s.employee_id ?? '',
        machineCount: s.machine_count ?? 1,
      })),
  )

  const cleanupWsRef = useRef<(() => void) | null>(null)

  // ── Master data for selectors ──────────────────────────────────────────────
  const { data: masterStations = [] } = useQuery({
    queryKey: ['master-stations'],
    queryFn: fetchStations,
    staleTime: 60_000,
  })
  const { data: masterEmployees = [] } = useQuery({
    queryKey: ['master-employees'],
    queryFn: fetchEmployees,
    staleTime: 60_000,
  })

  const stationOptions = masterStations.map((s) => ({ value: s.id, label: s.name }))
  const employeeOptions = masterEmployees.map((e) => ({
    value: e.id,
    label: `${e.name} (${e.skill_level})`,
  }))

  // ── Station config CRUD ────────────────────────────────────────────────────
  const addStation = useCallback(() => {
    setStationConfigs((prev) => [
      ...prev,
      { stationId: '', employeeId: '', machineCount: 1 },
    ])
  }, [])

  const removeStation = useCallback((idx: number) => {
    setStationConfigs((prev) => prev.filter((_, i) => i !== idx))
  }, [])

  const updateStation = useCallback(
    (idx: number, field: keyof StationConfig, val: string | number) => {
      setStationConfigs((prev) =>
        prev.map((c, i) => (i === idx ? { ...c, [field]: val } : c)),
      )
    },
    [],
  )

  const jobMutation = useMutation({
    mutationFn: (payload: LineBalanceRequest) => submitLineBalanceJob(payload),
    onSuccess: ({ job_id }) => {
      if (!token) {
        toast.error('Not authenticated')
        setSimState('error')
        return
      }
      setSimState('running')
      setProgress({ pct: 0, status: 'Connecting…' })

      cleanupWsRef.current = connectSimulationWs(
        job_id,
        token,
        (event: SimProgressEvent) => {
          if (event.progress === 100 && event.result) {
            setProgress({ pct: 100, status: 'Simulation complete' })
            setResult(event.result)
            setSimState('complete')
            cleanupWsRef.current?.()
          } else if (event.progress === -1) {
            setProgress({ pct: -1, status: event.error ?? 'Simulation failed' })
            setSimState('error')
            toast.error(event.error ?? 'Simulation failed')
            cleanupWsRef.current?.()
          } else {
            setProgress({ pct: event.progress, status: event.status })
          }
        },
        (errMsg) => {
          setProgress({ pct: -1, status: errMsg })
          setSimState('error')
          toast.error(errMsg)
        },
      )
    },
    onError: () => {
      setSimState('error')
    },
  })

  const isRunning = simState === 'running' || jobMutation.isPending
  const configuredStations = stationConfigs.filter((c) => c.stationId)

  const handleRun = useCallback(() => {
    cleanupWsRef.current?.()
    setResult(null)
    setSimState('idle')
    setProgress({ pct: 0, status: '' })

    const payload: LineBalanceRequest = {
      project_id: projectId,
      takt_time: taktTime,
      stations: stationConfigs
        .filter((c) => c.stationId)
        .map((c) => ({
          id: c.stationId,
          sop_ids: activeSopVersionId ? [activeSopVersionId] : [],
          employee_id: c.employeeId || undefined,
          machine_count: c.machineCount,
        })),
    }
    jobMutation.mutate(payload)
  }, [projectId, taktTime, stationConfigs, activeSopVersionId, jobMutation])

  return (
    <section className="space-y-4 rounded-2xl border border-gray-700 bg-gray-900/50 p-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Line Balance Simulation</h2>
          <p className="text-xs text-gray-400">Real-time async · WebSocket stream</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-gray-400">
            Takt Time (s)
            <input
              type="number"
              min={1}
              step={1}
              value={taktTime}
              onChange={(e) => setTaktTime(Number(e.target.value))}
              disabled={isRunning}
              className="w-20 rounded bg-gray-800 border border-gray-600 px-2 py-1 text-gray-100 text-xs focus:border-cyan-500 focus:outline-none disabled:opacity-50"
            />
          </label>
          <button
            onClick={handleRun}
            disabled={isRunning || configuredStations.length === 0}
            className={[
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
              isRunning || configuredStations.length === 0
                ? 'cursor-not-allowed bg-gray-700 text-gray-500'
                : 'bg-cyan-600 text-white hover:bg-cyan-500',
            ].join(' ')}
          >
            {isRunning ? 'Running…' : 'Run Simulation'}
          </button>
          {(simState === 'complete' || simState === 'error') && (
            <button
              onClick={handleRun}
              className="rounded-lg border border-gray-600 px-3 py-2 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
            >
              Re-run
            </button>
          )}
        </div>
      </div>

      {/* Station configurator */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Station Configuration
          </p>
          <button
            onClick={addStation}
            disabled={isRunning}
            className="rounded border border-gray-600 px-2 py-0.5 text-xs text-gray-400 hover:bg-gray-700 disabled:opacity-40 transition-colors"
          >
            + Add Station
          </button>
        </div>

        {stationConfigs.length === 0 && (
          <p className="text-xs text-gray-600 italic py-2">
            No stations configured. Add a station to enable the simulation.
          </p>
        )}

        {stationConfigs.map((config, idx) => (
          <div
            key={idx}
            className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800/30 px-3 py-2"
          >
            <Combobox
              options={stationOptions}
              value={config.stationId}
              onChange={(v) => updateStation(idx, 'stationId', v)}
              placeholder="Select station…"
              disabled={isRunning}
              className="flex-1 min-w-0"
            />
            <Combobox
              options={employeeOptions}
              value={config.employeeId}
              onChange={(v) => updateStation(idx, 'employeeId', v)}
              placeholder="Employee (optional)…"
              disabled={isRunning}
              className="flex-1 min-w-0"
            />
            <label className="flex items-center gap-1.5 shrink-0 text-xs text-gray-400 whitespace-nowrap">
              Machines
              <input
                type="number"
                min={1}
                max={10}
                value={config.machineCount}
                onChange={(e) =>
                  updateStation(idx, 'machineCount', Math.max(1, Number(e.target.value)))
                }
                disabled={isRunning}
                className="w-14 rounded bg-gray-800 border border-gray-600 px-2 py-1 text-gray-100 text-xs focus:border-cyan-500 focus:outline-none disabled:opacity-50"
              />
            </label>
            <button
              onClick={() => removeStation(idx)}
              disabled={isRunning}
              className="text-gray-600 hover:text-red-400 disabled:opacity-30 transition-colors text-sm leading-none px-1"
              title="Remove station"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      {/* Progress bar — visible during and after run */}
      {simState !== 'idle' && (
        <ProgressBar
          progress={progress.pct}
          status={progress.status}
          className="mt-2"
        />
      )}

      {/* Results */}
      {simState === 'complete' && result && (
        <div className="space-y-4 pt-2">
        {/* KPI strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            {/* Core simulation KPIs */}
            {[
              { label: 'Cycle Time', value: `${result.cycle_time.toFixed(2)}s`, colorClass: 'text-gray-100' },
              { label: 'UPH', value: result.uph.toString(), colorClass: 'text-gray-100' },
              {
                label: 'Balance Rate',
                value: `${(result.balance_rate * 100).toFixed(1)}%`,
                colorClass: result.balance_rate >= 0.85 ? 'text-green-400' : 'text-gray-100',
              },
              { label: 'Bottleneck', value: result.bottleneck_station, colorClass: 'text-gray-100' },
            ].map(({ label, value, colorClass }) => (
              <div
                key={label}
                className="rounded-xl border border-gray-700 bg-gray-800/50 p-3"
              >
                <p className="text-xs text-gray-500">{label}</p>
                <p className={`mt-1 text-lg font-bold ${colorClass}`}>{value}</p>
              </div>
            ))}
            {/* Balance Efficiency KPIs from BalanceReport */}
            {result.balance_report && (() => {
              const eff = result.balance_report.balance_efficiency_pct
              const effColor = eff >= 85 ? 'text-green-400' : eff >= 70 ? 'text-amber-400' : 'text-red-400'
              return (
                <>
                  <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Efficiency</p>
                    <p className={`mt-1 text-lg font-bold ${effColor}`}>
                      {eff.toFixed(1)}%
                    </p>
                  </div>
                  <div className="rounded-xl border border-gray-700 bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Balance Loss</p>
                    <p className={`mt-1 text-lg font-bold ${
                      result.balance_report.balance_loss_pct > 30
                        ? 'text-red-400'
                        : result.balance_report.balance_loss_pct > 15
                          ? 'text-amber-400'
                          : 'text-gray-100'
                    }`}>
                      {result.balance_report.balance_loss_pct.toFixed(1)}%
                    </p>
                  </div>
                </>
              )
            })()}
          </div>

          {/* Simulation-level alerts */}
          {result.alerts.length > 0 && (
            <div className="rounded-lg border border-amber-700/50 bg-amber-950/30 p-3 space-y-1">
              <p className="text-xs font-semibold text-amber-400">Alerts</p>
              {result.alerts.map((a, i) => (
                <p key={i} className="text-xs text-amber-300">· {a}</p>
              ))}
            </div>
          )}

          {/* Station cards */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {result.station_results.map((s) => (
              <StationCard
                key={s.id}
                station={s}
                taktTime={taktTime}
                isBottleneck={s.id === result.bottleneck_station}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
