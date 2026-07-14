"""Per-file test for LIVE-EDGE D1 shadow conditioner + ledger + grader.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_shadow.py -q
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

from scripts.platformkit.live_edge.shadow import conditioner as cnd
from scripts.platformkit.live_edge.shadow import shadow_ledger as sl
from scripts.platformkit.omni import close_lookup as cl

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_STORE = _REPO_ROOT / "data" / "cache" / "inplay_odds" / "nba_price_series.parquet"


def _moneyline_payload(prob=0.6):
    return {
        "away": "Boston Celtics", "book": "kalshi", "captured_at": "2026-04-26T18:00:00+00:00",
        "commence_time": "2026-04-27T00:00:00Z", "devigged_prob": prob, "game_id": "KXNBAGAME-26APR26BOSPHI",
        "home": "Philadelphia 76ers", "line": None, "market_type": "moneyline", "odds": None,
        "side": "home", "sport": "nba",
    }


def test_condition_tick_no_active_mechanism_is_noop():
    """C1 is registered but INACTIVE today -- moneyline ticks pass through unchanged."""
    out = cnd.condition_tick(_moneyline_payload(0.62))
    assert out["market_family"] == "pregame.moneyline"
    assert out["unconditioned_pred"] == pytest.approx(0.62)
    assert out["conditioned_pred"] == pytest.approx(0.62)
    assert out["mechanism_applied"] is None


def test_condition_tick_active_mechanism_overlays_and_clips():
    """Prove the registry plumbing: an ACTIVE mechanism on a matching family
    overlays and a probability family clips to [0, 1]."""
    fake_registry = [{
        "name": "fake_mech", "market_family": "pregame.moneyline",
        "active": True, "apply": lambda state: 0.5,
    }]
    out = cnd.condition_tick(_moneyline_payload(0.62), registry=fake_registry)
    assert out["mechanism_applied"] == "fake_mech"
    assert out["conditioned_pred"] == pytest.approx(1.0)  # 0.62+0.5=1.12 clipped
    assert out["unconditioned_pred"] == pytest.approx(0.62)  # unconditioned untouched


def test_condition_tick_non_prob_family_not_clipped():
    payload = {"devigged_prob": 30.0, "market_type": "minutes_prop"}
    fake_registry = [{
        "name": "big_adj", "market_family": "other.minutes_prop",
        "active": True, "apply": lambda state: 5.0,
    }]
    out = cnd.condition_tick(payload, registry=fake_registry)
    assert out["conditioned_pred"] == pytest.approx(35.0)  # not clipped -- not a prob family


def test_shadow_row_roundtrip(tmp_path):
    row = sl.make_shadow_row(
        ts="2026-04-26T18:00:00+00:00", sport="nba", game="PHI@BOS:2026-04-26",
        market="pregame.moneyline", book="kalshi",
        unconditioned_pred=0.29, conditioned_pred=0.29, market_price=0.29,
    )
    assert row["edge_claimed"] is False
    assert row["is_clv_suspect"] is None
    sl.append_shadow_row(row, shadow_dir=tmp_path)
    out_path = sl.shadow_path("2026-04-26", shadow_dir=tmp_path)
    assert out_path.is_file()
    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["game"] == "PHI@BOS:2026-04-26"


def test_grade_row_same_book_vs_cross_venue():
    row = sl.make_shadow_row(
        ts="2026-04-26T18:00:00+00:00", sport="nba", game="PHI@BOS:2026-04-26",
        market="pregame.moneyline", book="kalshi",
        unconditioned_pred=0.29, conditioned_pred=0.34, market_price=0.29,
    )
    close = {"prob_home_devig": 0.27, "source": "kalshi", "ts": 1777161420}
    graded = sl.grade_row(row, close)
    assert graded["is_clv_suspect"] is False  # same book as close source
    assert graded["edge_claimed"] is False
    # close < market_price -> market_move negative -> sign=-1
    assert graded["unconditioned_clv_units"] == pytest.approx((0.29 - 0.29) * -1.0)
    assert graded["conditioned_clv_units"] == pytest.approx((0.34 - 0.29) * -1.0)
    assert graded["unconditioned_sq_err_vs_close"] == pytest.approx((0.29 - 0.27) ** 2)

    cross_row = dict(row, book="fanduel")
    graded_cross = sl.grade_row(cross_row, close)
    assert graded_cross["is_clv_suspect"] is True  # fanduel row, kalshi close


@pytest.mark.skipif(not _STORE.is_file(), reason="inplay_odds nba store not present")
def test_replay_historical_tick_end_to_end(tmp_path):
    """REPLAY a REAL historical bus-shaped tick (not live): an early captured
    kalshi price for Philadelphia 76ers (home) vs Boston Celtics on
    2026-04-26, well before the close close_lookup resolves for that game.
    Proves the schema + grading math on real disk data end-to-end."""
    df = pd.read_parquet(_STORE)
    grp = df[(df["venue"] == "kalshi") & (df["market_type"] == "moneyline")
             & (df["event_key"] == "KXNBAGAME-26APR26BOSPHI")].sort_values("ts")
    assert not grp.empty
    early_ts = grp["ts"].min()
    phi = grp[(grp["ts"] == early_ts) & (grp["side"] == "PHI")]["prob"].iloc[0]
    bos = grp[(grp["ts"] == early_ts) & (grp["side"] == "BOS")]["prob"].iloc[0]
    early_home_devig = float(phi) / (float(phi) + float(bos))

    payload = _moneyline_payload(prob=early_home_devig)
    surfaces = cnd.condition_tick(payload)
    assert surfaces["mechanism_applied"] is None  # C1 inactive -- honest, no fake edge

    row = sl.make_shadow_row(
        ts="2026-04-26T18:00:00+00:00", sport="nba", game=payload["game_id"], market=surfaces["market_family"],
        book=payload["book"], unconditioned_pred=surfaces["unconditioned_pred"],
        conditioned_pred=surfaces["conditioned_pred"], market_price=payload["devigged_prob"],
        mechanism_applied=surfaces["mechanism_applied"],
    )
    sl.append_shadow_row(row, date="2026-04-26", shadow_dir=tmp_path)

    close = cl.pregame_close("nba", "2026-04-26", payload["home"], payload["away"])
    assert close is not None  # real close resolves from the real store
    graded = sl.grade_row(row, close)
    assert graded["close_source"] == "kalshi"
    assert graded["is_clv_suspect"] is False  # kalshi row, kalshi close
    assert graded["edge_claimed"] is False
    assert graded["unconditioned_clv_units"] == graded["conditioned_clv_units"]  # C1 inactive -> identical
