import React, { useState } from 'react';
import { IconChevronLeft } from './Icons.jsx';

/**
 * Full contract schema viewer showing rules, NL rules, mode, and metadata.
 */
export default function ContractDetail({ contract, onBack }) {
  if (!contract) {
    return (
      <div className="empty-state">
        <p>No contract selected.</p>
      </div>
    );
  }

  const c = contract;
  const [showJson, setShowJson] = useState(false);

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        <IconChevronLeft size={14} /> Back to previous view
      </button>

      <div className="page-header">
        <h2>Contract: {c.name}</h2>
        <p>{c.source} {'\u2192'} {c.target}</p>
      </div>

      <div className="detail-panel">
        {/* Overview */}
        <div className="detail-section">
          <h4>Overview</h4>
          <dl className="detail-kv">
            <dt>Name</dt>
            <dd>{c.name}</dd>
            <dt>Source Agent</dt>
            <dd>{c.source}</dd>
            <dt>Target Agent</dt>
            <dd>{c.target}</dd>
            <dt>Mode</dt>
            <dd>
              <span className={`badge ${c.mode === 'block' ? 'badge-fail' : 'badge-warn'}`}>
                {c.mode}
              </span>
            </dd>
          </dl>
        </div>

        {/* Deterministic Rules */}
        <div className="detail-section">
          <h4>Deterministic Rules ({c.rules?.length || 0})</h4>
          {(!c.rules || c.rules.length === 0) ? (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No deterministic rules defined.</p>
          ) : (
            <ul className="rule-list">
              {c.rules.map((rule, i) => (
                <li key={i}>
                  <div className="rule-type">{rule.rule_type}</div>
                  <div className="rule-config">
                    {JSON.stringify(rule.config, null, 2)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* NL Rules */}
        <div className="detail-section">
          <h4>Natural Language Rules ({c.nl_rules?.length || 0})</h4>
          {(!c.nl_rules || c.nl_rules.length === 0) ? (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No NL rules defined.</p>
          ) : (
            <ul className="rule-list">
              {c.nl_rules.map((rule, i) => (
                <li key={i} style={{ fontStyle: 'italic', color: 'var(--purple)' }}>
                  &ldquo;{rule}&rdquo;
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Metadata */}
        {c.metadata && Object.keys(c.metadata).length > 0 && (
          <div className="detail-section">
            <h4>Metadata</h4>
            <div className="code-block">
              {JSON.stringify(c.metadata, null, 2)}
            </div>
          </div>
        )}

        {/* Raw JSON — collapsed by default */}
        <div className="detail-section">
          <button className="json-toggle" onClick={() => setShowJson(!showJson)}>
            {showJson ? 'Hide raw JSON' : 'Show raw JSON'}
          </button>
          {showJson && (
            <div className="code-block" style={{ marginTop: 8 }}>
              {JSON.stringify(c, null, 2)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
