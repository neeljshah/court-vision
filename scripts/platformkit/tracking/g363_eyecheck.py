"""G363 eye check: 30 evenly spaced native frames carrying the blind ratings and
the winner arm's output side by side.

Contract A3: the 30 frames are drawn evenly over the whole scored held-out set,
sorted by game, section and frame index, never from its head.  Every rater row is
drawn, including the adjudicator's, so a reader can see what the reference was and
what the arm did about it.  Rater centres are recorded in sheet pixels and are
converted to native pixels here with the archived sheet_scale.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
import sys
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import file_sha256, read_csv, write_csv

MAX_BYTES = 200_000
N_SHEETS = 30
COLOURS = {"terra": (60, 200, 60), "sol": (60, 200, 255), "ADJUDICATOR": (255, 120, 60)}
PRED_COLOUR = (0, 0, 255)
FIELDS = ("rank", "frame_key", "split", "game", "section", "frame_index", "reference_label",
          "arm", "n_predictions", "file", "sha256", "bytes")


def evenly(rows: list[dict], count: int) -> list[dict]:
    """Evenly spaced picks across the whole ordered set; never a head slice."""
    ordered = sorted(rows, key=lambda row: (row["game"], row["section"], int(row["frame_index"])))
    if len(ordered) <= count:
        return ordered
    step = len(ordered) / float(count)
    return [ordered[min(len(ordered) - 1, int(round(index * step)))] for index in range(count)]


def draw(cv2, image, ratings: list[dict], preds: list[dict], scale: float, caption: str):
    """Overlay every blind rating and every scored prediction on the native frame."""
    font, line = cv2.FONT_HERSHEY_SIMPLEX, cv2.LINE_AA
    y_text = 34
    cv2.putText(image, caption, (12, y_text), font, 1.0, (0, 0, 0), 5, line)
    cv2.putText(image, caption, (12, y_text), font, 1.0, (255, 255, 255), 2, line)
    for row in ratings:
        colour = COLOURS.get(row["rater"], (200, 200, 200))
        y_text += 32
        note = f"{row['rater']}: {row['label']}"
        if row.get("cx"):
            cx, cy = float(row["cx"]) / scale, float(row["cy"]) / scale
            cv2.circle(image, (int(cx), int(cy)), 26, colour, 3, line)
            cv2.line(image, (int(cx) - 34, int(cy)), (int(cx) + 34, int(cy)), colour, 1, line)
            note += f" ({int(cx)},{int(cy)})"
        cv2.putText(image, note, (12, y_text), font, 0.8, (0, 0, 0), 4, line)
        cv2.putText(image, note, (12, y_text), font, 0.8, colour, 2, line)
    for row in preds:
        x, y = int(float(row["x"])), int(float(row["y"]))
        half_w, half_h = int(float(row["w"])) // 2, int(float(row["h"])) // 2
        cv2.rectangle(image, (x - half_w, y - half_h), (x + half_w, y + half_h), PRED_COLOUR, 3)
        note = f"{row['arm']} rank{row['rank']} {row['score']}"
        cv2.putText(image, note, (x - half_w, max(14, y - half_h - 8)), font, 0.7, (0, 0, 0), 4, line)
        cv2.putText(image, note, (x - half_w, max(14, y - half_h - 8)), font, 0.7, PRED_COLOUR, 2, line)
    return image


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="g363_eyecheck")
    parser.add_argument("--frames", required=True)
    parser.add_argument("--ratings", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--split", default="heldout")
    parser.add_argument("--out", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)

    import cv2

    cv2.setNumThreads(1)
    frames = [row for row in read_csv(Path(args.frames)) if row["split"] == args.split]
    ratings: dict[str, list[dict]] = {}
    for row in read_csv(Path(args.ratings)):
        ratings.setdefault(row["frame_key"], []).append(row)
    preds: dict[str, list[dict]] = {}
    for row in read_csv(Path(args.predictions)):
        if row["arm"] == args.arm and row["tick_history"] == "OBSERVED":
            preds.setdefault(row["frame_key"], []).append(row)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for index, row in enumerate(evenly(frames, N_SHEETS)):
        image = cv2.imread(str(Path(args.cache) / (row["frame_key"] + ".png")))
        if image is None:
            print("ABSENT-CACHE " + row["frame_key"])
            continue
        rows = sorted(ratings.get(row["frame_key"], []), key=lambda item: item["rater"])
        found = sorted(preds.get(row["frame_key"], []), key=lambda item: int(item["rank"]))
        reference = next((item["label"] for item in rows if item["rater"] == "ADJUDICATOR"),
                         rows[0]["label"] if rows else "NONE")
        caption = (f"{index:02d} {row['section']} f{row['frame_index']} ref={reference} "
                   f"arm={args.arm} preds={len(found)}")
        drawn = draw(cv2, image, rows, found, float(row["sheet_scale"]), caption)
        buffer = None
        for quality in (85, 75, 65, 55, 45, 35, 25):
            ok, buffer = cv2.imencode(".jpg", drawn, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if ok and buffer.nbytes <= MAX_BYTES:
                break
        target = out_dir / f"eye_{index:02d}_{row['frame_key'][:12]}.jpg"
        target.write_bytes(buffer.tobytes())
        manifest.append({"rank": index, "frame_key": row["frame_key"], "split": row["split"],
                         "game": row["game"], "section": row["section"],
                         "frame_index": row["frame_index"], "reference_label": reference,
                         "arm": args.arm, "n_predictions": len(found), "file": target.name,
                         "sha256": file_sha256(target), "bytes": target.stat().st_size})
    write_csv(Path(args.manifest), FIELDS, manifest)
    print(f"EYECHECK n={len(manifest)} max_bytes={max([r['bytes'] for r in manifest] or [0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
