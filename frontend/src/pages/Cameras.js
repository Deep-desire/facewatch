import React, { useState, useEffect } from 'react';
import { camerasApi } from '../api';
import toast from 'react-hot-toast';

function CameraModal({ camera, onClose, onSaved }) {
  const [form, setForm] = useState(camera || { name: '', location: '', rtsp_url: '', description: '' });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (camera) {
        await camerasApi.update(camera.id, form);
        toast.success('Camera updated');
      } else {
        await camerasApi.create(form);
        toast.success('Camera added');
      }
      onSaved();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error saving camera');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-header">
          <h2 className="modal-title">{camera ? 'Edit Camera' : 'Add Camera'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Camera Name *</label>
              <input className="form-input" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. Main Entrance" />
            </div>
            <div className="form-group">
              <label className="form-label">RTSP URL *</label>
              <input className="form-input" required value={form.rtsp_url} onChange={e => setForm(f => ({ ...f, rtsp_url: e.target.value }))} placeholder="rtsp://192.168.1.100:554/stream" style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} />
            </div>
            <div className="form-group">
              <label className="form-label">Location</label>
              <input className="form-input" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} placeholder="Building A, Floor 2" />
            </div>
            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea className="form-textarea" value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={2} placeholder="Optional description..." />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving...' : (camera ? 'Update' : 'Add Camera')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Cameras() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // null | 'add' | camera object

  const load = () => {
    camerasApi.list().then(r => setCameras(r.data)).catch(console.error).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this camera?')) return;
    try {
      await camerasApi.delete(id);
      toast.success('Camera deleted');
      load();
    } catch { toast.error('Error deleting camera'); }
  };

  const handleToggle = async (id) => {
    try {
      const res = await camerasApi.toggle(id);
      setCameras(prev => prev.map(cam => cam.id === id ? res.data : cam));
      load();
    } catch { toast.error('Error'); }
  };

  if (loading) return <div className="loading"><div className="spinner" /> Loading cameras...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Cameras</h1>
          <p className="page-subtitle">{cameras.length} total · {cameras.filter(c => c.is_active).length} active</p>
        </div>
        <button className="btn btn-primary" onClick={() => setModal('add')}>+ Add Camera</button>
      </div>

      {cameras.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">⬡</div>
          <div className="empty-text">No cameras configured</div>
          <div className="empty-sub">Add your first RTSP camera to begin monitoring</div>
        </div>
      ) : (
        <div className="camera-grid">
          {cameras.map(cam => (
            <div className="camera-card" key={cam.id}>
              <div className="camera-preview">
                <div className="camera-preview-placeholder">
                  <div className="camera-preview-icon">⬡</div>
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>RTSP STREAM</span>
                </div>
                {cam.is_active && (
                  <div className="camera-live-badge">
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--danger)', boxShadow: '0 0 4px var(--danger)' }} />
                    LIVE
                  </div>
                )}
              </div>
              <div className="camera-info">
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
                  <div className="camera-name">{cam.name}</div>
                  <span className={`badge ${cam.is_active ? 'badge-green' : 'badge-red'}`}>
                    {cam.is_active ? 'Active' : 'Off'}
                  </span>
                </div>
                {cam.location && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontFamily: 'var(--font-mono)' }}>📍 {cam.location}</div>
                )}
                <div className="camera-url">{cam.rtsp_url}</div>
                <div className="camera-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => setModal(cam)}>Edit</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleToggle(cam.id)}>
                    {cam.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(cam.id)}>Delete</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <CameraModal
          camera={modal === 'add' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}
