"""tests/test_bankroll_dashboard_filter.py — R19_L8.

Verifies the synthetic-row filter for the bankroll monitor + mobile HTML
dashboard. Builds a synthetic-vs-real fixture, asserts that:

* ``is_synthetic_row`` classifies single rows correctly.
* ``filter_ledger`` excludes synthetic + pre-date rows.
* ``compute_roi`` runs only on the filtered subset.
* ``tick`` writes ``filter_info`` + ``roi`` keys into the state JSON.
* ``render_filter_banner`` in mobile_html_server emits the banner when
  filter_info is present and an empty string when it is absent.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bankroll_monitor_daemon import (  # noqa: E402
    compute_roi,
    filter_ledger,
    is_synthetic_row,
    tick,
)
from mobile_html_server import render_filter_banner  # noqa: E402


NOW = datetime(2026, 5, 26, 18, 0, 0, tzinfo=timezone.utc)


def _row(**kw):
    base = dict(
        bet_id="x", placed_at=NOW.isoformat(), game_id="g1", player_id=1,
        player="Real Player", team="SAS", stat="pts", line=10.0, side="OVER",
        book="pin", american_odds=-110, stake=10.0, model_pred=11.0,
        model_prob=0.55, model_edge=0.05, kelly_pct=0.02,
        status="won", settled_at=NOW.isoformat(), actual_stat=12.0,
        profit_loss=9.09, bankroll_after=1009.09, strategy="default",
    )
    base.update(kw)
    return base


def _mixed_df():
    """3 synthetic rows + 2 real rows + 1 boundary row."""
    rows = [
        # Synthetic: player matches Player_N + book PP
        _row(bet_id="s1", player="Player_1", book="PP", profit_loss=10.0,
             status="won", placed_at="2024-01-01T00:00:00+00:00"),
        _row(bet_id="s2", player="Player_22", book="PP", profit_loss=-50.0,
             status="lost", placed_at="2024-06-15T00:00:00+00:00"),
        _row(bet_id="s3", player="Player_333", book="PP", profit_loss=45.45,
             status="won", placed_at="2025-04-30T00:00:00+00:00"),
        # Real
        _row(bet_id="r1", player="Nikola Jokic", book="pin", profit_loss=42.02,
             stake=50.0, status="won", placed_at="2026-05-26T12:00:00+00:00"),
        _row(bet_id="r2", player="Keldon Johnson", book="pin", profit_loss=-50.0,
             stake=50.0, status="lost", placed_at="2026-05-26T13:00:00+00:00"),
        # Boundary: "Player_5" but real book ('fd') -> NOT synthetic
        _row(bet_id="b1", player="Player_5", book="fd", profit_loss=20.0,
             stake=50.0, status="won", placed_at="2026-05-26T14:00:00+00:00"),
    ]
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# is_synthetic_row                                                            #
# --------------------------------------------------------------------------- #
def test_is_synthetic_row_classification():
    syn = pd.Series({"player": "Player_42", "book": "PP"})
    real = pd.Series({"player": "Nikola Jokic", "book": "pin"})
    boundary = pd.Series({"player": "Player_5", "book": "fd"})
    real_pp = pd.Series({"player": "LeBron James", "book": "PP"})
    assert is_synthetic_row(syn) is True
    assert is_synthetic_row(real) is False
    assert is_synthetic_row(boundary) is False  # PP book required
    assert is_synthetic_row(real_pp) is False   # real player name


# --------------------------------------------------------------------------- #
# filter_ledger                                                               #
# --------------------------------------------------------------------------- #
def test_filter_ledger_exclude_synthetic_only():
    df = _mixed_df()
    res = filter_ledger(df, exclude_synthetic=True, start_date=None)
    assert res["n_total"] == 6
    assert res["n_synth_excluded"] == 3
    assert res["n_date_excluded"] == 0
    assert res["n_kept"] == 3
    bet_ids = set(res["filtered"]["bet_id"])
    assert bet_ids == {"r1", "r2", "b1"}


def test_filter_ledger_start_date_only():
    df = _mixed_df()
    res = filter_ledger(df, exclude_synthetic=False, start_date="2026-05-25")
    # Only the 3 rows on 2026-05-26 survive the date cut.
    assert res["n_date_excluded"] == 3
    assert res["n_kept"] == 3
    bet_ids = set(res["filtered"]["bet_id"])
    assert bet_ids == {"r1", "r2", "b1"}


def test_filter_ledger_combined():
    df = _mixed_df()
    res = filter_ledger(df, exclude_synthetic=True, start_date="2026-05-25")
    assert res["n_synth_excluded"] == 3
    # After dropping 3 synth, only 3 rows remain — none pre-date.
    assert res["n_date_excluded"] == 0
    assert res["n_kept"] == 3


def test_filter_ledger_empty_df():
    res = filter_ledger(pd.DataFrame(), exclude_synthetic=True, start_date="2026-05-25")
    assert res["n_kept"] == 0
    assert res["n_total"] == 0


def test_filter_ledger_no_filters_noop():
    df = _mixed_df()
    res = filter_ledger(df, exclude_synthetic=False, start_date=None)
    assert res["n_kept"] == 6
    assert res["n_synth_excluded"] == 0
    assert res["n_date_excluded"] == 0


# --------------------------------------------------------------------------- #
# compute_roi                                                                 #
# --------------------------------------------------------------------------- #
def test_compute_roi_real_subset_only():
    df = _mixed_df()
    filtered = filter_ledger(df, exclude_synthetic=True, start_date=None)["filtered"]
    roi = compute_roi(filtered)
    # r1: +42.02 won (stake 50), r2: -50.00 lost (stake 50), b1: +20.0 won (stake 50)
    assert roi["n_bets"] == 3
    assert roi["total_stake"] == pytest.approx(150.0)
    assert roi["total_pnl"] == pytest.approx(12.02)
    assert roi["roi_pct"] == pytest.approx(12.02 / 150.0 * 100.0, rel=1e-3)


def test_compute_roi_unfiltered_dominated_by_synthetic():
    df = _mixed_df()
    roi_all = compute_roi(df)
    # synth pnl: 10 + -50 + 45.45 = 5.45; real pnl: 12.02 -> total 17.47 on 220 stake
    assert roi_all["n_bets"] == 6
    assert roi_all["total_pnl"] == pytest.approx(17.47, abs=0.01)


def test_compute_roi_empty():
    roi = compute_roi(pd.DataFrame())
    assert roi == {"n_bets": 0, "total_stake": 0.0, "total_pnl": 0.0, "roi_pct": 0.0}


# --------------------------------------------------------------------------- #
# tick() writes filter_info + roi into state                                  #
# --------------------------------------------------------------------------- #
def test_tick_writes_filter_info_and_roi(tmp_path: Path):
    ledger_path = tmp_path / "ledger.csv"
    state_path = tmp_path / "state.json"
    dash_path = tmp_path / "dash.md"
    alerts_path = tmp_path / "alerts.md"

    _mixed_df().to_csv(ledger_path, index=False)

    metrics = tick(
        start_bankroll=1000.0,
        ledger_path=ledger_path,
        state_path=state_path,
        dashboard_path=dash_path,
        alerts_path=alerts_path,
        exclude_synthetic=True,
        start_date="2026-05-25",
    )
    assert "filter_info" in metrics
    assert metrics["filter_info"]["n_synth_excluded"] == 3
    assert metrics["filter_info"]["n_kept"] == 3
    assert "roi" in metrics
    assert metrics["roi"]["n_bets"] == 3

    blob = json.loads(state_path.read_text(encoding="utf-8"))
    assert blob["filter_info"]["exclude_synthetic"] is True
    assert blob["filter_info"]["start_date"] == "2026-05-25"
    assert blob["roi"]["roi_pct"] == pytest.approx(
        metrics["roi"]["roi_pct"], rel=1e-6
    )

    # Current bankroll reflects ONLY the filtered subset.
    expected_current = 1000.0 + 12.02
    assert metrics["current_bankroll"] == pytest.approx(expected_current, abs=0.01)


def test_tick_unfiltered_pollutes_bankroll(tmp_path: Path):
    """Sanity check the BUG we're fixing: without filter, synth dominates."""
    ledger_path = tmp_path / "ledger.csv"
    state_path = tmp_path / "state.json"
    dash_path = tmp_path / "dash.md"
    alerts_path = tmp_path / "alerts.md"
    _mixed_df().to_csv(ledger_path, index=False)

    m = tick(
        start_bankroll=1000.0, ledger_path=ledger_path,
        state_path=state_path, dashboard_path=dash_path,
        alerts_path=alerts_path,
        exclude_synthetic=False, start_date=None,
    )
    # All 6 rows count -> bankroll = 1000 + (10 - 50 + 45.45) + (42.02 - 50 + 20)
    expected = 1000.0 + 5.45 + 12.02
    assert m["current_bankroll"] == pytest.approx(expected, abs=0.01)
    assert m["filter_info"]["n_synth_excluded"] == 0


# --------------------------------------------------------------------------- #
# render_filter_banner                                                        #
# --------------------------------------------------------------------------- #
def test_render_filter_banner_with_filter():
    state = {
        "filter_info": {
            "exclude_synthetic": True,
            "start_date": "2026-05-25",
            "n_synth_excluded": 335139,
            "n_date_excluded": 0,
            "n_kept": 2,
            "n_total": 335141,
        }
    }
    html = render_filter_banner(state)
    assert "335,139 synthetic rows" in html
    assert "showing 2 of 335,141" in html
    assert "R19_L8" in html


def test_render_filter_banner_without_filter():
    # No filter applied -> empty string (do not clutter the page).
    state = {
        "filter_info": {
            "exclude_synthetic": False,
            "start_date": None,
            "n_synth_excluded": 0,
            "n_date_excluded": 0,
            "n_kept": 100,
            "n_total": 100,
        }
    }
    assert render_filter_banner(state) == ""


def test_render_filter_banner_no_state():
    assert render_filter_banner(None) == ""
    assert render_filter_banner({}) == ""
