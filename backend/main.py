from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import cameras, employees, detection, dashboard
from app.core.database import engine, Base
import os

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="FaceWatch CCTV System",
    description="Production CCTV Face Detection & Employee Management System",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads/employees", exist_ok=True)
os.makedirs("uploads/faces", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
app.include_router(employees.router, prefix="/api/employees", tags=["Employees"])
app.include_router(detection.router, prefix="/api/detection", tags=["Detection"])
app.include_router(detection.compat_router, prefix="/api", tags=["Detection Compatibility"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

@app.get("/")
def root():
    return {"message": "FaceWatch CCTV System API", "version": "1.0.0", "status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
