"""
backend/config.py
Configuration and settings for VanDrishti backend API.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = REPO_ROOT / "data"
RESULTS_GIS_DIR = REPO_ROOT / "results" / "gis"
FRONTEND_DATA_DIR = REPO_ROOT / "frontend" / "public" / "data"
UPLOADS_DIR = DATA_DIR / "uploads"

# Ensure essential directories exist
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_GIS_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables (.env in REPO_ROOT or current dir)
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# Database
DB_PATH = BACKEND_DIR / "vandrishti.db"

# API Settings
API_TITLE = "VanDrishti Forest Intelligence API"
API_DESCRIPTION = (
    "AI-powered geospatial analytics and field verification API for forest tree detection, "
    "verification-priority scoring, terrain-aware Dijkstra/Held-Karp TSP routing, "
    "canopy degradation, and NASA FIRMS fire monitoring."
)
API_VERSION = "1.0.0"

# CORS origins
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
