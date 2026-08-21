"""
reproject_frontend_data.py
Reprojects GIS GeoJSON layers from their native source CRS to target CRS (default EPSG:4326 WGS84 lat/lon)
and exports them to frontend/public/data/. Reads CRS directly per dataset and validates bounds dynamically.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Optional, Union
import geopandas as gpd
import rasterio
from pyproj import Transformer

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader


def transform_coords(coords, transformer):
    """
    Recursively transforms coordinates from Source CRS (Easting, Northing)
    to Target CRS (Longitude, Latitude).
    """
    if not coords:
        return coords
    if isinstance(coords[0], (int, float)):
        easting, northing = coords[0], coords[1]
        lat, lon = transformer.transform(easting, northing)
        return [round(lon, 7), round(lat, 7)]
    else:
        return [transform_coords(c, transformer) for c in coords]


def reproject_geojson_file(in_path: Path, out_path: Path, source_crs, target_crs="EPSG:4326"):
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=False)
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    for feat in features:
        geom = feat.get("geometry")
        if geom and "coordinates" in geom:
            geom["coordinates"] = transform_coords(geom["coordinates"], transformer)

    data["crs"] = {
        "type": "name",
        "properties": {
            "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
        }
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return len(features), data


def reproject_all(config_path: Optional[Union[str, Path]] = None, target_crs: str = "EPSG:4326"):
    if config_path is None:
        config_path = REPO_ROOT / "config.yaml"
    cfg = config_loader.load(config_path)
    site_name = cfg.get("site", {}).get("name", "study_area")
    
    gis_dir = cfg.path("outputs", "gis_dir") or (REPO_ROOT / "results" / "gis")
    public_data_dir = cfg.path("outputs", "frontend_dir") or (REPO_ROOT / "frontend" / "public" / "data")
    public_data_dir.mkdir(parents=True, exist_ok=True)

    # Base fallback raster CRS
    rgb_path = cfg.path("site", "rasters", "rgb_t2", required=True)
    with rasterio.open(rgb_path) as src:
        base_raster_crs = src.crs
        src_bounds = src.bounds

    print(f"Base Raster ({rgb_path.name}) CRS: {base_raster_crs}")
    print(f"Study Area Bounds: {src_bounds}\n")

    # Ensure chm_removal_only.geojson exists if chm_loss_polygons exists
    loss_poly_path = gis_dir / "chm_loss_polygons.geojson"
    removal_poly_path = gis_dir / "chm_removal_only.geojson"
    if loss_poly_path.exists():
        gdf_loss = gpd.read_file(loss_poly_path)
        gdf_removal = gdf_loss[gdf_loss["class_id"] == 1].copy().reset_index(drop=True)
        gdf_removal.to_file(removal_poly_path, driver="GeoJSON")

    # Comprehensive candidate export file list
    candidate_files = [
        f"{site_name}_trees_chm_valid.geojson",
        f"{site_name}_trees_clean.geojson",
        f"{site_name}_trees_filtered.geojson",
        f"{site_name}_verification_priority.geojson",
        f"{site_name}_trees_with_boundary_status.geojson",
        f"{site_name}_boundary.geojson",
        "route_terrain.geojson",
        f"{site_name}_field_route_lcp_optimized.geojson",
        f"{site_name}_field_route_lcp.geojson",
        "chm_loss_polygons.geojson",
        "chm_removal_only.geojson",
        "forest_health_grid.geojson",
        "trees_degraded.geojson",
        "trees_degraded_interior.geojson",
        "OSBS_022_2019_field_route_lcp.geojson",
        "OSBS_022_2019_field_route.geojson",
        "OSBS_022_2019_verification_priority.geojson",
        "OSBS_022_2019_trees_with_boundary_status.geojson",
        "OSBS_022_degradation_zones.geojson",
    ]

    reprojected_counts = {}
    validation_trees_data = None

    for fname in candidate_files:
        in_p = gis_dir / fname
        out_p = public_data_dir / fname
        if not in_p.exists():
            continue

        # Dynamically determine source CRS per file
        try:
            gdf_temp = gpd.read_file(in_p)
            file_crs = gdf_temp.crs or base_raster_crs
        except Exception:
            file_crs = base_raster_crs

        count, data = reproject_geojson_file(in_p, out_p, file_crs, target_crs=target_crs)
        reprojected_counts[fname] = count
        print(f"Exported {fname:<45} -> {count:>5} features (source CRS: {file_crs})")

        if fname == f"{site_name}_trees_filtered.geojson" or (validation_trees_data is None and "trees" in fname):
            validation_trees_data = data

    # Copy static / non-projected auxiliary files
    fire_in = gis_dir / "fire_hotspots_osbs_live.geojson"
    fire_out = public_data_dir / "fire_hotspots_osbs_live.geojson"
    if fire_in.exists():
        shutil.copy2(fire_in, fire_out)
        with open(fire_in) as f:
            fire_cnt = len(json.load(f).get("features", []))
        reprojected_counts[fire_in.name] = fire_cnt
        print(f"Copied   {fire_in.name:<45} -> {fire_cnt:>5} features (unmodified WGS84)")

    # Copy maps and stats
    for img_file in gis_dir.glob("*.png"):
        shutil.copy2(img_file, public_data_dir / img_file.name)
    for json_file in gis_dir.glob("*_stats.json"):
        shutil.copy2(json_file, public_data_dir / json_file.name)

    # Optional sync to frontend/dist/data if dist directory exists
    dist_data_dir = REPO_ROOT / "frontend" / "dist" / "data"
    if dist_data_dir.parent.exists():
        dist_data_dir.mkdir(parents=True, exist_ok=True)
        for item in public_data_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, dist_data_dir / item.name)

    # Coordinate Validation against source raster bounds
    transformer = Transformer.from_crs(base_raster_crs, target_crs, always_xy=False)
    lat_min_src, lon_min_src = transformer.transform(src_bounds.left, src_bounds.bottom)
    lat_max_src, lon_max_src = transformer.transform(src_bounds.right, src_bounds.top)
    expected_lon_min, expected_lon_max = min(lon_min_src, lon_max_src), max(lon_min_src, lon_max_src)
    expected_lat_min, expected_lat_max = min(lat_min_src, lat_max_src), max(lat_min_src, lat_max_src)

    if validation_trees_data and validation_trees_data.get("features"):
        all_lons = [feat["geometry"]["coordinates"][0] for feat in validation_trees_data["features"]]
        all_lats = [feat["geometry"]["coordinates"][1] for feat in validation_trees_data["features"]]

        min_lon, max_lon = min(all_lons), max(all_lons)
        min_lat, max_lat = min(all_lats), max(all_lats)

        print("\n" + "="*80)
        print("           REPROJECTED DATASET COORDINATE VALIDATION")
        print("="*80)
        print(f"Site Name:              {site_name}")
        print(f"Source CRS -> Target:   {base_raster_crs} -> {target_crs}")
        print(f"Reprojected Longitude:  [{min_lon:.6f}, {max_lon:.6f}] (Expected ~[{expected_lon_min:.6f}, {expected_lon_max:.6f}])")
        print(f"Reprojected Latitude:   [{min_lat:.6f}, {max_lat:.6f}] (Expected ~[{expected_lat_min:.6f}, {expected_lat_max:.6f}])")
        
        eps = 0.005
        if not (expected_lon_min - eps <= min_lon <= expected_lon_max + eps and
                expected_lat_min - eps <= min_lat <= expected_lat_max + eps):
            print("\nERROR: Reprojected coordinates fall outside the source raster geographic bounds!")
            sys.exit(1)
        else:
            print("CONFIRMED: Coordinates successfully validated against source raster extent!")
        print("="*80)

    # Detailed export audit table
    print("\n" + "="*80)
    print("           FRONTEND PUBLIC DATA EXPORT INVENTORY")
    print("="*80)
    print(f"{'Filename':<48} {'Features':>10}  {'Modified Timestamp':<20}")
    print("-" * 80)
    for p in sorted(public_data_dir.iterdir()):
        if p.name.endswith(".geojson"):
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            try:
                with open(p) as f:
                    cnt = len(json.load(f).get("features", []))
            except Exception:
                cnt = "N/A"
            print(f"{p.name:<48} {str(cnt):>10}  {mtime}")
    print("="*80 + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--target-crs", default="EPSG:4326")
    args = ap.parse_args()
    reproject_all(config_path=args.config, target_crs=args.target_crs)


if __name__ == "__main__":
    main()
