"""domains.tennis.knowledge.validate_research_wave3 -- research-wave-3
UNTESTED rows #37 (post-break game-level hold-rate momentum) and #38
(new-ball-cycle serve execution) from domains/tennis/knowledge/mechanisms.md,
against the same `slam_points.parquet` corpus #16/#35 already use. Mirrors
domains/soccer/knowledge/validate_research_wave3.py's run/run_split_half
shape (same wave, same even/odd split-half requirement in both rows' own
test-spec text).

Premise-check (this session, fresh reads): slam_points.parquet confirmed
columns match_id/set_no/game_no/point_number/point_server/point_winner/
p1_games_won/p2_games_won/p1_ace/p2_ace/speed_kmh (543,772 rows, same
corpus as #16/#35); speed_kmh 99.9% non-null; `game_no` resets to 1 at the
start of each new set (confirmed by direct inspection -- a per-match
CUMULATIVE game index must be derived, not read off `game_no` directly).
`point_server`==0 is a sentinel confined EXCLUSIVELY to (set_no=1,game_no=1)
first rows (1,554 of 85,220 game groups) -- treated as unresolved, not a
real server value; harmless for both rows since no break can precede a
match's own first game.

Winner-of-a-game derivation: a game's own last point's `p1_games_won`/
`p2_games_won` already reflects THAT game's own outcome (verified this
session on several matches: the score increments on the game's own last row,
resetting to 0 at each new set) -- delta vs the previous game_no's own
last-row state WITHIN THE SAME SET (baseline (0,0) for game_no==1) isolates
exactly one game's winner; a delta that isn't a clean (+1,0)/(0,+1) is left
unresolved (dropped), matching #35's own resolve-or-drop philosophy rather
than mis-attributing an ambiguous game.

Leak audit: both rows are same-match structural reads (game order/serve
sequence within one already-played match), no cross-match or as-of forecast
ingredient -- same leak posture as #35 (structural, contemporaneous).

Run: python -m domains.tennis.knowledge.validate_research_wave3
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.tennis.knowledge._data import LEDGER_PATH, load_slam_points
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_BREAKS = 200          # declared floor, this validator (mirrors wave2's MIN_TB pattern)
MIN_BUCKET = 200          # declared floor, mechanisms.md #38's "same bar family as #34/#36"
MIN_EFFECT_37 = 0.03      # declared bar, mechanisms.md #37: |eff|>=0.03 rate points
MIN_EFFECT_ACE = 0.01     # declared bar, mechanisms.md #38: |eff|>=0.01 ace-rate points
MIN_EFFECT_SPEED = 1.0    # declared bar, mechanisms.md #38: |eff|>=1.0 km/h


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or (isinstance(p, float) and p != p):  # NaN-safe
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _game_level_frame(sp: pd.DataFrame) -> pd.DataFrame:
    """One row per (match_id, set_no, game_no): cumulative in-match game
    `seq` (1-based, chronological across sets), `server` (1/2 or NaN if the
    sentinel-0 first point), `winner` (1/2 or NaN if unresolved), `hold`
    (winner == server, or NaN)."""
    sub = sp.sort_values(["match_id", "set_no", "game_no", "point_number"])[
        ["match_id", "set_no", "game_no", "point_server", "p1_games_won", "p2_games_won"]]
    grp = sub.groupby(["match_id", "set_no", "game_no"], sort=False)
    first_df = grp["point_server"].first().rename("server_raw").reset_index()
    last_df = grp[["p1_games_won", "p2_games_won"]].last().reset_index()
    g = first_df.merge(last_df, on=["match_id", "set_no", "game_no"])
    g = g.sort_values(["match_id", "set_no", "game_no"]).reset_index(drop=True)
    g["seq"] = g.groupby("match_id").cumcount() + 1
    prev_p1 = g.groupby(["match_id", "set_no"])["p1_games_won"].shift(1).fillna(0)
    prev_p2 = g.groupby(["match_id", "set_no"])["p2_games_won"].shift(1).fillna(0)
    d1 = g["p1_games_won"] - prev_p1
    d2 = g["p2_games_won"] - prev_p2
    winner = pd.Series(np.nan, index=g.index)
    winner[(d1 == 1) & (d2 == 0)] = 1.0
    winner[(d1 == 0) & (d2 == 1)] = 2.0
    g["winner"] = winner
    g["server"] = g["server_raw"].where(g["server_raw"].isin([1, 2])).astype(float)
    g["hold"] = np.where(g["server"].notna() & g["winner"].notna(), g["winner"] == g["server"], np.nan)
    return g


def _break_pairs(g: pd.DataFrame) -> pd.DataFrame:
    """mechanisms.md #37: for each resolvable break (winner != server), the
    breaker's very next in-match game (seq+1) as the paired treatment
    observation, vs that breaker's own baseline hold rate over their OTHER
    service games in this match (excludes the treatment game itself)."""
    g = g.sort_values(["match_id", "seq"])
    next_winner = g.groupby("match_id")["winner"].shift(-1)
    next_server = g.groupby("match_id")["server"].shift(-1)
    resolvable = g["server"].notna() & g["winner"].notna()
    is_break = resolvable & (g["winner"] != g["server"])
    cand = g.loc[is_break & next_winner.notna() & next_server.notna()].copy()
    cand["breaker"] = cand["winner"]
    cand["next_winner"] = next_winner.loc[cand.index]
    cand["next_server"] = next_server.loc[cand.index]
    cand = cand[cand["next_server"] == cand["breaker"]]  # alternation sanity check
    cand["treatment"] = (cand["next_winner"] == cand["breaker"]).astype(float)

    svc = g.loc[resolvable].groupby(["match_id", "server"])["hold"].agg(
        total_hold="sum", total_n="count").reset_index()
    cand = cand.merge(svc, left_on=["match_id", "breaker"], right_on=["match_id", "server"],
                       how="left", suffixes=("", "_svc"))
    cand["base_n"] = cand["total_n"] - 1
    cand = cand[cand["base_n"] >= 1]
    cand["baseline"] = (cand["total_hold"] - cand["treatment"]) / cand["base_n"]
    return cand[["treatment", "baseline"]]


def post_break_hold_rate(g: pd.DataFrame, hyp: str = "post_break_hold_rate") -> Dict[str, Any]:
    pairs = _break_pairs(g)
    n = len(pairs)
    if n < MIN_BREAKS:
        return {"hypothesis": hyp, "n": n, "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than %d resolvable paired break events" % MIN_BREAKS}
    t, p = stats.ttest_rel(pairs["treatment"], pairs["baseline"])
    eff = float((pairs["treatment"] - pairs["baseline"]).mean())
    return {"hypothesis": hyp, "n": n, "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, MIN_EFFECT_37),
            "note": "post-break next-service-game hold %.4f vs own baseline %.4f (n=%d breaks), "
                    "paired t=%.3f" % (pairs["treatment"].mean(), pairs["baseline"].mean(), n, t)}


def _ball_cycle_tag(seq: np.ndarray) -> np.ndarray:
    """Standard tour rule: first ball change after game 7, then every 9
    games (segment starts at cumulative game 1, 8, 17, 26, ...). 'fresh' =
    first 2 games of a segment; 'worn' = last 2 games of a segment; else ''."""
    seq = np.asarray(seq, dtype=np.int64)
    tag = np.full(seq.shape, "", dtype=object)
    first_len, cycle_len = 7, 9
    in_first = seq <= first_len
    tag[in_first & (seq <= 2)] = "fresh"
    tag[in_first & (seq >= first_len - 1)] = "worn"
    later = ~in_first
    pos = ((seq[later] - first_len - 1) % cycle_len) + 1
    tag_later = np.full(pos.shape, "", dtype=object)
    tag_later[pos <= 2] = "fresh"
    tag_later[pos >= cycle_len - 1] = "worn"
    tag[later] = tag_later
    return tag


def point_ball_cycle_frame(sp: pd.DataFrame, g: pd.DataFrame) -> pd.DataFrame:
    """mechanisms.md #38: point rows joined to their game's cumulative `seq`,
    restricted to resolvable servers, tagged fresh/worn by ball-cycle
    position; `server_ace` = the CURRENT server's own ace flag."""
    seq_map = g[["match_id", "set_no", "game_no", "seq"]]
    pts = sp.merge(seq_map, on=["match_id", "set_no", "game_no"], how="inner")
    pts = pts[pts["point_server"].isin([1, 2])].copy()
    pts["server_ace"] = pts["p1_ace"].where(pts["point_server"] == 1, pts["p2_ace"])
    pts["tag"] = _ball_cycle_tag(pts["seq"].to_numpy())
    return pts


def _bucket_test(pts: pd.DataFrame, col: str, hyp: str, min_abs_effect: float, unit: str) -> Dict[str, Any]:
    fresh = pts.loc[pts["tag"] == "fresh", col].dropna().astype(float)
    worn = pts.loc[pts["tag"] == "worn", col].dropna().astype(float)
    if len(fresh) < MIN_BUCKET or len(worn) < MIN_BUCKET:
        return {"hypothesis": hyp, "n": int(len(fresh) + len(worn)), "effect": None, "p": None,
                "verdict": "NOT_TESTABLE",
                "note": "fewer than %d points in fresh (n=%d) or worn (n=%d) ball-cycle bucket" % (
                    MIN_BUCKET, len(fresh), len(worn))}
    t, p = stats.ttest_ind(fresh, worn, equal_var=False)
    eff = float(fresh.mean() - worn.mean())
    return {"hypothesis": hyp, "n": int(len(fresh) + len(worn)), "effect": round(eff, 4), "p": float(p),
            "verdict": _verdict(p, eff, min_abs_effect),
            "note": "%s fresh(games1-2 post-change) %.4f%s (n=%d) vs worn(pre-change) %.4f%s (n=%d), "
                    "Welch t=%.3f" % (col, fresh.mean(), unit, len(fresh), worn.mean(), unit, len(worn), t)}


def ball_cycle_ace_rate(pts: pd.DataFrame, suffix: str = "") -> Dict[str, Any]:
    return _bucket_test(pts, "server_ace", "ball_cycle_ace_rate" + suffix, MIN_EFFECT_ACE, "")


def ball_cycle_serve_speed(pts: pd.DataFrame, suffix: str = "") -> Dict[str, Any]:
    return _bucket_test(pts, "speed_kmh", "ball_cycle_serve_speed_kmh" + suffix, MIN_EFFECT_SPEED, "km/h")


def _stamp_and_write(rows: List[Dict[str, Any]], corpus: str) -> List[Dict[str, Any]]:
    for r in rows:
        r["sport"] = "tennis"
        r["corpus"] = corpus
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def run() -> List[Dict[str, Any]]:
    sp = load_slam_points()
    g = _game_level_frame(sp)
    pts = point_ball_cycle_frame(sp, g)
    rows = [post_break_hold_rate(g), ball_cycle_ace_rate(pts), ball_cycle_serve_speed(pts)]
    return _stamp_and_write(rows, "slam_points")


def run_split_half() -> List[Dict[str, Any]]:
    """Even/odd match-index split -- the >=2-independent-groups evidence the
    honesty bar requires behind an affirmative (CONFIRMED_LOCAL) verdict,
    per both rows' own declared test-spec text."""
    sp = load_slam_points()
    g = _game_level_frame(sp)
    match_ids = g["match_id"].drop_duplicates().reset_index(drop=True)
    half_of = pd.Series((match_ids.index % 2 == 0), index=match_ids.values)  # True="A", False="B"
    g_half = g["match_id"].map(half_of)

    rows: List[Dict[str, Any]] = []
    for half, is_a in (("A", True), ("B", False)):
        gh = g[g_half == is_a]
        pts_h = point_ball_cycle_frame(sp, gh)
        rows.append(post_break_hold_rate(gh, "post_break_hold_rate__split_%s" % half))
        rows.append(ball_cycle_ace_rate(pts_h, "__split_%s" % half))
        rows.append(ball_cycle_serve_speed(pts_h, "__split_%s" % half))
    return _stamp_and_write(rows, "slam_points__split_half")


def main() -> int:
    for r in run() + run_split_half():
        print("%-38s %-14s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    tag = _ball_cycle_tag(np.array([1, 2, 6, 7, 8, 9, 16, 17]))
    assert list(tag) == ["fresh", "fresh", "worn", "worn", "fresh", "fresh", "worn", "fresh"]
    print("self-check OK")
