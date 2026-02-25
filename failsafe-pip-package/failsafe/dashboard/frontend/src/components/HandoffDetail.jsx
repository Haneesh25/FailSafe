import React, { useState, useCallback, useMemo } from 'react';
import { IconChevronLeft } from './Icons.jsx';

const SENSITIVE_PATTERNS = [
  'ssn', 'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
  'credit_card', 'card_number', 'account_number', 'tax_id', 'private_key',
];

const isSensitiveKey = (key) =>
  SENSITIVE_PATTERNS.some((p) => key.toLowerCase().includes(p));

const SEVERITY_COLORS = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#ca8a04',
  low: '#4f46e5',
};

/**
 * Recursively format a JSON value into React elements with syntax classes.
 */
const formatJson = (value, indent = 0) => {
  const pad = '  '.repeat(indent);
  const padInner = '  '.repeat(indent + 1);

  if (value === null) {
    return <span className="json-null">null</span>;
  }
  if (typeof value === 'boolean') {
    return <span className="json-boolean">{value ? 'true' : 'false'}</span>;
  }
  if (typeof value === 'number') {
    return <span className="json-number">{value}</span>;
  }
  if (typeof value === 'string') {
    if (value === '***MASKED***') {
      return <span className="json-masked">"{value}"</span>;
    }
    return <span className="json-string">"{value}"</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>{'[]'}</span>;
    return (
      <span>
        {'[\n'}
        {value.map((item, i) => (
          <span key={i}>
            {padInner}
            {formatJson(item, indent + 1)}
            {i < value.length - 1 ? ',' : ''}
            {'\n'}
          </span>
        ))}
        {pad}{']'}
      </span>
    );
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 0) return <span>{'{}'}</span>;
    return (
      <span>
        {'{\n'}
        {keys.map((k, i) => (
          <span key={k}>
            {padInner}
            <span className="json-key">"{k}"</span>
            {': '}
            {formatJson(value[k], indent + 1)}
            {i < keys.length - 1 ? ',' : ''}
            {'\n'}
          </span>
        ))}
        {pad}{'}'}
      </span>
    );
  }
  return <span>{String(value)}</span>;
};

/**
 * Detailed view for a single handoff event.
 * Shows payload data, violations, and navigation between events.
 */
export default function HandoffDetail({ event, events, onBack, onNavigate }) {
  const [payloadTab, setPayloadTab] = useState('masked');
  const [expandedEvidence, setExpandedEvidence] = useState(new Set());
  const [copied, setCopied] = useState(false);

  const d = event?.data || event;

  // Find current event index among validation events for prev/next
  const validationEvents = useMemo(
    () => events.filter((e) => e.type === 'validation'),
    [events],
  );

  const currentIndex = useMemo(() => {
    return validationEvents.findIndex((e) => e === event);
  }, [validationEvents, event]);

  const prevEvent = currentIndex > 0 ? validationEvents[currentIndex - 1] : null;
  const nextEvent = currentIndex < validationEvents.length - 1 ? validationEvents[currentIndex + 1] : null;

  const toggleEvidence = useCallback((index) => {
    setExpandedEvidence((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const copyTraceId = useCallback(() => {
    if (d?.trace_id) {
      navigator.clipboard.writeText(d.trace_id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [d?.trace_id]);

  const violationFields = useMemo(() => {
    const fields = new Set();
    if (d?.violations) {
      d.violations.forEach((v) => {
        if (v.field) fields.add(v.field);
      });
    }
    return fields;
  }, [d?.violations]);

  const formatTimestamp = (ts) => {
    if (!ts) return '-';
    try {
      return new Date(ts).toLocaleString('en-US', {
        hour12: false,
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    } catch {
      return ts;
    }
  };

  if (!event || !d) {
    return (
      <div className="empty-state">
        <p>No event selected.</p>
      </div>
    );
  }

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        <IconChevronLeft size={14} /> Back to previous view
      </button>

      {/* Header */}
      <div className="page-header">
        <h2 className="handoff-detail-title">{d.source} {'\u2192'} {d.target}</h2>
        <div className="handoff-detail-meta">
          <span className={`badge ${d.passed ? 'badge-pass' : 'badge-fail'}`}>
            {d.passed ? 'PASS' : 'FAIL'}
          </span>
          <span className="handoff-meta-item">{d.contract || 'No contract'}</span>
          <span className="handoff-meta-item">{formatTimestamp(d.timestamp)}</span>
          {d.duration_ms != null && (
            <span className="handoff-meta-item">{d.duration_ms.toFixed(1)}ms</span>
          )}
        </div>
      </div>

      {/* Trace ID */}
      {d.trace_id && (
        <div className="handoff-trace-row">
          <span className="handoff-trace-label">Trace ID</span>
          <code className="handoff-trace-id">{d.trace_id}</code>
          <button className="btn handoff-copy-btn" onClick={copyTraceId}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      )}

      {/* Payload Section */}
      {(d.payload || d.payload_keys || d.payload_preview) && (
        <div className="detail-panel" style={{ marginTop: 16 }}>
          <div className="card-header" style={{ padding: '14px 20px', margin: '-20px -20px 16px' }}>
            <h3>
              Payload
              {d.payload_keys && (
                <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
                  {d.payload_keys.length} key{d.payload_keys.length !== 1 ? 's' : ''}
                  {d.payload_size != null && ` \u00b7 ${d.payload_size} bytes`}
                </span>
              )}
            </h3>
          </div>

          {/* Tabs */}
          <div className="handoff-tabs">
            <button
              className={`handoff-tab ${payloadTab === 'masked' ? 'active' : ''}`}
              onClick={() => setPayloadTab('masked')}
            >
              Masked View
            </button>
            <button
              className={`handoff-tab ${payloadTab === 'keys' ? 'active' : ''}`}
              onClick={() => setPayloadTab('keys')}
            >
              Keys Only
            </button>
            <button
              className={`handoff-tab ${payloadTab === 'raw' ? 'active' : ''}`}
              onClick={() => setPayloadTab('raw')}
            >
              Raw Preview
            </button>
          </div>

          {/* Tab content */}
          <div className="handoff-tab-content">
            {payloadTab === 'masked' && d.payload && (
              <pre className="payload-json">
                {formatJson(d.payload)}
              </pre>
            )}
            {payloadTab === 'keys' && d.payload_keys && (
              <div className="handoff-keys-grid">
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
                    <span key={key} className={cls}>
                      {prefix}{key}
                    </span>
                  );
                })}
              </div>
            )}
            {payloadTab === 'raw' && d.payload_preview && (
              <pre className="payload-json" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {d.payload_preview}
              </pre>
            )}
          </div>

          {/* Payload Keys summary — always visible below tabs */}
          {d.payload_keys && d.payload_keys.length > 0 && (
            <div className="detail-section" style={{ marginTop: 16 }}>
              <h4>Payload Keys</h4>
              <div className="payload-keys">
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
                    <span key={key} className={cls}>
                      {prefix}{key}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Violations Section */}
      {d.violations && d.violations.length > 0 && (
        <div className="detail-panel" style={{ marginTop: 16 }}>
          <div className="card-header" style={{ padding: '14px 20px', margin: '-20px -20px 16px' }}>
            <h3>Violations ({d.violations.length})</h3>
          </div>
          <div className="handoff-violations-list">
            {d.violations.map((v, vi) => {
              const sevColor = SEVERITY_COLORS[v.severity] || SEVERITY_COLORS.medium;
              const evidenceExpanded = expandedEvidence.has(vi);
              return (
                <div
                  key={vi}
                  className="handoff-violation-card"
                  style={{ borderLeftColor: sevColor }}
                >
                  <div className="handoff-violation-header">
                    <span className={`badge badge-${v.severity || 'medium'}`}>
                      {v.severity || 'medium'}
                    </span>
                    {v.rule && (
                      <code className="handoff-violation-rule">{v.rule}</code>
                    )}
                  </div>
                  <div className="handoff-violation-message">{v.message}</div>
                  {v.field && (
                    <div className="handoff-violation-field">
                      Field: <code>{v.field}</code>
                    </div>
                  )}
                  {v.evidence && (
                    <div>
                      <button
                        className="payload-toggle"
                        onClick={() => toggleEvidence(vi)}
                      >
                        {evidenceExpanded ? '\u25BC Evidence' : '\u25B6 Evidence'}
                      </button>
                      {evidenceExpanded && (
                        <pre className="payload-json" style={{ marginTop: 6 }}>
                          {formatJson(v.evidence)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Prev / Next navigation */}
      <div className="handoff-nav-row">
        <button
          className="btn"
          disabled={!prevEvent}
          onClick={() => prevEvent && onBack && onNavigate && onNavigate('__handoff_prev__')}
          style={{ visibility: prevEvent ? 'visible' : 'hidden' }}
        >
          {'\u2190'} Previous
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {currentIndex >= 0
            ? `${currentIndex + 1} of ${validationEvents.length}`
            : ''}
        </span>
        <button
          className="btn"
          disabled={!nextEvent}
          onClick={() => nextEvent && onBack && onNavigate && onNavigate('__handoff_next__')}
          style={{ visibility: nextEvent ? 'visible' : 'hidden' }}
        >
          Next {'\u2192'}
        </button>
      </div>
    </div>
  );
}
