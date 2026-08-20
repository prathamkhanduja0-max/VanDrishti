"""
visualize_canopy_route_clean.py
Generates a clean 2-panel visualization:
Panel 1: High-Resolution RGB Orthomosaic + Dijkstra Least-Cost Route
Panel 2: Binary Canopy Mask (Black = Canopy, White = Open Ground) + Route & Stops
"""

import math
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio


def generate_canopy_route_clean():
    project_root = Path("C:/VanDrishtiProject")
    tif_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    route_geojson = project_root / "results" / "gis" / "OSBS_large_2019_field_route_lcp.geojson"
    prio_geojson = project_root / "results" / "gis" / "OSBS_large_2019_verification_priority.geojson"
    boundary_geojson = project_root / "results" / "gis" / "OSBS_large_2019_boundary.geojson"
    gis_dir = project_root / "results" / "gis"

    out_mask_tif = gis_dir / "OSBS_large_2019_canopy_mask_clean.tif"
    out_map_png = gis_dir / "OSBS_large_2019_canopy_route_clean.png"

    # 1. Load GeoTIFF
    print("Loading base raster GeoTIFF...")
    with rasterio.open(tif_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        profile = ds.profile.copy()
        rgb = ds.read([1, 2, 3])

    r = rgb[0].astype(np.float32)
    g = rgb[1].astype(np.float32)
    b = rgb[2].astype(np.float32)

    # 2. Compute Binary Canopy Mask
    # ExG = 2*G - R - B
    exg = 2.0 * g - r - b
    canopy_bool = (exg > 15.0) & (g > 30.0)
    canopy_pct = float(np.mean(canopy_bool) * 100.0)
    open_pct = 100.0 - canopy_pct
    print(f"Canopy Coverage: {canopy_pct:.2f}% | Open Ground: {open_pct:.2f}%")

    # Binary image array: 0 for canopy (black), 255 for open ground (white)
    # Mask array: uint8 where 1 = canopy, 0 = open
    binary_img = np.where(canopy_bool, 0, 255).astype(np.uint8)

    # Save clean mask GeoTIFF
    mask_profile = profile.copy()
    mask_profile.update({
        "count": 1,
        "dtype": "uint8",
        "nodata": None
    })
    with rasterio.open(out_mask_tif, "w", **mask_profile) as dst:
        dst.write(binary_img, 1)
    print(f"Saved binary canopy mask raster to: {out_mask_tif.name}")

    # Prepare RGB array for display
    rgb_display = np.transpose(rgb, (1, 2, 0))
    if rgb_display.max() > 1.0:
        rgb_display = rgb_display.astype(np.uint8)

    # 3. Load Vector Layers
    gdf_route = gpd.read_file(route_geojson)
    gdf_prio = gpd.read_file(prio_geojson)
    gdf_boundary = gpd.read_file(boundary_geojson)

    gdf_high = gdf_prio[gdf_prio["verification_priority"] == "HIGH"].copy()
    route_geom = gdf_route.geometry.iloc[0]
    route_coords = list(route_geom.coords)
    total_lcp_dist = gdf_route.iloc[0]["total_physical_distance_meters"]

    # Order high-priority stops by route visiting sequence
    seq_str = gdf_route.iloc[0]["visiting_sequence"]
    # E.g. "Ranger Base / Entry Point -> Tree #666 -> Tree #646 -> ..."
    stop_names = [s.strip() for s in seq_str.split("->")[1:]] # exclude entry
    ordered_stops = []
    for s_idx, s_name in enumerate(stop_names, 1):
        t_id = int(s_name.replace("Tree #", ""))
        match = gdf_high[gdf_high["tree_id"] == t_id]
        if not match.empty:
            row = match.iloc[0]
            ordered_stops.append({
                "stop_num": s_idx,
                "tree_id": t_id,
                "confidence": row["confidence"],
                "easting": row["geo_easting"],
                "northing": row["geo_northing"]
            })

    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    entry_x, entry_y = bounds.left, bounds.bottom

    # 4. Generate 2-Panel Composite Figure
    print("Generating clean 2-panel visualization...")
    fig, axes = plt.subplots(1, 2, figsize=(24, 12), dpi=200)
    plt.subplots_adjust(wspace=0.10, top=0.88, bottom=0.06, left=0.04, right=0.96)

    # -------------------------------------------------------------
    # Panel 1: RGB Orthomosaic + Route + Stops
    # -------------------------------------------------------------
    ax1 = axes[0]
    ax1.imshow(rgb_display, extent=extent, origin="upper")

    # Corridor Boundary
    gdf_boundary.boundary.plot(ax=ax1, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor (24% Area)")
    gdf_boundary.plot(ax=ax1, facecolor="#FF0055", alpha=0.08)

    # Route Line
    xs, ys = zip(*route_coords)
    ax1.plot(xs, ys, color="#00FFFF", linewidth=3.2, linestyle="-", label=f"Dijkstra Least-Cost Route ({total_lcp_dist:.1f} m)", zorder=5)

    # Directional Arrows on Route
    n_pts = len(route_coords)
    for frac in [0.08, 0.22, 0.38, 0.52, 0.68, 0.82, 0.94]:
        idx = int(n_pts * frac)
        if idx < n_pts - 1:
            x1, y1 = route_coords[idx]
            x2, y2 = route_coords[idx + 1]
            dx, dy = x2 - x1, y2 - y1
            if math.hypot(dx, dy) > 1e-4:
                ax1.annotate(
                    "", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#00FFFF", lw=2.2, mutation_scale=14),
                    zorder=6
                )

    # Ranger Entry Point
    ax1.scatter([entry_x], [entry_y], color="#00B4D8", edgecolor="black", s=280, marker="s", linewidth=2.2, label="Ranger Entry Point (Start)", zorder=7)
    ax1.annotate("RANGER ENTRY (START)", (entry_x, entry_y), textcoords="offset points", xytext=(8, 8),
                 color="black", fontweight="bold", fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.3", fc="#00B4D8", alpha=0.92, ec="black"), zorder=8)

    # Numbered Stops
    for st in ordered_stops:
        gx, gy = st["easting"], st["northing"]
        t_id = st["tree_id"]
        conf = st["confidence"]
        s_num = st["stop_num"]

        ax1.scatter([gx], [gy], color="#FFE600", edgecolor="red", s=190, linewidth=2.2, marker="o", zorder=7)
        ax1.annotate(
            f"STOP {s_num}: T{t_id}\n({conf:.1%})", (gx, gy),
            textcoords="offset points", xytext=(7, 7), color="white", fontweight="bold", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.25", fc="red", alpha=0.88, ec="black"), zorder=8
        )

    ax1.set_title("Panel 1: High-Resolution RGB Orthomosaic\nField Verification Route & 13 Priority Stops", fontsize=13, fontweight="bold", pad=12)
    ax1.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax1.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax1.set_xlim(bounds.left, bounds.right)
    ax1.set_ylim(bounds.bottom, bounds.top)
    ax1.grid(True, linestyle=":", alpha=0.35, color="white")
    ax1.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    # -------------------------------------------------------------
    # Panel 2: Binary Canopy Mask + Route + Stops
    # -------------------------------------------------------------
    ax2 = axes[1]
    ax2.imshow(binary_img, extent=extent, origin="upper", cmap="gray", vmin=0, vmax=255)

    # Corridor Boundary
    gdf_boundary.boundary.plot(ax=ax2, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor")

    # Route Line (Electric Cyan / Green on black/white mask)
    ax2.plot(xs, ys, color="#00E5FF", linewidth=3.2, linestyle="-", label=f"Least-Cost Path ({total_lcp_dist:.1f} m)", zorder=5)

    for frac in [0.08, 0.22, 0.38, 0.52, 0.68, 0.82, 0.94]:
        idx = int(n_pts * frac)
        if idx < n_pts - 1:
            x1, y1 = route_coords[idx]
            x2, y2 = route_coords[idx + 1]
            dx, dy = x2 - x1, y2 - y1
            if math.hypot(dx, dy) > 1e-4:
                ax2.annotate(
                    "", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#00E5FF", lw=2.2, mutation_scale=14),
                    zorder=6
                )

    # Ranger Entry Point
    ax2.scatter([entry_x], [entry_y], color="#00B4D8", edgecolor="black", s=280, marker="s", linewidth=2.2, zorder=7)
    ax2.annotate("RANGER ENTRY (START)", (entry_x, entry_y), textcoords="offset points", xytext=(8, 8),
                 color="black", fontweight="bold", fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.3", fc="#00B4D8", alpha=0.95, ec="black"), zorder=8)

    # Numbered Stops
    for st in ordered_stops:
        gx, gy = st["easting"], st["northing"]
        t_id = st["tree_id"]
        conf = st["confidence"]
        s_num = st["stop_num"]

        ax2.scatter([gx], [gy], color="#FFE600", edgecolor="red", s=190, linewidth=2.2, marker="o", zorder=7)
        ax2.annotate(
            f"STOP {s_num}: T{t_id}\n({conf:.1%})", (gx, gy),
            textcoords="offset points", xytext=(7, 7), color="white", fontweight="bold", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.25", fc="red", alpha=0.90, ec="black"), zorder=8
        )

    ax2.set_title(
        f"Panel 2: Binary Canopy Mask (Black = Canopy {canopy_pct:.1f}%, White = Open Ground {open_pct:.1f}%)\n"
        f"Canopy-Avoiding Least-Cost Path Trajectory",
        fontsize=13,
        fontweight="bold",
        pad=12
    )
    ax2.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax2.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax2.set_xlim(bounds.left, bounds.right)
    ax2.set_ylim(bounds.bottom, bounds.top)
    ax2.grid(True, linestyle=":", alpha=0.35, color="gray")
    ax2.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    fig.suptitle(
        f"VanDrishti: 250m Study Area — Binary Canopy Mask & Terrain-Aware Verification Route\n"
        f"Area: 250m × 250m (6.25 ha) | 13 HIGH-Priority Audit Stops | LCP Route Length: {total_lcp_dist:.1f} m",
        fontsize=15,
        fontweight="bold",
        y=0.96
    )

    plt.savefig(out_map_png, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Successfully generated clean visualization: {out_map_png}")

    return {
        "canopy_pct": canopy_pct,
        "open_pct": open_pct,
        "out_mask_tif": str(out_mask_tif),
        "out_map_png": str(out_map_png)
    }


if __name__ == "__main__":
    generate_canopy_route_clean()
