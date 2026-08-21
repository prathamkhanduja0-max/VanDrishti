"""
run_deepforest_baseline.py
Runs pretrained DeepForest release model on test images,
saves predicted bounding boxes to CSV files, and saves visualization PNGs.
"""

from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw
from deepforest.main import deepforest


def run_baseline():
    project_root = Path(__file__).resolve().parent.parent
    test_dir = project_root / "data" / "processed" / "yolo" / "images" / "test"
    results_dir = project_root / "results" / "deepforest"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("Initializing DeepForest release model...")
    model = deepforest()
    if hasattr(model, "use_release"):
        model.use_release()

    test_images = [
        test_dir / "OSBS_022_2019.tif",
        test_dir / "OSBS_023_2019.tif",
    ]

    report = {}

    for img_path in test_images:
        stem = img_path.stem
        print(f"\nProcessing {img_path.name}...")

        if not img_path.exists():
            print(f"Error: Image not found: {img_path}")
            continue

        # Run prediction
        preds = model.predict_image(path=str(img_path))

        csv_path = results_dir / f"{stem}_preds.csv"
        viz_path = results_dir / f"{stem}_viz.png"

        # Load image for drawing
        image = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        if preds is not None and not preds.empty:
            # Format and save CSV
            cols_to_save = [c for c in ["xmin", "ymin", "xmax", "ymax", "label", "score"] if c in preds.columns]
            preds[cols_to_save].to_csv(csv_path, index=False)
            count = len(preds)
            score_col = "score" if "score" in preds.columns else ("confidence" if "confidence" in preds.columns else None)
            avg_score = float(preds[score_col].mean()) if score_col else 0.0

            for _, row in preds.iterrows():
                xmin = float(row["xmin"])
                ymin = float(row["ymin"])
                xmax = float(row["xmax"])
                ymax = float(row["ymax"])
                score = float(row[score_col]) if score_col else 1.0

                draw.rectangle([xmin, ymin, xmax, ymax], outline="yellow", width=2)
                draw.text((xmin + 3, ymin + 3), f"{score:.2f}", fill="yellow")
        else:
            pd.DataFrame(columns=["xmin", "ymin", "xmax", "ymax", "label", "score"]).to_csv(csv_path, index=False)
            count = 0
            avg_score = 0.0

        image.save(viz_path, "PNG")
        print(f"Saved predictions CSV to: {csv_path}")
        print(f"Saved visualization to: {viz_path}")
        print(f"Detected trees: {count}, Avg confidence: {avg_score:.4f}")

        report[stem] = {
            "count": count,
            "avg_score": avg_score,
            "csv": str(csv_path),
            "viz": str(viz_path),
        }

    return report


if __name__ == "__main__":
    report = run_baseline()
    print("\n================== DEEPFOREST BASELINE RESULTS ==================")
    for stem, stats in report.items():
        print(f"File: {stem}")
        print(f"  Trees Detected:     {stats['count']}")
        print(f"  Average Confidence: {stats['avg_score']:.4f}")
        print(f"  Predictions CSV:    {stats['csv']}")
        print(f"  Visualization PNG:  {stats['viz']}")
    print("=================================================================")
