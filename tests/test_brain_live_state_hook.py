"""P3.1/P3.2/P3.4 — the live wiring seam (src/ingame/live_state_hook.py).

Proves the load-bearing discipline at the SEAM:
  - apply_ingame_state with the default identity trust curve LEAVES every row UNTOUCHED (byte-identical);
  - with a trust_override it re-prices toward the frozen prior and stamps +bayes;
  - apply_universal_winprob FAILS CLOSED before Q4 / off mc_full (advisory None, served WP untouched) and
    ROUTES the projected-final win-prob into the served field only when eligible (Q4 + mc_full).
These are pure functions tested WITHOUT loading any heavy model (the extractable seam).
"""
import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from ingame.live_state_hook import (  # noqa: E402
    apply_ingame_state, apply_universal_winprob, remaining_min_from, _margin_bucket,
)


def _snap(period=4, clock="06:00"):
    return {
        "game_id": "0022500001", "home_team": "NYK", "away_team": "SAS",
        "period": period, "clock": clock, "home_score": 60, "away_score": 55,
        "players": [
            {"player_id": 1, "team": "home", "on_court": True, "min_so_far": 30.0, "pf": 2},
            {"player_id": 2, "team": "away", "on_court": True, "min_so_far": 28.0, "pf": 3},
        ],
    }


def _rows():
    return [
        {"player_id": 1, "team": "NYK", "stat": "pts", "current": 18.0, "projected_final": 25.0,
         "projection_source": "cycle_88_linear"},
        {"player_id": 1, "team": "NYK", "stat": "reb", "current": 4.0, "projected_final": 6.0,
         "projection_source": "cycle_88_linear"},
        {"player_id": 2, "team": "SAS", "stat": "pts", "current": 12.0, "projected_final": 20.0,
         "projection_source": "cycle_88_linear"},
    ]


# --------------------------------------------------------------------------- helpers

def test_remaining_min_from_share():
    # 30 of 42 elapsed min (share 0.714) of 6 remaining game min -> ~4.29
    assert abs(remaining_min_from(30.0, 2520.0, 360.0) - (6.0 * (30.0 / 42.0))) < 1e-9
    # tip-off: no pace yet -> full remaining
    assert remaining_min_from(0.0, 0.0, 2880.0) == 48.0
    # share clamped to 1.0 (cannot play more than wall-clock)
    assert remaining_min_from(100.0, 2520.0, 360.0) == 6.0


def test_margin_bucket():
    assert _margin_bucket(0) == 0 and _margin_bucket(5) == 0
    assert _margin_bucket(6) == 1 and _margin_bucket(12) == 1
    assert _margin_bucket(13) == 2 and _margin_bucket(-30) == 2


# --------------------------------------------------------------------------- apply_ingame_state

def test_identity_curve_leaves_rows_byte_identical():
    rows = _rows()
    before = copy.deepcopy(rows)
    out = apply_ingame_state(_snap(), rows)  # default identity trust curve -> trust_w == 0 everywhere
    assert out == before  # every row dict untouched (byte-identical to the OFF path)


def test_trust_override_reprices_toward_prior_and_stamps_bayes():
    rows = _rows()
    out = apply_ingame_state(_snap(), rows, trust_override=0.5)
    pts_row = [r for r in out if r["player_id"] == 1 and r["stat"] == "pts"][0]
    # prior 25, current 18 -> posterior pulled between current and prior, strictly changed
    assert pts_row["projected_final"] != 25.0
    assert 18.0 <= pts_row["projected_final"] < 25.0
    assert "+bayes" in pts_row["projection_source"]


def test_apply_ingame_state_never_raises_on_garbage():
    # malformed snapshot / rows must fall through to the unchanged rows, never raise
    out = apply_ingame_state({"garbage": True}, [{"stat": "pts", "projected_final": None}])
    assert isinstance(out, list)


def test_non_counting_stat_rows_untouched_even_with_trust():
    rows = [{"player_id": 1, "team": "NYK", "stat": "min", "current": 30.0, "projected_final": 36.0}]
    before = copy.deepcopy(rows)
    out = apply_ingame_state(_snap(), rows, trust_override=0.9)
    assert out == before  # "min" is not one of the 7 counting stats -> skipped


# --------------------------------------------------------------------------- apply_universal_winprob

def test_universal_wp_fails_closed_before_q4():
    rows = _rows()
    for r in rows:
        r["home_win_prob_inplay"] = 0.61  # pretend the existing stack already served this
    out = apply_universal_winprob(_snap(period=2, clock="06:00"), rows, coverage_class="mc_full")
    for r in out:
        assert r["universal_home_win_prob"] is None        # advisory: not eligible
        assert r["home_win_prob_inplay"] == 0.61            # served WP left UNTOUCHED (fail-closed)
        assert r.get("winprob_source") != "universal_projection"


def test_universal_wp_fails_closed_off_mc_coverage():
    rows = _rows()
    for r in rows:
        r["home_win_prob_inplay"] = 0.61
    out = apply_universal_winprob(_snap(period=4), rows, coverage_class="league_min")
    for r in out:
        assert r["universal_home_win_prob"] is None
        assert r["home_win_prob_inplay"] == 0.61


def test_universal_wp_routes_when_eligible_q4_mc_full():
    rows = _rows()
    for r in rows:
        r["home_win_prob_inplay"] = 0.50
    # home pts proj 25 vs away 20 -> projected margin +5, Q4, mc_full -> eligible, home favoured
    out = apply_universal_winprob(_snap(period=4, clock="06:00"), rows, coverage_class="mc_full")
    for r in out:
        assert r["universal_home_win_prob"] is not None and r["universal_home_win_prob"] > 0.5
        assert r["home_win_prob_inplay"] == r["universal_home_win_prob"]
        assert r["winprob_source"] == "universal_projection"


def test_universal_wp_never_uses_raw_margin():
    # raw live margin is +5 (60-55) but home pts projection (25) only barely leads away (20);
    # the served wp must come from the PROJECTED margin, not the raw scoreboard margin.
    rows = _rows()
    out = apply_universal_winprob(_snap(period=4, clock="00:30"), rows, coverage_class="mc_full")
    # at 30s remaining the band is tight; a +5 projected margin -> near-certain home win
    wp = out[0]["universal_home_win_prob"]
    assert wp is not None and wp > 0.9
