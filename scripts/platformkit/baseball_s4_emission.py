"""Re-emit the S4a NPB census with calibration and content status separated.

The baseball adapter's pitch-geometry gate is intentionally strict: it detects
only a mound/plate calibration opportunity.  It is not a classifier for
whether a frame belongs to a confirmed game broadcast.  This helper preserves
the original 300-frame NPB census denominator and emits every confirmed-game
frame as ``unsolved`` until a validated full-field solve exists.

Run:
    python -m scripts.platformkit.baseball_s4_emission \
        --census-manifest scripts/platformkit/a3_artifacts/census_fulltimeline/sample_manifest.csv \
        --output-dir scripts/platformkit/a3_artifacts/s4a_npb_reemission
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

CONFIRMED_NPB_CLIP = "data/footage_corpus/npb__npb_3PwJwWdTMek.mp4"


def confirmed_npb_rows(census: pd.DataFrame) -> pd.DataFrame:
    """Return the one confirmed-game NPB source from a census manifest.

    This is an explicit corpus decision, not a vision heuristic.  The source
    was confirmed by the blind-label review; unconfirmed MLB/KBO sources are
    rejected rather than inferred from a grass or mound threshold.
    """
    required = {"clip", "source_frame", "jpeg_path"}
    if missing := required - set(census.columns):
        raise ValueError("census manifest missing columns: %s" % ", ".join(sorted(missing)))
    rows = census[census["clip"] == CONFIRMED_NPB_CLIP].copy()
    clips = sorted(rows["clip"].unique())
    if len(clips) != 1:
        raise ValueError("expected the one confirmed NPB source, found: %s" % ", ".join(clips))
    if rows.empty:
        raise ValueError("confirmed NPB census is empty")
    if rows["source_frame"].duplicated().any():
        raise ValueError("confirmed NPB source_frame values must be unique")
    missing_frames = [path for path in rows["jpeg_path"] if not Path(path).is_file()]
    if missing_frames:
        raise FileNotFoundError("missing NPB census frame: %s" % missing_frames[0])
    return rows.sort_values("source_frame").reset_index(drop=True)


def corrected_manifest(census: pd.DataFrame) -> pd.DataFrame:
    """Emit no false ``non_play`` labels for a confirmed-game source.

    No full-field homography is validated, so ``solved`` remains zero.  A
    calibration failure is represented as ``unsolved``; it is not evidence
    that the broadcast frame is non-play.
    """
    rows = confirmed_npb_rows(census)
    return pd.DataFrame({"frame": rows["source_frame"].astype(int),
                         "status": "unsolved"})


def manifest_counts(manifest: pd.DataFrame) -> dict[str, int]:
    """Validate the S4a three-status contract and return its exact counts."""
    if list(manifest.columns) != ["frame", "status"]:
        raise ValueError("manifest columns must be frame,status")
    if manifest["frame"].duplicated().any():
        raise ValueError("manifest frame values must be unique")
    statuses = {"solved", "unsolved", "non_play"}
    unknown = sorted(set(manifest["status"]) - statuses)
    if unknown:
        raise ValueError("unknown manifest status: %s" % ", ".join(unknown))
    return {status: int((manifest["status"] == status).sum()) for status in sorted(statuses)}


def reemit(census_path: Path, output_dir: Path) -> dict[str, int]:
    """Write the corrected NPB census manifest and its count sidecar."""
    manifest = corrected_manifest(pd.read_csv(census_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = manifest_counts(manifest)
    manifest.to_csv(output_dir / "npb_s4a.decode_manifest.csv", index=False)
    payload = {
        "decoded_frames": len(manifest),
        "solved": counts["solved"],
        "unsolved": counts["unsolved"],
        "non_play": counts["non_play"],
        "classification": "confirmed_game_source_not_pitch_geometry_gate",
        "calibration": "full_field_homography_unvalidated",
        "note": "no positional accuracy is claimed",
    }
    (output_dir / "tracking_completeness.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {key: int(payload[key]) for key in ("decoded_frames", "solved", "unsolved", "non_play")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-emit corrected NPB S4a status manifest.")
    parser.add_argument("--census-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    counts = reemit(args.census_manifest, args.output_dir)
    print("decoded=%d solved=%d unsolved=%d non_play=%d" % (
        counts["decoded_frames"], counts["solved"], counts["unsolved"], counts["non_play"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
