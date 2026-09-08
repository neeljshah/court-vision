"""Finisher-only, read-only G346 liveness census over a footage corpus."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from scripts.platformkit import footage_liveness


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stem_key(path: Path) -> str:
    """Per-section ledger key. Measured on the pod ledger 2026-09-08: the daemon
    ledger's `game_id` field is keyed PER SECTION (e.g. `eurocup-qrWmO434a0k_s90`),
    not per game, so the ledger cross must join on the full section stem, not on
    the game-level id."""
    return path.stem.split("__", 1)[-1]


def _game_id(key: str) -> str:
    """True game id for the resolution x game confound table (drops the trailing
    _s<offset> section marker so multiple sections of one game group together).
    Takes either a corpus stem key (`_stem_key`) or a raw ledger key -- both are
    the same string shape."""
    return key.rsplit("_s", 1)[0]


def _read_ledger(ledger: Path) -> dict[str, dict]:
    """Read every ledger entry keyed by its per-section `game_id` field. An absent
    ledger is a HARD ERROR: fix 1b (G346_VERIFY, codex-sol) found the prior silent
    empty-dict fallback let the census claim a ledger cross it never actually made."""
    if not ledger.is_file():
        raise FileNotFoundError("ledger not found (hard error, not silently empty): %s" % ledger)
    entries: dict[str, dict] = {}
    with ledger.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
                key = str(entry["game_id"])
                rows = int(entry["rows"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            entries[key] = {"rows": rows, "sport": str(entry.get("sport", "")),
                             "status": str(entry.get("status", ""))}
    return entries


def _quantile(values: list[float], level: float) -> str:
    return "" if not values else "%.6f" % float(np.quantile(values, level))


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def census(corpus: Path, ledger: Path, output: Path) -> None:
    """Write sealed section detail, aggregate census, resolution-game table, and
    a sealed ledger extract so the ledger cross is recomputable from the artifact
    alone (no live re-read of the pod ledger required)."""
    output.mkdir(parents=True, exist_ok=True)
    ledger_entries = _read_ledger(ledger)  # raises if ledger is absent
    low_rows = {key: entry["rows"] for key, entry in ledger_entries.items()
                if entry["rows"] < 50}
    detail: list[dict[str, str]] = []
    matched_keys: set[str] = set()
    videos = sorted(path for path in corpus.rglob("*")
                    if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi"})
    for video in videos:
        # ponytail: the corpus is a live rotating queue (G335); a section listed at
        # `videos = sorted(...)` time can be gone by the time it is opened. base is
        # built INSIDE the try so a mid-census removal is one UNREADABLE row, not a
        # crash that loses every row already measured.
        key = _stem_key(video)
        matched_keys.add(key)
        base = {"section_path": str(video), "game_id": _game_id(key),
                "ledger_rows": "%06d" % low_rows.get(key, 0),
                "ledger_entry_present": str(key in ledger_entries)}
        try:
            base["sha256"] = _hash(video)
            base["bytes"] = "%06d" % video.stat().st_size
            measured = footage_liveness.measure_liveness(video)
            detail.append({**base, "width": "%06d" % measured.width,
                           "height": "%06d" % measured.height,
                           "frame_count": "%06d" % measured.frame_count,
                           "valid_frames": "%06d" % measured.valid_frames,
                           "bytes_per_frame": "%.6f" % measured.bytes_per_frame,
                           "mean_abs_delta": "%.6f" % measured.mean_abs_delta,
                           "near_identical_share": "%.6f" % measured.near_identical_share,
                           "liveness": measured.verdict, "error": ""})
        except (OSError, ValueError) as exc:
            detail.append({**base, "width": "000000", "height": "000000",
                           "frame_count": "000000", "valid_frames": "000000",
                           "bytes_per_frame": "", "mean_abs_delta": "",
                           "near_identical_share": "",
                           "liveness": "UNREADABLE", "error": str(exc)[:160]})
    # NEW GAP fix (G346_VERIFY): ledger-only sources with rows < 50 whose file is
    # no longer in the corpus scan are represented as their own rows, not omitted.
    absent_rows: list[dict[str, str]] = []
    for key in sorted(low_rows):
        if key in matched_keys:
            continue
        absent_rows.append({"section_path": "", "sha256": "", "bytes": "000000",
                            "game_id": _game_id(key), "ledger_rows": "%06d" % low_rows[key],
                            "ledger_entry_present": "True", "width": "000000",
                            "height": "000000", "frame_count": "000000",
                            "valid_frames": "000000", "bytes_per_frame": "",
                            "mean_abs_delta": "", "near_identical_share": "",
                            "liveness": "ABSENT_FILE",
                            "error": "ledger-only: rows<50, no matching corpus file"})
    detail_fields = ["section_path", "sha256", "bytes", "game_id", "ledger_rows",
                     "ledger_entry_present", "width", "height", "frame_count",
                     "valid_frames", "bytes_per_frame", "mean_abs_delta",
                     "near_identical_share", "liveness", "error"]
    _write(output / "sealed_sections.csv", detail_fields, detail + absent_rows)
    live = [row for row in detail if row["liveness"] == "LIVE"]
    frozen = [row for row in detail if row["liveness"] == "FROZEN"]
    readable = live + frozen
    bpf = [float(row["bytes_per_frame"]) for row in readable]
    delta = [float(row["mean_abs_delta"]) for row in readable]
    frozen_rows = [int(row["ledger_rows"]) for row in frozen if int(row["ledger_rows"])]
    aggregate = [{
        "scope": "all_sections", "n_sections": "%06d" % len(detail),
        "n_frozen": "%06d" % len(frozen), "n_live": "%06d" % len(live),
        "n_unreadable": "%06d" % (len(detail) - len(readable)),
        "bpf_p10": _quantile(bpf, .10), "bpf_p50": _quantile(bpf, .50),
        "bpf_p90": _quantile(bpf, .90), "delta_p10": _quantile(delta, .10),
        "delta_p50": _quantile(delta, .50), "delta_p90": _quantile(delta, .90),
        "n_frozen_with_ledger_rows": "%06d" % len(frozen_rows),
        "ledger_rows_from_frozen": "%06d" % sum(frozen_rows),
        "n_ledger_only_absent_file": "%06d" % len(absent_rows),
    }]
    _write(output / "census.csv", list(aggregate[0]), aggregate)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in detail:
        groups[row["width"] + "x" + row["height"]].append(row)
    resolutions = [{"resolution": key, "n_sections": "%06d" % len(rows),
                    "n_distinct_games": "%06d" % len({r["game_id"] for r in rows})}
                   for key, rows in sorted(groups.items())]
    _write(output / "resolution_games.csv",
           ["resolution", "n_sections", "n_distinct_games"], resolutions)
    # Sealed ledger extract: every ledger row matched to a census section plus
    # every rows<50 row (ledger-only included), with the ledger file's own path,
    # byte size and SHA-256 at extraction time so the cross needs no live re-read.
    extract_keys = matched_keys | set(low_rows)
    extract_rows = []
    ledger_bytes = "%06d" % ledger.stat().st_size
    ledger_sha256 = _hash(ledger)
    for key in sorted(extract_keys):
        entry = ledger_entries.get(key)
        if entry is None:
            continue
        extract_rows.append({"ledger_key": key, "rows": "%06d" % entry["rows"],
                             "sport": entry["sport"], "status": entry["status"],
                             "in_corpus_scan": str(key in matched_keys),
                             "rows_lt_50": str(entry["rows"] < 50),
                             "ledger_path": str(ledger), "ledger_bytes": ledger_bytes,
                             "ledger_sha256": ledger_sha256})
    _write(output / "ledger_extract.csv",
           ["ledger_key", "rows", "sport", "status", "in_corpus_scan", "rows_lt_50",
            "ledger_path", "ledger_bytes", "ledger_sha256"], extract_rows)
    identities = [{"path": str(Path(__file__).resolve()), "sha256": _hash(Path(__file__))},
                  {"path": str(Path(footage_liveness.__file__).resolve()),
                   "sha256": _hash(Path(footage_liveness.__file__))}]
    _write(output / "code_identity.csv", ["path", "sha256"], identities)


def main() -> None:
    parser = argparse.ArgumentParser(description="G346 read-only footage census")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    census(args.corpus, args.ledger, args.output)


if __name__ == "__main__":
    main()
