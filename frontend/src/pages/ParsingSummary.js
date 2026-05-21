import React, { useState, useEffect, useCallback } from 'react';
import { getParsingSummary } from '../api';

function ParsingSummary() {
  var _s = function(v) { return useState(v); };
  var _r = _s([]), records = _r[0], setRecords = _r[1];
  var _t = _s(0), total = _t[0], setTotal = _t[1];
  var _p = _s(1), page = _p[0], setPage = _p[1];
  var _st = _s(''), status = _st[0], setStatus = _st[1];
  var _l = _s(true), loading = _l[0], setLoading = _l[1];
  var _e = _s(null), error = _e[0], setError = _e[1];
  var perPage = 50;

  var fetchData = useCallback(function () {
    setLoading(true);
    getParsingSummary({ page: page, per_page: perPage, status: status })
      .then(function (data) { setRecords(data.records || []); setTotal(data.total || 0); })
      .catch(function (err) { setError((err && err.message) || 'Failed'); })
      .finally(function () { setLoading(false); });
  }, [page, status]);

  useEffect(function () { fetchData(); }, [fetchData]);

  var badge = function (s) {
    var val = String(s || '').toLowerCase();
    var colors = {
      'parsed': { bg: '#dcfce7', color: '#16a34a' },
      'not parsed': { bg: '#fee2e2', color: '#dc2626' },
      'no table found': { bg: '#fef3c7', color: '#92400e' },
      'no table': { bg: '#fef3c7', color: '#92400e' },
      'already exist': { bg: '#e0e7ff', color: '#3730a3' },
    };
    var c = colors[val] || { bg: '#f1f5f9', color: '#64748b' };
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: c.bg, color: c.color };
  };

  // Fix date: DD/MM/YYYY or ISO format
  var formatDate = function (d) {
    if (!d || d === 'nan' || d === 'None') return '-';
    var s = String(d);
    // DD/MM/YYYY format
    var parts = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (parts) return parts[1] + '/' + parts[2] + '/' + parts[3];
    // ISO format
    if (s.indexOf('T') > -1 || s.indexOf('-') > -1) {
      try { return new Date(s).toLocaleDateString(); } catch(e) { return s; }
    }
    return s;
  };

  var totalPages = Math.ceil(total / perPage);

  return (
    <div>
      <div className="page-header">
        <h2>Parsing Summary</h2>
        <span style={{ color: '#64748b', fontSize: 14 }}>{total} records</span>
      </div>
      <div className="page-body">
        {error && <div className="error-message">{error}</div>}
        <div style={{ marginBottom: 16 }}>
          <select value={status} onChange={function (e) { setStatus(e.target.value); setPage(1); }}
            style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #e2e8f0', fontSize: 14 }}>
            <option value="">All Statuses</option>
            <option value="Parsed">Parsed</option>
            <option value="Not Parsed">Not Parsed</option>
            <option value="No Table found">No Table Found</option>
            <option value="Already Exist">Already Exist</option>
          </select>
        </div>

        {loading ? <div className="loading">Loading...</div> : (
          <div className="card">
            <div className="card-body" style={{ padding: 0, overflowX: 'auto' }}>
              <table style={{ fontSize: 12, width: '100%' }}>
                <thead>
                  <tr style={{ background: '#1e293b', color: 'white' }}>
                    <th style={{ padding: 10 }}>#</th>
                    <th style={{ padding: 10 }}>Company Name</th>
                    <th style={{ padding: 10 }}>Fiscal Year</th>
                    <th style={{ padding: 10 }}>SCT</th>
                    <th style={{ padding: 10 }}>Equity</th>
                    <th style={{ padding: 10 }}>Exercise</th>
                    <th style={{ padding: 10 }}>PBA</th>
                    <th style={{ padding: 10 }}>Parsed Date</th>
                    <th style={{ padding: 10 }}>Filing</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map(function (r, i) {
                    return (
                      <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? 'white' : '#f8fafc' }}>
                        <td style={{ padding: 8, color: '#94a3b8' }}>{(page - 1) * perPage + i + 1}</td>
                        <td style={{ padding: 8, fontWeight: 600 }}>{r.CompanyName || '-'}</td>
                        <td style={{ padding: 8 }}>{r.FiscalYear || '-'}</td>
                        <td style={{ padding: 8 }}><span style={badge(r.SCT_Parsed)}>{r.SCT_Parsed || '-'}</span></td>
                        <td style={{ padding: 8 }}><span style={badge(r.Outstanding_Equity_Parsed)}>{r.Outstanding_Equity_Parsed || '-'}</span></td>
                        <td style={{ padding: 8 }}><span style={badge(r.Vested_Parsed)}>{r.Vested_Parsed || '-'}</span></td>
                        <td style={{ padding: 8 }}><span style={badge(r.PBA_Parsed)}>{r.PBA_Parsed || '-'}</span></td>
                        <td style={{ padding: 8 }}>{formatDate(r.Parsed_Date)}</td>
                        <td style={{ padding: 8 }}>{r.Link ? <a href={r.Link} target="_blank" rel="noreferrer" style={{ color: '#3b82f6', fontSize: 11 }}>View</a> : '-'}</td>
                      </tr>
                    );
                  })}
                  {records.length === 0 && (
                    <tr><td colSpan={9} style={{ textAlign: 'center', color: '#94a3b8', padding: 40 }}>No records found</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 16 }}>
            <button onClick={function () { setPage(page - 1); }} disabled={page <= 1}
              style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer' }}>Previous</button>
            <span style={{ padding: '8px 16px', color: '#64748b' }}>Page {page} of {totalPages}</span>
            <button onClick={function () { setPage(page + 1); }} disabled={page >= totalPages}
              style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer' }}>Next</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ParsingSummary;
