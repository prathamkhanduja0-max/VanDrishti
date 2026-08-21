"""
run_pipeline_large_study_area.py
Full clean GIS, Priority, and Dijkstra routing pipeline for the 250m OSBS Large 2019 Study Area.
"""

import math
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Polygon, LineString, Point


def run_full_pipeline():
    project_root = Path(__file__).resolve().parent.parent
    tif_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    raw_trees_geojson = project_root / "results" / "gis" / "OSBS_large_2019_trees.geojson"
    gis_dir = project_root / "results" / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    out_filtered_geojson = gis_dir / "OSBS_large_2019_trees_filtered.geojson"
    out_boundary_geojson = gis_dir / "OSBS_large_2019_boundary.geojson"
    out_trees_boundary_geojson = gis_dir / "OSBS_large_2019_trees_with_boundary_status.geojson"
    out_priority_geojson = gis_dir / "OSBS_large_2019_verification_priority.geojson"
    out_route_geojson = gis_dir / "OSBS_large_2019_field_route_lcp.geojson"
    out_overview_map = gis_dir / "OSBS_large_2019_overview_map.png"

    # =========================================================================
    # STEP 0: Load Base Raster
    # =========================================================================
    print("=== STEP 0: Loading 250m Base GeoTIFF ===")
    with rasterio.open(tif_path) as ds:
        raster_crs = ds.crs
        bounds = ds.bounds
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])

    rgb_display = np.transpose(rgb_data, (1, 2, 0))
    if rgb_display.max() > 1.0:
        rgb_display = rgb_display.astype(np.uint8)

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom
    print(f"CRS:        {raster_crs}")
    print(f"Bounds:     {bounds}")
    print(f"Dimensions: {orig_w}x{orig_h} px | {width_m:.1f}m x {height_m:.1f}m")

    # =========================================================================
    # STEP 1: Filter to Reliable Trees (Confidence >= 0.50)
    # =========================================================================
    print("\n=== STEP 1: Filtering Reliable Trees (Confidence >= 0.50) ===")
    gdf_raw = gpd.read_file(raw_trees_geojson)
    total_raw_trees = len(gdf_raw)
    gdf_filtered = gdf_raw[gdf_raw["confidence"] >= 0.50].copy().reset_index(drop=True)
    total_filtered_trees = len(gdf_filtered)
    
    gdf_filtered.to_file(out_filtered_geojson, driver="GeoJSON")
    print(f"Raw Trees:      {total_raw_trees}")
    print(f"Filtered Trees: {total_filtered_trees} (Confidence >= 0.50)")
    print(f"Saved:          {out_filtered_geojson.name}")

    # =========================================================================
    # STEP 2: Project Boundary Corridor (24% of Tile Area) & Tagging
    # =========================================================================
    print("\n=== STEP 2: Creating Synthetic Project Corridor & Spatial Tagging ===")
    # Diagonal corridor polygon across the middle of the 250m tile
    corridor_poly = Polygon([
        (407700.0, 3283800.0),
        (407700.0, 3283860.0),
        (407950.0, 3283960.0),
        (407950.0, 3283900.0),
    ])
    corridor_area = corridor_poly.area
    tile_area = width_m * height_m
    coverage_pct = (corridor_area / tile_area) * 100.0

    gdf_boundary = gpd.GeoDataFrame(
        [{
            "name": "OSBS Large 2019 Infrastructure Corridor",
            "area_sq_m": round(corridor_area, 2),
            "tile_coverage_pct": round(coverage_pct, 2),
        }],
        geometry=[corridor_poly],
        crs=raster_crs
    )
    gdf_boundary.to_file(out_boundary_geojson, driver="GeoJSON")
    print(f"Corridor Area:  {corridor_area:.1f} m^2 ({coverage_pct:.1f}% of study area)")
    print(f"Saved:          {out_boundary_geojson.name}")

    # Tag filtered trees inside/outside
    gdf_filtered["inside_boundary"] = gdf_filtered.geometry.within(corridor_poly)
    gdf_filtered.to_file(out_trees_boundary_geojson, driver="GeoJSON")
    
    inside_count = int(gdf_filtered["inside_boundary"].sum())
    outside_count = total_filtered_trees - inside_count
    print(f"Trees Inside Corridor:  {inside_count}")
    print(f"Trees Outside Corridor: {outside_count}")
    print(f"Saved:                  {out_trees_boundary_geojson.name}")

    # =========================================================================
    # STEP 3: Verification Priority Assignment
    # =========================================================================
    print("\n=== STEP 3: Assigning Verification Priority ===")
    # Reusing OSBS_022 logic with calibrated threshold for ~8-15 clean HIGH priority stops
    # Inside corridor + confidence <= 0.515 -> HIGH (13 trees)
    # Inside corridor (higher confidence) OR outside corridor (moderate confidence <= 0.60) -> MEDIUM
    # Outside corridor + confidence > 0.60 -> LOW
    def determine_priority(row):
        conf = row["confidence"]
        inside = row["inside_boundary"]
        
        if inside and conf <= 0.515:
            return pd.Series([
                "HIGH",
                "Inside project corridor (corridor impact) & Low-tier confidence (mandatory ground audit)"
            ], index=["verification_priority", "priority_reason"])
        elif inside:
            return pd.Series([
                "MEDIUM",
                f"Inside project corridor (corridor impact, statutory check) [Conf: {conf:.1%}]"
            ], index=["verification_priority", "priority_reason"])
        elif conf <= 0.60:
            return pd.Series([
                "MEDIUM",
                f"Outside corridor with moderate confidence [Conf: {conf:.1%}]"
            ], index=["verification_priority", "priority_reason"])
        else:
            return pd.Series([
                "LOW",
                f"Outside corridor with high confidence (safe canopy) [Conf: {conf:.1%}]"
            ], index=["verification_priority", "priority_reason"])

    prio_df = gdf_filtered.apply(determine_priority, axis=1)
    gdf_filtered["verification_priority"] = prio_df["verification_priority"]
    gdf_filtered["priority_reason"] = prio_df["priority_reason"]
    gdf_filtered["priority_rank"] = gdf_filtered["verification_priority"].map({"HIGH": 1, "MEDIUM": 2, "LOW": 3})

    gdf_filtered.to_file(out_priority_geojson, driver="GeoJSON")
    print(f"Saved: {out_priority_geojson.name}")

    prio_counts = gdf_filtered["verification_priority"].value_counts()
    high_count = prio_counts.get("HIGH", 0)
    med_count = prio_counts.get("MEDIUM", 0)
    low_count = prio_counts.get("LOW", 0)
    print(f"HIGH Priority Trees:   {high_count}")
    print(f"MEDIUM Priority Trees: {med_count}")
    print(f"LOW Priority Trees:    {low_count}")

    # =========================================================================
    # STEP 4: Terrain-Aware Dijkstra Least-Cost Path (LCP) Field Route
    # =========================================================================
    print("\n=== STEP 4: Terrain-Aware Dijkstra Least-Cost Path Routing ===")
    grid_h, grid_w = 250, 250
    cell_size_x = width_m / grid_w  # 1.0 m
    cell_size_y = height_m / grid_h  # 1.0 m
    cell_size = (cell_size_x + cell_size_y) / 2.0  # 1.0 m
    print(f"Cost Surface Discretization: {grid_w}x{grid_h} grid | Cell Size: {cell_size:.2f}m x {cell_size:.2f}m")

    # Downsample RGB from 2500x2500 to 250x250 via 10x10 block averaging
    rgb_float = rgb_data.astype(np.float64)
    rgb_down = rgb_float.reshape(3, grid_h, 10, grid_w, 10).mean(axis=(2, 4))
    r_ch, g_ch, b_ch = rgb_down[0], rgb_down[1], rgb_down[2]

    # Excess Green Index (ExG = 2G - R - B)
    exg = 2.0 * g_ch - r_ch - b_ch
    p1, p99 = np.percentile(exg, 1), np.percentile(exg, 99)
    exg_norm = np.clip((exg - p1) / (p99 - p1 + 1e-6), 0.0, 1.0)
    cost_surface = 1.0 + 4.0 * exg_norm
    print(f"Cost Surface: Min={cost_surface.min():.2f}, Max={cost_surface.max():.2f}, Mean={cost_surface.mean():.2f}")

    def utm_to_grid(x, y):
        c = int(np.clip((x - bounds.left) / cell_size_x, 0, grid_w - 1))
        r = int(np.clip((bounds.top - y) / cell_size_y, 0, grid_h - 1))
        return (r, c)

    def grid_to_utm(r, c):
        x = bounds.left + (c + 0.5) * cell_size_x
        y = bounds.top - (r + 0.5) * cell_size_y
        return (x, y)

    # 8-connected grid graph
    G = nx.Graph()
    edges = []
    SQRT2 = math.sqrt(2.0)
    for r in range(grid_h):
        for c in range(grid_w):
            u = (r, c)
            c_u = cost_surface[r, c]
            if c + 1 < grid_w:
                w = cell_size * (c_u + cost_surface[r, c + 1]) / 2.0
                edges.append((u, (r, c + 1), w))
            if r + 1 < grid_h:
                w = cell_size * (c_u + cost_surface[r + 1, c]) / 2.0
                edges.append((u, (r + 1, c), w))
                if c + 1 < grid_w:
                    w = cell_size * SQRT2 * (c_u + cost_surface[r + 1, c + 1]) / 2.0
                    edges.append((u, (r + 1, c + 1), w))
                if c - 1 >= 0:
                    w = cell_size * SQRT2 * (c_u + cost_surface[r + 1, c - 1]) / 2.0
                    edges.append((u, (r + 1, c - 1), w))

    G.add_weighted_edges_from(edges)
    print(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Ranger Entry Point (Bottom-Left Corner)
    entry_x, entry_y = bounds.left, bounds.bottom
    entry_grid = utm_to_grid(entry_x, entry_y)

    gdf_high = gdf_filtered[gdf_filtered["verification_priority"] == "HIGH"].copy().reset_index(drop=True)
    
    waypoint_nodes = {"ENTRY": entry_grid}
    waypoint_info = {
        "ENTRY": {
            "name": "Ranger Base / Entry Point",
            "tree_id": 0,
            "utm": (entry_x, entry_y),
            "grid": entry_grid,
            "conf": 1.0
        }
    }

    for _, row in gdf_high.iterrows():
        t_id = row["tree_id"]
        node_id = f"T{t_id}"
        gx, gy = row["geo_easting"], row["geo_northing"]
        t_grid = utm_to_grid(gx, gy)
        waypoint_nodes[node_id] = t_grid
        waypoint_info[node_id] = {
            "name": f"Tree #{t_id}",
            "tree_id": t_id,
            "utm": (gx, gy),
            "grid": t_grid,
            "conf": row["confidence"]
        }

    # Dijkstra distance matrix
    wp_keys = list(waypoint_nodes.keys())
    dijkstra_matrix = {u: {} for u in wp_keys}
    for u in wp_keys:
        for v in wp_keys:
            if u == v:
                dijkstra_matrix[u][v] = 0.0
            else:
                dijkstra_matrix[u][v] = nx.dijkstra_path_length(
                    G, waypoint_nodes[u], waypoint_nodes[v], weight="weight"
                )

    # Nearest-Neighbor visiting sequence
    unvisited = set(wp_keys)
    unvisited.remove("ENTRY")
    current_wp = "ENTRY"
    route_sequence = ["ENTRY"]
    stitched_utm_coords = []
    total_physical_dist_m = 0.0
    total_weighted_cost = 0.0
    legs_info = []

    step_idx = 1
    while unvisited:
        next_wp = min(unvisited, key=lambda target: dijkstra_matrix[current_wp][target])
        weighted_cost = dijkstra_matrix[current_wp][next_wp]

        cell_path = nx.dijkstra_path(
            G, waypoint_nodes[current_wp], waypoint_nodes[next_wp], weight="weight"
        )
        leg_utm_coords = [grid_to_utm(r, c) for (r, c) in cell_path]
        leg_phys_dist = sum(
            math.hypot(leg_utm_coords[i+1][0] - leg_utm_coords[i][0], leg_utm_coords[i+1][1] - leg_utm_coords[i][1])
            for i in range(len(leg_utm_coords) - 1)
        )

        total_physical_dist_m += leg_phys_dist
        total_weighted_cost += weighted_cost

        if not stitched_utm_coords:
            stitched_utm_coords.extend(leg_utm_coords)
        else:
            stitched_utm_coords.extend(leg_utm_coords[1:])

        legs_info.append({
            "leg": step_idx,
            "from_node": current_wp,
            "to_node": next_wp,
            "from_name": waypoint_info[current_wp]["name"],
            "to_name": waypoint_info[next_wp]["name"],
            "grid_steps": len(cell_path),
            "physical_dist_m": round(leg_phys_dist, 2),
            "cumulative_phys_dist_m": round(total_physical_dist_m, 2),
            "weighted_cost": round(weighted_cost, 2),
        })

        route_sequence.append(next_wp)
        unvisited.remove(next_wp)
        current_wp = next_wp
        step_idx += 1

    # Save LineString GeoJSON
    route_line_geom = LineString(stitched_utm_coords)
    gdf_route = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS Large 2019 Dijkstra Least-Cost Path",
            "study_area": "250m x 250m (6.25 ha)",
            "total_physical_distance_meters": round(total_physical_dist_m, 2),
            "total_least_cost_score": round(total_weighted_cost, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in route_sequence]),
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
            "cost_surface_model": "ExG (2G-R-B) canopy impedance scaled to [1.0, 5.0]",
        }],
        geometry=[route_line_geom],
        crs=raster_crs
    )
    gdf_route.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Total Dijkstra LCP Distance: {total_physical_dist_m:.2f} m across {len(gdf_high)} stops")
    print(f"Saved:                       {out_route_geojson.name}")

    # =========================================================================
    # STEP 5: Overview Map Visualization
    # =========================================================================
    print("\n=== STEP 5: Generating High-Resolution Overview Map ===")
    fig, ax = plt.subplots(figsize=(14, 14), dpi=200)
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]

    # A. Base RGB image
    ax.imshow(rgb_display, extent=extent, origin="upper")

    # B. Semi-transparent Walkability Cost Heatmap
    cost_heatmap = ax.imshow(
        cost_surface,
        extent=extent,
        origin="upper",
        cmap="YlGn_r",
        alpha=0.25,
        vmin=1.0,
        vmax=5.0
    )
    cbar = plt.colorbar(cost_heatmap, ax=ax, fraction=0.032, pad=0.02)
    cbar.set_label("Walkability Impedance (1.0 = Open Bare Ground, 5.0 = Dense Canopy)", fontsize=10)

    # C. Project Boundary Corridor
    gdf_boundary.boundary.plot(
        ax=ax, color="red", linewidth=2.5, linestyle="--", label="Project Corridor (24% Tile Area)"
    )
    gdf_boundary.plot(ax=ax, facecolor="red", alpha=0.10)

    # D. Filtered Trees by Priority
    gdf_low_p = gdf_filtered[gdf_filtered["verification_priority"] == "LOW"]
    gdf_med_p = gdf_filtered[gdf_filtered["verification_priority"] == "MEDIUM"]

    if not gdf_low_p.empty:
        gdf_low_p.plot(
            ax=ax,
            color="#55a630",
            edgecolor="darkgreen",
            markersize=30,
            linewidth=0.5,
            marker="o",
            alpha=0.65,
            label=f"LOW Priority (Safe / High Conf, n={len(gdf_low_p)})",
            zorder=3
        )

    if not gdf_med_p.empty:
        gdf_med_p.plot(
            ax=ax,
            color="#ffb703",
            edgecolor="#d48b00",
            markersize=45,
            linewidth=0.8,
            marker="o",
            alpha=0.75,
            label=f"MEDIUM Priority (Corridor Check / Moderate Conf, n={len(gdf_med_p)})",
            zorder=4
        )

    # E. Dijkstra Least-Cost Path
    xs, ys = zip(*stitched_utm_coords)
    ax.plot(
        xs,
        ys,
        color="cyan",
        linewidth=3.0,
        linestyle="-",
        label=f"Dijkstra Least-Cost Route ({total_physical_dist_m:.1f} m)",
        zorder=5
    )

    # F. Directional Arrows along the Route
    n_pts = len(stitched_utm_coords)
    for frac in [0.08, 0.20, 0.35, 0.50, 0.65, 0.80, 0.92]:
        idx = int(n_pts * frac)
        if idx < n_pts - 1:
            x1, y1 = stitched_utm_coords[idx]
            x2, y2 = stitched_utm_coords[idx + 1]
            dx, dy = x2 - x1, y2 - y1
            if math.hypot(dx, dy) > 1e-4:
                ax.annotate(
                    "",
                    xy=(x2, y2),
                    xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", color="#00ffff", lw=2.2, mutation_scale=14),
                    zorder=6
                )

    # G. Ranger Entry Point
    ax.scatter(
        [entry_x],
        [entry_y],
        color="deepskyblue",
        edgecolor="black",
        s=280,
        marker="s",
        linewidth=2.2,
        label="Ranger Entry Point (Start)",
        zorder=7
    )
    ax.annotate(
        "RANGER ENTRY (START)",
        (entry_x, entry_y),
        textcoords="offset points",
        xytext=(8, 8),
        color="black",
        fontweight="bold",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", fc="deepskyblue", alpha=0.92, ec="black"),
        zorder=8
    )

    # H. Numbered HIGH Priority Stops
    for stop_num, node_id in enumerate(route_sequence[1:], 1):
        gx, gy = waypoint_info[node_id]["utm"]
        t_id = waypoint_info[node_id]["tree_id"]
        conf = waypoint_info[node_id]["conf"]

        ax.scatter(
            [gx],
            [gy],
            color="#ffe600",
            edgecolor="red",
            s=180,
            linewidth=2.2,
            marker="o",
            zorder=7
        )
        ax.annotate(
            f"STOP {stop_num}: T{t_id}\n({conf:.1%})",
            (gx, gy),
            textcoords="offset points",
            xytext=(7, 7),
            color="white",
            fontweight="bold",
            fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.25", fc="red", alpha=0.88, ec="black"),
            zorder=8
        )

    ax.set_title(
        f"VanDrishti: 250m Study Area Overview & Field Verification Route (OSBS Large 2019)\n"
        f"Filtered Trees: {total_filtered_trees} | HIGH Stops: {len(gdf_high)} | LCP Route: {total_physical_dist_m:.1f} m",
        fontsize=13,
        fontweight="bold",
        pad=14
    )
    ax.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=11)
    ax.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=11)
    ax.set_xlim(bounds.left, bounds.right)
    ax.set_ylim(bounds.bottom, bounds.top)
    ax.grid(True, linestyle=":", alpha=0.35, color="white")
    ax.legend(loc="upper left", framealpha=0.92, fontsize=9.5)
    plt.tight_layout()

    plt.savefig(out_overview_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved Overview Map: {out_overview_map.name}")

    # =========================================================================
    # STEP 6: Summary Report
    # =========================================================================
    print("\n" + "="*70)
    print("      VAN-DRISHTI: OSBS LARGE 2019 (250m) PIPELINE REPORT")
    print("="*70)
    print(f"1. Reliable Trees (Confidence >= 0.50): {total_filtered_trees} (from 1,998 raw detections)")
    print(f"2. Corridor Impact Status:")
    print(f"   - Inside Infrastructure Corridor:   {inside_count} trees ({inside_count/total_filtered_trees*100:.1f}%)")
    print(f"   - Outside Corridor (Safe Buffer):   {outside_count} trees ({outside_count/total_filtered_trees*100:.1f}%)")
    print(f"3. Verification Priority Breakdown:")
    print(f"   - HIGH Priority (Audit Targets):    {high_count} trees")
    print(f"   - MEDIUM Priority (Corridor/Mod):   {med_count} trees")
    print(f"   - LOW Priority (Safe / High Conf):  {low_count} trees")
    print(f"4. Terrain-Aware Dijkstra Field Route:")
    print(f"   - Target Audit Stops:               {len(gdf_high)} stops")
    print(f"   - Start Point:                      Ranger Base (407700.0, 3283750.0 UTM)")
    print(f"   - Cost Grid Cell Size:              {cell_size:.2f} m x {cell_size:.2f} m (250x250 cells)")
    print(f"   - Total Least-Cost Path Length:     {total_physical_dist_m:.2f} meters")
    print(f"   - Visiting Sequence:")
    for leg in legs_info:
        print(f"     Leg {leg['leg']:2d}: {leg['from_name']:<25} -> {leg['to_name']:<12} ({leg['physical_dist_m']:6.2f} m, cumulative: {leg['cumulative_phys_dist_m']:6.2f} m)")
    print("="*70)

    return {
        "filtered_trees": total_filtered_trees,
        "inside_count": inside_count,
        "outside_count": outside_count,
        "high_count": high_count,
        "med_count": med_count,
        "low_count": low_count,
        "stops_count": len(gdf_high),
        "lcp_distance_m": total_physical_dist_m,
        "cell_size_m": cell_size,
        "overview_map": str(out_overview_map)
    }


if __name__ == "__main__":
    run_full_pipeline()
