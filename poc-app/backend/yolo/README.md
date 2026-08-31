# YOLOv8 box-counting pipeline

Replaces the classical OpenCV contour pipeline (`app/services/real_extraction.py::detect_item_boxes`)
for the two failure modes it structurally can't solve — a box that's a different color
from the rest, and boxes touching edge-to-edge with no visible gap. A learned detector
doesn't rely on edge/threshold heuristics for either case; it just needs to have seen
examples of both during training.

**Status: tooling only, no trained model yet.** Nothing in the live app
(`poc-app/backend/app/`) has been switched over — there's no `best.pt` to switch to
until you label data and train. `infer.py` is written so that once `runs/train/weights/best.pt`
exists, wiring it into `app/services/real_extraction.py` is a small, mechanical change (see
"Wiring into the live app" at the bottom).

Environment already verified working in this repo's Python (3.14, CPU-only — no CUDA
GPU on this machine):

```
pip install ultralytics
```

Installed: `ultralytics==8.4.129`, `torch==2.13.0+cpu`. Training will run on CPU; see
the time-budget note in `train.py`'s docstring before you kick off a big run.

---

## 1. Labeling workflow

You need ~20-30 photos of boxes-in-a-carton, each with every visible box's bounding
box drawn and labeled `box` (single class). Quantity over precision at this stage:
20-30 *varied* photos (different lighting, density, the dark-box case, the touching-pair
case, different angles) will generalize far better than 30 near-duplicate photos.

### Option A — Roboflow (recommended, easiest export)

1. Go to roboflow.com, create a free account, create a new project — **Object
   Detection**, single class.
2. Upload your 20-30 source images.
3. Annotate: draw a box around every physical carton/box in each image, label every
   one `box`. Roboflow's "smart polygon"/box-assist tools can speed this up but check
   each one — a wrong box here is training-data noise.
4. Split: Roboflow's default 70/20/10 train/val/test is fine for a dataset this small;
   for 20-30 images you can also do a manual 80/20 train/val split (test set isn't
   worth carving out separately at this size).
5. **Generate a version**, then **Export** → format **"YOLOv8"** (this is the
   `YOLOv5 PyTorch` / Ultralytics txt-label format — one `.txt` file per image,
   normalized `class x_center y_center width height`, one line per box).
6. Download the exported zip. It contains `train/images`, `train/labels`,
   `valid/images`, `valid/labels`, and its own `data.yaml`.
7. Copy the contents into this repo's `dataset/` folder so the layout matches:
   ```
   yolo/dataset/images/train/*.jpg
   yolo/dataset/images/val/*.jpg      (Roboflow's "valid" -> rename to "val")
   yolo/dataset/labels/train/*.txt
   yolo/dataset/labels/val/*.txt
   ```
   The `data.yaml` already in this folder points at those paths — you can ignore
   Roboflow's own generated `data.yaml` (or diff it against this one if your class
   name/order differs).

### Option B — LabelImg (fully local, no account)

1. `pip install labelImg` then run `labelImg`.
2. Open your image directory. In LabelImg's toolbar, set save format to **YOLO**
   (not the default PascalVOC) — there's a button that toggles between them, confirm
   it says "YOLO" before you start.
3. For each image: press `W` to draw a box, drag around each physical box in the
   photo, type/select the class name `box`, repeat for every box in that image, then
   `Ctrl+S` to save and move to the next image (`D`).
4. This produces one `.txt` label file per image directly next to the image, plus a
   `classes.txt` (should contain exactly one line: `box`). Split the images+labels
   80/20 yourself into `dataset/images/train` + `dataset/labels/train` and
   `dataset/images/val` + `dataset/labels/val` (move matching image/label pairs
   together — same base filename, `.jpg` + `.txt`).

### Label file format (either tool produces this — good to know for sanity-checking)

One `.txt` per image, same base filename as the image, one line per box:
```
0 0.4234 0.5512 0.0821 0.1103
```
`0` = class index (only class here is `box` = 0), then `x_center y_center width
height`, all normalized to [0, 1] relative to image width/height. An image with no
boxes gets an empty `.txt` file (shouldn't happen for this dataset, but ultralytics
tolerates it as a "background" example if it ever does).

### Sanity-check your labels before training

Bad labels silently produce a bad model with no error message. Quick visual check:

```python
from ultralytics.data.utils import visualize_image_annotations
# or simpler — just run infer.py's draw_boxes() against your own label files
# by converting normalized coords to pixel coords and drawing them, same as
# you'd do for a prediction. Eyeball a handful before spending training time.
```
The cheapest real check: open a few `dataset/images/train/*.jpg` files next to their
`.txt` in LabelImg or Roboflow's own preview — confirm boxes are tight around each
carton, not offset, not doubled, not missing the dark box or the touching pair (the
two cases this whole switch exists for — make sure your 20-30 images actually include
several examples of each, not just easy well-lit uniform grids).

---

## 2. Training

```
python train.py
```

See `train.py` for the full command and every flag's reasoning (epochs, imgsz, batch,
patience). Defaults: `yolov8n.pt` pretrained weights, `imgsz=640`, `epochs=100` with
early-stopping `patience=20` (small dataset — more epochs than a large-dataset run
needs, but early stopping means it won't actually run all 100 if val loss plateaus
sooner, which it likely will well before 100 given the dataset size).

Output lands in `runs/train/weights/best.pt` (best val performance) and `last.pt`
(final epoch) — `best.pt` is what `infer.py` and the live app should use.

## 3. Inference

```
python infer.py --source path/to/photo.jpg --weights runs/train/weights/best.pt
```

Draws numbered boxes (same left-to-right/top-to-bottom convention as the existing
`draw_item_boxes` in the main app), prints the total count, and saves the annotated
image next to the source. See `infer.py`'s docstring for the confidence/IoU threshold
guidance and how to tune them.

## Wiring into the live app (once you have a trained best.pt)

`infer.py`'s `detect_boxes_yolo(image_bytes, weights_path, conf, iou)` function
returns the same `list[tuple[x, y, w, h]]` shape that
`app/services/real_extraction.py::detect_item_boxes()` already returns, on purpose —
so swapping the box-detection step in `extract_via_opencv()` for a YOLO call is a
same-shape drop-in, not a rewrite of the pipeline around it (OCR-per-box, majority
voting, annotated-image drawing all stay as-is). Copy `runs/train/weights/best.pt`
somewhere under `app/` (e.g. `app/models/box_detector.pt`), then swap the one call
site — flag this to whoever's doing that edit next, it's intentionally left as a
manual step until there's an actual trained weights file to point at.
