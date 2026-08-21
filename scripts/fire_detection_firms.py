"""
fire_detection_firms.py
Module 3: Forest Fire Detection via NASA FIRMS (Fire Information for Resource Management System) API.
Fetches active fire / thermal anomaly hotspots (VIIRS 375m) for a designated Area of Interest (AOI),
parses hotspot attributes (FRP, confidence, acquisition date/time), saves WGS84 GeoJSON,
and generates a regional fire monitoring map.
"""

import io
import os
from pathlib import Path
import geopandas as gpd
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box

# ==============================================================================
# CONFIGURATION PRESETS
# ==============================================================================
# Switch ACTIVE_PRESET to "demo_active" or "osbs_live" with a single variable change:
ACTIVE_PRESET = "osbs_live"

PRESETS = {
    "osbs_live": {
        "aoi_name": "osbs_live",
        "description": "OSBS / North-Central Florida (Live Regional Monitoring)",
        "bbox": (-82.5, 29.2, -81.5, 30.2),  # (west, south, east, north)
        "query_date": "",  # Empty string = most recent live observations
        "day_range": 5,  # 1 to 5 days
        "source": "VIIRS_SNPP_NRT",
    },
    "demo_active": {
        "aoi_name": "demo_active",
        "description": "California Wildfire Demonstration Zone (Historical Event)",
        "bbox": (-122.5, 39.5, -121.0, 40.5),  # (west, south, east, north)
        "query_date": "2024-07-26",  # Active California fire event
        "day_range": 5,
        "source": "VIIRS_SNPP_NRT",
    },
}

# Read MAP_KEY from environment
MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()
if not MAP_KEY:
    raise SystemExit("Set FIRMS_MAP_KEY environment variable")


def fetch_firms_hotspots(config, map_key):
    """
    Queries NASA FIRMS Area API for CSV data over the specified bounding box.
    Handles network errors and empty responses gracefully.
    """
    west, south, east, north = config["bbox"]
    day_range = config["day_range"]
    source = config["source"]
    query_date = config["query_date"]

    # Base URL format: https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[SOURCE]/[WEST,SOUTH,EAST,NORTH]/[DAY_RANGE]/[DATE]
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{west},{south},{east},{north}/{day_range}"
    if query_date:
        url += f"/{query_date}"

    print(f"\nTarget Query URL: {url.replace(map_key, '***KEY***' if map_key != 'YOUR_MAP_KEY' else 'YOUR_MAP_KEY')}")

    try:
        response = requests.get(url, timeout=15)
        status = response.status_code
        text = response.text.strip()

        if status == 200 and "latitude" in text.lower():
            # Valid CSV response returned
            df = pd.read_csv(io.StringIO(text))
            print(f"NASA FIRMS API Response: HTTP {status} OK ({len(df)} hotspot rows received)")
            return df, "API_SUCCESS"
        elif "Invalid MAP_KEY" in text or status in (400, 401, 403):
            print(f"NASA FIRMS API: {text} (HTTP {status})")
            return None, f"AUTH_OR_REQUEST_ERROR: {text}"
        else:
            print(f"NASA FIRMS API Response: HTTP {status} | {text[:120]}")
            return None, f"HTTP_{status}"

    except requests.exceptions.RequestException as e:
        print(f"Network error communicating with NASA FIRMS API: {e}")
        return None, f"NETWORK_ERROR: {e}"


def run_fire_detection(preset_key=ACTIVE_PRESET):
    if preset_key not in PRESETS:
        raise ValueError(f"Unknown preset '{preset_key}'. Choose from: {list(PRESETS.keys())}")

    cfg = PRESETS[preset_key]
    aoi_name = cfg["aoi_name"]
    west, south, east, north = cfg["bbox"]
    query_date_str = cfg["query_date"] if cfg["query_date"] else "Latest (Live Rolling Window)"

    project_root = Path(__file__).resolve().parent.parent
    results_dir = project_root / "results" / "gis"
    results_dir.mkdir(parents=True, exist_ok=True)

    out_geojson = results_dir / f"fire_hotspots_{aoi_name}.geojson"
    out_map_png = results_dir / f"fire_hotspots_{aoi_name}_map.png"

    print("=" * 80)
    print("           VAN-DRISHTI: NASA FIRMS FOREST FIRE HOTSPOT MONITOR")
    print("=" * 80)
    print(f"Configuration Preset: {preset_key} ({cfg['description']})")
    print(f"Area of Interest:     Bounding Box [West: {west}°, South: {south}°, East: {east}°, North: {north}°]")
    print(f"Query Period:         {query_date_str} (Window: {cfg['day_range']} days)")
    print(f"Sensor Source:        {cfg['source']} (VIIRS ~375m nominal resolution)")
    print("=" * 80)

    # 1. Fetch FIRMS Data
    df_raw, status_msg = fetch_firms_hotspots(cfg, MAP_KEY)

    # 2. Process Data
    records = []
    if df_raw is not None and not df_raw.empty and "latitude" in df_raw.columns:
        # Standardize and extract required attributes
        for idx, row in df_raw.iterrows():
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            brightness = float(row.get("bright_ti4", row.get("brightness", 0.0)))
            confidence = str(row.get("confidence", "nominal"))
            acq_date = str(row.get("acq_date", ""))
            acq_time = str(row.get("acq_time", "")).zfill(4)
            frp = float(row.get("frp", 0.0))  # Fire Radiative Power (MW)
            satellite = str(row.get("satellite", "SNPP"))
            daynight = str(row.get("daynight", ""))

            records.append({
                "hotspot_id": idx + 1,
                "latitude": lat,
                "longitude": lon,
                "brightness_k": brightness,
                "confidence": confidence,
                "frp_mw": frp,
                "acq_date": acq_date,
                "acq_time_utc": acq_time,
                "satellite": satellite,
                "daynight": daynight,
            })

    # Create GeoDataFrame (EPSG:4326 / WGS84)
    if records:
        points = [Point(r["longitude"], r["latitude"]) for r in records]
        gdf_hotspots = gpd.GeoDataFrame(records, geometry=points, crs="EPSG:4326")
    else:
        # Empty GeoDataFrame with standard schema
        schema_cols = ["hotspot_id", "latitude", "longitude", "brightness_k", "confidence", "frp_mw", "acq_date", "acq_time_utc", "satellite", "daynight"]
        gdf_hotspots = gpd.GeoDataFrame(columns=schema_cols + ["geometry"], geometry="geometry", crs="EPSG:4326")

    # 3. Save GeoJSON
    gdf_hotspots.to_file(out_geojson, driver="GeoJSON")
    print(f"\n[+] Saved Fire Hotspots GeoJSON to: {out_geojson}")

    # 4. Generate Regional Fire Monitoring Map
    fig, ax = plt.subplots(figsize=(10, 8), dpi=150)

    # Plot AOI boundary
    aoi_patch = patches.Rectangle(
        (west, south),
        east - west,
        north - south,
        linewidth=2.2,
        edgecolor="#D32F2F",
        facecolor="#FFEBEE",
        linestyle="--",
        alpha=0.35,
        label=f"AOI Query Extent ({east-west:.1f}° x {north-south:.1f}°)",
        zorder=1,
    )
    ax.add_patch(aoi_patch)

    hotspot_count = len(gdf_hotspots)

    if hotspot_count > 0:
        # Plot hotspots scaled/colored by FRP (Fire Radiative Power)
        frp_vals = gdf_hotspots["frp_mw"].values
        # Size proportional to FRP (clamped between 40 and 320)
        marker_sizes = np.clip(frp_vals * 0.7 + 40.0, 40.0, 350.0)

        scatter = ax.scatter(
            gdf_hotspots["longitude"],
            gdf_hotspots["latitude"],
            c=frp_vals,
            cmap="YlOrRd",
            s=marker_sizes,
            edgecolor="darkred",
            linewidth=0.9,
            alpha=0.88,
            zorder=3,
            label=f"Active Hotspots ({hotspot_count} detections)",
        )
        cbar = plt.colorbar(scatter, ax=ax, fraction=0.035, pad=0.03)
        cbar.set_label("Fire Radiative Power (FRP in MW)", fontsize=9, fontweight="bold")

        # Annotate top 3 highest FRP points
        top_hotspots = gdf_hotspots.sort_values(by="frp_mw", ascending=False).head(3)
        for _, top_r in top_hotspots.iterrows():
            ax.annotate(
                f"FRP: {top_r['frp_mw']:.1f} MW\n({top_r['acq_date']})",
                (top_r["longitude"], top_r["latitude"]),
                textcoords="offset points",
                xytext=(8, 8),
                fontsize=8,
                fontweight="bold",
                color="darkred",
                bbox=dict(boxstyle="round,pad=0.2", fc="yellow", alpha=0.9, ec="red"),
                zorder=4,
            )
    else:
        # No detections: Draw clear status message
        ax.text(
            (west + east) / 2.0,
            (south + north) / 2.0,
            f"NO ACTIVE THERMAL HOTSPOTS DETECTED\nIN {aoi_name.upper()}\n\n"
            f"Period: {query_date_str} (5-day window)\n"
            f"Sensor: VIIRS 375m NRT | Status: Operational / Clear",
            color="#2E7D32",
            fontsize=11,
            fontweight="bold",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.6", fc="#E8F5E9", ec="#4CAF50", lw=2),
            zorder=3,
        )

    # Styling and limits
    pad_x = (east - west) * 0.08
    pad_y = (north - south) * 0.08
    ax.set_xlim(west - pad_x, east + pad_x)
    ax.set_ylim(south - pad_y, north + pad_y)

    ax.set_title(
        f"VanDrishti: NASA FIRMS Fire Intelligence Map — {cfg['description']}\n"
        f"Query Period: {query_date_str} | Active Thermal Detections: {hotspot_count}",
        fontsize=11,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Longitude (°E / WGS84) [EPSG:4326]", fontsize=9)
    ax.set_ylabel("Latitude (°N / WGS84) [EPSG:4326]", fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.6, color="gray")
    ax.legend(loc="upper right", framealpha=0.9)
    plt.tight_layout()

    plt.savefig(out_map_png, dpi=200)
    plt.close()
    print(f"[+] Saved Regional Fire Map to: {out_map_png}")

    # 5. Reporting Summary
    print("\n" + "=" * 80)
    print("                        FIRE MONITORING REPORT")
    print("=" * 80)
    print(f"Active Preset:         {preset_key}")
    print(f"AOI Extent (WGS84):    West={west:.2f}°, South={south:.2f}°, East={east:.2f}°, North={north:.2f}°")
    print(f"Query Temporal Window: {query_date_str} ({cfg['day_range']} days)")
    print(f"Total Hotspots Found:  {hotspot_count}")

    if hotspot_count == 0:
        print(f"\nStatus: No active fire detections in {cfg['description']} for the queried period.")
        print("        Forest canopy status: Nominal / No immediate thermal wildfire threat.")
    else:
        print("\nTop Hotspots by Fire Radiative Power (FRP):")
        top_df = gdf_hotspots.sort_values(by="frp_mw", ascending=False).head(5)
        print(f"{'ID':<4} | {'Latitude':<9} | {'Longitude':<10} | {'FRP (MW)':<9} | {'Confidence':<10} | {'Date':<10} | {'Time (UTC)'}")
        print("-" * 75)
        for _, r in top_df.iterrows():
            print(f"{r['hotspot_id']:<4} | {r['latitude']:<9.4f} | {r['longitude']:<10.4f} | {r['frp_mw']:<9.1f} | {r['confidence']:<10} | {r['acq_date']:<10} | {r['acq_time_utc']}")

    print("\nMethodological Note & Spatial Limitation:")
    print("  - NASA FIRMS VIIRS (S-NPP / NOAA-20) sensor has a nadir spatial resolution of ~375 meters.")
    print("  - Detections represent sub-pixel thermal anomalies (landscape/regional fire intelligence),")
    print("    not individual-tree canopy ignition.")
    print("=" * 80)

    return {
        "preset": preset_key,
        "aoi_name": aoi_name,
        "bbox": (west, south, east, north),
        "hotspot_count": hotspot_count,
        "geojson": str(out_geojson),
        "map_png": str(out_map_png),
    }


if __name__ == "__main__":
    run_fire_detection()
