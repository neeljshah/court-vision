"""Tests for domains.tennis.mcp_2026 -- schema assertions + one hand-verified match.

Run: python -m pytest domains/tennis/test_mcp_2026.py -q   (per-file only)

The hand-verified match (Rome Masters 2026 final, Ruud vs Sinner) is recounted
from the RAW CSV with an independent stdlib-csv implementation -- if the pandas
parser and this recount ever disagree, one of them is wrong.
"""
from __future__ import annotations

import csv

import pandas as pd
import pytest

from domains.tennis.mcp_2026 import (MATCHES_COLS, OUT_DIR, POINTS_COLS,
                                     POPULATION, RAW_DIR, SR_COLS, build_all,
                                     classify_serve, rally_count)

MID = "20260517-M-Rome_Masters-F-Casper_Ruud-Jannik_Sinner"


@pytest.fixture(scope="module")
def frames():
    paths = [OUT_DIR / f for f in
             ("points.parquet", "match_serve_return.parquet", "matches.parquet")]
    if all(p.exists() for p in paths):
        return {"points": pd.read_parquet(paths[0]),
                "match_serve_return": pd.read_parquet(paths[1]),
                "matches": pd.read_parquet(paths[2])}
    return build_all()


def test_classify_serve_tokens():
    assert classify_serve("6*") == "ace"
    assert classify_serve("4n") == "fault"
    assert classify_serve("5f3x#") == "in_play"      # return attempt = not an ace
    assert classify_serve("4b37y1r3n#") == "in_play"
    assert classify_serve("") == "unknown"
    assert classify_serve("5#") == "svc_winner"


def test_rally_count():
    assert rally_count("6*") == 1        # ace counts as 1 shot
    assert rally_count("4b37b3*") == 3   # serve + 2 shots, winner
    assert rally_count("5f3x#") == 1     # return error excluded
    assert rally_count("4n") == 0        # fault
    assert rally_count("") is None


def test_points_schema(frames):
    p = frames["points"]
    assert list(p.columns) == POINTS_COLS
    assert len(p) >= 56371                       # 2026 slice as of 2026-07 raw pull
    assert (p["population"] == POPULATION).all()
    assert p["point_server"].isin([1, 2]).all()
    assert p["point_winner"].isin([1, 2]).all()
    assert (p["year"] == 2026).all()
    assert p["set_no"].dtype == "int64"
    assert p["match_id"].notna().all()
    assert set(p["tour"].unique()) <= {"m", "w"}
    reg = ~p["is_tiebreak"]
    assert p.loc[reg, "p1_score"].isin(["0", "15", "30", "40", "AD"]).all()


def test_serve_return_schema(frames):
    sr = frames["match_serve_return"]
    assert list(sr.columns) == SR_COLS
    assert len(sr) == 2 * frames["matches"].shape[0]
    assert (sr["population"] == POPULATION).all()
    assert (sr["first_in"] <= sr["serve_pts"]).all()
    assert (sr["first_won"] <= sr["first_in"]).all()
    assert (sr["second_won"] <= sr["second_pts"]).all()
    assert (sr["bp_saved"] <= sr["bp_faced"]).all()
    assert (sr["aces"] <= sr["serve_pts"]).all()


def test_matches_schema(frames):
    m = frames["matches"]
    assert list(m.columns) == MATCHES_COLS
    assert m["match_id"].is_unique
    assert (m["population"] == POPULATION).all()
    resolved = m["winner"].notna()
    assert (m.loc[resolved, "winner_derivation"] == "point_sequence_sets").all()
    ok = (m.loc[resolved, "winner"] == m.loc[resolved, "player1"]) | (
        m.loc[resolved, "winner"] == m.loc[resolved, "player2"])
    assert ok.all()


def _recount_raw():
    """Independent stdlib-csv recount of the hand-verified match."""
    path = RAW_DIR / "charting-m-points-2020s.csv"
    with open(path, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["match_id"] == MID]
    rally = set("fbrsvzopuylmhijktq")

    def is_fault(t):
        return bool(t) and not (set(t) & rally) and "*" not in t and "#" not in t

    out = {}
    for p in ("1", "2"):
        served = [r for r in rows if r["Svr"] == p]
        out[p] = {
            "serve_pts": len(served),
            "serve_pts_won": sum(1 for r in served if r["PtWinner"] == p),
            "first_in": sum(1 for r in served if not is_fault(r["1st"])),
            "aces": sum(1 for r in served
                        for tok in [r["2nd"] if is_fault(r["1st"]) else r["1st"]]
                        if "*" in tok and not set(tok) & rally),
            "dfs": sum(1 for r in served
                       if is_fault(r["1st"]) and is_fault(r["2nd"])),
        }
    return len(rows), out


def test_hand_verified_rome_final(frames):
    n_raw, raw = _recount_raw()
    assert n_raw == 119

    m = frames["matches"]
    row = m[m["match_id"] == MID].iloc[0]
    assert row["n_points"] == 119
    assert row["winner"] == "Jannik Sinner"     # last game -> 4-6 set 2, Set2=1 prior

    sr = frames["match_serve_return"]
    for p in (1, 2):
        got = sr[(sr["match_id"] == MID) & (sr["player_no"] == p)].iloc[0]
        want = raw[str(p)]
        for k in ("serve_pts", "serve_pts_won", "first_in", "aces", "dfs"):
            assert int(got[k]) == want[k], (p, k, int(got[k]), want[k])
    # exact hand-checked values (also verified by eye against the raw CSV)
    p1 = sr[(sr["match_id"] == MID) & (sr["player_no"] == 1)].iloc[0]
    assert (int(p1["serve_pts"]), int(p1["first_in"]), int(p1["aces"]),
            int(p1["dfs"])) == (64, 37, 3, 2)
