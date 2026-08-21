"""
run_tsp_optimization_large.py
Solves exact open-path TSP on any configured study area using terrain-aware
cost surface (Tobler's hiking function on DTM slope + normalized CHM canopy impedance).
Driven by config.yaml via config_loader.py. Eliminates backtracking and saves route_terrain.geojson.
"""

import itertools
import math
from pathlib import Path
import sys
from typing import Optional, Union
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
from shapely.geometry import LineString

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import config_loader
from terrain_cost import slope_degrees, tobler_cost


def get_entry_point(cfg, bounds):
    """Returns entry point from config or defaults to bottom-left corner."""
    routing_cfg = cfg.get("routing", {})
    ep = routing_cfg.get("entry_point", "auto")
    if ep == "auto" or not isinstance(ep, (list, tuple)):
        return (bounds.left, bounds.bottom)
    return (float(ep[0]), float(ep[1]))


def run_tsp_optimization(config_path: Optional[Union[str, Path]] = None):
    if config_path is None:
        config_path = REPO_ROOT / "config.yaml"
    cfg = config_loader.load(config_path)

    # Startup Capability Assessment
    rasters = config_loader.inspect_rasters(cfg)
    caps = config_loader.assess(rasters)
    if caps.get("routing", {}).get("level") == "BLOCKED":
        missing = ", ".join(caps["routing"]["missing"])
        raise RuntimeError(f"Module 'routing' is BLOCKED due to missing required data: {missing}. Aborting.")

    site_name = cfg.get("site", {}).get("name", "study_area")
    rgb_path = cfg.path("site", "rasters", "rgb_t2", required=True)
    dtm_path = cfg.path("site", "rasters", "dtm")
    chm_path = cfg.path("site", "rasters", "chm_t2")

    gis_dir = cfg.path("outputs", "gis_dir") or (REPO_ROOT / "results" / "gis")
    gis_dir.mkdir(parents=True, exist_ok=True)

    prio_geojson = gis_dir / f"{site_name}_verification_priority.geojson"
    boundary_geojson = gis_dir / f"{site_name}_boundary.geojson"
    out_route_geojson = gis_dir / "route_terrain.geojson"
    out_overview_map = gis_dir / f"{site_name}_overview_map_optimized.png"
    out_canopy_map = gis_dir / f"{site_name}_canopy_route_optimized.png"

    w_veg = float(cfg.get("routing", {}).get("w_veg", 4.0))
    max_slope_deg = float(cfg.get("routing", {}).get("max_slope_deg", 45.0))
    grid_res_m = float(cfg.get("routing", {}).get("grid_res_m", 1.0))
    impedance_mode = cfg.get("routing", {}).get("impedance", "chm")

    # 1. Load GeoTIFF
    print(f"Loading base raster GeoTIFF and terrain layers ({site_name})...")
    with rasterio.open(rgb_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom

    grid_w = int(round(width_m / grid_res_m))
    grid_h = int(round(height_m / grid_res_m))
    cell_size_x = width_m / grid_w
    cell_size_y = height_m / grid_h
    cell_size = (cell_size_x + cell_size_y) / 2.0

    # 2. Build Terrain-Aware Cost Surface
    # A. Slope and Tobler cost
    if dtm_path and dtm_path.exists():
        with rasterio.open(dtm_path) as dtm_ds:
            dtm = dtm_ds.read(1).astype(np.float64)
            dtm_res_x, dtm_res_y = dtm_ds.res
        if np.isnan(dtm).any():
            dtm = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm)
        slope = slope_degrees(dtm, dtm_res_x, dtm_res_y)
        t_cost = tobler_cost(slope, max_slope_deg=max_slope_deg)  # hours per km
    else:
        print("! [DEGRADED] DTM is missing. Flat terrain assumed (Tobler slope = 0°).")
        slope = np.zeros((grid_h, grid_w), dtype=np.float64)
        t_cost = tobler_cost(slope, max_slope_deg=max_slope_deg)

    # B. Vegetation Impedance
    use_chm = (impedance_mode == "chm") and (chm_path is not None and chm_path.exists())
    if impedance_mode == "chm" and not (chm_path and chm_path.exists()):
        print("! [DEGRADED] Impedance requested as 'chm', but CHM raster is unavailable. Falling back to ExG (2G-R-B) 2D vegetation proxy.")
        use_chm = False

    if use_chm:
        with rasterio.open(chm_path) as chm_ds:
            chm = chm_ds.read(1).astype(np.float64)
        chm_p95 = float(np.nanpercentile(chm, 95))
        veg_norm = np.clip(chm / (chm_p95 + 1e-6), 0.0, 1.0)
        canopy_bool = chm > 2.0
        canopy_pct = float(np.mean(canopy_bool) * 100.0)
        open_pct = 100.0 - canopy_pct
        binary_img = np.where(canopy_bool, 0, 255).astype(np.uint8)
    else:
        scale_y = orig_h // grid_h
        scale_x = orig_w // grid_w
        rgb_float = rgb_data.astype(np.float64)
        rgb_down = rgb_float[:, :grid_h * scale_y, :grid_w * scale_x].reshape(3, grid_h, scale_y, grid_w, scale_x).mean(axis=(2, 4))
        r_ch, g_ch, b_ch = rgb_down[0], rgb_down[1], rgb_down[2]
        exg = 2.0 * g_ch - r_ch - b_ch
        p1, p99 = np.percentile(exg, 1), np.percentile(exg, 99)
        veg_norm = np.clip((exg - p1) / (p99 - p1 + 1e-6), 0.0, 1.0)
        chm = np.zeros((grid_h, grid_w), dtype=np.float64)
        chm_p95 = 0.0
        canopy_bool = exg > 15.0
        canopy_pct = float(np.mean(canopy_bool) * 100.0)
        open_pct = 100.0 - canopy_pct
        binary_img = np.where(canopy_bool, 0, 255).astype(np.uint8)

    # Cost surface in minutes per meter: (hours/km) * (60 min / 1000 m) = 0.06 min/m
    cost_surface = t_cost * 0.06 * (1.0 + w_veg * veg_norm)

    rgb_display = np.transpose(rgb_data, (1, 2, 0))
    if rgb_display.max() > 1.0:
        rgb_display = rgb_display.astype(np.uint8)

    # 3. Build 8-Connected NetworkX Grid Graph (edge weights in minutes)
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
                edges.append((u, (r, c + 1), cell_size * (c_u + cost_surface[r, c + 1]) / 2.0))
            if r + 1 < grid_h:
                edges.append((u, (r + 1, c), cell_size * (c_u + cost_surface[r + 1, c]) / 2.0))
                if c + 1 < grid_w:
                    edges.append((u, (r + 1, c + 1), cell_size * SQRT2 * (c_u + cost_surface[r + 1, c + 1]) / 2.0))
                if c - 1 >= 0:
                    edges.append((u, (r + 1, c - 1), cell_size * SQRT2 * (c_u + cost_surface[r + 1, c - 1]) / 2.0))

    G.add_weighted_edges_from(edges)

    # 4. Load HIGH Priority Stops
    gdf_prio = gpd.read_file(prio_geojson)
    gdf_boundary = gpd.read_file(boundary_geojson)
    gdf_high = gdf_prio[gdf_prio["verification_priority"] == "HIGH"].copy().reset_index(drop=True)

    entry_x, entry_y = get_entry_point(cfg, bounds)
    entry_grid = utm_to_grid(entry_x, entry_y)

    waypoint_nodes = {"ENTRY": entry_grid}
    waypoint_info = {
        "ENTRY": {
            "name": "Ranger Base / Entry Point",
            "tree_id": 0,
            "utm": (entry_x, entry_y),
            "conf": 1.0
        }
    }

    for _, row in gdf_high.iterrows():
        t_id = row["tree_id"]
        node_id = f"T{t_id}"
        gx, gy = row["geo_easting"], row["geo_northing"]
        waypoint_nodes[node_id] = utm_to_grid(gx, gy)
        waypoint_info[node_id] = {
            "name": f"Tree #{t_id}",
            "tree_id": t_id,
            "utm": (gx, gy),
            "conf": row["confidence"]
        }

    # 5. Compute All-Pairs Dijkstra Paths, Physical Distances, and Travel Times
    wp_keys = list(waypoint_nodes.keys())
    time_matrix = {}
    phys_dist_matrix = {}
    path_cache = {}

    for u in wp_keys:
        time_matrix[u] = {}
        phys_dist_matrix[u] = {}
        for v in wp_keys:
            if u == v:
                time_matrix[u][v] = 0.0
                phys_dist_matrix[u][v] = 0.0
                path_cache[(u, v)] = [waypoint_nodes[u]]
            else:
                c_path = nx.dijkstra_path(G, waypoint_nodes[u], waypoint_nodes[v], weight="weight")
                path_cache[(u, v)] = c_path
                u_coords = [grid_to_utm(r, c) for (r, c) in c_path]
                leg_dist = sum(
                    math.hypot(u_coords[i+1][0] - u_coords[i][0], u_coords[i+1][1] - u_coords[i][1])
                    for i in range(len(u_coords)-1)
                )
                phys_dist_matrix[u][v] = leg_dist
                time_matrix[u][v] = nx.dijkstra_path_length(G, waypoint_nodes[u], waypoint_nodes[v], weight="weight")

    # 6. Evaluate Runtime Nearest-Neighbor (NN) Baseline
    unvisited_nn = set(wp_keys)
    unvisited_nn.remove("ENTRY")
    cur_nn = "ENTRY"
    nn_route = ["ENTRY"]
    nn_dist_m = 0.0
    nn_time_min = 0.0
    while unvisited_nn:
        nxt_nn = min(unvisited_nn, key=lambda target: time_matrix[cur_nn][target])
        nn_dist_m += phys_dist_matrix[cur_nn][nxt_nn]
        nn_time_min += time_matrix[cur_nn][nxt_nn]
        nn_route.append(nxt_nn)
        unvisited_nn.remove(nxt_nn)
        cur_nn = nxt_nn

    # 7. Solve Exact Open-Path TSP via Held-Karp DP (Minimizing Travel Time)
    targets = [k for k in wp_keys if k != "ENTRY"]
    n_targets = len(targets)
    memo = {}

    for i, t in enumerate(targets):
        t_time = time_matrix["ENTRY"][t]
        memo[(1 << i, i)] = (t_time, ["ENTRY", t])

    for size in range(2, n_targets + 1):
        for subset in itertools.combinations(range(n_targets), size):
            mask = sum(1 << i for i in subset)
            for last in subset:
                prev_mask = mask ^ (1 << last)
                best_t = float("inf")
                best_path = None
                last_target = targets[last]
                for prev in subset:
                    if prev == last:
                        continue
                    prev_t, prev_path = memo[(prev_mask, prev)]
                    d = prev_t + time_matrix[targets[prev]][last_target]
                    if d < best_t:
                        best_t = d
                        best_path = prev_path + [last_target]
                memo[(mask, last)] = (best_t, best_path)

    full_mask = (1 << n_targets) - 1
    best_total_time = float("inf")
    best_tsp_route = None

    for last in range(n_targets):
        t_val, path = memo[(full_mask, last)]
        if t_val < best_total_time:
            best_total_time = t_val
            best_tsp_route = path

    # 8. Reconstruct Full Geometric Path
    stitched_utm_coords = []
    total_opt_phys_dist = 0.0
    total_opt_time = 0.0
    legs_info = []

    for leg_idx in range(len(best_tsp_route) - 1):
        u_node = best_tsp_route[leg_idx]
        v_node = best_tsp_route[leg_idx + 1]
        c_path = path_cache[(u_node, v_node)]
        leg_utm_coords = [grid_to_utm(r, c) for (r, c) in c_path]
        leg_phys_dist = sum(
            math.hypot(leg_utm_coords[i+1][0] - leg_utm_coords[i][0], leg_utm_coords[i+1][1] - leg_utm_coords[i][1])
            for i in range(len(leg_utm_coords) - 1)
        )
        leg_time = time_matrix[u_node][v_node]

        total_opt_phys_dist += leg_phys_dist
        total_opt_time += leg_time

        if not stitched_utm_coords:
            stitched_utm_coords.extend(leg_utm_coords)
        else:
            stitched_utm_coords.extend(leg_utm_coords[1:])

        legs_info.append({
            "leg": leg_idx + 1,
            "from_node": u_node,
            "to_node": v_node,
            "from_name": waypoint_info[u_node]["name"],
            "to_name": waypoint_info[v_node]["name"],
            "grid_steps": len(c_path),
            "physical_dist_m": round(leg_phys_dist, 2),
            "cumulative_phys_dist_m": round(total_opt_phys_dist, 2),
            "travel_time_min": round(leg_time, 2),
            "cumulative_time_min": round(total_opt_time, 2),
        })

    route_line_geom = LineString(stitched_utm_coords)
    gdf_route_terrain = gpd.GeoDataFrame(
        [{
            "route_name": f"{site_name} Terrain-Aware TSP-Optimized Field Route",
            "cost_model": "Tobler's Hiking Function (DTM Slope) + Normalized Canopy Height Model (CHM p95)" if use_chm else "Tobler's Hiking Function (DTM Slope) + ExG Vegetation Index",
            "optimization_metric": "Travel Time Minimization (minutes)",
            "study_area": f"{width_m:.0f}m x {height_m:.0f}m ({width_m*height_m/10000:.2f} ha)",
            "total_physical_distance_meters": round(total_opt_phys_dist, 2),
            "total_travel_time_minutes": round(total_opt_time, 2),
            "nn_baseline_distance_meters": round(nn_dist_m, 2),
            "nn_baseline_time_minutes": round(nn_time_min, 2),
            "time_saved_minutes": round(nn_time_min - total_opt_time, 2),
            "time_improvement_pct": round((nn_time_min - total_opt_time) / nn_time_min * 100, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in best_tsp_route]),
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
        }],
        geometry=[route_line_geom],
        crs=crs
    )
    gdf_route_terrain.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Saved terrain-aware route to: {out_route_geojson.name}")

    # 9. Visualizations
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    ordered_stops = []
    for s_idx, node_id in enumerate(best_tsp_route[1:], 1):
        info = waypoint_info[node_id]
        ordered_stops.append({
            "stop_num": s_idx,
            "tree_id": info["tree_id"],
            "conf": info["conf"],
            "easting": info["utm"][0],
            "northing": info["utm"][1]
        })

    fig, axes = plt.subplots(1, 2, figsize=(24, 12.5), dpi=200)
    plt.subplots_adjust(wspace=0.10, top=0.84, bottom=0.06, left=0.04, right=0.96)

    # Panel 1: RGB
    ax1 = axes[0]
    ax1.imshow(rgb_display, extent=extent, origin="upper")
    gdf_boundary.boundary.plot(ax=ax1, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor")
    gdf_boundary.plot(ax=ax1, facecolor="#FF0055", alpha=0.08)

    xs, ys = zip(*stitched_utm_coords)
    ax1.plot(xs, ys, color="#00FFFF", linewidth=3.2, linestyle="-", label=f"Terrain-Aware TSP Route ({total_opt_phys_dist:.1f} m | {total_opt_time:.1f} min)", zorder=5)

    n_pts = len(stitched_utm_coords)
    for frac in [0.08, 0.22, 0.38, 0.52, 0.68, 0.82, 0.94]:
        idx = int(n_pts * frac)
        if idx < n_pts - 1:
            x1, y1 = stitched_utm_coords[idx]
            x2, y2 = stitched_utm_coords[idx + 1]
            dx, dy = x2 - x1, y2 - y1
            if math.hypot(dx, dy) > 1e-4:
                ax1.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#00FFFF", lw=2.2, mutation_scale=14), zorder=6)

    ax1.scatter([entry_x], [entry_y], color="#00B4D8", edgecolor="black", s=280, marker="s", linewidth=2.2, label="Ranger Entry Point (Start)", zorder=7)
    ax1.annotate("RANGER ENTRY (START)", (entry_x, entry_y), textcoords="offset points", xytext=(8, 8), color="black", fontweight="bold", fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc="#00B4D8", alpha=0.92, ec="black"), zorder=8)

    for st in ordered_stops:
        gx, gy = st["easting"], st["northing"]
        t_id = st["tree_id"]
        conf = st["conf"]
        s_num = st["stop_num"]
        ax1.scatter([gx], [gy], color="#FFE600", edgecolor="red", s=190, linewidth=2.2, marker="o", zorder=7)
        ax1.annotate(f"STOP {s_num}: T{t_id}\n({conf:.1%})", (gx, gy), textcoords="offset points", xytext=(7, 7), color="white", fontweight="bold", fontsize=8.5, bbox=dict(boxstyle="round,pad=0.25", fc="red", alpha=0.88, ec="black"), zorder=8)

    ax1.set_title(f"Panel 1: High-Resolution RGB Orthomosaic\nTerrain-Aware Route ({total_opt_phys_dist:.1f} m, {total_opt_time:.1f} min)", fontsize=13, fontweight="bold", pad=14)
    ax1.set_xlabel(f"Easting (m) [{crs}]", fontsize=10)
    ax1.set_ylabel(f"Northing (m) [{crs}]", fontsize=10)
    ax1.set_xlim(bounds.left, bounds.right)
    ax1.set_ylim(bounds.bottom, bounds.top)
    ax1.grid(True, linestyle=":", alpha=0.35, color="white")
    ax1.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    # Panel 2: CHM / Canopy
    ax2 = axes[1]
    chm_im = ax2.imshow(chm if use_chm else binary_img, extent=extent, origin="upper", cmap="YlGn_r" if use_chm else "gray", vmin=0, vmax=chm_p95 if use_chm else 255)
    if use_chm:
        cbar = plt.colorbar(chm_im, ax=ax2, fraction=0.032, pad=0.02)
        cbar.set_label("NEON Canopy Height Model (m)", fontsize=9)
    gdf_boundary.boundary.plot(ax=ax2, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor")
    ax2.plot(xs, ys, color="#00E5FF", linewidth=3.2, linestyle="-", label=f"Terrain TSP Route ({total_opt_phys_dist:.1f} m)", zorder=5)

    for frac in [0.08, 0.22, 0.38, 0.52, 0.68, 0.82, 0.94]:
        idx = int(n_pts * frac)
        if idx < n_pts - 1:
            x1, y1 = stitched_utm_coords[idx]
            x2, y2 = stitched_utm_coords[idx + 1]
            dx, dy = x2 - x1, y2 - y1
            if math.hypot(dx, dy) > 1e-4:
                ax2.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#00E5FF", lw=2.2, mutation_scale=14), zorder=6)

    ax2.scatter([entry_x], [entry_y], color="#00B4D8", edgecolor="black", s=280, marker="s", linewidth=2.2, zorder=7)
    ax2.annotate("RANGER ENTRY (START)", (entry_x, entry_y), textcoords="offset points", xytext=(8, 8), color="black", fontweight="bold", fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc="#00B4D8", alpha=0.95, ec="black"), zorder=8)

    for st in ordered_stops:
        gx, gy = st["easting"], st["northing"]
        t_id = st["tree_id"]
        conf = st["conf"]
        s_num = st["stop_num"]
        ax2.scatter([gx], [gy], color="#FFE600", edgecolor="red", s=190, linewidth=2.2, marker="o", zorder=7)
        ax2.annotate(f"STOP {s_num}: T{t_id}\n({conf:.1%})", (gx, gy), textcoords="offset points", xytext=(7, 7), color="white", fontweight="bold", fontsize=8.5, bbox=dict(boxstyle="round,pad=0.25", fc="red", alpha=0.90, ec="black"), zorder=8)

    panel2_title = f"Panel 2: NEON CHM (Canopy p95={chm_p95:.1f}m)\nSlope: Mean={slope.mean():.1f}°, P95={np.percentile(slope,95):.1f}°" if use_chm else f"Panel 2: Binary Canopy Mask (Canopy {canopy_pct:.1f}%)"
    ax2.set_title(panel2_title, fontsize=13, fontweight="bold", pad=14)
    ax2.set_xlabel(f"Easting (m) [{crs}]", fontsize=10)
    ax2.set_ylabel(f"Northing (m) [{crs}]", fontsize=10)
    ax2.set_xlim(bounds.left, bounds.right)
    ax2.set_ylim(bounds.bottom, bounds.top)
    ax2.grid(True, linestyle=":", alpha=0.35, color="gray")
    ax2.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    fig.suptitle(
        f"VanDrishti: {site_name} — Terrain-Aware TSP-Optimized Route (DTM Slope + CHM)\n"
        f"13 HIGH Stops | Physical Distance: {total_opt_phys_dist:.1f} m | Estimated Travel Time: {total_opt_time:.1f} min",
        fontsize=15,
        fontweight="bold",
        y=0.96
    )

    plt.savefig(out_overview_map, dpi=200, bbox_inches="tight")
    plt.savefig(out_canopy_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved optimized overview map to: {out_overview_map.name}")

    print("\n" + "="*80)
    print(f"      VAN-DRISHTI: {site_name.upper()} TERRAIN-AWARE TSP REPORT")
    print("="*80)
    print(f"1. Topographic & Canopy Characteristics:")
    if dtm_path and dtm_path.exists():
        print(f"   - DTM Elevation Range:      {dtm.min():.2f} m to {dtm.max():.2f} m (Total Relief: {dtm.max() - dtm.min():.2f} m)")
    print(f"   - Slope Stats:              Min {slope.min():.2f}°, Mean {slope.mean():.2f}°, Median {np.percentile(slope, 50):.2f}°, P95 {np.percentile(slope, 95):.2f}°, Max {slope.max():.2f}°")
    if use_chm:
        print(f"   - CHM Canopy Height:        P95 {chm_p95:.2f} m, Max {chm.max():.2f} m")
    print(f"2. Optimization Comparison:")
    print(f"   - Legacy ExG TSP Distance:  432.08 meters")
    print(f"   - New Terrain NN Baseline:  {nn_dist_m:.2f} meters | {nn_time_min:.2f} minutes")
    print(f"   - New Terrain TSP Route:    {total_opt_phys_dist:.2f} meters | {total_opt_time:.2f} minutes")
    print(f"   - Time Saved vs NN Baseline: {nn_time_min - total_opt_time:.2f} minutes ({(nn_time_min - total_opt_time) / nn_time_min * 100:.1f}% reduction)")
    print(f"\nOptimal Visiting Sequence:")
    for leg in legs_info:
        print(f"  Leg {leg['leg']:2d}: {leg['from_name']:<25} -> {leg['to_name']:<12} ({leg['physical_dist_m']:6.2f} m, {leg['travel_time_min']:5.2f} min | cumulative: {leg['cumulative_phys_dist_m']:6.2f} m, {leg['cumulative_time_min']:5.2f} min)")
    print("="*80)

    return {
        "legacy_length_m": 432.08,
        "new_length_m": total_opt_phys_dist,
        "new_time_min": total_opt_time,
        "new_baseline_dist_m": nn_dist_m,
        "new_baseline_time_min": nn_time_min,
        "geojson": str(out_route_geojson),
        "map_png": str(out_overview_map)
    }


if __name__ == "__main__":
    run_tsp_optimization()
