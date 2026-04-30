import os
import uuid
import json
import shutil
import numpy as np
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.models import Employee, EmployeePhoto
from app.models.schemas import EmployeeCreate, EmployeeUpdate
from app.services.detection_service import detection_service
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads/employees"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ANGLE_LABELS = ["front", "left", "right", "slight_left", "slight_right", "up", "down"]


def generate_face_id(db: Session) -> str:
    """Generate a unique, sequential face ID like FW-000001."""
    count = db.query(Employee).count()
    return f"FW-{(count + 1):06d}"


def get_known_encodings(db: Session):
    """Load all employee face encodings from DB for recognition."""
    employees = db.query(Employee).filter(
        Employee.is_active == True,
        Employee.face_encoding.isnot(None)
    ).all()
    result = []
    for emp in employees:
        try:
            enc_list = json.loads(emp.face_encoding)
            enc = np.asarray(enc_list, dtype=np.float32)
            if enc.shape[0] != 128:
                raise ValueError(f"encoding length must be 128, got {enc.shape[0]}")
            name = f"{emp.first_name} {emp.last_name}"
            result.append((emp.face_id, name, enc))
        except Exception as e:
            logger.warning(f"Bad encoding for {emp.face_id}: {e}")
    return result


def create_employee(db: Session, data: EmployeeCreate) -> Employee:
    face_id = generate_face_id(db)

    employee_code = (data.employee_code or "").strip() or f"EMP-{face_id}"
    email = (data.email or "").strip() or None
    phone = (data.phone or "").strip() or None
    department = (data.department or "").strip() or None
    designation = (data.designation or "").strip() or None

    emp = Employee(
        face_id=face_id,
        first_name=data.first_name,
        last_name=data.last_name,
        employee_code=employee_code,
        department=department,
        designation=designation,
        email=email,
        phone=phone,
    )
    db.add(emp)
    try:
        db.commit()
        db.refresh(emp)
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Employee create failed due to uniqueness conflict")
        raise ValueError("Employee with this email or employee code already exists") from exc
    return emp


def update_employee(db: Session, employee_id: int, data: EmployeeUpdate) -> Optional[Employee]:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        return None
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(emp, field, value)
    try:
        db.commit()
        db.refresh(emp)
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Employee update failed due to uniqueness conflict")
        raise ValueError("Employee with this email or employee code already exists") from exc
    return emp


def delete_employee(db: Session, employee_id: int) -> bool:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        return False
    # Remove photo files
    for photo in emp.photos:
        if os.path.exists(photo.file_path):
            os.remove(photo.file_path)
    db.delete(emp)
    db.commit()
    return True


def save_employee_photo(
    db: Session,
    employee_id: int,
    file_bytes: bytes,
    original_filename: str,
    angle_label: str = "front",
    is_primary: bool = False
) -> Optional[EmployeePhoto]:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        return None

    ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
    filename = f"{emp.face_id}_{uuid.uuid4().hex}{ext}"
    emp_dir = os.path.join(UPLOAD_DIR, str(employee_id))
    os.makedirs(emp_dir, exist_ok=True)
    file_path = os.path.join(emp_dir, filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # If primary, unset other primaries
    if is_primary:
        db.query(EmployeePhoto).filter(
            EmployeePhoto.employee_id == employee_id,
            EmployeePhoto.is_primary == True
        ).update({"is_primary": False})

    photo = EmployeePhoto(
        employee_id=employee_id,
        filename=filename,
        file_path=file_path,
        angle_label=angle_label,
        is_primary=is_primary,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    # Recompute face encoding from all photos
    _recompute_encoding(db, emp)

    return photo


def delete_employee_photo(db: Session, photo_id: int) -> bool:
    photo = db.query(EmployeePhoto).filter(EmployeePhoto.id == photo_id).first()
    if not photo:
        return False
    if os.path.exists(photo.file_path):
        os.remove(photo.file_path)
    employee_id = photo.employee_id
    db.delete(photo)
    db.commit()

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if emp:
        _recompute_encoding(db, emp)
    return True


def _recompute_encoding(db: Session, emp: Employee):
    """Recalculate face encoding using all employee photos."""
    db.refresh(emp)
    paths = [p.file_path for p in emp.photos if os.path.exists(p.file_path)]
    if paths:
        encoding_json = detection_service.encode_face_from_multiple(paths)
        emp.face_encoding = encoding_json
    else:
        emp.face_encoding = None
    db.commit()
