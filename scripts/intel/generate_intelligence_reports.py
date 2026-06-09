"""generate_intelligence_reports.py — synthesize the FULL intelligence-report layer.

Assembles the already-shipped atlas sections (28 player + 16 team) plus the
persistent profile-factory JSON into ONE coherent descriptive dossier per entity,
for EVERY player present across the atlas parquets / PLAYER_INDEX and ALL 30 teams.

This is a read-side ASSEMBLER over existing data. It does NOT build new
intelligence, does NOT call any external feed, and does NOT call an LLM
per-entity — narratives are generated deterministically by the threshold/
percentile rules already living in ``src/intel/player_report.py`` and
``src/intel/team_report.py``.

Outputs (additive, under data/cache/profiles/):
  * players/<id>.json          -> adds a top-level "intelligence_report" section
                                  (the full dossier) in-place, preserving the
                                  profile-factory content.
  * PLAYER_REPORTS.json         -> {player_id: full dossier} convenience index.
  * teams/<TRI>_dossier.json    -> full team dossier (same file the team script
                                  already writes; refreshed here).
  * TEAM_REPORTS.json           -> {tricode: full dossier} convenience index.
  * PLAYER_INDEX.json           -> each player entry gets a one-line
                                  "intel_headline" (archetype + how-they-play +
                                  completeness) + "intel_completeness".
  * TEAM_INDEX.json             -> each team entry gets "intel_headline" +
                                  "intel_completeness".

Performance: the per-player atlas lookup in player_report._atlas_row does a full
boolean-mask scan per (section, player). For ~1250 players x 28 sections that is
slow, so this script pre-indexes every atlas section by player_id once and
monkeypatches a fast O(1) lookup in. Team side is already vectorized in
team_report (atlases + league context loaded once).

Usage:
  python scripts/intel/generate_intelligence_reports.py            # all + write
  python scripts/intel/generate_intelligence_reports.py --no-write # build+summarize
  python scripts/intel/generate_intelligence_reports.py --limit 25 # smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import src.intel.player_report as pr  # noqa: E402
from src.intel.team_report import (  # noqa: E402
    TEAMS_PROF_DIR, build_all_team_reports,
)

PROFILES_DIR = ROOT / "data" / "cache" / "profiles"
PLAYERS_DIR = PROFILES_DIR / "players"
PLAYER_INDEX = PROFILES_DIR / "PLAYER_INDEX.json"
TEAM_INDEX = PROFILES_DIR / "TEAM_INDEX.json"
PLAYER_REPORTS = PROFILES_DIR / "PLAYER_REPORTS.json"
TEAM_REPORTS = PROFILES_DIR / "TEAM_REPORTS.json"


# --------------------------------------------------------------------------- #
# Fast atlas indexing — pre-build {section: {player_id: row_dict}} once and
# monkeypatch player_report._atlas_row to an O(1) dict lookup.
# --------------------------------------------------------------------------- #
def install_fast_atlas_lookup() -> Dict[str, set]:
    """Index every atlas player section by player_id; patch pr._atlas_row.

    Returns {section: set(player_ids)} so the caller can compute the full id
    universe without re-reading parquets.
    """
    section_index: Dict[str, Dict[int, Dict[str, Any]]] = {}
    section_ids: Dict[str, set] = {}
    for section in pr.ATLAS_SECTIONS:
        df = pr._load_atlas_section(section)
        if df is None or "player_id" not in df.columns:
            section_index[section] = {}
            section_ids[section] = set()
            continue
        idx: Dict[int, Dict[str, Any]] = {}
        # to_dict("records") once, keyed by player_id (last row wins, matching iloc[0]
        # semantics is not preserved — but atlas sections are 1 row/player; verified).
        for rec in df.to_dict("records"):
            pid = rec.get("player_id")
            if pid is None:
                continue
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                continue
            # keep first occurrence (matches original sub.iloc[0])
            if pid not in idx:
                idx[pid] = rec
        section_index[section] = idx
        section_ids[section] = set(idx.keys())

    def _fast_atlas_row(section: str, player_id: int) -> Optional[Dict[str, Any]]:
        return section_index.get(section, {}).get(int(player_id))

    pr._atlas_row = _fast_atlas_row  # type: ignore[assignment]
    return section_ids


# --------------------------------------------------------------------------- #
# Player universe = union of all atlas section ids + PLAYER_INDEX ids
# --------------------------------------------------------------------------- #
def player_universe(section_ids: Dict[str, set]) -> List[int]:
    ids: set = set()
    for s in section_ids.values():
        ids.update(s)
    if PLAYER_INDEX.exists():
        try:
            idx = json.loads(PLAYER_INDEX.read_text(encoding="utf-8"))
            for p in idx.get("players", []):
                if p.get("player_id") is not None:
                    ids.add(int(p["player_id"]))
        except Exception:
            pass
    return sorted(ids)


# --------------------------------------------------------------------------- #
# Headlines (one-liners stamped into the index files)
# --------------------------------------------------------------------------- #
def _player_headline(rep: Dict[str, Any]) -> str:
    arch = (((rep.get("archetype_role") or {}).get("data") or {}).get("archetype") or {})
    label = arch.get("label", "Role Player")
    secondary = arch.get("secondary")
    head = label if not secondary else f"{label} ({secondary})"
    narr = rep.get("narrative") or ""
    comp = rep.get("data_completeness") or {}
    sp = comp.get("sections_present", 0)
    st = comp.get("sections_total", 0)
    # keep it one line: archetype + first narrative sentence + completeness
    first = narr.split(". ")[0].strip()
    if first and not first.endswith("."):
        first += "."
    return f"{head} — {first} [{sp}/{st} sections]"


def _team_headline(dossier: Dict[str, Any]) -> str:
    htp = dossier.get("how_they_play") or ""
    comp = dossier.get("completeness") or {}
    npres = comp.get("n_blocks_present", 0)
    nexp = comp.get("n_blocks_expected", 0)
    # leading offense/defense identity sentence
    first = htp.split(". ")[0].strip()
    if first and not first.endswith("."):
        first += "."
    return f"{first} [{npres}/{nexp} blocks]"


# --------------------------------------------------------------------------- #
# Player generation
# --------------------------------------------------------------------------- #
def generate_players(
    pids: List[int], write: bool, build_date: str
) -> Dict[str, Any]:
    reports: Dict[str, Any] = {}
    headlines: Dict[int, str] = {}
    completeness: Dict[int, Dict[str, Any]] = {}
    comp_scores: List[float] = []
    section_present_counts: Dict[str, int] = {s: 0 for s in pr.ATLAS_SECTIONS}
    n_with_profile = 0
    errors = 0

    for pid in pids:
        try:
            rep = pr.build_player_report(pid)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  ERR player {pid}: {exc}")
            continue
        reports[str(pid)] = rep
        headlines[pid] = _player_headline(rep)
        comp = rep.get("data_completeness") or {}
        completeness[pid] = {
            "score": comp.get("score"),
            "sections_present": comp.get("sections_present"),
            "sections_total": comp.get("sections_total"),
            "sections_high_conf": comp.get("sections_high_conf"),
        }
        if comp.get("score") is not None:
            comp_scores.append(float(comp["score"]))
        # tally per-section presence for low-coverage report
        missing = set(comp.get("low_or_missing_sections") or [])
        for s in pr.ATLAS_SECTIONS:
            # "present" = appears with confidence (not in low_or_missing) — but
            # low_or_missing includes low-conf-present too. Use prov walk instead.
            pass
        # accurate per-section presence via provenance walk
        _tally_presence(rep, section_present_counts)

        if write:
            _write_player_inplace(pid, rep, build_date)
            if reports[str(pid)].get("player_name") is not None:
                n_with_profile += 1

    if write:
        PLAYER_REPORTS.write_text(
            json.dumps(reports, indent=1, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        _update_player_index(headlines, completeness, build_date)

    mean_comp = round(sum(comp_scores) / len(comp_scores), 4) if comp_scores else None
    n = len(reports)
    low_cov = {
        s: round(c / n, 3) for s, c in sorted(section_present_counts.items(), key=lambda kv: kv[1])
        if n and (c / n) < 0.60
    }
    return {
        "n_players": n,
        "errors": errors,
        "mean_completeness": mean_comp,
        "section_coverage": {s: round(c / n, 3) for s, c in section_present_counts.items()} if n else {},
        "low_coverage_sections": low_cov,
    }


def _tally_presence(rep: Dict[str, Any], counts: Dict[str, int]) -> None:
    """Walk the report provenance and increment counts for sections that are present."""
    seen: set = set()

    def _walk(p: Any):
        if isinstance(p, dict):
            if "source" in p and "present" in p:
                if p.get("present"):
                    src = str(p["source"]).replace("atlas_player_", "").replace(".parquet", "")
                    seen.add(src)
            else:
                for v in p.values():
                    _walk(v)

    for block in ("archetype_role", "scoring", "playmaking", "rebounding",
                  "defense", "situational", "consistency_durability"):
        b = rep.get(block) or {}
        _walk(b.get("provenance"))
    for s in seen:
        if s in counts:
            counts[s] += 1


def _write_player_inplace(pid: int, rep: Dict[str, Any], build_date: str) -> None:
    """Add/refresh the 'intelligence_report' section inside the player's profile JSON.

    If no profile file exists yet (atlas-only player), create a minimal stub so the
    dossier is still persisted and indexable.
    """
    path = PLAYERS_DIR / f"{pid}.json"
    if path.exists():
        try:
            prof = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            prof = {"player_id": pid}
    else:
        prof = {
            "player_id": pid,
            "player_name": rep.get("player_name"),
            "schema_version": "profile_stub/1.0",
            "sections": {},
            "_provenance": {"_note": "stub created by generate_intelligence_reports "
                                     "(atlas-only player, no profile-factory file)"},
        }
    prof["intelligence_report"] = rep
    prof.setdefault("_provenance", {})
    if isinstance(prof.get("_provenance"), dict):
        prof["_provenance"]["intelligence_report_built"] = build_date
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prof, indent=1, default=str, ensure_ascii=False),
                    encoding="utf-8")


def _update_player_index(headlines, completeness, build_date) -> None:
    if not PLAYER_INDEX.exists():
        return
    idx = json.loads(PLAYER_INDEX.read_text(encoding="utf-8"))
    for p in idx.get("players", []):
        pid = p.get("player_id")
        if pid is None:
            continue
        pid = int(pid)
        if pid in headlines:
            p["intel_headline"] = headlines[pid]
            p["intel_completeness"] = completeness.get(pid)
    idx["intel_reports_built"] = build_date
    idx["n_intel_reports"] = len(headlines)
    PLAYER_INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False),
                            encoding="utf-8")


# --------------------------------------------------------------------------- #
# Team generation
# --------------------------------------------------------------------------- #
def generate_teams(write: bool, build_date: str) -> Dict[str, Any]:
    reports = build_all_team_reports(build_date=build_date)
    headlines: Dict[str, str] = {}
    completeness: Dict[str, Any] = {}
    cov_scores: List[float] = []
    block_present: Dict[str, int] = {}

    for tri, d in reports.items():
        headlines[tri] = _team_headline(d)
        comp = d.get("completeness") or {}
        completeness[tri] = {
            "n_blocks_present": comp.get("n_blocks_present"),
            "n_blocks_expected": comp.get("n_blocks_expected"),
            "coverage_pct": comp.get("coverage_pct"),
        }
        if comp.get("coverage_pct") is not None:
            cov_scores.append(float(comp["coverage_pct"]))
        for b in comp.get("present", []):
            block_present[b] = block_present.get(b, 0) + 1

    if write:
        TEAMS_PROF_DIR.mkdir(parents=True, exist_ok=True)
        for tri, d in reports.items():
            (TEAMS_PROF_DIR / f"{tri}_dossier.json").write_text(
                json.dumps(d, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        TEAM_REPORTS.write_text(
            json.dumps(reports, indent=1, default=str, ensure_ascii=False),
            encoding="utf-8")
        _update_team_index(headlines, completeness, build_date)

    n = len(reports)
    mean_cov = round(sum(cov_scores) / len(cov_scores), 2) if cov_scores else None
    low_cov = {b: round(c / n, 3) for b, c in block_present.items() if n and (c / n) < 0.80}
    return {
        "n_teams": n,
        "mean_coverage_pct": mean_cov,
        "block_coverage": {b: round(c / n, 3) for b, c in block_present.items()} if n else {},
        "low_coverage_blocks": low_cov,
    }


def _update_team_index(headlines, completeness, build_date) -> None:
    if not TEAM_INDEX.exists():
        return
    idx = json.loads(TEAM_INDEX.read_text(encoding="utf-8"))
    for t in idx.get("teams", []):
        tri = t.get("team")
        if tri in headlines:
            t["intel_headline"] = headlines[tri]
            t["intel_completeness"] = completeness.get(tri)
    idx["intel_reports_built"] = build_date
    TEAM_INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False),
                          encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="cap #players (smoke test)")
    ap.add_argument("--build-date", default=date.today().isoformat())
    ap.add_argument("--players-only", action="store_true")
    ap.add_argument("--teams-only", action="store_true")
    args = ap.parse_args()
    write = not args.no_write

    t0 = time.time()
    section_ids = install_fast_atlas_lookup()

    summary: Dict[str, Any] = {"build_date": args.build_date, "write": write}

    if not args.teams_only:
        pids = player_universe(section_ids)
        if args.limit:
            pids = pids[: args.limit]
        print(f"Building player reports for {len(pids)} players ...")
        summary["players"] = generate_players(pids, write, args.build_date)
        print(f"  done players in {round(time.time()-t0,1)}s")

    if not args.players_only:
        t1 = time.time()
        print("Building team reports for all teams ...")
        summary["teams"] = generate_teams(write, args.build_date)
        print(f"  done teams in {round(time.time()-t1,1)}s")

    summary["elapsed_sec"] = round(time.time() - t0, 1)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
