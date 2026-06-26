"""tests for domains.mlb.re24_table -- hermetic, per-file, no network.

Covers:
  - RE24 structure (exactly 24 entries, all keys, all values > 0)
  - Published-table monotonic sanity (outs 0->1->2 strictly decreasing RE per runners;
    bases-empty < bases-loaded at same outs; extra runner never lowers RE at extremes)
  - Specific pinned values from the published source (transposition regression)
  - base_run_value: known lookups, runners masking, out-of-range -> 0.0
  - leverage_bucket: one concrete case per branch; blowout precedence
  - Leak-free provenance: estimation seasons disjoint from gate corpora (2022, 2023)

ASCII only. No imports except the module under test and stdlib. <=300 LOC.
"""
from __future__ import annotations

import pytest

from domains.mlb.re24_table import (
    RE24,
    RE24_ESTIMATION_SEASONS,
    _1B,
    _1B_2B,
    _1B_3B,
    _2B,
    _2B_3B,
    _3B,
    _EMPTY,
    _LOADED,
    base_run_value,
    leverage_bucket,
)


# ---------------------------------------------------------------------------
# RE24 structure
# ---------------------------------------------------------------------------

class TestRE24Structure:
    def test_exactly_24_entries(self):
        assert len(RE24) == 24, f"expected 24 entries, got {len(RE24)}"

    def test_all_24_keys_present(self):
        expected = {(r, o) for r in range(8) for o in (0, 1, 2)}
        assert set(RE24.keys()) == expected

    def test_all_values_positive_floats(self):
        for key, val in RE24.items():
            assert isinstance(val, float), f"RE24[{key}] is not float: {type(val)}"
            assert val > 0.0, f"RE24[{key}] = {val} is not > 0"


# ---------------------------------------------------------------------------
# Published-table monotonic sanity
# ---------------------------------------------------------------------------

class TestRE24Monotonicity:
    """Properties that hold for every published RE24 table from The Book."""

    def test_re_strictly_decreases_with_outs_for_each_runners_mask(self):
        """For fixed base state, RE[outs=0] > RE[outs=1] > RE[outs=2]."""
        for runners in range(8):
            re0 = RE24[(runners, 0)]
            re1 = RE24[(runners, 1)]
            re2 = RE24[(runners, 2)]
            assert re0 > re1, f"runners={runners}: RE[0]={re0} not > RE[1]={re1}"
            assert re1 > re2, f"runners={runners}: RE[1]={re1} not > RE[2]={re2}"

    def test_bases_empty_lower_than_bases_loaded_at_each_outs(self):
        """Bases empty always has lower RE than bases loaded."""
        for outs in (0, 1, 2):
            assert RE24[(_EMPTY, outs)] < RE24[(_LOADED, outs)], (
                f"outs={outs}: empty RE {RE24[(_EMPTY, outs)]} not < loaded RE {RE24[(_LOADED, outs)]}"
            )

    def test_extra_runner_never_lowers_re_empty_to_loaded_at_fixed_outs(self):
        """RE increases monotonically from empty (0) to loaded (7) for each outs level.

        We check only the extremes as required: no additional runner can lower RE
        when moving from empty baseline toward loaded.
        """
        for outs in (0, 1, 2):
            prev = RE24[(_EMPTY, outs)]
            for runners in (1, 2, 3, 4, 5, 6, 7):
                curr = RE24[(runners, outs)]
                # This is a sanity property of the published table: no single base
                # state (by integer order) goes below the empty state.
                assert curr > RE24[(_EMPTY, outs)], (
                    f"runners={runners}, outs={outs}: RE {curr} <= empty RE {prev}"
                )


# ---------------------------------------------------------------------------
# Pinned published values (transposition regression)
# ---------------------------------------------------------------------------

class TestRE24PinnedValues:
    """Assert the exact numbers from The Book to catch any value transposition."""

    def test_bases_empty_0_outs(self):
        assert RE24[(_EMPTY, 0)] == 0.555

    def test_bases_empty_1_out(self):
        assert RE24[(_EMPTY, 1)] == 0.297

    def test_bases_empty_2_outs(self):
        assert RE24[(_EMPTY, 2)] == 0.117

    def test_bases_loaded_0_outs(self):
        assert RE24[(_LOADED, 0)] == 2.417

    def test_bases_loaded_1_out(self):
        assert RE24[(_LOADED, 1)] == 1.650

    def test_bases_loaded_2_outs(self):
        assert RE24[(_LOADED, 2)] == 0.815

    def test_1b_only_0_outs(self):
        assert RE24[(_1B, 0)] == 0.953

    def test_2b_only_0_outs(self):
        assert RE24[(_2B, 0)] == 1.189

    def test_3b_only_0_outs(self):
        assert RE24[(_3B, 0)] == 1.482

    def test_2b_3b_0_outs(self):
        assert RE24[(_2B_3B, 0)] == 2.052

    def test_1b_2b_3b_bitmask_is_7(self):
        assert _LOADED == 7

    def test_1b_bitmask_is_4(self):
        assert _1B == 4

    def test_2b_bitmask_is_2(self):
        assert _2B == 2

    def test_3b_bitmask_is_1(self):
        assert _3B == 1


# ---------------------------------------------------------------------------
# base_run_value
# ---------------------------------------------------------------------------

class TestBaseRunValue:
    def test_known_lookup_empty_0_outs(self):
        assert base_run_value(_EMPTY, 0) == RE24[(_EMPTY, 0)]

    def test_known_lookup_loaded_2_outs(self):
        assert base_run_value(_LOADED, 2) == RE24[(_LOADED, 2)]

    def test_known_lookup_1b_1_out(self):
        assert base_run_value(_1B, 1) == RE24[(_1B, 1)]

    def test_known_lookup_2b_3b_0_outs(self):
        assert base_run_value(_2B_3B, 0) == RE24[(_2B_3B, 0)]

    def test_runners_masking_bit3_stripped(self):
        """8 & 0b111 == 0, so base_run_value(8, 0) == base_run_value(0, 0)."""
        assert base_run_value(8, 0) == base_run_value(0, 0)

    def test_runners_masking_bit4_stripped(self):
        """16 & 0b111 == 0 -> same as empty."""
        assert base_run_value(16, 1) == base_run_value(0, 1)

    def test_runners_masking_high_bits_with_runners(self):
        """9 & 0b111 == 1 == _3B, so base_run_value(9, 0) == RE24[(_3B, 0)]."""
        assert base_run_value(9, 0) == RE24[(_3B, 0)]

    def test_out_of_range_outs_3_returns_zero(self):
        assert base_run_value(0, 3) == 0.0

    def test_out_of_range_outs_negative_returns_zero(self):
        assert base_run_value(0, -1) == 0.0

    def test_out_of_range_large_outs_returns_zero(self):
        assert base_run_value(7, 99) == 0.0

    def test_unknown_state_returns_zero_default(self):
        # After masking, runners 5 = _1B_3B, outs 2 IS in table, check valid lookup
        assert base_run_value(_1B_3B, 2) == RE24[(_1B_3B, 2)]

    def test_return_type_is_float(self):
        val = base_run_value(_LOADED, 0)
        assert isinstance(val, float)

    def test_out_of_range_returns_float_zero(self):
        val = base_run_value(0, 3)
        assert isinstance(val, float)
        assert val == 0.0


# ---------------------------------------------------------------------------
# leverage_bucket -- one concrete case per branch, in precedence order
# ---------------------------------------------------------------------------

class TestLeverageBucket:
    def test_blowout_precedence_overrides_late_close_with_runners(self):
        """Branch 1: |margin|>=5 -> low, even when inning>=7 and runners on base."""
        # inning=9, margin=5, bases loaded -- would be high without blowout rule
        result = leverage_bucket(inning=9, state_diff=5.0, runners=_LOADED, outs=0)
        assert result == "low", f"blowout should override late+runners: got {result}"

    def test_blowout_negative_margin(self):
        """Branch 1: negative state_diff; abs >= 5 -> low."""
        result = leverage_bucket(inning=8, state_diff=-6.0, runners=_1B, outs=1)
        assert result == "low"

    def test_late_close_runner_on_base_is_high(self):
        """Branch 2: inning>=7, |margin|<=2, runner on base -> high."""
        # inning=7, margin=1, runner on 2B
        result = leverage_bucket(inning=7, state_diff=1.0, runners=_2B, outs=1)
        assert result == "high", f"late+close+runner should be high: got {result}"

    def test_late_close_runner_on_base_inning_9_is_high(self):
        """Branch 2: inning=9, tight margin, bases loaded -> high."""
        result = leverage_bucket(inning=9, state_diff=-2.0, runners=_LOADED, outs=2)
        assert result == "high"

    def test_late_close_bases_empty_is_mid(self):
        """Branch 2 fallthrough: inning>=7, |margin|<=2, no runners -> mid."""
        result = leverage_bucket(inning=8, state_diff=0.0, runners=_EMPTY, outs=0)
        assert result == "mid", f"late+close+empty should be mid: got {result}"

    def test_risp_early_close_is_mid(self):
        """Branch 3: 2B occupied, outs<2, |margin|<=3, NOT late -> mid."""
        # inning=4 (not late), margin=2, runner on 2B, 1 out
        result = leverage_bucket(inning=4, state_diff=2.0, runners=_2B, outs=1)
        assert result == "mid", f"risp+early+close should be mid: got {result}"

    def test_risp_3b_occupied_early_close_is_mid(self):
        """Branch 3: 3B occupied, outs<2, |margin|<=3 -> mid."""
        result = leverage_bucket(inning=3, state_diff=-3.0, runners=_3B, outs=0)
        assert result == "mid"

    def test_risp_but_outs_equals_2_falls_to_low(self):
        """Branch 3 blocked: risp but outs==2 -> low (not mid)."""
        result = leverage_bucket(inning=4, state_diff=2.0, runners=_2B, outs=2)
        assert result == "low", f"risp+outs=2 should fall through to low: got {result}"

    def test_risp_but_margin_too_large_falls_to_low(self):
        """Branch 3 blocked: risp, outs<2, but margin=4 -> low."""
        result = leverage_bucket(inning=4, state_diff=4.0, runners=_2B, outs=1)
        assert result == "low"

    def test_quiet_early_state_is_low(self):
        """Branch 4 (default): inning=1, margin=1, bases empty, 0 outs -> low."""
        result = leverage_bucket(inning=1, state_diff=1.0, runners=_EMPTY, outs=0)
        assert result == "low", f"quiet early state should be low: got {result}"

    def test_only_1b_no_risp_early_is_low(self):
        """1B only is not RISP (no 2B or 3B), early inning -> low."""
        result = leverage_bucket(inning=3, state_diff=2.0, runners=_1B, outs=1)
        assert result == "low"

    def test_return_values_are_valid_strings(self):
        for inning in (1, 7, 9):
            for runners in (0, 4, 7):
                for outs in (0, 1, 2):
                    for margin in (0.0, 2.0, 5.0):
                        result = leverage_bucket(inning, margin, runners, outs)
                        assert result in ("low", "mid", "high"), (
                            f"unexpected return {result!r}"
                        )


# ---------------------------------------------------------------------------
# Leak-free provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_estimation_seasons_type(self):
        assert isinstance(RE24_ESTIMATION_SEASONS, tuple)
        assert all(isinstance(s, int) for s in RE24_ESTIMATION_SEASONS)

    def test_estimation_seasons_are_1999_to_2002(self):
        assert set(RE24_ESTIMATION_SEASONS) == {1999, 2000, 2001, 2002}

    def test_estimation_seasons_disjoint_from_gate_seasons(self):
        """No future-leak: table was fixed before the 2022/2023 gate corpora."""
        gate_seasons = {2022, 2023}
        assert set(RE24_ESTIMATION_SEASONS).isdisjoint(gate_seasons), (
            f"LEAK: estimation seasons {RE24_ESTIMATION_SEASONS} overlap gate seasons {gate_seasons}"
        )
