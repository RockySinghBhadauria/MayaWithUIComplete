import React, { useState, useEffect, useRef, useCallback } from 'react';
import { getPipelineSteps, runPipeline, getPipelineStatus, getPipelineHistory, getLogs, deleteTodayData, stopPipeline } from '../api';

var STEP_DESCRIPTIONS = {
  rss_feed: 'Fetch SEC EDGAR filings',
  sct_parse: 'Parse compensation tables',
  data_entry: 'Insert company metadata to DB',
  sql_parse: 'Process officer data',
  equity_parse: 'Parse equity holdings',
  exercise_parse: 'Parse option exercises',
  pba_parse: 'Parse plan-based awards',
  dct_parse: 'Parse director compensation',
};

function Pipeline() {
  var _s = function(init) { return useState(init); };

  var _steps = _s([]), steps = _steps[0], setSteps = _steps[1];
  var _status = _s(null), status = _status[0], setStatus = _status[1];
  var _history = _s([]), history = _history[0], setHistory = _history[1];
  var _loading = _s(true), loading = _loading[0], setLoading = _loading[1];
  var _error = _s(null), error = _error[0], setError = _error[1];
  var _running = _s(false), isRunning = _running[0], setIsRunning = _running[1];
  var _logs = _s([]), logs = _logs[0], setLogs = _logs[1];
  var _elapsed = _s(0), elapsed = _elapsed[0], setElapsed = _elapsed[1];

  var pollRef = useRef(null);
  var timerRef = useRef(null);
  var logsEndRef = useRef(null);

  var fetchAll = useCallback(function () {
    Promise.all([getPipelineSteps(), getPipelineHistory(), getPipelineStatus()])
      .then(function (results) {
        setSteps(results[0].steps || []);
        setHistory(results[1].runs || []);
        var st = results[2];
        setStatus(st);
        // Check if running from API OR if any step shows "running"
        var apiRunning = st && st.is_running;
        var stepRunning = st && st.steps && st.steps.some(function (s) { return s.status === 'running'; });
        if (apiRunning || stepRunning) {
          setIsRunning(true);
          startPolling();
        } else {
          setIsRunning(false);
        }
      })
      .catch(function (err) {
        setError((err && err.message) || 'Failed to load');
      })
      .finally(function () { setLoading(false); });
  }, []);

  useEffect(function () {
    fetchAll();
    return function () {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchAll]);

  var startPolling = useCallback(function () {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);

    setElapsed(0);
    timerRef.current = setInterval(function () {
      setElapsed(function (prev) { return prev + 1; });
    }, 1000);

    pollRef.current = setInterval(function () {
      Promise.all([getPipelineStatus(), getLogs(50)])
        .then(function (results) {
          var s = results[0];
          var l = results[1];
          setStatus(s);
          setLogs(l.logs || []);
          if (!s.is_running) {
            clearInterval(pollRef.current);
            clearInterval(timerRef.current);
            pollRef.current = null;
            timerRef.current = null;
            setIsRunning(false);
            // Refresh history
            getPipelineHistory().then(function (h) {
              setHistory(h.runs || []);
            });
          }
        })
        .catch(function () {});
    }, 2000);
  }, []);

  var handleRun = function (step) {
    var body = step ? { step: step } : {};
    setIsRunning(true);
    setError(null);
    setLogs([]);
    runPipeline(body)
      .then(function () { startPolling(); })
      .catch(function (err) {
        var detail = (err && err.response && err.response.data && err.response.data.detail) || (err && err.message) || 'Failed';
        setError(detail);
        setIsRunning(false);
      });
  };

  var formatTime = function (secs) {
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    return (m > 0 ? m + 'm ' : '') + s + 's';
  };

  var getStepInfo = function (stepName) {
    if (!status || !status.steps) return null;
    for (var i = 0; i < status.steps.length; i++) {
      if ((status.steps[i].step_name || '') === stepName) return status.steps[i];
    }
    return null;
  };

  var badgeStyle = function (s) {
    if (!s || s === '-') return { background: 'transparent', color: '#cbd5e1' };
    var l = s.toLowerCase();
    if (l === 'completed') return { background: '#dcfce7', color: '#16a34a' };
    if (l === 'failed') return { background: '#fee2e2', color: '#dc2626' };
    if (l === 'running') return { background: '#fef3c7', color: '#d97706', animation: 'pulse 1.5s infinite' };
    return { background: '#e2e8f0', color: '#64748b' };
  };

  if (loading) return <div className="loading">Loading pipeline...</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Pipeline Control</h2>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            className="btn"
            onClick={function () {
              if (window.confirm('Delete TODAY\'s parsed data? This lets you re-run the pipeline fresh.')) {
                deleteTodayData().then(function () { fetchAll(); }).catch(function (e) { setError(e.message); });
              }
            }}
            disabled={isRunning}
            style={{ background: '#fef3c7', color: '#92400e', border: '1px solid #fbbf24', padding: '10px 16px', borderRadius: 6, cursor: 'pointer' }}
          >
            Reset Today
          </button>
          {isRunning ? (
            <button
              className="btn"
              onClick={function () {
                stopPipeline().then(function () {
                  setIsRunning(false);
                  fetchAll();
                }).catch(function (e) { setError((e && e.message) || 'Stop failed'); });
              }}
              style={{ fontSize: 16, padding: '10px 24px', background: '#ef4444', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer' }}
            >
              {'\u25A0'} Stop Pipeline
            </button>
          ) : (
            <button
              className="btn btn-success"
              onClick={function () { handleRun(null); }}
              style={{ fontSize: 16, padding: '10px 24px' }}
            >
              {'\u25B6'} Run All Steps
            </button>
          )}
        </div>
      </div>
      <div className="page-body">
        {error && <div className="error-message">{error}</div>}

        {/* Running indicator bar */}
        {isRunning && (
          <div style={{
            background: 'linear-gradient(90deg, #3b82f6, #8b5cf6, #3b82f6)',
            backgroundSize: '200% 100%',
            animation: 'shimmer 2s linear infinite',
            height: 4, borderRadius: 2, marginBottom: 20
          }} />
        )}

        {/* Running status banner */}
        {isRunning && (
          <div style={{
            background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8,
            padding: '16px 20px', marginBottom: 20, display: 'flex',
            alignItems: 'center', justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{
                width: 12, height: 12, borderRadius: '50%', background: '#3b82f6',
                animation: 'pulse 1s infinite'
              }} />
              <span style={{ fontWeight: 600, color: '#1e40af' }}>
                Pipeline is running...
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <span style={{ color: '#3b82f6', fontWeight: 600, fontSize: 18 }}>
                {formatTime(elapsed)}
              </span>
              <button
                onClick={function () {
                  stopPipeline().then(function () {
                    setIsRunning(false);
                    fetchAll();
                  }).catch(function () {});
                }}
                style={{ padding: '8px 20px', background: '#ef4444', color: 'white', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 }}
              >
                {'\u25A0'} STOP
              </button>
            </div>
          </div>
        )}

        {/* Pipeline Steps */}
        <div className="card">
          <div className="card-header">Pipeline Steps</div>
          <div className="card-body" style={{ padding: 0 }}>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th style={{width: 40}}>#</th>
                    <th>Step</th>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Processed</th>
                    <th>Parsed</th>
                    <th>Failed</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map(function (step, i) {
                    var name = typeof step === 'string' ? step : (step.name || '');
                    var info = getStepInfo(name);
                    var hasRun = status && status.steps && status.steps.length > 0;
                    var st = info ? (info.status || '-') : (hasRun ? '-' : '-');
                    var desc = STEP_DESCRIPTIONS[name] || '';

                    return (
                      <tr key={i} style={st === 'running' ? {background: '#eff6ff'} : {}}>
                        <td style={{color: '#94a3b8'}}>{i + 1}</td>
                        <td><strong>{name}</strong></td>
                        <td style={{color: '#64748b'}}>{desc}</td>
                        <td>
                          <span style={Object.assign({
                            padding: '4px 12px', borderRadius: 12, fontSize: 12,
                            fontWeight: 600, display: 'inline-block'
                          }, badgeStyle(st))}>
                            {st === 'running' ? '\u23F3 ' + st : st}
                          </span>
                        </td>
                        <td>{info ? (info.companies_processed || 0) : '-'}</td>
                        <td style={{color: '#16a34a'}}>{info ? (info.companies_parsed || 0) : '-'}</td>
                        <td style={{color: info && info.companies_failed > 0 ? '#dc2626' : '#64748b'}}>
                          {info ? (info.companies_failed || 0) : '-'}
                        </td>
                        <td>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={function () { handleRun(name); }}
                            disabled={isRunning}
                          >
                            Run
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Live Logs (shown when running or when logs exist) */}
        {(isRunning || logs.length > 0) && (
          <div className="card" style={{ marginTop: 20 }}>
            <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>
                Live Logs
                {isRunning && (
                  <span style={{
                    display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                    background: '#22c55e', marginLeft: 8, animation: 'pulse 1s infinite'
                  }} />
                )}
              </span>
              <span style={{ fontSize: 12, color: '#94a3b8' }}>{logs.length} entries</span>
            </div>
            <div style={{
              background: '#0f172a', color: '#e2e8f0', fontFamily: 'monospace',
              fontSize: 12, padding: 16, maxHeight: 300, overflowY: 'auto',
              borderRadius: '0 0 8px 8px', lineHeight: 1.6
            }}>
              {logs.length > 0 ? logs.map(function (line, i) {
                var color = '#e2e8f0';
                if (line.indexOf('ERROR') !== -1) color = '#f87171';
                if (line.indexOf('WARNING') !== -1) color = '#fbbf24';
                if (line.indexOf('INFO') !== -1 && line.indexOf('Added:') !== -1) color = '#4ade80';
                if (line.indexOf('complete') !== -1 || line.indexOf('Saved') !== -1) color = '#22d3ee';
                return <div key={i} style={{ color: color }}>{line}</div>;
              }) : <div style={{color: '#64748b'}}>Waiting for log output...</div>}
              <div ref={logsEndRef} />
            </div>
          </div>
        )}

        {/* Pipeline History */}
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-header">Pipeline History</div>
          <div className="card-body" style={{ padding: 0 }}>
            {history.length > 0 ? (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Run Group</th>
                      <th>Date</th>
                      <th>Steps</th>
                      <th>Completed</th>
                      <th>Failed</th>
                      <th>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map(function (run, i) {
                      var duration = '-';
                      if (run.started && run.finished) {
                        var secs = Math.round((new Date(run.finished) - new Date(run.started)) / 1000);
                        duration = formatTime(secs);
                      }
                      return (
                        <tr key={i}>
                          <td style={{fontFamily: 'monospace', fontSize: 12}}>{run.run_group || '-'}</td>
                          <td>{run.run_date || '-'}</td>
                          <td>{run.total_steps || 0}</td>
                          <td style={{ color: '#16a34a', fontWeight: 600 }}>{run.completed || 0}</td>
                          <td style={{ color: (run.failed || 0) > 0 ? '#dc2626' : '#64748b', fontWeight: 600 }}>
                            {run.failed || 0}
                          </td>
                          <td>{duration}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ color: '#94a3b8', textAlign: 'center', padding: 20 }}>No pipeline history</p>
            )}
          </div>
        </div>
      </div>

      <style>{"\
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }\
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }\
      "}</style>
    </div>
  );
}

export default Pipeline;
