"""scripts.platformkit.live_edge.foul_attr.build_foul -- per-possession LEAK-FREE
cumulative foul state, reusing sim2's own segmentation (resolve_segments +
_infer_home_team), the SAME approach PLAYER-ATTR used for scorer attribution.
The possession key emitted here (game_id, season, poss_idx, period,
clock_start, off_is_home, points) is IDENTICAL to sim2_possessions.parquet's
row order -- not a fuzzy join.

SCHEMA NOTE (probe finding): 2025-26 pbp JSON carries actionType == 'foul'
with a populated subType. 2023-24/2024-25 pbp JSON folds fouls into
actionType == 'other' with subType == '' -- the foul TYPE (offensive /
shooting / personal / technical / ...) is only recoverable from the
free-text `description` field. classify_foul() unifies both schemas.

SIMPLIFICATION (documented, not claimed as official box-score truth):
- player personal-foul counter increments on all foul kinds except
  'technical' (matches the 6-foul disqualification rule: offensive,
  defensive, and flagrant fouls count; technicals do not).
- team-foul-for-bonus counter increments on 'defensive' + 'flagrant' kinds
  only (offensive fouls are bonus-exempt); bonus flag is an approximation
  (>=5 team fouls in the period), NOT re-derived from an official bonus
  indicator (none exists in this feed).

LEAK GUARD: every emitted row's counters are a snapshot of the running
per-game counters taken at the moment the possession's OWN segment starts,
strictly BEFORE any of that possession's own actions (incl. its own fouls)
are applied. No future possession's fouls -- or even this possession's own
foul -- ever enters its row.

OUTPUT: data/omni/live_edge/foul_attr/foul_state_<season>.parquet
  game_id, season, poss_idx, period, clock_start, off_is_home, points,
  off_team_fouls_period, def_team_fouls_period, off_bonus, def_bonus,
  pf_map (json string personId(str) -> personal-foul count as-of start),
  + (2024-25 / 2025-26 only, lineup-store seasons) off_lineup_ids,
  def_lineup_ids, off_lineup_max_pf, def_lineup_max_pf,
  off_lineup_foultrouble_ct, def_lineup_foultrouble_ct (on-floor players
  with pf>=4 as-of start), lineup_available.

SUBSTRATE ONLY -- no claims mined here (a later cycle re-mines the B1 grid
with this axis).

CLI: python -m scripts.platformkit.live_edge.foul_attr.build_foul
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.composition.shot_clock_proxy import resolve_segments, _detect_mode
from domains.basketball_nba.lineups.pbp_lineups import _period_length_s
from domains.basketball_nba.sim2.possession_model import _infer_home_team
from scripts.platformkit.live_edge.situation_grid import attach_lineups, LINEUP_SEASONS

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = REPO_ROOT / "data" / "cache" / "team_system"
PBP_DIRS = {"2023-24": _TS / "pbp_2023_24", "2024-25": _TS / "pbp_2024_25", "2025-26": _TS / "pbp"}
OUT_DIR = REPO_ROOT / "data" / "omni" / "live_edge" / "foul_attr"
SIM2_POSSESSIONS_PATH = REPO_ROOT / "data" / "cache" / "ingame" / "sim2_possessions.parquet"

_TECH_RE = re.compile(r"technical|techfoul", re.I)
_OFF_RE = re.compile(r"offensive", re.I)
_FLAG_RE = re.compile(r"flagrant", re.I)


def classify_foul(action: Dict[str, Any]) -> Optional[str]:
    """None if not a foul action; else one of offensive/technical/flagrant/defensive."""
    desc = str(action.get("description") or "")
    is_foul = action.get("actionType") == "foul" or "foul" in desc.lower()
    if not is_foul:
        return None
    sub = str(action.get("subType") or "").lower()
    if sub == "offensive" or _OFF_RE.search(desc):
        return "offensive"
    if sub == "technical" or _TECH_RE.search(desc):
        return "technical"
    if sub == "flagrant" or _FLAG_RE.search(desc):
        return "flagrant"
    return "defensive"


def _team_ids(actions: List[Dict[str, Any]], home: int) -> Optional[int]:
    for a in actions:
        tid = a.get("teamId")
        if tid is not None and int(tid) != home:
            return int(tid)
    return None


def extract_foul_possessions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same segment walk as sim2/build_attr, plus leak-free foul-state snapshot
    taken at each possession's own start. Returns [] if unusable."""
    if not actions:
        return []
    home = _infer_home_team(actions)
    if home is None:
        return []
    away = _team_ids(actions, home)
    mode = _detect_mode(actions)
    seg = {r["action_number"]: r for r in resolve_segments(actions, mode=mode)}
    acts = sorted(actions, key=lambda x: x["actionNumber"])

    poss: List[Dict[str, Any]] = []
    cur_key = None
    cur_period = None
    start_h = start_a = 0
    start_elapsed = 0.0
    prev_h = prev_a = 0
    pf: Dict[int, int] = {}
    team_fouls: Dict[tuple, int] = {}  # (period, teamId) -> count
    pending_snap: tuple = ({}, {})

    def emit(key, sh0, sa0, sh1, sa1, s_elapsed, period, snap):
        off_team = key[1]
        off_is_home = off_team == home
        pts_off = (sh1 - sh0) if off_is_home else (sa1 - sa0)
        if pts_off < 0:
            return
        def_team = away if off_is_home else home
        clock_start = _period_length_s(period) - s_elapsed
        pf_snap, tf_snap = snap
        poss.append({
            "period": int(period), "clock_start": float(clock_start),
            "off_is_home": bool(off_is_home), "points": int(min(pts_off, 6)),
            "off_team_fouls_period": int(tf_snap.get((period, off_team), 0)),
            "def_team_fouls_period": int(tf_snap.get((period, def_team), 0)) if def_team is not None else 0,
            "pf_map": json.dumps({str(k): v for k, v in pf_snap.items() if v > 0}),
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
                emit(cur_key, start_h, start_a, prev_h, prev_a, start_elapsed, cur_period, pending_snap)
            cur_key = key
            cur_period = r["period"]
            start_h, start_a = prev_h, prev_a
            start_elapsed = r["seg_start_s"]
            pending_snap = ({k: v for k, v in pf.items()}, {k: v for k, v in team_fouls.items()})
        kind = classify_foul(a)
        if kind is not None:
            pid, tid, period = a.get("personId"), a.get("teamId"), r["period"]
            if kind != "technical" and pid:
                pf[int(pid)] = pf.get(int(pid), 0) + 1
            if kind in ("defensive", "flagrant") and tid:
                tkey = (period, int(tid))
                team_fouls[tkey] = team_fouls.get(tkey, 0) + 1
        prev_h = int(a.get("scoreHome") or prev_h)
        prev_a = int(a.get("scoreAway") or prev_a)
    if cur_key is not None:
        emit(cur_key, start_h, start_a, prev_h, prev_a, start_elapsed, cur_period, pending_snap)
    return poss


def _lineup_pf(lineup_ids: Any, pf_map_str: str) -> tuple:
    if lineup_ids is None or (isinstance(lineup_ids, float)):
        return (None, None)
    pf_map = json.loads(pf_map_str)
    ids = [x for x in str(lineup_ids).split(",") if x]
    counts = [pf_map.get(pid, 0) for pid in ids]
    if not counts:
        return (None, None)
    return (max(counts), sum(1 for c in counts if c >= 4))


def build_season(season: str, pbp_dir: Path, max_games: Optional[int] = None) -> pd.DataFrame:
    files = sorted(pbp_dir.glob("*.json"))
    if max_games:
        files = files[:max_games]
    rows: List[Dict[str, Any]] = []
    for fp in files:
        try:
            g = json.loads(fp.read_text(encoding="utf-8"))["game"]
            ps = extract_foul_possessions(g["actions"])
        except Exception:
            continue
        for i, p in enumerate(ps):
            p["game_id"] = str(g["gameId"])
            p["season"] = season
            p["poss_idx"] = i
        rows.extend(ps)
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df
    df["off_bonus"] = df["off_team_fouls_period"] >= 5
    df["def_bonus"] = df["def_team_fouls_period"] >= 5
    if season in LINEUP_SEASONS:
        df = attach_lineups(df)
        maxpf = df.apply(lambda r: _lineup_pf(r["off_lineup_ids"], r["pf_map"]), axis=1)
        df["off_lineup_max_pf"], df["off_lineup_foultrouble_ct"] = zip(*maxpf)
        maxpf_d = df.apply(lambda r: _lineup_pf(r["def_lineup_ids"], r["pf_map"]), axis=1)
        df["def_lineup_max_pf"], df["def_lineup_foultrouble_ct"] = zip(*maxpf_d)
    else:
        for c in ("off_lineup_ids", "def_lineup_ids", "off_lineup_max_pf", "def_lineup_max_pf",
                   "off_lineup_foultrouble_ct", "def_lineup_foultrouble_ct"):
            df[c] = None
        df["lineup_available"] = False
    return df


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-games", type=int, default=None)
    args = parser.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for season, d in PBP_DIRS.items():
        df = build_season(season, d, args.max_games)
        out_path = OUT_DIR / f"foul_state_{season.replace('-', '_')}.parquet"
        df.to_parquet(out_path, index=False)
        n_lineup = int(df["lineup_available"].sum()) if len(df) and "lineup_available" in df else 0
        print(f"{season}: poss_rows={len(df)} lineup_rows={n_lineup} -> {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
