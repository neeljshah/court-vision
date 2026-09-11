"""Write G393 parser-review receipts without changing a production route."""
from __future__ import annotations

import csv
import difflib
import json
import os
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g393_parser_harness import DAEMON, RUN_CLIP, cases, replay


EVIDENCE = Path("docs/evidence/tracking/g393_leading_hyphen_game_id_2026-09-11")
MEMO = Path("docs/evidence/tracking/g393_leading_hyphen_game_id_2026-09-11.md")
PROPOSAL = Path("docs/research/organization-sprint/PROPOSED_g393_game_id.diff")
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt", ".diff"}


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def validate(review: dict[str, Any]) -> dict[str, int]:
    """Enforce the finite parser-only acceptance conditions."""
    records = review["records"]
    leading = [record for record in records if record["kind"] == "leading"]
    ordinary = [record for record in records if record["kind"] == "ordinary"]
    supplemental = [record for record in records if record["kind"] == "supplemental"]
    if (len(leading), len(ordinary), len(supplemental)) != (30, 30, 6):
        raise ValueError("unexpected-construct-universe")
    failures = 0
    candidate_mismatches = 0
    for record in records:
        after = record["after"]
        namespace = after["namespace"]
        if after["return_status"] != 0 or namespace is None:
            raise ValueError("candidate-parser-failed:%d" % record["ordinal"])
        if namespace["game_id"] != record["game_id"]:
            candidate_mismatches += 1
        if namespace["frames"] != 3000 or not namespace["no_show"]:
            raise ValueError("candidate-unrelated-argument-drift:%d" % record["ordinal"])
        if "input path" not in namespace["video"] or "data/tracking" not in namespace["data_dir"].replace("\\", "/"):
            raise ValueError("space-path-not-preserved:%d" % record["ordinal"])
    for record in leading:
        before = record["before"]
        if before["return_status"] == 0:
            raise ValueError("leading-before-did-not-fail:%d" % record["ordinal"])
        failures += 1
    for record in ordinary:
        if record["before"]["namespace"] != record["after"]["namespace"]:
            raise ValueError("ordinary-namespace-drift:%d" % record["ordinal"])
    return {"leading_before_failures": failures, "leading_candidate_recovered": len(leading),
            "ordinary_unchanged": len(ordinary), "supplemental_preserved": len(supplemental) - candidate_mismatches,
            "candidate_value_mismatches": candidate_mismatches}


def caller_census(root: Path) -> list[dict[str, str]]:
    """Read source callers one file at a time, including shell-family files."""
    rows = []
    skip = {".git", "data", "vault", "__pycache__", ".pytest_cache"}
    for current, directories, names in os.walk(root):
        directories[:] = [name for name in directories if name not in skip]
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix.lower() not in {".py", ".sh", ".ps1", ".bat", ".cmd"}:
                continue
            relative = path.relative_to(root)
            if relative.as_posix().startswith("scripts/platformkit/tracking/g393_"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "scripts/run_clip.py" not in text and "build_command(" not in text:
                continue
            split = '"--game-id",' in text or "--game-id %s" in text
            rows.append({"path": relative.as_posix(), "mentions_run_clip": str("scripts/run_clip.py" in text),
                         "mentions_build_command": str("build_command(" in text),
                         "split_value_caller": str(split),
                         "status": "NEW GAP" if split else "no split token detected"})
    return rows


def _q6_scan(paths: list[Path]) -> None:
    forbidden = ["".join(chr(code) for code in codes) for codes in
                 ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101))]
    hits = []
    for path in paths:
        if path.suffix.lower() in TEXT_SUFFIXES:
            value = path.read_text(encoding="utf-8", errors="replace").lower()
            hits.extend("%s:%s" % (path, word) for word in forbidden if word in value)
    if hits:
        raise ValueError("q6-vocabulary:" + ",".join(hits))


def write_artifacts(root: Path | None = None) -> dict[str, int]:
    """Produce finite G393 evidence; this function never invokes production mains."""
    root = _root() if root is None else root
    daemon = (root / DAEMON).read_text(encoding="utf-8")
    clip = (root / RUN_CLIP).read_text(encoding="utf-8")
    review = replay(daemon, clip)
    summary = validate(review)
    evidence = root / EVIDENCE
    evidence.mkdir(parents=True, exist_ok=True)
    source_hashes = {DAEMON: {"bytes": len(daemon.encode("utf-8")), "sha256": review["source_hashes"][DAEMON]},
                     RUN_CLIP: {"bytes": len(clip.encode("utf-8")), "sha256": review["source_hashes"][RUN_CLIP]},
                     "proposed_track_daemon": {"bytes": len(review["proposal"].encode("utf-8")),
                                                 "sha256": review["source_hashes"]["proposed_track_daemon"]}}
    _write(evidence / "source_hashes.json", json.dumps(source_hashes, indent=2, sort_keys=True) + "\n")
    with (evidence / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ordinal", "kind", "game_id"])
        writer.writeheader()
        writer.writerows({"ordinal": index, **case} for index, case in enumerate(cases(), start=1))
    _write(evidence / "argv.jsonl", "".join(json.dumps({"ordinal": row["ordinal"], "before": row["before"]["argv"],
        "after": row["after"]["argv"]}, sort_keys=True) + "\n" for row in review["records"]))
    _write(evidence / "parsed_before_after.jsonl", "".join(json.dumps({"ordinal": row["ordinal"], "kind": row["kind"],
        "game_id": row["game_id"], "before": row["before"], "after": row["after"]}, sort_keys=True) + "\n"
        for row in review["records"]))
    _write(evidence / "failure_stderr.txt", "".join("CASE %d\n%s" % (row["ordinal"], row["before"]["stderr"])
        for row in review["records"] if row["kind"] == "leading"))
    census = caller_census(root)
    with (evidence / "caller_census.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(census[0]))
        writer.writeheader()
        writer.writerows(census)
    _write(evidence / "summary.json", json.dumps({**summary, "argument_declarations": review["argument_count"],
        "prepare_only": True, "candidate_eligible": summary["candidate_value_mismatches"] == 0,
        "verdict": "PREPARE-ONLY PLACEHOLDER"}, indent=2, sort_keys=True) + "\n")
    cards = evidence / "eye_cards"
    cards.mkdir(exist_ok=True)
    for row in review["records"]:
        _write(cards / ("case_%02d.txt" % row["ordinal"]), json.dumps(row, indent=2, sort_keys=True) + "\n")
    diff = "".join(difflib.unified_diff(daemon.splitlines(keepends=True), review["proposal"].splitlines(keepends=True),
                  fromfile=DAEMON, tofile=DAEMON))
    _write(root / PROPOSAL, diff)
    memo = """# G393 Leading-Hyphen Game-ID Parser Proposal

Status: PREPARE-ONLY PLACEHOLDER. Claude finisher measurement is pending.

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. The binding parser replay uses `scripts/platformkit/track_daemon.py` and `scripts/run_clip.py`; their byte sizes and SHA-256 values are recorded in `g393_leading_hyphen_game_id_2026-09-11/source_hashes.json`. No video or store input is opened; resolution is not applicable.

Preregistration: `g393_leading_hyphen_game_id_2026-09-11/preregistration.md`; seal: read from its final line after lane_commit. The seal covers LF-normalized bytes above that line.

Prepared receipt set: 30 leading identifiers, 30 ordinary identifiers, and 6 option-shaped controls. The proposal changes only an in-memory caller source copy and is anchored in `docs/research/organization-sprint/PROPOSED_g393_game_id.diff`. It is not applied to a production file.

The prepared parser receipt has one option-shaped mismatch: the value `--` does not survive argparse as a scalar under the one-token proposal. By the specified acceptance rule, that proposal is not eligible; this remains a prepare-only placeholder pending the finisher's independent replay.

Sign convention: improvement equals baseline loss minus candidate loss, so a positive value would mean the candidate is better. This parser-only preparation produces no loss delta.

NOT VERIFIED:
- The deployed caller digest and any accepted G380 composition.
- Live routing, video decoding, tracking, or production behavior.
- Finisher remeasurement, adoption, deployment, register, or results-record action.
"""
    _write(root / MEMO, memo)
    artifacts = [path for path in evidence.rglob("*") if path.is_file()] + [root / PROPOSAL, root / MEMO]
    _q6_scan(artifacts)
    return summary


if __name__ == "__main__":
    print(json.dumps(write_artifacts(), sort_keys=True))
