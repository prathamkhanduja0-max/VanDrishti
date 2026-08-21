"""
run_tsp_optimization_large.py
Solves exact open-path TSP on the 250m OSBS Large study area using terrain-aware
cost surface (Tobler's hiking function on DTM slope + normalized CHM canopy impedance).
Eliminates backtracking, saves the optimized LineString GeoJSON (route_terrain.geojson),
and generates high-resolution map visualizations.
"""

import itertools
import math
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
from shapely.geometry import LineString

try:
    from scripts.terrain_cost import slope_degrees, tobler_cost
except ImportError:
    from terrain_cost import slope_degrees, tobler_cost


def run_tsp_optimization():
    """
    Terrain-aware TSP optimization using NEON DTM slope (Tobler hiking function)
    and NEON CHM (Canopy Height Model normalized at 95th percentile).
    Cost is in travel time (minutes/meter). Minimizes total route travel time.
    """
    project_root = Path(__file__).resolve().parent.parent
    rgb_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    dtm_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019_DTM.tif"
    chm_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019_CHM.tif"
    prio_geojson = project_root / "results" / "gis" / "OSBS_large_2019_verification_priority.geojson"
    boundary_geojson = project_root / "results" / "gis" / "OSBS_large_2019_boundary.geojson"
    gis_dir = project_root / "results" / "gis"
    gis_dir.mkdir(parents=True, exist_ok=True)

    out_route_geojson = gis_dir / "route_terrain.geojson"
    out_overview_map = gis_dir / "OSBS_large_2019_overview_map_optimized.png"
    out_canopy_map = gis_dir / "OSBS_large_2019_canopy_route_optimized.png"

    # 1. Load GeoTIFF and Terrain Rasters
    print("Loading base raster GeoTIFF and terrain layers (DTM, CHM)...")
    with rasterio.open(rgb_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom

    # 2. Build Terrain-Aware Cost Surface (250x250 grid = 1.0m/cell)
    # A. Slope and Tobler cost from DTM
    with rasterio.open(dtm_path) as dtm_ds:
        dtm = dtm_ds.read(1).astype(np.float64)
        cell_size_x, cell_size_y = dtm_ds.res
        grid_h, grid_w = dtm_ds.shape

    if np.isnan(dtm).any():
        dtm = np.where(np.isnan(dtm), np.nanmedian(dtm), dtm)

    slope = slope_degrees(dtm, cell_size_x, cell_size_y)
    t_cost = tobler_cost(slope)  # hours per km

    # B. Vegetation impedance from CHM (normalized to [0,1] by clipping at 95th percentile)
    with rasterio.open(chm_path) as chm_ds:
        chm = chm_ds.read(1).astype(np.float64)

    chm_p95 = float(np.nanpercentile(chm, 95))
    chm_norm = np.clip(chm / (chm_p95 + 1e-6), 0.0, 1.0)
    w_veg = 4.0

    # Cost surface in minutes per meter: (hours/km) * (60 min / 1000 m) = 0.06 min/m
    cost_surface = t_cost * 0.06 * (1.0 + w_veg * chm_norm)
    cell_size = (cell_size_x + cell_size_y) / 2.0

    # Binary canopy mask for visualization (CHM > 2.0m height = canopy)
    canopy_bool = chm > 2.0
    canopy_pct = float(np.mean(canopy_bool) * 100.0)
    open_pct = 100.0 - canopy_pct
    binary_img = np.where(canopy_bool, 0, 255).astype(np.uint8)

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

    entry_x, entry_y = bounds.left, bounds.bottom
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

    # 6. Evaluate Runtime Nearest-Neighbor (NN) Baseline on New Terrain Surface
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

    # Save Terrain-Aware Route GeoJSON (results/gis/route_terrain.geojson)
    route_line_geom = LineString(stitched_utm_coords)
    gdf_route_terrain = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS Large 2019 Terrain-Aware TSP-Optimized Field Route",
            "cost_model": "Tobler's Hiking Function (DTM Slope) + Normalized Canopy Height Model (CHM p95)",
            "optimization_metric": "Travel Time Minimization (minutes)",
            "study_area": "250m x 250m (6.25 ha)",
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

    # 9. Generate Visualizations (Overview Map & Clean 2-Panel Map)
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

    # Panel 1: RGB + Elevation Contours
    ax1 = axes[0]
    ax1.imshow(rgb_display, extent=extent, origin="upper")
    gdf_boundary.boundary.plot(ax=ax1, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor (24% Area)")
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
    ax1.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax1.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax1.set_xlim(bounds.left, bounds.right)
    ax1.set_ylim(bounds.bottom, bounds.top)
    ax1.grid(True, linestyle=":", alpha=0.35, color="white")
    ax1.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    # Panel 2: CHM Canopy + DTM Slope Heatmap
    ax2 = axes[1]
    chm_im = ax2.imshow(chm, extent=extent, origin="upper", cmap="YlGn_r", vmin=0, vmax=chm_p95)
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

    ax2.set_title(f"Panel 2: NEON CHM (Canopy p95={chm_p95:.1f}m, Max={chm.max():.1f}m)\nSlope: Mean={slope.mean():.1f}°, P95={np.percentile(slope,95):.1f}°, Relief={dtm.max()-dtm.min():.1f}m", fontsize=13, fontweight="bold", pad=14)
    ax2.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax2.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax2.set_xlim(bounds.left, bounds.right)
    ax2.set_ylim(bounds.bottom, bounds.top)
    ax2.grid(True, linestyle=":", alpha=0.35, color="gray")
    ax2.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    fig.suptitle(
        f"VanDrishti: 250m Study Area — Terrain-Aware TSP-Optimized Route (DTM Slope + CHM)\n"
        f"13 HIGH Stops | Physical Distance: {total_opt_phys_dist:.1f} m | Estimated Travel Time: {total_opt_time:.1f} min",
        fontsize=15,
        fontweight="bold",
        y=0.96
    )

    plt.savefig(out_overview_map, dpi=200, bbox_inches="tight")
    plt.savefig(out_canopy_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved optimized overview map to: {out_overview_map.name}")

    # Print Full Comparison Report
    print("\n" + "="*80)
    print("      VAN-DRISHTI: TERRAIN-AWARE TSP-OPTIMIZED FIELD ROUTE REPORT")
    print("="*80)
    print(f"1. Topographic & Canopy Characteristics (OSBS Large 2019):")
    print(f"   - DTM Elevation Range:      {dtm.min():.2f} m to {dtm.max():.2f} m (Total Relief: {dtm.max() - dtm.min():.2f} m)")
    print(f"   - Slope Stats:              Min {slope.min():.2f}°, Mean {slope.mean():.2f}°, Median {np.percentile(slope, 50):.2f}°, P95 {np.percentile(slope, 95):.2f}°, Max {slope.max():.2f}°")
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
        "slope_stats": {
            "dtm_relief_m": dtm.max() - dtm.min(),
            "slope_mean_deg": slope.mean(),
            "slope_p50_deg": np.percentile(slope, 50),
            "slope_p95_deg": np.percentile(slope, 95),
            "slope_max_deg": slope.max(),
        },
        "geojson": str(out_route_geojson),
        "map_png": str(out_overview_map)
    }


def run_tsp_optimization_legacy():
    """Legacy ExG-based optimization function preserved for A/B comparison."""
    project_root = Path(__file__).resolve().parent.parent
    tif_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    prio_geojson = project_root / "results" / "gis" / "OSBS_large_2019_verification_priority.geojson"
    boundary_geojson = project_root / "results" / "gis" / "OSBS_large_2019_boundary.geojson"
    gis_dir = project_root / "results" / "gis"

    out_route_geojson = gis_dir / "OSBS_large_2019_field_route_lcp_optimized.geojson"

    with rasterio.open(tif_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom

    grid_h, grid_w = 250, 250
    cell_size_x = width_m / grid_w
    cell_size_y = height_m / grid_h
    cell_size = (cell_size_x + cell_size_y) / 2.0

    rgb_float = rgb_data.astype(np.float64)
    rgb_down = rgb_float.reshape(3, grid_h, 10, grid_w, 10).mean(axis=(2, 4))
    r_ch, g_ch, b_ch = rgb_down[0], rgb_down[1], rgb_down[2]

    exg = 2.0 * g_ch - r_ch - b_ch
    p1, p99 = np.percentile(exg, 1), np.percentile(exg, 99)
    exg_norm = np.clip((exg - p1) / (p99 - p1 + 1e-6), 0.0, 1.0)
    cost_surface = 1.0 + 4.0 * exg_norm

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

    gdf_prio = gpd.read_file(prio_geojson)
    gdf_high = gdf_prio[gdf_prio["verification_priority"] == "HIGH"].copy().reset_index(drop=True)

    entry_x, entry_y = bounds.left, bounds.bottom
    entry_grid = utm_to_grid(entry_x, entry_y)

    waypoint_nodes = {"ENTRY": entry_grid}
    waypoint_info = {"ENTRY": {"name": "Ranger Base / Entry Point", "tree_id": 0, "utm": (entry_x, entry_y), "conf": 1.0}}

    for _, row in gdf_high.iterrows():
        t_id = row["tree_id"]
        node_id = f"T{t_id}"
        gx, gy = row["geo_easting"], row["geo_northing"]
        waypoint_nodes[node_id] = utm_to_grid(gx, gy)
        waypoint_info[node_id] = {"name": f"Tree #{t_id}", "tree_id": t_id, "utm": (gx, gy), "conf": row["confidence"]}

    wp_keys = list(waypoint_nodes.keys())
    phys_dist_matrix = {}
    weighted_cost_matrix = {}
    path_cache = {}

    for u in wp_keys:
        phys_dist_matrix[u] = {}
        weighted_cost_matrix[u] = {}
        for v in wp_keys:
            if u == v:
                phys_dist_matrix[u][v] = 0.0
                weighted_cost_matrix[u][v] = 0.0
                path_cache[(u, v)] = [waypoint_nodes[u]]
            else:
                c_path = nx.dijkstra_path(G, waypoint_nodes[u], waypoint_nodes[v], weight="weight")
                path_cache[(u, v)] = c_path
                u_coords = [grid_to_utm(r, c) for (r, c) in c_path]
                leg_dist = sum(math.hypot(u_coords[i+1][0] - u_coords[i][0], u_coords[i+1][1] - u_coords[i][1]) for i in range(len(u_coords)-1))
                phys_dist_matrix[u][v] = leg_dist
                weighted_cost_matrix[u][v] = nx.dijkstra_path_length(G, waypoint_nodes[u], waypoint_nodes[v], weight="weight")

    targets = [k for k in wp_keys if k != "ENTRY"]
    n_targets = len(targets)
    memo = {}

    for i, t in enumerate(targets):
        dist = phys_dist_matrix["ENTRY"][t]
        memo[(1 << i, i)] = (dist, ["ENTRY", t])

    for size in range(2, n_targets + 1):
        for subset in itertools.combinations(range(n_targets), size):
            mask = sum(1 << i for i in subset)
            for last in subset:
                prev_mask = mask ^ (1 << last)
                best_dist = float("inf")
                best_path = None
                last_target = targets[last]
                for prev in subset:
                    if prev == last:
                        continue
                    prev_dist, prev_path = memo[(prev_mask, prev)]
                    d = prev_dist + phys_dist_matrix[targets[prev]][last_target]
                    if d < best_dist:
                        best_dist = d
                        best_path = prev_path + [last_target]
                memo[(mask, last)] = (best_dist, best_path)

    full_mask = (1 << n_targets) - 1
    best_total_dist = float("inf")
    best_tsp_route = None

    for last in range(n_targets):
        dist, path = memo[(full_mask, last)]
        if dist < best_total_dist:
            best_total_dist = dist
            best_tsp_route = path

    stitched_utm_coords = []
    total_opt_phys_dist = 0.0
    for leg_idx in range(len(best_tsp_route) - 1):
        u_node = best_tsp_route[leg_idx]
        v_node = best_tsp_route[leg_idx + 1]
        c_path = path_cache[(u_node, v_node)]
        leg_utm_coords = [grid_to_utm(r, c) for (r, c) in c_path]
        leg_phys_dist = sum(math.hypot(leg_utm_coords[i+1][0] - leg_utm_coords[i][0], leg_utm_coords[i+1][1] - leg_utm_coords[i][1]) for i in range(len(leg_utm_coords) - 1))
        total_opt_phys_dist += leg_phys_dist
        if not stitched_utm_coords:
            stitched_utm_coords.extend(leg_utm_coords)
        else:
            stitched_utm_coords.extend(leg_utm_coords[1:])

    route_line_geom = LineString(stitched_utm_coords)
    gdf_route_opt = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS Large 2019 TSP-Optimized Dijkstra Least-Cost Path (Legacy)",
            "optimization_method": "Exact Held-Karp Dynamic Programming Open-Path TSP over ExG Dijkstra Matrix",
            "study_area": "250m x 250m (6.25 ha)",
            "total_physical_distance_meters": round(total_opt_phys_dist, 2),
            "nn_baseline_distance_meters": 449.58,
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in best_tsp_route]),
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
        }],
        geometry=[route_line_geom],
        crs=crs
    )
    gdf_route_opt.to_file(out_route_geojson, driver="GeoJSON")
    return {"opt_distance_m": total_opt_phys_dist, "sequence": best_tsp_route}


if __name__ == "__main__":
    run_tsp_optimization()
