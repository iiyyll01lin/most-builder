import { useCallback, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  Position,
  MarkerType,
  BackgroundVariant,
} from '@xyflow/react'
import dagre from 'dagre'
import '@xyflow/react/dist/style.css'
import type { PrecedenceGraph } from '@/api/types'

// ─── Dagre layout helpers ─────────────────────────────────────────────────────

const NODE_W = 220
const NODE_H = 80

function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'LR',
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 })
  g.setDefaultEdgeLabel(() => ({}))

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))

  dagre.layout(g)

  return {
    nodes: nodes.map((n) => {
      const { x, y } = g.node(n.id)
      return {
        ...n,
        targetPosition: Position.Left,
        sourcePosition: Position.Right,
        position: { x: x - NODE_W / 2, y: y - NODE_H / 2 },
      }
    }),
    edges,
  }
}

// ─── Custom node ──────────────────────────────────────────────────────────────

interface NodeData extends Record<string, unknown> {
  label: string
  adjustedCt: number
  mainSeq?: string
  isCycleNode: boolean
  status?: string
}

function PrecedenceNodeComponent({ data }: { data: NodeData }) {
  return (
    <div
      className={[
        'flex flex-col gap-1 rounded-lg border px-3 py-2 text-xs shadow-lg transition-colors',
        'w-[220px] min-h-[80px]',
        data.isCycleNode
          ? 'border-red-500 bg-red-950/70 text-red-200'
          : 'border-gray-600 bg-gray-800/90 text-gray-100',
      ].join(' ')}
    >
      <div className="flex items-center justify-between gap-1">
        {data.mainSeq && (
          <span className="rounded bg-cyan-900/60 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
            SEQ {data.mainSeq}
          </span>
        )}
        {data.isCycleNode && (
          <span className="ml-auto rounded bg-red-800 px-1.5 py-0.5 text-[10px] text-red-100">
            ⚠ CYCLE
          </span>
        )}
        {data.status && !data.isCycleNode && (
          <span className="ml-auto rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-300">
            {data.status}
          </span>
        )}
      </div>
      <p className="line-clamp-2 font-medium leading-snug">{data.label}</p>
      <p className="mt-auto text-gray-400">
        CT: <span className="text-amber-300">{data.adjustedCt.toFixed(2)}s</span>
      </p>
    </div>
  )
}

const nodeTypes = { precedence: PrecedenceNodeComponent }

// ─── Main component ───────────────────────────────────────────────────────────

interface PrecedenceGraphViewerProps {
  graph: PrecedenceGraph
}

export function PrecedenceGraphViewer({ graph }: PrecedenceGraphViewerProps) {
  const hasCycle = graph.cycle_errors.length > 0

  // Collect action IDs that are part of any cycle error message
  const cycleNodeIds = useMemo<Set<string>>(() => {
    if (!hasCycle) return new Set()
    const ids = new Set<string>()
    graph.cycle_errors.forEach((errMsg) => {
      // The error format: "Precedence cycle detected involving action(s): id1, id2, ..."
      const match = errMsg.match(/action\(s\):\s*(.+)\.\s*A cyclic/)
      if (match) {
        match[1].split(',').forEach((id) => ids.add(id.trim()))
      }
    })
    // Also flag any node referenced in a cycle edge (in_degree > 0 after topological sort).
    // Since we don't re-run the algorithm, fall back to marking all graph nodes if extraction fails.
    if (ids.size === 0) graph.nodes.forEach((n) => ids.add(n.id))
    return ids
  }, [hasCycle, graph.cycle_errors, graph.nodes])

  const initialNodes = useMemo<Node[]>(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: 'precedence',
        position: { x: 0, y: 0 },
        data: {
          label: n.description,
          adjustedCt: n.adjusted_ct,
          mainSeq: n.main_seq,
          isCycleNode: cycleNodeIds.has(n.id),
          status: n.status_label,
        } satisfies NodeData,
      })),
    [graph.nodes, cycleNodeIds],
  )

  const initialEdges = useMemo<Edge[]>(
    () =>
      graph.precedence_edges.map((e, i) => ({
        id: `e-${i}-${e.from}-${e.to}`,
        source: e.from,
        target: e.to,
        label: e.type === 'main' ? 'main' : undefined,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#6b7280' },
        style: {
          stroke: cycleNodeIds.has(e.from) && cycleNodeIds.has(e.to)
            ? '#ef4444'
            : '#6b7280',
          strokeWidth: 1.5,
        },
        labelStyle: { fill: '#9ca3af', fontSize: 10 },
        labelBgStyle: { fill: '#1f2937' },
      })),
    [graph.precedence_edges, cycleNodeIds],
  )

  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(
    () => applyDagreLayout(initialNodes, initialEdges, 'LR'),
    [initialNodes, initialEdges],
  )

  const [nodes, , onNodesChange] = useNodesState(layoutNodes)
  const [edges, , onEdgesChange] = useEdgesState(layoutEdges)

  const onInit = useCallback(
    (instance: { fitView: () => void }) => instance.fitView(),
    [],
  )

  return (
    <div className="flex flex-col gap-2">
      {hasCycle && (
        <div className="rounded-lg border border-red-700 bg-red-950/50 p-3 text-sm text-red-300">
          <p className="font-semibold">⚠ Precedence Cycle Detected</p>
          {graph.cycle_errors.map((err, i) => (
            <p key={i} className="mt-1 text-xs text-red-400">
              {err}
            </p>
          ))}
        </div>
      )}
      <div className="h-[520px] w-full overflow-hidden rounded-xl border border-gray-700 bg-gray-900/60">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={onInit}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="#374151"
          />
          <Controls className="[&_button]:bg-gray-700 [&_button]:border-gray-600 [&_button]:text-gray-300" />
          <MiniMap
            nodeColor={(n) =>
              (n.data as NodeData).isCycleNode ? '#ef444480' : '#1f293780'
            }
            maskColor="#0a0e1a80"
            style={{ background: '#111827', border: '1px solid #374151' }}
          />
        </ReactFlow>
      </div>
      <div className="flex justify-between text-xs text-gray-500">
        <span>{graph.nodes.length} nodes · {graph.precedence_edges.length} edges</span>
        <span>
          Total CT:{' '}
          <span className="text-amber-300">
            {graph.total_effective_ct.toFixed(2)}s
          </span>
        </span>
      </div>
    </div>
  )
}
