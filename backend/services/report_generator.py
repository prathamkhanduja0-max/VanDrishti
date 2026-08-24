"""
backend/services/report_generator.py
Generates CSV tree inventory exports and publication-ready PDF reports
for the Site-Specific Forest Diversion Assessment.
Uses get_diversion_assessment as the CANONICAL SINGLE SOURCE OF TRUTH.
"""

import csv
import io
from pathlib import Path
from typing import Any, Dict

from backend.services.diversion_service import get_diversion_assessment


def generate_diversion_csv(site_name: str = "OSBS_large_2019") -> str:
    """
    Generates a CSV tree inventory export from the canonical assessment payload.
    """
    assessment = get_diversion_assessment(site_name)
    inventory = assessment.get("inventory_sample", [])
    site_ctx = assessment.get("site_context", {})

    output = io.StringIO()
    writer = csv.writer(output)

    # Write Header
    writer.writerow([
        "Tree_ID",
        "Latitude_WGS84",
        "Longitude_WGS84",
        "UTM_Easting_m",
        "UTM_Northing_m",
        "Confidence_Score",
        "CHM_Height_m",
        "Corridor_Status",
        "Verification_Priority",
        "Priority_Rationale",
        "Site_ID",
        "Site_Label"
    ])

    # Write Tree Records
    for item in inventory:
        writer.writerow([
            item.get("tree_id"),
            item.get("latitude"),
            item.get("longitude"),
            item.get("utm_easting"),
            item.get("utm_northing"),
            item.get("confidence"),
            item.get("chm_height_m"),
            item.get("corridor_status"),
            item.get("priority"),
            item.get("rationale"),
            site_ctx.get("site_id"),
            site_ctx.get("site_label")
        ])

    return output.getvalue()


def generate_diversion_pdf(site_name: str = "OSBS_large_2019") -> bytes:
    """
    Generates a publication-ready PDF report from the canonical assessment payload.
    Ensures 100% numerical parity with the WebGIS UI and CSV export.
    """
    assessment = get_diversion_assessment(site_name)
    summary = assessment.get("summary", {})
    site_ctx = assessment.get("site_context", {})
    provenance = assessment.get("provenance", {})
    capabilities = assessment.get("capabilities", {})

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import (
            HRFlowable,
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#064e3b")
        )
        subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#047857")
        )
        h2_style = ParagraphStyle(
            "Heading2Custom",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#065f46"),
            spaceBefore=8,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            "BodyCustom",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor("#1e293b")
        )
        disclaimer_style = ParagraphStyle(
            "Disclaimer",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#991b1b")
        )

        story = []

        # 1. Header Title Banner & Site Context
        story.append(Paragraph("VanDrishti — Forest Intelligence Platform", subtitle_style))
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"Site-Specific Forest Diversion Assessment: {site_ctx.get('site_label')}", title_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"Generated: {site_ctx.get('generated_at')} | CRS: {site_ctx.get('crs_processing')} → {site_ctx.get('crs_webgis')}", body_style))
        story.append(Spacer(1, 5))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#059669"), spaceBefore=2, spaceAfter=6))

        # 2. Executive Summary & Statutory Disclaimer
        story.append(Paragraph("1. Executive Summary & Statutory Disclaimer", h2_style))
        story.append(Paragraph(
            f"This assessment evaluates proposed land diversion over a <b>{summary.get('corridor_area_sq_m', 0):,.1f} m²</b> corridor "
            f"covering <b>{summary.get('corridor_coverage_pct', 0):.1f}%</b> of the study area. Out of an operational inventory of <b>{summary.get('operational_inventory_count', 0):,} trees</b>, "
            f"a total of <b>{summary.get('impacted_trees_count', 0):,} trees ({summary.get('impacted_pct', 0):.1f}%)</b> fall within the direct right-of-way corridor.",
            body_style
        ))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<b>Statutory Disclaimer:</b> {assessment.get('statutory_disclaimer')}", disclaimer_style))
        story.append(Spacer(1, 6))

        # 3. Data Inventory & Provenance Pipeline
        story.append(Paragraph("2. Data Inventory & Provenance Pipeline", h2_style))
        story.append(Paragraph(f"<i>{assessment.get('funnel_explanation')}</i>", body_style))
        story.append(Spacer(1, 4))

        funnel_data = [
            ["Pipeline Stage", "Tree Count", "Data Provenance & Freshness"],
            ["Raw Model Detections", f"{summary.get('raw_trees_count', 0):,}", f"{provenance.get('tree_detection', {}).get('source')} [{provenance.get('tree_detection', {}).get('freshness')}]"],
            ["LiDAR Validated Trees", f"{summary.get('validated_trees_count', 0):,}", f"{provenance.get('lidar_validation', {}).get('source')} (CHM height >= 2.0m)"],
            ["Operational Inventory", f"{summary.get('operational_inventory_count', 0):,}", "Confidence >= 0.50 & Spatial Centroid NMS Deduplication"],
            ["Corridor-Impacted Trees", f"{summary.get('impacted_trees_count', 0):,}", "Direct spatial intersection with proposed project corridor"]
        ]
        t_funnel = Table(funnel_data, colWidths=[130, 80, 310])
        t_funnel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
        ]))
        story.append(t_funnel)
        story.append(Spacer(1, 8))

        # 4. Priority Audit Breakdown & Field Traversal Route
        story.append(Paragraph("3. Priority Audit Breakdown & Field Traversal Route", h2_style))
        prio_data = [
            ["Priority Tier", "Total Count", "Corridor Impacted", "Ground Audit Protocol"],
            ["HIGH Priority", f"{summary.get('high_priority_count', 0)}", f"{summary.get('impacted_high_priority_count', 0)}", "Mandatory ground truth audit (Corridor impact & low confidence)"],
            ["MEDIUM Priority", f"{summary.get('medium_priority_count', 0)}", f"{summary.get('impacted_medium_priority_count', 0)}", "Statutory check (Corridor impact with moderate confidence)"],
            ["LOW Priority", f"{summary.get('low_priority_count', 0)}", f"{summary.get('impacted_low_priority_count', 0)}", "Safe buffer canopy outside project corridor"]
        ]
        t_prio = Table(prio_data, colWidths=[110, 70, 95, 245])
        t_prio.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#047857")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
        ]))
        story.append(t_prio)
        story.append(Spacer(1, 4))

        route_src = provenance.get("field_routing", {}).get("source", "Tobler DTM Dijkstra")
        story.append(Paragraph(
            f"<b>Field Traversal Route ({route_src}):</b> Covers "
            f"<b>{summary.get('field_route_stops_count', 0)} audit stops</b> over <b>{summary.get('field_route_distance_m', 0):.1f} meters</b> "
            f"(estimated traversal time: <b>{summary.get('field_route_time_min', 0):.1f} minutes</b>).",
            body_style
        ))
        story.append(Spacer(1, 8))

        # 5. Forest Health, Degradation & Fire Intelligence
        story.append(Paragraph("4. Health, Degradation & Thermal Fire Intelligence", h2_style))
        health_data = [
            ["Metric Module", "Value / Status", "Provenance & Breakdown"],
            ["Forest Health Grid", f"{summary.get('total_health_cells', 0)} cells ({capabilities.get('health_score', 'UNAVAILABLE')})", f"Grade A: {summary.get('health_grade_a', 0)} | B: {summary.get('health_grade_b', 0)} | C: {summary.get('health_grade_c', 0)} | D: {summary.get('health_grade_d', 0)}"],
            ["Canopy Loss Polygons", f"{summary.get('total_degradation_polygons', 0)} zones ({capabilities.get('degradation', 'UNAVAILABLE')})", f"Severe Removal (ΔH <= -5m): {summary.get('degradation_removal_count', 0)} | Thinning: {summary.get('degradation_thinning_count', 0)}"],
            ["Thermal Fire Hotspots", f"{summary.get('fire_hotspots_count', 0)} hotspots ({capabilities.get('fire', 'LIVE_REAL_TIME')})", f"{provenance.get('fire_monitoring', {}).get('source')} [{provenance.get('fire_monitoring', {}).get('freshness')}]"]
        ]
        t_health = Table(health_data, colWidths=[130, 110, 280])
        t_health.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
        ]))
        story.append(t_health)

        # Build Document
        doc.build(story)
        return buffer.getvalue()

    except ImportError:
        fallback_text = (
            f"VanDrishti — Forest Diversion Assessment Report\n"
            f"Site: {site_ctx.get('site_label')}\n"
            f"Generated: {site_ctx.get('generated_at')}\n\n"
            f"SUMMARY:\n"
            f"Corridor Area: {summary.get('corridor_area_sq_m'):,.1f} m²\n"
            f"Operational Inventory: {summary.get('operational_inventory_count')} trees\n"
            f"Impacted Corridor Trees: {summary.get('impacted_trees_count')} trees\n"
            f"HIGH Priority Stops: {summary.get('high_priority_count')}\n"
            f"TSP Route Length: {summary.get('field_route_distance_m')} m\n\n"
            f"Statutory Disclaimer: {assessment.get('statutory_disclaimer')}\n"
        )
        return fallback_text.encode("utf-8")
