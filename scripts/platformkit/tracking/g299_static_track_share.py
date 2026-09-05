"""G299: census of image-space motion in committed detector-box observations."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g289_implausible_step_decomposition import measure_steps
from scripts.platformkit.tracking.verifier_footpoint_analyses import (
    G267, load_detections, overlay_bands, steps,
)

EVID = G267.parent.parent
STEP_CSV = EVID / "g289_implausible_step_decomposition_artifact/steps.csv"
OUT = EVID / "g299_static_track_share_artifact"
MIN_OBS = 20
CUTS_PX = (10, 25, 50)  # Declared arbitrary descriptive cuts; 25 is primary.
BANDS = {
    "top_strip_0_89": (0, 89),
    "score_bug_90_300": (90, 300),
    "lower_third_850_980": (850, 980),
    "bottom_strip_990_1079": (990, 1079),
}
LIMITS = (
    "STATIC IS NOT THE SAME AS FURNITURE. A player standing still, a track living "
    "entirely during a held camera, or a short id in a static shot all look static, "
    "and this row has NO image evidence and NO eye check to tell them apart -- "
    "naming furniture would need crops this row does not render. The camera moves, "
    "so screen-fixed overlay graphics are static in image space while the court "
    "is not; that is the signal being used and it is INDIRECT. ONE clip, ONE span "
    "(19599-23399), ONE draw of a non-deterministic route (G241: 808 of 1,201 "
    "records differed). Per G278 the span is measurably friendlier than the clip "
    "(0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. The population "
    "is detector-box observations, not authenticated players. The lower-third "
    "band also contains the near court; occupancy is not evidence of furniture. "
    "Motion cannot attribute a share of G281's 0.935 purity to furniture; no "
    "per-track identity labels, ground truth, or purity recomputation."
)


def verified_step_rows(records: list[dict], path: Path = STEP_CSV) -> list[dict]:
    """Read G289 steps and check every field against its existing verifier trace."""
    reference = steps(records)
    expected = measure_steps(records, reference)
    with path.open(encoding="ascii", newline="") as handle:
        archived = list(csv.DictReader(handle))
    assert len(archived) == len(expected), "G289 step count mismatch"
    rows = []
    for raw, original in zip(archived, expected):
        typed = {}
        for key, value in original.items():
            cell = raw[key]
            if value is None:
                assert cell == ""
                typed[key] = None
            elif isinstance(value, bool):
                assert cell in ("True", "False")
                typed[key] = cell == "True"
            else:
                typed[key] = type(value)(cell)
        assert typed == original, "G289 step endpoints or measurements changed"
        rows.append(typed)
    return rows


def band_for(y: float) -> str:
    """Use the verifier's inclusive image-row bands, with the remainder explicit."""
    return next((name for name, (lo, hi) in BANDS.items() if lo <= y <= hi), "other")


def per_track(records: list[dict], step_rows: list[dict]) -> list[dict]:
    """Summarize all finite retained footpoints and the already defined steps."""
    observations, distances = defaultdict(list), defaultdict(list)
    for rec in records:
        for det in rec.get("detections") or []:
            if det.get("finite"):
                observations[det["track_id"]].append(dict(det, source_frame=rec["source_frame"]))
    for step in step_rows:
        distances[step["track_id"]].append(step["image_displacement_px"])
    result = []
    for tid, points in sorted(observations.items()):
        xs, ys = [p["foot_x_px"] for p in points], [p["foot_y_px"] for p in points]
        assert all(math.isfinite(v) for v in xs + ys)
        ds = distances[tid]
        row = dict(track_id=tid, observation_count=len(points), step_count=len(ds),
                   first_frame=min(p["source_frame"] for p in points),
                   last_frame=max(p["source_frame"] for p in points),
                   min_x_px=min(xs), max_x_px=max(xs), min_y_px=min(ys), max_y_px=max(ys),
                   path_length_px=math.fsum(ds),
                   footpoint_bbox_diagonal_px=math.hypot(max(xs) - min(xs), max(ys) - min(ys)),
                   median_step_displacement_px=st.median(ds) if ds else None,
                   eligible=len(points) >= MIN_OBS)
        for name in (*BANDS, "other"):
            row[f"observations_{name}"] = sum(band_for(y) == name for y in ys)
        result.append(row)
    return result


def distribution(values: list[float | None]) -> dict:
    """Linear empirical quantiles across IDs; undefined medians remain excluded and named."""
    ordered = sorted(v for v in values if v is not None)
    out = dict(ids_total=len(values), ids_defined=len(ordered), ids_undefined=len(values) - len(ordered))
    for label, p in (("min", 0), ("p10", .1), ("p25", .25), ("median", .5),
                     ("p75", .75), ("p90", .9), ("p95", .95), ("max", 1)):
        rank = (len(ordered) - 1) * p
        lo, hi = math.floor(rank), math.ceil(rank)
        out[label] = (ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)) if ordered else None
    return out


def summarize(tracks: list[dict], min_obs: int = MIN_OBS, cuts: tuple = CUTS_PX) -> dict[str, Any]:
    """Classify by footpoint extent, naming eligible IDs and all-detection denominators."""
    total = sum(t["observation_count"] for t in tracks)
    eligible = [t for t in tracks if t["observation_count"] >= min_obs]
    cut_rows = []
    for cut in cuts:
        static = [t for t in eligible if t["footpoint_bbox_diagonal_px"] < cut]
        nstatic = sum(t["observation_count"] for t in static)
        bands = []
        for name in (*BANDS, "other"):
            field = f"observations_{name}"
            nband = sum(t[field] for t in tracks)
            n = sum(t[field] for t in static)
            bands.append(dict(band=name, all_band_detections=nband, all_retained_detections=total,
                              static_band_detections=n, all_static_detections=nstatic,
                              share_all_retained=n / total if total else None,
                              share_static_detections=n / nstatic if nstatic else None,
                              static_share_of_band=n / nband if nband else None,
                              static_ids_touching_band=[t["track_id"] for t in static if t[field]]))
        cut_rows.append(dict(diagonal_cut_px=cut, eligible_ids=len(eligible),
                             static_ids=[t["track_id"] for t in static], static_id_count=len(static),
                             static_id_share=len(static) / len(eligible) if eligible else None,
                             static_detections=nstatic, all_retained_detections=total,
                             detection_share=nstatic / total if total else None, bands=bands))
    metrics = ("observation_count", "path_length_px", "footpoint_bbox_diagonal_px", "median_step_displacement_px")
    return dict(all_ids=len(tracks), all_retained_detections=total, eligible_ids=len(eligible),
                excluded_short_ids=[t["track_id"] for t in tracks if t["observation_count"] < min_obs],
                excluded_short_detections=sum(t["observation_count"] for t in tracks if t["observation_count"] < min_obs),
                minimum_observations=min_obs, arbitrary_cuts=True, primary_cut_px=25,
                classification="observation_count >= minimum AND footpoint_bbox_diagonal_px < cut",
                cuts=cut_rows, distributions={label: {m: distribution([t[m] for t in rows]) for m in metrics}
                                             for label, rows in (("all_ids", tracks), ("eligible_ids", eligible))})


def provenance(path: Path, resolution: str) -> dict:
    """Identify an opened input exactly, including bytes and coordinate resolution."""
    return dict(path=str(path.resolve()), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), resolution=resolution)


def main() -> None:
    """Write only new G299 artifacts after complete coordinate and step reconciliation."""
    records = load_detections()
    rows = verified_step_rows(records)
    tracks = per_track(records, rows)
    result = summarize(tracks)
    pairs = [(r["source_frame"], d["track_id"]) for r in records
             for d in r.get("detections") or [] if d.get("finite")]
    assert (len(pairs), len(set(pairs)), len(rows), len(tracks)) == (30071, 30071, 29973, 98)
    assert all(t["step_count"] == t["observation_count"] - 1 for t in tracks)
    assert (min(r["source_frame"] for r in records), max(r["source_frame"] for r in records)) == (19599, 23399)
    for name, share in overlay_bands(records).items():
        assert result["cuts"][0]["bands"][list(BANDS).index(name)]["all_band_detections"] / len(pairs) == share
    source = json.loads(G267.read_text(encoding="utf-8"))["input"]
    result.update(steps=len(rows), frame_records=len(records), unique_frame_id_observations=len(set(pairs)),
                  source_frame_span_inclusive=[19599, 23399], limits=LIMITS,
                  zero_image_steps=sum(r["image_displacement_px"] == 0 for r in rows),
                  zero_image_median_court_ft=st.median(r["court_displacement_ft"] for r in rows if r["image_displacement_px"] == 0),
                  inputs=[provenance(p, "not raster; coordinates at 1920x1080") for p in (G267, STEP_CSV)],
                  inherited_video_metadata_not_opened=source,
                  code=[provenance(Path(p), "not applicable (Python source)") for p in
                        (__file__, steps.__code__.co_filename, measure_steps.__code__.co_filename)],
                  machine=dict(host=platform.node(), system=platform.system(), python=platform.python_version(),
                               worktree=str(Path.cwd()), reason="Local CPU arithmetic on committed coordinates"))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "per_track.csv").open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tracks[0]))
        writer.writeheader()
        writer.writerows(tracks)
    (OUT / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="ascii")
    lines = [f"CENSUS: {len(pairs)} retained detector-box observations, {len(tracks)} IDs, {len(rows)} steps"]
    for cut in result["cuts"]:
        lines.append(f"ARBITRARY diagonal <{cut['diagonal_cut_px']} px, n>=20: "
                     f"{cut['static_id_count']}/{cut['eligible_ids']} eligible IDs; "
                     f"{cut['static_detections']}/{cut['all_retained_detections']} retained detections "
                     f"= {cut['detection_share']:.9f}")
    output = "\n".join(lines) + "\n"
    (OUT / "run_stdout.txt").write_text(output, encoding="ascii")
    print(output, end="")


if __name__ == "__main__":
    main()
