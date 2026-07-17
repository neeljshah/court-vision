"""scripts.platformkit.pod_sprint.player_value_asof -- Family P (player-grain availability
+ value), walk-forward, leak-free. See DEEP_FEATURES_PREREG.md P1-P4.

LOCKED value definition (premise check 2026-07-17): plus_minus IS available in
data/domains/basketball_nba/player_boxscores.parquet (0 nulls across 77744 rows, seasons
2023-24..2025-26, team abbrs already canonical -- GSW/NYK/NOP/SAS/UTA/WAS, matching
asof_box_accuracy._CANON's target set). PRIMARY definition used: per-minute margin
contribution = plus_minus / min, exponentially-weighted (alpha=_ALPHA) per player, shrunk
toward the walk-forward GLOBAL per-minute mean by career minutes played (shrinkage constant
_SHRINK_K minutes, ~15 games of starter run -- no formal tuning). The prereg's game-score
fallback is NOT used.

Grain: one output row per (date, team_abbr) team-game. For team-game T, every feature is
read from state as of strictly BEFORE T -- built only from games through that team's
PREVIOUS game. State updates for a game_id happen only AFTER BOTH teams' features for that
game_id have been emitted, so a team's read never sees its own game's stats, not even the
OPPONENT's same-game stats (which would otherwise leak into the shared global-mean shrinkage
target). See test_player_value_asof.test_leak_trap.

P1 roster_value_asof = sum over players in the team's PREVIOUS game of (shrunk EW
    per-minute value * EW minutes share) -- an expected-available-roster-value proxy.
P2 star_absence_delta = team's trailing-10-game max(P1) - current P1 (0.0 before history).
P3 continuity = weighted Jaccard (Ruzicka: sum-min / sum-max) of last-game minutes-share
    rotation vs the trailing-5-game aggregate rotation (0.0 before history).
P4 top_heavy = share of P1 held by the top-2 contributing players (0.0 if P1~0 or empty).

CLI: python -m scripts.platformkit.pod_sprint.player_value_asof
     writes data/domains/basketball_nba/player_value_features.parquet
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Dict, List

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_NBA = _REPO / "data" / "domains" / "basketball_nba"
_OUT = _NBA / "player_value_features.parquet"

_ALPHA = 0.15       # EW smoothing, both per-minute value and minutes share
_SHRINK_K = 500.0   # shrinkage constant in career minutes (~15 games of starter run)
_TOP_HEAVY_EPS = 0.02  # |P1| floor before computing the top2/P1 ratio (near-zero P1 blows
_TOP_HEAVY_CLIP = 3.0  # the ratio up); both are numerical guards, not tuned (measured: >99th
                        # pctl of |P1| on the real corpus is ~0.4, so this clip only bites
                        # the P1~0 tail -- see player_value_features.parquet describe()).


def _shares(minutes: Dict[int, float]) -> Dict[int, float]:
    total = sum(minutes.values())
    return {k: v / total for k, v in minutes.items()} if total > 0 else {}


def _ruzicka(a: Dict[int, float], b: Dict[int, float]) -> float:
    """Weighted Jaccard (sum-min / sum-max) between two player->share dicts."""
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    s_min = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    s_max = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return s_min / s_max if s_max > 0 else 0.0


def build_player_value_features(pb: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward pass over player_boxscores, one output row per (date, team_abbr)
    team-game. See module docstring for the LOCKED definitions + leak discipline."""
    pb = pb.sort_values(["date", "game_id"]).reset_index(drop=True)

    v_ew: Dict[int, float] = {}
    share_ew: Dict[int, float] = {}
    career_min: Dict[int, float] = {}
    global_sum_pm = 0.0
    global_min = 0.0

    last_game_minutes: Dict[str, Dict[int, float]] = {}  # team -> {pid: min} of its PREVIOUS game
    rotation_hist: Dict[str, deque] = {}                 # team -> deque[{pid: min}], maxlen=5
    p1_hist: Dict[str, deque] = {}                       # team -> deque[float], maxlen=10

    rows: List[dict] = []
    for game_id, gg in pb.groupby("game_id", sort=False):
        date = gg["date"].iloc[0]
        global_mean = (global_sum_pm / global_min) if global_min > 0 else 0.0

        # ---- EMIT features for every team in this game_id using PRE-game_id state ----
        per_team_rows: Dict[str, dict] = {}
        for team, tgrp in gg.groupby("team", sort=False):
            roster_shares = _shares(last_game_minutes.get(team, {}))
            contributions = {}
            for pid, sh in roster_shares.items():
                cm = career_min.get(pid, 0.0)
                w = cm / (cm + _SHRINK_K)
                v_shrunk = w * v_ew.get(pid, global_mean) + (1.0 - w) * global_mean
                contributions[pid] = v_shrunk * share_ew.get(pid, 0.0)
            p1 = sum(contributions.values())

            trail10 = p1_hist.setdefault(team, deque(maxlen=10))
            star_absence_delta = (max(trail10) - p1) if trail10 else 0.0

            rot5 = rotation_hist.setdefault(team, deque(maxlen=5))
            if rot5:
                last_share = _shares(rot5[-1])
                trail5_agg: Dict[int, float] = {}
                for g_minutes in rot5:
                    for pid, mins in g_minutes.items():
                        trail5_agg[pid] = trail5_agg.get(pid, 0.0) + mins
                continuity = _ruzicka(last_share, _shares(trail5_agg))
            else:
                continuity = 0.0

            if contributions and abs(p1) > _TOP_HEAVY_EPS:
                top2 = sorted(contributions.values(), reverse=True)[:2]
                top_heavy = max(-_TOP_HEAVY_CLIP, min(_TOP_HEAVY_CLIP, sum(top2) / p1))
            else:
                top_heavy = 0.0

            per_team_rows[team] = {
                "date": date, "team_abbr": team, "game_id": game_id,
                "roster_value_asof": p1, "star_absence_delta": star_absence_delta,
                "continuity": continuity, "top_heavy": top_heavy,
            }
        rows.extend(per_team_rows.values())

        # ---- UPDATE state with THIS game_id's own data, for FUTURE games only ----
        for team, tgrp in gg.groupby("team", sort=False):
            team_min_total = float(tgrp["min"].sum())
            this_game_minutes: Dict[int, float] = {}
            for r in tgrp.itertuples():
                pid, minutes, pm = r.player_id, float(r.min), float(r.plus_minus)
                if minutes <= 0:
                    continue
                this_game_minutes[pid] = minutes
                raw_pm = pm / minutes
                v_prev = v_ew.get(pid, global_mean)
                v_ew[pid] = v_prev + _ALPHA * (raw_pm - v_prev)
                this_share = minutes / team_min_total if team_min_total > 0 else 0.0
                share_prev = share_ew.get(pid)
                share_ew[pid] = this_share if share_prev is None else share_prev + _ALPHA * (this_share - share_prev)
                career_min[pid] = career_min.get(pid, 0.0) + minutes
                global_sum_pm += pm
                global_min += minutes
            p1_hist[team].append(per_team_rows[team]["roster_value_asof"])
            rotation_hist[team].append(this_game_minutes)
            last_game_minutes[team] = this_game_minutes

    return pd.DataFrame(rows)


def run_cli() -> Dict:
    pb = pd.read_parquet(_NBA / "player_boxscores.parquet")
    feats = build_player_value_features(pb)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(_OUT, index=False)
    return {"status": "ok", "n_team_games": len(feats),
            "out": str(_OUT.relative_to(_REPO)).replace("\\", "/")}


def _main() -> int:
    rep = run_cli()
    print(f"player_value_features: {rep['n_team_games']} team-games -> {rep['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
