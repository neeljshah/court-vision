"""G400 step 0: whole-pool census, old-identity disjointness and the sealed draw.

Consumes the pod census JSONL (one row per retained basketball-family section, with
an actual ffprobe) plus the landed old identities, then emits census.csv,
game_disjointness.csv and draw.csv. Nothing here opens a rating input or a detector.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g400_prepare as rails

MIN_SPAN_S = 11.0
CENSUS_FIELDS = ("video_id", "competition", "sport_tag", "canonical_game", "title",
                 "sections", "median_section_file", "median_section_path",
                 "median_section_bytes", "source_digest", "width", "height", "fps",
                 "duration_s", "probe_status", "eligibility", "exclusion_reason")
DRAW_FIELDS = ("draw_index", "population_index", "competition", "canonical_game",
               "video_id", "source_digest", "median_section_path",
               "median_section_bytes", "width", "height", "fps", "duration_s")
WORD = re.compile(r"[a-z0-9]+")


def canonical(title: str, competition: str) -> str:
    """A resolved canonical game key; an empty title is an unresolved identity."""
    tokens = WORD.findall(title.lower())
    return competition + "|" + " ".join(tokens) if tokens else ""


def old_identities(frames_csv: Path, context_csv: Path) -> set[str]:
    found: set[str] = set()
    with frames_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            found.add(row["game"])
    with context_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            found.add(row["video_id"])
    return found


def load_digests(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        digest, _, name = line.partition("  ")
        if digest and name:
            found[name.strip()] = digest
    return found


def build_census(rows: list[dict], digests: dict[str, str]) -> list[dict]:
    """One census row per retained video id, with its median-PTS section pinned."""
    by_game: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        if row.get("parse") == "ok":
            by_game[row["video_id"]].append(row)
    census: list[dict] = []
    for video_id, group in sorted(by_game.items()):
        ordered = sorted(group, key=lambda row: (row["offset_s"], row["file"]))
        median = ordered[(len(ordered) - 1) // 2]
        title = str(median.get("title") or "")
        competition = str(median["league_tag"])
        census.append({
            "video_id": video_id, "competition": competition,
            "sport_tag": median["sport_tag"],
            "canonical_game": canonical(title, competition), "title": title,
            "sections": len(ordered), "median_section_file": median["file"],
            "median_section_path": median["path"],
            "median_section_bytes": median["bytes"],
            "source_digest": digests.get(median["path"], ""),
            "width": median.get("width") or 0, "height": median.get("height") or 0,
            "fps": round(float(median.get("fps") or 0.0), 6),
            "duration_s": round(float(median.get("duration_s") or 0.0), 6),
            "probe_status": median.get("probe_status", ""),
            "eligibility": "ELIGIBLE", "exclusion_reason": ""})
    return census


def apply_exclusions(census: list[dict], old: set[str]) -> None:
    """Name every exclusion in the census itself, before any draw is computed."""
    seen_canonical: dict[str, str] = {}
    for row in sorted(census, key=lambda item: (item["competition"],
                                                item["canonical_game"],
                                                item["source_digest"])):
        reasons = []
        if row["video_id"] in old:
            reasons.append("OLD_IDENTITY_OVERLAP")
        if not row["canonical_game"]:
            reasons.append("UNRESOLVED_GAME_IDENTITY")
        if row["probe_status"] != "ok" or not row["source_digest"]:
            reasons.append("NOT_DECODABLE_OR_UNHASHED")
        if float(row["duration_s"]) < MIN_SPAN_S:
            reasons.append("SPAN_TOO_SHORT_FOR_TEN_TARGETS")
        if row["canonical_game"] and row["canonical_game"] in seen_canonical:
            reasons.append("ALTERNATE_UPLOAD_OF_" + seen_canonical[row["canonical_game"]])
        if reasons:
            row["eligibility"] = "EXCLUDED"
            row["exclusion_reason"] = ";".join(reasons)
        else:
            seen_canonical[row["canonical_game"]] = row["video_id"]


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")).encode(
                "ascii", "replace").decode("ascii") for field in fields})


def run(args) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in
            Path(args.census_jsonl).read_text(encoding="utf-8").splitlines() if line]
    digests = load_digests(Path(args.digests))
    old = old_identities(Path(args.frames_csv), Path(args.context_csv))
    census = build_census(rows, digests)
    apply_exclusions(census, old)
    write_csv(out / "census.csv", CENSUS_FIELDS,
              sorted(census, key=lambda row: (row["competition"], row["canonical_game"],
                                              row["source_digest"])))
    disjoint = [{"video_id": row["video_id"], "competition": row["competition"],
                 "canonical_game": row["canonical_game"],
                 "in_old_identity_set": int(row["video_id"] in old),
                 "old_title_resolvable": "NOT_RESOLVABLE",
                 "eligibility": row["eligibility"],
                 "exclusion_reason": row["exclusion_reason"]} for row in census]
    write_csv(out / "game_disjointness.csv",
              ("video_id", "competition", "canonical_game", "in_old_identity_set",
               "old_title_resolvable", "eligibility", "exclusion_reason"), disjoint)
    eligible = [row for row in census if row["eligibility"] == "ELIGIBLE"]
    premise = {"census_utc": args.census_utc, "retained_sections": len(rows),
               "retained_games": len(census), "old_identities": len(old),
               "eligible_games": len(eligible),
               "competitions": sorted({row["competition"] for row in eligible}),
               "old_overlap_excluded": sorted(row["video_id"] for row in census
                                              if row["video_id"] in old),
               "required_games": rails.GAMES,
               "premise": "TRUE" if len(eligible) >= rails.GAMES else "FALSE"}
    (out / "premise.json").write_text(json.dumps(premise, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii")
    print("PREMISE", premise["premise"], "eligible", len(eligible),
          "competitions", len(premise["competitions"]))
    if premise["premise"] != "TRUE":
        return 1
    population = sorted(eligible, key=lambda row: (row["competition"],
                                                   row["canonical_game"],
                                                   row["source_digest"]))
    order = {row["video_id"]: index for index, row in enumerate(population)}
    selected = rails.draw_games(population)
    rails.assert_frozen_draw(population, selected)
    draw = [{"draw_index": index + 1, "population_index": order[row["video_id"]],
             **{field: row[field] for field in DRAW_FIELDS[2:]}}
            for index, row in enumerate(selected)]
    write_csv(out / "draw.csv", DRAW_FIELDS, draw)
    print("DRAW", len(draw), "games from population", len(population))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_census")
    for flag in ("--census-jsonl", "--digests", "--frames-csv", "--context-csv",
                 "--out-dir", "--census-utc"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
