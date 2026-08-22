"""
backend/services/site_context.py
Authoritative Canonical Site Context service for VanDrishti.
Serves as the single source of truth for study tile metadata, bounds, CRS,
provenance labels, and acquisition dates.
"""

from typing import Any, Dict
from backend.config import REPO_ROOT

def get_canonical_site_context(site_id: str = "OSBS_large_2019") -> Dict[str, Any]:
    """
    Returns the authoritative site context dictionary for a site or upload job ID.
    Primary operational site: OSBS_large_2019 (250m x 250m study tile, 6.25 ha).
    """
    site_clean = site_id.strip()
    is_teak = "teak" in site_clean.lower()
    is_upload = site_clean.startswith("upload_")

    if is_upload:
        return {
            "site_id": site_clean,
            "site_name": f"Uploaded Raster Dataset ({site_clean})",
            "study_tile_label": "User Custom Upload Area",
            "study_tile_area_ha": 0.0,
            "crs_processing": "Dynamic Auto-Detected (Raster CRS)",
            "crs_webgis": "EPSG:4326 (WGS84)",
            "data_provenance": {
                "rgb_source": "User Uploaded GeoTIFF",
                "chm_source": "User Uploaded CHM / ExG Fallback",
                "fire_source": "N/A (Upload Area)",
                "routing_source": "User Cost Surface Dijkstra"
            },
            "acquisition_dates": {
                "rgb": "Upload Session",
                "lidar_baseline": "N/A",
                "lidar_current": "Upload Session",
                "fire": "N/A"
            }
        }

    if is_teak:
        return {
            "site_id": "TEAK_043_2018",
            "site_name": "Teakettle (TEAK), Sierra Nevada CA",
            "study_tile_label": "Secondary Validation Dataset (TEAK_043)",
            "study_tile_area_ha": 0.16,
            "crs_processing": "EPSG:32611 (UTM Zone 11N)",
            "crs_webgis": "EPSG:4326 (WGS84)",
            "data_provenance": {
                "rgb_source": "2018 NEON AOP Airborne RGB",
                "chm_source": "2018 NEON LiDAR CHM",
                "fire_source": "N/A (Historical Test Area)",
                "routing_source": "Tobler DTM + LCP Dijkstra"
            },
            "acquisition_dates": {
                "rgb": "2018 NEON AOP",
                "lidar_baseline": "2018 NEON LiDAR",
                "lidar_current": "2018 NEON LiDAR",
                "fire": "N/A"
            }
        }

    # Primary Production Site: OSBS_large_2019
    return {
        "site_id": "OSBS_large_2019",
        "site_name": "Ordway-Swisher Biological Station (OSBS)",
        "study_tile_label": "250m × 250m Operational Study Area (6.25 ha)",
        "study_tile_area_ha": 6.25,
        "crs_processing": "EPSG:32617 (UTM Zone 17N)",
        "crs_webgis": "EPSG:4326 (WGS84)",
        "data_provenance": {
            "rgb_source": "2019 NEON AOP Aerial RGB Orthomosaic (10 cm)",
            "chm_source": "Dual-Epoch NEON LiDAR CHM (2018 vs 2019)",
            "health_grid_source": "25m Composite Canopy Cover + Height Diversity",
            "degradation_source": "Dual-Epoch CHM Differencing (ΔH <= -5m)",
            "fire_source": "Live NASA FIRMS VIIRS 375m NRT Thermal Stream",
            "routing_source": "Tobler Slope DTM + CHM Impedance Held-Karp TSP"
        },
        "acquisition_dates": {
            "rgb": "2019-05 (Historical / Processed)",
            "lidar_baseline": "2018-05 (Historical LiDAR CHM)",
            "lidar_current": "2019-05 (Historical LiDAR CHM)",
            "fire": "Live Real-Time Stream (NASA FIRMS NRT)"
        }
    }
