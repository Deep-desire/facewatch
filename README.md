# FaceWatch — Production CCTV Face Detection System

A full-stack production system for CCTV camera management with real-time YOLO-powered face detection and employee recognition.

---

## Architecture

```
facewatch/
├── backend/               # Python FastAPI
│   ├── main.py            # App entry point
│   ├── app/
│   │   ├── api/           # REST + WebSocket endpoints
│   │   │   ├── cameras.py
│   │   │   ├── employees.py
│   │   │   ├── detection.py   # WebSocket live stream
│   │   │   └── dashboard.py
│   │   ├── models/
│   │   │   ├── models.py      # SQLAlchemy ORM
│   │   │   └── schemas.py     # Pydantic schemas
│   │   ├── services/
│   │   │   ├── detection_service.py  # YOLOv8 + face_recognition
│   │   │   └── employee_service.py   # Face ID management
│   │   └── core/
│   │       └── database.py    # SQLite/PostgreSQL
│   └── Dockerfile
│
├── frontend/              # React.js SPA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.js     # Stats + charts
│   │   │   ├── Cameras.js       # Camera CRUD
│   │   │   ├── Employees.js     # Employee + photo management
│   │   │   ├── LiveFeed.js      # WebSocket live streams
│   │   │   └── DetectionLogs.js # Detection history
│   │   ├── api/index.js         # Axios API client
│   │   └── App.js               # Router + layout
│   └── Dockerfile
│
└── docker-compose.yml
```

---

## Features

### 🎥 Camera Management
- Add cameras with RTSP streaming URLs
- Update / delete cameras
- Enable / disable cameras
- Duplicate RTSP URL prevention

### 👤 Employee Management
- Unique auto-generated **Face ID** (format: `FW-000001`)
- Face IDs are permanent — re-detection never creates a duplicate
- Upload **multiple face photos** from different angles (front, left, right, etc.)
- Face encodings are averaged across all photos for higher accuracy
- Add / update / delete employees
- Photo management with angle labels

### 📡 Live Feed (WebSocket)
- Real-time RTSP stream ingestion via OpenCV
- **YOLOv8** face detection (falls back to Haar cascade if unavailable)
- **face_recognition** library for 128-d face encoding & matching
- Detected employees highlighted with **name + Face ID**
- Unknown faces flagged in red
- Confidence scores shown
- Detection events logged to database

### 📊 Dashboard
- Live stats: cameras, employees, detections
- 7-day activity chart
- Top detected employees
- Recent detection log

### 📝 Detection Logs
- Full history of all face detection events
- Filter by camera or known/unknown
- Confidence score visualization

---

## Quick Start

### Option A: Docker Compose (Recommended)

```bash
git clone <repo>
cd facewatch
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option B: Local Development

**Backend:**
```bash
cd backend

# Install system deps (Ubuntu/Debian)
sudo apt-get install build-essential cmake libopenblas-dev libboost-python-dev ffmpeg


python -m venv .venv 
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

---

## YOLO Face Detection Setup

The system uses `ultralytics` YOLOv8 with the `yolov8n-face.pt` model.

On first run, the model downloads automatically (~6MB). If YOLO is unavailable, it falls back to OpenCV's Haar cascade.

For GPU acceleration:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install ultralytics
```

---

## API Reference

Full interactive docs at: `http://localhost:8000/docs`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras/` | List cameras |
| POST | `/api/cameras/` | Add camera |
| PUT | `/api/cameras/{id}` | Update camera |
| DELETE | `/api/cameras/{id}` | Delete camera |
| GET | `/api/employees/` | List employees |
| POST | `/api/employees/` | Create employee |
| POST | `/api/employees/{id}/photos` | Upload single photo |
| POST | `/api/employees/{id}/photos/batch` | Upload multiple photos |
| DELETE | `/api/employees/{id}/photos/{photo_id}` | Delete photo |
| WS | `/api/detection/ws/{camera_id}` | Live detection WebSocket |
| GET | `/api/detection/logs` | Detection history |
| GET | `/api/dashboard/stats` | Dashboard stats |

---

## Face ID System

- Every employee gets a unique `FW-XXXXXX` Face ID on creation
- Face encodings are computed from all uploaded photos (averaged)
- Recognition uses cosine similarity with 0.5 tolerance
- Re-detected employees are matched to existing IDs — **no duplicate IDs ever created**
- Face encodings automatically recalculate when photos are added or removed

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/facewatch.db` | Database connection string |
| `REACT_APP_API_URL` | `http://localhost:8000` | Backend API URL |

For PostgreSQL:
```
DATABASE_URL=postgresql://user:pass@localhost/facewatch
```
