"""G400 landing: summary.json, the Q6 scan, common receipts and SHA256SUMS."""
from __future__ import annotations

import argparse
import csv
import re
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g400_prepare as rails
from g400_q6_scan import scan

BYTE_DOMAIN = ("# byte domain: SHA-256 over the exact on-disk bytes of every file "
               "listed below, relative to the repository root, LF endings as stored; "
               "source mp4 bytes live in the off-repo receiver and are NOT listed here")
TEXT_SUFFIX = (".md", ".csv", ".json", ".txt", ".py")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _lf(path: Path) -> None:
    """Force LF bytes: text-mode writes on Windows emit CRLF (fix 1c)."""
    raw = path.read_bytes()
    crlf = bytes((13, 10))
    if crlf in raw:
        path.write_bytes(raw.replace(crlf, bytes((10,))))


def summary(out: Path, extra: dict) -> dict:
    kappa = _read(out / "kappa.csv")
    yields = {row["metric"]: row["value"] for row in _read(out / "yield.csv")}
    controls = _read(out / "transform_controls.csv")
    receipts = _read(out / "source_receipts.csv")
    manifest = _read(out / "native_manifest.csv")
    ratings = _read(out / "ratings.csv")
    audit = _read(out / "box_audit.csv")
    pooled = next((row for row in kappa if row["round"] == "POOLED"), {})
    payload = {
        "row": "G400", "planned_states": rails.PLANNED_STATES, "games": rails.GAMES,
        "retained_sources": sum(int(row["byte_agreement"]) for row in receipts),
        "decoded_states": sum(1 for row in manifest if row["status"] == "PLANNED"),
        "reviewed_by_both": sum(1 for row in ratings
                                if row["terra_label"] and row["sol_label"]),
        "unvisited": sum(1 for row in ratings
                         if not row["terra_label"] or not row["sol_label"]),
        "reviewed_unknown": sum(1 for row in ratings
                                if row["terra_label"] == row["sol_label"] == "UNKNOWN"),
        "pooled_kappa": pooled.get("kappa", ""),
        "pooled_paired_n": pooled.get("paired_n", ""),
        "rounds_pass": sum(1 for row in kappa
                           if row["round"] != "POOLED" and row["verdict"] == "PASS"),
        "rounds_total": sum(1 for row in kappa if row["round"] != "POOLED"),
        "controls": len(controls),
        "controls_roundtrip_exact": sum(int(row["roundtrip_exact"]) for row in controls),
        "controls_centre_rule_match": sum(int(row["centre_rule_match"])
                                          for row in controls),
        "controls_false_positive": sum(int(row["false_positive"]) for row in controls),
        "accepted_audited_new_boxes": yields.get("accepted_audited_new_boxes", ""),
        "stage_yield": yields.get("stage_yield", ""),
        "games_contributing": yields.get("games_contributing", ""),
        "route_verdict": yields.get("route_verdict", ""),
        "audited_states": len(audit),
        "milestone_1500_boxes_57_games": "NOT MET BY THIS STAGE",
        "training_arm_allocated": False, "gpu_minutes": 0,
        "flag_changes": 0, "registry_writes": 0}
    payload.update(extra)
    (out / "summary.json").write_text(json.dumps(payload, indent=1, sort_keys=True)
                                      + "\n", encoding="ascii")
    _lf(out / "summary.json")
    return payload


def _classify(path: Path, hits: list[str]) -> str:
    """A hit is opaque when the reserved token never occurs as a whole word.

    The scan is substring-based, so a reserved three-letter token can be flagged
    inside an ordinary proper noun (a franchise city in a canonical game title).
    That is disclosed and classified, never silenced: a whole-word occurrence is
    still a non-opaque hit and fails the scan.
    """
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    for hit in hits:
        token = "".join(chr(int(code)) for code in hit.split("-"))
        if re.search(r"(?<![a-z])" + token + r"(?![a-z])", text):
            return "NON-OPAQUE"
    return "OPAQUE-SUBSTRING-IN-PROPER-NOUN"


def q6(out: Path, extras: list[Path]) -> dict:
    targets = sorted(path for path in out.rglob("*")
                     if path.is_file() and path.suffix in TEXT_SUFFIX
                     and path.name != "q6_scan.json")
    targets.extend(extras)
    findings = scan(targets)
    classified = {str(path): _classify(Path(path), hits)
                  for path, hits in findings.items()}
    non_opaque = sum(1 for item in classified.values() if item == "NON-OPAQUE")
    payload = {"scanned": len(targets), "flagged_files": len(classified),
               "non_opaque_hits": non_opaque, "findings": findings,
               "findings_classified": classified}
    (out / "q6_scan.json").write_text(json.dumps(payload, indent=1, sort_keys=True)
                                      + "\n", encoding="ascii")
    _lf(out / "q6_scan.json")
    print("Q6 scanned", len(targets), "hits", len(findings))
    return payload


def sha256sums(out: Path, root: Path) -> int:
    lines = [BYTE_DOMAIN]
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(digest + "  " + path.relative_to(root).as_posix())
    (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")
    _lf(out / "SHA256SUMS")
    return len(lines) - 1


def run(args) -> int:
    out = Path(args.out_dir)
    root = Path(args.root)
    (out / "common_receipts").mkdir(parents=True, exist_ok=True)
    if args.stage == "all":
        extra = json.loads(Path(args.extra).read_text(encoding="ascii")) if args.extra else {}
        payload = summary(out, extra)
        print(json.dumps({key: payload[key] for key in
                          ("accepted_audited_new_boxes", "stage_yield", "pooled_kappa",
                           "route_verdict")}, sort_keys=True))
    q6(out, [Path(item) for item in args.also.split("|") if item])
    count = sha256sums(out, root)
    print("SHA256SUMS files", count)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_finish")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--extra", default="")
    parser.add_argument("--also", default="")
    parser.add_argument("--stage", choices=("all", "q6-sha"), default="all")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
