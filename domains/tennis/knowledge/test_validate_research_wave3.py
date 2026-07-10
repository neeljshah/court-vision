"""Per-file test for knowledge.validate_research_wave3. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_research_wave3.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_research_wave3 as vw3


def _synthetic_games(match_id, servers, winners, set_no=1, start_pn=0):
    """Point rows for one (match_id, set_no)'s sequential games: 2 filler
    points with unchanged score, then a deciding point that increments the
    winner's games_won -- mirrors the real corpus's own-last-row-increment
    shape confirmed this session."""
    rows = []
    p1, p2 = 0, 0
    pn = start_pn
    for g, (srv, win) in enumerate(zip(servers, winners), start=1):
        for _ in range(2):
            pn += 1
            rows.append({"match_id": match_id, "set_no": set_no, "game_no": g, "point_number": pn,
                         "point_server": srv, "p1_games_won": p1, "p2_games_won": p2,
                         "p1_ace": 0, "p2_ace": 0, "speed_kmh": 150.0})
        pn += 1
        if win == 1:
            p1 += 1
        else:
            p2 += 1
        rows.append({"match_id": match_id, "set_no": set_no, "game_no": g, "point_number": pn,
                     "point_server": srv, "p1_games_won": p1, "p2_games_won": p2,
                     "p1_ace": int(srv == 1), "p2_ace": int(srv == 2), "speed_kmh": 150.0 + g})
    return pd.DataFrame(rows), pn


def test_verdict_nan_p_is_not_testable_never_misclassified():
    assert vw3._verdict(float("nan"), 0.5, 0.03) == "NOT_TESTABLE"
    assert vw3._verdict(0.001, 0.5, 0.03) == "CONFIRMED_LOCAL"
    assert vw3._verdict(0.5, 0.5, 0.03) == "NULL_LOCAL"
    assert vw3._verdict(0.001, 0.01, 0.03) == "NULL_LOCAL"  # significant but below effect bar


def test_ball_cycle_tag_boundaries():
    seq = np.array([1, 2, 3, 6, 7, 8, 9, 10, 15, 16, 17])
    tag = vw3._ball_cycle_tag(seq)
    assert list(tag) == ["fresh", "fresh", "", "worn", "worn", "fresh", "fresh", "",
                          "worn", "worn", "fresh"]


def test_game_level_frame_derives_server_winner_seq_across_set_boundary():
    sp1, last_pn = _synthetic_games("m1", servers=[1, 2, 1], winners=[1, 2, 1], set_no=1)
    sp2, _ = _synthetic_games("m1", servers=[2, 1], winners=[2, 2], set_no=2, start_pn=last_pn)
    sp = pd.concat([sp1, sp2], ignore_index=True)
    g = vw3._game_level_frame(sp).sort_values(["set_no", "game_no"]).reset_index(drop=True)
    assert list(g["seq"]) == [1, 2, 3, 4, 5]  # cumulative across the set boundary
    assert list(g["server"]) == [1.0, 2.0, 1.0, 2.0, 1.0]
    assert list(g["winner"]) == [1.0, 2.0, 1.0, 2.0, 2.0]
    # seq4 (set2 g1): baseline resets to (0,0) despite set1 ending 2-1; server2==winner2 -> hold.
    # seq5 (set2 g2): server1, winner2 -> break, not a hold.
    assert list(g["hold"]) == [True, True, True, True, False]


def test_game_level_frame_sentinel_server_zero_is_unresolved():
    sp, _ = _synthetic_games("m1", servers=[1, 2], winners=[1, 2])
    sp.loc[sp["game_no"] == 1, "point_server"] = 0  # real-corpus sentinel, confined to game 1
    g = vw3._game_level_frame(sp).sort_values("seq")
    assert pd.isna(g.iloc[0]["server"])
    assert g.iloc[1]["server"] == 2.0


def test_break_pairs_hand_computed_treatment_and_baseline():
    # servers=[1,2,1,2,1,2], winners=[1,2,1,1,2,2] -> breaks at game4 (breaker=1) and game5 (breaker=2)
    sp, _ = _synthetic_games("m1", servers=[1, 2, 1, 2, 1, 2], winners=[1, 2, 1, 1, 2, 2])
    g = vw3._game_level_frame(sp)
    pairs = vw3._break_pairs(g).sort_values("treatment").reset_index(drop=True)
    assert len(pairs) == 2
    assert pairs.loc[0, "treatment"] == 0.0 and abs(pairs.loc[0, "baseline"] - 1.0) < 1e-9
    assert pairs.loc[1, "treatment"] == 1.0 and abs(pairs.loc[1, "baseline"] - 0.5) < 1e-9


def test_post_break_hold_rate_not_testable_below_floor():
    sp, _ = _synthetic_games("m1", servers=[1, 2, 1, 2], winners=[1, 2, 1, 1])  # 1 break only
    g = vw3._game_level_frame(sp)
    r = vw3.post_break_hold_rate(g)
    assert r["verdict"] == "NOT_TESTABLE"
    assert r["n"] < vw3.MIN_BREAKS


def test_point_ball_cycle_frame_and_bucket_not_testable_below_floor():
    sp, _ = _synthetic_games("m1", servers=[1, 2, 1, 2, 1, 2, 1], winners=[1, 2, 1, 2, 1, 2, 1])
    g = vw3._game_level_frame(sp)
    pts = vw3.point_ball_cycle_frame(sp, g)
    assert set(pts["tag"].unique()) <= {"fresh", "worn", ""}
    r_ace = vw3.ball_cycle_ace_rate(pts)
    r_speed = vw3.ball_cycle_serve_speed(pts)
    assert r_ace["verdict"] == "NOT_TESTABLE" and r_speed["verdict"] == "NOT_TESTABLE"


def test_run_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    sp, _ = _synthetic_games("m1", servers=[1, 2, 1, 2, 1, 2, 1], winners=[1, 2, 1, 2, 1, 2, 1])
    monkeypatch.setattr(vw3, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw3, "load_slam_points", lambda: sp)
    rows = vw3.run()
    assert len(rows) == 3
    assert {r["hypothesis"] for r in rows} == {
        "post_break_hold_rate", "ball_cycle_ace_rate", "ball_cycle_serve_speed_kmh"}
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3


def test_run_split_half_writes_six_rows_three_per_half(tmp_path, monkeypatch):
    frames = []
    pn = 0
    for i in range(4):
        sp_i, pn = _synthetic_games("m%d" % i, servers=[1, 2, 1, 2, 1, 2, 1],
                                     winners=[1, 2, 1, 2, 1, 2, 1], start_pn=pn)
        frames.append(sp_i)
    sp = pd.concat(frames, ignore_index=True)
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw3, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw3, "load_slam_points", lambda: sp)
    rows = vw3.run_split_half()
    assert len(rows) == 6
    assert {r["hypothesis"] for r in rows} == {
        "post_break_hold_rate__split_A", "post_break_hold_rate__split_B",
        "ball_cycle_ace_rate__split_A", "ball_cycle_ace_rate__split_B",
        "ball_cycle_serve_speed_kmh__split_A", "ball_cycle_serve_speed_kmh__split_B"}
    assert all(r["edge_claimed"] is False for r in rows)


def test_self_check_runs():
    vw3._self_check()
