"""
field_pathing_dijkstra.py
Upgraded Module 2: Terrain-Aware Dijkstra Least-Cost Path (LCP) routing.
Generates an obstacle/canopy-avoiding field verification route for HIGH priority trees
using an Excess Green (ExG) vegetation cost surface and 8-connected grid Dijkstra shortest path.
Saves LCP route to GeoJSON and generates a high-resolution comparison map.
"""

import math
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
from shapely.geometry import LineString, Point


def generate_dijkstra_field_route():
    project_root = Path("C:/VanDrishtiProject")
    tif_path = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"
    input_geojson = project_root / "results" / "gis" / "OSBS_022_2019_verification_priority.geojson"
    boundary_geojson = project_root / "data" / "demo" / "project_boundary_OSBS_022.geojson"

    gis_results_dir = project_root / "results" / "gis"
    gis_results_dir.mkdir(parents=True, exist_ok=True)

    out_route_geojson = gis_results_dir / "OSBS_022_2019_field_route_lcp.geojson"
    out_route_map = gis_results_dir / "OSBS_022_2019_field_route_lcp_map.png"

    # 1. Load GeoTIFF and extract raster metadata
    print("=== Step 1: Loading GeoTIFF & Extracting Spatial Bounds ===")
    with rasterio.open(tif_path) as ds:
        raster_crs = ds.crs
        bounds = ds.bounds
        orig_h, orig_w = ds.shape
        rgb_data = ds.read([1, 2, 3])  # Shape: (3, 400, 400)

    # Prepare RGB array for background visualization
    rgb_display = np.transpose(rgb_data, (1, 2, 0))
    if rgb_display.max() > 1.0:
        rgb_display = rgb_display.astype(np.uint8)

    width_m = bounds.right - bounds.left
    height_m = bounds.top - bounds.bottom
    print(f"Raster CRS:        {raster_crs}")
    print(f"Raster Bounds:     {bounds}")
    print(f"Dimensions:        {orig_w}x{orig_h} px | {width_m:.1f}m x {height_m:.1f}m")

    # 2. Ranger Entry Point at bottom-left corner
    entry_x = bounds.left
    entry_y = bounds.bottom
    print(f"Ranger Entry Point (Start): UTM ({entry_x:.3f} E, {entry_y:.3f} N)")

    # 3. Filter HIGH Priority Trees
    print("\n=== Step 2: Filtering Mandatory HIGH Priority Tree Stops ===")
    gdf_trees = gpd.read_file(input_geojson)
    gdf_high = gdf_trees[gdf_trees["verification_priority"] == "HIGH"].copy()
    print(f"Total Trees: {len(gdf_trees)} | HIGH Priority Targets: {len(gdf_high)}")

    # 4. Build Walkability Cost Surface
    print("\n=== Step 3: Generating Walkability Cost Surface ===")
    # Target grid size: 200x200 (downsampled from 400x400 via 2x2 mean pooling)
    grid_h, grid_w = 200, 200
    cell_size_x = width_m / grid_w  # 0.20 m
    cell_size_y = height_m / grid_h  # 0.20 m
    cell_size = (cell_size_x + cell_size_y) / 2.0  # 0.20 m

    # Downsample RGB channels by 2x2 block averaging
    rgb_float = rgb_data.astype(np.float64)
    rgb_down = rgb_float.reshape(3, grid_h, 2, grid_w, 2).mean(axis=(2, 4))
    r_ch, g_ch, b_ch = rgb_down[0], rgb_down[1], rgb_down[2]

    # Compute Excess Green Index (ExG): 2*G - R - B
    exg = 2.0 * g_ch - r_ch - b_ch
    p1, p99 = np.percentile(exg, 1), np.percentile(exg, 99)
    exg_norm = np.clip((exg - p1) / (p99 - p1 + 1e-6), 0.0, 1.0)

    # Cost model: 1.0 (open bare ground / easy traversal) to 5.0 (dense canopy / high impediment)
    cost_surface = 1.0 + 4.0 * exg_norm
    print(f"Cost Surface Grid: {grid_w}x{grid_h} cells | Cell Size: {cell_size:.2f} meters")
    print(f"Cost Values:       Min={cost_surface.min():.2f}, Max={cost_surface.max():.2f}, Mean={cost_surface.mean():.2f}")

    # Coordinate mapping functions
    def utm_to_grid(x, y):
        c = int(np.clip((x - bounds.left) / cell_size_x, 0, grid_w - 1))
        r = int(np.clip((bounds.top - y) / cell_size_y, 0, grid_h - 1))
        return (r, c)

    def grid_to_utm(r, c):
        x = bounds.left + (c + 0.5) * cell_size_x
        y = bounds.top - (r + 0.5) * cell_size_y
        return (x, y)

    # 5. Build 8-Connected Grid Graph with NetworkX
    print("\n=== Step 4: Constructing 8-Connected NetworkX Grid Graph ===")
    G = nx.Graph()
    edges = []
    SQRT2 = math.sqrt(2.0)

    for r in range(grid_h):
        for c in range(grid_w):
            u = (r, c)
            c_u = cost_surface[r, c]
            # 4 forward directions to prevent duplicate edges
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
    print(f"Graph built: {G.number_of_nodes()} grid nodes, {G.number_of_edges()} traversable edges.")

    # 6. Snap Waypoints to Grid Nodes
    print("\n=== Step 5: Snapping Waypoints to Grid Cells ===")
    waypoint_nodes = {}
    waypoint_info = {}

    # Entry point snap
    entry_grid = utm_to_grid(entry_x, entry_y)
    waypoint_nodes["ENTRY"] = entry_grid
    waypoint_info["ENTRY"] = {
        "name": "Ranger Base / Entry Point",
        "tree_id": 0,
        "utm": (entry_x, entry_y),
        "grid": entry_grid,
        "conf": 1.0,
    }
    print(f"  [ENTRY] UTM ({entry_x:.2f}, {entry_y:.2f}) -> Grid Cell (r={entry_grid[0]}, c={entry_grid[1]})")

    # Tree stops snap
    for _, row in gdf_high.iterrows():
        node_id = f"T{row['tree_id']}"
        gx = row["geo_easting"]
        gy = row["geo_northing"]
        t_grid = utm_to_grid(gx, gy)
        waypoint_nodes[node_id] = t_grid
        waypoint_info[node_id] = {
            "name": f"Tree #{row['tree_id']}",
            "tree_id": row["tree_id"],
            "utm": (gx, gy),
            "grid": t_grid,
            "conf": row["confidence"],
            "inside": row["inside_boundary"],
            "reason": row.get("priority_reason", ""),
        }
        print(f"  [{node_id}]  UTM ({gx:.2f}, {gy:.2f}) -> Grid Cell (r={t_grid[0]}, c={t_grid[1]}) | Conf: {row['confidence']:.1%}")

    # 7. Compute Dijkstra Distance Matrix
    print("\n=== Step 6: Computing Dijkstra Least-Cost Distance Matrix ===")
    wp_keys = list(waypoint_nodes.keys())
    dijkstra_matrix = {}
    for u_key in wp_keys:
        dijkstra_matrix[u_key] = {}
        for v_key in wp_keys:
            if u_key == v_key:
                dijkstra_matrix[u_key][v_key] = 0.0
            else:
                d_len = nx.dijkstra_path_length(
                    G, waypoint_nodes[u_key], waypoint_nodes[v_key], weight="weight"
                )
                dijkstra_matrix[u_key][v_key] = d_len

    # 8. Nearest-Neighbor Visiting Order on Dijkstra Matrix
    print("\n=== Step 7: Determining Visiting Order via Nearest-Neighbor Heuristic ===")
    unvisited = set(wp_keys)
    unvisited.remove("ENTRY")

    current_wp = "ENTRY"
    route_sequence = ["ENTRY"]
    legs_info = []
    stitched_utm_coords = []
    total_physical_dist_m = 0.0
    total_weighted_cost = 0.0

    step_idx = 1
    while unvisited:
        # Choose closest unvisited waypoint based on least-cost Dijkstra distance
        next_wp = min(unvisited, key=lambda target: dijkstra_matrix[current_wp][target])
        weighted_cost = dijkstra_matrix[current_wp][next_wp]

        # 9. Reconstruct actual cell-by-cell Dijkstra path
        cell_path = nx.dijkstra_path(
            G, waypoint_nodes[current_wp], waypoint_nodes[next_wp], weight="weight"
        )

        # Convert grid path to UTM coordinates
        leg_utm_coords = [grid_to_utm(r, c) for (r, c) in cell_path]

        # Compute physical path distance along the curved trajectory
        leg_phys_dist = 0.0
        for i in range(len(leg_utm_coords) - 1):
            x1, y1 = leg_utm_coords[i]
            x2, y2 = leg_utm_coords[i + 1]
            leg_phys_dist += math.hypot(x2 - x1, y2 - y1)

        total_physical_dist_m += leg_phys_dist
        total_weighted_cost += weighted_cost

        # Add to stitched continuous route (avoid duplicate joining points)
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
            "path_coords": leg_utm_coords,
        })

        route_sequence.append(next_wp)
        unvisited.remove(next_wp)
        current_wp = next_wp
        step_idx += 1

    # 10. Save Route to GeoJSON (NEW file: OSBS_022_2019_field_route_lcp.geojson)
    print("\n=== Step 8: Saving Least-Cost Route GeoJSON ===")
    route_line_geom = LineString(stitched_utm_coords)

    gdf_route_lcp = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS_022 Terrain-Aware Dijkstra Least-Cost Path",
            "total_physical_distance_meters": round(total_physical_dist_m, 2),
            "total_least_cost_score": round(total_weighted_cost, 2),
            "straight_line_baseline_distance_meters": 54.80,
            "detour_increase_pct": round(((total_physical_dist_m - 54.80) / 54.80) * 100, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([waypoint_info[n]["name"] for n in route_sequence]),
            "cost_surface_model": "Excess Green Index (ExG = 2G - R - B) scaled to [1.0, 5.0]",
            "grid_resolution_meters": round(cell_size, 2),
            "grid_dimensions": f"{grid_w}x{grid_h}",
            "methodology_notes": (
                "8-connected grid graph over 200x200 ExG vegetation impedance surface. "
                "Calculates least-cost path avoiding high-density canopy barriers."
            ),
        }],
        geometry=[route_line_geom],
        crs=raster_crs,
    )
    gdf_route_lcp.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Saved LCP GeoJSON to: {out_route_geojson}")

    # 11. Generate Map Visualization (NEW file: OSBS_022_2019_field_route_lcp_map.png)
    print("\n=== Step 9: Generating High-Resolution LCP Route Map ===")
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)

    # A. Plot RGB base image
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    ax.imshow(rgb_display, extent=extent, origin="upper")

    # B. Overlay semi-transparent vegetation cost surface heatmap
    cost_heatmap = ax.imshow(
        cost_surface,
        extent=extent,
        origin="upper",
        cmap="YlGn_r",
        alpha=0.32,
        vmin=1.0,
        vmax=5.0,
    )
    cbar = plt.colorbar(cost_heatmap, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("Walkability Cost (1.0 = Open Path, 5.0 = Dense Canopy)", fontsize=9)

    # C. Plot Project Boundary
    gdf_boundary = gpd.read_file(boundary_geojson)
    gdf_boundary.boundary.plot(
        ax=ax, color="red", linewidth=2.0, linestyle="--", label="Project Corridor"
    )
    gdf_boundary.plot(ax=ax, facecolor="red", alpha=0.10)

    # D. Plot Non-Target Trees (Context)
    gdf_other = gdf_trees[gdf_trees["verification_priority"] != "HIGH"]
    if not gdf_other.empty:
        gdf_other.plot(
            ax=ax,
            color="lightgreen",
            edgecolor="darkgreen",
            markersize=80,
            linewidth=1.2,
            marker="o",
            alpha=0.85,
            label=f"Medium/Low Priority (Safe, {len(gdf_other)} trees)",
            zorder=4,
        )
        for _, r in gdf_other.iterrows():
            ax.annotate(
                f"T{r['tree_id']}",
                (r["geo_easting"], r["geo_northing"]),
                textcoords="offset points",
                xytext=(5, 5),
                color="black",
                fontsize=8,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.75, ec="gray"),
                zorder=5,
            )

    # E. Plot Winding Dijkstra Route
    xs, ys = zip(*stitched_utm_coords)
    ax.plot(
        xs,
        ys,
        color="cyan",
        linewidth=3.2,
        linestyle="-",
        label=f"Dijkstra Least-Cost Route ({total_physical_dist_m:.1f} m)",
        zorder=6,
    )

    # F. Add Directional Flow Markers along the winding route
    n_pts = len(stitched_utm_coords)
    arrow_indices = [int(n_pts * f) for f in [0.20, 0.45, 0.70, 0.90] if int(n_pts * f) < n_pts - 1]
    for idx in arrow_indices:
        x1, y1 = stitched_utm_coords[idx]
        x2, y2 = stitched_utm_coords[idx + 1]
        dx = x2 - x1
        dy = y2 - y1
        mag = math.hypot(dx, dy)
        if mag > 1e-5:
            ax.annotate(
                "",
                xy=(x2, y2),
                xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color="yellow", lw=2.5, mutation_scale=16),
                zorder=7,
            )

    # G. Plot Entry Point Marker
    ax.scatter(
        [entry_x],
        [entry_y],
        color="deepskyblue",
        edgecolor="black",
        s=260,
        marker="s",
        linewidth=2,
        label="Ranger Entry Point (Start)",
        zorder=8,
    )
    ax.annotate(
        "ENTRY START",
        (entry_x, entry_y),
        textcoords="offset points",
        xytext=(8, 8),
        color="black",
        fontweight="bold",
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", fc="deepskyblue", alpha=0.92, ec="black"),
        zorder=9,
    )

    # H. Plot HIGH Priority Tree Stops
    for stop_num, node_id in enumerate(route_sequence[1:], 1):
        gx, gy = waypoint_info[node_id]["utm"]
        t_id = waypoint_info[node_id]["tree_id"]
        conf = waypoint_info[node_id]["conf"]

        ax.scatter(
            [gx],
            [gy],
            color="yellow",
            edgecolor="red",
            s=220,
            linewidth=2.5,
            marker="o",
            zorder=8,
        )
        ax.annotate(
            f"STOP {stop_num}: Tree #{t_id}\n(Conf: {conf:.1%})",
            (gx, gy),
            textcoords="offset points",
            xytext=(10, 8),
            color="white",
            fontweight="bold",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="red", alpha=0.90, ec="black"),
            zorder=9,
        )

    ax.set_title(
        f"VanDrishti: Terrain-Aware Dijkstra Least-Cost Verification Route (OSBS_022)\n"
        f"Visiting Sequence: Entry -> " + " -> ".join(route_sequence[1:]) + f" | LCP Distance: {total_physical_dist_m:.1f} m",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("UTM Easting (m) [EPSG:32617]", fontsize=10)
    ax.set_ylabel("UTM Northing (m) [EPSG:32617]", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.4, color="white")
    ax.legend(loc="upper left", framealpha=0.9)
    plt.tight_layout()

    plt.savefig(out_route_map, dpi=200)
    plt.close()
    print(f"Saved LCP map to: {out_route_map}")

    # Print Summary Report
    print("\n" + "=" * 90)
    print("             VAN-DRISHTI: TERRAIN-AWARE DIJKSTRA FIELD ROUTE REPORT")
    print("=" * 90)
    print(f"{'Leg':<5} | {'From':<25} | {'To Destination':<16} | {'Steps':<6} | {'Distance (m)':<13} | {'Cumulative (m)'}")
    print("-" * 90)
    for leg in legs_info:
        print(f"{leg['leg']:<5} | {leg['from_name']:<25} | {leg['to_name']:<16} | {leg['grid_steps']:<6} | {leg['physical_dist_m']:<13.2f} | {leg['cumulative_phys_dist_m']:.2f}")
    print("=" * 90)
    print(f"Visiting Order Sequence:       " + " -> ".join([waypoint_info[n]["name"] for n in route_sequence]))
    print(f"Total Least-Cost Path Length:  {total_physical_dist_m:.2f} meters")
    print(f"Straight-Line Baseline Length: 54.80 meters")
    print(f"Detour / Terrain Expansion:    +{total_physical_dist_m - 54.80:.2f} meters (+{((total_physical_dist_m - 54.80) / 54.80) * 100:.1f}%)")
    print(f"Cost Model:                    Excess Green Index (ExG = 2G - R - B) scaled to [1.0, 5.0]")
    print(f"Grid Discretization:           200x200 cells ({cell_size:.2f}m x {cell_size:.2f}m per cell)")
    print("=" * 90)

    return {
        "sequence": route_sequence,
        "lcp_distance_m": total_physical_dist_m,
        "straight_line_dist_m": 54.80,
        "legs": legs_info,
        "cost_surface_shape": (grid_h, grid_w),
        "cell_size_m": cell_size,
        "route_geojson": str(out_route_geojson),
        "route_map": str(out_route_map),
    }


if __name__ == "__main__":
    generate_dijkstra_field_route()
