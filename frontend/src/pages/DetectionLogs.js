import React, { useState, useEffect } from 'react';
import { detectionApi, camerasApi } from '../api';

export default function DetectionLogs() {
  const [logs, setLogs] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCamera, setSelectedCamera] = useState('');
  const [filter, setFilter] = useState('all'); // all | known | unknown

  const load = async () => {
    try {
      const [logsRes, camsRes] = await Promise.all([
        detectionApi.logs(selectedCamera || undefined, 100),
        camerasApi.list(),
      ]);
      setLogs(logsRes.data);
      setCameras(camsRes.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [selectedCamera]);

  const filtered = logs.filter(l => {
    if (filter === 'known') return l.face_id && l.face_id !== 'unknown';
    if (filter === 'unknown') return !l.face_id || l.face_id === 'unknown';
    return true;
  });

  if (loading) return <div className="loading"><div className="spinner" /> Loading logs...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Detection Logs</h1>
          <p className="page-subtitle">{filtered.length} records</p>
        </div>
        <button className="btn btn-ghost" onClick={load}>↻ Refresh</button>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <select className="form-select" style={{ width: 200 }} value={selectedCamera} onChange={e => setSelectedCamera(e.target.value)}>
          <option value="">All Cameras</option>
          {cameras.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>

        <div style={{ display: 'flex', gap: 6 }}>
          {['all', 'known', 'unknown'].map(f => (
            <button key={f} className={`btn btn-sm ${filter === f ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setFilter(f)}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        {filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">≡</div>
            <div className="empty-text">No detection logs</div>
            <div className="empty-sub">Logs will appear when faces are detected in live feeds</div>
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Face ID</th>
                  <th>Camera</th>
                  <th>Confidence</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(log => {
                  const cam = cameras.find(c => c.id === log.camera_id);
                  const known = log.face_id && log.face_id !== 'unknown';
                  return (
                    <tr key={log.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>#{log.id}</td>
                      <td>
                        {known
                          ? <span className="face-id">{log.face_id}</span>
                          : <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--danger)' }}>Unknown</span>
                        }
                      </td>
                      <td>{cam ? cam.name : log.camera_id ? `Cam #${log.camera_id}` : '—'}</td>
                      <td>
                        {log.confidence != null ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ height: 4, width: 60, background: 'var(--bg-4)', borderRadius: 2, overflow: 'hidden' }}>
                              <div style={{ height: '100%', width: `${log.confidence}%`, background: log.confidence > 70 ? 'var(--success)' : 'var(--warning)', borderRadius: 2 }} />
                            </div>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{log.confidence.toFixed(1)}%</span>
                          </div>
                        ) : '—'}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
