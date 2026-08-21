"""
reproject_frontend_data.py
Reprojects GIS GeoJSON layers from native raster CRS to target CRS (default EPSG:4326 WGS84 lat/lon)
and places them into frontend/public/data/. Validates coordinates against the source raster's bounds.
"""

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Optional, Union
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
    if isinstance(coords[0], (int, float)):
        easting, northing = coords[0], coords[1]
        lat, lon = transformer.transform(easting, northing)
        return [round(lon, 7), round(lat, 7)]
    else:
        return [transform_coords(c, transformer) for c in coords]


def reproject_geojson(in_path: Path, out_path: Path, transformer: Transformer):
    print(f"Reprojecting {in_path.name} -> {out_path.name}...")
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
    print(f"  Successfully wrote {len(features)} features to {out_path}")
    return data


def reproject_all(config_path: Optional[Union[str, Path]] = None, target_crs: str = "EPSG:4326"):
    if config_path is None:
        config_path = REPO_ROOT / "config.yaml"
    cfg = config_loader.load(config_path)
    site_name = cfg.get("site", {}).get("name", "study_area")
    
    gis_dir = cfg.path("outputs", "gis_dir") or (REPO_ROOT / "results" / "gis")
    public_data_dir = cfg.path("outputs", "frontend_dir") or (REPO_ROOT / "frontend" / "public" / "data")
    public_data_dir.mkdir(parents=True, exist_ok=True)

    rgb_path = cfg.path("site", "rasters", "rgb_t2", required=True)
    with rasterio.open(rgb_path) as src:
        source_crs = src.crs
        src_bounds = src.bounds

    print(f"Source CRS dynamically read from {rgb_path.name}: {source_crs}")
    print(f"Source Bounds: {src_bounds}")

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=False)

    files_to_reproject = [
        f"{site_name}_trees_filtered.geojson",
        f"{site_name}_verification_priority.geojson",
        f"{site_name}_boundary.geojson",
    ]
    
    for route_cand in ["route_terrain.geojson", f"{site_name}_field_route_lcp_optimized.geojson", f"{site_name}_field_route_lcp.geojson"]:
        if (gis_dir / route_cand).exists():
            files_to_reproject.append(route_cand)

    reprojected_trees = None
    for fname in files_to_reproject:
        in_p = gis_dir / fname
        out_p = public_data_dir / fname
        if not in_p.exists():
            print(f"Skipping non-existent file: {fname}")
            continue
        data = reproject_geojson(in_p, out_p, transformer)
        if "trees_filtered" in fname:
            reprojected_trees = data

    fire_in = gis_dir / "fire_hotspots_osbs_live.geojson"
    fire_out = public_data_dir / "fire_hotspots_osbs_live.geojson"
    if fire_in.exists():
        shutil.copy2(fire_in, fire_out)
        print(f"Copied {fire_in.name} AS-IS to {fire_out}")

    for map_name in [f"{site_name}_route_clean.png", f"{site_name}_overview_map_optimized.png", f"{site_name}_overview_map.png"]:
        img_in = gis_dir / map_name
        img_out = public_data_dir / map_name
        if img_in.exists():
            shutil.copy2(img_in, img_out)
            print(f"Copied {img_in.name} to {img_out}")

    # Coordinate Validation against source raster bounds
    # Convert source bounds to target_crs to validate accurately
    lat_min_src, lon_min_src = transformer.transform(src_bounds.left, src_bounds.bottom)
    lat_max_src, lon_max_src = transformer.transform(src_bounds.right, src_bounds.top)
    expected_lon_min, expected_lon_max = min(lon_min_src, lon_max_src), max(lon_min_src, lon_max_src)
    expected_lat_min, expected_lat_max = min(lat_min_src, lat_max_src), max(lat_min_src, lat_max_src)

    if reprojected_trees and reprojected_trees.get("features"):
        all_lons = [feat["geometry"]["coordinates"][0] for feat in reprojected_trees["features"]]
        all_lats = [feat["geometry"]["coordinates"][1] for feat in reprojected_trees["features"]]

        min_lon, max_lon = min(all_lons), max(all_lons)
        min_lat, max_lat = min(all_lats), max(all_lats)
        center_lon = (min_lon + max_lon) / 2.0
        center_lat = (min_lat + max_lat) / 2.0

        print("\n" + "="*80)
        print("           REPROJECTED DATASET COORDINATE VALIDATION")
        print("="*80)
        print(f"Site Name:              {site_name}")
        print(f"Source CRS -> Target:   {source_crs} -> {target_crs}")
        print(f"Total Features Checked: {len(reprojected_trees['features'])}")
        print(f"Reprojected Longitude:  [{min_lon:.6f}, {max_lon:.6f}] (Expected ~[{expected_lon_min:.6f}, {expected_lon_max:.6f}])")
        print(f"Reprojected Latitude:   [{min_lat:.6f}, {max_lat:.6f}] (Expected ~[{expected_lat_min:.6f}, {expected_lat_max:.6f}])")
        
        # Validate against source raster transformed bounds (with small epsilon tolerance)
        eps = 0.005
        if not (expected_lon_min - eps <= min_lon <= expected_lon_max + eps and
                expected_lat_min - eps <= min_lat <= expected_lat_max + eps):
            print("\nERROR: Reprojected coordinates fall outside the source raster geographic bounds!")
            sys.exit(1)
        else:
            print("CONFIRMED: Coordinates successfully validated against source raster extent!")
        print("="*80)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--target-crs", default="EPSG:4326")
    args = ap.parse_args()
    reproject_all(config_path=args.config, target_crs=args.target_crs)


if __name__ == "__main__":
    main()
