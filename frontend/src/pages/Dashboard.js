import React, { useEffect, useState } from 'react';
import { dashboardApi } from '../api';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

const TOOLTIP_STYLE = {
  contentStyle: { background: '#161b24', border: '1px solid #2a3444', borderRadius: 8, fontFamily: 'JetBrains Mono', fontSize: 11 },
  labelStyle: { color: '#7a8899' },
  itemStyle: { color: '#00e5ff' },
};

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);
  const [topDetected, setTopDetected] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      dashboardApi.stats(),
      dashboardApi.activity(7),
      dashboardApi.topDetected(5),
    ]).then(([s, a, t]) => {
      setStats(s.data);
      setActivity(a.data);
      setTopDetected(t.data);
    }).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="loading"><div className="spinner" /> Loading dashboard...</div>;

  const STAT_CARDS = stats ? [
    { label: 'Total Cameras', value: stats.total_cameras, sub: `${stats.active_cameras} active` },
    { label: 'Total Employees', value: stats.total_employees, sub: `${stats.active_employees} active` },
    { label: 'Detections Today', value: stats.detections_today, sub: 'face recognitions' },
    { label: 'This Week', value: stats.detections_this_week, sub: '7-day total' },
  ] : [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">FaceWatch Intelligence Overview</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          <div className="status-dot" />
          Live
        </div>
      </div>

      <div className="stats-grid">
        {STAT_CARDS.map(c => (
          <div className="stat-card" key={c.label}>
            <div className="stat-label">{c.label}</div>
            <div className="stat-value">{c.value}</div>
            <div className="stat-sub">{c.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 20, marginBottom: 24 }}>
        {/* Activity Chart */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Detection Activity (7 days)</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={activity} margin={{ top: 5, right: 10, bottom: 5, left: -20 }}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#00e5ff" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#00e5ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10, fontFamily: 'JetBrains Mono', fill: '#4a5568' }} />
              <YAxis tick={{ fontSize: 10, fontFamily: 'JetBrains Mono', fill: '#4a5568' }} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Area type="monotone" dataKey="count" stroke="#00e5ff" fill="url(#grad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Top Detected */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Top Detected</span>
          </div>
          {topDetected.length === 0 ? (
            <div className="empty-state" style={{ padding: '20px 0' }}>
              <div className="empty-sub">No detections yet</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {topDetected.map((t, i) => (
                <div key={t.face_id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', width: 14 }}>{i + 1}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{t.name}</div>
                    <div className="face-id">{t.face_id}</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--accent)' }}>{t.count}×</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Detections */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Recent Detections</span>
        </div>
        {stats?.recent_detections?.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">◉</div>
            <div className="empty-text">No detections yet</div>
            <div className="empty-sub">Add cameras and employees to begin monitoring</div>
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Face ID</th>
                  <th>Camera</th>
                  <th>Confidence</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {(stats?.recent_detections || []).map(d => (
                  <tr key={d.id}>
                    <td><span className="face-id">{d.face_id || '—'}</span></td>
                    <td>{d.camera_id ? `Cam #${d.camera_id}` : '—'}</td>
                    <td>{d.confidence ? `${d.confidence.toFixed(1)}%` : '—'}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                      {d.timestamp ? new Date(d.timestamp).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
