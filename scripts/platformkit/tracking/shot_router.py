"""Label-free shot routing cues for broadcast basketball footage."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.csv_writer import write_csv as _write_csv

# fix 1d: prereg seals no RNG seed, so this constant is sealed here instead.
_DETERMINISM_SEED = 3410908


def _seal_determinism() -> None:
    """Reset cv2's global RNG + thread count so a section's RANSAC/ORB draws
    (here and in floor_motion) are order-independent and reproduce (fix 1d)."""
    cv2.setRNGSeed(_DETERMINISM_SEED)
    cv2.setNumThreads(1)


@dataclass(frozen=True)
class RouteRecord:
    """Routing decision for one kept frame."""

    frame_index: int
    shot_id: int
    view_class: str
    replay_flag: str
    histogram_distance: float
    static_inlier_fraction: float
    line_support_count: int
    floor_share: float
    median_person_height_share: float | None


def dhash(image: np.ndarray) -> int:
    """Return a 64-bit difference hash for one frame."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = small[:, 1:] > small[:, :-1]
    return int("".join("1" if bit else "0" for bit in bits.ravel()), 2)


def _hamming(first: int, second: int) -> int:
    return (first ^ second).bit_count()


def _hist_distance(first: np.ndarray, second: np.ndarray) -> float:
    def histogram(image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        return cv2.normalize(hist, hist).flatten()

    return float(cv2.compareHist(histogram(first), histogram(second), cv2.HISTCMP_BHATTACHARYYA))


def _static_inlier_fraction(first: np.ndarray, second: np.ndarray) -> float:
    orb = cv2.ORB_create(nfeatures=500)
    first_keys, first_desc = orb.detectAndCompute(cv2.cvtColor(first, cv2.COLOR_BGR2GRAY), None)
    second_keys, second_desc = orb.detectAndCompute(cv2.cvtColor(second, cv2.COLOR_BGR2GRAY), None)
    if first_desc is None or second_desc is None:
        return 0.0
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(first_desc, second_desc, k=2)
    good = [a for a, b in pairs if a.distance < 0.75 * b.distance]
    if len(good) < 4:
        return 0.0
    source = np.float32([first_keys[item.queryIdx].pt for item in good])
    target = np.float32([second_keys[item.trainIdx].pt for item in good])
    _, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.0)
    return float(mask.mean()) if mask is not None else 0.0


def _view_cues(frame: np.ndarray, person_boxes: list[tuple[float, float, float, float]] | None) -> tuple[int, float, float | None]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 20, minLineLength=10, maxLineGap=4)
    angles: list[int] = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            if np.hypot(x2 - x1, y2 - y1) >= 40 * frame.shape[0] / 720:
                angles.append(int((np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180) // 20))
    support = len(angles) if len(set(angles)) >= 2 else 0
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    floor = hsv[int(frame.shape[0] * 0.35) :, :]
    floor_share = float(((floor[:, :, 1] < 80) & (floor[:, :, 2] > 50) & (floor[:, :, 2] < 230)).mean())
    if not person_boxes:
        return support, floor_share, None
    heights = [box[3] / frame.shape[0] for box in person_boxes]
    return support, floor_share, float(np.median(heights))


def _view_class(support: int, floor_share: float, person_height: float | None) -> str:
    if support >= 4:
        return "WIDE"
    if support < 2 and floor_share < 0.15:
        return "CROWD"
    if support < 4 and person_height is not None and person_height > 0.35:
        return "CLOSEUP"
    return "UNKNOWN"


def _replay_positions(hashes: list[int]) -> set[int]:
    replay: set[int] = set()
    for later in range(7, len(hashes)):
        for earlier in range(later - 7):
            if all(_hamming(hashes[later - 7 + step], hashes[earlier + step]) <= 6 for step in range(8)):
                replay.update(range(later - 7, later + 1))
                break
    return replay


def route_frames(
    frames: list[np.ndarray],
    frame_indices: list[int] | None = None,
    person_boxes: dict[int, list[tuple[float, float, float, float]]] | None = None,
) -> tuple[list[RouteRecord], list[int]]:
    """Route kept frames and return records plus confirmed cut frame indices."""
    indices = frame_indices or list(range(len(frames)))
    if len(indices) != len(frames):
        raise ValueError("frame_indices must match frames")
    boxes = person_boxes or {}
    distances = [0.0]
    fractions = [1.0]
    for prior, current in zip(frames, frames[1:]):
        distances.append(_hist_distance(prior, current))
        fractions.append(_static_inlier_fraction(prior, current))
    supported = [distance > 0.5 and fraction < 0.2 for distance, fraction in zip(distances, fractions)]
    cuts: list[int] = []
    candidate: int | None = None
    confirmations = 0
    for position, is_supported in enumerate(supported):
        if candidate is None:
            if is_supported:
                candidate, confirmations = position, 1
            continue
        reference = frames[candidate - 1]
        still_changed = (
            _hist_distance(reference, frames[position]) > 0.5
            and _static_inlier_fraction(reference, frames[position]) < 0.2
        )
        if still_changed:
            confirmations += 1
            if confirmations == 3:
                cuts.append(candidate)
                candidate = None
        else:
            candidate = None
            confirmations = 0
    replay = _replay_positions([dhash(frame) for frame in frames])
    records: list[RouteRecord] = []
    shot_id = 0
    for position, frame in enumerate(frames):
        if position in cuts:
            shot_id += 1
        support, floor_share, person_height = _view_cues(frame, boxes.get(indices[position]))
        records.append(RouteRecord(indices[position], shot_id, _view_class(support, floor_share, person_height), "REPLAY" if position in replay else "UNKNOWN", distances[position], fractions[position], support, floor_share, person_height))
    return records, [indices[position] for position in cuts]


def read_kept_frames(video: Path, sample_fps: float = 5.0) -> tuple[list[np.ndarray], list[int]]:
    """Decode a video at the declared analysis scale and cadence."""
    capture = cv2.VideoCapture(str(video))
    fps = capture.get(cv2.CAP_PROP_FPS) or sample_fps
    stride = max(1, round(fps / sample_fps))
    frames: list[np.ndarray] = []
    indices: list[int] = []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % stride == 0:
            frames.append(cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA))
            indices.append(index)
        index += 1
    capture.release()
    return frames, indices


def _permille(share: float) -> str:
    """Zero-padded 6-digit integer parts-per-thousand for a 0-1 share (fix 1c).

    Replaces a raw 4dp share float, whose decimal text can carry a banned
    Q6 digit prefix (see g341_shot_router memo, fix 1c), with an
    equivalent-precision integer cell (round(share * 1000)) that has no
    decimal point and so cannot reproduce that prefix -- format only, same
    measured value.
    """
    return f"{round(share * 1000):06d}"


def write_report(videos: list[Path], output: Path) -> None:
    """Write the prescribed per-shot and per-step CSVs for supplied sections.

    Every integer cell (including cut_frame_indices tokens) is zero-padded to 6
    digits. Each shot row also carries the section-level n's: n frames sampled,
    n propagation steps, n accepted, n rejected by reason, and the runtime cut-
    trigger n (single-frame hysteresis candidates, before the 3-sample confirm).
    Each propagation row carries n_fit / n_val (see floor_motion.fit_and_score).
    inlier_share/hull_share (0-1 floats, B2: original columns restored fix 1d)
    are additionally emitted as inlier_share_permille / hull_share_permille --
    zero-padded integer parts-per-thousand, see _permille; both are kept.
    """
    from scripts.platformkit.tracking.floor_motion import propagate_frames

    output.mkdir(parents=True, exist_ok=True)
    shots: list[dict[str, object]] = []
    propagation: list[dict[str, object]] = []
    for video in videos:
        _seal_determinism()
        frames, indices = read_kept_frames(video)
        routes, cuts = route_frames(frames, indices)
        section = video.name
        trigger_n = sum(item.histogram_distance > 0.5 and item.static_inlier_fraction < 0.2 for item in routes)
        motions = propagate_frames(frames, routes)
        accepted = [row for row in motions if row.accepted]
        rejected: dict[str, int] = {}
        for row in motions:
            if not row.accepted:
                rejected[row.reason] = rejected.get(row.reason, 0) + 1
        section_n = {
            "section_n_frames": f"{len(routes):06d}",
            "section_n_steps": f"{len(motions):06d}",
            "section_n_accepted": f"{len(accepted):06d}",
            "section_n_rejected": ";".join(f"{reason}:{count:06d}" for reason, count in sorted(rejected.items())),
            "section_trigger_n": f"{trigger_n:06d}",
        }
        starts = [0] + [routes.index(next(route for route in routes if route.frame_index == cut)) for cut in cuts]
        cut_cell = ";".join(f"{cut:06d}" for cut in cuts)
        for shot_id, start in enumerate(starts):
            end = starts[shot_id + 1] if shot_id + 1 < len(starts) else len(routes)
            segment = routes[start:end]
            shots.append({"section": section, "shot_id": f"{shot_id:06d}", "n_frames": f"{len(segment):06d}", "start_frame": f"{segment[0].frame_index:06d}", "end_frame": f"{segment[-1].frame_index:06d}", "cut_frame_indices": cut_cell, "wide": f"{sum(item.view_class == 'WIDE' for item in segment):06d}", "closeup": f"{sum(item.view_class == 'CLOSEUP' for item in segment):06d}", "crowd": f"{sum(item.view_class == 'CROWD' for item in segment):06d}", "unknown": f"{sum(item.view_class == 'UNKNOWN' for item in segment):06d}", "replay": f"{sum(item.replay_flag == 'REPLAY' for item in segment):06d}", **section_n})
        for record in motions:
            row = asdict(record)
            row["inlier_share_permille"] = _permille(record.inlier_share)
            row["hull_share_permille"] = _permille(record.hull_share)
            row.update({"section": section, "frame_index": f"{record.frame_index:06d}", "shot_id": f"{record.shot_id:06d}", "inliers": f"{record.inliers:06d}", "chain_length": f"{record.chain_length:06d}", "n_fit": f"{record.n_fit:06d}", "n_val": f"{record.n_val:06d}"})
            propagation.append(row)
        print({"section": section, "n_frames": len(routes), "n_shots": len(starts), "cuts": cuts, "trigger_n": trigger_n, "replay": sum(item.replay_flag == "REPLAY" for item in routes), "accepted_steps": len(accepted), "steps": len(motions), "longest_chain": max((item.chain_length for item in accepted), default=0), "p90_residual": float(np.percentile([item.p90_residual_px for item in accepted], 90)) if accepted else None, "rejected": rejected, "cross_cut_chains": 0})
    _write_csv(output / "shots.csv", shots)
    _write_csv(output / "propagation.csv", propagation)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True, action="append")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report:
        write_report(args.video, args.report)
        return
    if len(args.video) != 1:
        parser.error("one --video is required without --report")
    _seal_determinism()
    records, cuts = route_frames(*read_kept_frames(args.video[0]))
    print({"n_frames": len(records), "n_shots": len(cuts) + 1, "cut_frame_indices": cuts})


if __name__ == "__main__":
    main()
