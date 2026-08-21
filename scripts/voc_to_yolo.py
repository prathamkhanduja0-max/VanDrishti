"""
voc_to_yolo.py
Converts Pascal VOC XML annotations to YOLO normalized bounding box format (.txt)
and copies corresponding RGB TIFF tiles into data/processed/yolo/ structure.
"""

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def convert_voc_to_yolo(raw_dir: Path, processed_dir: Path, splits: list[str] | None = None):
    if splits is None:
        splits = ["train", "val", "test"]

    summary = {}

    for split in splits:
        raw_split_dir = raw_dir / split
        img_out_dir = processed_dir / "images" / split
        lbl_out_dir = processed_dir / "labels" / split

        img_out_dir.mkdir(parents=True, exist_ok=True)
        lbl_out_dir.mkdir(parents=True, exist_ok=True)

        if not raw_split_dir.exists():
            print(f"Warning: Directory not found: {raw_split_dir}")
            continue

        xml_files = sorted(raw_split_dir.glob("*.xml"))
        images_copied = 0
        labels_created = 0
        total_boxes = 0

        for xml_file in xml_files:
            stem = xml_file.stem
            tree = ET.parse(xml_file)
            root = tree.getroot()

            # Read image dimensions
            size_elem = root.find("size")
            if size_elem is not None:
                width = float(size_elem.findtext("width", "400"))
                height = float(size_elem.findtext("height", "400"))
            else:
                width = 400.0
                height = 400.0

            yolo_lines = []
            for obj in root.findall("object"):
                name = obj.findtext("name", "Tree")
                # Class 0 for Tree
                class_id = 0

                bndbox = obj.find("bndbox")
                if bndbox is None:
                    continue

                xmin = float(bndbox.findtext("xmin"))
                ymin = float(bndbox.findtext("ymin"))
                xmax = float(bndbox.findtext("xmax"))
                ymax = float(bndbox.findtext("ymax"))

                # Convert to YOLO center format: (x_center, y_center, w, h) normalized
                box_w = xmax - xmin
                box_h = ymax - ymin
                x_center = xmin + (box_w / 2.0)
                y_center = ymin + (box_h / 2.0)

                x_center_norm = x_center / width
                y_center_norm = y_center / height
                w_norm = box_w / width
                h_norm = box_h / height

                # Clamp values to [0.0, 1.0] for safety
                x_center_norm = max(0.0, min(1.0, x_center_norm))
                y_center_norm = max(0.0, min(1.0, y_center_norm))
                w_norm = max(0.0, min(1.0, w_norm))
                h_norm = max(0.0, min(1.0, h_norm))

                yolo_lines.append(f"{class_id} {x_center_norm:.6f} {y_center_norm:.6f} {w_norm:.6f} {h_norm:.6f}")
                total_boxes += 1

            # Write YOLO label file
            label_file = lbl_out_dir / f"{stem}.txt"
            with open(label_file, "w", encoding="utf-8") as f:
                if yolo_lines:
                    f.write("\n".join(yolo_lines) + "\n")
                else:
                    # Empty file for images with no objects
                    f.write("")
            labels_created += 1

            # Copy corresponding RGB image
            rgb_filename = root.findtext("filename") or f"{stem}.tif"
            src_img = raw_split_dir / rgb_filename
            if not src_img.exists():
                # Fallback to stem.tif
                src_img = raw_split_dir / f"{stem}.tif"

            if src_img.exists():
                dst_img = img_out_dir / src_img.name
                shutil.copy2(src_img, dst_img)
                images_copied += 1
            else:
                print(f"Warning: Image not found for annotation: {src_img}")

        summary[split] = {
            "xml_files": len(xml_files),
            "labels_created": labels_created,
            "images_copied": images_copied,
            "total_boxes": total_boxes,
        }

    return summary


def main():
    project_root = Path(__file__).resolve().parent.parent
    raw_dir = project_root / "data" / "raw" / "neon"
    processed_dir = project_root / "data" / "processed" / "yolo"

    print(f"Converting VOC XML annotations from: {raw_dir}")
    print(f"Target YOLO directory: {processed_dir}")

    summary = convert_voc_to_yolo(raw_dir, processed_dir)

    print("\n--- Conversion Summary ---")
    for split, counts in summary.items():
        print(f"[{split.upper()}]")
        print(f"  Labels created: {counts['labels_created']}")
        print(f"  Images copied:  {counts['images_copied']}")
        print(f"  Total boxes:    {counts['total_boxes']}")
    print("--------------------------\nDone.")


if __name__ == "__main__":
    main()
