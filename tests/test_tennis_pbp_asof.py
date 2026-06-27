"""Per-file test for the tennis POINT-BY-POINT as-of layer.

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/test_tennis_pbp_asof.py -q

Covers (all OFFLINE -- never touches the network):
  - ingest_sackmann_pbp.build_points / aggregate_match_pbp on a hand-built fixture
    (correct break-point save/convert, pressure win, decider rates; NaN -- never
    0-fill -- when an optional column is absent),
  - asof_pbp leak-free walk-forward: a player's FIRST match snapshots to NaN (debut),
    a later match sees the strictly-prior mean, the current match's own points are
    NEVER used; the no-future-leak assertion in walk_forward_asof holds,
  - the gate runner's planted-null + signal scoring math through the IDENTICAL
    proven gate (signal column ships, noise column rejects, degenerate base flags).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from domains.tennis import ingest_sackmann_pbp as ing
from domains.tennis import asof_pbp as ao
from scripts.platformkit import gate_run_tennis_pbp as gr


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _points_fixture(match_id: str = "M1") -> pd.DataFrame:
    """A tiny bo3 match: 6 points. Player 1 serves pts 1-3, player 2 serves 4-6.

    Engineered so the within-match rates are hand-checkable.
    """
    rows = [
        # PointServer, PointWinner, ServeNumber, RallyCount, SetNo, P1BreakPoint, P2BreakPoint, BreakPoint, GamePoint, SetPoint
        (1, 1, 1, 2, 1, 0, 0, 0, 0, 0),  # p1 serves, p1 wins, 1st serve, short rally
        (1, 2, 2, 6, 1, 0, 1, 1, 0, 0),  # p1 serves, p2 wins -> p2 had BP (p2 converts BP); long rally
        (1, 1, 1, 1, 1, 0, 1, 1, 0, 0),  # p1 serves, p1 wins, p2 had BP -> p1 SAVES bp; short
        (2, 2, 1, 3, 1, 0, 0, 0, 0, 0),  # p2 serves, p2 wins, 1st serve, short
        (2, 1, 1, 8, 2, 1, 0, 1, 0, 1),  # p2 serves, p1 wins, p1 had BP -> p1 converts; SetPoint; decider set; long
        (2, 2, 2, 4, 2, 1, 0, 1, 0, 0),  # p2 serves, p2 wins, p1 had BP -> p2 SAVES; short
    ]
    cols = ["PointServer", "PointWinner", "ServeNumber", "RallyCount", "SetNo",
            "P1BreakPoint", "P2BreakPoint", "BreakPoint", "GamePoint", "SetPoint"]
    df = pd.DataFrame(rows, columns=cols)
    df.insert(0, "match_id", match_id)
    df.insert(1, "PointNumber", range(1, len(df) + 1))
    return df


def test_build_points_keeps_core_cols():
    df = ing.build_points(_points_fixture())
    for c in ing._POINT_COLS_CORE:
        assert c in df.columns
    assert len(df) == 6


def test_aggregate_rates_hand_checked():
    pts = ing.build_points(_points_fixture())
    agg = ing.aggregate_match_pbp(pts, best_of=3)
    assert set(agg["player"]) == {1, 2}
    p1 = agg[agg["player"] == 1].iloc[0]
    p2 = agg[agg["player"] == 2].iloc[0]

    # P1 serves pts 1,2,3. P1 faced BP on pts 2 and 3 (P2BreakPoint==1 while serving).
    # Saved pt3 (won), lost pt2 -> bp_save = 1/2 = 0.5
    assert abs(p1["bp_save_pct"] - 0.5) < 1e-9
    # P1 returns pts 4,5,6. P1 had BP on pts 5,6 (P1BreakPoint==1 while returning).
    # Converted pt5 (won), lost pt6 -> bp_convert = 1/2 = 0.5
    assert abs(p1["bp_convert_pct"] - 0.5) < 1e-9
    # decider set (SetNo==2 for bo3): pts 5,6. P1 won pt5, lost pt6 -> 1/2
    assert abs(p1["decider_pts_win_pct"] - 0.5) < 1e-9
    assert p1["decider_pts"] == 2
    # P2 mirror: serves 4,5,6; faced BP on 5,6, saved pt6 -> 1/2
    assert abs(p2["bp_save_pct"] - 0.5) < 1e-9


def test_missing_optional_col_is_nan_not_zero():
    pts = ing.build_points(_points_fixture()).drop(columns=["RallyCount"])
    agg = ing.aggregate_match_pbp(pts, best_of=3)
    p1 = agg[agg["player"] == 1].iloc[0]
    # rally tendencies must degrade to NaN, NEVER fabricate 0.0
    assert pd.isna(p1["short_rally_win_pct"])
    assert pd.isna(p1["long_rally_win_pct"])


# --------------------------------------------------------------------------- #
# As-of leak-free
# --------------------------------------------------------------------------- #
def _two_match_long():
    """Build a long table for player X across two chronological matches."""
    agg_rows = []
    for mid, val in (("MA", 0.40), ("MB", 0.80)):
        # player 1 = X (varying stat), player 2 = a fresh opponent each time
        agg_rows.append({"match_id": mid, "player": 1, "bp_save_pct": val,
                         "bp_convert_pct": val, "pressure_win_pct": val,
                         "serve1_win_pct": val, "short_rally_win_pct": val,
                         "long_rally_win_pct": val, "decider_pts_win_pct": val,
                         "pts_played": 50, "serve_pts": 25, "return_pts": 25,
                         "pressure_pts": 5, "decider_pts": 3})
        agg_rows.append({"match_id": mid, "player": 2, "bp_save_pct": 0.5,
                         "bp_convert_pct": 0.5, "pressure_win_pct": 0.5,
                         "serve1_win_pct": 0.5, "short_rally_win_pct": 0.5,
                         "long_rally_win_pct": 0.5, "decider_pts_win_pct": 0.5,
                         "pts_played": 50, "serve_pts": 25, "return_pts": 25,
                         "pressure_pts": 5, "decider_pts": 3})
    agg = pd.DataFrame(agg_rows)
    matches = pd.DataFrame({
        "match_id": ["MA", "MB"],
        "date": ["2019-01-14", "2019-01-16"],
        "round": ["R128", "R64"],
        "player1": ["X", "X"],          # X is p1 in both
        "player2": ["OppA", "OppB"],    # different opponents -> X has prior history
        "winner": [1, 1],
    })
    return agg, matches


def test_asof_debut_is_nan_and_prior_only():
    agg, matches = _two_match_long()
    long = ao.build_match_player_long(agg, matches)
    asof = ao.build_asof(long, stats=["bp_save_pct"])
    # X's debut (MA) must snapshot to NaN with n_prior 0 (no leak of its own value)
    xa = asof[(asof["match_id"] == "MA") & (asof["slot"] == 1)].iloc[0]
    assert pd.isna(xa["bp_save_pct_asof"])
    assert xa["bp_save_pct_n_prior"] == 0
    # X's 2nd match (MB) must see ONLY MA's value (0.40), NOT MB's own (0.80)
    xb = asof[(asof["match_id"] == "MB") & (asof["slot"] == 1)].iloc[0]
    assert abs(xb["bp_save_pct_asof"] - 0.40) < 1e-9
    assert xb["bp_save_pct_n_prior"] == 1


def test_to_match_diff_shapes():
    agg, matches = _two_match_long()
    long = ao.build_match_player_long(agg, matches)
    asof = ao.build_asof(long, stats=["bp_save_pct"])
    diff = ao.to_match_diff(asof, stats=["bp_save_pct"])
    assert "bp_save_pct_asof_diff" in diff.columns
    assert "bp_save_pct_n_prior_min" in diff.columns
    assert "p1_won" in diff.columns
    # MA: both players debut -> diff is NaN (no fabricated 0)
    ma = diff[diff["match_id"] == "MA"].iloc[0]
    assert pd.isna(ma["bp_save_pct_asof_diff"])


# --------------------------------------------------------------------------- #
# Gate scoring math through the IDENTICAL proven gate
# --------------------------------------------------------------------------- #
def _synthetic_corpus(n: int = 1200, signal: float = 1.2, seed: int = 1):
    """A gateable corpus: real Elo base + a planted SIGNAL diff that helps + noise.

    Columns required by gate_feature_on_corpus: date, winner, event_id, win_prob_p1,
    plus the candidate feature columns.
    """
    rng = np.random.default_rng(seed)
    elo_diff = rng.normal(0, 1.0, n)
    sig = rng.normal(0, 1.0, n)
    # true outcome depends on elo AND the signal (so signal genuinely adds skill)
    logit = 0.9 * elo_diff + signal * sig
    p = 1.0 / (1.0 + np.exp(-logit))
    winner = np.where(rng.uniform(size=n) < p, 1, 2)
    # Elo base sees only a noisy version of elo_diff (so a real gap remains for sig)
    base_logit = 0.9 * elo_diff
    win_prob_p1 = 1.0 / (1.0 + np.exp(-base_logit))
    years = np.where(np.arange(n) < n * 0.6, 2021, 2024)  # train<=2022, test>2022
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in range(n)],
        "date": pd.to_datetime([f"{y}-06-01" for y in years]),
        "winner": winner,
        "win_prob_p1": win_prob_p1,
        "bp_save_pct_asof_diff": sig,            # the planted SIGNAL
    })


def test_planted_signal_ships_and_null_rejects():
    c1 = _synthetic_corpus(seed=1)
    c2 = _synthetic_corpus(seed=2)
    res = gr.gate_corpora(c1, c2, eps=0.05, seed=0)
    # the gate must be able to FAIL noise (trust check)
    assert res["null_rejects"] is True
    # base must be skillful (degenerate guard not tripped on a real Elo base)
    assert res["base_skillful"] is True
    # the planted real signal should SHIP through the identical gate (both dirs)
    sig_res = next(r for r in res["results"]
                   if r["column"] == "bp_save_pct_asof_diff")
    assert sig_res["verdict"] == "SHIP", sig_res
    # the null column itself must NOT ship
    assert res["null"]["verdict"] != "SHIP"


def test_run_is_tier3_blocked_without_corpora(monkeypatch):
    # With no real point-by-point cache + no reachable source, run() must HONESTLY
    # report TIER3_BLOCKED -- never fabricate a corpus or a SHIP.
    monkeypatch.setattr(gr, "corpora_available",
                        lambda: {"available": False, "n_corpora": 0,
                                 "agg_files": [], "base_present": [],
                                 "reason": "source unreachable; no join base"})
    res = gr.run()
    assert res["verdict"] == "TIER3_BLOCKED"
    assert res["results"] == []


def test_verdict_json_has_no_dollar_field(tmp_path):
    res = {"layer": "tennis_pbp", "verdict": "TIER3_BLOCKED", "n_corpora": 0,
           "reason": "blocked", "acquisition": {"available": False},
           "results": [], "null": None, "proposal_only": True,
           "vs_close": gr._VS_CLOSE}
    out = gr.write_verdict(res, out_path=tmp_path / "v.json")
    txt = out.read_text(encoding="ascii").lower()
    for banned in ("roi", "profit", "$", "edge\":", "dollar"):
        assert banned not in txt, banned
    assert "held_out_brier" in txt
