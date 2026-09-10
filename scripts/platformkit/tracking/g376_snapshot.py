"""G376 snapshot -- build the immutable lane copy the whole row reads.

The pod `/workspace/data/tracking` is LIVE under the daemon, so every table is copied ONCE into
`data/g376_snapshot/` and pinned by sha256, exactly as sealed in g376_prereg_2026-09-10.md
section 1 (SEAL sha256 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee).

A section's two TABLES come from the live store when its `tracking_data.csv` still hashes to the
G370 pin (same run), and otherwise from `/workspace/g370_snapshot`, the immutable copy G370 itself
scored. The two small sidecars are copied ONLY beside tables taken from the live store, because a
sidecar from a later re-track does not describe the pinned run. Nothing is written outside the
snapshot directory; `/workspace/data` is never modified.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from scripts.platformkit.tracking.g361_source_identity import sha256_file
from scripts.platformkit.tracking.g376_schedule import SNAPSHOT_FILES, TRACKING

TABLES = ("tracking_data.csv", "ball_tracking.csv")
SOURCE_FIELDS = ("section_id", "set", "pin", "live_sha256", "g370_sha256", "tables_from",
                 "sidecars_from", "pin_check")


def _pins(evidence: Path) -> dict[str, str]:
    """The G370 tracking-table pin per section, from both of its landed manifests."""
    pins: dict[str, str] = {}
    sealed = json.loads((evidence / "sealed_manifest.json").read_text(encoding="utf-8"))
    for section in sealed.get("sections", []):
        pins[section["section_id"]] = section.get("table_sha256_pin") or ""
    with (evidence / "fresh_sections.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("selected") == "1":
                pins[row["section_name"]] = row.get("tracking_sha256") or ""
    return pins


def build(sections: dict[str, str], live: Path, fallback: Path, snapshot: Path,
          evidence: Path) -> list[dict[str, str]]:
    """Copy each section once and report where every file came from; absence is named."""
    pins = _pins(evidence)
    rows = []
    for section_id, set_name in sorted(sections.items()):
        pin = pins.get(section_id, "")
        live_dir, fallback_dir = live / section_id, fallback / section_id
        live_sha = sha256_file(live_dir / TRACKING) if (live_dir / TRACKING).exists() else "ABSENT"
        alt_sha = (sha256_file(fallback_dir / TRACKING)
                   if (fallback_dir / TRACKING).exists() else "ABSENT")
        from_live = bool(pin) and live_sha == pin
        source = live_dir if from_live else (fallback_dir if alt_sha == pin else live_dir)
        target = snapshot / section_id
        target.mkdir(parents=True, exist_ok=True)
        names = SNAPSHOT_FILES if source is live_dir else TABLES
        for name in names:
            if (source / name).exists():
                shutil.copy2(source / name, target / name)
        rows.append({"section_id": section_id, "set": set_name, "pin": pin or "ABSENT",
                     "live_sha256": live_sha, "g370_sha256": alt_sha,
                     "tables_from": str(source), "sidecars_from":
                     str(source) if source is live_dir else "NONE",
                     "pin_check": "MATCH" if sha256_file(target / TRACKING) == pin else "DIFFER"})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="the landed G370 evidence directory")
    parser.add_argument("--live", default="/workspace/data/tracking")
    parser.add_argument("--fallback", default="/workspace/g370_snapshot")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    evidence = Path(args.evidence)
    sections = {row["section_id"]: "SEALED34" for row in csv.DictReader(
        (evidence / "sealed_denominator_census.csv").open(newline="", encoding="utf-8"))}
    for row in csv.DictReader((evidence / "fresh_sections.csv").open(newline="", encoding="utf-8")):
        if row.get("selected") == "1":
            sections[row["section_name"]] = "FRESH69"
    rows = build(sections, Path(args.live), Path(args.fallback), Path(args.snapshot), evidence)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.out).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SOURCE_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    matched = sum(1 for row in rows if row["pin_check"] == "MATCH")
    live_rows = sum(1 for row in rows if row["sidecars_from"] != "NONE")
    print("sections=%d pin_match=%d pin_differ=%d sidecars=%d"
          % (len(rows), matched, len(rows) - matched, live_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
