import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

/**
 * Custom node component for agents.
 */
function AgentNode({ data }) {
  const statusClass = data.status === 'error'
    ? 'status-error'
    : data.status === 'warning'
    ? 'status-warning'
    : 'status-healthy';

  return (
    <div className={`agent-node ${statusClass}`}>
      <div className="node-label">{data.label}</div>
      {data.description && (
        <div className="node-meta">{data.description}</div>
      )}
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode };

/**
 * Derive agent health status from recent WS events.
 */
function deriveAgentStatuses(events) {
  const statuses = {};
  // Look at the most recent 100 events
  const recent = events.slice(-100);
  for (const evt of recent) {
    if (evt.type !== 'validation') continue;
    const d = evt.data || evt;
    const src = d.source;
    const tgt = d.target;
    if (!d.passed) {
      const severity = (d.violations || []).some(v => v.severity === 'critical' || v.severity === 'high')
        ? 'error'
        : 'warning';
      statuses[src] = severity === 'error' ? 'error' : (statuses[src] === 'error' ? 'error' : severity);
      statuses[tgt] = severity === 'error' ? 'error' : (statuses[tgt] === 'error' ? 'error' : severity);
    }
  }
  return statuses;
}

/**
 * Derive edge health from recent events.
 */
function deriveEdgeStatuses(events) {
  const edgeStats = {}; // key: source->target, value: {pass, fail}
  const recent = events.slice(-100);
  for (const evt of recent) {
    if (evt.type !== 'validation') continue;
    const d = evt.data || evt;
    const key = `${d.source}->${d.target}`;
    if (!edgeStats[key]) edgeStats[key] = { pass: 0, fail: 0 };
    if (d.passed) edgeStats[key].pass++;
    else edgeStats[key].fail++;
  }
  return edgeStats;
}

function getEdgeColor(edgeStats, source, target) {
  const key = `${source}->${target}`;
  const stats = edgeStats[key];
  if (!stats) return '#475569'; // gray, no activity
  if (stats.fail === 0) return '#22c55e'; // green, all passing
  if (stats.pass === 0) return '#ef4444'; // red, all failing
  return '#eab308'; // yellow, mixed
}

/**
 * Auto-layout nodes in a force-directed-like grid.
 */
function layoutNodes(rawNodes) {
  const count = rawNodes.length;
  if (count === 0) return [];

  const cols = Math.ceil(Math.sqrt(count));
  const spacingX = 220;
  const spacingY = 140;

  return rawNodes.map((node, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return {
      ...node,
      position: { x: 80 + col * spacingX, y: 80 + row * spacingY },
    };
  });
}

export default function AgentGraph({ graphData, events, onNodeClick }) {
  const agentStatuses = useMemo(() => deriveAgentStatuses(events), [events]);
  const edgeStats = useMemo(() => deriveEdgeStatuses(events), [events]);

  const initialNodes = useMemo(() => {
    const raw = (graphData.nodes || []).map((n) => ({
      id: n.id,
      type: 'agentNode',
      data: {
        label: n.label || n.id,
        description: n.data?.description || '',
        status: agentStatuses[n.id] || 'healthy',
      },
    }));
    return layoutNodes(raw);
  }, [graphData.nodes, agentStatuses]);

  const initialEdges = useMemo(() => {
    return (graphData.edges || []).map((e) => {
      const color = getEdgeColor(edgeStats, e.source, e.target);
      return {
        id: e.id || `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.label || '',
        animated: true,
        style: { stroke: color, strokeWidth: 2 },
        labelStyle: { fill: '#94a3b8', fontSize: 11 },
        labelBgStyle: { fill: '#1a1f2e', fillOpacity: 0.9 },
        labelBgPadding: [6, 3],
        labelBgBorderRadius: 3,
        markerEnd: { type: MarkerType.ArrowClosed, color },
      };
    });
  }, [graphData.edges, edgeStats]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  React.useEffect(() => { setNodes(initialNodes); }, [initialNodes, setNodes]);
  React.useEffect(() => { setEdges(initialEdges); }, [initialEdges, setEdges]);

  const onNodeClickHandler = useCallback((_, node) => {
    if (onNodeClick) onNodeClick(node.data);
  }, [onNodeClick]);

  return (
    <div>
      <div className="page-header">
        <h2>Agent Dependency Graph</h2>
        <p>Live view of agents and handoff connections. Color reflects recent validation health.</p>
      </div>
      <div className="card">
        <div className="graph-container">
          {initialNodes.length === 0 ? (
            <div className="empty-state" style={{ paddingTop: 120 }}>
              <div className="icon">{'\u29BF'}</div>
              <p>No agents registered yet. Start FailSafe with agents and contracts to see the graph.</p>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeClick={onNodeClickHandler}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.3 }}
              proOptions={{ hideAttribution: true }}
              style={{ background: '#111827' }}
            >
              <Background color="#1e293b" gap={20} />
              <Controls
                style={{ background: '#1a1f2e', borderColor: '#334155' }}
              />
            </ReactFlow>
          )}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
        <span><span style={{ color: '#22c55e' }}>{'\u25CF'}</span> Healthy</span>
        <span><span style={{ color: '#eab308' }}>{'\u25CF'}</span> Warnings</span>
        <span><span style={{ color: '#ef4444' }}>{'\u25CF'}</span> Errors</span>
        <span style={{ marginLeft: 'auto' }}>
          Edges: <span style={{ color: '#22c55e' }}>green</span>=passing,{' '}
          <span style={{ color: '#eab308' }}>yellow</span>=mixed,{' '}
          <span style={{ color: '#ef4444' }}>red</span>=failing
        </span>
      </div>
    </div>
  );
}
