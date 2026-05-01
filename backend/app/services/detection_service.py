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
        self.person_hog = None
        self._init_detector()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_detector(self):
        if not _CV2_AVAILABLE:
            logger.warning("Skipping detector initialization because OpenCV is unavailable")
            return

        try:
            self.person_hog = cv2.HOGDescriptor()
            self.person_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception as e:
            logger.warning("HOG person detector init failed: %s", e)
            self.person_hog = None

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
            locations = face_recognition.face_locations(img, model="hog")
            if not locations:
                return None
            # Prefer the largest face region when a photo has multiple people.
            locations = sorted(
                locations,
                key=lambda loc: max(0, loc[2] - loc[0]) * max(0, loc[1] - loc[3]),
                reverse=True,
            )
            encodings = face_recognition.face_encodings(
                img,
                known_face_locations=[locations[0]],
                num_jitters=2,
                model="large",
            )
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
                locations = face_recognition.face_locations(img, model="hog")
                if not locations:
                    logger.warning("No face found in %s", path)
                    continue
                locations = sorted(
                    locations,
                    key=lambda loc: max(0, loc[2] - loc[0]) * max(0, loc[1] - loc[3]),
                    reverse=True,
                )
                encs = face_recognition.face_encodings(
                    img,
                    known_face_locations=[locations[0]],
                    num_jitters=2,
                    model="large",
                )
                if encs:
                    all_encodings.append(encs[0])
            except Exception as e:
                logger.warning(f"Skipping {path}: {e}")
        if not all_encodings:
            return None
        enc_mat = np.asarray(all_encodings, dtype=np.float32)
        centroid = np.mean(enc_mat, axis=0)
        distances = np.linalg.norm(enc_mat - centroid, axis=1)
        inlier_mask = distances <= (np.mean(distances) + np.std(distances) + 1e-6)
        filtered = enc_mat[inlier_mask] if np.any(inlier_mask) else enc_mat
        avg = np.mean(filtered, axis=0)
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

    def _is_face_quality_acceptable(self, rgb_face: np.ndarray) -> bool:
        """Reject very blurry/low-detail crops that cause random identity flips."""
        if rgb_face is None or rgb_face.size == 0:
            return False
        h, w = rgb_face.shape[:2]
        if h < 34 or w < 34:
            return False
        gray = cv2.cvtColor(rgb_face, cv2.COLOR_RGB2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
        min_side = min(h, w)
        dynamic_blur_floor = 6.0 if min_side < 64 else 8.0
        return blur_score >= dynamic_blur_floor

    # ── Recognition ───────────────────────────────────────────────────────────

    def identify_face(
        self,
        frame: np.ndarray,
        bbox: Dict,
        known_encodings: List[Tuple[str, str, np.ndarray]],  # (face_id, name, encoding)
        tolerance: float = 0.74,
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
        min_side = min(w, h)
        dynamic_tolerance = tolerance
        if min_side < 90:
            dynamic_tolerance = min(0.82, tolerance + 0.06)
        elif min_side < 130:
            dynamic_tolerance = min(0.80, tolerance + 0.03)
        sorted_distances = np.sort(distances)
        second_best = float(sorted_distances[1]) if len(sorted_distances) > 1 else 1.0
        margin = second_best - best_dist

        # Accept only confident and non-ambiguous matches.
        if best_dist <= dynamic_tolerance and margin >= 0.0:
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
            entity = det.get("entity", "face")
            if entity == "person":
                known = False
                color = (255, 165, 0)
            else:
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
            if entity == "person":
                label = "Person"
            elif known:
                label += f" [{det['face_id']}]"
            conf_label = f" {det.get('confidence', 0):.1f}%"
            text_y = max(18, ry1 - 10)
            cv2.putText(out, label + conf_label, (rx1, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return out

    def detect_people(self, frame: np.ndarray) -> List[Dict]:
        """Detect person bodies using OpenCV HOG detector."""
        if not _CV2_AVAILABLE or self.person_hog is None:
            return []
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return []

        scale = 1.0
        work = frame
        if w > 960:
            scale = 960.0 / float(w)
            work = cv2.resize(frame, (960, int(h * scale)), interpolation=cv2.INTER_LINEAR)

        rects, weights = self.person_hog.detectMultiScale(
            work,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )

        people = []
        inv = 1.0 / scale
        for (x, y, pw, ph), conf in zip(rects, weights):
            if pw < 40 or ph < 80:
                continue
            people.append(
                {
                    "x": int(x * inv),
                    "y": int(y * inv),
                    "w": int(pw * inv),
                    "h": int(ph * inv),
                    "confidence": round(float(conf) * 100.0, 2),
                    "name": "Person",
                    "entity": "person",
                }
            )
        return people

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
        bboxes = [b for b in bboxes if b.get("w", 0) >= 24 and b.get("h", 0) >= 24]
        # Keep recognition bounded for predictable latency in multi-camera mode.
        if len(bboxes) > 8:
            bboxes = sorted(bboxes, key=lambda b: b["w"] * b["h"], reverse=True)[:8]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if bboxes else None
        results = []
        for bbox in bboxes:
            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            x2 = min(frame.shape[1], x + w)
            y2 = min(frame.shape[0], y + h)
            rgb_face = rgb_frame[max(0, y):y2, max(0, x):x2] if rgb_frame is not None else None
            if not self._is_face_quality_acceptable(rgb_face):
                det = {**bbox, "face_id": "unknown", "name": "Unknown", "confidence": 0.0}
                results.append(det)
                continue
            identity = self.identify_face(frame, bbox, known_encodings, rgb_frame=rgb_frame)
            det = {**bbox, **identity}
            results.append(det)

        # Prevent one employee identity being assigned to multiple people in same frame.
        best_by_face_id: Dict[str, int] = {}
        for idx, det in enumerate(results):
            face_id = det.get("face_id", "unknown")
            if not face_id or face_id == "unknown":
                continue
            if face_id not in best_by_face_id:
                best_by_face_id[face_id] = idx
                continue
            prev_idx = best_by_face_id[face_id]
            prev_conf = float(results[prev_idx].get("confidence", 0.0))
            cur_conf = float(det.get("confidence", 0.0))
            if cur_conf > prev_conf:
                results[prev_idx]["face_id"] = "unknown"
                results[prev_idx]["name"] = "Unknown"
                results[prev_idx]["confidence"] = 0.0
                best_by_face_id[face_id] = idx
            else:
                det["face_id"] = "unknown"
                det["name"] = "Unknown"
                det["confidence"] = 0.0
        annotated = self.annotate_frame(frame, results)
        return annotated, results


# Singleton
detection_service = DetectionService()
