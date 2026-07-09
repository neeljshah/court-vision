"""domains.tennis.point_engine.corpus -- canonical POINT-level state frame from
the Sackmann Grand Slam point-by-point corpus (data/cache/sackmann_pbp/slam_points.parquet,
already ingested read-only by sackmann_pbp_ingest.py -- this module never re-parses
raw CSVs for points, only re-reads matches.csv for player NAME identity).

ATOMIC UNIT (declared): one served POINT. Real point-by-point sequences (not a
scoreline proxy) -- confirmed columns point_number/point_server/point_winner give
the actual rally-by-rally outcome for 2011-2015 across all 4 majors, singles only.

WALK-FORWARD SPLIT: FIT_YEARS = 2011-2013 (all 4 slams), TEST_YEAR = 2014 (all 4
slams). 2015 (ausopen only) is left untouched -- future-season leak avoided by
construction (year is fixed at ingest, never derived from same-match data).

SCORE STATE (leak-free, PRE-point): p1_score/p2_score in slam_points are POST-point
scores; the state used to predict a point is the PRIOR point's post-score in the
same (match,set,game) -- computed via a groupby+shift, first point of a game seeded
0-0. Canonical bucket collapses (server_pts, returner_pts) with the game-ending AD/
deuce region into 19 cells (see score_bucket()).

DATA LANDMINE (declared, found by direct file inspection): matches.csv `status`,
`winner`, `event_name`, `player1id`/`player2id` are populated for 2011 ONLY --
every 2012-2015 file has them entirely NaN (upstream schema drift). Only
`player1`/`player2` (name strings) survive across all years, so player identity
uses NAMES, not ids. Match winner and total games are therefore derived directly
from the real point sequence (last point of each game decides the game; games
aggregate to sets; sets decide the match) rather than trusted from matches.csv.
`best_of` is inferred empirically (5 if the match reached a 4th+ set, else 3) --
this undercounts straight-set bo5 wins as bo3; a declared v1 simplification.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_corpus.py -q
"""
from __future__ import annotations

import glob
from pathlib import Path
from typing import Tuple

import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
SLAM_POINTS = _REPO / "data" / "cache" / "sackmann_pbp" / "slam_points.parquet"
RAW_DIR = (_REPO / "data" / "domains" / "tennis" / "_raw" / "sackmann_pbp_repos"
           / "tennis_slam_pointbypoint")
FIT_YEARS = (2011, 2012, 2013)
TEST_YEAR = 2014

SCORE_MAP = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4}
N_SCORE_BUCKETS = 19   # 0..15 normal (s,r in 0..3), 16=deuce, 17=ad_server, 18=ad_returner
N_SET_BUCKETS = 3      # set 1, set 2, set >=3


def score_bucket(server_pts: int, returner_pts: int) -> int:
    """Collapse (server_pts, returner_pts), each 0..4 (4=='AD'), to one of 19 cells."""
    if server_pts == 4:
        return 17
    if returner_pts == 4:
        return 18
    if server_pts == 3 and returner_pts == 3:
        return 16
    return server_pts * 4 + returner_pts


def set_bucket(set_no: int) -> int:
    return min(int(set_no) - 1, N_SET_BUCKETS - 1)


def _load_matches_meta() -> pd.DataFrame:
    """player1/player2 NAME strings per match_id (the only identity columns
    populated across ALL years -- see module docstring landmine note)."""
    frames = []
    for p in sorted(glob.glob(str(RAW_DIR / "*-matches.csv"))):
        m = pd.read_csv(p, dtype=str)
        frames.append(m[["match_id", "player1", "player2"]])
    meta = pd.concat(frames, ignore_index=True).drop_duplicates(subset="match_id")
    return meta.dropna(subset=["player1", "player2"]).set_index("match_id")


def _prep_points(years: Tuple[int, ...], meta_index: pd.Index) -> pd.DataFrame:
    pts = pd.read_parquet(SLAM_POINTS)
    pts = pts[pts["year"].isin(years) & (pts["point_number"] >= 1)].copy()
    pts = pts.dropna(subset=["set_no", "game_no", "point_server", "point_winner"]).copy()
    pts = pts[pts["match_id"].isin(meta_index)].copy()
    return pts.sort_values(["match_id", "set_no", "game_no", "point_number"])


def build_point_frame(years: Tuple[int, ...]) -> pd.DataFrame:
    """Canonical point frame for the given years: one row per REAL played point,
    server_id/returner_id (player NAME strings), score_bucket (pre-point),
    set_bucket, server_won (0/1)."""
    meta = _load_matches_meta()
    pts = _prep_points(years, meta.index)

    def _num(s: pd.Series) -> pd.Series:
        return s.map(SCORE_MAP).fillna(0).astype(int)

    p1_post, p2_post = _num(pts["p1_score"]), _num(pts["p2_score"])
    key = [pts["match_id"], pts["set_no"], pts["game_no"]]
    p1_prior = p1_post.groupby(key).shift(1).fillna(0).astype(int)
    p2_prior = p2_post.groupby(key).shift(1).fillna(0).astype(int)

    server_is_p1 = pts["point_server"] == 1
    server_prior = p1_prior.where(server_is_p1, p2_prior)
    returner_prior = p2_prior.where(server_is_p1, p1_prior)

    m1 = pts["match_id"].map(meta["player1"])
    m2 = pts["match_id"].map(meta["player2"])
    out = pd.DataFrame({
        "match_id": pts["match_id"].to_numpy(),
        "year": pts["year"].to_numpy(),
        "tourney": pts["tourney"].to_numpy(),
        "set_no": pts["set_no"].astype(int).to_numpy(),
        "server_id": m1.where(server_is_p1, m2).to_numpy(),
        "returner_id": m2.where(server_is_p1, m1).to_numpy(),
        "score_bucket": [score_bucket(int(s), int(r))
                         for s, r in zip(server_prior, returner_prior)],
        "set_bucket": [set_bucket(s) for s in pts["set_no"]],
        "server_won": (pts["point_winner"] == pts["point_server"]).astype(int).to_numpy(),
    })
    return out.dropna(subset=["server_id", "returner_id"])


def _game_winner_p1(g: pd.DataFrame) -> bool:
    """True if player1 won this game -- decided by who won the LAST recorded
    point of the (set_no, game_no) group (real data, no fabrication)."""
    last = g.sort_values("point_number").iloc[-1]
    return int(last["point_winner"]) == 1


def build_match_frame(years: Tuple[int, ...]) -> pd.DataFrame:
    """One row per usable match: winner_id, best_of (empirically inferred),
    total_games (n distinct (set_no,game_no) actually played -- real, possibly
    retirement-shortened), first_server_id (server at point 1). Winner and set
    scores are derived from the real point sequence, not from the broken
    matches.csv winner/status columns (see module docstring)."""
    meta = _load_matches_meta()
    pts = _prep_points(years, meta.index)

    rows = []
    for mid, g in pts.groupby("match_id"):
        row = meta.loc[mid]
        first = g[g["point_number"] == 1]
        if first.empty:
            continue
        fs = int(first["point_server"].iloc[0])
        if fs not in (1, 2):
            continue
        sets_p1 = sets_p2 = 0
        for (_set_no), sg in g.groupby("set_no"):
            games_p1 = sum(_game_winner_p1(gg) for _, gg in sg.groupby("game_no"))
            games_p2 = sg["game_no"].nunique() - games_p1
            if games_p1 > games_p2:
                sets_p1 += 1
            elif games_p2 > games_p1:
                sets_p2 += 1
        if sets_p1 == sets_p2:
            continue   # no unambiguous winner (unfinished/corrupt); drop
        n_sets = sets_p1 + sets_p2
        best_of = 5 if n_sets > 3 else 3
        total_games = g.drop_duplicates(subset=["set_no", "game_no"]).shape[0]
        winner_id = row["player1"] if sets_p1 > sets_p2 else row["player2"]
        first_server_id = row["player1"] if fs == 1 else row["player2"]
        rows.append({
            "match_id": mid, "year": int(g["year"].iloc[0]), "best_of": best_of,
            "player1id": row["player1"], "player2id": row["player2"],
            "winner_id": winner_id, "first_server_id": first_server_id,
            "total_games": int(total_games),
        })
    return pd.DataFrame(rows)


__all__ = ["SLAM_POINTS", "RAW_DIR", "FIT_YEARS", "TEST_YEAR", "SCORE_MAP",
           "N_SCORE_BUCKETS", "N_SET_BUCKETS", "score_bucket", "set_bucket",
           "build_point_frame", "build_match_frame"]
