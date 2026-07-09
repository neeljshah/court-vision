"""domains.basketball_nba.knowledge.validate_usage_events -- 4 UNTESTED
usage/foul-trouble/hub-passing mechanisms (mechanisms.md #26 usage-
redistribution persistence, #27 assist-hub concentration, #32 early-foul-
trouble minutes reduction, #33 star-injury usage-vacuum event-study). Leak
audit: #26/#33 build absence occasions from player_boxscores DNP rows within
a single already-played season (descriptive, not a forecast feature); #32
joins first-half (Q1+Q2) quarter_box fouls to that SAME game's final minutes
(contemporaneous, no future leak); #27 is a single-season cross-section
(30 teams), not a per-game feature.

Run: python -m domains.basketball_nba.knowledge.validate_usage_events
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, REPO, load_player_boxscores
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
QBOX_DIR = REPO / "data" / "cache" / "quarter_box"
FF_ENV_PATH = REPO / "data" / "cache" / "team_system" / "four_factor_env.parquet"
SEASON = "2025-26"
MIN_GAMES = 30
MAX_MISSED = 15


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _absence_occasions(pbox: pd.DataFrame) -> pd.DataFrame:
    """For each (team, high-usage player) with a real in-season absence stretch,
    one row per (game_id, teammate, fga_share, games_since_absence_start)."""
    d = pbox[pbox["season"] == SEASON].copy()
    team_games = d.groupby("team")["game_id"].apply(lambda s: sorted(s.unique())).to_dict()
    out: List[Dict[str, Any]] = []
    for team, sched in team_games.items():
        td = d[d["team"] == team]
        counts = td.groupby("player_id")["game_id"].nunique()
        regulars = counts[(counts >= MIN_GAMES) & (counts <= len(sched) - 1)].index
        for pid in regulars:
            played = set(td[td["player_id"] == pid]["game_id"])
            missed = len(sched) - len(played)
            if missed == 0 or missed > MAX_MISSED:
                continue
            since = 0
            for gid in sched:
                if gid not in played:
                    since += 1
                    game = td[td["game_id"] == gid]
                    team_fga = game["fga"].sum()
                    if team_fga <= 0:
                        continue
                    for _, row in game.iterrows():
                        if row["player_id"] == pid:
                            continue
                        out.append({"team": team, "missing_pid": pid, "teammate_pid": row["player_id"],
                                    "game_id": gid, "fga_share": row["fga"] / team_fga,
                                    "games_since_absence": since})
                else:
                    since = 0
    return pd.DataFrame(out)


def _teammate_baseline(pbox: pd.DataFrame) -> pd.DataFrame:
    d = pbox[pbox["season"] == SEASON].copy()
    team_fga = d.groupby("game_id")["fga"].transform("sum")
    d = d[team_fga > 0].copy()
    d["fga_share"] = d["fga"] / team_fga.loc[d.index]
    return d.groupby(["team", "player_id"])["fga_share"].mean().rename("baseline_share").reset_index()


def usage_redistribution_persistence(pbox: pd.DataFrame) -> Dict[str, Any]:
    occ = _absence_occasions(pbox)
    if occ.empty:
        return {"hypothesis": "usage_redistribution_persistence", "n": 0, "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "no team/high-usage-player pair had a real mid-season absence stretch"}
    occ = occ.sort_values("game_id")
    occ["occ_rank"] = occ.groupby(["team", "missing_pid"]).cumcount()
    occ["half"] = np.where(occ["occ_rank"] % 2 == 0, "A", "B")
    piv = occ.groupby(["team", "missing_pid", "teammate_pid", "half"])["fga_share"].mean().unstack("half").dropna()
    piv = piv[(piv.index.get_level_values("teammate_pid") >= 0)]
    if len(piv) < 20:
        return {"hypothesis": "usage_redistribution_persistence", "n": int(len(piv)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "fewer than 20 teammate-pairs with both split halves populated"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "usage_redistribution_persistence", "n": int(len(piv)), "effect": round(float(r), 4),
            "p": float(p), "verdict": _verdict(p, 0.1, r),
            "note": "split-half (odd/even absence occasions) pearson r of teammate fga_share-during-absence, "
                    "%d team/missing-player/teammate triples, season %s" % (len(piv), SEASON)}


def star_injury_usage_vacuum_event_study(pbox: pd.DataFrame) -> Dict[str, Any]:
    occ = _absence_occasions(pbox)
    base = _teammate_baseline(pbox)
    if occ.empty:
        return {"hypothesis": "star_injury_usage_vacuum_event_study", "n": 0, "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "no absence occasions available (see usage_redistribution_persistence)"}
    m = occ.merge(base.rename(columns={"player_id": "teammate_pid"}), on=["team", "teammate_pid"])
    m["deviation"] = m["fga_share"] - m["baseline_share"]
    g1 = m[m["games_since_absence"] == 1]["deviation"]
    g2plus = m[m["games_since_absence"] >= 2]["deviation"]
    t, p = stats.ttest_ind(g1, g2plus, equal_var=False)
    eff = float(g1.mean() - g2plus.mean())
    return {"hypothesis": "star_injury_usage_vacuum_event_study", "n": int(len(g1) + len(g2plus)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 0.01, eff),
            "note": "teammate fga_share deviation-from-normal-baseline, game-1-of-absence (%.4f, n=%d) vs "
                    "games>=2-of-absence (%.4f, n=%d)" % (g1.mean(), len(g1), g2plus.mean(), len(g2plus))}


def assist_hub_concentration_offrtg(pbox: pd.DataFrame) -> Dict[str, Any]:
    d = pbox[pbox["season"] == SEASON]
    team_ast = d.groupby("team")["ast"].sum()
    top_ast = d.groupby(["team", "player_id"])["ast"].sum().groupby("team").max()
    hub_share = (top_ast / team_ast).rename("hub_share")
    ff = pd.read_parquet(FF_ENV_PATH)[["team", "ppp_all_off"]]
    m = ff.merge(hub_share, on="team")
    m["hub_share_sq"] = m["hub_share"] ** 2
    X = np.column_stack([np.ones(len(m)), m["hub_share"], m["hub_share_sq"]])
    beta, *_ = np.linalg.lstsq(X, m["ppp_all_off"], rcond=None)
    resid = m["ppp_all_off"] - X @ beta
    dof = len(m) - 3
    sigma2 = float((resid @ resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se_quad = float(np.sqrt(cov[2, 2]))
    t_quad = beta[2] / se_quad
    p_quad = float(2 * (1 - stats.t.cdf(abs(t_quad), df=dof)))
    return {"hypothesis": "assist_hub_concentration_offrtg", "n": int(len(m)), "effect": round(float(beta[2]), 4),
            "p": p_quad, "verdict": _verdict(p_quad, 0.5, beta[2]),
            "note": "OLS ppp_all_off ~ hub_share + hub_share^2, quadratic coef=%.4f (linear=%.4f), "
                    "30-team cross-section season %s" % (beta[2], beta[1], SEASON)}


def _first_half_fouls(game_ids: set) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for gid in game_ids:
        pf = {}
        ok = True
        for q in ("q1", "q2"):
            fp = QBOX_DIR / f"{gid}_{q}.json"
            if not fp.exists():
                ok = False
                break
            d = json.loads(fp.read_text(encoding="utf-8"))
            for pl in d["players"]:
                pf[pl["player_id"]] = pf.get(pl["player_id"], 0) + (pl.get("pf") or 0)
        if not ok:
            continue
        for pid, fouls in pf.items():
            rows.append({"game_id": gid, "player_id": pid, "first_half_pf": fouls})
    return pd.DataFrame(rows)


def foul_trouble_minutes_reduction(pbox: pd.DataFrame) -> Dict[str, Any]:
    q1_files = glob.glob(str(QBOX_DIR / "*_q1.json"))
    game_ids = {os.path.basename(f).split("_q1")[0] for f in q1_files}
    fh = _first_half_fouls(game_ids)
    if fh.empty:
        return {"hypothesis": "foul_trouble_minutes_reduction", "n": 0, "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "no game had both q1+q2 quarter_box files"}
    starters = pbox[pbox["starter"] == 1][["game_id", "player_id", "min", "season"]]
    d = fh.merge(starters, on=["game_id", "player_id"])
    season_avg = pbox[pbox["starter"] == 1].groupby(["season", "player_id"])["min"].mean().rename("season_avg_min")
    d = d.merge(season_avg, on=["season", "player_id"])
    d["gap"] = d["min"] - d["season_avg_min"]
    trouble = d[d["first_half_pf"] >= 2]["gap"]
    fine = d[d["first_half_pf"] < 2]["gap"]
    t, p = stats.ttest_ind(trouble, fine, equal_var=False)
    eff = float(trouble.mean() - fine.mean())
    return {"hypothesis": "foul_trouble_minutes_reduction", "n": int(len(trouble) + len(fine)),
            "effect": round(eff, 4), "p": float(p), "verdict": _verdict(p, 1.0, eff),
            "note": "starter minutes-gap-vs-season-avg, >=2 first-half fouls (%.2f, n=%d) vs <2 (%.2f, n=%d), "
                    "quarter_box q1+q2 coverage" % (trouble.mean(), len(trouble), fine.mean(), len(fine))}


def run() -> List[Dict[str, Any]]:
    pbox = load_player_boxscores()
    rows = [usage_redistribution_persistence(pbox), star_injury_usage_vacuum_event_study(pbox),
            assist_hub_concentration_offrtg(pbox), foul_trouble_minutes_reduction(pbox)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_2025_26+quarter_box+four_factor_env"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-32s %-16s n=%-6d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    print("self-check OK")
