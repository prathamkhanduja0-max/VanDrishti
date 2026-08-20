"""
train_yolov8.py
Trains a YOLOv8 nano model on NEON RGB dataset,
evaluates validation metrics, runs inference on test images,
and saves prediction CSVs and visualizations.
"""

from pathlib import Path
import pandas as pd
from PIL import Image, ImageDraw
from ultralytics import YOLO


def main():
    project_root = Path("C:/VanDrishtiProject")
    dataset_yaml = project_root / "data" / "processed" / "yolo" / "dataset.yaml"
    results_dir = project_root / "results" / "yolov8"
    test_dir = project_root / "data" / "processed" / "yolo" / "images" / "test"

    results_dir.mkdir(parents=True, exist_ok=True)

    print("=== Step 1: Starting YOLOv8 Nano Training ===")
    model = YOLO("yolov8n.pt")

    train_results = model.train(
        data=str(dataset_yaml),
        epochs=50,
        imgsz=400,
        batch=2,
        project=str(results_dir),
        name="train",
        exist_ok=True,
        workers=0,
        device="cpu",
        verbose=True,
    )

    weights_dir = results_dir / "train" / "weights"
    best_weights = weights_dir / "best.pt"
    if not best_weights.exists():
        best_weights = weights_dir / "last.pt"

    print(f"\nTraining completed. Weights saved to: {best_weights}")

    # Read training metrics
    metrics_csv = results_dir / "train" / "results.csv"
    if metrics_csv.exists():
        df_metrics = pd.read_csv(metrics_csv)
        # Strip whitespace from column names
        df_metrics.columns = df_metrics.columns.str.strip()
        last_row = df_metrics.iloc[-1]
        
        # Look for metric column names
        p_col = [c for c in df_metrics.columns if "precision(B)" in c or "precision" in c.lower()]
        r_col = [c for c in df_metrics.columns if "recall(B)" in c or "recall" in c.lower()]
        map50_col = [c for c in df_metrics.columns if "mAP50(B)" in c or "map50" in c.lower()]
        map50_95_col = [c for c in df_metrics.columns if "mAP50-95(B)" in c or "map50-95" in c.lower()]

        precision_val = last_row[p_col[0]] if p_col else "N/A"
        recall_val = last_row[r_col[0]] if r_col else "N/A"
        map50_val = last_row[map50_col[0]] if map50_col else "N/A"
        map50_95_val = last_row[map50_95_col[0]] if map50_95_col else "N/A"
    else:
        precision_val = "N/A"
        recall_val = "N/A"
        map50_val = "N/A"
        map50_95_val = "N/A"

    print("\n=== Step 2: Running Inference on Test Images ===")
    trained_model = YOLO(str(best_weights))

    test_images = [
        test_dir / "OSBS_022_2019.tif",
        test_dir / "OSBS_023_2019.tif",
    ]

    test_summary = {}

    for img_path in test_images:
        stem = img_path.stem
        print(f"\nInference on {img_path.name}...")

        # Predict
        preds = trained_model.predict(
            source=str(img_path),
            imgsz=400,
            conf=0.25,
            device="cpu",
            save=False,
            verbose=False,
        )[0]

        csv_path = results_dir / f"{stem}_preds.csv"
        viz_path = results_dir / f"{stem}_viz.png"

        # Extract detections
        boxes_data = []
        image = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        if preds.boxes is not None and len(preds.boxes) > 0:
            for box in preds.boxes:
                xyxy = box.xyxy[0].tolist()  # [xmin, ymin, xmax, ymax]
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                label_name = trained_model.names.get(cls_id, "Tree")

                xmin, ymin, xmax, ymax = xyxy
                boxes_data.append({
                    "xmin": xmin,
                    "ymin": ymin,
                    "xmax": xmax,
                    "ymax": ymax,
                    "label": label_name,
                    "score": conf,
                })

                # Draw box on image
                draw.rectangle([xmin, ymin, xmax, ymax], outline="cyan", width=2)
                draw.text((xmin + 3, ymin + 3), f"{conf:.2f}", fill="cyan")

            df_preds = pd.DataFrame(boxes_data)
            df_preds.to_csv(csv_path, index=False)
            count = len(df_preds)
            avg_conf = float(df_preds["score"].mean())
        else:
            df_preds = pd.DataFrame(columns=["xmin", "ymin", "xmax", "ymax", "label", "score"])
            df_preds.to_csv(csv_path, index=False)
            count = 0
            avg_conf = 0.0

        image.save(viz_path, "PNG")
        print(f"  Saved CSV: {csv_path}")
        print(f"  Saved Viz: {viz_path}")
        print(f"  Detections: {count}, Avg Conf: {avg_conf:.4f}")

        test_summary[stem] = {
            "count": count,
            "avg_conf": avg_conf,
            "detections": boxes_data,
            "csv_path": str(csv_path),
            "viz_path": str(viz_path),
        }

    print("\n======================= YOLOV8 TRAINING & EVALUATION REPORT =======================")
    print(f"Trained Weights: {best_weights}")
    print(f"Training Metrics (Epoch 50):")
    print(f"  - Precision: {precision_val}")
    print(f"  - Recall:    {recall_val}")
    print(f"  - mAP50:     {map50_val}")
    print(f"  - mAP50-95:  {map50_95_val}")
    print("\nTest Image Results:")
    for stem, stats in test_summary.items():
        print(f"  [{stem}]")
        print(f"    - Trees Detected: {stats['count']}")
        print(f"    - Avg Confidence: {stats['avg_conf']:.4f}")
        for idx, d in enumerate(stats['detections'], 1):
            print(f"      Box {idx}: [{d['xmin']:.1f}, {d['ymin']:.1f}, {d['xmax']:.1f}, {d['ymax']:.1f}] -> Conf: {d['score']:.4f}")
    print("====================================================================================")


if __name__ == "__main__":
    main()
