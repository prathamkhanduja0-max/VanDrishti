"""
backend/routers/assessment.py
Router for inspecting raster georeferencing, dimensions, CRS, and module capability levels.
"""

import sys
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Query
from backend.config import REPO_ROOT

SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

router = APIRouter(prefix="/api/assessment", tags=["Capability Assessment"])


@router.get("/inspect", summary="Dynamically assess capability and spatial health of a configured site")
async def inspect_site_capability(site: str = Query("osbs", description="'osbs' or 'teak'")):
    config_file = "config_teak.yaml" if "teak" in site.lower() else "config.yaml"
    config_path = REPO_ROOT / config_file
    
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Config file '{config_file}' not found")
        
    try:
        import config_loader
        cfg = config_loader.load(config_path)
        rasters = config_loader.inspect_rasters(cfg)
        caps = config_loader.assess(rasters)
        
        return {
            "site_name": cfg.get("site", {}).get("name", site),
            "description": cfg.get("site", {}).get("description", ""),
            "config_file": config_file,
            "rasters": rasters,
            "capabilities": caps,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assessment failed: {str(e)}")
