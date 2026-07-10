"""domains.tennis.knowledge.validate_research_wave2 -- 2 UNTESTED mechanisms
from the 2026-07-10 research-wave-2 seed (mechanisms.md #35 tiebreak
serve-order, #36 within-tournament rest gap).

Premise-check (this session, fresh reads): slam_points.parquet confirmed
columns match_id/set_no/game_no/point_number/point_server/p1_games_won/
p2_games_won (543,772 rows) -- matches #35's artifact-link exactly.
matches.parquet (ATP, 30,616 rows) + wta_matches.parquet both carry
tourney_id/p1_id/p2_id/date/event_id -- matches #36's premise-check note
(schedule_density.parquet's rest_days IS global, no tourney_id column,
confirmed) and its test spec's own "ATP+WTA 2015-2025" scope.

#35 winner-derivation correction: the row's own spec says the winning side's
games_won "increments at the NEXT game_no after the TB game" -- true for
only ~46% of TB games sampled this session (the other ~54% already show the
7-6/6-7 increment on the LAST point of the TB's OWN game_no group, before
any next-game row exists). `_tb_winner` below checks BOTH: the TB game's own
last row first, then falls back to the next game_no's first row, so no TB
with a resolvable increment is dropped for a derivation-ordering reason
alone (unresolved cases -- e.g. TB is the final game_no of the match's last
set with no next-game and no same-row increment recorded -- are dropped as
genuinely unresolvable, not miscounted).

Leak audit: #35 is a same-match structural read (who serves the TB's first
point vs who wins it), no as-of/predictive feature involved -- same
raw-rate framing as the cited literature. #36 uses only PRIOR-match dates
within the same tourney_id (a real as-of quantity: the gap since that
player's OWN previous match in this event) joined to the CURRENT match's
realized stats -- same leak posture as #13/#34's asof-vs-realized pattern.

#36 premise correction (fresh read this session): the row's test spec
assumes `matches.parquet`'s `date` column is per-match. It is NOT -- it is
the TOURNAMENT START date, constant across every round of a given
tourney_id (2321/2322 tourney_ids have exactly 1 distinct date value across
all their rows). A "diff of consecutive match dates within tourney_id" is
therefore always 0 and the row's literal derivation is NOT_TESTABLE on this
corpus, not merely underpowered -- see `_rest_gap_test`'s note. `round`
(R32/R16/.../F) exists as a coarser round-ordinal but is a different metric
than the day-level physiological-fatigue gap the row's causal story
specifies, so it is not substituted in as a stand-in.

Run: python -m domains.tennis.knowledge.validate_research_wave2
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, TENNIS_DIR, load_matches, load_slam_points
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_TB = 30              # declared floor, mechanisms.md #35: >=30 TBs for a first pass
MIN_BUCKET = 200         # declared floor, mechanisms.md #36: min n floor 200/bucket
MIN_ABS_EFFECT_36 = 0.01  # declared bar, mechanisms.md #36: |eff|>=0.01 rate points


def load_match_stats() -> pd.DataFrame:
    """event_id -> p1/p2 serve stats. Not added to _data.py -- same reasoning
    as validate_research_wave1.py's local loader."""
    return pd.read_parquet(TENNIS_DIR / "match_stats.parquet")


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _tb_winner(group: pd.DataFrame, next_first_row: "pd.Series | None") -> "int | None":
    """1 or 2 (winner of the tiebreak), or None if unresolvable. `group` is
    one (match_id, set_no, game_no) TB's rows, already sorted by
    point_number. See module docstring for the two-path derivation."""
    last = group.iloc[-1]
    if last["p1_games_won"] == 7:
        return 1
    if last["p2_games_won"] == 7:
        return 2
    if next_first_row is not None:
        if next_first_row["p1_games_won"] == 7:
            return 1
        if next_first_row["p2_games_won"] == 7:
            return 2
    return None


def tiebreak_serve_order_win_rate(sp: pd.DataFrame) -> Dict[str, Any]:
    """mechanisms.md #35: raw P(first-server wins the TB) vs 0.5."""
    sp = sp.sort_values(["match_id", "set_no", "game_no", "point_number"])
    tb_mask = (sp["p1_games_won"] == 6) & (sp["p2_games_won"] == 6)
    tb_keys = sp.loc[tb_mask, ["match_id", "set_no", "game_no"]].drop_duplicates()
    by_group = {k: g for k, g in sp.groupby(["match_id", "set_no", "game_no"])}
    results = []
    for _, key in tb_keys.iterrows():
        gkey = (key["match_id"], key["set_no"], key["game_no"])
        group = by_group.get(gkey)
        if group is None or len(group) == 0:
            continue
        first_server = int(group.iloc[0]["point_server"])
        next_key = (key["match_id"], key["set_no"], key["game_no"] + 1)
        next_group = by_group.get(next_key)
        next_first_row = next_group.iloc[0] if next_group is not None and len(next_group) else None
        winner = _tb_winner(group, next_first_row)
        if winner is None:
            continue
        results.append(int(winner == first_server))
    n = len(results)
    if n < MIN_TB:
        return {"hypothesis": "tiebreak_serve_order_win_rate", "n": n, "effect": None, "p": None,
                "verdict": "NOT_TESTABLE", "note": "fewer than %d resolvable tiebreaks" % MIN_TB}
    arr = np.array(results, dtype=float)
    rate = float(arr.mean())
    t, p = stats.ttest_1samp(arr, 0.5)
    eff = rate - 0.5
    return {"hypothesis": "tiebreak_serve_order_win_rate", "n": n, "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, 0.0),  # any significant deviation from 0.5 is the finding, per row's spec
            "note": "first-server won %.4f (n=%d) of resolvable tiebreaks, one-sample t-test vs 0.5 "
                    "(t=%.3f, p=%.3g); literature reference ~0.497" % (rate, n, t, p)}


def _long_player_frame(matches: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    """One row per (event_id, player_id): tourney_id, date, ace_rate,
    1st_in_pct -- long format, mirrors validate_research_wave1.py's
    p1/p2 -> long concat pattern."""
    d = matches.dropna(subset=["tourney_id", "date", "p1_id", "p2_id"]).merge(
        stats_df, on="event_id", how="inner")
    d["date"] = pd.to_datetime(d["date"])
    l1 = d[["event_id", "tourney_id", "date", "p1_id", "p1_ace_rate", "p1_1st_in_pct"]].rename(
        columns={"p1_id": "player_id", "p1_ace_rate": "ace_rate", "p1_1st_in_pct": "first_in_pct"})
    l2 = d[["event_id", "tourney_id", "date", "p2_id", "p2_ace_rate", "p2_1st_in_pct"]].rename(
        columns={"p2_id": "player_id", "p2_ace_rate": "ace_rate", "p2_1st_in_pct": "first_in_pct"})
    long = pd.concat([l1, l2], ignore_index=True).dropna(subset=["player_id", "ace_rate", "first_in_pct"])
    long = long.sort_values(["player_id", "tourney_id", "date"])
    prev_date = long.groupby(["player_id", "tourney_id"])["date"].shift(1)
    long["same_tourney_rest_days"] = (long["date"] - prev_date).dt.days
    return long.dropna(subset=["same_tourney_rest_days"])


def _rest_gap_test(long: pd.DataFrame, col: str, hyp: str) -> Dict[str, Any]:
    short = long.loc[long["same_tourney_rest_days"] <= 1, col]
    longer = long.loc[long["same_tourney_rest_days"] >= 2, col]
    if long["same_tourney_rest_days"].nunique(dropna=True) <= 1:
        return {"hypothesis": hyp, "n": int(len(long)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "premise failure, not underpowered: matches.parquet's date column is the TOURNAMENT "
                        "START date (verified this session: 2321/2322 tourney_ids have exactly 1 distinct "
                        "date across ALL rounds), not a per-match date -- so a consecutive-date diff within "
                        "tourney_id is always 0 (%d/%d rows), and the row's literal test spec (diff of "
                        "consecutive match dates) cannot be derived from this corpus; `round` (R32/QF/SF/F "
                        "etc) exists but is a different, coarser ordinal, not the day-gap the row's causal "
                        "story specifies -- not substituted here" % (len(short), len(long))}
    if len(short) < MIN_BUCKET or len(longer) < MIN_BUCKET:
        return {"hypothesis": hyp, "n": int(len(long)), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d rows in short (<=1d, n=%d) or long (>=2d, n=%d) within-tourney "
                        "rest-gap bucket" % (MIN_BUCKET, len(short), len(longer))}
    t, p = stats.ttest_ind(short, longer, equal_var=False)
    eff = float(short.mean() - longer.mean())
    return {"hypothesis": hyp, "n": int(len(short) + len(longer)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, MIN_ABS_EFFECT_36),
            "note": "%s short within-tourney gap (<=1d) %.4f (n=%d) vs longer (>=2d) %.4f (n=%d), "
                    "Welch t=%.3f" % (col, short.mean(), len(short), longer.mean(), len(longer), t)}


def within_tournament_rest_gap_ace_rate(matches: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    long = _long_player_frame(matches, stats_df)
    return _rest_gap_test(long, "ace_rate", "within_tournament_rest_gap_ace_rate")


def within_tournament_rest_gap_first_serve(matches: pd.DataFrame, stats_df: pd.DataFrame) -> Dict[str, Any]:
    long = _long_player_frame(matches, stats_df)
    return _rest_gap_test(long, "first_in_pct", "within_tournament_rest_gap_first_serve")


def run() -> List[Dict[str, Any]]:
    sp = load_slam_points()
    matches = load_matches()
    stats_df = load_match_stats()
    rows = [
        tiebreak_serve_order_win_rate(sp),
        within_tournament_rest_gap_ace_rate(matches, stats_df),
        within_tournament_rest_gap_first_serve(matches, stats_df),
    ]
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = "slam_points" if r["hypothesis"].startswith("tiebreak") else "matches_match_stats_atp_wta"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-40s %-14s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    g = pd.DataFrame({"p1_games_won": [6, 6, 7], "p2_games_won": [6, 6, 6]})
    assert _tb_winner(g, None) == 1
    g2 = pd.DataFrame({"p1_games_won": [6, 6, 6], "p2_games_won": [6, 6, 6]})
    nxt = pd.Series({"p1_games_won": 6, "p2_games_won": 7})
    assert _tb_winner(g2, nxt) == 2
    assert _tb_winner(g2, None) is None
    print("self-check OK")
