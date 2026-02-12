import React, { useState, useRef, useEffect, useCallback } from 'react';

/**
 * Real-time feed of validation events from the WebSocket.
 * Auto-scrolls to bottom, with a pause button. Failed events highlighted.
 */
export default function ValidationStream({ events, onClear, onViolationClick }) {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState('all'); // 'all' | 'failed' | 'passed'
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

  return (
    <div>
      <div className="page-header">
        <h2>Live Validation Stream</h2>
        <p>Real-time feed of handoff validations from the WebSocket</p>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>Events ({filtered.length})</h3>
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
          </div>
        </div>

        <div className="stream-container" ref={containerRef}>
          {filtered.length === 0 && (
            <div className="empty-state">
              <p>No events yet. Waiting for validations...</p>
            </div>
          )}
          {filtered.map((evt, i) => {
            const d = evt.data || evt;
            const failed = !d.passed;
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
