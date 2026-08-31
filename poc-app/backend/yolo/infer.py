"""
Runs a trained YOLOv8 box detector on one image: detects every box, numbers
them in reading order (top-to-bottom by row, left-to-right within each row —
matches how a person would count a grid of cartons in a photo), draws the
numbered boxes, prints the total count, and saves the annotated image next
to the source.

--- Confidence threshold (--conf) ---
Start at 0.25 (this script's default, and ultralytics' own default). This is
the minimum detection-confidence score a candidate box must clear to be kept
at all.
  - Missing real boxes (false negatives) -> LOWER --conf (e.g. 0.15-0.20).
    You'll likely also pick up a few more false positives as a side effect;
    that's the trade you're making deliberately, not a bug.
  - Phantom boxes on empty background / label text / shadows (false
    positives) -> RAISE --conf (e.g. 0.35-0.50).
  - The right value is genuinely dataset-dependent (how visually distinct
    "box" is from the background in your photos) — there's no universal
    correct number, only "check the annotated output and adjust."

--- NMS IoU threshold (--iou) ---
Start at 0.45 (also ultralytics' default). This controls how much two
candidate boxes are allowed to overlap before non-max suppression treats
them as "the same detection" and keeps only the higher-confidence one.
  - Two boxes drawn around the SAME physical box (duplicate detections) ->
    LOWER --iou (e.g. 0.3), so NMS collapses overlapping candidates more
    aggressively.
  - Two REAL adjacent/touching boxes getting merged into one detection (the
    exact failure this whole switch from OpenCV was meant to fix) -> RAISE
    --iou (e.g. 0.6-0.7), so NMS is more tolerant of legitimate overlap
    between two neighboring true boxes and doesn't suppress one of them.
  - These two failure modes pull in opposite directions — if you're seeing
    BOTH duplicates in one region of the photo AND merged touching-boxes in
    another, that's usually a training-data problem (not enough labeled
    examples of the touching case) rather than something --iou alone can
    fix; add more touching-box examples to dataset/ and retrain.

Usage:
    python infer.py --source path/to/photo.jpg --weights runs/train/weights/best.pt
    python infer.py --source photo.jpg --weights best.pt --conf 0.35 --iou 0.5
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def detect_boxes_yolo(
    image_bytes: bytes,
    weights_path: str,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 640,
) -> list[tuple[int, int, int, int]]:
    """
    Runs YOLO inference on image bytes, returns bounding boxes as
    (x, y, w, h) in original image pixel coordinates — same return shape as
    app/services/real_extraction.py's detect_item_boxes(), on purpose, so
    this is a drop-in replacement for that function's box-detection step
    once you have a trained best.pt (see README.md "Wiring into the live
    app"). Boxes are returned in raw model-order (highest confidence
    first); use sort_reading_order() separately if you want them numbered
    top-to-bottom/left-to-right instead.
    """
    model = YOLO(weights_path)
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is None:
        return []

    results = model.predict(img_cv, conf=conf, iou=iou, imgsz=imgsz, verbose=False)
    boxes: list[tuple[int, int, int, int]] = []
    for r in results:
        for xyxy in r.boxes.xyxy.cpu().numpy():
            x1, y1, x2, y2 = xyxy
            boxes.append((int(x1), int(y1), int(x2 - x1), int(y2 - y1)))
    return boxes


def sort_reading_order(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """
    Orders boxes top-to-bottom by row, left-to-right within each row — the
    order a person counting a grid of cartons in a photo would use, and the
    numbering convention this script draws with. Rows are inferred rather
    than assumed on a fixed grid, since real carton photos are rarely
    perfectly aligned: sort by top-edge y, then greedily group a box into
    the current row if its vertical center falls within half the row's
    reference box height of that row's first box (handles mild tilt/
    misalignment); a bigger vertical jump starts a new row. Each row is
    then sorted left-to-right by x before rows are concatenated.
    """
    if not boxes:
        return []

    by_y = sorted(boxes, key=lambda b: b[1])
    rows: list[list[tuple[int, int, int, int]]] = []
    current_row: list[tuple[int, int, int, int]] = [by_y[0]]
    row_ref_y, row_ref_h = by_y[0][1], by_y[0][3]

    for box in by_y[1:]:
        _, y, _, h = box
        row_center = row_ref_y + row_ref_h / 2
        box_center = y + h / 2
        if abs(box_center - row_center) <= row_ref_h * 0.6:
            current_row.append(box)
        else:
            rows.append(current_row)
            current_row = [box]
            row_ref_y, row_ref_h = y, h

    rows.append(current_row)

    ordered: list[tuple[int, int, int, int]] = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: b[0]))
    return ordered


def draw_numbered_boxes(image_bytes: bytes, boxes: list[tuple[int, int, int, int]]) -> bytes:
    """Same drawing convention as app/services/real_extraction.py::draw_item_boxes
    (numbered red boxes) — kept visually consistent with the rest of the app."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img_cv = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_cv is None:
        return image_bytes
    for i, (x, y, w, h) in enumerate(boxes):
        cv2.rectangle(img_cv, (x, y), (x + w, y + h), (0, 0, 255), 3)
        label = str(i + 1)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img_cv, (x, y), (x + tw + 8, y + th + 10), (0, 0, 255), -1)
        cv2.putText(img_cv, label, (x + 4, y + th + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    ok, buf = cv2.imencode(".jpg", img_cv, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return buf.tobytes() if ok else image_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="path to the image to run inference on")
    parser.add_argument("--weights", required=True, help="path to trained .pt weights (e.g. runs/train/weights/best.pt)")
    parser.add_argument("--conf", type=float, default=0.25, help="confidence threshold — see docstring for tuning")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS IoU threshold — see docstring for tuning")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--out", default=None, help="output path for annotated image (default: <source>_annotated.jpg)")
    args = parser.parse_args()

    source_path = Path(args.source)
    image_bytes = source_path.read_bytes()

    raw_boxes = detect_boxes_yolo(image_bytes, args.weights, conf=args.conf, iou=args.iou, imgsz=args.imgsz)
    boxes = sort_reading_order(raw_boxes)

    print(f"[infer] weights={args.weights}  conf={args.conf}  iou={args.iou}")
    print(f"[infer] TOTAL BOXES DETECTED: {len(boxes)}")

    annotated = draw_numbered_boxes(image_bytes, boxes)
    out_path = Path(args.out) if args.out else source_path.with_name(f"{source_path.stem}_annotated.jpg")
    out_path.write_bytes(annotated)
    print(f"[infer] annotated image written to: {out_path}")


if __name__ == "__main__":
    main()
