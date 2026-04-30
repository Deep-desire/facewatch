import axios from 'axios';

const DEFAULT_API_PORT = '8000';
const resolvedHost = typeof window !== 'undefined' ? window.location.hostname : '127.0.0.1';
const BASE_URL = process.env.REACT_APP_API_URL || `http://${resolvedHost}:${DEFAULT_API_PORT}`;

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

// ─── Camera API ───────────────────────────────────────────────────────────────
export const camerasApi = {
  list: () => api.get('/api/cameras/'),
  create: (data) => api.post('/api/cameras/', data),
  update: (id, data) => api.put(`/api/cameras/${id}`, data),
  delete: (id) => api.delete(`/api/cameras/${id}`),
  toggle: (id) => api.patch(`/api/cameras/${id}/toggle`),
  get: (id) => api.get(`/api/cameras/${id}`),
};

// ─── Employee API ─────────────────────────────────────────────────────────────
export const employeesApi = {
  list: () => api.get('/api/employees/'),
  create: (data) => api.post('/api/employees/', data),
  update: (id, data) => api.put(`/api/employees/${id}`, data),
  delete: (id) => api.delete(`/api/employees/${id}`),
  get: (id) => api.get(`/api/employees/${id}`),
  uploadPhoto: (id, formData) =>
    api.post(`/api/employees/${id}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  uploadPhotoBatch: (id, formData) =>
    api.post(`/api/employees/${id}/photos/batch`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  deletePhoto: (employeeId, photoId) =>
    api.delete(`/api/employees/${employeeId}/photos/${photoId}`),
};

// ─── Dashboard API ────────────────────────────────────────────────────────────
export const dashboardApi = {
  stats: () => api.get('/api/dashboard/stats'),
  activity: (days = 7) => api.get(`/api/dashboard/activity?days=${days}`),
  topDetected: (limit = 5) => api.get(`/api/dashboard/top-detected?limit=${limit}`),
};

// ─── Detection API ────────────────────────────────────────────────────────────
export const detectionApi = {
  logs: (cameraId, limit = 50) => {
    const params = new URLSearchParams({ limit });
    if (cameraId) params.set('camera_id', cameraId);
    return api.get(`/api/detection/logs?${params}`);
  },
};

export const WS_BASE = BASE_URL.replace(/^http/, 'ws');
export default api;
