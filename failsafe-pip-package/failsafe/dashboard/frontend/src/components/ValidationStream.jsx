import React, { useState, useRef, useEffect, useCallback } from 'react';
import { IconActivity, IconCheckCircle } from './Icons.jsx';

const SENSITIVE_PATTERNS = [
  'ssn', 'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
  'credit_card', 'card_number', 'account_number', 'tax_id', 'private_key',
];

const isSensitiveKey = (key) =>
  SENSITIVE_PATTERNS.some((p) => key.toLowerCase().includes(p));

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
 * Real-time feed of validation events streamed via SSE.
 * Auto-scrolls to bottom, with a pause button. Failed events highlighted.
 */
export default function ValidationStream({ events, onClear, onViolationClick }) {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState('failed'); // 'all' | 'failed' | 'passed'
  const [expanded, setExpanded] = useState(new Set());
  const bottomRef = useRef(null);
  const containerRef = useRef(null);

  // Only show validation events
  const validationEvents = events.filter((e) => e.type === 'validation');

  const filtered = validationEvents.filter((e) => {
    const d = e.data || e;
    if (filter === 'failed') return !d.passed;
    if (filter === 'passed') return d.passed;
    return true;
  });

  // Auto-scroll to bottom unless paused
  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [filtered.length, paused]);

  const formatTime = useCallback((ts) => {
    if (!ts) return '--:--:--';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { hour12: false });
    } catch {
      return ts;
    }
  }, []);

  const toggleExpanded = useCallback((index) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const allExpanded = filtered.length > 0 && expanded.size >= filtered.length;

  const toggleAll = useCallback(() => {
    if (allExpanded) {
      setExpanded(new Set());
    } else {
      setExpanded(new Set(filtered.map((_, i) => i)));
    }
  }, [allExpanded, filtered]);

  const getViolationFields = (violations) => {
    const fields = new Set();
    if (violations) {
      violations.forEach((v) => {
        if (v.field) fields.add(v.field);
      });
    }
    return fields;
  };

  return (
    <div>
      <div className="page-header">
        <h2>Live Activity</h2>
        <p>Real-time validation events as they happen</p>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>{filter === 'failed' ? `${filtered.length} failure${filtered.length !== 1 ? 's' : ''}` : `${filtered.length} event${filtered.length !== 1 ? 's' : ''}`}</h3>
          <div className="stream-controls">
            <button
              className={`btn ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All
            </button>
            <button
              className={`btn ${filter === 'failed' ? 'active' : ''}`}
              onClick={() => setFilter('failed')}
            >
              Failed
            </button>
            <button
              className={`btn ${filter === 'passed' ? 'active' : ''}`}
              onClick={() => setFilter('passed')}
            >
              Passed
            </button>
            <span style={{ width: 1, height: 20, background: 'var(--border-light)' }} />
            <button className="btn" onClick={() => setPaused(!paused)}>
              {paused ? '\u25B6 Resume' : '\u23F8 Pause'}
            </button>
            <button className="btn" onClick={onClear}>
              Clear
            </button>
            {filtered.length > 0 && (
              <button className="btn" onClick={toggleAll}>
                {allExpanded ? '\u25BC Collapse all' : '\u25B6 Expand all'}
              </button>
            )}
          </div>
        </div>

        <div className="stream-container" ref={containerRef}>
          {filtered.length === 0 && (
            <div className="empty-state">
              {filter === 'failed' ? (
                <>
                  <div className="empty-state-icon"><IconCheckCircle size={36} /></div>
                  <p className="empty-state-title">No failures detected</p>
                  <p className="empty-state-desc">All validations are passing. Switch to "All" to see all events.</p>
                </>
              ) : (
                <>
                  <div className="empty-state-icon"><IconActivity size={36} /></div>
                  <p className="empty-state-title">Waiting for events</p>
                  <p className="empty-state-desc">Events will appear here as agents communicate. Make sure FailSafe is running.</p>
                </>
              )}
            </div>
          )}
          {filtered.map((evt, i) => {
            const d = evt.data || evt;
            const failed = !d.passed;
            const violationFields = getViolationFields(d.violations);
            const isExpanded = expanded.has(i);
            return (
              <div
                key={`${d.trace_id || i}-${evt.timestamp || i}`}
                className={`stream-event ${failed ? 'failed' : ''}`}
                onClick={() => {
                  if (failed && onViolationClick && d.trace_id) {
                    onViolationClick(d.trace_id);
                  }
                }}
                style={{ cursor: failed ? 'pointer' : 'default' }}
              >
                <span className="stream-time">
                  {formatTime(d.timestamp || evt.timestamp)}
                </span>
                <div className="stream-body">
                  <div className="stream-agents">
                    {d.source} {'\u2192'} {d.target}
                    <span style={{ marginLeft: 10 }}>
                      <span className={`badge ${d.passed ? 'badge-pass' : 'badge-fail'}`}>
                        {d.passed ? 'PASS' : 'FAIL'}
                      </span>
                    </span>
                    {d.contract && (
                      <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-muted)' }}>
                        {d.contract}
                      </span>
                    )}
                  </div>
                  {failed && d.violations && d.violations.length > 0 && (
                    <div className="stream-violations">
                      {d.violations.map((v, vi) => (
                        <div key={vi}>
                          <span className={`badge badge-${v.severity || 'medium'}`} style={{ marginRight: 6 }}>
                            {v.severity || 'medium'}
                          </span>
                          {v.message}
                        </div>
                      ))}
                    </div>
                  )}
                  {d.payload_keys && d.payload_keys.length > 0 && (
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
                  )}
                  {d.payload_preview && (
                    <div className="payload-preview">
                      {d.payload_preview}
                      {d.payload_size != null && (
                        <span> ({d.payload_size} bytes)</span>
                      )}
                    </div>
                  )}
                  {d.payload && (
                    <div className="payload-section">
                      <button
                        className="payload-toggle"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpanded(i);
                        }}
                      >
                        {isExpanded ? '\u25BC Payload' : '\u25B6 Payload'}
                      </button>
                      {isExpanded && (
                        <pre className="payload-json">
                          {formatJson(d.payload)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
                {d.duration_ms != null && (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                    {d.duration_ms.toFixed(1)}ms
                  </span>
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
