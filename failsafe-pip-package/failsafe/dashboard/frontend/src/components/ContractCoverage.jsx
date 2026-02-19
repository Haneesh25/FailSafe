import React, { useMemo } from 'react';
import { IconShield } from './Icons.jsx';

/**
 * Matrix/heatmap showing contract coverage between agent pairs.
 * green = passing (covered), yellow = has violations, red = no contract, gray = no communication (self)
 */
export default function ContractCoverage({ coverage, contracts, onCellClick }) {
  const agents = useMemo(() => Object.keys(coverage).sort(), [coverage]);

  const cellSymbol = {
    covered: '\u2713',
    uncovered: '\u2717',
    self: '\u2014',
  };

  const cellTitle = {
    covered: 'Contract exists',
    uncovered: 'No contract defined',
    self: 'Self',
  };

  const findContract = (source, target) => {
    return contracts.find(c => c.source === source && c.target === target);
  };

  if (agents.length === 0) {
    return (
      <div>
        <div className="page-header">
          <h2>Coverage</h2>
          <p>Which agent pairs have contracts and how they're performing</p>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon"><IconShield size={36} /></div>
          <p className="empty-state-title">No agents registered</p>
          <p className="empty-state-desc">Register agents and contracts to see coverage across your system.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h2>Coverage</h2>
        <p>Which agent pairs have contracts defined. Click a covered cell to view details.</p>
      </div>

      <div className="card">
        <div className="card-body">
          <div className="coverage-grid">
            <div style={{ display: 'inline-grid', gridTemplateColumns: `auto repeat(${agents.length}, 44px)`, gap: 3, alignItems: 'center' }}>
              {/* Header row */}
              <div style={{
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                textAlign: 'right',
                paddingRight: 8,
              }}>
                Source ↓ Target →
              </div>
              {agents.map((a) => (
                <div key={`h-${a}`} style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  textAlign: 'center',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }} title={a}>
                  {a.replace(/_agent$/, '')}
                </div>
              ))}

              {/* Data rows */}
              {agents.map((source) => (
                <React.Fragment key={source}>
                  <div style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--text-primary)',
                    textAlign: 'right',
                    paddingRight: 8,
                    whiteSpace: 'nowrap',
                  }}>
                    {source.replace(/_agent$/, '')}
                  </div>
                  {agents.map((target) => {
                    const status = coverage[source]?.[target] || 'no-comm';
                    const cellClass = status === 'covered'
                      ? 'covered'
                      : status === 'uncovered'
                      ? 'uncovered'
                      : status === 'self'
                      ? 'self'
                      : 'no-comm';

                    return (
                      <div
                        key={target}
                        className={`coverage-cell ${cellClass}`}
                        title={`${source} → ${target}: ${cellTitle[status] || status}`}
                        onClick={() => {
                          if (status === 'covered' && onCellClick) {
                            const c = findContract(source, target);
                            if (c) onCellClick(c);
                          }
                        }}
                        style={{
                          width: 40,
                          height: 40,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: status === 'covered' ? 'pointer' : 'default',
                          borderRadius: 'var(--radius-sm)',
                          fontSize: 14,
                          fontWeight: 700,
                        }}
                      >
                        {cellSymbol[status] || ''}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div style={{ display: 'flex', gap: 20, marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>
            <span>
              <span className="coverage-cell covered" style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 3, verticalAlign: 'middle', marginRight: 4 }} />
              Covered (contract exists)
            </span>
            <span>
              <span className="coverage-cell uncovered" style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 3, verticalAlign: 'middle', marginRight: 4 }} />
              Uncovered (no contract)
            </span>
            <span>
              <span className="coverage-cell self" style={{ display: 'inline-block', width: 14, height: 14, borderRadius: 3, verticalAlign: 'middle', marginRight: 4 }} />
              Self
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
