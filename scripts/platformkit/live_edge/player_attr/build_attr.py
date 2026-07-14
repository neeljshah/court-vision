"""scripts.platformkit.live_edge.player_attr.build_attr -- scorer->possession
attribution, leak-free. Reuses sim2's own segmentation (resolve_segments +
_infer_home_team) so the possession key this emits (period, clock_start,
off_is_home, points, game_id, season) is IDENTICAL to sim2_possessions.parquet
-- not a fuzzy join, the same deterministic walk with scoring personIds kept
instead of discarded.

OUTPUT: one row per possession --
  data/omni/live_edge/player_attr/scorer_possession_<season>.parquet
  game_id, season, period, clock_start, off_is_home, points, poss_idx,
  scorer_player_id (nullable: 0-point poss, or a points>0 poss with no
  matched made-shot/FT action -- rare data gap), scorer_points, n_scorers.

LEAK: fully determined by actions inside the possession itself (same instant
sim2's own row is knowable); no future-possession info enters a row.

CLI: python -m scripts.platformkit.live_edge.player_attr.build_attr
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import resolve_segments, _detect_mode
from domains.basketball_nba.lineups.pbp_lineups import _period_length_s
from domains.basketball_nba.sim2.possession_model import _infer_home_team

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = REPO_ROOT / "data" / "cache" / "team_system"
PBP_DIRS = {"2023-24": _TS / "pbp_2023_24", "2024-25": _TS / "pbp_2024_25", "2025-26": _TS / "pbp"}
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "player_attr"
SIM2_POSSESSIONS_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"

_SCORE_TYPES = {"2pt", "3pt", "freethrow"}


def _shot_points(action_type: str) -> int:
    return 3 if action_type == "3pt" else 1 if action_type == "freethrow" else 2


def extract_scorer_possessions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same segment walk as sim2's extract_possessions, plus per-segment
    scorer accumulation. Returns [] if unusable (mirrors sim2 behavior)."""
    if not actions:
        return []
    home = _infer_home_team(actions)
    if home is None:
        return []
    mode = _detect_mode(actions)
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
    acts = sorted(actions, key=lambda x: x["actionNumber"])

    poss: List[Dict[str, Any]] = []
    cur_key = None
    start_h = start_a = 0
    start_elapsed = 0.0
    cur_period = None
    prev_h = prev_a = 0
    scorers: Dict[int, int] = {}

    def emit(key, sh0, sa0, sh1, sa1, s_elapsed, e_elapsed, period, scorer_pts: Dict[int, int]):
        off_team = key[1]
        off_is_home = off_team == home
        pts_off = (sh1 - sh0) if off_is_home else (sa1 - sa0)
        if pts_off < 0:
            return
        clock_start = _period_length_s(period) - s_elapsed
        primary_id, primary_pts = None, 0
        for pid, pts in scorer_pts.items():
            if pts > primary_pts:
                primary_id, primary_pts = pid, pts
        poss.append({
            "period": int(period), "clock_start": float(clock_start),
            "off_is_home": bool(off_is_home), "points": int(min(pts_off, 6)),
            "scorer_player_id": primary_id, "scorer_points": int(primary_pts),
            "n_scorers": len(scorer_pts),
        })

    for a in acts:
        r = seg.get(a["actionNumber"])
        if r is None or r["seg_team"] is None:
            prev_h = int(a.get("scoreHome") or prev_h)
            prev_a = int(a.get("scoreAway") or prev_a)
            continue
        key = (r["period"], r["seg_team"], r["seg_start_s"])
        if key != cur_key:
            if cur_key is not None:
                emit(cur_key, start_h, start_a, prev_h, prev_a, start_elapsed, r["elapsed_s"], cur_period, scorers)
            cur_key = key
            cur_period = r["period"]
            start_h, start_a = prev_h, prev_a
            start_elapsed = r["seg_start_s"]
            scorers = {}
        if a.get("actionType") in _SCORE_TYPES and a.get("shotResult") == "Made" and a.get("personId"):
            pid = int(a["personId"])
            scorers[pid] = scorers.get(pid, 0) + _shot_points(a["actionType"])
        prev_h = int(a.get("scoreHome") or prev_h)
        prev_a = int(a.get("scoreAway") or prev_a)
    if cur_key is not None:
        emit(cur_key, start_h, start_a, prev_h, prev_a, start_elapsed, _period_length_s(cur_period), cur_period, scorers)
    return poss


def build_season(season: str, pbp_dir: Path, max_games: Optional[int] = None) -> pd.DataFrame:
    files = sorted(pbp_dir.glob("*.json"))
    if max_games:
        files = files[:max_games]
    rows: List[Dict[str, Any]] = []
    for fp in files:
        try:
            g = json.loads(fp.read_text(encoding="utf-8"))["game"]
            ps = extract_scorer_possessions(g["actions"])
        except Exception:
            continue
        for i, p in enumerate(ps):
            p["game_id"] = str(g["gameId"])
            p["season"] = season
            p["poss_idx"] = i
        rows.extend(ps)
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-games", type=int, default=None)
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for season, d in PBP_DIRS.items():
        df = build_season(season, d, args.max_games)
        out_path = OUT_DIR / f"scorer_possession_{season.replace('-', '_')}.parquet"
        df.to_parquet(out_path, index=False)
        n_scored = int((df["points"] > 0).sum()) if len(df) else 0
        n_attr = int(((df["points"] > 0) & df["scorer_player_id"].notna()).sum()) if len(df) else 0
        rate = (n_attr / n_scored) if n_scored else 0.0
        print(f"{season}: poss_rows={len(df)} scored_poss={n_scored} attributed={n_attr} rate={rate:.4f} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
