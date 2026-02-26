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
 * Detailed view for a single handoff event from the SSE stream.
 * Shows header, payload (tabbed), violations, and prev/next navigation.
 */
export default function HandoffDetail({ event, events, onBack, onNavigate }) {
  const [payloadTab, setPayloadTab] = useState('masked');
  const [expandedEvidence, setExpandedEvidence] = useState(new Set());
  const [copied, setCopied] = useState(false);

  const validationEvents = useMemo(
    () => events.filter((e) => e.type === 'validation'),
    [events],
  );

  // Find the initial index from the event prop (only on mount)
  const initialIndex = useMemo(() => {
    const ed = event?.data || event;
    if (!ed?.trace_id) return -1;
    return validationEvents.findIndex((e) => {
      const dd = e.data || e;
      return dd.trace_id === ed.trace_id;
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const [currentIndex, setCurrentIndex] = useState(initialIndex >= 0 ? initialIndex : 0);

  // Derive the displayed event from internal index, falling back to the prop
  const currentEvent = validationEvents[currentIndex] || event;
  const d = currentEvent?.data || currentEvent || {};

  const isValid = d && typeof d === 'object' && (d.source || d.target);

  const violationFields = useMemo(() => {
    const fields = new Set();
    if (d?.violations) {
      d.violations.forEach((v) => {
        if (v.field) fields.add(v.field);
      });
    }
    return fields;
  }, [d?.violations]);

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

  const navigatePrev = useCallback(() => {
    if (currentIndex > 0) {
      setCurrentIndex(currentIndex - 1);
      setExpandedEvidence(new Set());
      setPayloadTab('masked');
    }
  }, [currentIndex]);

  const navigateNext = useCallback(() => {
    if (currentIndex < validationEvents.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setExpandedEvidence(new Set());
      setPayloadTab('masked');
    }
  }, [currentIndex, validationEvents.length]);

  // Fallback for events that aren't valid SSE objects (e.g. audit DB IDs)
  if (!isValid) {
    return (
      <div>
        <button className="back-link" onClick={onBack}>
          <IconChevronLeft size={14} /> Back
        </button>
        <div className="detail-panel" style={{ marginTop: 16 }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            This handoff event is not available in the current session.
            Check the Live Activity stream for real-time events.
          </p>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => onNavigate('stream')}>
            Go to Live Activity
          </button>
        </div>
      </div>
    );
  }

  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < validationEvents.length - 1;
  const payloadKeyCount = d.payload_keys?.length || (d.payload ? Object.keys(d.payload).length : 0);

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        <IconChevronLeft size={14} /> Back
      </button>

      {/* Header */}
      <div className="handoff-detail-header">
        <h2 className="handoff-detail-title">{d.source} {'\u2192'} {d.target}</h2>
        <div className="handoff-detail-meta">
          <span className={`badge ${d.passed ? 'badge-pass' : 'badge-fail'}`}>
            {d.passed ? 'PASS' : 'FAIL'}
          </span>
          <span className="handoff-meta-item">{d.contract || 'No contract'}</span>
          {d.timestamp && (
            <span className="handoff-meta-item">
              {new Date(d.timestamp).toLocaleString()}
            </span>
          )}
          {d.duration_ms != null && (
            <span className="handoff-meta-item">{d.duration_ms.toFixed(1)}ms</span>
          )}
        </div>
      </div>

      {/* Trace ID */}
      {d.trace_id && (
        <div className="handoff-trace-row">
          <code className="handoff-trace-id">{d.trace_id}</code>
          <button className="btn handoff-copy-btn" onClick={copyTraceId}>
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
      )}

      {/* Payload Section */}
      {(d.payload || d.payload_keys || d.payload_preview) && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-header">
            <h3>
              Payload
              {payloadKeyCount > 0 && (
                <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
                  {payloadKeyCount} key{payloadKeyCount !== 1 ? 's' : ''}
                </span>
              )}
              {d.payload_size != null && (
                <span style={{ fontWeight: 400, fontSize: 12, color: 'var(--text-muted)', marginLeft: 8 }}>
                  {'\u00b7'} {d.payload_size} bytes
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
            {payloadTab === 'masked' && (
              d.payload ? (
                <pre className="payload-json">{formatJson(d.payload)}</pre>
              ) : (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No masked payload available.</p>
              )
            )}
            {payloadTab === 'keys' && (
              d.payload_keys && d.payload_keys.length > 0 ? (
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
              ) : (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No payload keys available.</p>
              )
            )}
            {payloadTab === 'raw' && (
              d.payload_preview ? (
                <pre className="payload-json" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {d.payload_preview}
                </pre>
              ) : (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>No raw preview available.</p>
              )
            )}
          </div>

          {/* Payload Keys summary below tabs */}
          {d.payload_keys && d.payload_keys.length > 0 && payloadTab !== 'keys' && (
            <div className="handoff-payload-keys-footer">
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
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--text-primary)' }}>
            Violations ({d.violations.length})
          </h3>
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
                          {typeof v.evidence === 'string'
                            ? v.evidence
                            : JSON.stringify(v.evidence, null, 2)}
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

      {/* Previous / Next navigation */}
      {validationEvents.length > 0 && (
        <div className="handoff-nav">
          <button
            className="btn"
            disabled={!hasPrev}
            onClick={navigatePrev}
          >
            {'\u2190'} Previous
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {currentIndex + 1} of {validationEvents.length}
          </span>
          <button
            className="btn"
            disabled={!hasNext}
            onClick={navigateNext}
          >
            Next {'\u2192'}
          </button>
        </div>
      )}
    </div>
  );
}
