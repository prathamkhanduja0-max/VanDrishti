"""
visualize_check.py
Visualizes YOLO normalized bounding boxes on an image to verify conversion accuracy.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def visualize_yolo_annotation(
    image_path: Path,
    label_path: Path,
    output_path: Path,
    box_color: str = "red",
    box_width: int = 2,
):
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load Image
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found at {image_path}")
    image = Image.open(image_path).convert("RGB")
    img_w, img_h = image.size

    # 2. Read Labels
    if not label_path.exists():
        raise FileNotFoundError(f"Label file not found at {label_path}")

    with open(label_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    draw = ImageDraw.Draw(image)

    print(f"Image: {image_path.name} ({img_w}x{img_h})")
    print(f"Labels ({len(lines)} objects):")

    # 3 & 4. Convert YOLO coords to pixel coords and draw boxes
    for idx, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) != 5:
            continue

        cls_id = int(parts[0])
        xc, yc, w, h = map(float, parts[1:])

        # Convert back to pixel coordinates
        box_w = w * img_w
        box_h = h * img_h
        xmin = (xc * img_w) - (box_w / 2.0)
        ymin = (yc * img_h) - (box_h / 2.0)
        xmax = (xc * img_w) + (box_w / 2.0)
        ymax = (yc * img_h) + (box_h / 2.0)

        # Round to integers for display / drawing
        xmin_r, ymin_r, xmax_r, ymax_r = round(xmin), round(ymin), round(xmax), round(ymax)
        print(f"  Box {idx}: class={cls_id} -> [xmin={xmin_r}, ymin={ymin_r}, xmax={xmax_r}, ymax={ymax_r}]")

        draw.rectangle([xmin, ymin, xmax, ymax], outline=box_color, width=box_width)
        draw.text((xmin + 3, ymin + 3), f"Tree", fill=box_color)

    # 5. Save Output
    image.save(output_path, "PNG")
    print(f"Saved visualization to: {output_path}")


def main():
    project_root = Path(__file__).resolve().parent.parent
    image_path = project_root / "data" / "processed" / "yolo" / "images" / "test" / "OSBS_022_2019.tif"
    label_path = project_root / "data" / "processed" / "yolo" / "labels" / "test" / "OSBS_022_2019.txt"
    output_path = project_root / "data" / "processed" / "yolo" / "visual_checks" / "OSBS_022_2019_check.png"

    visualize_yolo_annotation(image_path, label_path, output_path)


if __name__ == "__main__":
    main()
