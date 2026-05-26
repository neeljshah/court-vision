"""patch_R28_U2_pace_calibration.py — R28_U2 fix.

Problem
-------
``backfill_pregame_features_2025_26.py`` (R25_R1) computes the leakage-free
expanding-window team ``pace`` via the simple Oliver possession formula
(``poss = FGA + 0.44*FTA + TOV - OREB``; ``pace = poss * 240 / MIN``).

The simple Oliver formula systematically over-counts possessions versus the
NBA Stats ``leaguedashteamstats`` Advanced ``PACE`` field (which is what the
historical seasons 2021-22 through 2024-25 store, since those files come
from ``fetch_historical_seasons.py`` which writes ``team_stats[tid]["pace"]``
verbatim).

Concrete numbers per team_stats cache:
    Season   |  NBA Stats PACE (truth)  |  R25_R1 custom pace
    2024-25  |  99.58                   |  99.57 (file IS NBA Stats)
    2025-26  | 100.22                   | 102.40 (file is custom Oliver)

That ~2.2σ gap is what R27_T3 drift detector flags as
``away_pace`` +1.46σ KS=0.526, ``home_pace`` +1.26σ. Real league pace shift
2024-25 → 2025-26 is only +0.64 PACE — the rest is method mismatch.

Fix
---
Recalibrate every ``home_pace`` / ``away_pace`` (and dependent
``pace_diff`` / ``elo_pace_interaction``) value in
``data/nba/season_games_2025-26.json`` by a per-team multiplicative ratio:

    ratio[team_id] = NBA_Stats_PACE[team_id] / mean(custom_pace[team_id])

This preserves the LEAK-FREE expanding-window per-game variation (the
non-constant-per-team signal R25_R1 introduced) while shifting the global
SCALE onto the same NBA Stats scale used by the historical 2021-22 →
2024-25 files. After the patch the drift detector compares apples-to-
apples.

The patch is idempotent via a marker in the payload:
``payload["pace_calibration_R28_U2"] = {applied_at, n_rows_patched, ...}``.

Atomic write via tmp + os.replace, with a one-shot backup to
``season_games_2025-26.json.bak_R28_U2``.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

SEASON_DEFAULT = "2025-26"

# nba_api static teams keep us out of any network call.
def _team_abbr_to_id() -> Dict[str, int]:
    try:
        from nba_api.stats.static import teams as nba_teams  # type: ignore
        return {t["abbreviation"]: int(t["id"]) for t in nba_teams.get_teams()}
    except Exception:
        # Hard-coded fallback (30 active franchises) — keeps patch usable
        # in environments where nba_api isn't importable.
        return {
            "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751,
            "CHA": 1610612766, "CHI": 1610612741, "CLE": 1610612739,
            "DAL": 1610612742, "DEN": 1610612743, "DET": 1610612765,
            "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
            "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763,
            "MIA": 1610612748, "MIL": 1610612749, "MIN": 1610612750,
            "NOP": 1610612740, "NYK": 1610612752, "OKC": 1610612760,
            "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
            "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759,
            "TOR": 1610612761, "UTA": 1610612762, "WAS": 1610612764,
        }


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def compute_team_ratios(
    rows: List[Dict[str, Any]],
    team_stats: Dict[str, Dict[str, Any]],
    abbr_to_id: Dict[str, int],
) -> Dict[int, float]:
    """team_id → multiplicative pace calibration ratio.

    ratio = NBA_Stats_PACE / mean(custom_pace observed in this file)

    Teams without enough samples or without a team_stats PACE fall back to
    the league-wide mean ratio (or 1.0 if even that is unknown).
    """
    custom_by_tid: Dict[int, List[float]] = {}
    for r in rows:
        ht = r.get("home_team"); at = r.get("away_team")
        hp = r.get("home_pace"); ap = r.get("away_pace")
        ht_id = abbr_to_id.get(ht) if isinstance(ht, str) else None
        at_id = abbr_to_id.get(at) if isinstance(at, str) else None
        if ht_id is not None and isinstance(hp, (int, float)):
            custom_by_tid.setdefault(int(ht_id), []).append(float(hp))
        if at_id is not None and isinstance(ap, (int, float)):
            custom_by_tid.setdefault(int(at_id), []).append(float(ap))

    per_team: Dict[int, float] = {}
    for tid, vals in custom_by_tid.items():
        if not vals:
            continue
        mean_custom = sum(vals) / len(vals)
        if mean_custom <= 0:
            continue
        truth = (team_stats.get(str(tid)) or team_stats.get(tid) or {}).get("pace")
        if truth is None:
            continue
        per_team[int(tid)] = float(truth) / float(mean_custom)

    if not per_team:
        return {}

    # Fall back ratio for teams missing from team_stats.
    league_ratio = sum(per_team.values()) / len(per_team)
    for tid in custom_by_tid:
        per_team.setdefault(int(tid), league_ratio)
    return per_team


def apply_calibration(
    rows: List[Dict[str, Any]],
    ratios: Dict[int, float],
    abbr_to_id: Dict[str, int],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Multiply per-team pace by its calibration ratio; recompute derived fields.

    Returns (new_rows, stats) where stats holds before/after summary numbers.
    """
    league_ratio = (sum(ratios.values()) / len(ratios)) if ratios else 1.0
    out: List[Dict[str, Any]] = []
    n_patched = 0
    before_home: List[float] = []
    after_home: List[float] = []
    before_away: List[float] = []
    after_away: List[float] = []
    for r in rows:
        nr = dict(r)
        ht_id = abbr_to_id.get(nr.get("home_team")) if isinstance(nr.get("home_team"), str) else None
        at_id = abbr_to_id.get(nr.get("away_team")) if isinstance(nr.get("away_team"), str) else None
        h_ratio = ratios.get(int(ht_id), league_ratio) if ht_id is not None else league_ratio
        a_ratio = ratios.get(int(at_id), league_ratio) if at_id is not None else league_ratio

        old_hp = nr.get("home_pace")
        old_ap = nr.get("away_pace")
        new_hp = old_hp
        new_ap = old_ap
        touched = False
        if isinstance(old_hp, (int, float)):
            new_hp = round(float(old_hp) * float(h_ratio), 3)
            nr["home_pace"] = new_hp
            before_home.append(float(old_hp))
            after_home.append(float(new_hp))
            touched = True
        if isinstance(old_ap, (int, float)):
            new_ap = round(float(old_ap) * float(a_ratio), 3)
            nr["away_pace"] = new_ap
            before_away.append(float(old_ap))
            after_away.append(float(new_ap))
            touched = True
        if isinstance(new_hp, (int, float)) and isinstance(new_ap, (int, float)):
            nr["pace_diff"] = round(float(new_hp) - float(new_ap), 3)
            h_elo = float(nr.get("home_elo", 1500.0))
            a_elo = float(nr.get("away_elo", 1500.0))
            nr["elo_pace_interaction"] = round(
                h_elo * float(new_hp) - a_elo * float(new_ap), 2
            )
        if touched:
            n_patched += 1
        out.append(nr)

    def _mean(xs: List[float]) -> Optional[float]:
        return (sum(xs) / len(xs)) if xs else None

    stats = {
        "n_rows":                   len(rows),
        "n_rows_patched":           n_patched,
        "n_teams_with_ratio":       len(ratios),
        "league_mean_ratio":        round(league_ratio, 4),
        "home_pace_mean_before":    _mean(before_home),
        "home_pace_mean_after":     _mean(after_home),
        "away_pace_mean_before":    _mean(before_away),
        "away_pace_mean_after":     _mean(after_away),
    }
    return out, stats


def patch_file(
    season_games_path: Path,
    team_stats_path: Path,
    *,
    backup_path: Optional[Path] = None,
    write_marker: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """Apply pace calibration to season_games file. Returns summary dict."""
    if not season_games_path.exists():
        return {"status": "BLOCKED", "reason": f"missing {season_games_path}"}
    if not team_stats_path.exists():
        return {"status": "BLOCKED", "reason": f"missing {team_stats_path}"}

    payload = _load_json(season_games_path)
    rows = payload["rows"] if isinstance(payload, dict) and "rows" in payload \
        else (list(payload) if isinstance(payload, list) else [])
    if not rows:
        return {"status": "BLOCKED", "reason": "season_games file has no rows"}

    # Idempotency guard.
    if isinstance(payload, dict) and not force \
            and isinstance(payload.get("pace_calibration_R28_U2"), dict):
        return {"status": "ALREADY_APPLIED",
                "marker": payload["pace_calibration_R28_U2"]}

    team_stats = _load_json(team_stats_path)
    if not isinstance(team_stats, dict) or not team_stats:
        return {"status": "BLOCKED", "reason": "team_stats payload empty"}

    abbr2id = _team_abbr_to_id()
    ratios = compute_team_ratios(rows, team_stats, abbr2id)
    if not ratios:
        return {"status": "BLOCKED", "reason": "no team calibration ratios"}
    new_rows, stats = apply_calibration(rows, ratios, abbr2id)

    # Backup once.
    if backup_path is not None and not backup_path.exists():
        try:
            shutil.copy2(season_games_path, backup_path)
        except Exception:
            pass

    if isinstance(payload, dict):
        payload["rows"] = new_rows
        if write_marker:
            payload["pace_calibration_R28_U2"] = {
                "applied_at":      _iso_now(),
                "n_rows_patched":  stats["n_rows_patched"],
                "league_mean_ratio": stats["league_mean_ratio"],
                "home_pace_mean_before": stats["home_pace_mean_before"],
                "home_pace_mean_after":  stats["home_pace_mean_after"],
                "away_pace_mean_before": stats["away_pace_mean_before"],
                "away_pace_mean_after":  stats["away_pace_mean_after"],
                "team_stats_source": str(team_stats_path.name),
            }
    else:
        payload = new_rows

    _atomic_write(season_games_path, payload)
    return {"status": "OK", **stats}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="R28_U2 pace calibration patch for season_games_2025-26.json"
    )
    ap.add_argument("--season", default=SEASON_DEFAULT)
    ap.add_argument("--data-root", default=str(PROJECT_DIR / "data"))
    ap.add_argument("--force", action="store_true",
                    help="Re-apply even if marker already present.")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    sg_path = data_root / "nba" / f"season_games_{args.season}.json"
    ts_path = data_root / "nba" / f"team_stats_{args.season}.json"
    bk_path = sg_path.with_suffix(sg_path.suffix + ".bak_R28_U2")

    t0 = time.time()
    print(f"=== R28_U2 pace calibration ===")
    print(f"  season_games: {sg_path}")
    print(f"  team_stats:   {ts_path}")
    res = patch_file(sg_path, ts_path, backup_path=bk_path, force=args.force)
    print(f"  result: {json.dumps(res, default=str, indent=2)}")
    print(f"  elapsed: {time.time() - t0:.2f}s")
    return 0 if res.get("status") in ("OK", "ALREADY_APPLIED") else 1


if __name__ == "__main__":
    sys.exit(main())
