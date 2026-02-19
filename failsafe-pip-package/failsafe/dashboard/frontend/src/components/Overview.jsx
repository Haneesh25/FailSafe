import React, { useMemo } from 'react';
import { IconCheckCircle, IconAlert, IconNodes, IconActivity, IconShield } from './Icons.jsx';

function formatTimeAgo(ts) {
  if (!ts) return '';
  try {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  } catch {
    return '';
  }
}

export default function Overview({
  agents, validations, events, coverage, contracts, connected,
  onNavigate, onViolationClick,
}) {
  const metrics = useMemo(() => {
    const total = validations.length;
    const passed = validations.filter(v => v.passed === 1 || v.passed === true).length;
    const failed = total - passed;
    const passRate = total > 0 ? ((passed / total) * 100).toFixed(1) : '0.0';
    const avgDuration = total > 0
      ? (validations.reduce((sum, v) => sum + (v.duration_ms || 0), 0) / total).toFixed(1)
      : '0.0';

    // Coverage stats
    const agentNames = Object.keys(coverage);
    let coveredPairs = 0;
    let uncoveredPairs = 0;
    for (const src of agentNames) {
      for (const tgt of agentNames) {
        const status = coverage[src]?.[tgt];
        if (status === 'covered') coveredPairs++;
        if (status === 'uncovered') uncoveredPairs++;
      }
    }

    // Agent health from SSE events
    const agentStatuses = {};
    const recent = events.slice(-100);
    for (const evt of recent) {
      if (evt.type !== 'validation') continue;
      const d = evt.data || evt;
      if (!d.passed) {
        const sev = (d.violations || []).some(v => v.severity === 'critical' || v.severity === 'high')
          ? 'error' : 'warning';
        for (const name of [d.source, d.target]) {
          if (sev === 'error' || agentStatuses[name] !== 'error') {
            agentStatuses[name] = sev;
          }
        }
      }
    }
    const healthyAgents = agents.filter(a => !agentStatuses[a.name]).length;
    const issueAgents = agents.length - healthyAgents;

    const recentFailures = validations
      .filter(v => !(v.passed === 1 || v.passed === true))
      .slice(0, 8);

    return {
      total, passed, failed, passRate, avgDuration,
      coveredPairs, uncoveredPairs, totalPairs: coveredPairs + uncoveredPairs,
      healthyAgents, issueAgents, recentFailures,
    };
  }, [agents, validations, events, coverage]);

  const systemHealthy = metrics.issueAgents === 0 && metrics.failed === 0;

  return (
    <div>
      <div className="page-header">
        <h2>Overview</h2>
        <p>System health and recent activity at a glance</p>
      </div>

      {/* Health banner */}
      <div className={`health-banner ${systemHealthy ? 'healthy' : 'attention'}`}>
        <div className="health-banner-icon">
          {systemHealthy ? <IconCheckCircle size={24} /> : <IconAlert size={24} />}
        </div>
        <div className="health-banner-text">
          <strong>
            {systemHealthy
              ? 'All systems healthy'
              : `${metrics.issueAgents} agent${metrics.issueAgents !== 1 ? 's' : ''} need attention`
            }
          </strong>
          <span>
            {agents.length} agents registered
            {' \u00b7 '}
            {connected ? 'Live monitoring active' : 'Reconnecting...'}
          </span>
        </div>
      </div>

      {/* Metric cards */}
      <div className="metrics-row">
        <div className="metric-card">
          <div className="metric-label">Total Validations</div>
          <div className="metric-value">{metrics.total}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Pass Rate</div>
          <div className="metric-value">{metrics.passRate}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg Latency</div>
          <div className="metric-value">{metrics.avgDuration}<span className="metric-unit">ms</span></div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Coverage</div>
          <div className="metric-value">
            {metrics.coveredPairs}/{metrics.totalPairs}
            <span className="metric-unit">pairs</span>
          </div>
        </div>
      </div>

      {/* Two-column: Recent failures + Quick links */}
      <div className="overview-grid">
        <div className="card">
          <div className="card-header">
            <h3>Recent Failures</h3>
            <button className="btn" onClick={() => onNavigate('log')}>View all</button>
          </div>
          {metrics.recentFailures.length === 0 ? (
            <div className="card-body">
              <div className="empty-state-inline">
                <IconCheckCircle size={20} />
                <span>No failures recorded. All validations passing.</span>
              </div>
            </div>
          ) : (
            <div className="card-body" style={{ padding: 0 }}>
              {metrics.recentFailures.map((v, i) => (
                <div
                  key={v.handoff_id || i}
                  className="overview-failure-row"
                  onClick={() => onViolationClick && onViolationClick(v.handoff_id)}
                >
                  <span className="overview-failure-agents">
                    {v.source} → {v.target}
                  </span>
                  <span className="overview-failure-contract">
                    {v.contract_name || 'No contract'}
                  </span>
                  <span className="overview-failure-time">
                    {formatTimeAgo(v.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="overview-quick-links">
          <div className="quick-link-card" onClick={() => onNavigate('graph')}>
            <div className="quick-link-icon"><IconNodes size={20} /></div>
            <div>
              <strong>System Map</strong>
              <span>{agents.length} agents, {contracts.length} contracts</span>
            </div>
          </div>
          <div className="quick-link-card" onClick={() => onNavigate('stream')}>
            <div className="quick-link-icon"><IconActivity size={20} /></div>
            <div>
              <strong>Live Activity</strong>
              <span>{events.filter(e => e.type === 'validation').length} events this session</span>
            </div>
          </div>
          <div className="quick-link-card" onClick={() => onNavigate('coverage')}>
            <div className="quick-link-icon"><IconShield size={20} /></div>
            <div>
              <strong>Coverage</strong>
              <span>{metrics.coveredPairs} of {metrics.totalPairs} pairs covered</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
