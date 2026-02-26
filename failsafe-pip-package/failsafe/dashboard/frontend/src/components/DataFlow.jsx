import React, { useState, useMemo, useCallback } from 'react';

const SENSITIVE_PATTERNS = [
  'ssn', 'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
  'credit_card', 'card_number', 'account_number', 'tax_id', 'private_key',
];

const isSensitiveKey = (key) =>
  SENSITIVE_PATTERNS.some((p) => key.toLowerCase().includes(p));

export default function DataFlow({ events, onHandoffClick }) {
  const [sourceFilter, setSourceFilter] = useState('All');
  const [targetFilter, setTargetFilter] = useState('All');
  const [onlyViolations, setOnlyViolations] = useState(false);
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState({});

  const validationEvents = useMemo(
    () => events.filter((e) => e.type === 'validation'),
    [events]
  );

  // Unique sources and targets
  const sources = useMemo(() => {
    const s = new Set();
    validationEvents.forEach((e) => {
      const d = e.data || e;
      if (d.source) s.add(d.source);
    });
    return ['All', ...Array.from(s).sort()];
  }, [validationEvents]);

  const targets = useMemo(() => {
    const t = new Set();
    validationEvents.forEach((e) => {
      const d = e.data || e;
      if (d.target) t.add(d.target);
    });
    return ['All', ...Array.from(t).sort()];
  }, [validationEvents]);

  // Filtered events
  const filtered = useMemo(() => {
    const lowerSearch = search.toLowerCase();
    return validationEvents.filter((evt) => {
      const d = evt.data || evt;
      if (sourceFilter !== 'All' && d.source !== sourceFilter) return false;
      if (targetFilter !== 'All' && d.target !== targetFilter) return false;
      if (onlyViolations && (d.passed !== false || !d.violations?.length)) return false;
      if (lowerSearch) {
        const keyMatch = (d.payload_keys || []).some((k) =>
          k.toLowerCase().includes(lowerSearch)
        );
        const previewMatch = (d.payload_preview || '').toLowerCase().includes(lowerSearch);
        if (!keyMatch && !previewMatch) return false;
      }
      return true;
    });
  }, [validationEvents, sourceFilter, targetFilter, onlyViolations, search]);

  // Group by trace_id
  const { groups, groupOrder } = useMemo(() => {
    const g = {};
    for (const evt of filtered) {
      const d = evt.data || evt;
      const tid = d.trace_id || 'unknown';
      if (!g[tid]) g[tid] = [];
      g[tid].push(evt);
    }
    // Sort groups by timestamp of first event, newest first
    const order = Object.keys(g).sort((a, b) => {
      const tsA = g[a][0]?.data?.timestamp || g[a][0]?.timestamp || '';
      const tsB = g[b][0]?.data?.timestamp || g[b][0]?.timestamp || '';
      return tsB > tsA ? 1 : tsB < tsA ? -1 : 0;
    });
    return { groups: g, groupOrder: order };
  }, [filtered]);

  // Field frequency
  const { fieldCounts, fieldViolations } = useMemo(() => {
    const counts = {};
    const violations = {};
    for (const evt of filtered) {
      const d = evt.data || evt;
      for (const key of d.payload_keys || []) {
        counts[key] = (counts[key] || 0) + 1;
      }
      for (const v of d.violations || []) {
        if (v.field) {
          for (const f of v.field.split(', ')) {
            violations[f.trim()] = (violations[f.trim()] || 0) + 1;
          }
        }
      }
    }
    return { fieldCounts: counts, fieldViolations: violations };
  }, [filtered]);

  // Sorted fields: violated first, then by frequency
  const sortedFields = useMemo(() => {
    return Object.keys(fieldCounts).sort((a, b) => {
      const aViol = fieldViolations[a] || 0;
      const bViol = fieldViolations[b] || 0;
      if (aViol && !bViol) return -1;
      if (!aViol && bViol) return 1;
      return (fieldCounts[b] || 0) - (fieldCounts[a] || 0);
    });
  }, [fieldCounts, fieldViolations]);

  // Sensitive fields detected
  const sensitiveFields = useMemo(() => {
    return sortedFields.filter((f) => isSensitiveKey(f));
  }, [sortedFields]);

  const formatTime = useCallback((ts) => {
    if (!ts) return '--:--:--';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { hour12: false });
    } catch {
      return ts;
    }
  }, []);

  const toggleGroup = useCallback((tid) => {
    setCollapsed((prev) => ({ ...prev, [tid]: !prev[tid] }));
  }, []);

  const getViolationFields = (violations) => {
    const fields = new Set();
    if (violations) {
      violations.forEach((v) => {
        if (v.field) v.field.split(', ').forEach((f) => fields.add(f.trim()));
      });
    }
    return fields;
  };

  const hasViolation = (evt) => {
    const d = evt.data || evt;
    return !d.passed && d.violations && d.violations.length > 0;
  };

  const groupViolationCount = (evts) =>
    evts.filter(hasViolation).length;

  // Default collapsed state: groups with violations expanded, clean collapsed
  const isCollapsed = (tid, evts) => {
    if (collapsed[tid] !== undefined) return collapsed[tid];
    return groupViolationCount(evts) === 0;
  };

  const renderHandoffRow = (evt) => {
    const d = evt.data || evt;
    const failed = !d.passed;
    const violationFields = getViolationFields(d.violations);

    return (
      <div
        className={`trace-handoff ${failed && d.violations?.length ? 'has-violation' : ''}`}
        onClick={() => onHandoffClick && onHandoffClick(evt)}
      >
        <div className="trace-handoff-agents">
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', minWidth: 60 }}>
            {formatTime(d.timestamp || evt.timestamp)}
          </span>
          <span>{d.source} → {d.target}</span>
          <span className={`badge ${d.passed ? 'badge-pass' : 'badge-fail'}`} style={{ marginLeft: 8 }}>
            {d.passed ? 'PASS' : 'FAIL'}
          </span>
        </div>
        {d.payload_keys && d.payload_keys.length > 0 && (
          <div className="payload-keys" style={{ marginTop: 4 }}>
            {d.payload_keys.map((key) => {
              let cls = 'payload-key payload-key-neutral';
              let prefix = '';
              if (violationFields.has(key)) {
                cls = 'payload-key payload-key-violation';
              } else if (isSensitiveKey(key)) {
                cls = 'payload-key payload-key-sensitive';
                prefix = '\uD83D\uDD12 ';
              }
              return (
                <span key={key} className={cls}>{prefix}{key}</span>
              );
            })}
          </div>
        )}
        {failed && d.violations && d.violations.length > 0 && (
          <div style={{ fontSize: 12, color: 'var(--red)', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {d.violations[0].message}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="page-header">
        <h2>Data Flow</h2>
        <p>Explore what data moves between agents and identify concerns</p>
      </div>

      {validationEvents.length === 0 ? (
        <div className="dataflow-empty">
          <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>No handoff data yet</p>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Validation events will appear here as agents communicate.</p>
        </div>
      ) : (
        <div className="dataflow-layout">
          {/* Left column: filters + timeline */}
          <div className="dataflow-timeline">
            <div className="dataflow-filter-bar">
              <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                {sources.map((s) => (
                  <option key={s} value={s}>{s === 'All' ? 'All sources' : s}</option>
                ))}
              </select>
              <select value={targetFilter} onChange={(e) => setTargetFilter(e.target.value)}>
                {targets.map((t) => (
                  <option key={t} value={t}>{t === 'All' ? 'All targets' : t}</option>
                ))}
              </select>
              <label>
                <input
                  type="checkbox"
                  checked={onlyViolations}
                  onChange={(e) => setOnlyViolations(e.target.checked)}
                />
                Only violations
              </label>
              <input
                type="text"
                placeholder="Search fields or payload..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ flex: 1, minWidth: 140 }}
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                {filtered.length} handoff{filtered.length !== 1 ? 's' : ''}
              </span>
            </div>

            {filtered.length === 0 ? (
              <div className="dataflow-empty">
                <p style={{ fontSize: 13 }}>No handoffs match filters</p>
              </div>
            ) : (
              groupOrder.map((tid) => {
                const evts = groups[tid];
                // Single event without shared trace: render standalone
                if (evts.length === 1) {
                  return (
                    <div key={tid} className="trace-group">
                      {renderHandoffRow(evts[0])}
                    </div>
                  );
                }

                const violCount = groupViolationCount(evts);
                const firstTs = evts[0]?.data?.timestamp || evts[0]?.timestamp;
                const groupCollapsed = isCollapsed(tid, evts);

                return (
                  <div key={tid} className="trace-group">
                    <div
                      className="trace-group-header"
                      onClick={() => toggleGroup(tid)}
                    >
                      <div>
                        <span style={{ marginRight: 8 }}>{groupCollapsed ? '▶' : '▼'}</span>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                          Trace {tid.slice(0, 8)}...
                        </span>
                        <span style={{ marginLeft: 10, fontSize: 11, color: 'var(--text-muted)' }}>
                          {evts.length} handoff{evts.length !== 1 ? 's' : ''}
                        </span>
                        {violCount > 0 && (
                          <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--red)', fontWeight: 600 }}>
                            {violCount} violation{violCount !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {formatTime(firstTs)}
                      </span>
                    </div>
                    {!groupCollapsed && (
                      <div className="trace-group-body">
                        {evts.map((evt, i) => (
                          <React.Fragment key={i}>
                            {renderHandoffRow(evt)}
                          </React.Fragment>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Right column: field frequency sidebar */}
          <div className="dataflow-sidebar">
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--text-primary)' }}>
              Fields Observed
            </h3>

            {sensitiveFields.length > 0 && (
              <div className="sensitive-banner">
                ⚠ {sensitiveFields.length} sensitive field{sensitiveFields.length !== 1 ? 's' : ''} detected
                <div style={{ marginTop: 4, fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  {sensitiveFields.join(', ')}
                </div>
              </div>
            )}

            {sortedFields.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '12px 0' }}>
                No fields observed
              </div>
            ) : (
              <div className="field-freq-list">
                {sortedFields.map((field) => {
                  const hasFlagViol = fieldViolations[field] > 0;
                  return (
                    <div
                      key={field}
                      className={`field-freq ${hasFlagViol ? 'field-freq-flagged' : ''}`}
                      onClick={() => setSearch(field)}
                    >
                      <span className="field-freq-name">{field}</span>
                      <span className="field-freq-count">
                        {fieldCounts[field]}
                        {hasFlagViol && (
                          <span style={{ color: 'var(--red)', marginLeft: 6, fontWeight: 600 }}>
                            {fieldViolations[field]} viol
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
