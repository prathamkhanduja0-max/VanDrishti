"""
generate_canopy_route_clean.py
Generates a minimal, elegant 2-panel stacked visualization:
- Top: Binary Canopy Mask (Black = Canopy, White = Open Ground) + Clean Cyan Route
- Bottom: High-Resolution RGB Satellite Image + Clean Red Route
Minimalist design: small solid stop markers, no per-stop text labels, subtle corridor outline.
"""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from PIL import Image


def run():
    project_root = Path("C:/VanDrishtiProject")
    tif_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    route_geojson_path = project_root / "results" / "gis" / "OSBS_large_2019_field_route_lcp_optimized.geojson"
    prio_geojson_path = project_root / "results" / "gis" / "OSBS_large_2019_verification_priority.geojson"
    boundary_geojson_path = project_root / "results" / "gis" / "OSBS_large_2019_boundary.geojson"
    gis_dir = project_root / "results" / "gis"

    out_clean_png = gis_dir / "OSBS_large_2019_route_clean.png"

    # 1. Load GeoTIFF raster
    print("Loading base raster GeoTIFF...")
    img = Image.open(tif_path)
    rgb = np.array(img.convert("RGB"))  # Shape: (2500, 2500, 3)

    # Geographic bounds (250m x 250m, EPSG:32617)
    left, right = 407700.0, 407950.0
    bottom, top = 3283750.0, 3284000.0
    extent = [left, right, bottom, top]

    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)

    # 2. Compute Binary Canopy Mask
    exg = 2.0 * g - r - b
    canopy_bool = (exg > 15.0) & (g > 30.0)
    canopy_pct = float(np.mean(canopy_bool) * 100.0)
    open_pct = 100.0 - canopy_pct
    print(f"Canopy: {canopy_pct:.1f}% | Open Ground: {open_pct:.1f}%")

    # Binary mask: 0 (black) = canopy, 255 (white) = open walkable ground
    binary_mask = np.where(canopy_bool, 0, 255).astype(np.uint8)

    # 3. Load Vector Layers
    with open(route_geojson_path, "r", encoding="utf-8") as f:
        route_geojson = json.load(f)
    route_props = route_geojson["features"][0]["properties"]
    route_coords = route_geojson["features"][0]["geometry"]["coordinates"]
    total_lcp_dist = route_props["total_physical_distance_meters"]
    rx, ry = zip(*route_coords)

    with open(boundary_geojson_path, "r", encoding="utf-8") as f:
        boundary_geojson = json.load(f)
    boundary_coords = boundary_geojson["features"][0]["geometry"]["coordinates"][0]
    bx, by = zip(*boundary_coords)

    with open(prio_geojson_path, "r", encoding="utf-8") as f:
        prio_geojson = json.load(f)

    high_stops_x = []
    high_stops_y = []
    for feat in prio_geojson["features"]:
        p = feat["properties"]
        if p.get("verification_priority") == "HIGH":
            high_stops_x.append(p["geo_easting"])
            high_stops_y.append(p["geo_northing"])

    entry_x, entry_y = left, bottom

    # 4. Render Minimal Clean 2-Panel Figure
    print("Rendering minimal clean 2-panel figure...")
    fig, axes = plt.subplots(2, 1, figsize=(12, 22), dpi=200)
    plt.subplots_adjust(hspace=0.14, top=0.95, bottom=0.03, left=0.10, right=0.94)

    # -----------------------------------------------------------------
    # Panel A (Top): BINARY CANOPY MASK + CYAN ROUTE
    # -----------------------------------------------------------------
    ax1 = axes[0]
    ax1.imshow(binary_mask, extent=extent, origin="upper", cmap="gray", vmin=0, vmax=255)

    # Subtle corridor outline
    ax1.plot(bx, by, color="#FF0055", linewidth=1.4, linestyle="--", alpha=0.85, label="Corridor Boundary")

    # Clean bright Cyan route
    ax1.plot(rx, ry, color="#00E5FF", linewidth=2.8, linestyle="-", label=f"Optimized Route ({total_lcp_dist:.0f}m)", zorder=4)

    # 13 High-priority stops (small solid dots)
    ax1.scatter(
        high_stops_x, high_stops_y,
        color="#FFD600", edgecolor="#D50000", linewidth=1.2, s=55,
        zorder=5, label=f"High-Priority Stops (n={len(high_stops_x)})"
    )

    # Ranger Entry Point (distinct small square with tiny 'Start' label)
    ax1.scatter([entry_x], [entry_y], color="#00E5FF", edgecolor="black", s=90, marker="s", linewidth=1.2, zorder=6, label="Start Point")
    ax1.annotate("Start", (entry_x, entry_y), textcoords="offset points", xytext=(8, 6),
                 color="black", fontweight="bold", fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.2", fc="#00E5FF", alpha=0.9, ec="none"), zorder=7)

    ax1.set_title(
        f"Canopy Mask (Black: Canopy {canopy_pct:.0f}%, White: Open {open_pct:.0f}%) — Least-Cost Verification Route",
        fontsize=12, fontweight="bold", pad=10
    )
    ax1.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=9.5)
    ax1.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=9.5)
    ax1.set_xlim(left, right)
    ax1.set_ylim(bottom, top)
    ax1.xaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
    ax1.yaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
    ax1.grid(True, linestyle=":", alpha=0.25, color="gray")
    ax1.legend(loc="upper left", framealpha=0.9, fontsize=9)

    # -----------------------------------------------------------------
    # Panel B (Bottom): RGB SATELLITE + RED ROUTE
    # -----------------------------------------------------------------
    ax2 = axes[1]
    ax2.imshow(rgb, extent=extent, origin="upper")

    # Subtle corridor outline
    ax2.plot(bx, by, color="#FFEA00", linewidth=1.4, linestyle="--", alpha=0.9, label="Corridor Boundary")

    # Clean bright Red route
    ax2.plot(rx, ry, color="#FF1744", linewidth=2.8, linestyle="-", label=f"Optimized Route ({total_lcp_dist:.0f}m)", zorder=4)

    # 13 High-priority stops (small solid cyan dots on satellite for contrast)
    ax2.scatter(
        high_stops_x, high_stops_y,
        color="#00E5FF", edgecolor="black", linewidth=1.0, s=55,
        zorder=5, label=f"High-Priority Stops (n={len(high_stops_x)})"
    )

    # Ranger Entry Point
    ax2.scatter([entry_x], [entry_y], color="#FF1744", edgecolor="white", s=90, marker="s", linewidth=1.2, zorder=6, label="Start Point")
    ax2.annotate("Start", (entry_x, entry_y), textcoords="offset points", xytext=(8, 6),
                 color="white", fontweight="bold", fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.2", fc="#FF1744", alpha=0.9, ec="none"), zorder=7)

    ax2.set_title(
        "RGB Orthomosaic (NEON 10 cm/px) — Field Trajectory through Natural Gaps",
        fontsize=12, fontweight="bold", pad=10
    )
    ax2.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=9.5)
    ax2.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=9.5)
    ax2.set_xlim(left, right)
    ax2.set_ylim(bottom, top)
    ax2.xaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
    ax2.yaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
    ax2.grid(True, linestyle=":", alpha=0.25, color="white")
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9)

    plt.savefig(out_clean_png, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved minimal clean figure to: {out_clean_png}")


if __name__ == "__main__":
    run()
