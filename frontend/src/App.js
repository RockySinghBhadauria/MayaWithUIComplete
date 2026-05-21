import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import './App.css';

import Dashboard from './pages/Dashboard';
import Pipeline from './pages/Pipeline';
import Companies from './pages/Companies';
import Officers from './pages/Officers';
import ParsingSummary from './pages/ParsingSummary';
import Logs from './pages/Logs';

function App() {
  return (
    <Router>
      <div className="app-layout">
        <aside className="sidebar">
          <div className="sidebar-header">
            <h1>MAYA</h1>
            <p>Enhanced Pipeline Dashboard</p>
          </div>
          <nav className="sidebar-nav">
            <NavLink to="/" end>
              <span className="nav-icon">{'\u2302'}</span>
              <span>Dashboard</span>
            </NavLink>
            <NavLink to="/pipeline">
              <span className="nav-icon">{'\u2699'}</span>
              <span>Pipeline</span>
            </NavLink>
            <NavLink to="/companies">
              <span className="nav-icon">{'\u2616'}</span>
              <span>Companies</span>
            </NavLink>
            <NavLink to="/officers">
              <span className="nav-icon">{'\u2639'}</span>
              <span>Officers</span>
            </NavLink>
            <NavLink to="/parsing-summary">
              <span className="nav-icon">{'\u2637'}</span>
              <span>Parsing Summary</span>
            </NavLink>
            <NavLink to="/logs">
              <span className="nav-icon">{'\u2263'}</span>
              <span>Logs</span>
            </NavLink>
          </nav>
        </aside>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/companies" element={<Companies />} />
            <Route path="/officers" element={<Officers />} />
            <Route path="/parsing-summary" element={<ParsingSummary />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
