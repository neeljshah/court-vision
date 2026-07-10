"""domains.tennis.point_engine.corpus_2026 -- 2026 MCP charted-match POINT and
MATCH frames, same column contract as corpus.py's build_point_frame/
build_match_frame (server_id/score_bucket/set_bucket/server_won for points;
match_id/player1id/player2id/best_of/first_server_id/winner_id/total_games for
matches) -- so validate.py's existing _panel_point_logloss/_panel_match are
reused UNCHANGED against this out-of-sample 2026 population (see validate_2026.py).

SOURCE: data/domains/tennis/mcp_2026/{points,matches}.parquet, already ingested
(yesterday's session). population column on every row reads
"mcp_charted_nonrepresentative" -- MatchChartingProject's charted sample is a
volunteer-selected subset of high-profile matches, NOT a random sample of the
tour. Every doc built from this module must carry that caveat forward.

Unlike the Sackmann corpus (corpus.py), matches.parquet here already carries
player1/player2 NAME strings, winner, and best_of directly (no broken-id
landmine to work around) -- this module is a thin reshape, not a re-parse.

SCORE COLLAPSE (same declared quirk as corpus.py, kept for calibration
consistency): p1_score/p2_score only recognizes "0"/"15"/"30"/"40"/"AD"; a
tiebreak point's raw digit score ("1".."12"+) is NOT in SCORE_MAP and collapses
to 0 via the same .map().fillna(0) -- this is corpus.py's own pre-existing
behavior, reproduced here verbatim, not a new bug.

INVARIANTS: domains-only; corpora READ-ONLY; ASCII; no src/kernel imports; <=300 LOC.
Tests: python -m pytest domains/tennis/point_engine/test_corpus_2026.py -q
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.tennis.point_engine.corpus import SCORE_MAP, score_bucket, set_bucket

_REPO = Path(__file__).resolve().parents[3]
_MCP_DIR = _REPO / "data" / "domains" / "tennis" / "mcp_2026"
POINTS_2026 = _MCP_DIR / "points.parquet"
MATCHES_2026 = _MCP_DIR / "matches.parquet"
POPULATION = "mcp_charted_nonrepresentative"


def _num(s: pd.Series) -> pd.Series:
    return s.map(SCORE_MAP).fillna(0).astype(int)


def build_point_frame_2026(points_path: Path = POINTS_2026,
                            matches_path: Path = MATCHES_2026) -> pd.DataFrame:
    """One row per real played 2026 charted point: server_id/returner_id (NAME
    strings), score_bucket (PRE-point, via groupby+shift, same as corpus.py),
    set_bucket, server_won. Same column contract as corpus.build_point_frame."""
    matches = pd.read_parquet(matches_path, columns=["match_id", "player1", "player2"]).set_index("match_id")
    pts = pd.read_parquet(points_path)
    pts = pts[pts["point_number"] >= 1].copy()
    pts = pts.dropna(subset=["set_no", "game_no", "point_server", "point_winner"]).copy()
    pts = pts[pts["match_id"].isin(matches.index)].copy()
    pts = pts.sort_values(["match_id", "set_no", "game_no", "point_number"])

    p1_post, p2_post = _num(pts["p1_score"]), _num(pts["p2_score"])
    key = [pts["match_id"], pts["set_no"], pts["game_no"]]
    p1_prior = p1_post.groupby(key).shift(1).fillna(0).astype(int)
    p2_prior = p2_post.groupby(key).shift(1).fillna(0).astype(int)

    server_is_p1 = pts["point_server"] == 1
    server_prior = p1_prior.where(server_is_p1, p2_prior)
    returner_prior = p2_prior.where(server_is_p1, p1_prior)

    m1 = pts["match_id"].map(matches["player1"])
    m2 = pts["match_id"].map(matches["player2"])
    out = pd.DataFrame({
        "match_id": pts["match_id"].to_numpy(),
        "server_id": m1.where(server_is_p1, m2).to_numpy(),
        "returner_id": m2.where(server_is_p1, m1).to_numpy(),
        "score_bucket": [score_bucket(int(s), int(r))
                         for s, r in zip(server_prior, returner_prior)],
        "set_bucket": [set_bucket(s) for s in pts["set_no"]],
        "server_won": (pts["point_winner"] == pts["point_server"]).astype(int).to_numpy(),
    })
    return out.dropna(subset=["server_id", "returner_id"])


def build_match_frame_2026(points_path: Path = POINTS_2026,
                             matches_path: Path = MATCHES_2026) -> pd.DataFrame:
    """One row per 2026 charted match: player1id/player2id (names), best_of,
    first_server_id (server at point 1, real), winner_id (real, from
    matches.parquet), total_games (n distinct (set_no,game_no) actually
    played). Same column contract as corpus.build_match_frame."""
    matches = pd.read_parquet(matches_path)
    pts = pd.read_parquet(points_path, columns=["match_id", "set_no", "game_no",
                                                 "point_number", "point_server"])
    pts = pts[pts["match_id"].isin(matches["match_id"])]
    first_server = (pts[pts["point_number"] == 1]
                     .drop_duplicates(subset="match_id")
                     .set_index("match_id")["point_server"])
    total_games = (pts.drop_duplicates(subset=["match_id", "set_no", "game_no"])
                       .groupby("match_id").size())

    rows = []
    for r in matches.itertuples(index=False):
        mid = r.match_id
        fs = first_server.get(mid)
        tg = total_games.get(mid)
        if fs not in (1, 2) or tg is None or pd.isna(r.winner):
            continue
        rows.append({
            "match_id": mid, "player1id": r.player1, "player2id": r.player2,
            "best_of": int(r.best_of) if pd.notna(r.best_of) else 3,
            "first_server_id": r.player1 if fs == 1 else r.player2,
            "winner_id": r.winner, "total_games": int(tg),
        })
    return pd.DataFrame(rows)


__all__ = ["POINTS_2026", "MATCHES_2026", "POPULATION",
           "build_point_frame_2026", "build_match_frame_2026"]
