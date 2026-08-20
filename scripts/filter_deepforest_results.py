"""
filter_deepforest_results.py
Filters DeepForest predictions by a confidence threshold (>= 0.40),
saves filtered CSVs, and generates filtered visualization images.
"""

from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw


def filter_predictions(threshold: float = 0.4):
    project_root = Path("C:/VanDrishtiProject")
    img_dir = project_root / "data" / "processed" / "yolo" / "images" / "test"
    results_dir = project_root / "results" / "deepforest"

    test_stems = ["OSBS_022_2019", "OSBS_023_2019"]
    report = {}

    for stem in test_stems:
        csv_path = results_dir / f"{stem}_preds.csv"
        img_path = img_dir / f"{stem}.tif"
        out_csv_path = results_dir / f"{stem}_preds_filtered.csv"
        out_viz_path = results_dir / f"{stem}_viz_filtered.png"

        if not csv_path.exists():
            print(f"Error: {csv_path} does not exist.")
            continue

        df = pd.read_csv(csv_path)
        orig_count = len(df)

        score_col = "score" if "score" in df.columns else ("confidence" if "confidence" in df.columns else None)
        if score_col:
            df_filtered = df[df[score_col] >= threshold].copy()
        else:
            df_filtered = df.copy()

        filtered_count = len(df_filtered)
        avg_score = float(df_filtered[score_col].mean()) if filtered_count > 0 and score_col else 0.0

        # Save filtered CSV
        df_filtered.to_csv(out_csv_path, index=False)

        # Draw filtered visualization
        if img_path.exists():
            image = Image.open(img_path).convert("RGB")
            draw = ImageDraw.Draw(image)

            for _, row in df_filtered.iterrows():
                xmin = float(row["xmin"])
                ymin = float(row["ymin"])
                xmax = float(row["xmax"])
                ymax = float(row["ymax"])
                score = float(row[score_col]) if score_col else 1.0

                draw.rectangle([xmin, ymin, xmax, ymax], outline="lime", width=2)
                draw.text((xmin + 3, ymin + 3), f"{score:.2f}", fill="lime")

            image.save(out_viz_path, "PNG")
        else:
            print(f"Warning: Image not found at {img_path}")

        report[stem] = {
            "original_count": orig_count,
            "filtered_count": filtered_count,
            "avg_confidence": avg_score,
            "csv_path": str(out_csv_path),
            "viz_path": str(out_viz_path),
        }

    return report


def main():
    print("Filtering DeepForest predictions (threshold >= 0.40)...")
    report = filter_predictions(threshold=0.4)

    print("\n================== FILTERED RESULTS (Threshold >= 0.40) ==================")
    for stem, stats in report.items():
        print(f"\nImage: {stem}")
        print(f"  Original Detections: {stats['original_count']}")
        print(f"  Filtered Detections: {stats['filtered_count']} (removed {stats['original_count'] - stats['filtered_count']})")
        print(f"  Avg Confidence:      {stats['avg_confidence']:.4f}")
        print(f"  Filtered CSV:        {stats['csv_path']}")
        print(f"  Filtered Viz:        {stats['viz_path']}")
    print("==========================================================================")


if __name__ == "__main__":
    main()
