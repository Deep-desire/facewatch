from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime

# ─── Camera Schemas ───────────────────────────────────────────────────────────

class CameraBase(BaseModel):
    name: str
    location: Optional[str] = None
    rtsp_url: str
    description: Optional[str] = None

class CameraCreate(CameraBase):
    pass

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    rtsp_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CameraOut(CameraBase):
    id: int
    uuid: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ─── Employee Schemas ─────────────────────────────────────────────────────────

class EmployeePhotoOut(BaseModel):
    id: int
    filename: str
    file_path: str
    angle_label: Optional[str] = None
    is_primary: bool
    created_at: datetime

    class Config:
        from_attributes = True

class EmployeeBase(BaseModel):
    first_name: str
    last_name: str
    employee_code: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeOut(EmployeeBase):
    id: int
    face_id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    photos: List[EmployeePhotoOut] = []

    class Config:
        from_attributes = True

# ─── Detection Schemas ────────────────────────────────────────────────────────

class DetectionLogOut(BaseModel):
    id: int
    camera_id: Optional[int] = None
    employee_id: Optional[int] = None
    face_id: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: datetime
    snapshot_path: Optional[str] = None

    class Config:
        from_attributes = True

# ─── Dashboard Schemas ────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_cameras: int
    active_cameras: int
    total_employees: int
    active_employees: int
    detections_today: int
    detections_this_week: int
    recent_detections: List[DetectionLogOut] = []
