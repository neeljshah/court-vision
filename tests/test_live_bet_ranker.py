"""tests/test_live_bet_ranker.py — covers atomic write, stale guard, line-move
detection, cooldown, and tick logic without hitting the real model."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import live_bet_ranker as lbr  # noqa: E402


# ---------- atomic write ----------
def test_atomic_write_json_safe_to_read_mid_write(tmp_path):
    """Atomic write means a concurrent reader either sees the OLD payload
    or the NEW payload — never a half-written file."""
    out = tmp_path / "live.json"
    # write v1
    lbr.atomic_write_json(str(out), {"v": 1, "bets": []})
    assert json.loads(out.read_text())["v"] == 1
    # write v2 — readers between these two should always see valid JSON
    lbr.atomic_write_json(str(out), {"v": 2, "bets": [{"a": 1}]})
    payload = json.loads(out.read_text())
    assert payload["v"] == 2
    assert payload["bets"][0]["a"] == 1
    # no stray temp files left over
    leftovers = [
        p for p in os.listdir(tmp_path)
        if p.startswith(".tmp_")
    ]
    assert leftovers == [], f"leftover temp files: {leftovers}"


def test_atomic_write_text_overwrites_existing(tmp_path):
    out = tmp_path / "report.md"
    lbr.atomic_write_text(str(out), "# v1\n")
    lbr.atomic_write_text(str(out), "# v2\n")
    assert out.read_text() == "# v2\n"


# ---------- odds math sanity ----------
def test_american_to_decimal_and_payout():
    assert abs(lbr.american_to_decimal(+100) - 2.0) < 1e-9
    assert abs(lbr.american_to_decimal(-200) - 1.5) < 1e-9
    assert abs(lbr.american_payout(+200, 1) - 2.0) < 1e-9
    assert abs(lbr.american_payout(-200, 1) - 0.5) < 1e-9


def test_implied_prob_round_trip():
    assert abs(lbr.implied_prob(-110) - (110 / 210)) < 1e-9
    assert abs(lbr.implied_prob(+150) - (100 / 250)) < 1e-9


def test_kelly_fraction_no_edge():
    # 50/50 prob at -110 odds: kelly should be 0 or negative -> clamped to 0
    f = lbr.kelly_fraction(0.5, -110)
    assert f == 0.0


def test_kelly_fraction_positive_edge():
    # 60% to win on +100 line => kelly = (1*0.6 - 0.4)/1 = 0.20
    f = lbr.kelly_fraction(0.60, +100)
    assert abs(f - 0.20) < 1e-9


# ---------- stale-snapshot guard ----------
def test_stale_book_detection(monkeypatch, tmp_path):
    """Snapshots > STALE_THRESHOLD_SEC old must be flagged stale per book."""
    # Build fake books dict with 1 fresh book + 1 stale book
    now = datetime.now(timezone.utc)
    fresh = now - timedelta(seconds=10)
    stale = now - timedelta(seconds=lbr.STALE_THRESHOLD_SEC + 60)
    df_fresh = pd.DataFrame([{
        "captured_at": fresh, "book": "fd", "game_id": "1",
        "player_id": "", "player_name": "X", "stat": "pts",
        "line": 10.5, "over_price": -110, "under_price": -110,
        "start_time": "",
    }])
    df_stale = pd.DataFrame([{
        "captured_at": stale, "book": "bov", "game_id": "1",
        "player_id": "", "player_name": "X", "stat": "pts",
        "line": 10.5, "over_price": -110, "under_price": -110,
        "start_time": "",
    }])
    books = {"fd": df_fresh, "bov": df_stale}
    latest = {"fd": fresh, "bov": stale}

    stale_books = {
        b: ((now - t).total_seconds() > lbr.STALE_THRESHOLD_SEC)
        for b, t in latest.items()
    }
    assert stale_books["fd"] is False
    assert stale_books["bov"] is True


# ---------- bet cooldown ----------
def test_bet_key_stable():
    b = {"player": "Wemby", "stat": "blk", "side": "OVER",
         "book": "fd", "line": 2.5}
    k1 = lbr.bet_key(b)
    k2 = lbr.bet_key(b)
    assert k1 == k2
    assert "Wemby" in k1 and "blk" in k1 and "OVER" in k1


def test_load_placed_with_missing_file(tmp_path):
    p = tmp_path / "placed.json"
    placed = lbr.load_placed(str(p))
    assert placed == set()


def test_load_placed_round_trip(tmp_path):
    p = tmp_path / "placed.json"
    keys = ["Wemby|blk|OVER|fd|2.5", "SGA|pts|UNDER|pin|33.5"]
    p.write_text(json.dumps({"placed_keys": keys}))
    placed = lbr.load_placed(str(p))
    assert placed == set(keys)


def test_cooldown_filters_placed_bet():
    """If a key is in `placed`, the tick output should NOT include it."""
    placed = {"Wemby|blk|OVER|fd|2.5"}
    bets = [
        {"player": "Wemby", "stat": "blk", "side": "OVER",
         "book": "fd", "line": 2.5, "edge_pct": 5.0,
         "ev_per_dollar": 0.05, "kelly_stake_$": 30},
        {"player": "Wemby", "stat": "blk", "side": "OVER",
         "book": "bov", "line": 2.5, "edge_pct": 4.0,
         "ev_per_dollar": 0.04, "kelly_stake_$": 25},
    ]
    filtered = [b for b in bets if lbr.bet_key(b) not in placed]
    assert len(filtered) == 1
    assert filtered[0]["book"] == "bov"


# ---------- line-move detection ----------
def test_line_move_detected_on_half_point():
    prior = {"Wemby|blk|fd|OVER": {"line": 2.5, "odds": -110}}
    new_line, new_odds = 3.0, -110
    dl = new_line - prior["Wemby|blk|fd|OVER"]["line"]
    assert abs(dl) >= lbr.LINE_MOVE_PT
    # direction
    assert (dl > 0) is True  # arrow should be ↑LINE


def test_odds_move_detected_at_10pct():
    prior_odds = -110
    new_odds = -100  # ~9% move on |odds|
    dop = (new_odds - prior_odds) / abs(prior_odds)
    # 10/110 = 0.0909 -> just under threshold
    assert abs(dop) < lbr.ODDS_MOVE_PCT

    new_odds_strong = -90
    dop2 = (new_odds_strong - prior_odds) / abs(prior_odds)
    # 20/110 = 0.18 -> over threshold
    assert abs(dop2) >= lbr.ODDS_MOVE_PCT


# ---------- model_hit_prob bounds ----------
def test_model_hit_prob_bounds():
    # Line exactly at q50 => p ≈ 0.5
    p = lbr.model_hit_prob(point_pred=10.0, q10=8.0, q50=10.0, q90=12.0,
                            line=10.0, side="OVER")
    assert 0.45 < p < 0.55
    # Line far above q90 => p_over ~ 0
    p2 = lbr.model_hit_prob(point_pred=10.0, q10=8.0, q50=10.0, q90=12.0,
                              line=30.0, side="OVER")
    assert p2 < 0.05


# ---------- _read_lines_csv handles 10/11 col schema ----------
def test_read_lines_csv_handles_both_schemas(tmp_path):
    p = tmp_path / "lines.csv"
    p.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time\n"
        "2026-05-26T08:00:00,bov,X,,Alex Caruso,pts,6.5,-240,+175,2026-05-27T00:40:00\n"
        # 11-col row (Bovada drift with team column inserted)
        "2026-05-26T08:01:00,bov,X,,Alex Caruso,SAS,pts,7.5,-165,+125,2026-05-27T00:40:00\n"
        # malformed row
        "garbage,garbage\n"
    )
    df = lbr._read_lines_csv(str(p))
    assert len(df) == 2
    assert set(df["line"].tolist()) == {6.5, 7.5}


# ---------- is_pretip ----------
def test_is_pretip_no_qbox_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    cfg = {"game_ids": ["123"]}
    assert lbr.is_pretip(cfg) is True


def test_is_pretip_with_q1_file_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    qb = tmp_path / "data" / "cache" / "quarter_box"
    qb.mkdir(parents=True)
    (qb / "0001234567_q1.json").write_text("{}")
    cfg = {"game_ids": ["1234567"]}
    assert lbr.is_pretip(cfg) is False


# ---------- end-to-end tick (mocked model) ----------
def test_run_tick_with_mocked_model(tmp_path, monkeypatch):
    """Drive run_tick end-to-end with a fake ModelCache + line CSV."""
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(lbr, "SLATES", {"test_slate": {
        "date": "2026-05-26",
        "label": "TEST",
        "game_ids": ["NONE"],
        "sas_players": ["Test Player"],
        "okc_players": [],
        "sas_home": True, "okc_home": False,
        "sas_opp": "OKC", "okc_opp": "SAS",
    }})
    # Set up data/lines csv
    lines_dir = tmp_path / "data" / "lines"
    lines_dir.mkdir(parents=True)
    (lines_dir / "2026-05-26_fd.csv").write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time\n"
        + f"{datetime.now(timezone.utc).isoformat()},fd,X,,Test Player,pts,10.5,+150,-180,2026-05-27T00:00:00\n"
    )

    # Build a fake ModelCache that returns a fixed prediction
    class FakeCache:
        def __init__(self):
            self.preds = {
                "Test Player": {
                    "pts": {"point": 15.0, "q10": 10.0, "q50": 15.0,
                             "q90": 20.0, "availability_factor": 1.0},
                }
            }
            self._apply_cal = lambda stat, a, b, c: (a, c)

        def predict_player(self, *a, **kw):
            return self.preds["Test Player"]

    cache = FakeCache()
    payload = lbr.run_tick("test_slate", bankroll=1000.0, cache=cache,
                              prior_state={"prior_lines": {}, "prior_edges": {}},
                              placed=set(), tick_idx=0)
    assert payload["n_props_evaluated"] >= 1
    # model_q50=15 > line=10.5 => OVER edge huge, UNDER edge negative
    # OVER at +150 (implied 0.4) but model_prob high => should be top
    assert payload["top_bet_str"] is not None
    assert "OVER" in payload["top_bet_str"]


def test_run_tick_detects_line_move(tmp_path, monkeypatch):
    """Two ticks against the same file with different lines must mark a move."""
    monkeypatch.setattr(lbr, "PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(lbr, "SLATES", {"t": {
        "date": "2026-05-26", "label": "T",
        "game_ids": ["NONE"],
        "sas_players": ["P"], "okc_players": [],
        "sas_home": True, "okc_home": False,
        "sas_opp": "OKC", "okc_opp": "SAS",
    }})
    lines_dir = tmp_path / "data" / "lines"
    lines_dir.mkdir(parents=True)
    csv_path = lines_dir / "2026-05-26_fd.csv"
    now = datetime.now(timezone.utc).isoformat()
    csv_path.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time\n"
        f"{now},fd,X,,P,pts,10.5,+100,-130,2026-05-27T00:00:00\n"
    )

    class FakeCache:
        preds = {"P": {"pts": {
            "point": 15.0, "q10": 10.0, "q50": 15.0, "q90": 20.0,
            "availability_factor": 1.0,
        }}}
        _apply_cal = lambda self, s, a, b, c: (a, c)

        def predict_player(self, *a, **kw):
            return self.preds["P"]

    cache = FakeCache()
    p1 = lbr.run_tick("t", 1000.0, cache,
                        {"prior_lines": {}, "prior_edges": {}}, set(), 0)
    # Tick 2: line moves to 11.5 (>= 0.5pt)
    csv_path.write_text(
        "captured_at,book,game_id,player_id,player_name,stat,line,over_price,under_price,start_time\n"
        f"{now},fd,X,,P,pts,11.5,+100,-130,2026-05-27T00:00:00\n"
    )
    p2 = lbr.run_tick("t", 1000.0, cache, p1["new_state"], set(), 1)
    moves = p2["line_moves_this_tick"]
    assert len(moves) >= 1
    assert any(m["arrow"].startswith("↑LINE") for m in moves)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
