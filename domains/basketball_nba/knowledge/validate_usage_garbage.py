"""domains.basketball_nba.knowledge.validate_usage_garbage -- 3 UNTESTED
usage/game-state mechanisms against the 2024-25 + 2025-26 corpus. Leak audit:
every comparison is CONTEMPORANEOUS (same game's outcome vs same game's usage
split) -- a descriptive mechanism check, not a forecast, so no future->past
leak. clutch_usage_compression regresses same-game clutch share on same-game
overall share; nothing here is used as a live pregame feature.

Run: python -m domains.basketball_nba.knowledge.validate_usage_garbage
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import (
    LEDGER_PATH, PBP_FEATURES_PATH, load_player_boxscores, team_game_frame,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
BLOWOUT_MARGIN = 20.0
MIN_MIN = 10.0


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def garbage_time_bench_inflation(pbox: pd.DataFrame, tg: pd.DataFrame) -> Dict[str, Any]:
    d = pbox.merge(tg[["game_id", "team", "margin"]], on=["game_id", "team"])
    d = d[(d["starter"] == 0) & (d["min"] >= 3)]
    d["pts_per_min"] = d["pts"] / d["min"]
    blowout = d[d["margin"].abs() >= BLOWOUT_MARGIN]["pts_per_min"]
    close = d[d["margin"].abs() < BLOWOUT_MARGIN]["pts_per_min"]
    t, p = stats.ttest_ind(blowout, close, equal_var=False)
    return {"hypothesis": "garbage_time_bench_inflation", "n": int(len(d)),
            "effect": round(float(blowout.mean() - close.mean()), 4), "p": float(p),
            "verdict": _verdict(p, blowout.mean() - close.mean(), 0.02),
            "note": "bench pts/min in |margin|>=20 games (%.3f, n=%d) vs closer games (%.3f, n=%d)"
                    % (blowout.mean(), len(blowout), close.mean(), len(close))}


def clutch_usage_compression(pbox: pd.DataFrame) -> Dict[str, Any]:
    pbp = pd.read_parquet(PBP_FEATURES_PATH)
    d = pbox.merge(pbp[["player_id", "game_id", "pbp_clutch_shots_attempted"]],
                    on=["player_id", "game_id"], how="inner")
    team_fga = d.groupby(["game_id", "team"])["fga"].transform("sum")
    team_clutch = d.groupby(["game_id", "team"])["pbp_clutch_shots_attempted"].transform("sum")
    d = d[(team_fga > 0) & (team_clutch > 0)].copy()
    d["overall_share"] = d["fga"] / team_fga
    d["clutch_share"] = d["pbp_clutch_shots_attempted"] / team_clutch
    slope, intercept, r, p_slope, se = stats.linregress(d["overall_share"], d["clutch_share"])
    t_vs_one = (slope - 1.0) / se
    p_vs_one = 2 * (1 - stats.t.cdf(abs(t_vs_one), df=len(d) - 2))
    return {"hypothesis": "clutch_usage_compression", "n": int(len(d)),
            "effect": round(float(slope - 1.0), 4), "p": float(p_vs_one),
            "verdict": _verdict(p_vs_one, slope - 1.0, 0.05),
            "note": "regression slope of clutch_share~overall_share = %.4f (r=%.3f, n=%d); "
                    "slope<1 means high-usage share compresses in clutch" % (slope, r, len(d))}


def player_b2b_scoring_dip(pbox: pd.DataFrame, tg: pd.DataFrame) -> Dict[str, Any]:
    d = pbox.merge(tg[["game_id", "team", "rest_days"]], on=["game_id", "team"]).dropna(subset=["rest_days"])
    d = d[d["min"] >= MIN_MIN].copy()
    d["ts_proxy"] = d["pts"] / (2 * (d["fga"] + 0.44 * d["fta"])).where(lambda s: s > 0)
    d = d.dropna(subset=["ts_proxy"])
    b2b = d[d["rest_days"] == 0]["ts_proxy"]
    rested = d[d["rest_days"] >= 1]["ts_proxy"]
    t, p = stats.ttest_ind(b2b, rested, equal_var=False)
    return {"hypothesis": "player_b2b_scoring_dip", "n": int(len(d)),
            "effect": round(float(b2b.mean() - rested.mean()), 4), "p": float(p),
            "verdict": _verdict(p, b2b.mean() - rested.mean(), 0.01),
            "note": "TS-proxy on 0-rest (%.4f, n=%d) vs >=1-day rest (%.4f, n=%d), min>=%.0f"
                    % (b2b.mean(), len(b2b), rested.mean(), len(rested), MIN_MIN)}


def run() -> List[Dict[str, Any]]:
    pbox = load_player_boxscores()
    tg = team_game_frame(pbox)
    rows = [garbage_time_bench_inflation(pbox, tg), clutch_usage_compression(pbox),
            player_b2b_scoring_dip(pbox, tg)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_2024_25_2025_26"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-28s %-16s n=%-6d effect=%+.4f p=%.4g -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.1, 0.02) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.1, 0.02) == "NULL_LOCAL"
    print("self-check OK")
