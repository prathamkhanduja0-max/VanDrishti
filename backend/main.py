"""
backend/main.py
Main entry point for VanDrishti FastAPI Backend Server.
"""

import os
import sys
from pathlib import Path

# Configure safe local HuggingFace cache directory before any ML imports
_cache = Path(__file__).resolve().parent.parent / ".hf_cache"
_cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_cache)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(_cache / "hub")

import matplotlib
matplotlib.use("Agg")

# Add repo root and backend dir to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
for p in [str(REPO_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import API_DESCRIPTION, API_TITLE, API_VERSION, CORS_ORIGINS
from backend.database import init_db
from backend.routers import assessment, diversion, fire, gis, process, upload

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all during local development / testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(upload.router)
app.include_router(process.router)
app.include_router(gis.router)
app.include_router(fire.router)
app.include_router(assessment.router)
app.include_router(diversion.router)


@app.get("/", tags=["Health"])
@app.get("/api/health", tags=["Health"])
async def health_check():
    """Returns system status, active modules, and API metadata."""
    return {
        "status": "online",
        "service": "VanDrishti Forest Intelligence API",
        "version": API_VERSION,
        "docs_url": "/docs",
        "endpoints": {
            "upload": "/api/upload",
            "process": "/api/process",
            "status": "/api/status/{job_id}",
            "trees": "/api/trees",
            "route": "/api/route",
            "fire_hotspots": "/api/fire-hotspots",
            "degradation": "/api/degradation",
            "health_grid": "/api/health-grid",
            "assessment": "/api/assessment",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
