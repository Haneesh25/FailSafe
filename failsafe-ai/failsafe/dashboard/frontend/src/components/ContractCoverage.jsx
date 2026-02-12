import React, { useMemo } from 'react';

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
          <h2>Contract Coverage</h2>
          <p>Heatmap of handoff contract coverage between agents</p>
        </div>
        <div className="empty-state">
          <div className="icon">{'\u25A6'}</div>
          <p>No agents registered yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h2>Contract Coverage</h2>
        <p>Matrix showing which agent pairs have contracts defined. Click a covered cell to view the contract.</p>
      </div>

      <div className="card">
        <div className="card-body">
          <div className="coverage-grid">
            <table>
              <thead>
                <tr>
                  <th style={{ textAlign: 'right', paddingRight: 12 }}>Source \ Target</th>
                  {agents.map((a) => (
                    <th key={a} style={{ textAlign: 'center', minWidth: 60 }}>
                      {a}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {agents.map((source) => (
                  <tr key={source}>
                    <td style={{
                      fontWeight: 600,
                      fontSize: 12,
                      textAlign: 'right',
                      paddingRight: 12,
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                    }}>
                      {source}
                    </td>
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
                        <td key={target} style={{ padding: 2 }}>
                          <div
                            className={`coverage-cell ${cellClass}`}
                            title={`${source} -> ${target}: ${cellTitle[status] || status}`}
                            onClick={() => {
                              if (status === 'covered' && onCellClick) {
                                const c = findContract(source, target);
                                if (c) onCellClick(c);
                              }
                            }}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              cursor: status === 'covered' ? 'pointer' : 'default',
                            }}
                          >
                            {cellSymbol[status] || ''}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
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
