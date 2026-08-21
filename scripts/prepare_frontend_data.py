"""
prepare_frontend_data.py
Part A: Reprojects VanDrishti GeoJSON layers from UTM Zone 17N (EPSG:32617) to WGS84 (EPSG:4326)
and copies all assets into the frontend public data directory for Leaflet web visualization.
"""

import json
from pathlib import Path
import shutil
import geopandas as gpd


def prepare_frontend_data():
    project_root = Path(__file__).resolve().parent.parent
    frontend_data_dirs = [
        project_root / "frontend" / "public" / "data",
        project_root / "frontend" / "data",
    ]

    for d in frontend_data_dirs:
        d.mkdir(parents=True, exist_ok=True)

    files_to_reproject = [
        ("project_boundary_OSBS_022.geojson", project_root / "data" / "demo" / "project_boundary_OSBS_022.geojson"),
        ("OSBS_022_2019_trees_with_boundary_status.geojson", project_root / "results" / "gis" / "OSBS_022_2019_trees_with_boundary_status.geojson"),
        ("OSBS_022_2019_verification_priority.geojson", project_root / "results" / "gis" / "OSBS_022_2019_verification_priority.geojson"),
        ("OSBS_022_2019_field_route.geojson", project_root / "results" / "gis" / "OSBS_022_2019_field_route.geojson"),
        ("OSBS_022_2019_field_route_lcp.geojson", project_root / "results" / "gis" / "OSBS_022_2019_field_route_lcp.geojson"),
        ("OSBS_022_degradation_zones.geojson", project_root / "results" / "gis" / "OSBS_022_degradation_zones.geojson"),
    ]

    print("=" * 88)
    print("           PART A: REPROJECTING GIS LAYERS TO WGS84 (EPSG:4326)")
    print("=" * 88)

    reprojected_info = {}

    for fname, src_path in files_to_reproject:
        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {src_path}")

        print(f"\nProcessing: {fname}")
        gdf = gpd.read_file(src_path)
        print(f"  Source CRS: {gdf.crs} | Features: {len(gdf)}")

        # Reproject to EPSG:4326 (WGS84 Lat/Lon)
        gdf_wgs84 = gdf.to_crs("EPSG:4326")

        # Bounds validation
        total_bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy] = [min_lon, min_lat, max_lon, max_lat]
        min_lon, min_lat, max_lon, max_lat = total_bounds

        # Strict validation: Coordinates must be in Florida range (Lon: ~ -82.0, Lat: ~ 29.7)
        if not (-85.0 <= min_lon <= -80.0 and 28.0 <= min_lat <= 32.0):
            raise ValueError(
                f"FATAL ERROR: Reprojection failed for {fname}! Coordinates out of range: "
                f"Lon [{min_lon}, {max_lon}], Lat [{min_lat}, {max_lat}]"
            )

        print(f"  Reprojected Bounds (WGS84): Lon [{min_lon:.6f} to {max_lon:.6f}], Lat [{min_lat:.6f} to {max_lat:.6f}]")

        # Save copies to both frontend data dirs
        for target_dir in frontend_data_dirs:
            target_path = target_dir / fname
            gdf_wgs84.to_file(target_path, driver="GeoJSON")

        reprojected_info[fname] = {
            "features": len(gdf_wgs84),
            "bounds": [round(b, 6) for b in total_bounds],
            "center": [round((min_lat + max_lat) / 2.0, 6), round((min_lon + max_lon) / 2.0, 6)],
        }
        print(f"  Saved WGS84 GeoJSON to frontend data directories.")

    # Copy fire hotspots (already EPSG:4326)
    fire_src = project_root / "results" / "gis" / "fire_hotspots_osbs_live.geojson"
    if fire_src.exists():
        gdf_fire = gpd.read_file(fire_src)
        print(f"\nCopying fire_hotspots_osbs_live.geojson (already EPSG:4326): {len(gdf_fire)} features")
        for target_dir in frontend_data_dirs:
            shutil.copy2(fire_src, target_dir / "fire_hotspots_osbs_live.geojson")
        reprojected_info["fire_hotspots_osbs_live.geojson"] = {
            "features": len(gdf_fire),
            "bounds": [round(b, 6) for b in gdf_fire.total_bounds],
        }

    # Copy PNG maps
    png_files = [
        "OSBS_022_2019_gis_map.png",
        "OSBS_022_degradation_map.png",
        "OSBS_022_2019_field_route_map.png",
        "OSBS_022_2019_field_route_lcp_map.png",
        "fire_hotspots_osbs_live_map.png",
    ]
    for png in png_files:
        src = project_root / "results" / "gis" / png
        if src.exists():
            for target_dir in frontend_data_dirs:
                shutil.copy2(src, target_dir / png)

    # Save manifest.json for frontend consumption
    manifest_path = frontend_data_dirs[0] / "manifest.json"
    manifest_data = {
        "study_area": {
            "name": "OSBS_022",
            "site": "Ordway-Swisher Biological Station (OSBS), Florida",
            "center": reprojected_info["OSBS_022_2019_trees_with_boundary_status.geojson"]["center"],
            "bounds": reprojected_info["OSBS_022_2019_trees_with_boundary_status.geojson"]["bounds"],
        },
        "layers": reprojected_info,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)

    with open(frontend_data_dirs[1] / "manifest.json", "w") as f:
        json.dump(manifest_data, f, indent=2)

    tree_bounds = reprojected_info["OSBS_022_2019_trees_with_boundary_status.geojson"]["bounds"]
    print("\n" + "=" * 88)
    print("                     PART A VALIDATION CONFIRMATION")
    print("=" * 88)
    print(f"Tree Layer Confirmed WGS84 Lat/Lon Bounding Box:")
    print(f"  - West Longitude:  {tree_bounds[0]:.6f}°")
    print(f"  - South Latitude:  {tree_bounds[1]:.6f}°")
    print(f"  - East Longitude:  {tree_bounds[2]:.6f}°")
    print(f"  - North Latitude:  {tree_bounds[3]:.6f}°")
    print(f"  - Geographic Center: Lat {manifest_data['study_area']['center'][0]:.6f}°, Lon {manifest_data['study_area']['center'][1]:.6f}°")
    print(f"All coordinates are verified in Florida (~lat 29.7, lon -82.0). Zero UTM leakage.")
    print("=" * 88)

    return manifest_data


if __name__ == "__main__":
    prepare_frontend_data()
