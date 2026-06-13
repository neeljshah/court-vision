"""tests/platform/test_clv.py — HONEST CLV tracker math + ledger tests.

All ledger IO is routed to tmp_path so real data/ is never touched.  No
network, no slow loads.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.frontend import clv as C

_BANNED = ("guaranteed", "profit", "beat the market", "+ev edge", "lock")


# ── conversion math ───────────────────────────────────────────────────────────

def test_decimal_to_prob():
    assert C._decimal_to_prob(2.0) == pytest.approx(0.5)


def test_american_to_decimal_and_prob():
    assert C._american_to_decimal(-110) == pytest.approx(1.909, abs=1e-3)
    assert C._decimal_to_prob(C._american_to_decimal(-110)) == pytest.approx(
        0.5238, abs=1e-3
    )
    assert C._american_to_decimal(150) == pytest.approx(2.5)
    assert C._decimal_to_prob(C._american_to_decimal(150)) == pytest.approx(0.4)


# ── CLV sign convention ───────────────────────────────────────────────────────

def test_clv_positive_when_close_shorter():
    # bet 2.5 (p=0.40), close 2.2 (p≈0.4545): close prob higher => beat close.
    clv_pct, ev = C._compute_clv(2.5, 2.2, stake=10.0)
    assert clv_pct > 0
    assert ev == pytest.approx(clv_pct / 100.0 * 10.0)


def test_clv_negative_when_close_longer():
    # bet 1.5 (p≈0.667), close 1.6 (p=0.625): close prob lower => worse.
    clv_pct, _ = C._compute_clv(1.5, 1.6, stake=1.0)
    assert clv_pct < 0


def test_clv_zero_when_equal():
    clv_pct, ev = C._compute_clv(2.0, 2.0, stake=5.0)
    assert clv_pct == pytest.approx(0.0)
    assert ev == pytest.approx(0.0)


def test_clv_sign_opposite_to_record_clv_bug():
    # OVER where the LINE is unchanged (record_clv's line metric => 0, "neutral")
    # but the PRICE you got is worse than the close: you locked the shorter
    # decimal 1.77, the close drifted out to the better price 1.91.  record_clv
    # (line CLV) would call this neutral; our PRICE-CLV correctly calls it
    # NEGATIVE — the two metrics disagree, which is the whole point.
    clv_pct, _ = C._compute_clv(1.77, 1.91, stake=1.0)
    line_clv = C._line_clv("over", bet_line=210.5, close_line=210.5)
    assert clv_pct < 0       # PRICE-CLV: you took a worse price than the close
    assert line_clv == 0.0   # line CLV (record_clv-style): blind to price move


# ── ledger roundtrip ──────────────────────────────────────────────────────────

def test_append_then_load_roundtrip(tmp_path):
    pid = C.append_pick(
        "nba", "EVT1", "ml", "home", bet_odds=2.0, stake=3.0, root=tmp_path
    )
    picks = C.load_picks(root=tmp_path, sport="nba")
    assert len(picks) == 1
    p = picks[0]
    assert p.pick_id == pid
    assert p.bet_decimal == pytest.approx(2.0)
    assert p.stake == pytest.approx(3.0)
    assert p.settled is False
    # ledger lives under the gitignored local clv dir, not data/registry.
    led = tmp_path / "data" / "domains" / "nba" / "clv" / "picks.jsonl"
    assert led.exists()


def test_settle_pick_computes_clv(tmp_path):
    pid = C.append_pick(
        "nba", "EVT2", "ml", "home", bet_odds=2.5, stake=10.0, root=tmp_path
    )
    settled = C.settle_pick(pid, close_odds=2.2, root=tmp_path, sport="nba")
    assert settled.settled is True
    assert settled.clv_pct is not None and settled.clv_pct > 0
    # load collapses pick + settle rows down to ONE settled pick.
    picks = C.load_picks(root=tmp_path, sport="nba")
    assert len(picks) == 1
    assert picks[0].settled is True
    assert picks[0].clv_pct == pytest.approx(settled.clv_pct)


def test_novig_close_uses_stripped_prob(tmp_path):
    # With an opposite-side close, the headline prob is the no-vig prob.
    raw_clv, _ = C._compute_clv(2.0, 2.0, stake=1.0)
    novig_clv, _ = C._compute_clv(2.0, 2.0, stake=1.0, close_dec_other=2.0)
    # both sides 2.0 -> no-vig prob 0.5 == bet prob -> still zero, but the
    # stripping path runs.  Now make the other side juicier so devig lowers
    # the side's stripped prob below the bet prob.
    devig_clv, _ = C._compute_clv(2.0, 2.0, stake=1.0, close_dec_other=1.5)
    assert raw_clv == pytest.approx(0.0)
    assert novig_clv == pytest.approx(0.0)
    assert devig_clv < 0  # stripped side prob < 0.5


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_empty_is_safe(tmp_path):
    s = C.clv_summary(root=tmp_path)
    assert s["n_settled"] == 0
    assert s["mean_clv_pct"] == 0.0
    assert s["median_clv_pct"] == 0.0
    assert s["pct_positive"] == 0.0
    assert s["total_ev_delta_usd"] == 0.0
    assert s["by_sport"] == {}
    assert s["by_market"] == {}
    dist = s["clv_pct_distribution"]
    for k in ("p10", "p25", "p50", "p75", "p90", "min", "max", "std"):
        assert dist[k] == 0.0
    assert s["honest_note"]


def test_summary_aggregates_and_beat_rate(tmp_path):
    # 4 picks across 2 sports: 3 positive CLV, 1 negative.
    specs = [
        ("nba", "E1", "ml", 2.5, 2.2),   # positive
        ("nba", "E2", "spread", 2.0, 1.8),  # positive
        ("soccer", "E3", "ou", 3.0, 2.5),  # positive
        ("soccer", "E4", "ml", 1.5, 1.7),  # negative
    ]
    for sport, evt, mkt, bet, close in specs:
        pid = C.append_pick(sport, evt, mkt, "home", bet_odds=bet, root=tmp_path)
        C.settle_pick(pid, close_odds=close, root=tmp_path, sport=sport)
    s = C.clv_summary(root=tmp_path)
    assert s["n_settled"] == 4
    assert s["pct_positive"] == pytest.approx(0.75)
    assert set(s["by_sport"].keys()) == {"nba", "soccer"}
    assert set(s["by_market"].keys()) == {"ml", "spread", "ou"}
    assert s["by_sport"]["nba"]["n"] == 2
    assert math.isfinite(s["mean_clv_pct"])


def test_no_banned_words(tmp_path):
    blob = json.dumps(C.clv_summary(root=tmp_path)).lower()
    for w in _BANNED:
        assert w not in blob, f"banned substring {w!r} leaked into summary"
