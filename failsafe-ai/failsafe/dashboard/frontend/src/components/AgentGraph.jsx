import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { IconNodes } from './Icons.jsx';

const THEME = {
  edgeInactive: '#cbd5e1',
  edgePass: '#16a34a',
  edgeFail: '#dc2626',
  edgeMixed: '#ca8a04',
  labelText: '#64748b',
  labelBg: '#ffffff',
  canvasBg: '#f1f3f9',
  gridDots: '#e2e8f0',
  controlsBg: '#ffffff',
  controlsBorder: '#e2e8f0',
};

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
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none' }} />
      <Handle type="target" position={Position.Left} id="left-target" style={{ background: 'transparent', border: 'none' }} />
      <div className="node-label">{data.label}</div>
      {data.description && (
        <div className="node-meta">{data.description}</div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none' }} />
      <Handle type="source" position={Position.Right} id="right-source" style={{ background: 'transparent', border: 'none' }} />
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
  if (!stats) return THEME.edgeInactive;
  if (stats.fail === 0) return THEME.edgePass;
  if (stats.pass === 0) return THEME.edgeFail;
  return THEME.edgeMixed;
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
        labelStyle: { fill: THEME.labelText, fontSize: 11 },
        labelBgStyle: { fill: THEME.labelBg, fillOpacity: 0.9 },
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
        <h2>System Map</h2>
        <p>Live view of your agents and how they connect. Color reflects recent health.</p>
      </div>
      <div className="card">
        <div className="graph-container">
          {initialNodes.length === 0 ? (
            <div className="empty-state" style={{ paddingTop: 120 }}>
              <div className="empty-state-icon"><IconNodes size={36} /></div>
              <p className="empty-state-title">No agents registered</p>
              <p className="empty-state-desc">Start FailSafe with agents and contracts to see them mapped here.</p>
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
              style={{ background: THEME.canvasBg }}
            >
              <Background color={THEME.gridDots} gap={20} />
              <Controls
                style={{ background: THEME.controlsBg, borderColor: THEME.controlsBorder }}
              />
            </ReactFlow>
          )}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
        <span><span style={{ color: THEME.edgePass }}>{'\u25CF'}</span> Healthy</span>
        <span><span style={{ color: THEME.edgeMixed }}>{'\u25CF'}</span> Warnings</span>
        <span><span style={{ color: THEME.edgeFail }}>{'\u25CF'}</span> Errors</span>
        <span style={{ marginLeft: 'auto' }}>
          Edges: <span style={{ color: THEME.edgePass }}>green</span>=passing,{' '}
          <span style={{ color: THEME.edgeMixed }}>yellow</span>=mixed,{' '}
          <span style={{ color: THEME.edgeFail }}>red</span>=failing
        </span>
      </div>
    </div>
  );
}
