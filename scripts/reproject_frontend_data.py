"""
reproject_frontend_data.py
Reprojects GIS GeoJSON layers from EPSG:32617 (UTM 17N) to EPSG:4326 (WGS84 lat/lon)
and places them into frontend/public/data/ along with fire hotspots and clean route image.
"""

import json
from pathlib import Path
import shutil
from pyproj import Transformer


def transform_coords(coords, transformer):
    """
    Recursively transforms coordinates from EPSG:32617 (Easting, Northing)
    to EPSG:4326 (Longitude, Latitude).
    """
    if isinstance(coords[0], (int, float)):
        # Base case: [x, y] -> (lon, lat)
        easting, northing = coords[0], coords[1]
        lat, lon = transformer.transform(easting, northing)
        # GeoJSON is [longitude, latitude]
        return [round(lon, 7), round(lat, 7)]
    else:
        return [transform_coords(c, transformer) for c in coords]


def reproject_geojson(in_path: Path, out_path: Path, transformer: Transformer):
    print(f"Reprojecting {in_path.name} -> {out_path.name}...")
    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Transform all features
    features = data.get("features", [])
    for feat in features:
        geom = feat.get("geometry")
        if geom and "coordinates" in geom:
            geom["coordinates"] = transform_coords(geom["coordinates"], transformer)

    # Update CRS definition if present
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


def main():
    project_root = Path("C:/VanDrishtiProject")
    gis_dir = project_root / "results" / "gis"
    public_data_dir = project_root / "frontend" / "public" / "data"
    public_data_dir.mkdir(parents=True, exist_ok=True)

    # EPSG:32617 (UTM Zone 17N) -> EPSG:4326 (WGS84 lat, lon)
    transformer = Transformer.from_crs("EPSG:32617", "EPSG:4326", always_xy=False)

    files_to_reproject = [
        "OSBS_large_2019_trees_filtered.geojson",
        "OSBS_large_2019_verification_priority.geojson",
        "OSBS_large_2019_boundary.geojson",
        "OSBS_large_2019_field_route_lcp_optimized.geojson"
    ]

    reprojected_trees = None
    for fname in files_to_reproject:
        in_p = gis_dir / fname
        out_p = public_data_dir / fname
        if not in_p.exists():
            raise FileNotFoundError(f"Missing input file: {in_p}")
        data = reproject_geojson(in_p, out_p, transformer)
        if fname == "OSBS_large_2019_trees_filtered.geojson":
            reprojected_trees = data

    # Copy fire_hotspots_osbs_live.geojson AS-IS
    fire_in = gis_dir / "fire_hotspots_osbs_live.geojson"
    fire_out = public_data_dir / "fire_hotspots_osbs_live.geojson"
    if fire_in.exists():
        shutil.copy2(fire_in, fire_out)
        print(f"Copied {fire_in.name} AS-IS to {fire_out}")

    # Copy clean route image
    img_in = gis_dir / "OSBS_large_2019_route_clean.png"
    img_out = public_data_dir / "OSBS_large_2019_route_clean.png"
    if img_in.exists():
        shutil.copy2(img_in, img_out)
        print(f"Copied {img_in.name} to {img_out}")

    # Inspect tree coordinates and print lat/lon bounding box
    all_lons = []
    all_lats = []
    for feat in reprojected_trees["features"]:
        coords = feat["geometry"]["coordinates"]
        all_lons.append(coords[0])
        all_lats.append(coords[1])

    min_lon, max_lon = min(all_lons), max(all_lons)
    min_lat, max_lat = min(all_lats), max(all_lats)
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0

    print("\n" + "="*80)
    print("           REPROJECTED TREE DATASET COORDINATE VALIDATION")
    print("="*80)
    print(f"Total Trees:       {len(reprojected_trees['features'])}")
    print(f"Longitude Bounds:  [{min_lon:.6f}, {max_lon:.6f}] (Center: {center_lon:.6f})")
    print(f"Latitude Bounds:   [{min_lat:.6f}, {max_lat:.6f}] (Center: {center_lat:.6f})")
    print(f"Target Check:      Florida OSBS ~lat 29.685, lon -81.96")

    # Sanity check
    if not (29.0 < min_lat < 30.5 and -83.0 < min_lon < -80.0):
        print("\nERROR: Coordinates do not match Florida WGS84 range!")
        exit(1)
    else:
        print("CONFIRMED: Coordinates successfully reprojected to WGS84 Florida OSBS study area!")
    print("="*80)


if __name__ == "__main__":
    main()
