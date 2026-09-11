"""G386 constructed scratch-only controls and the twice-repeated manifest export.

Every control runs against bytes this module writes inside its own scratch
directory. No live corpus file, feeder, daemon or guard is touched, and no
constructed fault counts toward the sampled draw.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tracking.g386_pin_copy import (  # noqa: E402
    pin_copy_one_pass, release_staging)

SCRATCH = Path("/workspace/g386_scratch/controls")
EV = Path("docs/evidence/tracking/g386_pin_copy_one_pass_2026-09-10")
EXPORT_FIELDS = ["attempt_id", "source_sha256", "source_bytes", "source_device",
                 "source_inode", "ffprobe_stream_sha256", "ledger_snapshot_line"]


def _fixture(name: str, payload: bytes) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / name
    path.write_bytes(payload)
    return path


def _run(name: str, expected: str, source: Path, attempt_id: str = "", **hooks) -> dict:
    hooks.setdefault("receiver_decode", lambda path: path.is_file())
    record = pin_copy_one_pass(source, SCRATCH / "stage", SCRATCH / "receiver",
                               "control_ledger_line", attempt_id or name,
                               probe=lambda p: "CONTROL", **hooks)
    released = release_staging(record)
    if record.staged_path:
        Path(record.staged_path).unlink(missing_ok=True)
    return dict(control=name, expected_status=expected, observed_status=record.status,
                exact=int(record.status == expected), staging_released=int(released),
                receipt_present=int(record.receipt is not None),
                version_id=record.receipt.version_id if record.receipt else "")


def controls() -> list:
    rows = []
    clean = _fixture("clean.bin", b"G386-clean-" + b"c" * 4096)
    rows.append(_run("c1_clean_capture", "CAPTURED", clean))

    replaced = _fixture("replaced.bin", b"G386-original-" + b"o" * 4096)

    def swap() -> None:
        replaced.unlink()
        replaced.write_bytes(b"G386-replacement-" + b"r" * 4096)

    rows.append(_run("c2_unlink_and_replace_after_pin", "CHANGED", replaced, after_pin=swap))

    mutated = _fixture("mutated.bin", b"G386-mutate-" + b"m" * 8192)

    def mutate() -> None:
        with mutated.open("r+b") as handle:
            handle.seek(0)
            handle.write(b"G386-MUTATE")

    rows.append(_run("c3_concurrent_mutation", "CHANGED", mutated, before_copy=mutate))

    short = _fixture("short.bin", b"G386-short-" + b"s" * 16384)

    def truncate() -> None:
        with short.open("r+b") as handle:
            handle.truncate(64)

    rows.append(_run("c4_short_read", "SHORT_READ", short, before_copy=truncate))

    corrupt_src = _fixture("corrupt.bin", b"G386-corrupt-" + b"k" * 4096)

    def corrupt() -> None:
        for temporary in sorted((SCRATCH / "receiver").glob("*.tmp")):
            data = bytearray(temporary.read_bytes())
            data[0] ^= 0xFF
            temporary.write_bytes(bytes(data))

    rows.append(_run("c5_receiver_corruption", "RECEIVER_MISMATCH", corrupt_src,
                     receiver_corrupt=corrupt))

    retry_a = _run("c6_versioned_retry_first", "CAPTURED", clean, attempt_id="c6_reused_name")
    retry_b = _run("c6_versioned_retry_second", "CAPTURED", clean, attempt_id="c6_reused_name")
    retry_b["exact"] = int(retry_b["exact"] and retry_a["version_id"] != retry_b["version_id"])
    rows.extend([retry_a, retry_b])
    return rows


def export_manifest(evidence: Path, out: Path) -> str:
    rows = list(csv.DictReader((evidence / "source_identity.csv").open(encoding="ascii")))
    payload = [{field: row[field] for field in EXPORT_FIELDS} for row in rows]
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    out.write_text(text, encoding="ascii")
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def main(evidence: Path) -> None:
    rows = controls()
    with (evidence / "faults.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    first = export_manifest(evidence, SCRATCH / "export_1.json")
    second = export_manifest(evidence, SCRATCH / "export_2.json")
    (evidence / "export_hashes.json").write_text(json.dumps(dict(
        export_1_sha256=first, export_2_sha256=second, identical=first == second,
        export_fields=EXPORT_FIELDS,
        source="docs/evidence/tracking/g386_pin_copy_one_pass_2026-09-10/source_identity.csv"),
        indent=2, sort_keys=True) + "\n", encoding="ascii")
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print(json.dumps(dict(controls=len(rows), exact=sum(r["exact"] for r in rows),
                          exports_identical=first == second)))


if __name__ == "__main__":
    main(EV if len(sys.argv) < 2 else Path(sys.argv[1]))
