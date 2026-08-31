from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine, SessionLocal
from app.routers import invoices, scans, dashboard, demo
from app.services.seed_data import seed_all
from app import config

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_all(db)

app = FastAPI(
    title="Pharma & Non-Pharma Shipment Validation POC",
    description="Image <-> Invoice <-> Tatmeen (dummy) reconciliation POC for Albatha/MPC. "
                "See Claude.md and project-plan.md in the repo root for full context.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(invoices.router)
app.include_router(scans.router)
app.include_router(dashboard.router)
app.include_router(demo.router)

# Serves the originally-uploaded invoice document and item/box photos back
# to the frontend so a user can click through and view exactly what they
# submitted, both right after upload and when reopening a completed
# validation later. Read-only, filename-only URLs — see config.UPLOADS_DIR.
app.mount("/api/files", StaticFiles(directory=config.UPLOADS_DIR), name="files")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "extraction_mode": config.EXTRACTION_MODE,
        "tatmeen_qty_mode": config.TATMEEN_QTY_MODE,
        "tatmeen_grace_days": config.TATMEEN_GRACE_DAYS,
    }
