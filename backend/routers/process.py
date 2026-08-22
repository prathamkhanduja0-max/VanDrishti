"""
backend/routers/process.py
Router for triggering analysis jobs (detection, priority scoring, Held-Karp routing)
and monitoring their real-time execution status and logs.
"""

import uuid
from typing import List
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.database import create_job, get_job, list_jobs
from backend.schemas import JobStatusResponse, ProcessRequest
from backend.services.pipeline_service import run_pipeline_job_sync

router = APIRouter(prefix="/api", tags=["Pipeline & Jobs"])


@router.post("/process", response_model=JobStatusResponse, summary="Trigger automated detection & routing pipeline")
async def trigger_pipeline_job(req: ProcessRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    site_name = req.site_name or "OSBS_large_2019"
    config_file = req.config_file or ("config_teak.yaml" if "teak" in site_name.lower() else "config.yaml")

    # Record job in database
    job_data = create_job(job_id=job_id, site_name=site_name, config_path=config_file)

    # Launch background task
    background_tasks.add_task(
        run_pipeline_job_sync,
        job_id=job_id,
        site_name=site_name,
        config_file=config_file,
        run_tsp=req.run_tsp,
        run_degradation=req.run_degradation,
        run_health_score=req.run_health_score,
        reproject_wgs84=req.reproject_wgs84,
    )

    return job_data


@router.get("/status/{job_id}", response_model=JobStatusResponse, summary="Get progress, status, and logs for a pipeline job")
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get("/jobs", response_model=List[JobStatusResponse], summary="List all recent pipeline runs")
async def get_all_jobs():
    return list_jobs()
