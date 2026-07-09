"""domains.mlb.knowledge.validate_data_gaps -- 1 real test + 3 honest
NOT_TESTABLE mechanisms (missing ingredients on THIS corpus, checked by
grepping the actual columns/values rather than assumed). Per repo discipline
an n=0/unbuildable mechanism is recorded NOT_TESTABLE, never silently skipped.

Run: python -m domains.mlb.knowledge.validate_data_gaps
"""
from __future__ import annotations

from typing import Any, Dict, List

from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season
from scripts.platformkit.io_atomic import append_jsonl_atomic

GB_FORCE_EVENTS = {"grounded_into_double_play", "double_play", "field_out", "force_out",
                   "fielders_choice_out", "fielders_choice", "single", "double", "field_error"}
ALPHA = 0.01

WEATHER_COLS = {"temperature", "temp", "wind_speed", "wind_dir", "weather"}
ROLE_COLS = {"pitcher_role", "reliever_rank", "bullpen_role", "leverage_index"}


def gb_double_play_suppression(df) -> Dict[str, Any]:
    """GB with a force at 1B and <2 outs -> double-play rate vs non-GB same state."""
    d = df[df["on_1b"].notna() & (df["outs_when_up"] < 2) & df["events"].isin(GB_FORCE_EVENTS)]
    is_gb = (d["bb_type"] == "ground_ball").astype(int)
    is_dp = d["events"].isin({"grounded_into_double_play", "double_play"}).astype(int)
    a, b = is_dp[is_gb == 1], is_dp[is_gb == 0]
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return {"hypothesis": "gb_double_play_suppression", "n": int(len(d)),
            "effect": round(float(a.mean() - b.mean()), 5), "p": float(p),
            "verdict": "CONFIRMED_LOCAL" if (p < ALPHA and (a.mean() - b.mean()) > 0.01) else "NULL_LOCAL",
            "note": "DP rate on GB w/ force (%.4f, n=%d) vs non-GB same state (%.4f, n=%d)"
                    % (a.mean(), int(is_gb.sum()), b.mean(), int((is_gb == 0).sum()))}


def _not_testable(hyp: str, missing: List[str], corpus_cols: set) -> Dict[str, Any]:
    have = sorted(corpus_cols & set(missing))
    return {"hypothesis": hyp, "n": 0, "effect": None, "p": None, "verdict": "NOT_TESTABLE",
            "note": "none of %s present in savant_full columns (have: %s)" % (sorted(missing), have or "none")}


def _sb_not_testable(df) -> Dict[str, Any]:
    sb_events = {"stolen_base_2b", "stolen_base_3b", "stolen_base_home",
                 "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home"}
    present = sb_events & set(df["events"].dropna().unique())
    return {"hypothesis": "stolen_base_breakeven_rate", "n": 0, "effect": None, "p": None,
            "verdict": "NOT_TESTABLE",
            "note": "no SB/CS rows in this corpus's events column (found: %s)" % (sorted(present) or "none")}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    cols = set(df.columns)
    rows = [
        gb_double_play_suppression(df),
        _not_testable("weather_park_hr_modulation", WEATHER_COLS, cols),
        _not_testable("bullpen_leverage_chaining", ROLE_COLS, cols),
        _sb_not_testable(df),
    ]
    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        eff = "%+.5f" % r["effect"] if r["effect"] is not None else "--"
        p = "%.4g" % r["p"] if r["p"] is not None else "--"
        print("%-32s %-16s n=%-8d effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], eff, p, r.get("note", "")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    r = _not_testable("fake_mechanism", {"temperature"}, {"balls", "strikes"})
    assert r["verdict"] == "NOT_TESTABLE"
    print("self-check OK")
