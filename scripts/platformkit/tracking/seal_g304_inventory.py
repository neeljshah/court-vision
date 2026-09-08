"""Seal G304's local, time-stratified inventory without running inference."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RENDER_DIR = ROOT / "g304_local_renders"
OUTPUT = ROOT / "docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json"
SOURCES = (
    ("wnba_01", "data/videos/bridge/wnba_01.f137.mp4", 5814.333333),
    ("wnba_04", "data/videos/bridge/wnba_04.f137.mp4", 3193.666667),
)


def sha256_file(path: Path) -> str:
    """Hash a file in bounded chunks without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_seal(manifest: dict) -> str:
    """SHA256 over the canonical payload: sorted keys, compact separators, ASCII."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def main() -> None:
    """Write the immutable inventory manifest and its canonical-payload seal."""
    source_rows = []
    rows = []
    for source_id, relative_path, duration in SOURCES:
        source = ROOT / relative_path
        source_rows.append(
            {
                "id": source_id,
                "path": relative_path,
                "bytes": source.stat().st_size,
                "sha256": sha256_file(source),
                "width": 1920,
                "height": 1080,
                "fps": "30/1",
                "duration_seconds": duration,
                "league": "wnba",
            }
        )
        for ordinal in range(1, 31):
            pts = round((ordinal - 0.5) * duration / 30, 6)
            render = RENDER_DIR / f"{source_id}_{ordinal:02d}.jpg"
            rows.append(
                {
                    "row_id": f"{source_id}_{ordinal:02d}",
                    "source_id": source_id,
                    "frame_index": math.ceil(pts * 30),
                    "pts_seconds": pts,
                    "dimensions": [1920, 1080],
                    "league": "wnba",
                    "decode_sha256": sha256_file(render),
                    "render_path_local": str(render.relative_to(ROOT)).replace("\\", "/"),
                    "selection_status": "UNRESOLVED_NO_INDEPENDENT_SECOND_LOCATOR",
                    "scope": "UNRESOLVED",
                    "shot_identity": "UNRESOLVED",
                    "court_end_identity": "UNRESOLVED",
                    "landmarks": [],
                    "locator_annotations": [
                        {
                            "locator_name": "Codex G304 visual review",
                            "locator_kind": "model",
                            "status": "UNRESOLVED",
                        }
                    ],
                }
            )
    manifest = {
        "packet_id": "G304_E1_UNVALIDATED_INVENTORY_2026-09-07",
        "status": "INSTRUMENT_NOT_VALIDATED",
        "source_rows": source_rows,
        "rows": rows,
        "selection_rule": "Thirty evenly spaced PTS positions per full broadcast; no inference output was viewed.",
        "eligibility_rule": "Identifiable, well-spread court evidence with six landmarks across at least three marking structures.",
        "frame_good_rule": "p90 <= 12 px AND max <= 24 px",
        "primary_acceptance": ">=16/20 frame-good per arena; <=1/10 accepted negatives per arena; no accepted wrong-end map; abstentions fail; zero false acceptances among the 40 eligible frames.",
        "adjudication_threshold_px": 4,
        "decode_recipe": {
            "ffprobe_stream": "codec_name=h264, codec_tag_string=avc1, width=1920, height=1080, pix_fmt=yuv420p, r_frame_rate=30/1, avg_frame_rate=30/1, time_base=1/15360, start_pts=0, start_time=0.000000; nb_frames=N/A on both sources",
            "extract_command": "ffmpeg -nostdin -v error -y -ss <pts_seconds> -i <source path> -frames:v 1 -q:v 2 <render_path_local>",
            "authoritative_value": "pts_seconds is authoritative; frame_index is derived from it and is never an independent input",
            "frame_index_rule": "frame_index = ceil(pts_seconds * 30), the first frame at or after the published six-decimal seek time, which is the frame the input-seek command above decodes",
            "reproduction_check": "the command above reproduces a render byte-for-byte, so decode_sha256 is re-derivable from pts_seconds alone",
        },
        "unresolved_reason": "Only one model locator was available; no second independent locator or adjudication was performed.",
        "measurement_scope": "Annotation inventory only; no registration, calibration, tracking, detector, prediction, or model run.",
    }
    manifest["manifest_sha256_canonical_payload"] = canonical_seal(manifest)
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"sealed_manifest={OUTPUT.relative_to(ROOT)}")
    print(f"manifest_sha256={manifest['manifest_sha256_canonical_payload']}")


if __name__ == "__main__":
    main()
