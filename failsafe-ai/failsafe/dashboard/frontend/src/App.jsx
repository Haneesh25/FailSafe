import React, { useState, useEffect, useCallback } from 'react';
import './styles.css';
import useWebSocket from './hooks/useWebSocket.js';
import AgentGraph from './components/AgentGraph.jsx';
import ValidationStream from './components/ValidationStream.jsx';
import InteractionLog from './components/InteractionLog.jsx';
import ContractCoverage from './components/ContractCoverage.jsx';
import ContractDetail from './components/ContractDetail.jsx';
import ViolationDetail from './components/ViolationDetail.jsx';

const NAV_ITEMS = [
  { id: 'graph',      label: 'Agent Graph',       icon: '\u29BF' },
  { id: 'stream',     label: 'Live Stream',        icon: '\u25C9' },
  { id: 'log',        label: 'Interaction Log',    icon: '\u2630' },
  { id: 'coverage',   label: 'Contract Coverage',  icon: '\u25A6' },
  { id: 'contracts',  label: 'Contracts',          icon: '\u2702' },
];

function getWsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws`;
}

export default function App() {
  const [page, setPage] = useState('graph');
  const [detail, setDetail] = useState(null); // {type: 'contract'|'violation', data}
  const { events, connected, clearEvents } = useWebSocket(getWsUrl());

  // ---- API fetchers ----
  const [agents, setAgents] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [coverage, setCoverage] = useState({});
  const [validations, setValidations] = useState([]);

  const fetchAll = useCallback(async () => {
    try {
      const [ag, co, gr, cv, va] = await Promise.all([
        fetch('/api/agents').then(r => r.ok ? r.json() : []),
        fetch('/api/contracts').then(r => r.ok ? r.json() : []),
        fetch('/api/graph').then(r => r.ok ? r.json() : { nodes: [], edges: [] }),
        fetch('/api/coverage').then(r => r.ok ? r.json() : {}),
        fetch('/api/validations?limit=200').then(r => r.ok ? r.json() : []),
      ]);
      setAgents(ag);
      setContracts(co);
      setGraphData(gr);
      setCoverage(cv);
      setValidations(va);
    } catch {
      // API not available yet
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // Navigation handlers that support detail views
  const openContract = useCallback((contract) => {
    setDetail({ type: 'contract', data: contract });
  }, []);

  const openViolation = useCallback((validationId) => {
    setDetail({ type: 'violation', data: validationId });
  }, []);

  const closeDetail = useCallback(() => {
    setDetail(null);
  }, []);

  // ---- Render current page ----
  function renderPage() {
    if (detail) {
      if (detail.type === 'contract') {
        return <ContractDetail contract={detail.data} onBack={closeDetail} />;
      }
      if (detail.type === 'violation') {
        return <ViolationDetail validationId={detail.data} onBack={closeDetail} />;
      }
    }

    switch (page) {
      case 'graph':
        return (
          <AgentGraph
            graphData={graphData}
            events={events}
            onNodeClick={(agent) => {/* future: agent detail */}}
          />
        );
      case 'stream':
        return (
          <ValidationStream
            events={events}
            onClear={clearEvents}
            onViolationClick={openViolation}
          />
        );
      case 'log':
        return (
          <InteractionLog
            validations={validations}
            onRowClick={openViolation}
            onContractClick={openContract}
            contracts={contracts}
          />
        );
      case 'coverage':
        return (
          <ContractCoverage
            coverage={coverage}
            contracts={contracts}
            onCellClick={openContract}
          />
        );
      case 'contracts':
        return (
          <div>
            <div className="page-header">
              <h2>Contracts</h2>
              <p>All registered handoff contracts</p>
            </div>
            {contracts.length === 0 ? (
              <div className="empty-state">
                <div className="icon">{'\u2702'}</div>
                <p>No contracts registered yet.</p>
              </div>
            ) : (
              <div className="card">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Source</th>
                        <th>Target</th>
                        <th>Mode</th>
                        <th>Rules</th>
                        <th>NL Rules</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contracts.map((c) => (
                        <tr
                          key={c.name}
                          className="clickable"
                          onClick={() => openContract(c)}
                        >
                          <td style={{ fontWeight: 600, color: 'var(--cyan)' }}>{c.name}</td>
                          <td>{c.source}</td>
                          <td>{c.target}</td>
                          <td>
                            <span className={`badge ${c.mode === 'block' ? 'badge-fail' : 'badge-warn'}`}>
                              {c.mode}
                            </span>
                          </td>
                          <td>{c.rules?.length || 0}</td>
                          <td>{c.nl_rules?.length || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          <h1>FailSafe AI</h1>
          <span>Dashboard</span>
        </div>
        <div className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={page === item.id && !detail ? 'active' : ''}
              onClick={() => { setDetail(null); setPage(item.id); }}
            >
              <span className="icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="ws-status">
            <span className={`ws-dot ${connected ? 'connected' : 'disconnected'}`} />
            {connected ? 'WebSocket connected' : 'Disconnected'}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
            {events.length} events | {agents.length} agents
          </div>
        </div>
      </nav>

      {/* Main */}
      <main className="main-content">
        {renderPage()}
      </main>
    </div>
  );
}
