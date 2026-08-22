"""
backend/services/fire_service.py
Service wrapping NASA FIRMS active fire detection queries,
caching results in SQLite, and providing GeoJSON responses.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from backend.config import FRONTEND_DATA_DIR, REPO_ROOT, RESULTS_GIS_DIR
from backend.database import get_db_connection

# Add scripts directory to sys.path
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def query_firms_hotspots(preset: str = "osbs_live", day_range: int = 5) -> Dict[str, Any]:
    """
    Executes or loads NASA FIRMS fire hotspots.
    Checks environment for FIRMS_MAP_KEY and delegates to fire_detection_firms.py.
    """
    try:
        import fire_detection_firms
        
        # Override preset parameter if needed
        fire_detection_firms.ACTIVE_PRESET = preset
        if preset in fire_detection_firms.PRESETS:
            fire_detection_firms.PRESETS[preset]["day_range"] = day_range
            
        result = fire_detection_firms.run_fire_detection(preset_key=preset)
        
        # Read the resulting GeoJSON
        geojson_path = Path(result["geojson"])
        if geojson_path.exists():
            with open(geojson_path, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)
        else:
            geojson_data = {"type": "FeatureCollection", "features": []}
            
        # Cache in database
        now = datetime.utcnow().isoformat()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO fire_cache (preset, hotspot_count, geojson_path, queried_at, data_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (preset, result.get("hotspot_count", 0), str(geojson_path), now, json.dumps(geojson_data))
            )
            conn.commit()
            
        return {
            "preset": preset,
            "aoi_name": result.get("aoi_name", preset),
            "hotspot_count": result.get("hotspot_count", 0),
            "source": "VIIRS_SNPP_NRT",
            "geojson": geojson_data,
        }
    except Exception as e:
        # Fallback to existing static GeoJSON in frontend/public/data
        fallback_file = FRONTEND_DATA_DIR / f"fire_hotspots_{preset}.geojson"
        if not fallback_file.exists():
            fallback_file = FRONTEND_DATA_DIR / "fire_hotspots_osbs_live.geojson"
            
        if fallback_file.exists():
            with open(fallback_file, "r", encoding="utf-8") as f:
                fallback_data = json.load(f)
            return {
                "preset": preset,
                "aoi_name": preset,
                "hotspot_count": len(fallback_data.get("features", [])),
                "source": "VIIRS_SNPP_NRT (Cached Fallback)",
                "geojson": fallback_data,
                "warning": f"Live query failed ({str(e)}), served cached data.",
            }
        raise RuntimeError(f"Failed to fetch fire hotspots: {e}")
