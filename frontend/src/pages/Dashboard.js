import React, { useState, useEffect } from 'react';
import { getStats, getRssFeed, getModuleOutput, getParsingSummary, deleteTodayData, deleteAllData } from '../api';

function Dashboard() {
  var _s = function(init) { return useState(init); };
  var _stats = _s(null), stats = _stats[0], setStats = _stats[1];
  var _loading = _s(true), loading = _loading[0], setLoading = _loading[1];
  var _tab = _s('tracking'), tab = _tab[0], setTab = _tab[1];
  var _data = _s(null), data = _data[0], setData = _data[1];
  var _dataLoading = _s(false), dataLoading = _dataLoading[0], setDataLoading = _dataLoading[1];

  var reload = function () {
    setLoading(true);
    getStats()
      .then(function (s) { setStats(s); })
      .catch(function () {})
      .finally(function () { setLoading(false); });
  };

  useEffect(function () { reload(); }, []);

  var loadTab = function (t) {
    setTab(t);
    setDataLoading(true);
    setData(null);
    if (t === 'tracking') {
      getParsingSummary({ per_page: 500 })
        .then(function (d) { setData(d); })
        .finally(function () { setDataLoading(false); });
    } else if (t === 'rss') {
      getRssFeed()
        .then(function (d) { setData(d); })
        .finally(function () { setDataLoading(false); });
    } else {
      getModuleOutput(t)
        .then(function (d) { setData(d); })
        .finally(function () { setDataLoading(false); });
    }
  };

  useEffect(function () { loadTab('tracking'); }, []);

  var fmt = function (v) {
    if (v === null || v === undefined || v === '' || v === 0) return '-';
    return '$' + Number(v).toLocaleString();
  };

  var badge = function (status) {
    var s = String(status || '').toLowerCase();
    var colors = {
      'parsed': { bg: '#dcfce7', color: '#16a34a' },
      'not parsed': { bg: '#fee2e2', color: '#dc2626' },
      'no table found': { bg: '#fef3c7', color: '#92400e' },
      'no table': { bg: '#fef3c7', color: '#92400e' },
      'already exist': { bg: '#e0e7ff', color: '#3730a3' },
      'error': { bg: '#fee2e2', color: '#dc2626' },
    };
    var c = colors[s] || { bg: '#f1f5f9', color: '#64748b' };
    return { display: 'inline-block', padding: '3px 10px', borderRadius: 10, fontSize: 11, fontWeight: 600, background: c.bg, color: c.color };
  };

  if (loading) return <div className="loading">Loading...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>MAYA Dashboard</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={function () { reload(); loadTab(tab); }} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #e2e8f0', cursor: 'pointer', background: 'white' }}>Refresh</button>
          <button onClick={function () {
            if (window.confirm('Delete ALL today\'s data and pipeline runs?')) {
              deleteTodayData().then(function () { reload(); loadTab(tab); });
            }
          }} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #fbbf24', cursor: 'pointer', background: '#fef3c7', color: '#92400e' }}>Reset Today</button>
          <button onClick={function () {
            if (window.confirm('DELETE ALL DATA? This removes all companies, officers, compensation records. Are you sure?')) {
              deleteAllData().then(function () { reload(); loadTab(tab); });
            }
          }} style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #ef4444', cursor: 'pointer', background: '#fee2e2', color: '#dc2626' }}>Delete All Data</button>
        </div>
      </div>

      <div className="page-body">
        {/* Stat cards */}
        {stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 24 }}>
            {[
              { label: 'Total Filings', value: stats.parsing_total, color: '#3b82f6' },
              { label: 'Parsed', value: stats.parsing_parsed, color: '#22c55e' },
              { label: 'Not Parsed', value: stats.parsing_not_parsed, color: '#ef4444' },
              { label: 'No Table Found', value: stats.parsing_no_table, color: '#f59e0b' },
              { label: 'Already Exist', value: stats.parsing_already_exist, color: '#6366f1' },
              { label: 'Companies', value: stats.companies, color: '#8b5cf6' },
              { label: 'Officers', value: stats.officers, color: '#06b6d4' },
              { label: 'SCT Records', value: stats.sct_records, color: '#10b981' },
            ].map(function (s, i) {
              return (
                <div key={i} style={{ background: 'white', borderRadius: 10, padding: '20px 16px', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' }}>
                  <div style={{ fontSize: 28, fontWeight: 700, color: s.color }}>{s.value || 0}</div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{s.label}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid #e2e8f0', marginBottom: 20 }}>
          {[
            { id: 'tracking', label: 'Filing Tracker' },
            { id: 'rss', label: 'Today\'s RSS Feed' },
            { id: 'sct', label: 'SCT Tables' },
            { id: 'equity', label: 'Equity' },
            { id: 'exercise', label: 'Exercise' },
            { id: 'pba', label: 'PBA' },
            { id: 'dct', label: 'DCT' },
          ].map(function (t) {
            return (
              <button key={t.id} onClick={function () { loadTab(t.id); }}
                style={{
                  padding: '12px 20px', border: 'none', cursor: 'pointer',
                  background: tab === t.id ? '#1e293b' : 'transparent',
                  color: tab === t.id ? 'white' : '#64748b',
                  fontWeight: tab === t.id ? 700 : 400, fontSize: 13,
                  borderRadius: '8px 8px 0 0',
                }}>
                {t.label}
              </button>
            );
          })}
        </div>

        {dataLoading && <div className="loading">Loading...</div>}

        {/* FILING TRACKER TAB — The main view your HOD needs */}
        {tab === 'tracking' && !dataLoading && data && (
          <div>
            <div style={{ marginBottom: 16, padding: 16, background: '#eff6ff', borderRadius: 8, border: '1px solid #bfdbfe' }}>
              <strong style={{ color: '#1e40af' }}>How to read this:</strong>
              <ul style={{ margin: '8px 0 0', paddingLeft: 20, color: '#1e40af', fontSize: 13, lineHeight: 1.8 }}>
                <li><span style={badge('Parsed')}>Parsed</span> = Compensation table found and data extracted</li>
                <li><span style={badge('Not Parsed')}>Not Parsed</span> = Page couldn't be processed (retry needed)</li>
                <li><span style={badge('No Table Found')}>No Table Found</span> = Filing has no compensation table (investment funds, small companies — this is normal)</li>
                <li><span style={badge('Already Exist')}>Already Exist</span> = Already processed in a previous run</li>
              </ul>
            </div>
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
                    {(data.records || []).map(function (r, i) {
                      var pd = String(r.Parsed_Date || '');
                      // Fix DD/MM/YYYY display
                      var dateStr = pd && pd !== 'nan' && pd !== 'None' ? pd : '-';
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? 'white' : '#f8fafc' }}>
                          <td style={{ padding: 8, color: '#94a3b8' }}>{i + 1}</td>
                          <td style={{ padding: 8, fontWeight: 600 }}>{r.CompanyName || '-'}</td>
                          <td style={{ padding: 8 }}>{r.FiscalYear || '-'}</td>
                          <td style={{ padding: 8 }}><span style={badge(r.SCT_Parsed)}>{r.SCT_Parsed || '-'}</span></td>
                          <td style={{ padding: 8 }}><span style={badge(r.Outstanding_Equity_Parsed)}>{r.Outstanding_Equity_Parsed || '-'}</span></td>
                          <td style={{ padding: 8 }}><span style={badge(r.Vested_Parsed)}>{r.Vested_Parsed || '-'}</span></td>
                          <td style={{ padding: 8 }}><span style={badge(r.PBA_Parsed)}>{r.PBA_Parsed || '-'}</span></td>
                          <td style={{ padding: 8, fontSize: 11 }}>{dateStr}</td>
                          <td style={{ padding: 8 }}>{r.Link ? <a href={r.Link} target="_blank" rel="noreferrer" style={{ color: '#3b82f6', fontSize: 11 }}>View</a> : '-'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* RSS FEED TAB */}
        {tab === 'rss' && !dataLoading && data && (
          <div className="card">
            <div className="card-header">SEC EDGAR Filings Received — {data.total || 0} companies ({data.file || 'no file'})</div>
            <div className="card-body" style={{ padding: 0 }}>
              {data.companies && data.companies.length > 0 ? (
                <table style={{ fontSize: 12, width: '100%' }}>
                  <thead><tr style={{ background: '#1e293b', color: 'white' }}>
                    <th style={{ padding: 10 }}>#</th>
                    <th style={{ padding: 10 }}>Company Name</th>
                    <th style={{ padding: 10 }}>Fiscal Year</th>
                    <th style={{ padding: 10 }}>Filing Date</th>
                    <th style={{ padding: 10 }}>SEC Filing</th>
                  </tr></thead>
                  <tbody>
                    {data.companies.map(function (c, i) {
                      return (
                        <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? 'white' : '#f8fafc' }}>
                          <td style={{ padding: 8, color: '#94a3b8' }}>{i + 1}</td>
                          <td style={{ padding: 8, fontWeight: 600 }}>{c.CompanyName || '-'}</td>
                          <td style={{ padding: 8 }}>{c.FiscalYear || '-'}</td>
                          <td style={{ padding: 8 }}>{c.Filing_Date || '-'}</td>
                          <td style={{ padding: 8 }}><a href={c.Link || '#'} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>Open Filing</a></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : <p style={{ color: '#94a3b8', textAlign: 'center', padding: 30 }}>No RSS feed today. Run the rss_feed step first.</p>}
            </div>
          </div>
        )}

        {/* SCT TABLES TAB */}
        {tab === 'sct' && !dataLoading && data && (
          <div>
            {data.grouped && data.grouped.length > 0 ? (
              <div>
                <p style={{ color: '#64748b', marginBottom: 16 }}>{data.companies_count} companies | {data.total} records</p>
                {data.grouped.map(function (company, ci) {
                  return (
                    <div key={ci} className="card" style={{ marginBottom: 20 }}>
                      <div style={{ background: '#1e293b', color: 'white', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderRadius: '8px 8px 0 0' }}>
                        <div>
                          <strong>{company.CompanyName}</strong>
                          <span style={{ marginLeft: 12, opacity: 0.7, fontSize: 12 }}>FY {company.FiscalYear || '-'}</span>
                        </div>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 11 }}>
                          {company.Parsed_Date && <span style={{ opacity: 0.7 }}>Parsed: {company.Parsed_Date}</span>}
                          <span style={{ padding: '3px 10px', borderRadius: 10, fontWeight: 600, background: company.SCT_Parsed === 'Parsed' ? '#22c55e' : '#f59e0b', color: 'white' }}>{company.SCT_Parsed || '?'}</span>
                        </div>
                      </div>
                      {company.FilingURL && (
                        <div style={{ padding: '6px 16px', background: '#f1f5f9', fontSize: 11 }}>
                          <a href={company.FilingURL} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>{company.FilingURL}</a>
                        </div>
                      )}
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ fontSize: 12, width: '100%' }}>
                          <thead><tr style={{ background: '#f8fafc' }}>
                            <th style={{ padding: '8px', textAlign: 'left' }}>Officer Name</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Year</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Salary</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Bonus</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Stock Awards</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Option Awards</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Non-Equity</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>Pension</th>
                            <th style={{ padding: '8px', textAlign: 'right' }}>All Other</th>
                            <th style={{ padding: '8px', textAlign: 'right', fontWeight: 700 }}>Total</th>
                          </tr></thead>
                          <tbody>
                            {company.officers.map(function (o, oi) {
                              return (
                                <tr key={oi} style={{ background: oi % 2 === 0 ? 'white' : '#f8fafc' }}>
                                  <td style={{ padding: 8, fontWeight: 500 }}>{o.OfficerName || '-'}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{o.FiscalYear || '-'}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Salary)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Bonus)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Stock_Award)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Option_Awards)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Non_Eq_Incentive_Plan_Comp)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.Chg_PensionValue_NQDC_Earnings)}</td>
                                  <td style={{ padding: 8, textAlign: 'right' }}>{fmt(o.All_Other)}</td>
                                  <td style={{ padding: 8, textAlign: 'right', fontWeight: 700, color: '#1e40af' }}>{fmt(o.Total)}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <p style={{ color: '#94a3b8', textAlign: 'center', padding: 30 }}>No SCT data. Run pipeline: rss_feed → sct_parse → sql_parse</p>}
          </div>
        )}

        {/* EQUITY / EXERCISE / PBA TABS */}
        {(tab === 'equity' || tab === 'exercise' || tab === 'pba' || tab === 'dct') && !dataLoading && data && (
          <div>
            {data.grouped && data.grouped.length > 0 ? (
              <div>
                <p style={{ color: '#64748b', marginBottom: 16 }}>{data.companies_count} companies | {data.total} records</p>
                {data.grouped.map(function (company, ci) {
                  return (
                    <div key={ci} className="card" style={{ marginBottom: 20 }}>
                      <div style={{ background: '#1e293b', color: 'white', padding: '12px 16px', borderRadius: '8px 8px 0 0' }}>
                        <strong>{company.CompanyName}</strong>
                        <span style={{ marginLeft: 12, opacity: 0.7, fontSize: 12 }}>FY {company.FiscalYear || '-'}</span>
                      </div>
                      {company.FilingURL && (
                        <div style={{ padding: '6px 16px', background: '#f1f5f9', fontSize: 11 }}>
                          <a href={company.FilingURL} target="_blank" rel="noreferrer" style={{ color: '#3b82f6' }}>{company.FilingURL}</a>
                        </div>
                      )}
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ fontSize: 12, width: '100%' }}>
                          <thead><tr style={{ background: '#f8fafc' }}>
                            <th style={{ padding: 8, textAlign: 'left' }}>Officer</th>
                            <th style={{ padding: 8 }}>Year</th>
                            {tab === 'equity' && <React.Fragment><th style={{ padding: 8 }}>Type</th><th style={{ padding: 8 }}>Securities</th><th style={{ padding: 8 }}>Ex Price</th><th style={{ padding: 8 }}>Market Value</th></React.Fragment>}
                            {tab === 'exercise' && <React.Fragment><th style={{ padding: 8 }}>Opt Shares</th><th style={{ padding: 8 }}>Opt Value</th><th style={{ padding: 8 }}>Stk Shares</th><th style={{ padding: 8 }}>Stk Value</th></React.Fragment>}
                            {tab === 'pba' && <React.Fragment><th style={{ padding: 8 }}>Category</th><th style={{ padding: 8 }}>Threshold</th><th style={{ padding: 8 }}>Target</th><th style={{ padding: 8 }}>Maximum</th></React.Fragment>}
                            {tab === 'dct' && <React.Fragment><th style={{ padding: 8 }}>Fees Earned</th><th style={{ padding: 8 }}>Stock Awards</th><th style={{ padding: 8 }}>Option Awards</th><th style={{ padding: 8 }}>All Other</th><th style={{ padding: 8 }}>Total</th></React.Fragment>}
                          </tr></thead>
                          <tbody>
                            {company.officers.map(function (o, oi) {
                              return (
                                <tr key={oi} style={{ background: oi % 2 === 0 ? 'white' : '#f8fafc' }}>
                                  <td style={{ padding: 8, fontWeight: 500 }}>{o.OfficerName || o.Director_Name || '-'}</td>
                                  <td style={{ padding: 8 }}>{o.FiscalYear || '-'}</td>
                                  {tab === 'equity' && <React.Fragment>
                                    <td style={{ padding: 8 }}>{o.Equity_Type || '-'}</td>
                                    <td style={{ padding: 8 }}>{o.Number_Securities || '-'}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Exercise_Price)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Market_Value)}</td>
                                  </React.Fragment>}
                                  {tab === 'exercise' && <React.Fragment>
                                    <td style={{ padding: 8 }}>{o.Option_Shares_Acquired || '-'}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Option_Value_Realized)}</td>
                                    <td style={{ padding: 8 }}>{o.Stock_Shares_Acquired || '-'}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Stock_Value_Realized)}</td>
                                  </React.Fragment>}
                                  {tab === 'pba' && <React.Fragment>
                                    <td style={{ padding: 8 }}>{o.Award_Category || '-'}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Threshold)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Target)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Maximum)}</td>
                                  </React.Fragment>}
                                  {tab === 'dct' && <React.Fragment>
                                    <td style={{ padding: 8 }}>{fmt(o.FeesEarnedorPaid)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.StockAwards)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.OptionAwards)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.AllotherComp)}</td>
                                    <td style={{ padding: 8 }}>{fmt(o.Total)}</td>
                                  </React.Fragment>}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <p style={{ color: '#94a3b8', textAlign: 'center', padding: 30 }}>No {tab} data yet. Run the {tab}_parse pipeline step.</p>}
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
