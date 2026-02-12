import React, { useState, useMemo } from 'react';

/**
 * Filterable table of all handoff validations.
 * Columns: timestamp, source, target, contract, status, violations, trace_id.
 * Rows are clickable.
 */
export default function InteractionLog({ validations, onRowClick, onContractClick, contracts }) {
  const [filterSource, setFilterSource] = useState('');
  const [filterTarget, setFilterTarget] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterTrace, setFilterTrace] = useState('');

  // Unique agents from validations
  const agents = useMemo(() => {
    const set = new Set();
    for (const v of validations) {
      if (v.source) set.add(v.source);
      if (v.target) set.add(v.target);
    }
    return Array.from(set).sort();
  }, [validations]);

  const filtered = useMemo(() => {
    return validations.filter((v) => {
      if (filterSource && v.source !== filterSource) return false;
      if (filterTarget && v.target !== filterTarget) return false;
      if (filterStatus === 'passed' && !v.passed) return false;
      if (filterStatus === 'failed' && v.passed) return false;
      if (filterTrace && !v.trace_id?.includes(filterTrace)) return false;
      return true;
    });
  }, [validations, filterSource, filterTarget, filterStatus, filterTrace]);

  const formatTime = (ts) => {
    if (!ts) return '-';
    try {
      const d = new Date(ts);
      return d.toLocaleString('en-US', { hour12: false, month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return ts;
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>Interaction Log</h2>
        <p>All recorded handoff validations from the audit log</p>
      </div>

      <div className="filter-bar">
        <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}>
          <option value="">All Sources</option>
          {agents.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={filterTarget} onChange={(e) => setFilterTarget(e.target.value)}>
          <option value="">All Targets</option>
          {agents.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
          <option value="all">All Status</option>
          <option value="passed">Passed</option>
          <option value="failed">Failed</option>
        </select>
        <input
          type="text"
          placeholder="Filter by trace ID..."
          value={filterTrace}
          onChange={(e) => setFilterTrace(e.target.value)}
          style={{ minWidth: 200 }}
        />
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
          {filtered.length} of {validations.length} records
        </span>
      </div>

      <div className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Source</th>
                <th>Target</th>
                <th>Contract</th>
                <th>Status</th>
                <th>Mode</th>
                <th>Duration</th>
                <th>Trace ID</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', padding: 32, color: 'var(--text-muted)' }}>
                    No records match the current filters.
                  </td>
                </tr>
              ) : (
                filtered.map((v, i) => {
                  const passed = v.passed === 1 || v.passed === true;
                  return (
                    <tr
                      key={v.handoff_id || i}
                      className="clickable"
                      onClick={() => {
                        if (!passed && onRowClick) {
                          onRowClick(v.handoff_id);
                        }
                      }}
                    >
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {formatTime(v.timestamp)}
                      </td>
                      <td style={{ fontWeight: 500 }}>{v.source}</td>
                      <td style={{ fontWeight: 500 }}>{v.target}</td>
                      <td>
                        {v.contract_name ? (
                          <span
                            style={{ color: 'var(--cyan)', cursor: 'pointer' }}
                            onClick={(e) => {
                              e.stopPropagation();
                              const c = contracts.find(c => c.name === v.contract_name);
                              if (c && onContractClick) onContractClick(c);
                            }}
                          >
                            {v.contract_name}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>none</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${passed ? 'badge-pass' : 'badge-fail'}`}>
                          {passed ? 'PASS' : 'FAIL'}
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {v.mode || '-'}
                        </span>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {v.duration_ms != null ? `${v.duration_ms.toFixed(1)}ms` : '-'}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {v.trace_id ? v.trace_id.substring(0, 12) + '...' : '-'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
