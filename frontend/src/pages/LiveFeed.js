import React, { useState, useEffect, useRef, useCallback } from 'react';
import { camerasApi } from '../api';
import { WS_BASE } from '../api';

function LiveCameraFeed({ camera }) {
  const imgRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const manualDisconnectRef = useRef(false);
  const detectionsSigRef = useRef('');
  const latestFrameRef = useRef('');
  const frameRafRef = useRef(null);
  const [detections, setDetections] = useState([]);
  const [status, setStatus] = useState('connecting');
  const [fps, setFps] = useState(0);
  const frameCountRef = useRef(0);
  const fpsIntervalRef = useRef(null);

  const flushLatestFrame = useCallback(() => {
    frameRafRef.current = null;
    if (imgRef.current && latestFrameRef.current) {
      imgRef.current.src = `data:image/jpeg;base64,${latestFrameRef.current}`;
      frameCountRef.current += 1;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) return;
    manualDisconnectRef.current = false;
    setStatus('connecting');
    const ws = new WebSocket(`${WS_BASE}/api/detection/ws/${camera.id}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('live');
      frameCountRef.current = 0;
      fpsIntervalRef.current = setInterval(() => {
        setFps(frameCountRef.current);
        frameCountRef.current = 0;
      }, 1000);
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.error) { setStatus('error'); return; }
      if (data.frame) {
        latestFrameRef.current = data.frame;
        if (!frameRafRef.current) {
          frameRafRef.current = requestAnimationFrame(flushLatestFrame);
        }
      }
      const nextDetections = data.detections || [];
      const nextSig = JSON.stringify(nextDetections);
      if (nextSig !== detectionsSigRef.current) {
        detectionsSigRef.current = nextSig;
        setDetections(nextDetections);
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      clearInterval(fpsIntervalRef.current);
      wsRef.current = null;
      if (!manualDisconnectRef.current && camera.is_active) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, 2000);
      }
    };

    ws.onerror = () => setStatus('error');
  }, [camera.id, camera.is_active, flushLatestFrame]);

  const disconnect = useCallback(() => {
    manualDisconnectRef.current = true;
    clearTimeout(reconnectTimerRef.current);
    if (frameRafRef.current) cancelAnimationFrame(frameRafRef.current);
    frameRafRef.current = null;
    wsRef.current?.close();
    clearInterval(fpsIntervalRef.current);
    setStatus('disconnected');
  }, []);

  useEffect(() => {
    connect();
    return () => {
      manualDisconnectRef.current = true;
      clearTimeout(reconnectTimerRef.current);
      disconnect();
    };
  }, [connect, disconnect]);

  const statusColor = { live: 'var(--success)', connecting: 'var(--warning)', disconnected: 'var(--text-muted)', error: 'var(--danger)' }[status];

  return (
    <div className="live-camera-card">
      <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border)' }}>
        <div>
          <span style={{ fontSize: 13, fontWeight: 700 }}>{camera.name}</span>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginLeft: 8 }}>{camera.location || ''}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: statusColor, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            ● {status}
          </span>
          {status === 'live' && <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>{fps} FPS</span>}
          {status === 'live' || status === 'connecting'
            ? <button onClick={disconnect} style={{ background: 'none', border: '1px solid var(--border)', color: 'var(--text-secondary)', borderRadius: 4, padding: '2px 8px', fontSize: 10, cursor: 'pointer' }}>Stop</button>
            : <button onClick={connect} style={{ background: 'none', border: '1px solid var(--accent)', color: 'var(--accent)', borderRadius: 4, padding: '2px 8px', fontSize: 10, cursor: 'pointer' }}>Connect</button>
          }
        </div>
      </div>

      <div className="live-camera-media">
        {status === 'connecting' && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10, color: 'var(--text-muted)', zIndex: 1 }}>
            <div className="spinner" />
            <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>Connecting to stream...</span>
          </div>
        )}
        {(status === 'disconnected' || status === 'error') && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10, color: 'var(--text-muted)', zIndex: 1 }}>
            <span style={{ fontSize: 28 }}>⬡</span>
            <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>{status === 'error' ? 'Stream error' : 'Disconnected'}</span>
          </div>
        )}
        <img
          ref={imgRef}
          alt="live"
          className="live-feed-canvas"
          style={{ display: status === 'live' ? 'block' : 'none' }}
        />
      </div>

      <div className="live-detections">
        {detections.length === 0
          ? <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>No faces detected</span>
          : detections.map((d, i) => (
            <div key={i} className={`detection-chip ${d.face_id !== 'unknown' ? 'known' : 'unknown'}`}>
              {d.face_id !== 'unknown' ? `✓ ${d.name} [${d.face_id}]` : '? Unknown'}
              {d.confidence > 0 && <span style={{ opacity: 0.7 }}>{d.confidence.toFixed(0)}%</span>}
            </div>
          ))
        }
      </div>
    </div>
  );
}

export default function LiveFeed() {
  const [cameras, setCameras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState([]);
  const [focusCameraId, setFocusCameraId] = useState(null);

  const loadCameras = useCallback(async () => {
    try {
      const r = await camerasApi.list();
      const all = r.data;
      setCameras(all);
      setSelected(prev => {
        const activeIds = all.filter(c => c.is_active).map(c => c.id);
        const next = new Set(prev.filter(id => all.some(c => c.id === id && c.is_active)));
        activeIds.forEach(id => next.add(id));
        return Array.from(next);
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCameras();
    const interval = setInterval(loadCameras, 5000);
    return () => clearInterval(interval);
  }, [loadCameras]);

  const toggleCamera = (id) => {
    const cam = cameras.find(c => c.id === id);
    if (!cam?.is_active) return;
    setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
  };

  const focusedCamera = focusCameraId ? cameras.find(c => c.id === focusCameraId && c.is_active) : null;

  if (loading) return <div className="loading"><div className="spinner" /> Loading...</div>;

  const activeCameras = cameras.filter(c => c.is_active);
  const visible = activeCameras.filter(c => selected.includes(c.id));

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Live Feed</h1>
          <p className="page-subtitle">Real-time YOLO face detection · {visible.length} streams active</p>
        </div>
      </div>

      {activeCameras.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">▶</div>
          <div className="empty-text">No active cameras</div>
          <div className="empty-sub">Enable cameras in the Cameras section to view live feeds</div>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
            {activeCameras.map(c => (
              <button
                key={c.id}
                onClick={() => toggleCamera(c.id)}
                className={`btn btn-sm ${selected.includes(c.id) ? 'btn-primary' : 'btn-ghost'}`}
              >
                {c.name}
              </button>
            ))}
            {focusedCamera && (
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => setFocusCameraId(null)}
              >
                Exit Fullscreen ({focusedCamera.name})
              </button>
            )}
          </div>

          {focusedCamera ? (
            <div className="live-grid live-grid-focus">
              <div onDoubleClick={() => setFocusCameraId(null)}>
                <LiveCameraFeed camera={focusedCamera} />
              </div>
            </div>
          ) : (
            <div className="live-grid">
              {visible.map(cam => (
                <div
                  key={cam.id}
                  className="live-camera-clickable"
                  onClick={() => setFocusCameraId(cam.id)}
                  title={`Click to fullscreen ${cam.name}`}
                >
                  <LiveCameraFeed camera={cam} />
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
