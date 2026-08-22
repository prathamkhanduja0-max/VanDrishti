"""
backend/database.py
Lightweight SQLite persistence layer for VanDrishti backend.
Stores upload references, pipeline job statuses, execution logs, and result paths.
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from backend.config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the database schema if tables do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Uploads table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER,
                crs TEXT,
                bounds TEXT,
                width INTEGER,
                height INTEGER,
                created_at TEXT NOT NULL,
                metadata_json TEXT
            )
        """)
        
        # Jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                site_name TEXT NOT NULL,
                config_path TEXT,
                status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed'
                progress_percent INTEGER DEFAULT 0,
                current_step TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                error_message TEXT,
                logs TEXT,
                results_json TEXT
            )
        """)
        
        # Fire monitoring cache
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fire_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preset TEXT NOT NULL,
                hotspot_count INTEGER DEFAULT 0,
                geojson_path TEXT,
                queried_at TEXT NOT NULL,
                data_json TEXT
            )
        """)
        
        conn.commit()


# Database helper methods
def create_upload_record(
    upload_id: str,
    filename: str,
    file_type: str,
    file_path: str,
    file_size_bytes: int,
    crs: Optional[str] = None,
    bounds: Optional[Dict[str, Any]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    bounds_str = json.dumps(bounds) if bounds else None
    meta_str = json.dumps(metadata) if metadata else None
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO uploads (id, filename, file_type, file_path, file_size_bytes, crs, bounds, width, height, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (upload_id, filename, file_type, file_path, file_size_bytes, crs, bounds_str, width, height, now, meta_str)
        )
        conn.commit()
        
    return {
        "id": upload_id,
        "filename": filename,
        "file_type": file_type,
        "file_path": file_path,
        "file_size_bytes": file_size_bytes,
        "crs": crs,
        "bounds": bounds,
        "width": width,
        "height": height,
        "created_at": now,
        "metadata": metadata or {},
    }


def list_uploads(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM uploads ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "filename": r["filename"],
            "file_type": r["file_type"],
            "file_path": r["file_path"],
            "file_size_bytes": r["file_size_bytes"],
            "crs": r["crs"],
            "bounds": json.loads(r["bounds"]) if r["bounds"] else None,
            "width": r["width"],
            "height": r["height"],
            "created_at": r["created_at"],
            "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else {},
        })
    return results


def create_job(job_id: str, site_name: str, config_path: str) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (id, site_name, config_path, status, progress_percent, current_step, created_at, logs)
            VALUES (?, ?, ?, 'pending', 0, 'Job initialized', ?, '')
            """,
            (job_id, site_name, config_path, now)
        )
        conn.commit()
        
    return {
        "job_id": job_id,
        "site_name": site_name,
        "status": "pending",
        "progress_percent": 0,
        "current_step": "Job initialized",
        "created_at": now,
    }


def update_job_status(
    job_id: str,
    status: str,
    progress_percent: Optional[int] = None,
    current_step: Optional[str] = None,
    error_message: Optional[str] = None,
    log_line: Optional[str] = None,
    results: Optional[Dict[str, Any]] = None,
):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT logs FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        existing_logs = row["logs"] if row and row["logs"] else ""
        
        if log_line:
            timestamp = datetime.utcnow().strftime("%H:%M:%S")
            existing_logs += f"[{timestamp}] {log_line}\n"
            
        completed_at = datetime.utcnow().isoformat() if status in ("completed", "failed") else None
        results_str = json.dumps(results) if results is not None else None
        
        updates = ["status = ?", "logs = ?"]
        params = [status, existing_logs]
        
        if progress_percent is not None:
            updates.append("progress_percent = ?")
            params.append(progress_percent)
            
        if current_step is not None:
            updates.append("current_step = ?")
            params.append(current_step)
            
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
            
        if completed_at is not None:
            updates.append("completed_at = ?")
            params.append(completed_at)
            
        if results_str is not None:
            updates.append("results_json = ?")
            params.append(results_str)
            
        params.append(job_id)
        query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        
    if not row:
        return None
        
    return {
        "job_id": row["id"],
        "site_name": row["site_name"],
        "config_path": row["config_path"],
        "status": row["status"],
        "progress_percent": row["progress_percent"],
        "current_step": row["current_step"],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"],
        "error_message": row["error_message"],
        "logs": row["logs"],
        "results": json.loads(row["results_json"]) if row["results_json"] else None,
    }


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        
    return [
        {
            "job_id": r["id"],
            "site_name": r["site_name"],
            "status": r["status"],
            "progress_percent": r["progress_percent"],
            "current_step": r["current_step"],
            "created_at": r["created_at"],
            "completed_at": r["completed_at"],
            "error_message": r["error_message"],
            "results": json.loads(r["results_json"]) if r["results_json"] else None,
        }
        for r in rows
    ]


# Initialize tables at import time
init_db()
