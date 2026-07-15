"""tests.platformkit.clv_grading.test_ingame_realized_clv"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.platformkit.clv_grading import ingame_realized_clv as m

T0 = 1_752_000_000.0  # arbitrary fixed epoch


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _bet(bet_id: str, game_id: str, taken_p: float, ts_epoch: float = T0,
          sport: str = "mlb") -> dict:
    return {"bet_id": bet_id, "game_id": game_id, "sport": sport, "channel": "paper_ingame",
            "ts": _iso(ts_epoch), "taken_decimal": 1.0 / taken_p}


def test_grade_row_correct_mid_at_horizons():
    snaps = {
        "GAME-AAA": [
            (T0, 0.40, 0.42),        # placement tick, mid .41 == taken_p
            (T0 + 30, 0.41, 0.43),   # +30s tick, mid .42
            (T0 + 120, 0.50, 0.52),  # +120s tick, mid .51
            (T0 + 300, 0.60, 0.62),  # +300s tick, mid .61
        ],
    }
    row = _bet("b1", "GAME", 0.41)
    out = m.grade_row(row, snaps, tier="dense", source="book_depth")
    assert out["ingame_clv_cadence_tier"] == "dense"
    assert out["ingame_clv_source"] == "book_depth"
    assert out["ingame_realized_clv_30s"] == pytest.approx(0.42 - 0.41, abs=1e-6)
    assert out["ingame_realized_clv_120s"] == pytest.approx(0.51 - 0.41, abs=1e-6)
    assert out["ingame_realized_clv_300s"] == pytest.approx(0.61 - 0.41, abs=1e-6)


def test_none_past_slack():
    snaps = {
        "GAME-AAA": [
            (T0, 0.40, 0.42),
            (T0 + 30, 0.41, 0.43),
            (T0 + 120, 0.50, 0.52),
            # no tick anywhere near T0+300 within SLACK_S=60
            (T0 + 300 + 200, 0.60, 0.62),
        ],
    }
    row = _bet("b2", "GAME", 0.41)
    out = m.grade_row(row, snaps, tier="dense", source="book_depth")
    assert out["ingame_realized_clv_30s"] is not None
    assert out["ingame_realized_clv_120s"] is not None
    assert out["ingame_realized_clv_300s"] is None
    # still gradeable overall (at least one horizon graded) -> not "insufficient"
    assert out["ingame_clv_cadence_tier"] == "dense"


def test_no_coverage_is_insufficient():
    row = _bet("b3", "GAME", 0.41)
    out = m.grade_row(row, {}, tier="dense", source="book_depth")
    assert out["ingame_clv_cadence_tier"] == "insufficient"
    assert out["ingame_clv_source"] is None
    assert all(out["ingame_realized_clv_%ds" % h] is None for h in m.HORIZONS_S)


def test_prefix_join_and_side_suffix_resolution():
    # Two candidates share the event-key prefix; taken_p=0.30 matches AAA's mid (~.30),
    # not BBB's complementary mid (~.70).
    snaps = {
        "GAME-AAA": [(T0, 0.29, 0.31), (T0 + 30, 0.35, 0.37)],
        "GAME-BBB": [(T0, 0.69, 0.71), (T0 + 30, 0.63, 0.65)],
    }
    row = _bet("b4", "GAME", 0.30)
    out = m.grade_row(row, snaps, tier="dense", source="book_depth")
    # +30s mid on AAA is .36 -> clv = .36 - .30 = .06; on BBB it would be .64-.30=.34
    assert out["ingame_realized_clv_30s"] == pytest.approx(0.06, abs=1e-6)


def _dense_rows(ticker: str, sport: str, ticks: list) -> list:
    return [{"ts": _iso(t), "ticker": ticker, "best_bid": b, "best_ask": a, "sport": sport}
            for t, b, a in ticks]


def test_backfill_sidecar_append_idempotent(tmp_path, monkeypatch):
    ledger_path = tmp_path / "clv_ledger.jsonl"
    sidecar_path = tmp_path / "ingame_realized_clv.jsonl"
    bets = [_bet("bet-a", "GAME1", 0.41), _bet("bet-b", "GAME2", 0.55)]
    with ledger_path.open("w", encoding="utf-8") as fh:
        for b in bets:
            fh.write(json.dumps(b) + "\n")

    dense_rows = (
        _dense_rows("GAME1-AAA", "mlb", [(T0, 0.40, 0.42), (T0 + 30, 0.41, 0.43)])
        + _dense_rows("GAME2-BBB", "mlb", [(T0, 0.54, 0.56), (T0 + 30, 0.50, 0.52)])
    )
    monkeypatch.setattr(m, "load_dense_rows", lambda: dense_rows)

    s1 = m.backfill(ledger_path=ledger_path, sports=("mlb",), write=True, sidecar_path=sidecar_path)
    assert s1["n_bets"] == 2
    assert s1["n_gradeable"] == 2
    lines1 = sidecar_path.read_text(encoding="utf-8").splitlines()
    assert len(lines1) == 2

    s2 = m.backfill(ledger_path=ledger_path, sports=("mlb",), write=True, sidecar_path=sidecar_path)
    assert s2["n_bets"] == 2
    lines2 = sidecar_path.read_text(encoding="utf-8").splitlines()
    assert len(lines2) == 2  # re-running never duplicates


def test_backfill_min_age_filters_recent_bets(tmp_path, monkeypatch):
    """A bet younger than min_age_s is skipped entirely (never graded, never
    written) so it gets a real second chance once its longest horizon can land
    -- write=True's bet_id dedup would otherwise lock in an incomplete row."""
    ledger_path = tmp_path / "clv_ledger.jsonl"
    sidecar_path = tmp_path / "ingame_realized_clv.jsonl"
    now = T0 + 1000.0
    old_bet = _bet("bet-old", "GAME1", 0.41, ts_epoch=T0)           # age 1000s
    new_bet = _bet("bet-new", "GAME2", 0.55, ts_epoch=T0 + 950.0)   # age 50s
    with ledger_path.open("w", encoding="utf-8") as fh:
        for b in (old_bet, new_bet):
            fh.write(json.dumps(b) + "\n")

    dense_rows = (
        _dense_rows("GAME1-AAA", "mlb", [(T0, 0.40, 0.42), (T0 + 30, 0.41, 0.43)])
        + _dense_rows("GAME2-BBB", "mlb", [(T0 + 950, 0.54, 0.56), (T0 + 980, 0.50, 0.52)])
    )
    monkeypatch.setattr(m, "load_dense_rows", lambda: dense_rows)

    out = m.backfill(ledger_path=ledger_path, sports=("mlb",), write=True,
                     sidecar_path=sidecar_path, min_age_s=300.0, now_epoch=now)
    assert out["n_bets"] == 1  # only the old-enough bet is graded at all
    lines = sidecar_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["bet_id"] == "bet-old"

    # re-running once the new bet ages past min_age_s grades + writes it too.
    out2 = m.backfill(ledger_path=ledger_path, sports=("mlb",), write=True,
                      sidecar_path=sidecar_path, min_age_s=300.0, now_epoch=now + 260.0)
    assert out2["n_bets"] == 2
    lines2 = sidecar_path.read_text(encoding="utf-8").splitlines()
    assert len(lines2) == 2


def test_summarize_math(tmp_path):
    sidecar_path = tmp_path / "ingame_realized_clv.jsonl"
    rows = [
        {"bet_id": "x1", "sport": "mlb", "ingame_realized_clv_30s": 0.10,
         "ingame_realized_clv_120s": None, "ingame_realized_clv_300s": None},
        {"bet_id": "x2", "sport": "mlb", "ingame_realized_clv_30s": -0.02,
         "ingame_realized_clv_120s": None, "ingame_realized_clv_300s": None},
    ]
    with sidecar_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    out = m.summarize(sidecar_path)
    s30 = out["mlb"]["30s"]
    assert s30["n"] == 2
    assert s30["mean_pp"] == pytest.approx((0.10 - 0.02) / 2, abs=1e-6)
    assert s30["median_pp"] == pytest.approx((0.10 + -0.02) / 2, abs=1e-6)
    assert s30["pct_favorable"] == pytest.approx(50.0, abs=1e-6)
    assert out["mlb"]["120s"]["n"] == 0
    assert out["mlb"]["120s"]["mean_pp"] is None
