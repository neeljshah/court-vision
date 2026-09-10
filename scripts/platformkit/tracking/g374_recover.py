"""Restore the pinned G364 validation sources absent at G374 finisher time."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.platformkit.tracking.g364_census import fetch, sha256_file


RESTORE_FIELDS = ("section_id", "source_path", "expected_sha256", "observed_sha256",
                  "expected_bytes", "observed_bytes", "status")


def _target(row: dict[str, str], scratch: Path) -> Path:
    """Return the pinned source path so a restored byte stream lands where it was pinned."""
    return scratch / ("%s_s%d.mp4" % (row["video_id"], int(row["offset_s"])))


def restore_one(row: dict[str, str], scratch: Path, timeout: int) -> dict[str, str]:
    """Restore one pinned source and verify it byte-for-byte against its sealed digest."""
    target = _target(row, scratch)
    expected = row["source_sha256"]
    if target.exists() and sha256_file(target) == expected:
        observed, status = expected, "already_present"
    else:
        fetched = fetch(row, scratch, timeout)
        if fetched is None:
            observed, status = "", "fetch_failed"
        else:
            observed = sha256_file(fetched)
            status = "restored" if observed == expected else "mismatch"
    return {"section_id": row["section_id"], "source_path": str(target),
            "expected_sha256": expected, "observed_sha256": observed,
            "expected_bytes": row["byte_size"],
            "observed_bytes": str(target.stat().st_size) if target.exists() else "0",
            "status": status}


def restore(sources: list[dict[str, str]], scratch: Path, timeout: int) -> list[dict[str, str]]:
    """Restore every pinned source in manifest order, never stopping on one failure."""
    scratch.mkdir(parents=True, exist_ok=True)
    report: list[dict[str, str]] = []
    for row in sources:
        record = restore_one(row, scratch, timeout)
        report.append(record)
        print("%s %s" % (record["status"].upper(), record["section_id"]), flush=True)
    return report


def write_report(path: Path, rows: list[dict[str, str]]) -> None:
    """Write the per-source restoration ledger with LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESTORE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="G374 pinned-source restoration")
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    with args.sources.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = restore(rows, args.scratch, args.timeout)
    counts = {status: sum(record["status"] == status for record in report)
              for status in sorted({record["status"] for record in report})}
    write_report(args.report, report)
    print("sources=%d %s" % (len(report), counts))


if __name__ == "__main__":
    main()
