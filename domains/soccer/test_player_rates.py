"""Per-file test for domains.soccer.player_rates (network-free, in-memory df).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_player_rates.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.player_rates import (
    canonical_stats,
    player_rate,
    position_baseline,
)


def _row(pid, date, pos, minutes, **stats):
    base = {
        "player_id": pid,
        "date": date,
        "position": pos,
        "minutes": minutes,
        "totalShots": 0,
        "shotsOnTarget": 0,
        "foulsCommitted": 0,
        "foulsSuffered": 0,
        "yellowCards": 0,
        "redCards": 0,
        "goalAssists": 0,
        "offsides": 0,
        "totalGoals": 0,
        "saves": 0,
    }
    base.update(stats)
    return base


def _df():
    rows = [
        # P1 forward: 2 prior matches before 2026-06-10, 90 min each, 4 then 2 shots.
        _row("P1", "2026-06-01", "F", 90, totalShots=4),
        _row("P1", "2026-06-05", "F", 90, totalShots=2),
        # P2 forward: lots of data to anchor the F baseline.
        _row("P2", "2026-05-20", "F", 90, totalShots=3),
        _row("P2", "2026-05-25", "F", 90, totalShots=3),
        _row("P2", "2026-05-28", "F", 90, totalShots=6),
        # P3 forward: THIN sample (one 90' match, 0 shots) -> should shrink up.
        _row("P3", "2026-06-02", "F", 90, totalShots=0),
    ]
    return pd.DataFrame(rows)


def test_canonical_stats_present():
    cs = canonical_stats()
    for name in ["Shots", "Cards", "Goal+Assist", "Saves"]:
        assert name in cs


def test_per90_hand_checked():
    df = _df()
    # P1: 6 shots over 180 min -> raw per90 = 90*6/180 = 3.0; with shrink toward
    # the F baseline it stays a finite positive rate. Check raw via a stat with
    # no baseline pull by isolating P1 only.
    only_p1 = df[df["player_id"] == "P1"]
    r = player_rate(only_p1, "P1", "Shots", "2026-06-10")
    # No other players -> baseline == P1's own pooled rate == 3.0; shrink to same.
    assert abs(r["per90"] - 3.0) < 1e-9
    assert r["status"] == "ok"
    assert r["n_matches"] == 2
    assert abs(r["minutes"] - 180.0) < 1e-9


def test_leak_free_future_match_ignored():
    df = _df()
    r_before = player_rate(df, "P1", "Shots", "2026-06-10")
    # Add a HUGE post-date match for P1 (dated == and after as_of). It must be
    # excluded -> the rate does NOT move.
    leak = pd.DataFrame([
        _row("P1", "2026-06-10", "F", 90, totalShots=99),   # == as_of -> excluded
        _row("P1", "2026-07-01", "F", 90, totalShots=99),   # after  -> excluded
    ])
    df2 = pd.concat([df, leak], ignore_index=True)
    r_after = player_rate(df2, "P1", "Shots", "2026-06-10")
    assert abs(r_before["per90"] - r_after["per90"]) < 1e-9
    assert r_before["n_matches"] == r_after["n_matches"]


def test_shrinkage_pulls_thin_sample_toward_baseline():
    df = _df()
    baseline = position_baseline(df, "Shots", "2026-06-10", "F")
    assert baseline is not None and baseline > 0
    # P3 raw per90 is 0.0 (thin); shrunk must be pulled UP toward baseline.
    r = player_rate(df, "P3", "Shots", "2026-06-10")
    assert r["shrunk"] is True
    assert 0.0 < r["per90"] < baseline  # between raw(0) and baseline
    # With one 90' match n_eff=1, K=3: shrunk = (1*0 + 3*b)/(1+3) = 0.75*b.
    assert abs(r["per90"] - 0.75 * baseline) < 1e-9


def test_zero_history_returns_baseline_shrunk():
    df = _df()
    r = player_rate(df, "P_NEW", "Shots", "2026-06-10", position="F")
    assert r["status"] == "ok"
    assert r["shrunk"] is True
    assert r["minutes"] == 0.0
    baseline = position_baseline(df, "Shots", "2026-06-10", "F")
    assert abs(r["per90"] - baseline) < 1e-9


def test_empty_history_unknown():
    empty = pd.DataFrame(columns=["player_id", "date", "position", "minutes", "totalShots"])
    r = player_rate(empty, "P1", "Shots", "2026-06-10")
    assert r["status"] == "unknown"
    assert r["per90"] is None


def test_unknown_stat_is_unknown():
    df = _df()
    r = player_rate(df, "P1", "Tackles", "2026-06-10")
    assert r["status"] == "unknown"
    assert r["per90"] is None


def test_club_prior_none_is_exact_legacy():
    df = _df()
    a = player_rate(df, "P1", "Shots", "2026-06-10")
    b = player_rate(df, "P1", "Shots", "2026-06-10", club_prior=None)
    assert abs(a["per90"] - b["per90"]) < 1e-12
    assert a["shrunk"] == b["shrunk"] and a["n_matches"] == b["n_matches"]


def test_club_prior_makes_thin_player_reliable():
    df = _df()
    # P3 has one thin WC match (n_eff WC = 1). A solid club season (10 starts)
    # lifts n_eff above CONFIDENCE_N_EFF so the rate is no longer thin.
    cp = {"per90": 2.5, "starts": 10.0, "status": "ok"}
    r = player_rate(df, "P3", "Shots", "2026-06-10", club_prior=cp)
    assert r["status"] == "ok"
    assert r["n_eff"] >= 5.0
    assert r["shrunk"] is False  # club-backed -> reliable
    # Blend: n_wc=1 at raw 0.0, club_w=10 at 2.5 -> (0 + 25)/11 ~= 2.273.
    assert abs(r["per90"] - (10 * 2.5) / 11.0) < 1e-6


def test_club_prior_weight_capped():
    df = _df()
    cp = {"per90": 5.0, "starts": 999.0, "status": "ok"}
    r = player_rate(df, "P3", "Shots", "2026-06-10", club_prior=cp)
    # weight capped at 20: n_eff = 1 + 20 = 21.
    assert abs(r["n_eff"] - 21.0) < 1e-9


def test_club_prior_unusable_falls_back_to_legacy():
    df = _df()
    # No per90 -> treated as None -> legacy path.
    cp = {"per90": None, "starts": 10.0, "status": "ok"}
    a = player_rate(df, "P3", "Shots", "2026-06-10", club_prior=cp)
    b = player_rate(df, "P3", "Shots", "2026-06-10")
    assert abs(a["per90"] - b["per90"]) < 1e-12
    assert a["shrunk"] == b["shrunk"]
