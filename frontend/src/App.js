import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Dashboard from './pages/Dashboard';
import Cameras from './pages/Cameras';
import Employees from './pages/Employees';
import LiveFeed from './pages/LiveFeed';
import DetectionLogs from './pages/DetectionLogs';
import './App.css';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: '◈' },
  { path: '/cameras', label: 'Cameras', icon: '⬡' },
  { path: '/employees', label: 'Employees', icon: '◉' },
  { path: '/live', label: 'Live Feed', icon: '▶' },
  { path: '/logs', label: 'Detection Logs', icon: '≡' },
];

function Sidebar({ collapsed, onToggle }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="logo">
          <span className="logo-icon">◈</span>
          {!collapsed && <span className="logo-text">FaceWatch</span>}
        </div>
        <button className="collapse-btn" onClick={onToggle}>
          {collapsed ? '→' : '←'}
        </button>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            {!collapsed && <span className="nav-label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        {!collapsed && (
          <div className="system-status">
            <div className="status-dot"></div>
            <span>System Online</span>
          </div>
        )}
      </div>
    </aside>
  );
}

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <BrowserRouter>
      <div className="app-shell">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(c => !c)}
        />
        <main className={`main-content ${sidebarCollapsed ? 'expanded' : ''}`}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/employees" element={<Employees />} />
            <Route path="/live" element={<LiveFeed />} />
            <Route path="/logs" element={<DetectionLogs />} />
          </Routes>
        </main>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'var(--bg-2)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              fontFamily: 'Syne, sans-serif',
            },
          }}
        />
      </div>
    </BrowserRouter>
  );
}

export default App;
