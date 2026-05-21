import React, { useState, useEffect, useRef } from 'react';
import { getLogs } from '../api';

function Logs() {
  var logs_state = useState([]);
  var logs = logs_state[0];
  var setLogs = logs_state[1];

  var loading_state = useState(true);
  var loading = loading_state[0];
  var setLoading = loading_state[1];

  var error_state = useState(null);
  var error = error_state[0];
  var setError = error_state[1];

  var autoScroll_state = useState(true);
  var autoScroll = autoScroll_state[0];
  var setAutoScroll = autoScroll_state[1];

  var autoRefresh_state = useState(true);
  var autoRefresh = autoRefresh_state[0];
  var setAutoRefresh = autoRefresh_state[1];

  var logEndRef = useRef(null);
  var pollRef = useRef(null);

  var fetchLogs = function () {
    getLogs(200)
      .then(function (data) {
        setLogs(data.logs || []);
        setError(null);
      })
      .catch(function (err) {
        if (logs.length === 0) {
          setError((err && err.message) || 'Failed to load logs');
        }
      })
      .finally(function () {
        setLoading(false);
      });
  };

  useEffect(function () {
    fetchLogs();
    if (autoRefresh) {
      pollRef.current = setInterval(fetchLogs, 3000);
    }
    return function () {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [autoRefresh]);

  useEffect(function () {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  var toggleAutoRefresh = function () {
    setAutoRefresh(function (prev) { return !prev; });
  };

  if (loading) return React.createElement('div', { className: 'loading' }, 'Loading logs...');

  return (
    <div>
      <div className="page-header">
        <h2>Logs</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {autoRefresh && (
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 12,
              color: '#22c55e',
              fontWeight: 600
            }}>
              <span style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: '#22c55e',
                display: 'inline-block',
                animation: 'pulse 1.5s infinite'
              }}></span>
              LIVE
            </span>
          )}
          <label style={{ fontSize: 13, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={toggleAutoRefresh}
            />
            Auto-refresh
          </label>
          <label style={{ fontSize: 13, color: '#64748b', display: 'flex', alignItems: 'center', gap: 6 }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={function (e) { setAutoScroll(e.target.checked); }}
            />
            Auto-scroll
          </label>
          <button className="btn btn-outline btn-sm" onClick={fetchLogs}>
            Refresh
          </button>
        </div>
      </div>
      <div className="page-body">
        {error && <div className="error-message">{error}</div>}
        <div className="log-viewer" style={{
          background: '#0f172a',
          borderRadius: 8,
          padding: 16,
          fontFamily: 'monospace',
          fontSize: 13,
          lineHeight: 1.6,
          maxHeight: 600,
          overflowY: 'auto',
          color: '#e2e8f0',
          border: '1px solid #1e293b'
        }}>
          {logs.length > 0 ? (
            logs.map(function (log, i) {
              var line = typeof log === 'string' ? log : ((log && log.message) || (log && log.msg) || JSON.stringify(log));
              return (
                <div className="log-line" key={i} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{line}</div>
              );
            })
          ) : (
            <div style={{ color: '#64748b', textAlign: 'center', padding: 40 }}>No logs available</div>
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}

export default Logs;
