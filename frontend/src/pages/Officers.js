import React, { useState, useEffect, useCallback } from 'react';
import { getOfficers } from '../api';

function Officers() {
  var officers_state = useState([]);
  var officers = officers_state[0];
  var setOfficers = officers_state[1];

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

  var hasMore_state = useState(false);
  var hasMore = hasMore_state[0];
  var setHasMore = hasMore_state[1];

  var fetchOfficers = useCallback(function () {
    setLoading(true);
    setError(null);
    getOfficers({ search: search, page: page })
      .then(function (data) {
        var list = data.officers || [];
        setOfficers(list);
        setHasMore(list.length >= 20);
      })
      .catch(function (err) {
        setError((err && err.message) || 'Failed to load officers');
      })
      .finally(function () {
        setLoading(false);
      });
  }, [search, page]);

  useEffect(function () { fetchOfficers(); }, [fetchOfficers]);

  var handleSearch = function (e) {
    setSearch(e.target.value);
    setPage(1);
  };

  var formatGender = function (val) {
    if (val === 1 || val === '1') return 'Male';
    if (val === 2 || val === '2') return 'Female';
    return val || '-';
  };

  return (
    <div>
      <div className="page-header">
        <h2>Officers</h2>
      </div>
      <div className="page-body">
        {error && <div className="error-message">{error}</div>}
        <div className="toolbar">
          <input
            className="search-input"
            type="text"
            placeholder="Search officers..."
            value={search}
            onChange={handleSearch}
          />
        </div>

        {loading ? (
          <div className="loading">Loading officers...</div>
        ) : (
          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Officer Name</th>
                      <th>Company</th>
                      <th>Fiscal Year</th>
                      <th>First Name</th>
                      <th>Last Name</th>
                      <th>Gender</th>
                    </tr>
                  </thead>
                  <tbody>
                    {officers.map(function (o, i) {
                      return (
                        <tr key={i}>
                          <td><strong>{o.OfficerName || o.officer_name || '-'}</strong></td>
                          <td>{o.CompanyName || o.company_name || '-'}</td>
                          <td>{o.FiscalYear || o.fiscal_year || '-'}</td>
                          <td>{o.First_name || o.first_name || o.FirstName || '-'}</td>
                          <td>{o.Last_name || o.last_name || o.LastName || '-'}</td>
                          <td>{formatGender(o.Gender || o.gender)}</td>
                        </tr>
                      );
                    })}
                    {officers.length === 0 && (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', color: '#94a3b8', padding: 40 }}>
                          No officers found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        <div className="pagination">
          <button onClick={function () { setPage(function (p) { return p - 1; }); }} disabled={page <= 1}>Previous</button>
          <span className="page-info">Page {page}</span>
          <button onClick={function () { setPage(function (p) { return p + 1; }); }} disabled={!hasMore}>Next</button>
        </div>
      </div>
    </div>
  );
}

export default Officers;
