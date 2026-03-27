/**
 * DigitalTwinView — Phase 2: 3D Line-Balance Spatial Visualization
 *                   Phase 7: Real-Time IoT Telemetry Active Digital Twin
 *
 * Component tree:
 *   <DigitalTwinView>                 — DOM wrapper, KPI overlay, legend
 *     <Canvas orthographic>           — R3F root (isometric ortho camera)
 *       <OrbitControls>               — pan / zoom / rotate
 *       <Scene>                       — holds hoveredId state, emits all 3D objects
 *         <ambientLight>
 *         <directionalLight> × 2
 *         <gridHelper>                — factory floor
 *         <TaktPlane>                 — translucent cyan reference plane at 100% CT
 *         <OperatorCluster> × N       — floor decal per unique operator (1P2M grouping)
 *         <WorkstationNode> × N       — bar + top-cap + hover tooltip + bottleneck halo
 *
 * State strategy:
 *   - hoveredId (string | null) — local useState inside <Scene>, propagated to nodes
 *   - result / taktTime          — pure props from SimulationPanel (no Zustand changes)
 *
 * Phase 7 — zero-re-render telemetry:
 *   - useTelemetry() opens WS once; emits to telemetryBus (module-level pub/sub)
 *   - WorkstationNode useEffect subscribes to bus.  On event → writes flashRef
 *     (plain object mutation, invisible to React)
 *   - useFrame reads flashRef every tick, drives mat.emissive imperatively
 *   - React reconciler is never invoked on a telemetry ping
 */

import { Canvas, useFrame } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import { useEffect, useRef, useState, useMemo } from 'react'
import * as THREE from 'three'
import type { LineBalanceResponse, StationResult } from '@/api/types'
import { useTelemetry, telemetryBus } from '@/hooks/useTelemetry'
import type { TelemetryStatus } from '@/hooks/useTelemetry'

// ─── Flash colour constants (Phase 7) ────────────────────────────────────────

/** Duration of the emissive flash animation in milliseconds */
const FLASH_DURATION_MS = 500

/** Event type → emissive flash colour */
const FLASH_COLORS: Record<string, string> = {
  fasten_ok: '#22c55e',
  fasten_timeout: '#ef4444',
  error: '#ef4444',
  warning: '#f59e0b',
}
const FLASH_COLOR_DEFAULT = '#a78bfa'

// ─── Layout & palette constants ───────────────────────────────────────────────

/** World-space distance between adjacent station centres on the X axis */
const SPACING = 3.5

/** Minimum bar height (zero-CT floor) */
const BASE_H = 0.3

/** Bar height when CT exactly equals takt time (100% utilisation line) */
const MAX_H = 5.0

/** Repeatable palette for operator cluster floor decals */
const CLUSTER_COLORS = [
  '#6366f1', '#0ea5e9', '#8b5cf6',
  '#14b8a6', '#f97316', '#ec4899', '#10b981',
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Map station actual CT to a 3D bar height, clamped with overflow for overload. */
function ctToHeight(actualTime: number, taktTime: number): number {
  return Math.max(
    BASE_H,
    Math.min(
      BASE_H + (actualTime / taktTime) * (MAX_H - BASE_H),
      MAX_H + 2.0, // allow visible overflow for overloaded stations
    ),
  )
}

// ─── Station Tooltip (HTML overlay via drei <Html>) ───────────────────────────

function StationTooltip({
  station,
  taktTime,
  isBottleneck,
}: {
  station: StationResult
  taktTime: number
  isBottleneck: boolean
}) {
  const utilPct = Math.min(300, (station.actual_time / taktTime) * 100)
  const utilColor = utilPct > 100 ? '#ef4444' : utilPct > 85 ? '#f59e0b' : '#22c55e'

  const rows: [string, string, string?][] = [
    ['Operator', station.operator],
    ['Skill', station.skill_level],
    ['Efficiency', `${(station.efficiency_factor * 100).toFixed(0)}%`],
    ['STD CT', `${station.standard_time.toFixed(2)}s`],
    ['ACT CT', `${station.actual_time.toFixed(2)}s`],
    ['Utilisation', `${utilPct.toFixed(1)}%`, utilColor],
  ]
  if ((station.machine_count ?? 1) > 1) {
    rows.push([`1P${station.machine_count}M`, 'Active'])
    if (station.machine_effective_time != null) {
      rows.push(['Eff CT', `${station.machine_effective_time.toFixed(2)}s`])
    }
  }

  return (
    <div
      style={{
        background: 'rgba(10,14,26,0.97)',
        border: '1px solid rgba(99,102,241,0.55)',
        borderRadius: 8,
        padding: '10px 14px',
        minWidth: 230,
        fontSize: 11,
        color: '#e2e8f0',
        boxShadow: '0 8px 32px rgba(0,0,0,0.75)',
        pointerEvents: 'none',
        lineHeight: 1.65,
        fontFamily: 'system-ui, sans-serif',
      }}
    >
      {/* Station name */}
      <p style={{ fontWeight: 700, fontSize: 13, marginBottom: 6, color: '#f1f5f9' }}>
        {station.name}
      </p>

      {/* Status badges */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
        {isBottleneck && (
          <span style={{ background: 'rgba(245,158,11,0.25)', border: '1px solid #f59e0b', borderRadius: 4, padding: '1px 6px', fontSize: 10, color: '#fcd34d', fontWeight: 700 }}>
            ⚡ BOTTLENECK
          </span>
        )}
        {station.is_overloaded && (
          <span style={{ background: 'rgba(239,68,68,0.2)', border: '1px solid #ef4444', borderRadius: 4, padding: '1px 6px', fontSize: 10, color: '#fca5a5', fontWeight: 700 }}>
            ⚠ OVERLOADED
          </span>
        )}
        {(station.machine_count ?? 1) > 1 && (
          <span style={{ background: 'rgba(249,115,22,0.2)', border: '1px solid #f97316', borderRadius: 4, padding: '1px 6px', fontSize: 10, color: '#fdba74' }}>
            1P{station.machine_count}M
          </span>
        )}
      </div>

      {/* KPI table */}
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <tbody>
          {rows.map(([label, value, color]) => (
            <tr key={label}>
              <td style={{ color: '#94a3b8', paddingRight: 10, paddingBottom: 1 }}>{label}</td>
              <td style={{ color: color ?? '#f1f5f9', fontWeight: 500 }}>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Skill alerts */}
      {(station.skill_alerts?.length ?? 0) > 0 && (
        <div style={{ marginTop: 7, borderTop: '1px solid rgba(239,68,68,0.3)', paddingTop: 5 }}>
          <p style={{ fontSize: 9, color: '#f87171', fontWeight: 700, marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Skill Alerts</p>
          {station.skill_alerts!.map((a, i) => (
            <p key={i} style={{ color: '#fca5a5', fontSize: 10 }}>⚠ {a}</p>
          ))}
        </div>
      )}

      {/* Required gloves */}
      {station.required_gloves.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <span style={{ fontSize: 9, color: '#a78bfa', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Gloves: </span>
          <span style={{ fontSize: 10, color: '#c4b5fd' }}>{station.required_gloves.join(', ')}</span>
        </div>
      )}

      {/* Precautions */}
      {(station.precautions?.length ?? 0) > 0 && (
        <div style={{ marginTop: 6, borderTop: '1px solid rgba(251,191,36,0.3)', paddingTop: 5 }}>
          <p style={{ fontSize: 9, color: '#fbbf24', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>Precautions</p>
          {station.precautions!.map((p, i) => (
            <p key={i} style={{ color: '#fde68a', fontSize: 10 }}>· {p}</p>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Bottleneck Halo (pulsing ring at station base) ───────────────────────────

function BottleneckHalo() {
  const ref = useRef<THREE.Mesh>(null!)

  useFrame(() => {
    if (!ref.current) return
    const t = Date.now() * 0.0025
    const pulse = 0.5 + 0.5 * Math.sin(t * Math.PI * 2)
    ref.current.scale.set(1 + 0.14 * pulse, 1, 1 + 0.14 * pulse)
    ;(ref.current.material as THREE.MeshBasicMaterial).opacity = 0.3 + 0.35 * pulse
  })

  return (
    // Horizontal ring lying flat on the floor
    <mesh ref={ref} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[1.1, 1.7, 32]} />
      <meshBasicMaterial
        color="#f59e0b"
        transparent
        opacity={0.5}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  )
}

// ─── WorkstationNode ──────────────────────────────────────────────────────────

interface WorkstationNodeProps {
  station: StationResult
  posX: number
  isBottleneck: boolean
  taktTime: number
  isHovered: boolean
  onHover: (id: string | null) => void
}

function WorkstationNode({
  station,
  posX,
  isBottleneck,
  taktTime,
  isHovered,
  onHover,
}: WorkstationNodeProps) {
  const barRef = useRef<THREE.Mesh>(null!)
  const barH = ctToHeight(station.actual_time, taktTime)
  const is1p2m = (station.machine_count ?? 1) > 1

  // ── Phase 7: Flash state ref (mutated by WS event, read by useFrame) ──────
  // Shape: { startMs: number; color: THREE.Color } | null
  // React never sees this — it's a plain object mutation.
  const flashRef = useRef<{ startMs: number; color: THREE.Color } | null>(null)

  useEffect(() => {
    // Subscribe to telemetry events for this station.
    const unsub = telemetryBus.subscribe(station.id, (event) => {
      const hex = FLASH_COLORS[event.event_type] ?? FLASH_COLOR_DEFAULT
      flashRef.current = { startMs: Date.now(), color: new THREE.Color(hex) }
    })
    return unsub
  }, [station.id])

  // Emissive pulse for bottleneck; telemetry flash; subtle glow for hover
  useFrame(() => {
    if (!barRef.current) return
    const mat = barRef.current.material as THREE.MeshStandardMaterial

    // ── Phase 7: telemetry flash (highest priority) ───────────────────────
    const flash = flashRef.current
    if (flash !== null) {
      const t = (Date.now() - flash.startMs) / FLASH_DURATION_MS  // 0 → 1
      if (t < 1) {
        // Ease-out: peak intensity at t=0, fade to 0 at t=1
        const intensity = (1 - t) * 2.5
        mat.emissive.copy(flash.color)
        mat.emissiveIntensity = intensity
        return
      }
      // Flash expired — clear so we fall through to base behaviour
      flashRef.current = null
    }

    // ── Base behaviour (bottleneck pulse / hover / idle) ──────────────────
    if (isBottleneck) {
      mat.emissiveIntensity = 0.28 + 0.28 * Math.sin(Date.now() * 0.004)
    } else if (isHovered) {
      mat.emissiveIntensity = 0.18
    } else {
      mat.emissiveIntensity = station.is_overloaded ? 0.12 : 0.0
    }
  })

  const barColor = station.is_overloaded
    ? '#ef4444'
    : isBottleneck
      ? '#f59e0b'
      : '#22d3ee'

  const emissiveColor = isBottleneck
    ? '#f59e0b'
    : station.is_overloaded
      ? '#ef4444'
      : '#000000'

  return (
    <group position={[posX, 0, 0]}>
      {/* ── Main CT bar ── */}
      <mesh
        ref={barRef}
        position={[0, barH / 2, 0]}
        castShadow
        receiveShadow
        onPointerOver={(e) => { e.stopPropagation(); onHover(station.id) }}
        onPointerOut={() => onHover(null)}
      >
        <boxGeometry args={[1.6, barH, 1.6]} />
        <meshStandardMaterial
          color={barColor}
          emissive={emissiveColor}
          emissiveIntensity={0}
          roughness={0.35}
          metalness={0.45}
        />
      </mesh>

      {/* ── Top cap platform (wider, slightly raised) ── */}
      <mesh position={[0, barH + 0.05, 0]} castShadow>
        <boxGeometry args={[2.1, 0.10, 2.1]} />
        <meshStandardMaterial color={barColor} roughness={0.25} metalness={0.55} />
      </mesh>

      {/* ── 1P2M secondary machine indicator (orange cube offset to the right) ── */}
      {is1p2m && (
        <mesh position={[1.55, 0.35, 0]} castShadow>
          <boxGeometry args={[0.55, 0.7, 0.55]} />
          <meshStandardMaterial color="#f97316" roughness={0.4} metalness={0.4} />
        </mesh>
      )}

      {/* ── Bottleneck pulsing halo (floor level) ── */}
      {isBottleneck && <BottleneckHalo />}

      {/* ── Floor label (always visible) ── */}
      <group position={[0, -0.45, 0]}>
        <Html center style={{ pointerEvents: 'none', userSelect: 'none' }}>
          <div style={{
            fontSize: 9,
            color: '#94a3b8',
            whiteSpace: 'nowrap',
            textShadow: '0 1px 4px rgba(0,0,0,0.9)',
            fontFamily: 'system-ui, sans-serif',
          }}>
            {station.name.length > 17 ? station.name.slice(0, 15) + '…' : station.name}
          </div>
        </Html>
      </group>

      {/* ── Hover tooltip (HTML overlay via drei) ── */}
      {isHovered && (
        <group position={[0, barH + 1.0, 0]}>
          <Html center style={{ pointerEvents: 'none', zIndex: 100 }}>
            <StationTooltip station={station} taktTime={taktTime} isBottleneck={isBottleneck} />
          </Html>
        </group>
      )}
    </group>
  )
}

// ─── Operator Cluster Floor Decal ─────────────────────────────────────────────

interface OperatorClusterProps {
  indices: number[]
  colorIndex: number
  label: string
}

function OperatorCluster({ indices, colorIndex, label }: OperatorClusterProps) {
  if (indices.length === 0) return null

  const minX = Math.min(...indices) * SPACING - 1.45
  const maxX = Math.max(...indices) * SPACING + 1.45
  const width = maxX - minX
  const cx = (minX + maxX) / 2

  const color = CLUSTER_COLORS[colorIndex % CLUSTER_COLORS.length]

  return (
    <group position={[cx, 0.02, 0]}>
      {/* Translucent fill plane */}
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[width, 2.9]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.11}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Operator label at the front edge */}
      <group position={[0, 0.06, 1.8]}>
        <Html center style={{ pointerEvents: 'none', userSelect: 'none' }}>
          <div style={{
            fontSize: 9,
            color,
            fontWeight: 700,
            whiteSpace: 'nowrap',
            textShadow: '0 1px 4px rgba(0,0,0,0.95)',
            fontFamily: 'system-ui, sans-serif',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}>
            {label}
          </div>
        </Html>
      </group>
    </group>
  )
}

// ─── Takt Reference Plane ─────────────────────────────────────────────────────

function TaktPlane({ centerX, stationCount }: { centerX: number; stationCount: number }) {
  const width = (stationCount + 1) * SPACING
  return (
    <group>
      {/* Translucent horizontal plane exactly at the 100% utilisation mark */}
      <mesh position={[centerX, MAX_H, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[width, 2.9]} />
        <meshBasicMaterial
          color="#06b6d4"
          transparent
          opacity={0.07}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* "TAKT" label at left edge */}
      <group position={[centerX - width / 2 - 0.4, MAX_H, 0]}>
        <Html center style={{ pointerEvents: 'none', userSelect: 'none' }}>
          <div style={{
            fontSize: 9,
            color: '#06b6d4',
            fontWeight: 700,
            textShadow: '0 1px 4px rgba(0,0,0,0.9)',
            fontFamily: 'system-ui, sans-serif',
            whiteSpace: 'nowrap',
          }}>
            TAKT
          </div>
        </Html>
      </group>
    </group>
  )
}

// ─── Scene (all 3D objects + raycasting state) ────────────────────────────────

function Scene({ result, taktTime }: { result: LineBalanceResponse; taktTime: number }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)

  const stations = result.station_results
  // Prefer the dedicated ID field from BalanceReport if available
  const bottleneckId =
    result.balance_report?.bottleneck_station_id ?? result.bottleneck_station

  const centerX = ((stations.length - 1) * SPACING) / 2
  const gridSize = (stations.length + 2) * SPACING
  const gridDivisions = Math.max(8, (stations.length + 2) * 4)

  // Group station indices by operator name → cluster decals
  const operatorClusters = useMemo(() => {
    const map = new Map<string, number[]>()
    stations.forEach((s, i) => {
      if (!map.has(s.operator)) map.set(s.operator, [])
      map.get(s.operator)!.push(i)
    })
    return Array.from(map.entries()).map(([op, indices], ci) => ({ op, indices, ci }))
  }, [stations])

  return (
    <>
      {/* ── Lighting ── */}
      <ambientLight intensity={0.5} />
      {/* Key light: warm from top-right-front */}
      <directionalLight
        position={[10, 18, 10]}
        intensity={1.1}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-camera-near={0.5}
        shadow-camera-far={80}
        shadow-camera-left={-20}
        shadow-camera-right={20}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
      />
      {/* Fill light: cool blue-purple from top-left-back */}
      <directionalLight position={[-8, 10, -8]} intensity={0.30} color="#c7d2fe" />

      {/* ── Factory floor grid ── */}
      <gridHelper
        args={[gridSize, gridDivisions, '#1e293b', '#0f172a']}
        position={[centerX, 0, 0]}
      />

      {/* ── Takt reference plane ── */}
      <TaktPlane centerX={centerX} stationCount={stations.length} />

      {/* ── Operator cluster decals ── */}
      {operatorClusters.map(({ op, indices, ci }) => {
        const clusterLabel = indices.length > 1
          ? `${op} · ${indices.length} stations`
          : op
        return (
          <OperatorCluster
            key={op}
            indices={indices}
            colorIndex={ci}
            label={clusterLabel}
          />
        )
      })}

      {/* ── Workstation nodes ── */}
      {stations.map((s, i) => (
        <WorkstationNode
          key={s.id}
          station={s}
          posX={i * SPACING}
          isBottleneck={s.id === bottleneckId}
          taktTime={taktTime}
          isHovered={hoveredId === s.id}
          onHover={setHoveredId}
        />
      ))}
    </>
  )
}

// ─── Telemetry Status Chip (Phase 7) ─────────────────────────────────────────

const _STATUS_STYLE: Record<string, { dot: string; label: string }> = {
  connected:    { dot: '#22c55e', label: 'IoT Live' },
  connecting:   { dot: '#f59e0b', label: 'IoT Connecting…' },
  disconnected: { dot: '#ef4444', label: 'IoT Offline' },
  disabled:     { dot: '#475569', label: 'IoT Disabled' },
}

function TelemetryStatusChip({ status }: { status: string }) {
  const style = _STATUS_STYLE[status] ?? _STATUS_STYLE.disabled
  return (
    <div
      className="absolute top-3 right-3 flex items-center gap-1.5 rounded border border-gray-700/70 bg-gray-900/85 px-2.5 py-1 backdrop-blur-sm pointer-events-none z-10"
      style={{ fontSize: 10, fontFamily: 'monospace' }}
    >
      <span
        style={{
          display: 'inline-block',
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: style.dot,
          boxShadow: status === 'connected' ? `0 0 5px ${style.dot}` : 'none',
        }}
      />
      <span style={{ color: '#94a3b8' }}>{style.label}</span>
    </div>
  )
}

// ─── KPI Overlay (DOM, absolute-positioned over the Canvas) ──────────────────

function KpiOverlay({
  result,
  taktTime,
}: {
  result: LineBalanceResponse
  taktTime: number
}) {
  const report = result.balance_report
  const effPct = report?.balance_efficiency_pct
  const lossPct = report?.balance_loss_pct
  const effColor = effPct == null
    ? '#94a3b8'
    : effPct >= 85 ? '#22c55e' : effPct >= 70 ? '#f59e0b' : '#ef4444'

  type Chip = { label: string; value: string; color?: string }
  const chips: Chip[] = [
    { label: 'CT', value: `${result.cycle_time.toFixed(2)}s` },
    { label: 'TAKT', value: `${taktTime}s`, color: '#06b6d4' },
    { label: 'UPH', value: result.uph.toString() },
    ...(effPct != null
      ? [{ label: 'EFF', value: `${effPct.toFixed(1)}%`, color: effColor }]
      : []),
    ...(lossPct != null
      ? [{ label: 'LOSS', value: `${lossPct.toFixed(1)}%` }]
      : []),
  ]

  return (
    <div className="absolute top-3 left-3 flex flex-wrap gap-1.5 pointer-events-none z-10">
      {chips.map(({ label, value, color }) => (
        <div
          key={label}
          className="rounded border border-gray-700/70 bg-gray-900/85 px-2.5 py-1 backdrop-blur-sm"
          style={{ fontSize: 11, fontFamily: 'monospace' }}
        >
          <span style={{ color: '#475569' }}>{label} </span>
          <span style={{ color: color ?? '#f1f5f9', fontWeight: 600 }}>{value}</span>
        </div>
      ))}
    </div>
  )
}

// ─── DigitalTwinView (exported) ───────────────────────────────────────────────

export interface DigitalTwinViewProps {
  result: LineBalanceResponse
  taktTime: number
}

export function DigitalTwinView({ result, taktTime }: DigitalTwinViewProps) {
  const stationCount = result.station_results.length

  // Phase 7: open telemetry WebSocket once at top of tree; status for UI chip
  const telemetryStatus: TelemetryStatus = useTelemetry()

  if (stationCount === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-gray-500 text-sm">
        No station results to visualize.
      </div>
    )
  }

  const centerX = ((stationCount - 1) * SPACING) / 2
  // Camera sits at an equal isometric offset on X, Y, Z from the scene centre
  const camDist = Math.max(10, stationCount * 2.2)
  const zoom = Math.max(28, Math.min(72, 200 / stationCount))

  return (
    <div className="relative w-full rounded-xl overflow-hidden" style={{ height: 460, background: '#080c18' }}>
      {/* DOM KPI chips overlay */}
      <KpiOverlay result={result} taktTime={taktTime} />

      {/* Phase 7: IoT telemetry connection status chip */}
      <TelemetryStatusChip status={telemetryStatus} />

      {/* Legend */}
      <div className="absolute bottom-8 right-3 pointer-events-none flex flex-col gap-1 z-10">
        {[
          { color: '#22d3ee', label: 'Normal' },
          { color: '#f59e0b', label: 'Bottleneck' },
          { color: '#ef4444', label: 'Overloaded' },
          { color: '#f97316', label: '1P2M machine' },
          { color: '#22c55e', label: '⚡ IoT ok flash' },
          { color: '#ef4444', label: '⚡ IoT error flash' },
        ].map(({ color, label }) => (
          <div
            key={label}
            className="flex items-center gap-2 rounded border border-gray-700/60 bg-gray-900/80 px-2 py-0.5 backdrop-blur-sm"
            style={{ fontSize: 10, fontFamily: 'system-ui, sans-serif' }}
          >
            <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: color, flexShrink: 0 }} />
            <span style={{ color: '#94a3b8' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Hint */}
      <p className="absolute bottom-2 left-1/2 -translate-x-1/2 text-[10px] text-gray-600 pointer-events-none z-10 whitespace-nowrap">
        Drag to orbit · Scroll to zoom · Hover station for details
      </p>

      {/* R3F Canvas — orthographic isometric */}
      <Canvas
        shadows
        gl={{ antialias: true, alpha: false }}
        orthographic
        camera={{
          position: [centerX + camDist, camDist * 0.9, camDist],
          zoom,
          near: 0.1,
          far: 500,
        }}
      >
        <OrbitControls
          target={[centerX, 2.0, 0]}
          enablePan
          enableZoom
          enableRotate
          minZoom={15}
          maxZoom={220}
          makeDefault
        />
        <Scene result={result} taktTime={taktTime} />
      </Canvas>
    </div>
  )
}
