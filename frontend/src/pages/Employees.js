import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { employeesApi } from '../api';
import toast from 'react-hot-toast';

const API_BASE = process.env.REACT_APP_API_URL || 'http://127.0.0.1:8001';

function formatFileSize(bytes) {
  if (!bytes) return '0 KB';
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(2)} MB` : `${Math.max(bytes / 1024, 0).toFixed(0)} KB`;
}

function PhotoDropzone({ onFiles }) {
  const [dragging, setDragging] = useState(false);

  const handleFiles = useCallback((files) => {
    const imgs = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (imgs.length) onFiles(imgs);
  }, [onFiles]);

  const openPicker = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.multiple = true;
    input.accept = 'image/*';
    input.onchange = e => handleFiles(e.target.files || []);
    input.click();
  }, [handleFiles]);

  return (
    <div
      className={`dropzone ${dragging ? 'active' : ''}`}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
      onClick={openPicker}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') openPicker(); }}
    >
      <div className="dropzone-icon">📸</div>
      <div className="dropzone-text">Drop face photos or click to upload</div>
      <div className="dropzone-sub">Multiple images supported · JPEG, PNG, WebP · Max 10MB each</div>
    </div>
  );
}

function EmployeeModal({ employee, onClose, onSaved }) {
  const [form, setForm] = useState(
    employee
      ? {
          first_name: employee.first_name,
          last_name: employee.last_name,
          employee_code: employee.employee_code || '',
          department: employee.department || '',
          designation: employee.designation || '',
          email: employee.email || '',
          phone: employee.phone || '',
        }
      : {
          first_name: '',
          last_name: '',
          employee_code: '',
          department: '',
          designation: '',
          email: '',
          phone: '',
        }
  );
  const [photos, setPhotos] = useState(employee?.photos || []);
  const [queuedPhotos, setQueuedPhotos] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  const queuedPreview = useMemo(
    () => queuedPhotos.map(file => ({
      name: file.name,
      size: file.size,
      type: file.type,
    })),
    [queuedPhotos]
  );

  const appendQueuedPhotos = useCallback((files) => {
    const incoming = Array.from(files).filter(f => f.type.startsWith('image/'));
    if (!incoming.length) return;
    setQueuedPhotos(prev => {
      const existing = new Set(prev.map(f => `${f.name}-${f.size}-${f.lastModified}`));
      const next = [...prev];
      for (const file of incoming) {
        const sig = `${file.name}-${file.size}-${file.lastModified}`;
        if (!existing.has(sig)) {
          next.push(file);
          existing.add(sig);
        }
      }
      return next;
    });
  }, []);

  const removeQueuedPhoto = (index) => {
    setQueuedPhotos(prev => prev.filter((_, i) => i !== index));
  };

  const uploadQueuedPhotos = useCallback(async (employeeId) => {
    if (!queuedPhotos.length || !employeeId) return;
    const fd = new FormData();
    queuedPhotos.forEach(file => fd.append('files', file));
    await employeesApi.uploadPhotoBatch(employeeId, fd);
    const res = await employeesApi.get(employeeId);
    setPhotos(res.data.photos || []);
    setQueuedPhotos([]);
  }, [queuedPhotos]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      let employeeId = employee?.id;

      if (employee) {
        await employeesApi.update(employee.id, form);
        toast.success('Employee updated');
      } else {
        const created = await employeesApi.create(form);
        employeeId = created.data.id;
        toast.success('Employee created');
      }

      if (queuedPhotos.length && employeeId) {
        setUploading(true);
        try {
          const uploadCount = queuedPhotos.length;
          await uploadQueuedPhotos(employeeId);
          toast.success(`${uploadCount} photo(s) uploaded`);
        } catch (uploadErr) {
          console.error('Photo upload failed', uploadErr);
          toast.error('Employee saved, but photo upload failed');
        } finally {
          setUploading(false);
        }
      }

      onSaved();
      onClose();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail || 'Error saving employee');
    } finally {
      setUploading(false);
      setSaving(false);
    }
  };

  const handleDeletePhoto = async (photoId) => {
    if (!employee) return;
    try {
      await employeesApi.deletePhoto(employee.id, photoId);
      setPhotos(p => p.filter(ph => ph.id !== photoId));
      toast.success('Photo removed');
    } catch {
      toast.error('Error deleting photo');
    }
  };

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 760 }}>
        <div className="modal-header">
          <h2 className="modal-title">{employee ? 'Edit Employee' : 'Add Employee'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {employee && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, padding: '10px 14px', background: 'var(--bg-3)', borderRadius: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>FACE ID</span>
                <span className="face-id">{employee.face_id}</span>
                <span className={`badge ${employee.face_encoding ? 'badge-green' : 'badge-red'}`} style={{ marginLeft: 'auto' }}>
                  {employee.face_encoding ? 'Face encoded' : 'No encoding'}
                </span>
              </div>
            )}

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">First Name *</label>
                <input className="form-input" required value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Last Name *</label>
                <input className="form-input" required value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Employee Code</label>
                <input className="form-input" value={form.employee_code} onChange={e => setForm(f => ({ ...f, employee_code: e.target.value }))} placeholder="Auto-generated" />
              </div>
              <div className="form-group">
                <label className="form-label">Department</label>
                <input className="form-input" value={form.department} onChange={e => setForm(f => ({ ...f, department: e.target.value }))} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Designation</label>
                <input className="form-input" value={form.designation} onChange={e => setForm(f => ({ ...f, designation: e.target.value }))} />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input className="form-input" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
              </div>
            </div>

            <div style={{ marginTop: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
                <label className="form-label" style={{ marginBottom: 0 }}>Face Photos (Multiple Angles)</label>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {employee ? 'Upload now or after editing' : 'Upload now, save once'}
                </span>
              </div>

              <PhotoDropzone onFiles={appendQueuedPhotos} />

              {!employee && (
                <p style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 8 }}>
                  Pick multiple photos now. They will be uploaded automatically after the employee is created.
                </p>
              )}

              {queuedPreview.length > 0 && (
                <div className="photo-grid" style={{ marginTop: 12 }}>
                  {queuedPreview.map((photo, idx) => (
                    <div className="photo-item" key={`${photo.name}-${idx}`} style={{ minHeight: 104, aspectRatio: 'auto' }}>
                      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 6, height: '100%' }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-primary)', wordBreak: 'break-word' }}>{photo.name}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {formatFileSize(photo.size)}
                        </div>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          style={{ alignSelf: 'flex-start', padding: '4px 8px' }}
                          onClick={() => removeQueuedPhoto(idx)}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {employee && photos.length > 0 && (
                <div className="photo-grid" style={{ marginTop: 12 }}>
                  {photos.map(p => (
                    <div className="photo-item" key={p.id}>
                      <img src={`${API_BASE}/${p.file_path}`} alt={p.angle_label || 'employee'} />
                      {p.is_primary && <div className="photo-primary-badge">PRIMARY</div>}
                      <div className="photo-label">{p.angle_label || 'front'}</div>
                      <button type="button" className="photo-delete" onClick={() => handleDeletePhoto(p.id)}>×</button>
                    </div>
                  ))}
                </div>
              )}

              {employee && photos.length === 0 && !uploading && (
                <p style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 8 }}>
                  No saved photos yet. Add several images for better recognition.
                </p>
              )}

              {uploading && (
                <div style={{ textAlign: 'center', padding: 8, fontSize: 12, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
                  Uploading and encoding faces...
                </div>
              )}
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={saving || uploading}>
              {saving ? 'Saving...' : (employee ? 'Update' : 'Create Employee')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Employees() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [search, setSearch] = useState('');

  const load = useCallback(() => {
    employeesApi.list()
      .then(r => setEmployees(r.data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this employee and all their data?')) return;
    try {
      await employeesApi.delete(id);
      toast.success('Employee deleted');
      load();
    } catch {
      toast.error('Error deleting employee');
    }
  };

  const filtered = employees.filter(e =>
    `${e.first_name} ${e.last_name} ${e.face_id} ${e.department || ''}`.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div className="loading"><div className="spinner" /> Loading employees...</div>;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Employees</h1>
          <p className="page-subtitle">{employees.length} registered · Face ID recognition enabled</p>
        </div>
        <button className="btn btn-primary" onClick={() => setModal('add')}>+ Add Employee</button>
      </div>

      <div style={{ marginBottom: 20 }}>
        <input
          className="form-input"
          style={{ maxWidth: 360 }}
          placeholder="Search name, face ID, department..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="card">
        {filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">◉</div>
            <div className="empty-text">{search ? 'No results' : 'No employees yet'}</div>
            <div className="empty-sub">{search ? 'Try a different search' : 'Add employees to enable face recognition'}</div>
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Face ID</th>
                  <th>Department</th>
                  <th>Designation</th>
                  <th>Photos</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(emp => {
                  const primary = emp.photos?.find(p => p.is_primary) || emp.photos?.[0];
                  return (
                    <tr key={emp.id}>
                      <td>
                        <div className="employee-info">
                          <div className="employee-avatar">
                            {primary
                              ? <img src={`${API_BASE}/${primary.file_path}`} alt="face" />
                              : '◉'}
                          </div>
                          <div>
                            <div className="employee-name">{emp.first_name} {emp.last_name}</div>
                            <div className="employee-dept">{emp.employee_code || '—'}</div>
                          </div>
                        </div>
                      </td>
                      <td><span className="face-id">{emp.face_id}</span></td>
                      <td>{emp.department || '—'}</td>
                      <td>{emp.designation || '—'}</td>
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                          {emp.photos?.length || 0} {emp.photos?.length === 1 ? 'photo' : 'photos'}
                        </span>
                      </td>
                      <td><span className={`badge ${emp.is_active ? 'badge-green' : 'badge-red'}`}>{emp.is_active ? 'Active' : 'Inactive'}</span></td>
                      <td>
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-ghost btn-sm" onClick={() => setModal(emp)}>Edit</button>
                          <button className="btn btn-danger btn-sm" onClick={() => handleDelete(emp.id)}>Delete</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modal && (
        <EmployeeModal
          employee={modal === 'add' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}
