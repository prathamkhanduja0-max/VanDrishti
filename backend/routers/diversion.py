"""
backend/routers/diversion.py
FastAPI router for serving Site-Aware Forest Diversion Assessment JSON payloads
and exporting publication-ready CSV and PDF reports.
"""

from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from backend.services.diversion_service import get_diversion_assessment
from backend.services.report_generator import generate_diversion_csv, generate_diversion_pdf

router = APIRouter(prefix="/api/diversion", tags=["Forest Diversion Assessment"])


@router.get("/assessment", summary="Get structured Site-Aware Forest Diversion Assessment payload")
async def fetch_diversion_assessment(site: str = Query("OSBS_large_2019", description="Site identifier or upload job ID")):
    site_clean = unquote(site).strip()
    data = get_diversion_assessment(site_clean)
    if not data:
        raise HTTPException(status_code=404, detail=f"Diversion assessment for site '{site_clean}' not found")
    return JSONResponse(content=data)


@router.get("/export/csv", summary="Export tree-by-tree inventory as CSV")
async def export_diversion_csv(site: str = Query("OSBS_large_2019", description="Site identifier or upload job ID")):
    site_clean = unquote(site).strip()
    try:
        csv_content = generate_diversion_csv(site_clean)
        filename = f"van_drishti_diversion_inventory_{site_clean}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV generation failed for '{site_clean}': {str(e)}")


@router.get("/export/pdf", summary="Export publication-ready PDF assessment report")
async def export_diversion_pdf(site: str = Query("OSBS_large_2019", description="Site identifier or upload job ID")):
    site_clean = unquote(site).strip()
    try:
        pdf_bytes = generate_diversion_pdf(site_clean)
        filename = f"van_drishti_diversion_report_{site_clean}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed for '{site_clean}': {str(e)}")
