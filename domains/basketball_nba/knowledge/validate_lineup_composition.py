"""domains.basketball_nba.knowledge.validate_lineup_composition -- 3 UNTESTED
lineup/rotation mechanisms (mechanisms.md #24 clutch-rotation-size, #25
rim-pressure-def x DREB, #30 bench-lineup continuity), reusing the existing
leak-checked PBP/stint pipeline in domains.basketball_nba.prereg.nba_hypotheses
rather than reimplementing the rebound-matching logic. Leak audit: all three
are CONTEMPORANEOUS descriptive checks (same-game/-season structure, not a
forecast feature) -- no season-final-aggregate-as-live-feature use.

Run: python -m domains.basketball_nba.knowledge.validate_lineup_composition
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge._data import LEDGER_PATH, PBP_FEATURES_PATH, load_player_boxscores
from domains.basketball_nba.prereg.nba_hypotheses import REPO_ROOT, _load_missed_shots_and_rebounds, _other_team
from domains.basketball_nba.prereg.stats_common import fit_single
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
STINTS_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
ZONE_ONOFF_DIR = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"
PBP_2024_25 = REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25"


def _verdict(p, min_abs_effect: float, effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def clutch_lineup_shortening(pbox: pd.DataFrame) -> Dict[str, Any]:
    pbp = pd.read_parquet(PBP_FEATURES_PATH)
    d = pbox.merge(pbp[["player_id", "game_id", "pbp_clutch_shots_attempted", "pbp_clutch_pts_scored"]],
                    on=["player_id", "game_id"], how="left")
    d[["pbp_clutch_shots_attempted", "pbp_clutch_pts_scored"]] = \
        d[["pbp_clutch_shots_attempted", "pbp_clutch_pts_scored"]].fillna(0)
    d["in_clutch"] = ((d["pbp_clutch_shots_attempted"] > 0) | (d["pbp_clutch_pts_scored"] > 0))
    full = d[d["min"] >= 5].groupby(["game_id", "team"])["player_id"].nunique().rename("full_size")
    clutch = d[d["in_clutch"]].groupby(["game_id", "team"])["player_id"].nunique().rename("clutch_size")
    m = pd.concat([full, clutch], axis=1).dropna()
    t, p = stats.ttest_rel(m["clutch_size"], m["full_size"])
    eff = float((m["clutch_size"] - m["full_size"]).mean())
    return {"hypothesis": "clutch_lineup_shortening", "n": int(len(m)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, 0.3, eff),
            "note": "paired: clutch distinct-player count (%.2f) vs full-game >=5min rotation size (%.2f), "
                    "team-games reaching a clutch state, n=%d" % (m["clutch_size"].mean(), m["full_size"].mean(), len(m))}


def rim_pressure_def_dreb(pbox: pd.DataFrame, season: str = "2024_25") -> Dict[str, Any]:
    zo = pd.read_parquet(ZONE_ONOFF_DIR / f"zone_onoff_{season}.parquet")
    zo = zo[(zo["rim_fga_on"] >= 30) & (zo["rim_fga_off"] >= 30)].dropna(
        subset=["rim_efg_allowed_on", "rim_efg_allowed_off"]).copy()
    zo["rim_pressure_def"] = zo["rim_efg_allowed_off"] - zo["rim_efg_allowed_on"]  # positive = tighter rim D on-court
    season_label = season.replace("_", "-")
    pb = pbox[(pbox["season"] == season_label) & (pbox["min"] > 0)]
    tot = pb.groupby("player_id").agg(dreb=("dreb", "sum"), minutes=("min", "sum"))
    tot = tot[tot["minutes"] >= 200]
    tot["dreb_per_min"] = tot["dreb"] / tot["minutes"]
    m = zo.merge(tot[["dreb_per_min"]], left_on="player_id", right_index=True)
    r, p = stats.pearsonr(m["rim_pressure_def"], m["dreb_per_min"])
    return {"hypothesis": "rim_pressure_def_dreb", "n": int(len(m)), "effect": round(float(r), 4), "p": float(p),
            "verdict": _verdict(p, 0.1, r),
            "note": "pearson r, rim_efg_allowed(off-on) vs season DREB/min, zone_onoff_%s, "
                    "rim_fga>=30 both states, minutes>=200 (n=%d)" % (season, len(m))}


def bench_continuity_dreb(pbox: pd.DataFrame, season: str = "2024_25") -> Dict[str, Any]:
    stints = pd.read_parquet(STINTS_DIR / f"stints_{season}.parquet")
    clean = stints[stints["n_on_court"] == 5].copy()
    season_label = season.replace("_", "-")
    starter_map = pbox[pbox["season"] == season_label].set_index(["game_id", "player_id"])["starter"].to_dict()

    def _starters_on(row) -> int:
        ids = [int(x) for x in str(row["lineup_key"]).split(",")]
        return sum(int(starter_map.get((row["game_id"], pid), 0)) for pid in ids)

    clean["starter_count"] = clean.apply(_starters_on, axis=1)
    bench_clean = clean[clean["starter_count"] <= 2]

    shots = _load_missed_shots_and_rebounds(pbp_dir=PBP_2024_25)
    team_ids_by_game = clean.groupby("game_id")["team_id"].unique().apply(list).to_dict()
    shots["defending_team_id"] = shots.apply(
        lambda r: _other_team(team_ids_by_game.get(r["game_id"], []), r["team_id"]), axis=1)
    shots = shots.dropna(subset=["defending_team_id"])
    shots["defending_team_id"] = shots["defending_team_id"].astype("int64")

    right = bench_clean.rename(columns={"team_id": "defending_team_id"})[
        ["game_id", "period", "defending_team_id", "start_s"]]
    matched = pd.merge_asof(
        shots.sort_values("elapsed_s"), right.sort_values("start_s"),
        left_on="elapsed_s", right_on="start_s", by=["game_id", "period", "defending_team_id"],
        direction="backward")
    matched["continuity_s"] = matched["elapsed_s"] - matched["start_s"]
    matched = matched.dropna(subset=["continuity_s"])
    if len(matched) < 50:
        return {"hypothesis": "bench_continuity_dreb", "n": int(len(matched)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "bench-heavy (<=2 starters on court) stint sample too thin"}
    fit = fit_single(matched, "is_dreb ~ continuity_s", kind="logit")
    return {"hypothesis": "bench_continuity_dreb", "n": fit["n"], "effect": round(fit["effect"], 6), "p": fit["p"],
            "verdict": _verdict(fit["p"], 0.0001, fit["effect"]),
            "note": "logit is_dreb~continuity_s restricted to <=2-starters-on-court stints, season %s "
                    "(cf. full-lineup #1 eff=0.000574 p=1.9e-16 n=116960)" % season}


def run() -> List[Dict[str, Any]]:
    pbox = load_player_boxscores()
    rows = [clutch_lineup_shortening(pbox), rim_pressure_def_dreb(pbox), bench_continuity_dreb(pbox)]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "player_boxscores_2024_25_2025_26+stints_2024_25+zone_onoff_2024_25"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-28s %-16s n=%-6d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.02, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.02, 0.1) == "NOT_TESTABLE"
    print("self-check OK")
