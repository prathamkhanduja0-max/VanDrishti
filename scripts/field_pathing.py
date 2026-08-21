"""
field_pathing.py
Generates an optimized field-verification patrol route for HIGH priority trees
using a nearest-neighbor heuristic on a complete graph (networkx).
Saves route as GeoJSON and creates a map visualization.
"""

import math
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import rasterio
from shapely.geometry import LineString, Point


def generate_field_route():
    project_root = Path(__file__).resolve().parent.parent
    tif_path = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"
    input_geojson = project_root / "results" / "gis" / "OSBS_022_2019_verification_priority.geojson"
    boundary_geojson = project_root / "data" / "demo" / "project_boundary_OSBS_022.geojson"

    gis_results_dir = project_root / "results" / "gis"
    gis_results_dir.mkdir(parents=True, exist_ok=True)

    out_route_geojson = gis_results_dir / "OSBS_022_2019_field_route.geojson"
    out_route_map = gis_results_dir / "OSBS_022_2019_field_route_map.png"

    # 1. Load GeoTIFF to determine entry point and extent
    print("=== Step 1: Defining Ranger Entry Point from Raster Bounds ===")
    with rasterio.open(tif_path) as ds:
        raster_crs = ds.crs
        bounds = ds.bounds
        rgb_data = ds.read([1, 2, 3])
        rgb_img = np.transpose(rgb_data, (1, 2, 0))
        if rgb_img.max() > 1.0:
            rgb_img = rgb_img.astype(np.uint8)

    entry_x = bounds.left
    entry_y = bounds.bottom
    entry_pt = Point(entry_x, entry_y)
    print(f"Ranger Entry Point (Bottom-Left Corner): UTM ({entry_x:.3f} E, {entry_y:.3f} N) [CRS: {raster_crs}]")

    # 2. Load Trees and filter HIGH priority
    print("\n=== Step 2: Filtering Mandatory HIGH Priority Tree Stops ===")
    gdf_trees = gpd.read_file(input_geojson)
    gdf_high = gdf_trees[gdf_trees["verification_priority"] == "HIGH"].copy()
    print(f"Total Trees: {len(gdf_trees)} | HIGH Priority (Mandatory Inspection): {len(gdf_high)}")

    # 3. Build Complete Graph with NetworkX
    print("\n=== Step 3: Building Distance Graph with NetworkX ===")
    G = nx.Graph()

    # Node positions dict
    node_coords = {"ENTRY": (entry_x, entry_y)}
    node_info = {"ENTRY": {"name": "Ranger Base / Entry Point", "tree_id": 0, "conf": 1.0}}

    for _, row in gdf_high.iterrows():
        node_id = f"T{row['tree_id']}"
        gx = row["geo_easting"]
        gy = row["geo_northing"]
        node_coords[node_id] = (gx, gy)
        node_info[node_id] = {
            "name": f"Tree #{row['tree_id']}",
            "tree_id": row["tree_id"],
            "conf": row["confidence"],
            "inside": row["inside_boundary"],
            "reason": row.get("priority_reason", ""),
        }

    # Add all nodes and pairwise Euclidean distance edges
    nodes_list = list(node_coords.keys())
    for i in range(len(nodes_list)):
        for j in range(i + 1, len(nodes_list)):
            u, v = nodes_list[i], nodes_list[j]
            x1, y1 = node_coords[u]
            x2, y2 = node_coords[v]
            dist = math.hypot(x2 - x1, y2 - y1)
            G.add_edge(u, v, weight=dist)

    print(f"Graph constructed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges.")

    # 4. Compute Nearest-Neighbor Route Heuristic
    print("\n=== Step 4: Computing Nearest-Neighbor Patrol Sequence ===")
    unvisited = set(nodes_list)
    unvisited.remove("ENTRY")

    current_node = "ENTRY"
    route_sequence = ["ENTRY"]
    route_segments = []
    total_dist = 0.0

    step_idx = 1
    while unvisited:
        next_node = min(unvisited, key=lambda n: G[current_node][n]["weight"])
        seg_dist = G[current_node][next_node]["weight"]
        total_dist += seg_dist
        route_segments.append({
            "step": step_idx,
            "from_node": current_node,
            "to_node": next_node,
            "from_name": node_info[current_node]["name"],
            "to_name": node_info[next_node]["name"],
            "segment_dist_m": round(seg_dist, 2),
            "cumulative_dist_m": round(total_dist, 2),
        })
        route_sequence.append(next_node)
        unvisited.remove(next_node)
        current_node = next_node
        step_idx += 1

    # 5. Create GeoJSON for Route
    print("\n=== Step 5: Saving Route GeoJSON ===")
    route_line_coords = [node_coords[n] for n in route_sequence]
    route_geom = LineString(route_line_coords)

    gdf_route = gpd.GeoDataFrame(
        [{
            "route_name": "OSBS_022 Field Verification Route",
            "total_distance_meters": round(total_dist, 2),
            "stops_count": len(gdf_high),
            "visiting_sequence": " -> ".join([node_info[n]["name"] for n in route_sequence]),
            "path_type": "Straight-line Euclidean (Nearest-Neighbor Heuristic)",
            "limitation_note": "Calculated via direct straight-line distance; real fieldwork path will conform to local terrain/trail topology.",
        }],
        geometry=[route_geom],
        crs=raster_crs,
    )
    gdf_route.to_file(out_route_geojson, driver="GeoJSON")
    print(f"Saved route GeoJSON to: {out_route_geojson}")

    # 6. Generate Map Visualization
    print("\n=== Step 6: Generating Route Visualization Map ===")
    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)

    # Plot RGB raster background
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    ax.imshow(rgb_img, extent=extent, origin="upper")

    # Plot Project Boundary
    gdf_boundary = gpd.read_file(boundary_geojson)
    gdf_boundary.boundary.plot(ax=ax, color="red", linewidth=2.0, linestyle="--", label="Project Corridor")
    gdf_boundary.plot(ax=ax, facecolor="red", alpha=0.12)

    # Plot Non-High Priority Trees (Context)
    gdf_other = gdf_trees[gdf_trees["verification_priority"] != "HIGH"]
    if not gdf_other.empty:
        gdf_other.plot(
            ax=ax,
            color="lightgreen",
            edgecolor="darkgreen",
            markersize=90,
            linewidth=1.2,
            marker="o",
            alpha=0.8,
            label=f"Medium/Low Priority (Unvisited, {len(gdf_other)} trees)",
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
                bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7, ec="gray"),
                zorder=5,
            )

    # Plot Route Line
    route_xs = [pt[0] for pt in route_line_coords]
    route_ys = [pt[1] for pt in route_line_coords]
    ax.plot(route_xs, route_ys, color="cyan", linewidth=3.0, linestyle="-", label="Inspection Patrol Path", zorder=6)

    # Draw direction arrows on segments
    for i in range(len(route_line_coords) - 1):
        x1, y1 = route_line_coords[i]
        x2, y2 = route_line_coords[i + 1]
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        dx = (x2 - x1) * 0.15
        dy = (y2 - y1) * 0.15
        ax.annotate(
            "",
            xy=(mid_x + dx, mid_y + dy),
            xytext=(mid_x - dx, mid_y - dy),
            arrowprops=dict(arrowstyle="->", color="yellow", lw=2.5, mutation_scale=18),
            zorder=7,
        )

    # Plot Entry Point
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
        bbox=dict(boxstyle="round,pad=0.3", fc="deepskyblue", alpha=0.9, ec="black"),
        zorder=9,
    )

    # Plot HIGH Priority Trees & Numbered Stop Badges
    for stop_num, node_id in enumerate(route_sequence[1:], 1):
        gx, gy = node_coords[node_id]
        t_id = node_info[node_id]["tree_id"]
        conf = node_info[node_id]["conf"]

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
            bbox=dict(boxstyle="round,pad=0.3", fc="red", alpha=0.88, ec="black"),
            zorder=9,
        )

    ax.set_title(
        f"VanDrishti: Field-Verification Patrol Route (OSBS_022)\n"
        f"Sequence: Entry -> " + " -> ".join(route_sequence[1:]) + f" | Total Distance: {total_dist:.1f} m",
        fontsize=12,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel(f"UTM Easting (m) [{raster_crs}]", fontsize=10)
    ax.set_ylabel(f"UTM Northing (m) [{raster_crs}]", fontsize=10)
    ax.grid(True, linestyle=":", alpha=0.4, color="white")
    ax.legend(loc="upper left", framealpha=0.9)
    plt.tight_layout()

    plt.savefig(out_route_map, dpi=200)
    plt.close()
    print(f"Saved route map to: {out_route_map}")

    # Summary Output Table
    print("\n" + "=" * 82)
    print("                 VAN-DRISHTI: FIELD PATROL ITINERARY")
    print("=" * 82)
    print(f"{'Leg':<5} | {'From':<20} | {'To Destination':<20} | {'Leg Dist (m)':<12} | {'Total Dist (m)'}")
    print("-" * 82)
    for seg in route_segments:
        print(f"{seg['step']:<5} | {seg['from_name']:<20} | {seg['to_name']:<20} | {seg['segment_dist_m']:<12.2f} | {seg['cumulative_dist_m']:.2f}")
    print("=" * 82)
    print(f"Total Inspection Path Length: {total_dist:.2f} meters")
    print(f"Route Visiting Order:         " + " -> ".join([node_info[n]["name"] for n in route_sequence]))
    print(f"Note: Edge weights use Euclidean distance in meters; actual field routing may vary based on terrain/trails.")
    print("=" * 82)

    return {
        "sequence": route_sequence,
        "total_distance_m": total_dist,
        "segments": route_segments,
        "route_geojson": str(out_route_geojson),
        "route_map": str(out_route_map),
    }


if __name__ == "__main__":
    generate_field_route()
