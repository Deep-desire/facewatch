from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db, SessionLocal
from app.models.models import Camera, DetectionLog
from app.services.detection_service import detection_service
from app.services.employee_service import get_known_encodings
import asyncio
import numpy as np
import json
import base64
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from app.core.optional_imports import safe_import_cv2

cv2, _CV2_AVAILABLE, _cv2_error = safe_import_cv2()

router = APIRouter()
compat_router = APIRouter()
logger = logging.getLogger(__name__)
STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=10)

if not _CV2_AVAILABLE:
    logger.warning(
        "OpenCV could not be imported in detection API (%s). WebSocket and snapshot "
        "features will return a clear error until the environment is fixed.",
        _cv2_error,
    )


# ─── WebSocket: live detection feed ───────────────────────────────────────────

@router.websocket("/ws/{camera_id}")
async def camera_ws(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    db = SessionLocal()
    try:
        if not _CV2_AVAILABLE:
            await websocket.send_json(
                {"error": "OpenCV/NumPy mismatch detected. Reinstall backend deps with numpy<2."}
            )
            await websocket.close()
            return

        camera = db.query(Camera).filter(Camera.id == camera_id, Camera.is_active == True).first()
        if not camera:
            await websocket.send_json({"error": "Camera not found or inactive"})
            await websocket.close()
            return

        known = get_known_encodings(db)
        cap = cv2.VideoCapture(camera.rtsp_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            await websocket.send_json({"error": f"Cannot open stream: {camera.rtsp_url}"})
            await websocket.close()
            return

        frame_skip = 0
        last_detections = []
        detection_interval = 2
        pending_detection = None
        pending_scale = 1.0
        known_refresh_interval = 30
        loop = asyncio.get_running_loop()
        tracks = {}
        next_track_id = 1

        def _iou(a, b):
            ax1, ay1, aw, ah = a["x"], a["y"], a["w"], a["h"]
            bx1, by1, bw, bh = b["x"], b["y"], b["w"], b["h"]
            ax2, ay2 = ax1 + aw, ay1 + ah
            bx2, by2 = bx1 + bw, by1 + bh
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
            inter = iw * ih
            if inter <= 0:
                return 0.0
            area_a = max(1, aw * ah)
            area_b = max(1, bw * bh)
            return inter / float(area_a + area_b - inter)

        def _stabilize_detections(raw_detections):
            nonlocal tracks, next_track_id, frame_skip
            if not raw_detections:
                tracks = {
                    tid: tr
                    for tid, tr in tracks.items()
                    if frame_skip - tr["last_seen"] <= 20
                }
                return []

            used_tracks = set()
            stabilized = []

            for det in raw_detections:
                best_track_id = None
                best_iou = 0.0
                for track_id, track in tracks.items():
                    if track_id in used_tracks:
                        continue
                    overlap = _iou(det, track["bbox"])
                    if overlap > best_iou:
                        best_iou = overlap
                        best_track_id = track_id

                if best_track_id is None or best_iou < 0.28:
                    best_track_id = next_track_id
                    next_track_id += 1
                    tracks[best_track_id] = {
                        "bbox": det,
                        "last_seen": frame_skip,
                        "votes": {},
                        "names": {},
                    }

                used_tracks.add(best_track_id)
                track = tracks[best_track_id]
                track["bbox"] = det
                track["last_seen"] = frame_skip

                label_key = det.get("face_id", "unknown") if det.get("face_id") else "unknown"
                weight = 2 if label_key != "unknown" else 1
                track["votes"][label_key] = track["votes"].get(label_key, 0) + weight
                if label_key != "unknown":
                    track["names"][label_key] = det.get("name", label_key)
                else:
                    # Keep "unknown" votes from dominating stable known identities forever.
                    track["votes"]["unknown"] = max(0, track["votes"]["unknown"] - 1)

                total_votes = sum(track["votes"].values())
                if total_votes > 30:
                    track["votes"] = {k: max(1, int(v * 0.6)) for k, v in track["votes"].items()}

                known_votes = {k: v for k, v in track["votes"].items() if k != "unknown"}
                unknown_votes = track["votes"].get("unknown", 0)

                stable_det = dict(det)
                immediate_known = (
                    det.get("face_id")
                    and det.get("face_id") != "unknown"
                    and float(det.get("confidence", 0.0)) >= 40.0
                )
                if known_votes:
                    best_label = max(known_votes, key=known_votes.get)
                    if immediate_known:
                        stable_det = det
                    elif known_votes[best_label] >= 2 and known_votes[best_label] + 1 >= unknown_votes:
                        if det.get("face_id") == best_label:
                            stable_det = det
                        else:
                            stable_det["face_id"] = best_label
                            stable_det["name"] = track["names"].get(best_label, best_label)
                            stable_det["confidence"] = max(0.0, det.get("confidence", 0.0) * 0.9)
                    else:
                        stable_det["face_id"] = "unknown"
                        stable_det["name"] = "Unknown"
                        stable_det["confidence"] = 0.0
                else:
                    stable_det["face_id"] = "unknown"
                    stable_det["name"] = "Unknown"
                    stable_det["confidence"] = 0.0

                stabilized.append(stable_det)

            tracks = {
                tid: tr
                for tid, tr in tracks.items()
                if frame_skip - tr["last_seen"] <= 20
            }
            return stabilized

        def _scale_detections(detections, factor):
            scaled = []
            for det in detections:
                scaled.append({
                    **det,
                    "x": int(det["x"] * factor),
                    "y": int(det["y"] * factor),
                    "w": int(det["w"] * factor),
                    "h": int(det["h"] * factor),
                })
            return scaled

        async def _finish_pending_detection():
            nonlocal pending_detection, last_detections
            if pending_detection is None or not pending_detection.done():
                return
            try:
                _annotated, detections = pending_detection.result()
                scaled = _scale_detections(detections, pending_scale)
                last_detections = _stabilize_detections(scaled)
            except Exception as exc:
                logger.warning("Async detection failed for camera %s: %s", camera_id, exc)
            finally:
                pending_detection = None

        while True:
            await _finish_pending_detection()

            def _read_frame():
                return cap.read()

            ret, frame = await loop.run_in_executor(STREAM_EXECUTOR, _read_frame)
            if not ret:
                await websocket.send_json({"error": "Stream ended"})
                break

            frame_skip += 1
            if frame_skip % known_refresh_interval == 0:
                # Pick up newly registered employees without restarting streams.
                known = get_known_encodings(db)

            # Keep the display frame larger, but run face detection on a smaller copy.
            display_frame = frame
            display_h, display_w = display_frame.shape[:2]
            if display_w > 1280:
                display_scale = 1280 / display_w
                display_frame = cv2.resize(display_frame, (1280, int(display_h * display_scale)))
            else:
                display_scale = 1.0

            analysis_frame = display_frame
            analysis_h, analysis_w = analysis_frame.shape[:2]
            if analysis_w > 1024:
                analysis_scale = 1024 / analysis_w
                analysis_frame = cv2.resize(analysis_frame, (1024, int(analysis_h * analysis_scale)))
            else:
                analysis_scale = 1.0

            if frame_skip % detection_interval == 0 and pending_detection is None:
                pending_scale = analysis_frame.shape[1] and (display_frame.shape[1] / analysis_frame.shape[1]) or 1.0
                pending_detection = loop.run_in_executor(
                    STREAM_EXECUTOR,
                    detection_service.process_frame,
                    analysis_frame.copy(),
                    known,
                )

            detections = last_detections
            
            def _process_display():
                ann = detection_service.annotate_frame(display_frame, detections) if detections else display_frame
                _, buf = cv2.imencode(".jpg", ann, [cv2.IMWRITE_JPEG_QUALITY, 55])
                b64 = base64.b64encode(buf).decode("utf-8")
                return [], b64
                
            people, img_b64 = await loop.run_in_executor(STREAM_EXECUTOR, _process_display)

            # Only persist detections on detection frames to avoid duplicate log spam.
            if frame_skip % detection_interval == 0 and detections:
                for det in detections:
                    if det.get("face_id") and det["face_id"] != "unknown":
                        log = DetectionLog(
                            camera_id=camera_id,
                            face_id=det["face_id"],
                            confidence=det.get("confidence"),
                            bbox_x=det["x"], bbox_y=det["y"],
                            bbox_w=det["w"], bbox_h=det["h"],
                        )
                        db.add(log)
                db.commit()

            payload = {
                "frame": img_b64,
                "detections": detections,
                "timestamp": datetime.utcnow().isoformat(),
                "camera_name": camera.name,
                "known_faces_loaded": len(known),
                "people_count": len(detections),
            }

            try:
                await websocket.send_json(payload)
            except Exception:
                break

            await asyncio.sleep(0.001)  # keep the loop responsive without adding visible lag

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for camera {camera_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        cap.release()
        db.close()


@compat_router.post("/webrtc/{camera_ref}/offer")
def webrtc_offer_compat(
    camera_ref: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
):
    """
    Backward-compatible endpoint for legacy clients that still POST WebRTC offers.
    This service uses WebSocket JPEG streaming, so we return upgrade instructions.
    """
    camera_id = None
    if camera_ref.isdigit():
        camera_id = int(camera_ref)
    elif camera_ref.lower().startswith("cam") and camera_ref[3:].isdigit():
        camera_id = int(camera_ref[3:])

    if not camera_id:
        raise HTTPException(status_code=400, detail="Invalid camera reference. Use cam1/cam2... or numeric id.")

    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not camera.is_active:
        raise HTTPException(status_code=409, detail="Camera is inactive")

    return {
        "status": "migrated",
        "message": "WebRTC offer endpoint is deprecated. Use WebSocket stream endpoint.",
        "camera_id": camera_id,
        "ws_path": f"/api/detection/ws/{camera_id}",
        "received_offer": bool(payload.get("sdp") or payload.get("offer")),
    }


# ─── Snapshot endpoint ────────────────────────────────────────────────────────

@router.get("/snapshot/{camera_id}")
def get_snapshot(camera_id: int, db: Session = Depends(get_db)):
    if not _CV2_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="OpenCV is unavailable due to a NumPy compatibility issue. Reinstall backend deps with numpy<2.",
        )
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    path = detection_service.capture_snapshot(camera.rtsp_url)
    if not path:
        raise HTTPException(status_code=503, detail="Could not capture snapshot from stream")

    def iterfile():
        with open(path, "rb") as f:
            yield from f

    return StreamingResponse(iterfile(), media_type="image/jpeg")


# ─── Recent detections ────────────────────────────────────────────────────────

@router.get("/logs")
def detection_logs(
    camera_id: int = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(DetectionLog)
    if camera_id:
        q = q.filter(DetectionLog.camera_id == camera_id)
    logs = q.order_by(DetectionLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "camera_id": l.camera_id,
            "face_id": l.face_id,
            "confidence": l.confidence,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
        }
        for l in logs
    ]
