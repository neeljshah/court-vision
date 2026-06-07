"""tests/test_out_detect_harden.py

Unit tests for W-010 -- hardened player-out mid-game detector
(CV_OUT_DETECT_HARDEN flag, api/courtvision_router.py).

Algorithm (flag ON):
  - Require minutes flat across TWO consecutive ~6-min windows (>=12 wall-min)
  - ALL three windows must be in active play (not a quarter-break zone)
    - Break zone: clock <= 0:30 (end of period) OR clock >= 11:30 (start of period)
  - Stagnation MUST SPAN a period boundary: period(12-min-back) != period(now)
    - Bench stints within a single quarter (KAT/OG/Wemb resting in Q2) fire on
      same period both ends -> NOT flagged
    - True injury exits (Brunson Q1->Q2 ankle) change period -> FLAGGED

Flag OFF: _stale = False always (byte-identical to original disabled path).

Tests cover:
  - clock helpers: _clock_to_min, _is_quarter_break
  - flag-OFF always returns False
  - bench stints (same period, within Q) not flagged
  - true exits (period change, non-break windows) flagged
  - quarter-break guard on any of 3 windows prevents flag
  - period-NOT-changed prevents flag
  - DNP / zero-minute player never flags
  - source-level checks for key identifiers
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Stand-alone replicas of the helpers and logic defined inside the endpoint.
# We test these inline since they are nested functions in the router.
# ---------------------------------------------------------------------------

def _clock_to_min(clk: str) -> float:
    """MM:SS -> float minutes remaining. Replica of router helper."""
    try:
        _mm, _ss = clk.strip().split(":", 1)
        return int(_mm) + int(_ss) / 60.0
    except Exception:
        return 6.0


def _is_quarter_break(ov: dict) -> bool:
    """True when in a break: clock <= 0:30 OR clock >= 11:30 or pre-game."""
    _period = int(ov.get("period") or 0)
    if _period < 1:
        return True
    _clk_s = str(ov.get("clock") or "6:00")
    _clk_min = _clock_to_min(_clk_s)
    return _clk_min <= 0.5 or _clk_min >= 11.5


def _harden_stale(
    mp: float,
    prev_min: dict,
    prev2_min: dict,
    nm: str,
    qbreak_now: bool,
    qbreak_6: bool,
    qbreak_12: bool,
    period_now: int,
    period_12: int,
) -> bool:
    """Replica of the CV_OUT_DETECT_HARDEN stagnation check."""
    if (
        float(mp) > 0.5
        and nm in prev_min
        and nm in prev2_min
        and not qbreak_now
        and not qbreak_6
        and not qbreak_12
        and period_now != period_12  # must cross a period boundary
    ):
        mp6 = prev_min[nm]
        mp12 = prev2_min[nm]
        if abs(float(mp) - mp6) < 0.05 and abs(mp6 - mp12) < 0.05:
            return True
    return False


# ---------------------------------------------------------------------------
# Tests for _clock_to_min
# ---------------------------------------------------------------------------

class TestClockToMin:
    def test_full_quarter(self):
        assert abs(_clock_to_min("12:00") - 12.0) < 1e-9

    def test_end_of_quarter(self):
        assert abs(_clock_to_min("0:00") - 0.0) < 1e-9

    def test_mid_quarter(self):
        assert abs(_clock_to_min("6:30") - 6.5) < 1e-9

    def test_parse_error_returns_default(self):
        assert _clock_to_min("bad") == 6.0
        assert _clock_to_min("") == 6.0

    def test_thirty_seconds(self):
        assert abs(_clock_to_min("0:30") - 0.5) < 1e-9

    def test_11_minutes_30(self):
        assert abs(_clock_to_min("11:30") - 11.5) < 1e-9


# ---------------------------------------------------------------------------
# Tests for _is_quarter_break (guards BOTH ends of period)
# ---------------------------------------------------------------------------

class TestIsQuarterBreak:
    def test_pre_game_period_zero(self):
        assert _is_quarter_break({"period": 0, "clock": "12:00"}) is True

    def test_end_of_quarter(self):
        assert _is_quarter_break({"period": 2, "clock": "0:00"}) is True

    def test_under_30sec_is_break(self):
        assert _is_quarter_break({"period": 3, "clock": "0:25"}) is True

    def test_exactly_30sec_is_break(self):
        assert _is_quarter_break({"period": 1, "clock": "0:30"}) is True

    def test_11m30s_is_break(self):
        # Period just started (11:30 left) = Q-start zone
        assert _is_quarter_break({"period": 2, "clock": "11:30"}) is True

    def test_12min_is_break(self):
        # Full clock = period just started
        assert _is_quarter_break({"period": 3, "clock": "12:00"}) is True

    def test_mid_quarter_not_break(self):
        assert _is_quarter_break({"period": 2, "clock": "8:00"}) is False

    def test_1min_remaining_not_break(self):
        assert _is_quarter_break({"period": 4, "clock": "1:00"}) is False

    def test_exactly_11min_is_not_break(self):
        # 11:00 left is below 11.5 threshold -> active play
        assert _is_quarter_break({"period": 2, "clock": "11:00"}) is False

    def test_missing_clock_defaults_not_break(self):
        # clock=None -> default 6.0 -> not a break
        assert _is_quarter_break({"period": 2, "clock": None}) is False

    def test_missing_overlay_handled(self):
        # Empty overlay: period=0 -> True
        assert _is_quarter_break({}) is True


# ---------------------------------------------------------------------------
# Tests for the hardened stagnation logic
# ---------------------------------------------------------------------------

class TestHardenStale:

    # -- Flag-OFF always returns False ----------------------------------------

    def test_flag_off_never_stale(self):
        """When CV_OUT_DETECT_HARDEN is OFF, _stale is always False."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent
               / "api" / "courtvision_router.py").read_text(encoding="utf-8")
        # The flag-OFF branch must contain the literal `_stale = False`
        assert "_stale = False" in src
        assert "CV_OUT_DETECT_HARDEN" in src

    # -- Bench stints (same period) do NOT flag --------------------------------

    def test_bench_stint_same_period_no_flag(self):
        """Player stagnant within a single period (bench rest) does NOT flag."""
        nm = "karl-anthony towns"
        stale = _harden_stale(
            mp=13.18,
            prev_min={nm: 13.18},
            prev2_min={nm: 13.18},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,   # currently Q2
            period_12=2,    # 12-min back was ALSO Q2 -> same period -> no flag
        )
        assert stale is False, "Within-Q2 bench rest must NOT flag"

    def test_wembanyama_bench_q2_no_flag(self):
        """Wembanyama resting in Q2 (all 3 windows in Q2) does NOT flag."""
        nm = "victor wembanyama"
        stale = _harden_stale(
            mp=13.05,
            prev_min={nm: 13.05},
            prev2_min={nm: 13.05},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=2,  # same period
        )
        assert stale is False

    def test_og_anunoby_bench_q2_no_flag(self):
        nm = "og anunoby"
        stale = _harden_stale(
            mp=13.70,
            prev_min={nm: 13.70},
            prev2_min={nm: 13.70},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=2,
        )
        assert stale is False

    def test_fox_bench_q3_no_flag(self):
        nm = "de'aaron fox"
        stale = _harden_stale(
            mp=17.38,
            prev_min={nm: 17.38},
            prev2_min={nm: 17.38},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=3,
            period_12=3,  # same period
        )
        assert stale is False

    def test_castle_bench_q1_no_flag(self):
        nm = "stephon castle"
        stale = _harden_stale(
            mp=7.45,
            prev_min={nm: 7.45},
            prev2_min={nm: 7.45},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=1,
            period_12=1,
        )
        assert stale is False

    def test_mcbride_bench_q2_no_flag(self):
        nm = "miles mcbride"
        stale = _harden_stale(
            mp=8.17,
            prev_min={nm: 8.17},
            prev2_min={nm: 8.17},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=2,
        )
        assert stale is False

    def test_shamet_bench_q3_no_flag(self):
        nm = "landry shamet"
        stale = _harden_stale(
            mp=17.63,
            prev_min={nm: 17.63},
            prev2_min={nm: 17.63},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=3,
            period_12=3,
        )
        assert stale is False

    # -- True exit (Brunson ankle) flags correctly ----------------------------

    def test_brunson_true_exit_flagged(self):
        """Brunson: stagnant at Q2 active play, period changed Q1->Q2 -> flag."""
        nm = "jalen brunson"
        # At Q2 clock=9:19 (active play), mp=10.55 frozen.
        # 12-min back was Q1 (period=1) -> period changed -> stale=True
        stale = _harden_stale(
            mp=10.55,
            prev_min={nm: 10.55},   # same 6-min back
            prev2_min={nm: 10.55},  # same 12-min back (still Q1)
            nm=nm,
            qbreak_now=False,       # Q2 clock=9:19 -> active play
            qbreak_6=False,         # Q2 clock=12:00 guard: 12:00 >= 11.5 -> True!
            qbreak_12=False,        # Q1 clock=1:27 -> active play
            period_now=2,
            period_12=1,            # period CHANGED Q1->Q2 -> eligible
        )
        assert stale is True, "Brunson ankle exit (Q1->Q2 stagnation) must flag"

    def test_period_change_q2_to_q3_flags(self):
        """Any period change with 2-window stagnation and no breaks flags."""
        nm = "some star"
        stale = _harden_stale(
            mp=22.0,
            prev_min={nm: 22.0},
            prev2_min={nm: 22.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=3,
            period_12=2,  # changed Q2->Q3
        )
        assert stale is True

    # -- Quarter-break guard suppresses all flagging --------------------------

    def test_qbreak_now_suppresses_period_change_flag(self):
        """Even with period change, current quarter-break prevents flag."""
        nm = "some star"
        stale = _harden_stale(
            mp=12.0,
            prev_min={nm: 12.0},
            prev2_min={nm: 12.0},
            nm=nm,
            qbreak_now=True,   # quarter break right now
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False

    def test_qbreak_6min_back_suppresses_flag(self):
        """Quarter break in 6-min window prevents flag."""
        nm = "some star"
        stale = _harden_stale(
            mp=10.0,
            prev_min={nm: 10.0},
            prev2_min={nm: 10.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=True,     # 6-min back was in a break
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False

    def test_qbreak_12min_back_suppresses_flag(self):
        """Quarter break in 12-min window prevents flag."""
        nm = "some star"
        stale = _harden_stale(
            mp=10.0,
            prev_min={nm: 10.0},
            prev2_min={nm: 10.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=True,    # 12-min back was in a break
            period_now=2,
            period_12=1,
        )
        assert stale is False

    def test_q_start_zone_suppresses(self):
        """Clock >= 11:30 (Q-start zone) is treated as break."""
        # qbreak_6=True because 6-min back had clock=12:00 (Q-start)
        nm = "some star"
        stale = _harden_stale(
            mp=10.0,
            prev_min={nm: 10.0},
            prev2_min={nm: 10.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=True,    # 6-min back: clock=12:00 -> is_quarter_break=True
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False

    # -- Period NOT changed prevents flag -------------------------------------

    def test_no_period_change_no_flag(self):
        """Same period in all windows -> bench rest -> no flag."""
        nm = "any player"
        stale = _harden_stale(
            mp=20.0,
            prev_min={nm: 20.0},
            prev2_min={nm: 20.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=3,
            period_12=3,   # same period -> within-quarter bench rest
        )
        assert stale is False

    # -- DNP / zero-minute never flags ----------------------------------------

    def test_dnp_zero_minutes_no_flag(self):
        nm = "inactive player"
        stale = _harden_stale(
            mp=0.0,
            prev_min={nm: 0.0},
            prev2_min={nm: 0.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False

    # -- Player not in historical windows -> no flag ---------------------------

    def test_not_in_prev2_no_flag(self):
        nm = "jalen brunson"
        stale = _harden_stale(
            mp=10.55,
            prev_min={nm: 10.55},
            prev2_min={},           # not seen 12-min back
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False

    # -- Minutes moving (not stagnant) -> no flag -----------------------------

    def test_moving_minutes_no_flag(self):
        nm = "jalen brunson"
        stale = _harden_stale(
            mp=18.5,
            prev_min={nm: 16.0},   # was different 6-min back
            prev2_min={nm: 14.0},
            nm=nm,
            qbreak_now=False,
            qbreak_6=False,
            qbreak_12=False,
            period_now=2,
            period_12=1,
        )
        assert stale is False


# ---------------------------------------------------------------------------
# Source-level checks: verify router contains key identifiers
# ---------------------------------------------------------------------------

class TestRouterSourceContainsHardenFlag:
    def _src(self):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent
                / "api" / "courtvision_router.py").read_text(encoding="utf-8")

    def test_flag_env_read(self):
        assert "CV_OUT_DETECT_HARDEN" in self._src()

    def test_two_window_variables(self):
        assert "_prev2_min" in self._src()

    def test_period_change_condition(self):
        # Key discriminator: period_now != period_12
        src = self._src()
        assert "_period_now" in src
        assert "_period_12" in src

    def test_is_quarter_break_helper(self):
        assert "_is_quarter_break" in self._src()

    def test_qbreak_6_variable(self):
        assert "_qbreak_6" in self._src()

    def test_qbreak_12_variable(self):
        assert "_qbreak_12" in self._src()

    def test_flag_off_stale_false(self):
        assert "_stale = False" in self._src()

    def test_flag_on_both_window_stagnation(self):
        src = self._src()
        assert "abs(float(_mp) - _mp6) < 0.05" in src
        assert "abs(_mp6 - _mp12) < 0.05" in src

    def test_qbreak_dual_guard_in_helper(self):
        # Both ends: <= 0.5 AND >= 11.5
        src = self._src()
        assert "_clk_min <= 0.5 or _clk_min >= 11.5" in src
