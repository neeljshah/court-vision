"""G393 finisher: score every candidate argv form and census the real callers.

Parser-only. Never imports or runs a production main; never writes a source file
outside the scratch directory. The three candidate forms are applied to an
IN-MEMORY copy of the caller source, exactly as the preregistration allows.
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g393_parser_harness import (
    DAEMON, PAIR, RUN_CLIP, cases, extract_build_command, extract_parser, parse_card, sha256_text)


EVIDENCE = Path("docs/evidence/tracking/g393_leading_hyphen_game_id_2026-09-11")
SCRATCH = Path("C:/Users/neelj/AppData/Local/Temp/g393_scratch")

# Candidate caller forms, as source replacements of the single anchored token pair.
FORMS = {
    "split_baseline": PAIR,                        # what the landed caller does today
    "dashdash_separator": '"--game-id", "--", game_id,',
    "equals_single_token": '"--game-id=" + game_id,',
}
# The six option-shaped controls are SEALED in the preregistration. The two extra
# controls are supplementary only and never relax the sealed bar.
CONTROLS_EXTRA = ("-x", "--video")


def form_source(source: str, form: str) -> str:
    """Return the in-memory caller source for one candidate form."""
    if source.count(PAIR) != 1:
        raise ValueError("unrecognized-proposal-anchor")
    return source.replace(PAIR, FORMS[form])


def _intact(namespace: dict[str, Any] | None) -> bool:
    """Every argument the row must not move is still at its expected value."""
    if namespace is None:
        return False
    return (namespace.get("frames") == 3000 and namespace.get("no_show") is True
            and "input path" in (namespace.get("video") or "")
            and "data/tracking" in (namespace.get("data_dir") or "").replace("\\", "/"))


def score(daemon_source: str, clip_source: str) -> dict[str, Any]:
    """Replay the sealed universe plus the extra controls through every form."""
    parser = extract_parser(clip_source)
    builders = {name: extract_build_command(form_source(daemon_source, name)) for name in FORMS}
    universe = list(cases()) + [{"kind": "control_extra", "game_id": value} for value in CONTROLS_EXTRA]
    records = []
    for ordinal, case in enumerate(universe, start=1):
        video = Path("input path") / ("clip %02d.mp4" % ordinal)
        row: dict[str, Any] = {"ordinal": ordinal, **case, "forms": {}}
        for name, builder in builders.items():
            card = parse_card(parser, builder("wnba", video, case["game_id"]))
            namespace = card["namespace"]
            row["forms"][name] = {
                "argv": card["argv"], "return_status": card["return_status"],
                "stderr": card["stderr"], "namespace": namespace,
                "recovered": bool(card["return_status"] == 0 and namespace is not None
                                  and namespace.get("game_id") == case["game_id"]),
                "unrelated_intact": _intact(namespace)}
        records.append(row)
    return {"records": records,
            "source_hashes": {DAEMON: sha256_text(daemon_source), RUN_CLIP: sha256_text(clip_source),
                              **{"form:" + name: sha256_text(form_source(daemon_source, name))
                                 for name in FORMS}}}


KIND_TO_COUNT = {"leading": "leading_recovered", "ordinary": "ordinary_recovered",
                 "supplemental": "supplemental_preserved", "control_extra": "control_extra_preserved"}


def tally(review: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per-form pass counts by case kind. A form is eligible only on the SEALED bar."""
    out: dict[str, dict[str, int]] = {}
    for name in FORMS:
        counts = {"leading_recovered": 0, "ordinary_recovered": 0, "supplemental_preserved": 0,
                  "control_extra_preserved": 0, "unrelated_drift": 0}
        for record in review["records"]:
            cell = record["forms"][name]
            counts[KIND_TO_COUNT[record["kind"]]] += int(cell["recovered"])
            if cell["recovered"] and not cell["unrelated_intact"]:
                counts["unrelated_drift"] += 1
        # SEALED bar: 30 leading + 30 ordinary + all 6 supplemental, nothing moved.
        counts["sealed_eligible"] = int(counts["leading_recovered"] == 30
                                        and counts["ordinary_recovered"] == 30
                                        and counts["supplemental_preserved"] == 6
                                        and counts["unrelated_drift"] == 0)
        out[name] = counts
    return out


CALLER_SUFFIXES = {".py", ".sh", ".ps1", ".bat", ".cmd"}
SPLIT_LIST = re.compile(r"""["']--game-id["']\s*,""")
SPLIT_SHELL = re.compile(r"--game-id\s+(%s|\{|\$)")
CONSTANT_ID = re.compile(r"""["']--game-id["']\s*,\s*["']""")


def caller_lines(root: Path) -> list[dict[str, str]]:
    """Every line that builds a run_clip game-id argument, with file:line.

    Scope: only files that name `run_clip` (every other `--game-id` in the tree
    belongs to some other program's own parser), and never an `add_argument`
    line, which DECLARES the option rather than passing a value to it.
    """
    rows = []
    skip = {".git", ".claude", ".codex", ".agents", "data", "vault", "__pycache__", ".pytest_cache", ".pytest_tmp_g393", "restored_sources"}  # 2026-09-11: stale agent worktrees under .claude/worktrees inflated the main-repo census to 215 lines
    for current, directories, names in os.walk(root):
        directories[:] = [name for name in directories if name not in skip]
        for name in sorted(names):
            path = Path(current) / name
            if path.suffix.lower() not in CALLER_SUFFIXES:
                continue
            relative = path.relative_to(root).as_posix()
            if relative.startswith("scripts/platformkit/tracking/g393_"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "run_clip" not in text:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if "--game-id" not in line or "add_argument" in line:
                    continue
                if SPLIT_LIST.search(line) and not CONSTANT_ID.search(line):
                    kind = "SPLIT_LIST_VARIABLE"
                elif SPLIT_LIST.search(line):
                    kind = "SPLIT_LIST_CONSTANT"
                elif SPLIT_SHELL.search(line):
                    kind = "SPLIT_SHELL_INTERPOLATED"
                else:
                    kind = "prose_or_help_text"
                rows.append({"path": relative, "line": str(number), "kind": kind,
                             "affected": str(kind in ("SPLIT_LIST_VARIABLE", "SPLIT_SHELL_INTERPOLATED")),
                             "code": line.strip()[:160]})
    return rows


def scratch_proof(daemon_source: str, clip_source: str) -> dict[str, Any]:
    """Write each form to the scratch tree and re-derive its leading-id result there."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    parser = extract_parser(clip_source)
    result = {}
    for name in FORMS:
        text = form_source(daemon_source, name)
        target = SCRATCH / ("track_daemon_%s.py" % name)
        target.write_text(text, encoding="utf-8", newline="\n")
        builder = extract_build_command(target.read_text(encoding="utf-8"))
        card = parse_card(parser, builder("wnba", Path("input path/clip 01.mp4"), "-Oa_BpdVT64_s1000"))
        result[name] = {"path": target.as_posix(), "sha256": sha256_text(text),
                        "leading_recovered": bool(card["return_status"] == 0 and card["namespace"] is not None
                                                  and card["namespace"]["game_id"] == "-Oa_BpdVT64_s1000")}
    return result


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".txt", ".diff"}
# Q6 patterns are built from character codes so this scanner never itself trips a scan.
# Whole words only: "ledger" contains one of these as a substring and is not a claim.
Q6_WORDS = ["".join(chr(code) for code in codes) for codes in
            ((114, 111, 105), (112, 114, 111, 102, 105, 116), (101, 100, 103, 101),
             (98, 97, 110, 107, 114, 111, 108, 108), (112, 110, 108))]
Q6_PATTERNS = [re.compile(r"\b%s\b" % word, re.IGNORECASE) for word in Q6_WORDS]
# A money amount, not a bare shell sigil: `$gid` in a quoted code excerpt is an
# opaque identifier and exempt under the Q6 NOTE (S223).
Q6_PATTERNS.append(re.compile(r"\$\s*\d"))
Q6_PATTERNS += [re.compile(re.escape(value)) for value in
                ("18.38", "0.119", "+54", "78.11", "8.94", "54.57")]


def q6_scan(paths: list[Path]) -> list[str]:
    """Return every non-opaque Q6 hit over the given text artifacts."""
    hits = []
    for path in sorted(paths):
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in Q6_PATTERNS:
            match = pattern.search(text)
            if match:
                hits.append("%s:%s" % (path.as_posix(), match.group(0)))
    return hits


def write_artifacts(root: Path | None = None) -> dict[str, Any]:
    """Emit the finisher receipts beside the sealed replay artifacts."""
    root = Path(__file__).resolve().parents[3] if root is None else root
    daemon = (root / DAEMON).read_text(encoding="utf-8")
    clip = (root / RUN_CLIP).read_text(encoding="utf-8")
    review = score(daemon, clip)
    counts = tally(review)
    evidence = root / EVIDENCE
    with (evidence / "forms_matrix.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ordinal", "kind", "game_id", "form", "return_status",
                                                    "recovered", "unrelated_intact", "parsed_game_id"])
        writer.writeheader()
        for record in review["records"]:
            for name in FORMS:
                cell = record["forms"][name]
                writer.writerow({"ordinal": record["ordinal"], "kind": record["kind"],
                                 "game_id": record["game_id"], "form": name,
                                 "return_status": cell["return_status"],
                                 "recovered": cell["recovered"],
                                 "unrelated_intact": cell["unrelated_intact"],
                                 "parsed_game_id": json.dumps((cell["namespace"] or {}).get("game_id"))})
    census = caller_lines(root)
    with (evidence / "caller_census_lines.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(census[0]))
        writer.writeheader()
        writer.writerows(census)
    proof = scratch_proof(daemon, clip)
    # Eye cards: EVEN sampling over the leading set (A3), plus every control, both extras.
    cards = evidence / "form_cards"
    cards.mkdir(exist_ok=True)
    leading = [r for r in review["records"] if r["kind"] == "leading"]
    chosen = leading[::6] + [r for r in review["records"] if r["kind"] in ("supplemental", "control_extra")]
    for record in chosen:
        _write(cards / ("form_case_%02d.txt" % record["ordinal"]),
               json.dumps(record, indent=2, sort_keys=True) + "\n")
    summary = {"forms": counts, "sealed_eligible_forms": sorted(n for n in FORMS if counts[n]["sealed_eligible"]),
               "affected_caller_lines": sorted("%s:%s" % (r["path"], r["line"])
                                               for r in census if r["affected"] == "True"),
               "eye_card_ordinals": [r["ordinal"] for r in chosen],
               "scratch_proof": proof, "source_hashes": review["source_hashes"]}
    _write(evidence / "forms_summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")
    scanned = [path for path in evidence.rglob("*") if path.is_file()]
    scanned += [root / "docs/research/organization-sprint/PROPOSED_g393_game_id.diff",
                root / (EVIDENCE.as_posix() + ".md")]
    summary["q6_files_scanned"] = len([p for p in scanned if p.suffix.lower() in TEXT_SUFFIXES])
    summary["q6_hits"] = q6_scan(scanned)
    _write(evidence / "forms_summary.json", json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    print(json.dumps(write_artifacts(), indent=2, sort_keys=True))
