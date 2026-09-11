"""G404 step 0: whole-pool census, old-identity disjointness and the supply premise.

Consumes the pod census JSONL plus every landed old-identity table and emits
census.csv, game_disjointness.csv and premise.json. Nothing here opens a rating
input, a detector or a gate; no draw is made unless the sealed supply bar holds.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path

MIN_SPAN_S = 11.0
GAMES = 30
CENSUS_FIELDS = ("video_id", "competition", "sport_tag", "canonical_game", "title",
                 "sections", "median_section_file", "median_section_path",
                 "median_section_bytes", "source_digest", "width", "height", "fps",
                 "duration_s", "probe_status", "eligibility", "exclusion_reason")
DISJOINT_FIELDS = ("video_id", "competition", "canonical_game", "in_old_identity_set",
                   "old_title_resolvable", "eligibility", "exclusion_reason")
WORD = re.compile(r"[a-z0-9]+")


def canonical(title: str, competition: str) -> str:
    """A resolved canonical game key; an empty title is an unresolved identity."""
    tokens = WORD.findall(title.lower())
    return competition + "|" + " ".join(tokens) if tokens else ""


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def old_identities(sources: list[tuple[Path, str, str]]) -> tuple[set[str], list[dict]]:
    """Union every landed old identity column; each source names its own role."""
    found: set[str] = set()
    ledger: list[dict] = []
    for path, field, role in sources:
        ids = {row[field].strip() for row in read_rows(path) if row.get(field, "").strip()}
        found |= ids
        ledger.append({"path": str(path).replace("\\", "/"), "field": field,
                       "role": role, "identities": len(ids)})
    return found, ledger


def load_digests(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        digest, _, name = line.partition("  ")
        if digest and name:
            found[name.strip()] = digest
    return found


def build_census(rows: list[dict], digests: dict[str, str]) -> list[dict]:
    """One census row per retained video id, with its median-offset section pinned."""
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
            "sport_tag": median["sport_tag"], "title": title,
            "canonical_game": canonical(title, competition),
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
    seen: dict[str, str] = {}
    for row in sorted(census, key=lambda item: (item["competition"], item["canonical_game"],
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
        if row["canonical_game"] and row["canonical_game"] in seen:
            reasons.append("ALTERNATE_UPLOAD_OF_" + seen[row["canonical_game"]])
        if reasons:
            row["eligibility"] = "EXCLUDED"
            row["exclusion_reason"] = ";".join(reasons)
        else:
            seen[row["canonical_game"]] = row["video_id"]


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")).encode(
                "ascii", "replace").decode("ascii") for field in fields})


def census_order(row: dict) -> tuple[str, str, str]:
    return (row["competition"], row["canonical_game"], row["source_digest"])


def run(args) -> int:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in
            Path(args.census_jsonl).read_text(encoding="utf-8").splitlines() if line]
    sources = [(Path(item.split("::")[0]), item.split("::")[1], item.split("::")[2])
               for item in args.old_source]
    old, ledger = old_identities(sources)
    census = build_census(rows, load_digests(Path(args.digests)))
    apply_exclusions(census, old)
    write_csv(out / "census.csv", CENSUS_FIELDS, sorted(census, key=census_order))
    write_csv(out / "game_disjointness.csv", DISJOINT_FIELDS,
              [{"video_id": row["video_id"], "competition": row["competition"],
                "canonical_game": row["canonical_game"],
                "in_old_identity_set": int(row["video_id"] in old),
                "old_title_resolvable": "NOT_RESOLVABLE",
                "eligibility": row["eligibility"],
                "exclusion_reason": row["exclusion_reason"]}
               for row in sorted(census, key=census_order)])
    eligible = [row for row in census if row["eligibility"] == "ELIGIBLE"]
    competitions = sorted({row["competition"] for row in eligible})
    premise = {"census_utc": args.census_utc, "retained_sections": len(rows),
               "retained_games": len(census), "old_identity_sources": ledger,
               "old_identities": len(old), "eligible_games": len(eligible),
               "competitions": competitions, "required_games": GAMES,
               "required_competitions": 2,
               "old_overlap_excluded": sorted(row["video_id"] for row in census
                                              if row["video_id"] in old),
               "premise": "TRUE" if len(eligible) >= GAMES and len(competitions) >= 2
                          else "FALSE"}
    (out / "premise.json").write_text(json.dumps(premise, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii", newline="\n")
    print("PREMISE", premise["premise"], "eligible", len(eligible),
          "of required", GAMES, "competitions", len(competitions))
    return 0 if premise["premise"] == "TRUE" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_census")
    for flag in ("--census-jsonl", "--digests", "--out-dir", "--census-utc"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--old-source", action="append", required=True,
                        help="path::field::role triple naming one landed identity table")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
