"""
Trains YOLOv8n on the single-class "box" dataset in dataset/ (see README.md
for how to produce that dataset via Roboflow or LabelImg).

Parameter choices, and why:

- model="yolov8n.pt" (nano): smallest/fastest YOLOv8 variant. Right call for
  a single-class, small (~20-30 image), simple-shape (rectangular cartons,
  no fine-grained sub-class distinction) detection task — a bigger model
  (s/m/l) needs more data to avoid overfitting and trains much slower on
  CPU, without a clear accuracy win for a problem this simple. Revisit only
  if yolov8n's val mAP is clearly underfitting after you have real data.

- imgsz=640: YOLOv8's standard default and a good match for carton photos
  (enough resolution to tell touching boxes apart at their shared edge,
  the exact case this whole switch is for). Only increase if the photos are
  very high-resolution and small objects are getting missed after a first
  training run (imgsz=960/1280 costs roughly proportionally more time).

- epochs=100 with patience=20: 100 is a generous ceiling for a small
  dataset, not a real expectation of training that long — patience=20
  (early stopping: stop if val loss hasn't improved in 20 epochs) means the
  actual run will almost certainly stop well before 100 once it converges,
  which is normal and fine, not a failure.

- batch=8: conservative default for CPU training on ~20-30 images (a handful
  of batches per epoch). Raise it if you have more images and RAM to spare;
  lower it (4 or even 2) if you hit an out-of-memory error.

- CPU TIME BUDGET (read this before you kick off a long run): this
  environment has no CUDA GPU (`torch.cuda.is_available()` is False here).
  YOLOv8n on ~20-30 images at imgsz=640 on CPU is roughly a few minutes per
  epoch depending on your machine — a full 100-epoch run could be over an
  hour, though early stopping will likely cut it well short of that. If
  it's too slow: (a) train in Google Colab's free GPU tier instead — same
  `yolo train ...` command, just upload dataset/ and download best.pt back,
  or (b) reduce imgsz to 416/480 for a rougher but much faster first pass to
  sanity-check your labels before committing to a full run.

Run:
    python train.py
Or override any parameter from the CLI, e.g.:
    python train.py --epochs 60 --imgsz 480 --batch 4
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="yolov8n.pt", help="pretrained weights to start from")
    parser.add_argument("--data", default=str(HERE / "data.yaml"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--patience", type=int, default=20, help="early-stop if val loss plateaus this many epochs")
    parser.add_argument("--project", default=str(HERE / "runs"))
    parser.add_argument("--name", default="train")
    args = parser.parse_args()

    train_images = HERE / "dataset" / "images" / "train"
    n_images = len(list(train_images.glob("*"))) if train_images.exists() else 0
    if n_images == 0:
        raise SystemExit(
            f"No training images found in {train_images}. "
            "Follow README.md's labeling workflow first — this script trains "
            "on whatever is actually in dataset/, it doesn't come with data."
        )
    print(f"Training on {n_images} images found in {train_images}")

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        project=args.project,
        name=args.name,
    )
    print(f"\nDone. Best weights: {Path(args.project) / args.name / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()
