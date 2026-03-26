import { useState, useCallback, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { submitLineBalanceJob, connectSimulationWs } from '@/api/simulation'
import { useAuthStore } from '@/store/authStore'
import { ProgressBar } from './ui/ProgressBar'
import type { LineBalanceRequest, LineBalanceResponse, SimProgressEvent } from '@/api/types'

// ─── Station result card ──────────────────────────────────────────────────────

function StationCard({
  station,
  taktTime,
}: {
  station: LineBalanceResponse['station_results'][number]
  taktTime: number
}) {
  const pct = Math.min(100, (station.actual_time / taktTime) * 100)
  return (
    <div
      className={[
        'rounded-xl border p-4 space-y-2 transition-colors',
        station.is_overloaded
          ? 'border-red-600/60 bg-red-950/30'
          : 'border-gray-700 bg-gray-800/40',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-100">{station.name}</p>
          <p className="text-xs text-gray-400">{station.operator} · {station.skill_level}</p>
        </div>
        {station.is_overloaded && (
          <span className="shrink-0 rounded bg-red-800 px-2 py-0.5 text-xs text-red-100">
            OVERLOADED
          </span>
        )}
        {station.ion_fan_required && (
          <span className="shrink-0 rounded bg-blue-800 px-2 py-0.5 text-xs text-blue-100">
            ION FAN
          </span>
        )}
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
    </div>
  )
}

// ─── SimulationPanel ──────────────────────────────────────────────────────────

interface SimulationPanelProps {
  projectId: string
  initialRequest?: Omit<LineBalanceRequest, 'project_id'>
}

type SimState = 'idle' | 'running' | 'complete' | 'error'

interface ProgressState {
  pct: number
  status: string
}

export function SimulationPanel({ projectId, initialRequest }: SimulationPanelProps) {
  const token = useAuthStore((s) => s.token)

  const [simState, setSimState] = useState<SimState>('idle')
  const [progress, setProgress] = useState<ProgressState>({ pct: 0, status: '' })
  const [result, setResult] = useState<
    (LineBalanceResponse & { id: string; timestamp: string; project_id: string; created_by: string }) | null
  >(null)
  const [taktTime, setTaktTime] = useState(initialRequest?.takt_time ?? 60)

  const cleanupWsRef = useRef<(() => void) | null>(null)

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

  const handleRun = useCallback(() => {
    cleanupWsRef.current?.()
    setResult(null)
    setSimState('idle')
    setProgress({ pct: 0, status: '' })

    // Build a minimal payload — real usage would collect station config from UI
    const payload: LineBalanceRequest = {
      project_id: projectId,
      takt_time: taktTime,
      stations: initialRequest?.stations ?? [],
    }
    jobMutation.mutate(payload)
  }, [projectId, taktTime, initialRequest, jobMutation])

  return (
    <section className="space-y-4 rounded-2xl border border-gray-700 bg-gray-900/50 p-5">
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
              disabled={simState === 'running'}
              className="w-20 rounded bg-gray-800 border border-gray-600 px-2 py-1 text-gray-100 text-xs focus:border-cyan-500 focus:outline-none disabled:opacity-50"
            />
          </label>
          <button
            onClick={handleRun}
            disabled={simState === 'running' || jobMutation.isPending}
            className={[
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
              simState === 'running' || jobMutation.isPending
                ? 'cursor-not-allowed bg-gray-700 text-gray-500'
                : 'bg-cyan-600 text-white hover:bg-cyan-500',
            ].join(' ')}
          >
            {simState === 'running' ? 'Running…' : 'Run Simulation'}
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: 'Cycle Time', value: `${result.cycle_time.toFixed(2)}s`, highlight: false },
              { label: 'UPH', value: result.uph.toString(), highlight: false },
              {
                label: 'Balance Rate',
                value: `${(result.balance_rate * 100).toFixed(1)}%`,
                highlight: result.balance_rate >= 0.85,
              },
              { label: 'Bottleneck', value: result.bottleneck_station, highlight: false },
            ].map(({ label, value, highlight }) => (
              <div
                key={label}
                className="rounded-xl border border-gray-700 bg-gray-800/50 p-3"
              >
                <p className="text-xs text-gray-500">{label}</p>
                <p className={`mt-1 text-lg font-bold ${highlight ? 'text-green-400' : 'text-gray-100'}`}>
                  {value}
                </p>
              </div>
            ))}
          </div>

          {/* Alerts */}
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
              <StationCard key={s.id} station={s} taktTime={taktTime} />
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
