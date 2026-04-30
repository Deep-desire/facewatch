from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.models import Employee, EmployeePhoto
from app.models.schemas import EmployeeCreate, EmployeeUpdate, EmployeeOut, EmployeePhotoOut
from app.services import employee_service

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.get("/", response_model=List[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).order_by(Employee.created_at.desc()).all()


@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    email = (data.email or "").strip() or None
    employee_code = (data.employee_code or "").strip() or None

    if email:
        existing = db.query(Employee).filter(Employee.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this email already exists")
    if employee_code:
        existing = db.query(Employee).filter(Employee.employee_code == employee_code).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this employee code already exists")

    try:
        emp = employee_service.create_employee(db, data)
        return emp
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.put("/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, data: EmployeeUpdate, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    updates = data.model_dump(exclude_unset=True)
    email = (updates.get("email") or "").strip() or None
    employee_code = (updates.get("employee_code") or "").strip() or None

    if email:
        existing = db.query(Employee).filter(Employee.email == email, Employee.id != employee_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this email already exists")
    if employee_code:
        existing = db.query(Employee).filter(Employee.employee_code == employee_code, Employee.id != employee_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this employee code already exists")

    try:
        updated = employee_service.update_employee(db, employee_id, data)
        return updated
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    success = employee_service.delete_employee(db, employee_id)
    if not success:
        raise HTTPException(status_code=404, detail="Employee not found")


# ─── Photo endpoints ──────────────────────────────────────────────────────────

@router.post("/{employee_id}/photos", response_model=EmployeePhotoOut, status_code=201)
async def upload_photo(
    employee_id: int,
    file: UploadFile = File(...),
    angle_label: str = Form("front"),
    is_primary: bool = Form(False),
    db: Session = Depends(get_db)
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {ALLOWED_TYPES}")

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    photo = employee_service.save_employee_photo(
        db, employee_id, contents, file.filename or "photo.jpg",
        angle_label=angle_label, is_primary=is_primary
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Employee not found")
    return photo


@router.post("/{employee_id}/photos/batch", status_code=201)
async def upload_multiple_photos(
    employee_id: int,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """Upload multiple face images at once (different angles)."""
    angle_labels = ["front", "left", "right", "slight_left", "slight_right", "up", "down"]
    results = []
    for idx, file in enumerate(files):
        if file.content_type not in ALLOWED_TYPES:
            continue
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            continue
        angle = angle_labels[idx % len(angle_labels)]
        photo = employee_service.save_employee_photo(
            db, employee_id, contents, file.filename or f"photo_{idx}.jpg",
            angle_label=angle, is_primary=(idx == 0)
        )
        if photo:
            results.append(photo)
    return {"uploaded": len(results), "photos": [p.id for p in results]}


@router.delete("/{employee_id}/photos/{photo_id}", status_code=204)
def delete_photo(employee_id: int, photo_id: int, db: Session = Depends(get_db)):
    success = employee_service.delete_employee_photo(db, photo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Photo not found")
