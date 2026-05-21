import React, { useState, useEffect, useCallback } from 'react';
import { getCompanies, getCompany } from '../api';

function Companies() {
  var companies_state = useState([]);
  var companies = companies_state[0];
  var setCompanies = companies_state[1];

  var total_state = useState(0);
  var total = total_state[0];
  var setTotal = total_state[1];

  var page_state = useState(1);
  var page = page_state[0];
  var setPage = page_state[1];

  var search_state = useState('');
  var search = search_state[0];
  var setSearch = search_state[1];

  var loading_state = useState(true);
  var loading = loading_state[0];
  var setLoading = loading_state[1];

  var error_state = useState(null);
  var error = error_state[0];
  var setError = error_state[1];

  var expanded_state = useState(null);
  var expandedId = expanded_state[0];
  var setExpandedId = expanded_state[1];

  var detail_state = useState(null);
  var detail = detail_state[0];
  var setDetail = detail_state[1];

  var detailLoading_state = useState(false);
  var detailLoading = detailLoading_state[0];
  var setDetailLoading = detailLoading_state[1];

  var perPage = 20;

  var fetchCompanies = useCallback(function () {
    setLoading(true);
    setError(null);
    getCompanies({ search: search, page: page, per_page: perPage })
      .then(function (data) {
        setCompanies(data.companies || []);
        setTotal(data.total || 0);
      })
      .catch(function (err) {
        setError((err && err.message) || 'Failed to load companies');
      })
      .finally(function () {
        setLoading(false);
      });
  }, [search, page]);

  useEffect(function () { fetchCompanies(); }, [fetchCompanies]);

  var _input = useState(''), inputVal = _input[0], setInputVal = _input[1];

  var handleSearchSubmit = function (e) {
    if (e) e.preventDefault();
    setSearch(inputVal);
    setPage(1);
    setExpandedId(null);
    setDetail(null);
  };

  var handleKeyPress = function (e) {
    if (e.key === 'Enter') handleSearchSubmit();
  };

  var toggleRow = function (id) {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setDetailLoading(true);
    getCompany(id)
      .then(function (d) { setDetail(d); })
      .catch(function () { setDetail(null); })
      .finally(function () { setDetailLoading(false); });
  };

  var totalPages = Math.ceil(total / perPage);

  var formatMoney = function (val) {
    if (val === null || val === undefined || val === '') return '-';
    return '$' + Number(val).toLocaleString();
  };

  return (
    <div>
      <div className="page-header">
        <h2>Companies</h2>
        <span style={{ color: '#64748b', fontSize: 14 }}>{total} total</span>
      </div>
      <div className="page-body">
        {error && <div className="error-message">{error}</div>}
        <div className="toolbar" style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
          <input
            className="search-input"
            type="text"
            placeholder="Search by company name, CIK, or symbol..."
            value={inputVal}
            onChange={function (e) { setInputVal(e.target.value); }}
            onKeyPress={handleKeyPress}
            style={{ flex: 1, padding: '10px 16px', fontSize: 14, border: '2px solid #e2e8f0', borderRadius: 8 }}
          />
          <button
            className="btn btn-primary"
            onClick={handleSearchSubmit}
            style={{ padding: '10px 24px', fontSize: 14, borderRadius: 8, background: '#3b82f6', color: 'white', border: 'none', cursor: 'pointer', fontWeight: 600 }}
          >
            Search
          </button>
          {search && (
            <button
              className="btn"
              onClick={function () { setInputVal(''); setSearch(''); setPage(1); }}
              style={{ padding: '10px 16px', fontSize: 14, borderRadius: 8, background: '#f1f5f9', border: '1px solid #e2e8f0', cursor: 'pointer' }}
            >
              Clear
            </button>
          )}
        </div>
        {search && <div style={{ color: '#64748b', fontSize: 13, marginBottom: 12 }}>Showing results for: <strong>{search}</strong></div>}

        {loading ? (
          <div className="loading">Loading companies...</div>
        ) : (
          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Company Name</th>
                      <th>CIK</th>
                      <th>Symbol</th>
                      <th>Fortune 1000</th>
                      <th>Russell 3000</th>
                      <th>Priority</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map(function (c) {
                      var id = c.Company_ID || c.id || c.CompanyID || c.company_id;
                      return (
                        <React.Fragment key={id}>
                          <tr
                            onClick={function () { toggleRow(id); }}
                            style={{ cursor: 'pointer', background: expandedId === id ? '#1e293b' : 'transparent' }}
                          >
                            <td><strong>{c.CompanyName || c.company_name || '-'}</strong></td>
                            <td>{c.CIK || c.cik || '-'}</td>
                            <td>{c.Symbol || c.Ticker || c.ticker || c.symbol || '-'}</td>
                            <td>{c.Fortune_1000 || c.fortune_1000 || '-'}</td>
                            <td>{c.Russell_3000 || c.russell_3000 || '-'}</td>
                            <td>{c.Priority || c.priority || '-'}</td>
                          </tr>
                          {expandedId === id && (
                            <tr className="detail-row">
                              <td colSpan={6}>
                                <div className="detail-content" style={{ padding: '16px 12px' }}>
                                  {detailLoading ? (
                                    <div className="loading">Loading details...</div>
                                  ) : detail ? (
                                    <div>
                                      {detail.officers && detail.officers.length > 0 && (
                                        <div style={{ marginBottom: 20 }}>
                                          <h4 style={{ marginBottom: 8 }}>Officers ({detail.officers.length})</h4>
                                          <table className="detail-table">
                                            <thead>
                                              <tr>
                                                <th>Name</th>
                                                <th>Title</th>
                                                <th>Gender</th>
                                                <th>Fiscal Year</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {detail.officers.map(function (o, i) {
                                                var genderVal = o.Gender || o.gender;
                                                var genderText = genderVal === 1 ? 'Male' : genderVal === 2 ? 'Female' : (genderVal || '-');
                                                return (
                                                  <tr key={i}>
                                                    <td>{o.OfficerName || o.officer_name || '-'}</td>
                                                    <td>{o.Title || o.title || '-'}</td>
                                                    <td>{genderText}</td>
                                                    <td>{o.FiscalYear || o.fiscal_year || '-'}</td>
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                          </table>
                                        </div>
                                      )}
                                      {detail.compensation && detail.compensation.length > 0 && (
                                        <div style={{ marginBottom: 20 }}>
                                          <h4 style={{ marginBottom: 8, color: '#1e40af' }}>Summary Compensation Table ({detail.compensation.length})</h4>
                                          <div style={{ overflowX: 'auto' }}>
                                          <table className="detail-table" style={{ fontSize: 12 }}>
                                            <thead>
                                              <tr style={{ background: '#1e293b', color: 'white' }}>
                                                <th>Officer</th>
                                                <th>Year</th>
                                                <th>Salary</th>
                                                <th>Bonus</th>
                                                <th>Stock Awards</th>
                                                <th>Option Awards</th>
                                                <th>Non-Equity Incentive</th>
                                                <th>Pension/NQDC</th>
                                                <th>All Other</th>
                                                <th style={{fontWeight: 700}}>Total</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {detail.compensation.map(function (comp, i) {
                                                return (
                                                  <tr key={i} style={{ background: i % 2 === 0 ? '#f8fafc' : 'white' }}>
                                                    <td style={{fontWeight: 600}}>{comp.OfficerName || '-'}</td>
                                                    <td>{comp.FiscalYear || '-'}</td>
                                                    <td>{formatMoney(comp.Salary)}</td>
                                                    <td>{formatMoney(comp.Bonus)}</td>
                                                    <td>{formatMoney(comp.Stock_Award)}</td>
                                                    <td>{formatMoney(comp.Option_Awards)}</td>
                                                    <td>{formatMoney(comp.Non_Eq_Incentive_Plan_Comp)}</td>
                                                    <td>{formatMoney(comp.Chg_PensionValue_NQDC_Earnings)}</td>
                                                    <td>{formatMoney(comp.All_Other)}</td>
                                                    <td style={{fontWeight: 700, color: '#1e40af'}}>{formatMoney(comp.Total)}</td>
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                          </table>
                                          </div>
                                        </div>
                                      )}
                                      {detail.equity && detail.equity.length > 0 && (
                                        <div style={{ marginBottom: 20 }}>
                                          <h4 style={{ marginBottom: 8 }}>Equity Awards ({detail.equity.length})</h4>
                                          <table className="detail-table">
                                            <thead>
                                              <tr>
                                                <th>Officer</th>
                                                <th>Type</th>
                                                <th>Value</th>
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {detail.equity.map(function (eq, i) {
                                                return (
                                                  <tr key={i}>
                                                    <td>{eq.OfficerName || eq.officer_name || '-'}</td>
                                                    <td>{eq.AwardType || eq.award_type || '-'}</td>
                                                    <td>{formatMoney(eq.Value || eq.value)}</td>
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                          </table>
                                        </div>
                                      )}
                                      {(!detail.officers || detail.officers.length === 0) &&
                                       (!detail.compensation || detail.compensation.length === 0) &&
                                       (!detail.equity || detail.equity.length === 0) && (
                                        <p style={{ color: '#94a3b8' }}>No additional data available for this company.</p>
                                      )}
                                    </div>
                                  ) : (
                                    <p style={{ color: '#94a3b8' }}>Failed to load details.</p>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                    {companies.length === 0 && (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', color: '#94a3b8', padding: 40 }}>
                          No companies found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <button onClick={function () { setPage(function (p) { return p - 1; }); }} disabled={page <= 1}>Previous</button>
            <span className="page-info">Page {page} of {totalPages}</span>
            <button onClick={function () { setPage(function (p) { return p + 1; }); }} disabled={page >= totalPages}>Next</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default Companies;
