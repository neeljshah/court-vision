"""Tag declared image-pixel basketball foot points outside the visible floor."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

_LOWER_MIDDLE = (0.45, 0.95, 0.20, 0.80)
_HUE_BAND = 15
_SAT_FRACTION = 0.55
_SAT_MIN_BAND = 25
_DILATION_HEIGHT_SHARE = 0.03
_TIGHT_FLOOR_SHARE = 0.15
_BANDS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


@dataclass(frozen=True)
class FloorColor:
    """Game-level HSV reference taken from lower-middle source-image pixels."""

    hue: int
    saturation: int


def lower_middle_hsv(frame: np.ndarray) -> FloorColor:
    """Return one lower-middle HSV median from a decoded BGR frame."""
    height, width = frame.shape[:2]
    y0, y1 = int(height * _LOWER_MIDDLE[0]), int(height * _LOWER_MIDDLE[1])
    x0, x1 = int(width * _LOWER_MIDDLE[2]), int(width * _LOWER_MIDDLE[3])
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    usable = hsv[(hsv[:, :, 1] >= 20) & (hsv[:, :, 2] >= 20)]
    if not len(usable):
        usable = hsv.reshape(-1, 3)
    median = np.median(usable, axis=0)
    return FloorColor(int(median[0]), int(median[1]))


def learn_floor_color(video: Path, frame_limit: int) -> FloorColor:
    """Learn a lighting-tolerant HSV court color reference for one game."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("cannot open video {}".format(video))
    colors: list[FloorColor] = []
    while len(colors) < frame_limit:
        ok, frame = capture.read()
        if not ok:
            break
        colors.append(lower_middle_hsv(frame))
    capture.release()
    if not colors:
        raise ValueError("video has no decoded frames {}".format(video))
    return FloorColor(int(np.median([item.hue for item in colors])),
                      int(np.median([item.saturation for item in colors])))


def floor_mask(frame: np.ndarray, color: FloorColor) -> np.ndarray:
    """Return the largest court-color component for a decoded BGR frame."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    hue_delta = np.abs(hue - color.hue)
    hue_delta = np.minimum(hue_delta, 180 - hue_delta)
    saturation = hsv[:, :, 1]
    sat_band = max(_SAT_MIN_BAND, int(color.saturation * _SAT_FRACTION))
    color_mask = ((hue_delta <= _HUE_BAND)
                  & (saturation >= max(0, color.saturation - sat_band))
                  & (saturation <= min(255, color.saturation + sat_band))).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(color_mask, 8)
    if count <= 1:
        return np.zeros(color_mask.shape, dtype=np.uint8)
    index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return (labels == index).astype(np.uint8)


def dilated_floor_mask(mask: np.ndarray) -> np.ndarray:
    """Dilate a floor mask by three percent of its frame height."""
    radius = max(1, int(round(mask.shape[0] * _DILATION_HEIGHT_SHARE)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.dilate(mask, kernel)


def _inside(mask: np.ndarray, x: float, y: float) -> bool:
    return np.isfinite(x) and np.isfinite(y) and 0 <= int(x) < mask.shape[1] and 0 <= int(y) < mask.shape[0] and bool(mask[int(y), int(x)])


def tag_rows(rows: pd.DataFrame, masks: dict[int, np.ndarray]) -> pd.DataFrame:
    """Add the nonfloor observation tag without removing or moving any row."""
    required = {"frame", "x", "y", "observation"}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError("tracking rows missing columns: {}".format(", ".join(missing)))
    result = rows.copy()
    frame = pd.to_numeric(result["frame"], errors="coerce")
    x = pd.to_numeric(result["x"], errors="coerce")
    y = pd.to_numeric(result["y"], errors="coerce")
    outside = []
    for number, point_x, point_y in zip(frame, x, y):
        mask = masks.get(int(number)) if pd.notna(number) else None
        outside.append(mask is None or not _inside(mask, float(point_x), float(point_y)))
    result.loc[np.asarray(outside), "observation"] = "nonfloor"
    return result


def containment_all(rows: pd.DataFrame) -> float | None:
    """Return all-row source-frame containment, independent of observation tags."""
    required = {"x", "y", "frame_width", "frame_height"}
    if not required <= set(rows.columns) or not len(rows):
        return None
    numeric = {name: pd.to_numeric(rows[name], errors="coerce") for name in required}
    inside = ((numeric["frame_width"] > 0) & (numeric["frame_height"] > 0)
              & (numeric["x"] >= 0) & (numeric["x"] <= numeric["frame_width"] - 1)
              & (numeric["y"] >= 0) & (numeric["y"] <= numeric["frame_height"] - 1))
    return float(inside.mean())


def height_bands(before: pd.DataFrame, after: pd.DataFrame) -> list[dict]:
    """Report before/after nonfloor share in fixed fractions of image height."""
    y = pd.to_numeric(before["y"], errors="coerce")
    height = pd.to_numeric(before["frame_height"], errors="coerce")
    ratio = y / height
    before_nonfloor = before["observation"].astype(str).eq("nonfloor")
    after_nonfloor = after["observation"].astype(str).eq("nonfloor")
    output = []
    for low, high in _BANDS:
        member = (ratio >= low) & ((ratio < high) if high < 1.0 else (ratio <= high))
        count = int(member.sum())
        output.append({"band": "{:d}-{:d}".format(int(low * 100), int(high * 100)),
                       "rows": count,
                       "nonfloor_share_before": float(before_nonfloor[member].mean()) if count else None,
                       "nonfloor_share_after": float(after_nonfloor[member].mean()) if count else None,
                       "floor_rows_after": int((member & ~after_nonfloor).sum()),
                       "nonfloor_rows_after": int((member & after_nonfloor).sum())})
    return output


def _video_for(game: str, footage_root: Path) -> Path:
    prefix = "wnba__" if game.startswith("wnba_") else "ncaa_basketball__"
    matches = sorted(footage_root.glob("{}{}.mp4".format(prefix, game)))
    exact = footage_root / "{}{}.mp4".format(prefix, game)
    if exact.exists():
        return exact
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError("one base video required for {}".format(game))


def _masks_for_video(video: Path, color: FloorColor,
                     frame_limit: int) -> tuple[dict[int, np.ndarray], int, list[int]]:
    capture = cv2.VideoCapture(str(video))
    masks: dict[int, np.ndarray] = {}
    tight: list[int] = []
    frame_number = 0
    while frame_number < frame_limit:
        ok, frame = capture.read()
        if not ok:
            break
        mask = floor_mask(frame, color)
        masks[frame_number] = dilated_floor_mask(mask)
        if float(mask.mean()) < _TIGHT_FLOOR_SHARE:
            tight.append(frame_number)
        frame_number += 1
    capture.release()
    return masks, frame_number, tight


def _render(video: Path, rows: pd.DataFrame, masks: dict[int, np.ndarray],
            tight: set[int], output: Path, count: int) -> list[str]:
    capture = cv2.VideoCapture(str(video))
    total = len(masks)
    targets = sorted(set(np.linspace(0, max(0, total - 1), count, dtype=int)))
    by_frame = {int(frame): group for frame, group in rows.groupby("frame")}
    written = []
    for target in targets:
        capture.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = capture.read()
        if not ok:
            continue
        mask = masks[target]
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(frame, contours, -1, (0, 255, 255), 2)
        for _, row in by_frame.get(target, pd.DataFrame()).iterrows():
            color = (0, 0, 255) if str(row["observation"]) == "nonfloor" else (0, 220, 0)
            cv2.circle(frame, (int(row["x"]), int(row["y"])), 6, color, 2)
        label = "frame {} tight_shot={}".format(target, str(target in tight).lower())
        cv2.putText(frame, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        path = output / "{}_f{:06d}.png".format(video.stem.split("__")[-1], target)
        output.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), frame)
        written.append(str(path))
    capture.release()
    return written


def process_game(table: Path, footage_root: Path, output_root: Path,
                 render: bool, render_count: int) -> dict:
    """Tag one input table and return its non-destructive measurement manifest."""
    game = table.parent.name
    before = pd.read_csv(table, low_memory=False)
    video = _video_for(game, footage_root)
    tracked_frames = int(pd.to_numeric(before["frame"], errors="coerce").max()) + 1
    color = learn_floor_color(video, tracked_frames)
    masks, decoded_frames, tight = _masks_for_video(video, color, tracked_frames)
    if decoded_frames != tracked_frames:
        raise ValueError("video ended at {} before tracked frame {}".format(
            decoded_frames, tracked_frames))
    after = tag_rows(before, masks)
    output = output_root / game
    output.mkdir(parents=True, exist_ok=True)
    after.to_csv(output / "tracking_data.csv", index=False)
    bands = height_bands(before, after)
    top = bands[0]
    manifest = {"game": game, "video": str(video), "rows": int(len(after)),
                "decoded_frames": decoded_frames, "floor_color_hsv": [color.hue, color.saturation],
                "nonfloor_rows": int(after["observation"].astype(str).eq("nonfloor").sum()),
                "tight_shot_frames": len(tight), "tight_shot_frame_share": len(tight) / decoded_frames,
                "containment_all_before": containment_all(before),
                "containment_all_after": containment_all(after), "height_bands": bands,
                "top_20_pct_rows": top["rows"], "top_20_pct_floor_rows": top["floor_rows_after"],
                "top_20_pct_nonfloor_rows": top["nonfloor_rows_after"]}
    if render:
        manifest["renders"] = _render(video, after, masks, set(tight), output / "renders", render_count)
    (output / "floor_gate_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    """Run the additive image-pixel floor gate over relabeled basketball tables."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--footage-root", type=Path, required=True)
    parser.add_argument("--render-games", nargs="*", default=[])
    parser.add_argument("--render-count", type=int, default=8)
    args = parser.parse_args()
    tables = sorted(args.input_root.glob("*/tracking_data.csv"))
    if not tables:
        raise FileNotFoundError("no */tracking_data.csv below {}".format(args.input_root))
    manifests = [process_game(table, args.footage_root, args.out,
                              table.parent.name in args.render_games, args.render_count)
                 for table in tables]
    (args.out / "summary.json").write_text(json.dumps(manifests, indent=2) + "\n", encoding="utf-8")
    for item in manifests:
        print("{} nonfloor={}/{} tight={}/{}".format(
            item["game"], item["nonfloor_rows"], item["rows"], item["tight_shot_frames"], item["decoded_frames"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
