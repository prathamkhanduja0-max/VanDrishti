"""
run_pipeline_large_study_area.py
Full clean GIS, Priority, and Dijkstra routing pipeline for any configured study area.
Driven entirely by config.yaml via config_loader.py (zero hardcoded paths, coordinates, or CRS).
"""

import math
from pathlib import Path
import sys
from typing import Optional, Union
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import LineString, Point, Polygon, box

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader


def get_corridor_polygon(cfg, bounds):
    """
    Returns corridor polygon supporting both:
      - 'polygon' / 'explicit' mode: coordinates given in config
      - 'auto' mode: generated from bearing, width, and offset relative to tile center.
    """
    corr_cfg = cfg.get("corridor", {})
    mode = corr_cfg.get("mode", "polygon")

    if mode in ("polygon", "explicit") and "polygon_coords" in corr_cfg and corr_cfg["polygon_coords"]:
        coords = [tuple(pt) for pt in corr_cfg["polygon_coords"]]
        return Polygon(coords)

    # auto mode
    auto_cfg = corr_cfg.get("auto", {})
    bearing_deg = float(auto_cfg.get("bearing_deg", 22.0))
    width_m = float(auto_cfg.get("width_m", 60.0))
    offset_m = float(auto_cfg.get("offset_m", 0.0))

    left, bottom, right, top = bounds.left, bounds.bottom, bounds.right, bounds.top
    cx = (left + right) / 2.0
    cy = (bottom + top) / 2.0

    rad = math.radians(bearing_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    nx_norm, ny_norm = -dy, dx

    cx += nx_norm * offset_m
    cy += ny_norm * offset_m

    diag = math.hypot(right - left, top - bottom)
    half_len = diag * 0.75
    half_w = width_m / 2.0

    p1 = (cx - dx * half_len + nx_norm * half_w, cy - dy * half_len + ny_norm * half_w)
    p2 = (cx - dx * half_len - nx_norm * half_w, cy - dy * half_len - ny_norm * half_w)
    p3 = (cx + dx * half_len - nx_norm * half_w, cy + dy * half_len - ny_norm * half_w)
    p4 = (cx + dx * half_len + nx_norm * half_w, cy + dy * half_len - ny_norm * half_w)

    tile_box = box(left, bottom, right, top)
    return Polygon([p1, p2, p3, p4]).intersection(tile_box)


def get_entry_point(cfg, bounds):
    """Returns entry point from config or defaults to bottom-left corner."""
    routing_cfg = cfg.get("routing", {})
    ep = routing_cfg.get("entry_point", "auto")
    if ep == "auto" or not isinstance(ep, (list, tuple)):
        return (bounds.left, bounds.bottom)
    return (float(ep[0]), float(ep[1]))


def run_full_pipeline(config_path: Optional[Union[str, Path]] = None):
    if config_path is None:
        config_path = REPO_ROOT / "config.yaml"
    cfg = config_loader.load(config_path)

    # Startup Capability Assessment
    rasters = config_loader.inspect_rasters(cfg)
    caps = config_loader.assess(rasters)
    for mod in ["detection", "priority", "routing"]:
        if caps.get(mod, {}).get("level") == "BLOCKED":
            missing = ", ".join(caps[mod]["missing"])
            raise RuntimeError(f"Module '{mod}' is BLOCKED due to missing required data: {missing}. Aborting.")

    site_name = cfg.get("site", {}).get("name", "study_area")
    tif_path = cfg.path("site", "rasters", "rgb_t2", required=True)
    raw_trees_geojson = cfg.path("detection", "raw_trees_geojson", required=True)
    gis_dir = cfg.path("outputs", "gis_dir") or (REPO_ROOT / "results" / "gis")
    gis_dir.mkdir(parents=True, exist_ok=True)

    out_filtered_geojson = gis_dir / f"{site_name}_trees_filtered.geojson"
    out_boundary_geojson = gis_dir / f"{site_name}_boundary.geojson"
    out_trees_boundary_geojson = gis_dir / f"{site_name}_trees_with_boundary_status.geojson"
    out_priority_geojson = gis_dir / f"{site_name}_verification_priority.geojson"
    out_route_geojson = gis_dir / f"{site_name}_field_route_lcp.geojson"
    out_overview_map = gis_dir / f"{site_name}_overview_map.png"

    min_conf = float(cfg.get("detection", {}).get("min_conf", 0.50))
    conf_low = float(cfg.get("priority", {}).get("conf_low", 0.515))
    conf_mid = float(cfg.get("priority", {}).get("conf_mid", 0.60))
    w_veg = float(cfg.get("routing", {}).get("w_veg", 4.0))
    grid_res_m = float(cfg.get("routing", {}).get("grid_res_m", 1.0))

    # STEP 0: Load Base Raster
    print(f"=== STEP 0: Loading Study Area Base GeoTIFF ({site_name}) ===")
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

    # STEP 1: Filter to Reliable Trees
    print(f"\n=== STEP 1: Filtering Reliable Trees (Confidence >= {min_conf:.2f}) ===")
    gdf_raw = gpd.read_file(raw_trees_geojson)
    total_raw_trees = len(gdf_raw)
    gdf_filtered = gdf_raw[gdf_raw["confidence"] >= min_conf].copy().reset_index(drop=True)
    total_filtered_trees = len(gdf_filtered)
    
    gdf_filtered.to_file(out_filtered_geojson, driver="GeoJSON")
    print(f"Raw Trees:      {total_raw_trees}")
    print(f"Filtered Trees: {total_filtered_trees} (Confidence >= {min_conf:.2f})")
    print(f"Saved:          {out_filtered_geojson.name}")

    # STEP 2: Project Boundary Corridor & Spatial Tagging
    print("\n=== STEP 2: Building Project Corridor & Spatial Tagging ===")
    corridor_poly = get_corridor_polygon(cfg, bounds)
    corridor_area = corridor_poly.area
    tile_area = width_m * height_m
    coverage_pct = (corridor_area / tile_area) * 100.0

    gdf_boundary = gpd.GeoDataFrame(
        [{
            "name": f"{site_name} Infrastructure Corridor",
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

    # STEP 3: Verification Priority Assignment
    print("\n=== STEP 3: Assigning Verification Priority ===")
    def determine_priority(row):
        conf = row["confidence"]
        inside = row["inside_boundary"]
        
        if inside and conf <= conf_low:
            return pd.Series([
                "HIGH",
                "Inside project corridor (corridor impact) & Low-tier confidence (mandatory ground audit)"
            ], index=["verification_priority", "priority_reason"])
        elif inside:
            return pd.Series([
                "MEDIUM",
                f"Inside project corridor (corridor impact, statutory check) [Conf: {conf:.1%}]"
            ], index=["verification_priority", "priority_reason"])
        elif conf <= conf_mid:
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

    # STEP 4: Dijkstra Least-Cost Path (LCP) Field Route
    print("\n=== STEP 4: Dijkstra Least-Cost Path Routing ===")
    grid_w = int(round(width_m / grid_res_m))
    grid_h = int(round(height_m / grid_res_m))
    cell_size_x = width_m / grid_w
    cell_size_y = height_m / grid_h
    cell_size = (cell_size_x + cell_size_y) / 2.0
    print(f"Cost Surface Discretization: {grid_w}x{grid_h} grid | Cell Size: {cell_size:.2f}m x {cell_size:.2f}m")

    scale_y = orig_h // grid_h
    scale_x = orig_w // grid_w
    rgb_float = rgb_data.astype(np.float64)
    rgb_down = rgb_float[:, :grid_h * scale_y, :grid_w * scale_x].reshape(3, grid_h, scale_y, grid_w, scale_x).mean(axis=(2, 4))
    r_ch, g_ch, b_ch = rgb_down[0], rgb_down[1], rgb_down[2]

    exg = 2.0 * g_ch - r_ch - b_ch
    p1, p99 = np.percentile(exg, 1), np.percentile(exg, 99)
    exg_norm = np.clip((exg - p1) / (p99 - p1 + 1e-6), 0.0, 1.0)
    cost_surface = 1.0 + w_veg * exg_norm

    def utm_to_grid(x, y):
        c = int(np.clip((x - bounds.left) / cell_size_x, 0, grid_w - 1))
        r = int(np.clip((bounds.top - y) / cell_size_y, 0, grid_h - 1))
        return (r, c)

    def grid_to_utm(r, c):
        x = bounds.left + (c + 0.5) * cell_size_x
        y = bounds.top - (r + 0.5) * cell_size_y
        return (x, y)

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

    entry_x, entry_y = get_entry_point(cfg, bounds)
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

    route_line_geom = LineString(stitched_utm_coords)
    gdf_route = gpd.GeoDataFrame(
        [{
            "route_name": f"{site_name} Dijkstra Least-Cost Path",
            "study_area": f"{width_m:.0f}m x {height_m:.0f}m ({tile_area/10000:.2f} ha)",
            "total_physical_distance_meters": round(total_physical_dist_m, 2),
            "total_least_cost_score": round(total_weighted_cost, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in route_sequence]),
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
            "cost_surface_model": f"ExG canopy impedance scaled to [1.0, {1.0+w_veg}]",
        }],
        geometry=[route_line_geom],
        crs=raster_crs
    )
    gdf_route.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Total Dijkstra LCP Distance: {total_physical_dist_m:.2f} m across {len(gdf_high)} stops")
    print(f"Saved:                       {out_route_geojson.name}")

    # STEP 5: Overview Map Visualization
    print("\n=== STEP 5: Generating High-Resolution Overview Map ===")
    fig, ax = plt.subplots(figsize=(14, 14), dpi=200)
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]

    ax.imshow(rgb_display, extent=extent, origin="upper")

    cost_heatmap = ax.imshow(
        cost_surface,
        extent=extent,
        origin="upper",
        cmap="YlGn_r",
        alpha=0.25,
        vmin=1.0,
        vmax=1.0 + w_veg
    )
    cbar = plt.colorbar(cost_heatmap, ax=ax, fraction=0.032, pad=0.02)
    cbar.set_label("Walkability Impedance (1.0 = Open Bare Ground, High = Dense Canopy)", fontsize=10)

    gdf_boundary.boundary.plot(
        ax=ax, color="red", linewidth=2.5, linestyle="--", label=f"Project Corridor ({coverage_pct:.0f}% Tile Area)"
    )
    gdf_boundary.plot(ax=ax, facecolor="red", alpha=0.10)

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
        f"VanDrishti: Study Area Overview & Field Verification Route ({site_name})\n"
        f"Filtered Trees: {total_filtered_trees} | HIGH Stops: {len(gdf_high)} | LCP Route: {total_physical_dist_m:.1f} m",
        fontsize=13,
        fontweight="bold",
        pad=14
    )
    ax.set_xlabel(f"Easting (m) [{raster_crs}]", fontsize=11)
    ax.set_ylabel(f"Northing (m) [{raster_crs}]", fontsize=11)
    ax.set_xlim(bounds.left, bounds.right)
    ax.set_ylim(bounds.bottom, bounds.top)
    ax.grid(True, linestyle=":", alpha=0.35, color="white")
    ax.legend(loc="upper left", framealpha=0.92, fontsize=9.5)
    plt.tight_layout()

    plt.savefig(out_overview_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved Overview Map: {out_overview_map.name}")

    # STEP 6: Summary Report
    print("\n" + "="*70)
    print(f"      VAN-DRISHTI: {site_name.upper()} PIPELINE REPORT")
    print("="*70)
    print(f"1. Reliable Trees (Confidence >= {min_conf:.2f}): {total_filtered_trees} (from {total_raw_trees} raw detections)")
    print(f"2. Corridor Impact Status:")
    print(f"   - Inside Infrastructure Corridor:   {inside_count} trees ({inside_count/total_filtered_trees*100:.1f}%)")
    print(f"   - Outside Corridor (Safe Buffer):   {outside_count} trees ({outside_count/total_filtered_trees*100:.1f}%)")
    print(f"3. Verification Priority Breakdown:")
    print(f"   - HIGH Priority (Audit Targets):    {high_count} trees")
    print(f"   - MEDIUM Priority (Corridor/Mod):   {med_count} trees")
    print(f"   - LOW Priority (Safe / High Conf):  {low_count} trees")
    print(f"4. Dijkstra Field Route:")
    print(f"   - Target Audit Stops:               {len(gdf_high)} stops")
    print(f"   - Start Point:                      Ranger Base ({entry_x:.1f}, {entry_y:.1f})")
    print(f"   - Cost Grid Cell Size:              {cell_size:.2f} m x {cell_size:.2f} m ({grid_w}x{grid_h} cells)")
    print(f"   - Total Least-Cost Path Length:     {total_physical_dist_m:.2f} meters")
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
