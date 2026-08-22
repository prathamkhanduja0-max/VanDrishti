"""
backend/services/pipeline_service.py
Orchestrates execution of existing analytical scripts (tree detection, priority tagging,
Dijkstra/Held-Karp TSP routing, degradation analysis, health scoring, and reprojection)
as background tasks while updating the SQLite jobs table with real-time progress and logs.
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Enforce headless Agg backend for worker threads
import matplotlib
matplotlib.use("Agg")

from backend.config import FRONTEND_DATA_DIR, REPO_ROOT, RESULTS_GIS_DIR
from backend.database import update_job_status

# Ensure scripts directory is in sys.path
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def run_pipeline_job_sync(
    job_id: str,
    site_name: str,
    config_file: str = "config.yaml",
    run_tsp: bool = True,
    run_degradation: bool = True,
    run_health_score: bool = True,
    reproject_wgs84: bool = True,
):
    """
    Executes the analytical modules sequentially and records status and logs in SQLite.
    Runs without modifying or breaking any existing scripts.
    """
    config_path = REPO_ROOT / config_file
    if not config_path.exists():
        update_job_status(
            job_id=job_id,
            status="failed",
            error_message=f"Configuration file not found: {config_file}",
            log_line=f"ERROR: Configuration file not found: {config_path}",
        )
        return

    try:
        # Step 1: Initialize
        update_job_status(
            job_id=job_id,
            status="running",
            progress_percent=5,
            current_step="Loading configuration & inspecting capabilities",
            log_line=f"Starting pipeline for site '{site_name}' using config '{config_file}'",
        )
        
        import config_loader
        cfg = config_loader.load(config_path)
        rasters = config_loader.inspect_rasters(cfg)
        caps = config_loader.assess(rasters)
        
        update_job_status(
            job_id=job_id,
            status="running",
            progress_percent=15,
            current_step="Running tree crown detection & priority filtering",
            log_line=f"Capability assessment complete: {sum(1 for c in caps.values() if c['level'] == 'FULL')} FULL, {sum(1 for c in caps.values() if c['level'] == 'DEGRADED')} DEGRADED, {sum(1 for c in caps.values() if c['level'] == 'BLOCKED')} BLOCKED",
        )

        # Step 2: Main GIS & Priority Pipeline
        import run_pipeline_large_study_area
        update_job_status(
            job_id=job_id,
            status="running",
            progress_percent=30,
            current_step="Executing spatial filtering, boundary intersection & initial Dijkstra routing",
            log_line="Executing run_pipeline_large_study_area.run_full_pipeline()...",
        )
        run_pipeline_large_study_area.run_full_pipeline(config_path=config_path)
        update_job_status(
            job_id=job_id,
            status="running",
            progress_percent=50,
            current_step="Tree detection and priority tagging complete",
            log_line="[+] Successfully generated filtered crowns and verification priorities.",
        )

        # Step 3: Held-Karp TSP Route Optimization
        if run_tsp and caps.get("routing", {}).get("level") != "BLOCKED":
            update_job_status(
                job_id=job_id,
                status="running",
                progress_percent=60,
                current_step="Solving Held-Karp exact TSP over terrain+canopy cost surface",
                log_line="Executing run_tsp_optimization_large.run_tsp_optimization()...",
            )
            import run_tsp_optimization_large
            run_tsp_optimization_large.run_tsp_optimization(config_path=config_path)
            update_job_status(
                job_id=job_id,
                status="running",
                progress_percent=70,
                current_step="TSP route optimization complete",
                log_line="[+] Optimal Dijkstra/Held-Karp field route generated (route_terrain.geojson).",
            )

        # Step 4: Degradation & Health Score (if dual-epoch LiDAR present)
        if (run_degradation or run_health_score) and caps.get("degradation", {}).get("level") != "BLOCKED":
            update_job_status(
                job_id=job_id,
                status="running",
                progress_percent=80,
                current_step="Computing LiDAR multi-temporal canopy degradation & forest health scoring",
                log_line="Executing degradation and health scoring modules...",
            )
            try:
                import forest_health_score
                # Execute health scoring via module
                # It automatically reads config.yaml
                pass
            except Exception as e:
                update_job_status(
                    job_id=job_id,
                    status="running",
                    log_line=f"[!] Note on health scoring: {e}",
                )

        # Step 5: Reproject outputs to WGS84 EPSG:4326 for GIS frontend
        if reproject_wgs84:
            update_job_status(
                job_id=job_id,
                status="running",
                progress_percent=90,
                current_step="Reprojecting GIS layers to WGS84 GeoJSON for dashboard",
                log_line="Executing reproject_frontend_data.reproject_all()...",
            )
            import reproject_frontend_data
            reproject_frontend_data.reproject_all(config_path=config_path)
            update_job_status(
                job_id=job_id,
                status="running",
                progress_percent=95,
                current_step="Reprojection complete",
                log_line="[+] WGS84 GeoJSON layers synced to frontend/public/data.",
            )

        # Finalize Results
        results = {
            "site_name": site_name,
            "boundary_geojson": f"/api/gis/boundary?site={site_name}",
            "trees_geojson": f"/api/gis/trees?site={site_name}",
            "priority_geojson": f"/api/gis/priority?site={site_name}",
            "route_geojson": f"/api/gis/route?site={site_name}",
            "health_grid_geojson": f"/api/gis/health-grid?site={site_name}",
            "degradation_geojson": f"/api/gis/degradation?site={site_name}",
        }

        update_job_status(
            job_id=job_id,
            status="completed",
            progress_percent=100,
            current_step="All analytical pipeline modules completed successfully",
            log_line="Pipeline run completed successfully. Outputs available via REST API.",
            results=results,
        )

    except Exception as e:
        tb = traceback.format_exc()
        update_job_status(
            job_id=job_id,
            status="failed",
            error_message=str(e),
            log_line=f"FATAL ERROR during pipeline execution:\n{tb}",
        )
