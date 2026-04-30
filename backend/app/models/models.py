from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

def gen_uuid():
    return str(uuid.uuid4())

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, default=gen_uuid, unique=True, index=True)
    name = Column(String(100), nullable=False)
    location = Column(String(200))
    rtsp_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    detections = relationship("DetectionLog", back_populates="camera")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    face_id = Column(String(50), unique=True, index=True, nullable=False)  # Unique face ID
    employee_code = Column(String(50), unique=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    department = Column(String(100))
    designation = Column(String(100))
    email = Column(String(200), unique=True)
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    face_encoding = Column(Text)  # JSON-serialized face encoding
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    photos = relationship("EmployeePhoto", back_populates="employee", cascade="all, delete-orphan")
    detections = relationship("DetectionLog", back_populates="employee")


class EmployeePhoto(Base):
    __tablename__ = "employee_photos"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    filename = Column(String(300), nullable=False)
    file_path = Column(String(500), nullable=False)
    angle_label = Column(String(50))  # front, left, right, up, down
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employee = relationship("Employee", back_populates="photos")


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    face_id = Column(String(50))  # employee face_id or "unknown"
    confidence = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    snapshot_path = Column(String(500))
    bbox_x = Column(Integer)
    bbox_y = Column(Integer)
    bbox_w = Column(Integer)
    bbox_h = Column(Integer)

    camera = relationship("Camera", back_populates="detections")
    employee = relationship("Employee", back_populates="detections")
