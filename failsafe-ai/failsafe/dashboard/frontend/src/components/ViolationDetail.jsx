import React, { useState, useEffect } from 'react';

/**
 * Deep provenance view for a specific violation.
 * Fetches violation details from the REST API and shows full payload, agents, trace.
 */
export default function ViolationDetail({ validationId, onBack }) {
  const [violations, setViolations] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!validationId) return;

    setLoading(true);
    setError(null);

    fetch(`/api/violations/${validationId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setViolations(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [validationId]);

  const severityColor = {
    critical: 'var(--red)',
    high: 'var(--orange)',
    medium: 'var(--yellow)',
    low: 'var(--accent)',
  };

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        {'\u2190'} Back
      </button>

      <div className="page-header">
        <h2>Violation Details</h2>
        <p>Validation ID: {validationId}</p>
      </div>

      {loading && (
        <div className="empty-state">
          <p>Loading violation details...</p>
        </div>
      )}

      {error && (
        <div className="detail-panel" style={{ borderColor: 'var(--red)' }}>
          <p style={{ color: 'var(--red)' }}>Error loading violations: {error}</p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
            The validation ID may refer to a trace_id from the WebSocket stream.
            Violation details are only available for audit-logged validations.
          </p>
        </div>
      )}

      {!loading && !error && violations && (
        <>
          {violations.length === 0 ? (
            <div className="detail-panel">
              <p style={{ color: 'var(--text-muted)' }}>
                No violations found for this validation. It may have passed or the ID may be invalid.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Summary */}
              <div className="detail-panel">
                <div className="detail-section">
                  <h4>Summary</h4>
                  <dl className="detail-kv">
                    <dt>Total Violations</dt>
                    <dd>{violations.length}</dd>
                    <dt>Severities</dt>
                    <dd>
                      {Object.entries(
                        violations.reduce((acc, v) => {
                          acc[v.severity] = (acc[v.severity] || 0) + 1;
                          return acc;
                        }, {})
                      ).map(([sev, count]) => (
                        <span key={sev} className={`badge badge-${sev}`} style={{ marginRight: 6 }}>
                          {count} {sev}
                        </span>
                      ))}
                    </dd>
                  </dl>
                </div>
              </div>

              {/* Individual violations */}
              {violations.map((v, i) => (
                <div key={v.id || i} className="detail-panel">
                  <h3 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: '50%',
                        background: severityColor[v.severity] || 'var(--text-muted)',
                        flexShrink: 0,
                      }}
                    />
                    Violation #{i + 1}
                    <span className={`badge badge-${v.severity}`} style={{ marginLeft: 'auto' }}>
                      {v.severity}
                    </span>
                  </h3>

                  <div className="detail-section" style={{ marginTop: 12 }}>
                    <h4>Details</h4>
                    <dl className="detail-kv">
                      <dt>Rule</dt>
                      <dd style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan)' }}>{v.rule}</dd>
                      <dt>Severity</dt>
                      <dd>
                        <span className={`badge badge-${v.severity}`}>{v.severity}</span>
                      </dd>
                      <dt>Message</dt>
                      <dd>{v.message}</dd>
                      {v.field && (
                        <>
                          <dt>Field</dt>
                          <dd style={{ fontFamily: 'var(--font-mono)' }}>{v.field}</dd>
                        </>
                      )}
                    </dl>
                  </div>

                  {v.evidence && (
                    <div className="detail-section">
                      <h4>Evidence</h4>
                      <div className="code-block">
                        {typeof v.evidence === 'string'
                          ? v.evidence
                          : JSON.stringify(
                              typeof v.evidence === 'string' ? JSON.parse(v.evidence) : v.evidence,
                              null,
                              2
                            )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
