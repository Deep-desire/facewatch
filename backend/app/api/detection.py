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
STREAM_EXECUTOR = ThreadPoolExecutor(max_workers=2)

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
        detection_interval = 10
        pending_detection = None
        pending_scale = 1.0
        known_refresh_interval = 60
        loop = asyncio.get_running_loop()

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
                last_detections = _scale_detections(detections, pending_scale)
            except Exception as exc:
                logger.warning("Async detection failed for camera %s: %s", camera_id, exc)
            finally:
                pending_detection = None

        while True:
            await _finish_pending_detection()

            # Drain a couple queued packets first to avoid lagging behind real time.
            for _ in range(2):
                cap.grab()
            ret, frame = cap.retrieve()
            if not ret:
                ret, frame = cap.read()
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
            if analysis_w > 768:
                analysis_scale = 768 / analysis_w
                analysis_frame = cv2.resize(analysis_frame, (768, int(analysis_h * analysis_scale)))
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
            annotated = detection_service.annotate_frame(display_frame, detections) if detections else display_frame

            # Encode frame as JPEG base64
            _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 65])
            img_b64 = base64.b64encode(buffer).decode("utf-8")

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
