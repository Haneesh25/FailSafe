import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './styles.css';
import useEventStream from './hooks/useEventStream.js';
import Overview from './components/Overview.jsx';
import AgentGraph from './components/AgentGraph.jsx';
import ValidationStream from './components/ValidationStream.jsx';
import InteractionLog from './components/InteractionLog.jsx';
import ContractCoverage from './components/ContractCoverage.jsx';
import ContractDetail from './components/ContractDetail.jsx';
import ViolationDetail from './components/ViolationDetail.jsx';
import HandoffDetail from './components/HandoffDetail.jsx';
import DataFlow from './components/DataFlow.jsx';
import { IconGrid, IconNodes, IconActivity, IconClock, IconShield, IconFile, IconDataFlow } from './components/Icons.jsx';

const NAV_ITEMS = [
  { id: 'overview',   label: 'Overview',       Icon: IconGrid },
  { id: 'graph',      label: 'System Map',     Icon: IconNodes },
  { id: 'stream',     label: 'Live Activity',  Icon: IconActivity },
  { id: 'dataflow',   label: 'Data Flow',      Icon: IconDataFlow },
  { id: 'log',        label: 'History',         Icon: IconClock },
  { id: 'coverage',   label: 'Coverage',        Icon: IconShield },
  { id: 'contracts',  label: 'Contracts',       Icon: IconFile },
];

function getStreamUrl() {
  return `${window.location.origin}/api/stream`;
}

export default function App() {
  const [page, setPage] = useState('overview');
  const [detail, setDetail] = useState(null);
  const { events, connected, clearEvents } = useEventStream(getStreamUrl());

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

  // Failure count for nav badge
  const recentFailureCount = useMemo(() => {
    return events.filter(e => e.type === 'validation' && !(e.data?.passed ?? e.passed)).length;
  }, [events]);

  // Navigation handlers
  const openContract = useCallback((contract) => {
    setDetail({ type: 'contract', data: contract });
  }, []);

  const openHandoff = useCallback((event) => {
    setDetail({ type: 'handoff', data: event });
  }, []);

  const openViolation = useCallback((validationId) => {
    setDetail({ type: 'violation', data: validationId });
  }, []);

  const closeDetail = useCallback(() => {
    setDetail(null);
  }, []);

  const navigateTo = useCallback((pageId) => {
    setDetail(null);
    setPage(pageId);
  }, []);

  // ---- Render current page ----
  function renderPage() {
    if (detail) {
      if (detail.type === 'handoff') {
        return <HandoffDetail event={detail.data} events={events} onBack={closeDetail} onNavigate={navigateTo} />;
      }
      if (detail.type === 'contract') {
        return <ContractDetail contract={detail.data} onBack={closeDetail} />;
      }
      if (detail.type === 'violation') {
        return <ViolationDetail validationId={detail.data} onBack={closeDetail} />;
      }
    }

    switch (page) {
      case 'overview':
        return (
          <Overview
            agents={agents}
            validations={validations}
            events={events}
            coverage={coverage}
            contracts={contracts}
            connected={connected}
            onNavigate={navigateTo}
            onHandoffClick={openHandoff}
            onContractClick={openContract}
          />
        );
      case 'graph':
        return (
          <AgentGraph
            graphData={graphData}
            events={events}
            onContractClick={openContract}
            onHandoffClick={openHandoff}
          />
        );
      case 'stream':
        return (
          <ValidationStream
            events={events}
            onClear={clearEvents}
            onHandoffClick={openHandoff}
          />
        );
      case 'dataflow':
        return (
          <DataFlow events={events} onHandoffClick={openHandoff} />
        );
      case 'log':
        return (
          <InteractionLog
            validations={validations}
            onRowClick={openHandoff}
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
              <p>Rules governing data passed between agents</p>
            </div>
            {contracts.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon"><IconFile size={36} /></div>
                <p className="empty-state-title">No contracts yet</p>
                <p className="empty-state-desc">Contracts define validation rules for agent handoffs. Register your first contract to start monitoring.</p>
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
              onClick={() => navigateTo(item.id)}
            >
              <span className="nav-icon"><item.Icon size={16} /></span>
              {item.label}
              {item.id === 'stream' && recentFailureCount > 0 && (
                <span className="nav-badge">{recentFailureCount > 99 ? '99+' : recentFailureCount}</span>
              )}
            </button>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="ws-status">
            <span className={`ws-dot ${connected ? 'connected' : 'disconnected'}`} />
            {connected
              ? (recentFailureCount === 0 ? 'All systems healthy' : `${recentFailureCount} issue${recentFailureCount !== 1 ? 's' : ''} detected`)
              : 'Reconnecting...'
            }
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
            {agents.length} agents {' \u00b7 '} {contracts.length} contracts
          </div>
        </div>
      </nav>

      <main className="main-content">
        {renderPage()}
      </main>
    </div>
  );
}
