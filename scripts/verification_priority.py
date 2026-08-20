"""
verification_priority.py
Computes field-verification priority for detected tree canopies based on:
1. Detection confidence thresholds (<0.50: HIGH, 0.50-0.65: MEDIUM, >0.65: LOW)
2. Project boundary impact status (trees INSIDE corridor are automatically escalated to HIGH priority)
Saves updated GeoJSON and prints sorted field checklists.
"""

from pathlib import Path
import geopandas as gpd
import pandas as pd


def determine_priority(row):
    conf = row["confidence"]
    inside = row["inside_boundary"]

    # Base priority by confidence
    if conf < 0.50:
        base_priority = "HIGH"
        reason = "Low detection confidence (< 0.50)"
    elif 0.50 <= conf <= 0.65:
        base_priority = "MEDIUM"
        reason = "Moderate detection confidence (0.50 - 0.65)"
    else:
        base_priority = "LOW"
        reason = "High detection confidence (> 0.65)"

    # Boundary impact rule (escalates to HIGH)
    if inside:
        final_priority = "HIGH"
        if base_priority == "HIGH":
            reason = "Inside project corridor (corridor impact) & Low confidence"
        else:
            reason = f"Inside project corridor (corridor impact, statutory check) [Base: {base_priority}]"
    else:
        final_priority = base_priority

    return pd.Series([final_priority, reason], index=["verification_priority", "priority_reason"])


def run_verification_priority():
    project_root = Path("C:/VanDrishtiProject")
    input_geojson = project_root / "results" / "gis" / "OSBS_022_2019_trees_with_boundary_status.geojson"
    out_geojson = project_root / "results" / "gis" / "OSBS_022_2019_verification_priority.geojson"

    if not input_geojson.exists():
        raise FileNotFoundError(f"Input file not found: {input_geojson}")

    print(f"Loading geocoded tree status from: {input_geojson.name}")
    gdf = gpd.read_file(input_geojson)

    # Apply priority logic
    priority_df = gdf.apply(determine_priority, axis=1)
    gdf["verification_priority"] = priority_df["verification_priority"]
    gdf["priority_reason"] = priority_df["priority_reason"]

    # Priority sort key (HIGH = 1, MEDIUM = 2, LOW = 3)
    priority_order = {"HIGH": 1, "MEDIUM": 2, "LOW": 3}
    gdf["priority_rank"] = gdf["verification_priority"].map(priority_order)

    # Save to updated GeoJSON
    gdf.to_file(out_geojson, driver="GeoJSON")
    print(f"Saved updated verification priority GeoJSON to: {out_geojson}\n")

    # Sort for Field Checklist
    gdf_sorted = gdf.sort_values(by=["priority_rank", "inside_boundary", "confidence"], ascending=[True, False, True])

    print("=" * 88)
    print("                      VAN-DRISHTI: FIELD-VERIFICATION CHECKLIST")
    print("=" * 88)
    print(f"{'Tree ID':<9} | {'Confidence':<10} | {'Corridor Status':<17} | {'Priority':<10} | {'Rationale / Action'}")
    print("-" * 88)
    for _, r in gdf_sorted.iterrows():
        status_text = "INSIDE (AFFECTED)" if r["inside_boundary"] else "OUTSIDE (SAFE)"
        print(f"Tree #{r['tree_id']:<3} | {r['confidence']:<10.2%} | {status_text:<17} | {r['verification_priority']:<10} | {r['priority_reason']}")
    print("=" * 88)

    # Summary counts
    priority_counts = gdf["verification_priority"].value_counts()
    print("\nPriority Breakdown:")
    for p in ["HIGH", "MEDIUM", "LOW"]:
        cnt = priority_counts.get(p, 0)
        print(f"  - {p} Priority:   {cnt} tree(s)")

    return gdf_sorted


if __name__ == "__main__":
    run_verification_priority()
