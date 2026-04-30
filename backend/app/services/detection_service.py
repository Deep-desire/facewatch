"""
FaceWatch Detection Service
Uses YOLOv8 for face detection + face_recognition for identification.
Falls back to OpenCV Haar cascade if YOLO/face_recognition not available.
"""

import numpy as np
import json
import os
import uuid
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from app.core.optional_imports import safe_import_cv2

logger = logging.getLogger(__name__)

cv2, _CV2_AVAILABLE, _cv2_error = safe_import_cv2()
if not _CV2_AVAILABLE:
    logger.warning(
        "OpenCV could not be imported (%s). Face detection will be disabled until "
        "NumPy/OpenCV are installed in a compatible environment.",
        _cv2_error,
    )

# ─── Try importing optional heavy deps ────────────────────────────────────────
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    logger.warning("ultralytics not installed — falling back to Haar cascade")

try:
    import face_recognition
    _FACE_REC_AVAILABLE = True
except ImportError:
    _FACE_REC_AVAILABLE = False
    logger.warning("face_recognition not installed — encoding disabled")

# ─── DetectionService ─────────────────────────────────────────────────────────

class DetectionService:
    """Core face detection + recognition engine."""

    def __init__(self):
        self.yolo_model = None
        self.haar_cascade = None
        self._init_detector()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_detector(self):
        if not _CV2_AVAILABLE:
            logger.warning("Skipping detector initialization because OpenCV is unavailable")
            return

        if _YOLO_AVAILABLE:
            try:
                # Uses the nano face-detection model; downloads automatically
                self.yolo_model = YOLO("yolov8n-face.pt")
                logger.info("YOLOv8 face model loaded")
                return
            except Exception as e:
                logger.warning(f"YOLOv8 load failed ({e}); falling back to Haar")

        # Haar cascade fallback
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.haar_cascade = cv2.CascadeClassifier(cascade_path)
        logger.info("Haar cascade detector loaded")

    # ── Face encoding helpers ─────────────────────────────────────────────────

    def encode_face(self, image_path: str) -> Optional[str]:
        """Return a JSON-serialised 128-d face encoding, or None."""
        if not _FACE_REC_AVAILABLE:
            logger.warning("face_recognition unavailable — skipping encoding")
            return None
        try:
            img = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(img)
            if encodings:
                return json.dumps(encodings[0].tolist())
        except Exception as e:
            logger.error(f"encode_face error: {e}")
        return None

    def encode_face_from_multiple(self, image_paths: List[str]) -> Optional[str]:
        """Average encodings across multiple images for robustness."""
        if not _FACE_REC_AVAILABLE:
            return None
        all_encodings = []
        for path in image_paths:
            try:
                img = face_recognition.load_image_file(path)
                encs = face_recognition.face_encodings(img)
                if encs:
                    all_encodings.append(encs[0])
            except Exception as e:
                logger.warning(f"Skipping {path}: {e}")
        if not all_encodings:
            return None
        avg = np.mean(all_encodings, axis=0)
        return json.dumps(avg.tolist())

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect_faces_yolo(self, frame: np.ndarray) -> List[Dict]:
        """Detect faces using YOLOv8. Returns list of bbox dicts."""
        results = []
        if self.yolo_model is None:
            return results
        try:
            preds = self.yolo_model(frame, conf=0.4, verbose=False)
            for pred in preds:
                for box in pred.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    results.append({
                        "x": x1, "y": y1,
                        "w": x2 - x1, "h": y2 - y1,
                        "confidence": conf
                    })
        except Exception as e:
            logger.error(f"YOLO detection error: {e}")
        return results

    def detect_faces_haar(self, frame: np.ndarray) -> List[Dict]:
        """Fallback Haar cascade detection."""
        results = []
        if not _CV2_AVAILABLE or self.haar_cascade is None:
            return results
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.haar_cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
        for (x, y, w, h) in faces:
            results.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "confidence": 0.85})
        return results

    def detect_faces(self, frame: np.ndarray) -> List[Dict]:
        if not _CV2_AVAILABLE:
            return []
        return self.detect_faces_yolo(frame) if self.yolo_model else self.detect_faces_haar(frame)

    # ── Recognition ───────────────────────────────────────────────────────────

    def identify_face(
        self,
        frame: np.ndarray,
        bbox: Dict,
        known_encodings: List[Tuple[str, str, np.ndarray]],  # (face_id, name, encoding)
        tolerance: float = 0.68,
        rgb_frame: Optional[np.ndarray] = None,
    ) -> Dict:
        """Match a detected face crop against known encodings."""
        if not _FACE_REC_AVAILABLE or not known_encodings:
            return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}
        if not _CV2_AVAILABLE:
            return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}

        x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
        frame_h, frame_w = frame.shape[:2]

        # Prefer encoding from the full frame and explicit detector bbox location.
        # This avoids running an additional detector inside the crop, which is
        # brittle for small/angled live-feed faces and often causes "Unknown".
        if rgb_frame is None:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        pad_x = int(max(6, w * 0.10))
        pad_y = int(max(6, h * 0.12))
        left = max(0, x - pad_x)
        top = max(0, y - pad_y)
        right = min(frame_w - 1, x + w + pad_x)
        bottom = min(frame_h - 1, y + h + pad_y)
        if right <= left or bottom <= top:
            return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}

        face_location = [(top, right, bottom, left)]
        try:
            enc_list = face_recognition.face_encodings(
                rgb_frame,
                known_face_locations=face_location,
                num_jitters=1,
                model="small",
            )
            if not enc_list:
                # Fallback path for detector/location mismatch edge cases.
                crop = frame[top:bottom, left:right]
                if crop.size == 0:
                    return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}
                rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                if rgb_crop.shape[0] < 120 or rgb_crop.shape[1] < 120:
                    rgb_crop = cv2.resize(rgb_crop, (160, 160), interpolation=cv2.INTER_LINEAR)
                enc_list = face_recognition.face_encodings(rgb_crop)
        except Exception:
            return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}

        if not enc_list:
            return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}

        query_enc = enc_list[0]
        ids, names, encs = zip(*known_encodings)
        distances = face_recognition.face_distance(list(encs), query_enc)
        best_idx = int(np.argmin(distances))
        best_dist = float(distances[best_idx])

        if best_dist <= tolerance:
            confidence = round((1 - best_dist) * 100, 2)
            return {"face_id": ids[best_idx], "name": names[best_idx], "confidence": confidence}

        return {"face_id": "unknown", "name": "Unknown", "confidence": 0.0}

    # ── Frame annotation ──────────────────────────────────────────────────────

    def annotate_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Draw bounding boxes + labels on a frame copy."""
        if not _CV2_AVAILABLE:
            return frame
        out = frame.copy()
        frame_h, frame_w = out.shape[:2]
        for det in detections:
            x, y, w, h = det["x"], det["y"], det["w"], det["h"]
            known = det.get("face_id", "unknown") != "unknown"
            color = (0, 255, 0) if known else (0, 0, 255)

            # Slightly larger box for better operator visibility.
            pad_x = int(max(4, w * 0.1))
            pad_y = int(max(4, h * 0.1))
            rx1 = max(0, x - pad_x)
            ry1 = max(0, y - pad_y)
            rx2 = min(frame_w - 1, x + w + pad_x)
            ry2 = min(frame_h - 1, y + h + pad_y)
            cv2.rectangle(out, (rx1, ry1), (rx2, ry2), color, 2)

            label = det.get("name", "Unknown")
            if known:
                label += f" [{det['face_id']}]"
            conf_label = f" {det.get('confidence', 0):.1f}%"
            text_y = max(18, ry1 - 10)
            cv2.putText(out, label + conf_label, (rx1, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return out

    # ── RTSP stream snapshot ───────────────────────────────────────────────────

    def capture_snapshot(self, rtsp_url: str, output_dir: str = "uploads/faces") -> Optional[str]:
        """Grab one frame from an RTSP stream and save it."""
        if not _CV2_AVAILABLE:
            logger.warning("Snapshot capture requested but OpenCV is unavailable")
            return None
        cap = cv2.VideoCapture(rtsp_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            logger.warning(f"Cannot open stream: {rtsp_url}")
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        filename = f"snapshot_{uuid.uuid4().hex}.jpg"
        path = os.path.join(output_dir, filename)
        cv2.imwrite(path, frame)
        return path

    # ── Process single frame ──────────────────────────────────────────────────

    def process_frame(
        self,
        frame: np.ndarray,
        known_encodings: List[Tuple[str, str, np.ndarray]]
    ) -> Tuple[np.ndarray, List[Dict]]:
        """Detect + identify faces. Returns (annotated_frame, detection_results)."""
        if not _CV2_AVAILABLE:
            return frame, []
        bboxes = self.detect_faces(frame)
        # Keep recognition bounded for predictable latency in multi-camera mode.
        if len(bboxes) > 3:
            bboxes = sorted(bboxes, key=lambda b: b["w"] * b["h"], reverse=True)[:3]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if bboxes else None
        results = []
        for bbox in bboxes:
            identity = self.identify_face(frame, bbox, known_encodings, rgb_frame=rgb_frame)
            det = {**bbox, **identity}
            results.append(det)
        annotated = self.annotate_frame(frame, results)
        return annotated, results


# Singleton
detection_service = DetectionService()
