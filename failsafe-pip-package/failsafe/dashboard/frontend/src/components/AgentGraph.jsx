import React, { useMemo, useCallback, useState, useEffect, useRef } from 'react';
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
import { IconNodes, IconFile } from './Icons.jsx';

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

/* ------------------------------------------------------------------ */
/*  Custom node: Agent                                                 */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/*  Custom node: Contract (pill between agents)                        */
/* ------------------------------------------------------------------ */

function ContractNode({ data }) {
  return (
    <div className="contract-node">
      <Handle type="target" position={Position.Top} style={{ background: 'transparent', border: 'none' }} />
      <Handle type="target" position={Position.Left} id="left-target" style={{ background: 'transparent', border: 'none' }} />
      <IconFile size={11} />
      <span className="contract-node-label">{data.label}</span>
      <Handle type="source" position={Position.Bottom} style={{ background: 'transparent', border: 'none' }} />
      <Handle type="source" position={Position.Right} id="right-source" style={{ background: 'transparent', border: 'none' }} />
    </div>
  );
}

const nodeTypes = { agentNode: AgentNode, contractNode: ContractNode };

/* ------------------------------------------------------------------ */
/*  macOS-style agent detail popup                                     */
/* ------------------------------------------------------------------ */

function AgentPopup({ data, position, onClose }) {
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });

  const currentPos = {
    x: position.x + dragOffset.x,
    y: position.y + dragOffset.y,
  };

  const onTitleBarMouseDown = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - dragOffset.x, y: e.clientY - dragOffset.y };
  }, [dragOffset]);

  useEffect(() => {
    if (!isDragging) return;
    const onMouseMove = (e) => {
      setDragOffset({
        x: e.clientX - dragStartRef.current.x,
        y: e.clientY - dragStartRef.current.y,
      });
    };
    const onMouseUp = () => setIsDragging(false);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [isDragging]);

  return (
    <div
      className="macos-popup"
      style={{ left: currentPos.x, top: currentPos.y }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="macos-popup-titlebar" onMouseDown={onTitleBarMouseDown}>
        <div className="macos-traffic-lights">
          <button className="traffic-light traffic-red" onClick={onClose} title="Close" />
          <button className="traffic-light traffic-yellow" title="Minimize" />
          <button className="traffic-light traffic-green" title="Maximize" />
        </div>
        <span className="macos-popup-title">{data.label}</span>
      </div>
      <div className="macos-popup-body">
        <div className="macos-popup-section">
          <div className="macos-popup-field">
            <span className="macos-popup-field-label">Agent</span>
            <span className="macos-popup-field-value">{data.label}</span>
          </div>
          {data.description && (
            <div className="macos-popup-field">
              <span className="macos-popup-field-label">Description</span>
              <span className="macos-popup-field-value">{data.description}</span>
            </div>
          )}
          <div className="macos-popup-field">
            <span className="macos-popup-field-label">Status</span>
            <span className={`badge ${
              data.status === 'error' ? 'badge-fail' :
              data.status === 'warning' ? 'badge-warn' : 'badge-pass'
            }`}>
              {data.status}
            </span>
          </div>
        </div>
        {data.agentData && (
          <div className="macos-popup-section">
            {data.agentData.model && (
              <div className="macos-popup-field">
                <span className="macos-popup-field-label">Model</span>
                <span className="macos-popup-field-value" style={{ fontFamily: 'var(--font-mono)' }}>
                  {data.agentData.model}
                </span>
              </div>
            )}
            {data.agentData.capabilities && data.agentData.capabilities.length > 0 && (
              <div className="macos-popup-field">
                <span className="macos-popup-field-label">Capabilities</span>
                <span className="macos-popup-field-value">
                  {data.agentData.capabilities.join(', ')}
                </span>
              </div>
            )}
            {data.agentData.description && (
              <div className="macos-popup-field">
                <span className="macos-popup-field-label">Details</span>
                <span className="macos-popup-field-value">{data.agentData.description}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function deriveAgentStatuses(events) {
  const statuses = {};
  const recent = events.slice(-100);
  for (const evt of recent) {
    if (evt.type !== 'validation') continue;
    const d = evt.data || evt;
    if (!d.passed) {
      const severity = (d.violations || []).some(v => v.severity === 'critical' || v.severity === 'high')
        ? 'error' : 'warning';
      for (const name of [d.source, d.target]) {
        if (severity === 'error' || statuses[name] !== 'error') {
          statuses[name] = severity;
        }
      }
    }
  }
  return statuses;
}

function deriveEdgeStatuses(events) {
  const edgeStats = {};
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

function layoutNodes(rawNodes) {
  const count = rawNodes.length;
  if (count === 0) return [];

  const cols = Math.ceil(Math.sqrt(count));
  const spacingX = 300;
  const spacingY = 200;

  return rawNodes.map((node, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return {
      ...node,
      position: { x: 80 + col * spacingX, y: 80 + row * spacingY },
    };
  });
}

/**
 * Build graph with contract nodes inserted between agents.
 * Each original edge becomes: agent → contractNode → agent
 */
function buildGraph(graphNodes, graphEdges, agentStatuses, edgeStats) {
  const agentNodes = layoutNodes(
    (graphNodes || []).map((n) => ({
      id: n.id,
      type: 'agentNode',
      data: {
        label: n.label || n.id,
        description: n.data?.description || '',
        status: agentStatuses[n.id] || 'healthy',
        agentData: n.data,
      },
    }))
  );

  const posMap = {};
  for (const n of agentNodes) posMap[n.id] = n.position;

  const contractNodes = [];
  const edges = [];

  // Track duplicate source→target pairs to offset overlapping contract nodes
  const pairCount = {};

  for (const e of (graphEdges || [])) {
    const sourcePos = posMap[e.source];
    const targetPos = posMap[e.target];
    if (!sourcePos || !targetPos) continue;

    const pairKey = `${e.source}->${e.target}`;
    const idx = pairCount[pairKey] || 0;
    pairCount[pairKey] = idx + 1;

    const contractId = `contract__${e.id || pairKey}`;
    const midX = (sourcePos.x + targetPos.x) / 2;
    const midY = (sourcePos.y + targetPos.y) / 2 + idx * 30;

    contractNodes.push({
      id: contractId,
      type: 'contractNode',
      position: { x: midX, y: midY },
      data: {
        label: e.label || e.id,
        contract: e.data,
      },
    });

    const color = getEdgeColor(edgeStats, e.source, e.target);
    const edgeStyle = { stroke: color, strokeWidth: 2 };
    const marker = { type: MarkerType.ArrowClosed, color };
    const stats = edgeStats[`${e.source}->${e.target}`];
    const edgeLabel = stats ? `${stats.pass + stats.fail} handoffs, ${stats.fail} failures` : '';

    edges.push({
      id: `${e.source}__to__${contractId}`,
      source: e.source,
      target: contractId,
      animated: true,
      style: edgeStyle,
      markerEnd: marker,
      label: edgeLabel,
      labelStyle: { fontSize: 10, fill: THEME.labelText },
      labelBgStyle: { fill: THEME.labelBg, fillOpacity: 0.85 },
      labelBgPadding: [4, 2],
      labelBgBorderRadius: 3,
    });

    edges.push({
      id: `${contractId}__to__${e.target}`,
      source: contractId,
      target: e.target,
      animated: true,
      style: edgeStyle,
      markerEnd: marker,
    });
  }

  return {
    nodes: [...agentNodes, ...contractNodes],
    edges,
  };
}

/* ------------------------------------------------------------------ */
/*  Edge Payload Panel                                                 */
/* ------------------------------------------------------------------ */

function EdgePayloadPanel({ source, target, contract, events, onClose, onContractClick, onHandoffClick }) {
  const edgeEvents = useMemo(() => {
    return events.filter(
      (e) => e.type === 'validation' && e.data?.source === source && e.data?.target === target
    );
  }, [events, source, target]);

  const recentEvents = edgeEvents.slice(-20).reverse();

  const stats = useMemo(() => {
    const total = edgeEvents.length;
    const passed = edgeEvents.filter((e) => e.data?.passed).length;
    const passRate = total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0';
    const totalSize = edgeEvents.reduce((sum, e) => sum + (e.data?.payload_size || 0), 0);
    const avgSize = total > 0 ? Math.round(totalSize / total) : 0;
    return { total, passRate, avgSize };
  }, [edgeEvents]);

  const formatTime = (ts) => {
    if (!ts) return '--:--:--';
    try {
      return new Date(ts).toLocaleTimeString('en-US', { hour12: false });
    } catch {
      return ts;
    }
  };

  const ruleTypes = useMemo(() => {
    if (!contract?.rules || contract.rules.length === 0) return '';
    return contract.rules.map((r) => r.rule_type).join(', ');
  }, [contract]);

  return (
    <div className="edge-panel" onClick={(e) => e.stopPropagation()}>
      <div className="edge-panel-header">
        <div>
          <div className="edge-panel-title">{source} {'\u2192'} {target}</div>
          {contract && (
            <span
              style={{ fontSize: 12, color: 'var(--cyan)', cursor: 'pointer' }}
              onClick={() => onContractClick && onContractClick(contract)}
            >
              {contract.name}
            </span>
          )}
        </div>
        <button className="edge-panel-close" onClick={onClose}>{'\u2715'}</button>
      </div>

      {contract && (
        <div className="edge-panel-section">
          <h4>Contract</h4>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className={`badge ${contract.mode === 'block' ? 'badge-fail' : 'badge-warn'}`}>
              {contract.mode}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {contract.rules?.length || 0} rules
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {contract.nl_rules?.length || 0} NL rules
            </span>
          </div>
          {ruleTypes && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, fontFamily: 'var(--font-mono)' }}>
              {ruleTypes}
            </div>
          )}
        </div>
      )}

      <div className="edge-panel-section" style={{ padding: '8px 16px' }}>
        <h4>Recent Payloads ({recentEvents.length})</h4>
      </div>

      <div className="edge-panel-body">
        {recentEvents.length === 0 ? (
          <div style={{ padding: '16px 8px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
            No handoffs recorded for this edge yet.
          </div>
        ) : (
          recentEvents.map((evt, i) => {
            const d = evt.data || evt;
            const preview = d.payload_preview
              ? (d.payload_preview.length > 60 ? d.payload_preview.substring(0, 60) + '...' : d.payload_preview)
              : '';
            return (
              <div
                key={d.trace_id || i}
                className="edge-payload-row"
                onClick={() => onHandoffClick && onHandoffClick(evt)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
                    {formatTime(d.timestamp || evt.timestamp)}
                  </span>
                  <span className={`badge ${d.passed ? 'badge-pass' : 'badge-fail'}`} style={{ fontSize: 10, padding: '1px 6px' }}>
                    {d.passed ? 'PASS' : 'FAIL'}
                  </span>
                  {d.payload_keys && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {d.payload_keys.length} keys
                    </span>
                  )}
                </div>
                {preview && (
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {preview}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div className="edge-panel-stats">
        <span>{stats.total} handoffs</span>
        <span>{stats.passRate}% pass</span>
        {stats.avgSize > 0 && <span>~{stats.avgSize}B avg</span>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                     */
/* ------------------------------------------------------------------ */

export default function AgentGraph({ graphData, events, onContractClick, onHandoffClick }) {
  const agentStatuses = useMemo(() => deriveAgentStatuses(events), [events]);
  const edgeStats = useMemo(() => deriveEdgeStatuses(events), [events]);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => buildGraph(graphData.nodes, graphData.edges, agentStatuses, edgeStats),
    [graphData.nodes, graphData.edges, agentStatuses, edgeStats]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync data changes while preserving user-dragged positions
  React.useEffect(() => {
    setNodes((prev) => {
      const posMap = {};
      for (const n of prev) posMap[n.id] = n.position;
      return initialNodes.map((n) => ({
        ...n,
        position: posMap[n.id] || n.position,
      }));
    });
  }, [initialNodes, setNodes]);

  React.useEffect(() => { setEdges(initialEdges); }, [initialEdges, setEdges]);

  // Popup & edge panel state
  const [popup, setPopup] = useState(null);
  const [edgePanel, setEdgePanel] = useState(null);
  const graphContainerRef = useRef(null);

  const onNodeClickHandler = useCallback((event, node) => {
    if (node.type === 'contractNode') {
      const contractData = node.data.contract;
      if (contractData) {
        setEdgePanel({
          source: contractData.source,
          target: contractData.target,
          contract: contractData,
        });
        setPopup(null);
      }
    } else if (node.type === 'agentNode') {
      const container = graphContainerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      setPopup({
        agentData: node.data,
        position: {
          x: Math.min(event.clientX - rect.left + 20, rect.width - 340),
          y: Math.max(event.clientY - rect.top - 40, 10),
        },
      });
    }
  }, []);

  const onPaneClick = useCallback(() => {
    setPopup(null);
    setEdgePanel(null);
  }, []);

  return (
    <div>
      <div className="page-header">
        <h2>System Map</h2>
        <p>Live view of your agents and how they connect. Color reflects recent health.</p>
      </div>
      <div className="card">
        <div className="graph-container" ref={graphContainerRef} style={{ position: 'relative' }}>
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
              onPaneClick={onPaneClick}
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

          {popup && (
            <AgentPopup
              data={popup.agentData}
              position={popup.position}
              onClose={() => setPopup(null)}
            />
          )}

          {edgePanel && (
            <EdgePayloadPanel
              source={edgePanel.source}
              target={edgePanel.target}
              contract={edgePanel.contract}
              events={events}
              onClose={() => setEdgePanel(null)}
              onContractClick={onContractClick}
              onHandoffClick={onHandoffClick}
            />
          )}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 20, marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
        <span><span style={{ color: THEME.edgePass }}>{'\u25CF'}</span> Healthy</span>
        <span><span style={{ color: THEME.edgeMixed }}>{'\u25CF'}</span> Warnings</span>
        <span><span style={{ color: THEME.edgeFail }}>{'\u25CF'}</span> Errors</span>
        <span style={{ marginLeft: 'auto' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><IconFile size={12} /> Contract node</span>
          {' \u00b7 '}Click agent for details
        </span>
      </div>
    </div>
  );
}
