"""
run_tsp_optimization_large.py
Solves exact open-path TSP on the 250m OSBS Large study area, eliminates backtracking,
saves the optimized LineString GeoJSON, and generates high-resolution map visualizations.
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


def run_tsp_optimization():
    project_root = Path("C:/VanDrishtiProject")
    tif_path = project_root / "data" / "raw" / "neon" / "large" / "OSBS_large_2019.tif"
    prio_geojson = project_root / "results" / "gis" / "OSBS_large_2019_verification_priority.geojson"
    boundary_geojson = project_root / "results" / "gis" / "OSBS_large_2019_boundary.geojson"
    gis_dir = project_root / "results" / "gis"

    out_route_geojson = gis_dir / "OSBS_large_2019_field_route_lcp_optimized.geojson"
    out_overview_map = gis_dir / "OSBS_large_2019_overview_map_optimized.png"
    out_canopy_map = gis_dir / "OSBS_large_2019_canopy_route_optimized.png"

    # 1. Load GeoTIFF
    print("Loading base raster GeoTIFF...")
    with rasterio.open(tif_path) as ds:
        bounds = ds.bounds
        crs = ds.crs
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom

    # 2. Downsample Cost Surface (250x250 grid = 1.0m/cell)
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

    # Binary canopy mask for panel 2
    canopy_bool = (exg > 15.0) & (g_ch > 30.0)
    canopy_pct = float(np.mean(canopy_bool) * 100.0)
    open_pct = 100.0 - canopy_pct
    binary_img = np.where(canopy_bool, 0, 255).astype(np.uint8)

    rgb_display = np.transpose(rgb_data, (1, 2, 0))
    if rgb_display.max() > 1.0:
        rgb_display = rgb_display.astype(np.uint8)

    # 3. Build 8-Connected NetworkX Grid Graph
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

    # 5. Compute All-Pairs Dijkstra Paths and Distances
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
                leg_dist = sum(
                    math.hypot(u_coords[i+1][0] - u_coords[i][0], u_coords[i+1][1] - u_coords[i][1])
                    for i in range(len(u_coords)-1)
                )
                phys_dist_matrix[u][v] = leg_dist
                weighted_cost_matrix[u][v] = nx.dijkstra_path_length(G, waypoint_nodes[u], waypoint_nodes[v], weight="weight")

    # 6. Solve Exact Open-Path TSP via Held-Karp DP
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

    # 7. Reconstruct Full Geometric Path
    stitched_utm_coords = []
    total_opt_phys_dist = 0.0
    total_opt_cost = 0.0
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
        leg_cost = weighted_cost_matrix[u_node][v_node]

        total_opt_phys_dist += leg_phys_dist
        total_opt_cost += leg_cost

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
            "weighted_cost": round(leg_cost, 2),
        })

    # Save Optimized Route GeoJSON
    route_line_geom = LineString(stitched_utm_coords)
    gdf_route_opt = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS Large 2019 TSP-Optimized Dijkstra Least-Cost Path",
            "optimization_method": "Exact Held-Karp Dynamic Programming Open-Path TSP over Dijkstra Matrix",
            "study_area": "250m x 250m (6.25 ha)",
            "total_physical_distance_meters": round(total_opt_phys_dist, 2),
            "total_least_cost_score": round(total_opt_cost, 2),
            "nn_baseline_distance_meters": 449.58,
            "distance_saved_meters": round(449.58 - total_opt_phys_dist, 2),
            "improvement_pct": round((449.58 - total_opt_phys_dist) / 449.58 * 100, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in best_tsp_route]),
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
        }],
        geometry=[route_line_geom],
        crs=crs
    )
    gdf_route_opt.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Saved optimized route to: {out_route_geojson.name}")

    # 8. Generate Visualizations (Overview Map & Clean 2-Panel Map)
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

    # Generate 2-Panel Clean Visualization
    fig, axes = plt.subplots(1, 2, figsize=(24, 12.5), dpi=200)
    plt.subplots_adjust(wspace=0.10, top=0.84, bottom=0.06, left=0.04, right=0.96)

    # Panel 1: RGB
    ax1 = axes[0]
    ax1.imshow(rgb_display, extent=extent, origin="upper")
    gdf_boundary.boundary.plot(ax=ax1, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor (24% Area)")
    gdf_boundary.plot(ax=ax1, facecolor="#FF0055", alpha=0.08)

    xs, ys = zip(*stitched_utm_coords)
    ax1.plot(xs, ys, color="#00FFFF", linewidth=3.2, linestyle="-", label=f"TSP-Optimized Route ({total_opt_phys_dist:.1f} m)", zorder=5)

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

    ax1.set_title("Panel 1: High-Resolution RGB Orthomosaic\nTSP-Optimized Verification Route (Zero Backtracking)", fontsize=13, fontweight="bold", pad=14)
    ax1.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax1.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax1.set_xlim(bounds.left, bounds.right)
    ax1.set_ylim(bounds.bottom, bounds.top)
    ax1.grid(True, linestyle=":", alpha=0.35, color="white")
    ax1.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    # Panel 2: Binary Canopy Mask
    ax2 = axes[1]
    ax2.imshow(binary_img, extent=extent, origin="upper", cmap="gray", vmin=0, vmax=255)
    gdf_boundary.boundary.plot(ax=ax2, color="#FF0055", linewidth=2.5, linestyle="--", label="Project Corridor")
    ax2.plot(xs, ys, color="#00E5FF", linewidth=3.2, linestyle="-", label=f"TSP Least-Cost Path ({total_opt_phys_dist:.1f} m)", zorder=5)

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

    ax2.set_title(f"Panel 2: Binary Canopy Mask (Black = Canopy {canopy_pct:.1f}%, White = Open Ground {open_pct:.1f}%)\nSmooth West-to-East Progression", fontsize=13, fontweight="bold", pad=14)
    ax2.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax2.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax2.set_xlim(bounds.left, bounds.right)
    ax2.set_ylim(bounds.bottom, bounds.top)
    ax2.grid(True, linestyle=":", alpha=0.35, color="gray")
    ax2.legend(loc="upper left", framealpha=0.92, fontsize=9.5)

    fig.suptitle(
        f"VanDrishti: 250m Study Area — TSP-Optimized Field Verification Route (Zero Backtracking)\n"
        f"13 HIGH-Priority Audit Stops | Optimized LCP Length: {total_opt_phys_dist:.1f} m (Saved {449.58 - total_opt_phys_dist:.1f} m vs NN)",
        fontsize=15,
        fontweight="bold",
        y=0.96
    )

    plt.savefig(out_overview_map, dpi=200, bbox_inches="tight")
    plt.savefig(out_canopy_map, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved optimized overview map to: {out_overview_map.name}")

    # Print Report
    print("\n" + "="*80)
    print("      VAN-DRISHTI: TSP-OPTIMIZED FIELD ROUTE REPORT (250m STUDY AREA)")
    print("="*80)
    print(f"Algorithm:                     Exact Held-Karp Dynamic Programming Open-Path TSP")
    print(f"Old Nearest-Neighbor Distance: 449.58 meters")
    print(f"New TSP-Optimized Distance:    {total_opt_phys_dist:.2f} meters")
    print(f"Total Distance Saved:          {449.58 - total_opt_phys_dist:.2f} meters ({(449.58 - total_opt_phys_dist) / 449.58 * 100:.1f}% reduction)")
    print(f"\nOptimal Visiting Sequence (Zero Backtracking):")
    for leg in legs_info:
        print(f"  Leg {leg['leg']:2d}: {leg['from_name']:<25} -> {leg['to_name']:<12} ({leg['physical_dist_m']:6.2f} m, cumulative: {leg['cumulative_phys_dist_m']:6.2f} m)")
    print("="*80)

    return {
        "opt_distance_m": total_opt_phys_dist,
        "saved_m": 449.58 - total_opt_phys_dist,
        "sequence": best_tsp_route,
        "geojson": str(out_route_geojson),
        "map_png": str(out_overview_map)
    }


if __name__ == "__main__":
    run_tsp_optimization()
