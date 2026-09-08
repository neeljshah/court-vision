"""Draw and seal the G304 pass-A2 extension inventory (annotation only, no inference).

The sealed pass-A inventory placed 30 bin-midpoint frames per broadcast. Blind
eligibility classification yielded 14/30 eligible for wnba_01 and 9/30 for wnba_04,
short of the spec's 20 eligible per arena. This module draws MORE rows with the SAME
time-stratified rule at a declared within-bin offset of 1/3 instead of 1/2, so the new
positions interleave with the sealed ones and can never collide with them.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.seal_g304_inventory import canonical_seal, sha256_file

ROOT = Path(__file__).resolve().parents[3]
ORIGINAL = ROOT / "docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json"
OUTPUT = ROOT / "docs/evidence/tracking/g304_e1_extension_manifest_2026-09-07.json"
RENDER_DIR = ROOT / "g304_local_renders_ext"
FPS = 30

# Sized from the blind eligibility rates (wnba_01 14/30, wnba_04 9/30) against the
# per-arena eligible shortfall (6 and 11): 30 * 0.4667 = 14.0 >= 6, but 30 * 0.30 = 9.0
# < 11, so wnba_04 is raised to 45 (45 * 0.30 = 13.5 >= 11).
EXTENSION_ROWS = {"wnba_01": 30, "wnba_04": 45}
BIN_OFFSET = 1.0 / 3.0
# wnba_04 is a partial download: the container header declares 3193.666667 s but the
# bytes stop at the 3147.666667 s packet (ffprobe: "partial file"), so it is stratified
# over its measured decodable span. wnba_01 decodes to 5814.300000, its full header
# duration, and keeps it. The sealed source bytes and SHA256s are unchanged either way.
DECODABLE_DURATION = {"wnba_04": 3147.666667}
SELECTION_RULE = (
    "Same time-stratified rule as the sealed pass-A inventory, at a declared within-bin "
    "offset of 1/3 instead of 1/2: N evenly spaced PTS positions across each full "
    "broadcast, pts = round((ordinal - 1/3) * duration / N, 6), N = 30 for wnba_01 and "
    "45 for wnba_04. duration is the measured decodable span: 5814.333333 s for wnba_01 "
    "(its full header duration) and 3147.666667 s for wnba_04, whose bytes are a partial "
    "download that stops 46 s before its declared header duration. No inference output, "
    "projection, homography, detector result or eligibility label was viewed while drawing "
    "these positions."
)
UNRESOLVED_REASON = (
    "Extension inventory only: no locator has annotated these rows, so scope, shot "
    "identity, court end and landmarks are all UNRESOLVED."
)


def extension_pts(ordinal: int, count: int, duration: float) -> float:
    """The published six-decimal seek time for one extension row."""
    return round((ordinal - BIN_OFFSET) * duration / count, 6)


def render(source: Path, pts: float, destination: Path) -> None:
    """Decode one native-size frame with the manifest's recorded ffmpeg recipe."""
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-y",
            "-ss", f"{pts:.6f}", "-i", str(source),
            "-frames:v", "1", "-q:v", "2", str(destination),
        ],
        check=True,
    )


def build_rows(original: dict, *, do_render: bool) -> list[dict]:
    """Draw every extension row, render it, and hash the render."""
    taken_pts = {(row["source_id"], row["pts_seconds"]) for row in original["rows"]}
    taken_frames = {(row["source_id"], row["frame_index"]) for row in original["rows"]}
    RENDER_DIR.mkdir(exist_ok=True)
    rows: list[dict] = []
    for source in original["source_rows"]:
        arena = source["id"]
        count = EXTENSION_ROWS[arena]
        path = ROOT / source["path"]
        duration = DECODABLE_DURATION.get(arena, source["duration_seconds"])
        for ordinal in range(1, count + 1):
            pts = extension_pts(ordinal, count, duration)
            frame_index = math.ceil(pts * FPS)
            if (arena, pts) in taken_pts or (arena, frame_index) in taken_frames:
                raise SystemExit(f"extension row {arena}_e{ordinal:02d} collides with pass A")
            render_path = RENDER_DIR / f"{arena}_e{ordinal:02d}.jpg"
            if do_render:
                render(path, pts, render_path)
            rows.append(
                {
                    "row_id": f"{arena}_e{ordinal:02d}",
                    "source_id": arena,
                    "frame_index": frame_index,
                    "pts_seconds": pts,
                    "dimensions": [source["width"], source["height"]],
                    "league": source["league"],
                    "decode_sha256": sha256_file(render_path),
                    "render_path_local": str(render_path.relative_to(ROOT)).replace("\\", "/"),
                    "selection_status": "UNRESOLVED_NOT_YET_CLASSIFIED",
                    "scope": "UNRESOLVED",
                    "shot_identity": "UNRESOLVED",
                    "court_end_identity": "UNRESOLVED",
                    "landmarks": [],
                    "locator_annotations": [],
                }
            )
    return rows


def main() -> None:
    """Verify both sources, draw the extension rows, and seal the extension manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-render", action="store_true", help="reseal from existing renders")
    do_render = not parser.parse_args().no_render

    original = json.loads(ORIGINAL.read_text(encoding="ascii"))
    source_rows = []
    for source in original["source_rows"]:
        path = ROOT / source["path"]
        size, digest = path.stat().st_size, sha256_file(path)
        if size != source["bytes"] or digest != source["sha256"]:
            raise SystemExit(f"{source['id']} does not match the sealed source bytes")
        print(f"source_verified={source['id']} bytes={size} sha256={digest}")
        row = dict(source)
        row["decodable_duration_seconds"] = DECODABLE_DURATION.get(
            source["id"], source["duration_seconds"]
        )
        source_rows.append(row)

    rows = build_rows(original, do_render=do_render)
    manifest = {
        "packet_id": "G304_E1_EXTENSION_UNVALIDATED_INVENTORY_2026-09-07",
        "status": "INSTRUMENT_NOT_VALIDATED",
        "extends": original["manifest_sha256_canonical_payload"],
        "source_rows": source_rows,
        "rows": rows,
        "extension_rows_per_arena": EXTENSION_ROWS,
        "selection_rule": SELECTION_RULE,
        "eligibility_rule": original["eligibility_rule"],
        "frame_good_rule": original["frame_good_rule"],
        "primary_acceptance": original["primary_acceptance"],
        "adjudication_threshold_px": original["adjudication_threshold_px"],
        "decode_recipe": original["decode_recipe"],
        "unresolved_reason": UNRESOLVED_REASON,
        "measurement_scope": original["measurement_scope"],
    }
    manifest["manifest_sha256_canonical_payload"] = canonical_seal(manifest)
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"extension_manifest={OUTPUT.relative_to(ROOT)}")
    print(f"rows={len(rows)} bytes={sum((ROOT / r['render_path_local']).stat().st_size for r in rows)}")
    print(f"extends={manifest['extends']}")
    print(f"manifest_sha256={manifest['manifest_sha256_canonical_payload']}")


if __name__ == "__main__":
    main()
