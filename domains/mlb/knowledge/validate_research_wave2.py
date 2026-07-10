"""domains.mlb.knowledge.validate_research_wave2 -- the 3 UNTESTED rows
seeded 2026-07-10 by the round-2 research-wave commit (mechanisms.md #46
catcher-framing multi-season trend, #47 TTO x platoon-handedness
interaction, #48 platoon-split persistence). One file: all 3 read from the
same savant_full__* parquets and reuse the sibling designs already CLOSED
in this ledger (edge-zone/taken-desc from wave1's compassionate-umpire row,
trip_number derivation from validate_situational_state.tto_decay_net_of_velo,
split-half persistence from validate_persistence_skill).

Leak audit: #46 is a season-over-season DESCRIPTIVE comparison of a skill
metric across already-completed seasons (no future-into-past leak -- 2023
and 2025 are both fully in the past relative to each other and to "now").
#47 is a contemporaneous within-PA comparison (trip_number/same_hand are
both resolved by the time xwOBA is observed on that PA). #48 is a
split-half-by-date stability check, same non-forecast framing as #15/#34.

Premise checks (this session): pitchers.parquet has no age/bio field
(['event_id','date','season','home_team','away_team','home_sp_name',
'away_sp_name','home_sp_present','away_sp_present','home_innings',
'away_innings']) and no bio parquet exists under data/domains/mlb/ --
confirms #46's scope-reduction to a within-catcher trend proxy is still
accurate. savant_full__2023/2024/2025.parquet all present locally with
fielder_2/zone/description/stand/p_throws/batter/pitcher/game_pk/
at_bat_number/estimated_woba_using_speedangle/game_date all present.
platoon_split_index.parquet confirmed single-window (season='2022_2023',
not split-half testable as-is) -- #48 re-derives from savant_full__2025
per its own spec rather than using that parquet directly.

Run: python -m domains.mlb.knowledge.validate_research_wave2
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import LEDGER_PATH, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
EDGE_ZONES = {11, 12, 13, 14}
TAKEN_DESC = {"ball", "called_strike"}
ON_BASE_EVENTS = {"single", "double", "triple", "walk", "hit_by_pitch", "home_run", "intent_walk"}

MIN_EFFECT = {"catcher_framing_multiseason_trend": 0.01,
              "tto_x_platoon_interaction": 0.005,
              "platoon_split_persistence": 0.15}


def _verdict(p, effect, hyp: str) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    base = hyp.split("__")[0]
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= MIN_EFFECT[base]) else "NULL_LOCAL"


def _framing_rate_by_catcher(df: pd.DataFrame, min_n: int = 500) -> pd.Series:
    """#46 helper: per-catcher (fielder_2) called-strike rate on taken
    edge-zone(11-14) pitches -- same shadow-zone-corner methodology as
    wave1's compassionate_umpire_count_zone / mlb_framing_claims.jsonl."""
    q = df.dropna(subset=["zone", "description", "fielder_2"])
    q = q[q["zone"].isin(EDGE_ZONES) & q["description"].isin(TAKEN_DESC)]
    cnt = q.groupby("fielder_2").size()
    ok = cnt[cnt >= min_n].index
    q = q[q["fielder_2"].isin(ok)]
    return q.groupby("fielder_2")["description"].apply(lambda s: (s == "called_strike").mean())


def _league_edge_rate(df: pd.DataFrame) -> float:
    """League-wide called-strike rate on taken edge-zone pitches, ALL catchers
    (not min-n filtered) -- the confound control for catcher_framing_multiseason_trend."""
    q = df.dropna(subset=["zone", "description"])
    q = q[q["zone"].isin(EDGE_ZONES) & q["description"].isin(TAKEN_DESC)]
    return float((q["description"] == "called_strike").mean())


def catcher_framing_multiseason_trend(s23: pd.DataFrame, s24: pd.DataFrame, s25: pd.DataFrame) -> Dict[str, Any]:
    """#46: paired one-sample t-test of (season3_rate - season1_rate) for
    catchers with >=500 borderline takes in ALL 3 seasons (2024 used only
    to confirm continuity, per the row's own spec).

    Confound check (this run): the raw per-catcher delta is CONFIRMED_LOCAL
    (eff=-0.013, p=9e-14) but the LEAGUE-WIDE edge-zone called-strike rate
    itself moved by almost the identical amount over the same window
    (2023=0.0607 -> 2025=0.0485, delta=-0.0121) -- a plausible zone/measurement
    or rule shift, not catcher aging. The row's claim is catcher-SPECIFIC
    decline, so the naive (raw) test cannot separate that from a league-wide
    shift; each catcher's rate is therefore league-demeaned per season before
    the paired test, same discipline as validate_situational_state's
    leverage_index_conversion confound adjustment."""
    hyp = "catcher_framing_multiseason_trend"
    r23, r24, r25 = _framing_rate_by_catcher(s23), _framing_rate_by_catcher(s24), _framing_rate_by_catcher(s25)
    common = r23.index.intersection(r24.index).intersection(r25.index)
    if len(common) < 5:
        return {"hypothesis": hyp, "n": int(len(common)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 5 catchers with >=500 borderline takes in all 3 seasons",
                "corpus": "savant_full__2023+2024+2025"}
    lg23, lg25 = _league_edge_rate(s23), _league_edge_rate(s25)
    raw_delta = r25.loc[common] - r23.loc[common]
    adj_delta = (r25.loc[common] - lg25) - (r23.loc[common] - lg23)
    t, p = stats.ttest_1samp(adj_delta, 0.0)
    eff = float(adj_delta.mean())
    return {"hypothesis": hyp, "n": int(len(common)), "effect": round(eff, 5), "p": float(p),
            "verdict": _verdict(p, eff, hyp),
            "note": ("league-demeaned paired one-sample t-test, season3(2025)-season1(2023) called-strike-rate "
                      "delta net of league-wide edge-zone rate that season, n=%d catchers (>=500 borderline "
                      "takes/season, present all 3 seasons); RAW (non-adjusted) delta was %.5f p=%.2e -- "
                      "CONFIRMED_LOCAL on its own, but that magnitude matches the league-wide edge-zone rate "
                      "shift (2023=%.4f -> 2025=%.4f, delta=%.4f) almost exactly, i.e. the raw signal is a "
                      "league-wide confound (zone/rule/measurement shift), not catcher-specific decline -- the "
                      "league-adjusted verdict above is the honest test of the row's actual (catcher-specific) claim"
                      % (len(common), float(raw_delta.mean()), stats.ttest_1samp(raw_delta, 0.0)[1],
                         lg23, lg25, lg25 - lg23)),
            "corpus": "savant_full__2023+2024+2025"}


def tto_x_platoon_interaction(pa: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    """#47: OLS xwOBA ~ trip_number + same_hand + trip_number:same_hand,
    PA-level, trip_number capped at 4 (reuses validate_situational_state's
    tto_decay_net_of_velo derivation, minus the velo term)."""
    hyp = "tto_x_platoon_interaction__%s" % half_label
    d = pa.dropna(subset=["estimated_woba_using_speedangle", "stand", "p_throws"]).copy()
    d = d[d["p_throws"].isin(["L", "R"]) & d["stand"].isin(["L", "R"])]
    d = d.sort_values(["game_pk", "pitcher", "batter", "at_bat_number"])
    d["trip_number"] = d.groupby(["game_pk", "pitcher", "batter"]).cumcount() + 1
    d = d[d["trip_number"] <= 4]
    if len(d) < 50:
        return {"hypothesis": hyp, "n": int(len(d)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 50 PAs"}
    same_hand = (d["stand"] == d["p_throws"]).astype(float).values
    trip = d["trip_number"].values.astype(float)
    X = np.column_stack([np.ones(len(d)), trip, same_hand, trip * same_hand])
    y = d["estimated_woba_using_speedangle"].values.astype(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(d) - X.shape[1]
    sigma2 = float((resid @ resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = float(np.sqrt(cov[3, 3]))
    t = beta[3] / se
    p = float(2 * (1 - stats.t.cdf(abs(t), df=dof)))
    eff = float(beta[3])
    return {"hypothesis": hyp, "n": int(len(d)), "effect": round(eff, 5), "p": p, "verdict": _verdict(p, eff, hyp),
            "note": "OLS xwOBA ~ trip_number + same_hand + trip_number:same_hand, PA-level (trips<=4), "
                    "interaction coef=%.5f, n=%d" % (eff, len(d))}


def _combine(base_hyp: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Row's own bar requires BOTH halves to individually clear p<ALPHA AND
    the declared effect-size bar, same direction -- mirrors wave1's >=2-
    corpora replication rule (a single significant half is PROVISIONAL,
    never CONFIRMED on one half alone)."""
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["verdict"] == "CONFIRMED_LOCAL"]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) == 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": "%s__combined" % base_hyp, "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "split-half-by-date, both halves required: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def _platoon_delta_by_hand(pa: pd.DataFrame, min_pa: int = 20) -> pd.Series:
    d = pa.dropna(subset=["events", "p_throws", "batter"]).copy()
    d = d[d["p_throws"].isin(["L", "R"])]
    d["on_base"] = d["events"].isin(ON_BASE_EVENTS)
    cnt = d.groupby(["batter", "p_throws"]).size().unstack("p_throws")
    if "L" not in cnt.columns or "R" not in cnt.columns:
        return pd.Series(dtype=float)  # this half has no batter with PAs vs both hands
    cnt = cnt.fillna(0)
    ok = cnt[(cnt["L"] >= min_pa) & (cnt["R"] >= min_pa)].index
    dd = d[d["batter"].isin(ok)]
    if dd.empty:
        return pd.Series(dtype=float)  # no batter cleared the min_pa/hand floor
    rate = dd.groupby(["batter", "p_throws"])["on_base"].mean().unstack("p_throws")
    return (rate["L"] - rate["R"]).dropna()


def platoon_split_persistence(pa: pd.DataFrame) -> Dict[str, Any]:
    """#48: split-half-by-date pearson r of per-batter platoon_delta
    (on-base rate vs LHP minus vs RHP), re-derived from savant_full__2025
    per the row's own premise fix (platoon_split_index.parquet is a single
    combined 2022_2023 window, not split-half testable as-is)."""
    hyp = "platoon_split_persistence"
    gd = pd.to_datetime(pa["game_date"])
    mid = gd.median()
    d1 = _platoon_delta_by_hand(pa[gd <= mid])
    d2 = _platoon_delta_by_hand(pa[gd > mid])
    common = d1.index.intersection(d2.index)
    if len(common) < 15:
        return {"hypothesis": hyp, "n": int(len(common)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 15 batters with >=20 PA/hand in both halves"}
    r, p = stats.pearsonr(d1.loc[common], d2.loc[common])
    eff = float(r)
    return {"hypothesis": hyp, "n": int(len(common)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, hyp),
            "note": "split-half pearson r, per-batter platoon_delta (on-base-rate vs L minus vs R), "
                    "n=%d batters (>=20 PA/hand/half)" % len(common)}


def run() -> List[Dict[str, Any]]:
    s23, s24, s25 = load_season(2023), load_season(2024), load_season(2025)
    rows: List[Dict[str, Any]] = [catcher_framing_multiseason_trend(s23, s24, s25)]
    del s23, s24

    pa25 = pa_final_pitch(s25)
    gd = pd.to_datetime(pa25["game_date"])
    mid = gd.median()
    halves = [tto_x_platoon_interaction(pa25[gd <= mid], "h1"), tto_x_platoon_interaction(pa25[gd > mid], "h2")]
    rows.extend(halves)
    rows.append(_combine("tto_x_platoon_interaction", halves))
    rows.append(platoon_split_persistence(pa25))

    for r in rows:
        r["sport"] = "mlb"
        r.setdefault("corpus", "savant_full__2025")
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-42s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict rule + trip_number/same_hand derivation
    + platoon_delta computation on synthetic frames -- no parquet needed."""
    assert _verdict(0.001, 0.02, "catcher_framing_multiseason_trend") == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.02, "catcher_framing_multiseason_trend") == "NULL_LOCAL"
    assert _verdict(0.001, 0.005, "catcher_framing_multiseason_trend") == "NULL_LOCAL"  # below 0.01 bar
    assert _verdict(None, 0.1, "platoon_split_persistence") == "NOT_TESTABLE"

    fake_pa = pd.DataFrame({
        "game_pk": [1, 1, 1, 1], "pitcher": [10, 10, 10, 10], "batter": [20, 20, 20, 20],
        "at_bat_number": [1, 2, 3, 4], "stand": ["R", "R", "R", "R"], "p_throws": ["R", "R", "R", "R"],
        "estimated_woba_using_speedangle": [0.3, 0.3, 0.3, 0.3],
    })
    r = tto_x_platoon_interaction(fake_pa, "h1")
    assert r["n"] == 4 and r["verdict"] == "NOT_TESTABLE"  # n<50 floor, expected on this tiny frame

    fake_platoon = pd.DataFrame({
        "batter": [1] * 30 + [2] * 30, "p_throws": (["L"] * 15 + ["R"] * 15) * 2,
        "events": (["walk"] * 6 + ["field_out"] * 9) * 4,
        "game_date": pd.to_datetime("2025-04-01"),
    })
    d = _platoon_delta_by_hand(fake_platoon, min_pa=15)
    assert set(d.index) == {1, 2}
    print("self-check OK")
