from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.core.database import get_db
from app.models.models import Camera, Employee, DetectionLog
from app.models.schemas import DashboardStats

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total_cameras = db.query(Camera).count()
    active_cameras = db.query(Camera).filter(Camera.is_active == True).count()
    total_employees = db.query(Employee).count()
    active_employees = db.query(Employee).filter(Employee.is_active == True).count()
    detections_today = db.query(DetectionLog).filter(DetectionLog.timestamp >= today_start).count()
    detections_week = db.query(DetectionLog).filter(DetectionLog.timestamp >= week_start).count()

    recent = db.query(DetectionLog).order_by(DetectionLog.timestamp.desc()).limit(10).all()

    return DashboardStats(
        total_cameras=total_cameras,
        active_cameras=active_cameras,
        total_employees=total_employees,
        active_employees=active_employees,
        detections_today=detections_today,
        detections_this_week=detections_week,
        recent_detections=recent,
    )


@router.get("/activity")
def activity_chart(days: int = 7, db: Session = Depends(get_db)):
    """Daily detection counts for the past N days."""
    results = []
    for i in range(days - 1, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = db.query(DetectionLog).filter(
            DetectionLog.timestamp >= day_start,
            DetectionLog.timestamp < day_end
        ).count()
        results.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})
    return results


@router.get("/top-detected")
def top_detected(limit: int = 5, db: Session = Depends(get_db)):
    """Most frequently detected employees."""
    rows = (
        db.query(DetectionLog.face_id, func.count(DetectionLog.id).label("count"))
        .filter(DetectionLog.face_id != "unknown")
        .group_by(DetectionLog.face_id)
        .order_by(func.count(DetectionLog.id).desc())
        .limit(limit)
        .all()
    )
    result = []
    for face_id, count in rows:
        emp = db.query(Employee).filter(Employee.face_id == face_id).first()
        result.append({
            "face_id": face_id,
            "name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown",
            "count": count,
        })
    return result
