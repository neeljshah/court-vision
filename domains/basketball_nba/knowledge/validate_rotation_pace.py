"""domains.basketball_nba.knowledge.validate_rotation_pace -- 4 UNTESTED
rotation/pace/foul-environment mechanisms. These are CROSS-SECTIONAL
(team-season) descriptive checks, not live per-game features -- per repo
rule ("no season-final aggregates as per-game features"), nothing here is
wired as a prediction input; it only asks whether the mechanism shows up at
all in our local data. Split-half checks are within-season reliability
checks (first-half-of-season vs second-half), not a forecast.

Run: python -m domains.basketball_nba.knowledge.validate_rotation_pace
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import (
    FOUR_FACTOR_PATH, LEDGER_PATH, load_player_boxscores, team_game_frame,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
ROTATION_MIN = 5.0  # minutes threshold to count as "in the rotation" that night


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _rotation_size(pbox: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_id, team): count of players with min>=ROTATION_MIN."""
    d = pbox[pbox["min"] >= ROTATION_MIN]
    return d.groupby(["game_id", "team", "season"], as_index=False).size().rename(columns={"size": "rot_size"})


def rotation_size_stability_vs_net_rating(pbox: pd.DataFrame, tg: pd.DataFrame) -> Dict[str, Any]:
    rot = _rotation_size(pbox)
    team_season = rot.groupby(["team", "season"])["rot_size"].mean().rename("avg_rot").reset_index()
    net = tg.groupby(["team", "season"])["margin"].mean().rename("avg_net").reset_index()
    m = team_season.merge(net, on=["team", "season"])
    r, p = stats.pearsonr(m["avg_rot"], m["avg_net"])
    return {"hypothesis": "rotation_size_stability_vs_net_rating", "n": int(len(m)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, r, 0.2),
            "note": "cross-sectional r(avg rotation size, avg net margin) across %d team-seasons" % len(m)}


def rotation_size_persists_split_half(pbox: pd.DataFrame) -> Dict[str, Any]:
    d = pbox[pbox["min"] >= ROTATION_MIN].copy()
    mid = d.groupby("team")["date"].transform(lambda s: s.median())
    d["half"] = np.where(d["date"] <= mid, "h1", "h2")
    rot = d.groupby(["game_id", "team", "half"], as_index=False).size().rename(columns={"size": "rot_size"})
    team_half = rot.groupby(["team", "half"])["rot_size"].mean().unstack("half").dropna()
    r, p = stats.pearsonr(team_half["h1"], team_half["h2"])
    return {"hypothesis": "rotation_size_persists_split_half", "n": int(len(team_half)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, r, 0.2),
            "note": "split-half r of avg rotation size across %d teams" % len(team_half)}


def pace_mismatch_variance(pbox: pd.DataFrame, tg: pd.DataFrame) -> Dict[str, Any]:
    team_pace = pbox.groupby(["game_id", "team"])["fga"].sum().groupby("team").mean().rename("pace")
    d = tg.merge(team_pace.rename("team_pace"), on="team").merge(
        team_pace.rename("opp_pace"), left_on="opp", right_on="team")
    d["combined_pace"] = d["team_pace"] + d["opp_pace"]
    d["tercile"] = pd.qcut(d["combined_pace"], 3, labels=["low", "mid", "high"])
    low = d.loc[d["tercile"] == "low", "margin"]
    high = d.loc[d["tercile"] == "high", "margin"]
    stat, p = stats.levene(low, high)
    return {"hypothesis": "pace_mismatch_variance", "n": int(len(d)),
            "effect": round(float(high.std() - low.std()), 3), "p": float(p),
            "verdict": _verdict(p, high.std() - low.std(), 0.5),
            "note": "Levene test margin-std: low-pace tercile std=%.2f (n=%d) vs high-pace tercile std=%.2f (n=%d)"
                    % (low.std(), len(low), high.std(), len(high))}


def ft_rate_environment_wins(tg: pd.DataFrame) -> Dict[str, Any]:
    ff = pd.read_parquet(FOUR_FACTOR_PATH)[["team", "fta_rate_off"]]
    winpct = tg.groupby("team")["win"].mean().rename("win_pct").reset_index()
    m = ff.merge(winpct, on="team")
    r, p = stats.pearsonr(m["fta_rate_off"], m["win_pct"])
    return {"hypothesis": "ft_rate_environment_wins", "n": int(len(m)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, r, 0.2),
            "note": "cross-sectional r(team FTA rate, win%%) across %d teams, single snapshot "
                    "(four_factor_env vs season-pooled win%%, not season-matched exactly)" % len(m)}


def run() -> List[Dict[str, Any]]:
    pbox = load_player_boxscores()
    tg = team_game_frame(pbox)
    rows = [rotation_size_stability_vs_net_rating(pbox, tg), rotation_size_persists_split_half(pbox),
            pace_mismatch_variance(pbox, tg), ft_rate_environment_wins(tg)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_2024_25_2025_26+four_factor_env"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-16s n=%-6d effect=%+.4f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.3, 0.2) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.3, 0.2) == "NULL_LOCAL"
    print("self-check OK")
