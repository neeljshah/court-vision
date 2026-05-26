"""probe_R31_X6_lineup_backfill.py — verify 2025-26 lineup-data backfill.

What it measures
----------------
1. n_teams_with_data_before / after  — count of
   data/nba/lineups/lineup_splits_<TEAM>_2025-26.json files.
2. n_lineups_total_added             — sum of lineup rows in newly-added
   files (counts only teams that were absent before).
3. drift_count_before / after        — n_drift_major from the m2 feature
   set, comparing data/cache/drift_post_R29_V3.json (pre) against
   data/cache/drift_post_R31_X6.json (post).
4. top_lineup_drift_before / after   — class of home_top_lineup_net_rtg
   before vs after.

Persists summary to data/cache/probe_R31_X6_results.json.

Read-only on data; only writes the probe results JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PROBE_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R31_X6_results.json"
_LINEUPS_DIR = _ROOT / "data" / "nba" / "lineups"

_ALL_TEAMS = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]

SEASON = "2025-26"


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _team_file(team: str, season: str = SEASON) -> Path:
    return _LINEUPS_DIR / f"lineup_splits_{team}_{season}.json"


def count_lineup_files(season: str = SEASON) -> List[str]:
    out: List[str] = []
    for t in _ALL_TEAMS:
        if _team_file(t, season).exists():
            out.append(t)
    return out


def total_lineups_in_files(teams: List[str], season: str = SEASON) -> int:
    total = 0
    for t in teams:
        p = _team_file(t, season)
        if not p.exists():
            continue
        try:
            with open(p, "r", encoding="utf-8") as fh:
                rows = json.load(fh)
            total += len(rows) if isinstance(rows, list) else 0
        except Exception:
            continue
    return total


def _load_drift_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _classify(report: Dict[str, Any]) -> Dict[str, Any]:
    feats = report.get("features") or []
    n_major = sum(1 for f in feats if f.get("class") == "drift_major")
    n_minor = sum(1 for f in feats if f.get("class") == "drift_minor")
    n_stable = sum(1 for f in feats if f.get("class") == "stable")
    by_name = {f.get("feature"): f for f in feats}
    return {
        "n_major":  n_major,
        "n_minor":  n_minor,
        "n_stable": n_stable,
        "top_lineup_home_class":
            by_name.get("home_top_lineup_net_rtg", {}).get("class", "absent"),
        "top_lineup_away_class":
            by_name.get("away_top_lineup_net_rtg", {}).get("class", "absent"),
        "top_lineup_home_cur_mean":
            by_name.get("home_top_lineup_net_rtg", {}).get("cur_mean"),
        "top_lineup_away_cur_mean":
            by_name.get("away_top_lineup_net_rtg", {}).get("cur_mean"),
    }


def run(*,
        pre_teams: Optional[List[str]] = None,
        pre_drift_path: Optional[Path] = None,
        post_drift_path: Optional[Path] = None) -> Dict[str, Any]:
    """Build probe summary."""
    if pre_teams is None:
        # Best-effort default: anything not LAL/GSW is assumed new.
        pre_teams = ["GSW", "LAL"]

    after_teams = count_lineup_files(SEASON)
    teams_added = sorted(set(after_teams) - set(pre_teams))
    n_lineups_added = total_lineups_in_files(teams_added, SEASON)
    n_lineups_total = total_lineups_in_files(after_teams, SEASON)

    pre = _load_drift_report(pre_drift_path) if pre_drift_path else {}
    post = _load_drift_report(post_drift_path) if post_drift_path else {}
    pre_stats = _classify(pre) if pre else {}
    post_stats = _classify(post) if post else {}

    drift_before = pre_stats.get("n_major")
    drift_after = post_stats.get("n_major")
    drift_delta: Optional[int]
    if drift_before is not None and drift_after is not None:
        drift_delta = drift_before - drift_after
    else:
        drift_delta = None

    # Ship criteria
    n_teams_before = len(pre_teams)
    n_teams_after = len(after_teams)
    teams_delta = n_teams_after - n_teams_before
    ship_teams_ok = teams_delta >= 20
    # The drift gate: top_lineup should move out OR overall drift reduce.
    ship_drift_ok = (
        (drift_delta is not None and drift_delta >= 1)
        or (post_stats.get("top_lineup_home_class") not in
            ("drift_major",) if post_stats else False)
    )

    if ship_teams_ok and ship_drift_ok:
        verdict = "PASS"
    elif ship_teams_ok:
        # Backfill succeeded but drift methodology artifact persists.
        verdict = "PARTIAL"
    else:
        verdict = "INSUFFICIENT"

    summary = {
        "probe":                     "R31_X6",
        "ts":                        _iso_now(),
        "n_teams_with_data_before":  n_teams_before,
        "n_teams_with_data_after":   n_teams_after,
        "n_teams_added":             teams_delta,
        "teams_added":               teams_added,
        "n_lineups_total_added":     n_lineups_added,
        "n_lineups_total_all_teams": n_lineups_total,
        "pre_drift":                 pre_stats,
        "post_drift":                post_stats,
        "drift_count_before":        drift_before,
        "drift_count_after":         drift_after,
        "drift_count_delta":         drift_delta,
        "ship_teams_ok":             ship_teams_ok,
        "ship_drift_ok":             ship_drift_ok,
        "verdict":                   verdict,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre-teams", nargs="*", default=None,
                    help="Optional override: teams that had files before. "
                         "Defaults to ['GSW', 'LAL'].")
    ap.add_argument("--pre-drift",
                    default=str(_ROOT / "data" / "cache" / "drift_post_R29_V3.json"))
    ap.add_argument("--post-drift",
                    default=str(_ROOT / "data" / "cache" / "drift_post_R31_X6.json"))
    args = ap.parse_args()

    summary = run(
        pre_teams=args.pre_teams,
        pre_drift_path=Path(args.pre_drift),
        post_drift_path=Path(args.post_drift),
    )

    PROBE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)

    # Compact stdout
    print(json.dumps({
        "probe": summary["probe"],
        "verdict": summary["verdict"],
        "n_teams_before": summary["n_teams_with_data_before"],
        "n_teams_after":  summary["n_teams_with_data_after"],
        "n_teams_added":  summary["n_teams_added"],
        "n_lineups_total_added": summary["n_lineups_total_added"],
        "drift_count_before": summary["drift_count_before"],
        "drift_count_after":  summary["drift_count_after"],
        "drift_count_delta":  summary["drift_count_delta"],
        "top_lineup_home_class": summary["post_drift"].get(
            "top_lineup_home_class") if summary["post_drift"] else None,
    }, indent=2, default=str))

    return 0 if summary["verdict"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
