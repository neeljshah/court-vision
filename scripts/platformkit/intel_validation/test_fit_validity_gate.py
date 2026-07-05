"""Tests for fit_validity_gate.py -- the guard is the point -- PLUS the V2
amendment's --spec pass-through and the real fit_validity_gate_impl math.

V1 REGRESSION (must stay green forever, DEFAULT spec_path):
    1. the pre-registration spec loads and its guard-relevant fields have
       the expected committed values (pre_registered=True, run_permitted=False).
    2. run_gate() ALWAYS raises FitGateNotAuthorized against the DEFAULT
       (V1) spec, regardless of explicit_run_requested, because
       run_permitted is False in the committed V1 spec.
    3. the planted-null/pure-noise STUBS in fit_validity_gate.py (V1's
       placeholders) still raise NotImplementedError -- they are never
       upgraded in place; the REAL null implementations live in
       fit_validity_gate_nulls.py and are tested separately below.

V2 AMENDMENT (new):
    4. the V2 spec loads and reports run_permitted=true, authorized_by set.
    5. --spec pointing at V2 clears fit_validity_gate.run_gate()'s guard
       (still defers to fit_validity_gate_impl for actual execution).
    6. null permutations in fit_validity_gate_nulls.py are REAL permutations
       (same multiset of values, deterministic given a seed, order changed).
    7. gate-comparability: H1's feature set is EXACTLY H0's plus [fit_score]
       -- verified structurally against the ingredient-construction output.

Per-file only: python -m pytest scripts/platformkit/intel_validation/test_fit_validity_gate.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.intel_validation.fit_validity_gate import (
    FitGateNotAuthorized,
    PREREG_SPEC_PATH,
    load_prereg_spec,
    pure_noise_control,
    run_gate,
    shuffle_move_team_assignment,
)
from scripts.platformkit.intel_validation.fit_validity_gate_impl import (
    V2_SPEC_PATH,
    build_ingredients,
    load_v2_spec,
)
from scripts.platformkit.intel_validation.fit_validity_gate_nulls import (
    shuffle_move_team_assignment as real_shuffle_destinations,
    shuffle_outcome_deltas as real_shuffle_outcomes,
)


def test_spec_loads_with_expected_guard_fields():
    spec = load_prereg_spec()
    assert spec.pre_registered is True
    assert spec.run_permitted is False
    assert spec.n_moves == 96
    assert spec.decision_current_wave.startswith("NOT_TESTABLE")


def test_spec_file_exists_at_documented_path():
    assert PREREG_SPEC_PATH.exists()
    assert PREREG_SPEC_PATH.name == "fit_validity_gate_prereg.json"


def test_run_gate_refuses_without_explicit_request():
    with pytest.raises(FitGateNotAuthorized, match="explicit_run_requested=False"):
        run_gate(explicit_run_requested=False)


def test_run_gate_refuses_even_with_explicit_request_because_run_not_permitted():
    with pytest.raises(FitGateNotAuthorized, match="run_permitted is False"):
        run_gate(explicit_run_requested=True)


def test_shuffle_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        shuffle_move_team_assignment(moves=None, seed=0)


def test_pure_noise_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        pure_noise_control(fit_scores=None, seed=0)


def test_missing_pre_registered_field_fails_closed(tmp_path):
    bad_spec = tmp_path / "bad_prereg.json"
    bad_spec.write_text(
        json.dumps({"run_permitted": False, "status": "x", "hypothesis": {"H1_candidate": "x"},
                    "corpus": {"verified_counts": {"n_strict_moves_team_changed": 0}},
                    "decision_rule": {"current_wave_verdict": "x"}}),
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="pre_registered"):
        load_prereg_spec(bad_spec)


# ---------------------------------------------------------------------------
# V2 amendment tests
# ---------------------------------------------------------------------------

def test_v2_spec_file_exists_and_loads():
    assert V2_SPEC_PATH.exists()
    payload = load_v2_spec(V2_SPEC_PATH)
    assert payload["pre_registered"] is True
    assert payload["run_permitted"] is True
    assert payload["recorded_fable_authorization"]["authorized_by"] == "fable_user_proxy_2026-07-05"
    assert payload["supersedes_by_reference"]["v1_sha256_prefix_pinned"] == "23c53baf5a658f2c"


def test_v1_default_spec_path_still_refuses_after_v2_added():
    """The core regression: adding --spec/V2 must NOT weaken the DEFAULT
    (no --spec) path. Calling run_gate() with no spec_path argument at all
    must still hit the frozen V1 spec and still refuse."""
    with pytest.raises(FitGateNotAuthorized, match="run_permitted is False"):
        run_gate(explicit_run_requested=True)  # spec_path defaults to PREREG_SPEC_PATH (V1)


def test_run_gate_with_explicit_v1_spec_path_still_refuses():
    with pytest.raises(FitGateNotAuthorized, match="run_permitted is False"):
        run_gate(explicit_run_requested=True, spec_path=PREREG_SPEC_PATH)


def test_run_gate_with_v2_spec_path_clears_guard_but_defers_to_impl():
    """V2 clears fit_validity_gate.run_gate()'s OWN guard (pre_registered/
    run_permitted/explicit_run_requested all True), but this guard module
    still never executes fit math -- it raises a DIFFERENT, distinguishing
    message pointing at fit_validity_gate_impl.run_gate()."""
    with pytest.raises(FitGateNotAuthorized, match="fit_validity_gate_impl"):
        run_gate(explicit_run_requested=True, spec_path=V2_SPEC_PATH)


def test_v1_refusal_message_and_v2_deferral_message_are_distinguishable():
    """Guards against a lazy fix that makes both spec paths raise the exact
    same generic message (which would hide a real authorization bug)."""
    with pytest.raises(FitGateNotAuthorized) as v1_exc:
        run_gate(explicit_run_requested=True, spec_path=PREREG_SPEC_PATH)
    with pytest.raises(FitGateNotAuthorized) as v2_exc:
        run_gate(explicit_run_requested=True, spec_path=V2_SPEC_PATH)
    assert "run_permitted is False" in str(v1_exc.value)
    assert "run_permitted is False" not in str(v2_exc.value)


# ---------------------------------------------------------------------------
# Null-permutation reality tests (fit_validity_gate_nulls.py)
# ---------------------------------------------------------------------------

def _toy_moves() -> pd.DataFrame:
    return pd.DataFrame({
        "player_name": [f"p{i}" for i in range(10)],
        "season_pre": ["2020-21"] * 5 + ["2021-22"] * 5,
        "team_post": ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"],
        "bpm_delta": [1.0, -2.0, 3.0, -4.0, 5.0, -1.5, 2.5, -3.5, 4.5, -5.5],
    })


def test_shuffle_destinations_is_a_real_permutation_within_fold():
    moves = _toy_moves()
    shuffled = real_shuffle_destinations(moves, seed=42)
    for season_pre, group in moves.groupby("season_pre"):
        shuffled_group = shuffled.loc[group.index]
        # same multiset of team_post values within the fold (a permutation,
        # not a redraw from an assumed distribution)
        assert sorted(shuffled_group["team_post"]) == sorted(group["team_post"])
    # bpm_delta must stay FIXED to the true realized outcome (null_1 only
    # corrupts the fit-score side, per V2 planted_null_design_v2)
    pd.testing.assert_series_equal(shuffled["bpm_delta"], moves["bpm_delta"])


def test_shuffle_destinations_is_deterministic_given_seed():
    moves = _toy_moves()
    a = real_shuffle_destinations(moves, seed=7)
    b = real_shuffle_destinations(moves, seed=7)
    pd.testing.assert_frame_equal(a, b)


def test_shuffle_outcomes_is_a_real_permutation_within_fold():
    moves = _toy_moves()
    shuffled = real_shuffle_outcomes(moves, seed=99)
    for season_pre, group in moves.groupby("season_pre"):
        shuffled_group = shuffled.loc[group.index]
        assert sorted(shuffled_group["bpm_delta"]) == sorted(group["bpm_delta"])
    # team_post must stay fixed to the TRUE destination (null_2 only
    # corrupts the outcome side)
    pd.testing.assert_series_equal(shuffled["team_post"], moves["team_post"])


def test_shuffle_outcomes_actually_changes_order_not_a_noop():
    """A shuffle that happens to return the identity permutation would be a
    false pass for a permutation test -- assert at least one seed among a
    small batch actually reorders values (guards against an accidental
    identity no-op)."""
    moves = _toy_moves()
    any_reordered = False
    for seed in range(10):
        shuffled = real_shuffle_outcomes(moves, seed=seed)
        if not shuffled["bpm_delta"].equals(moves["bpm_delta"]):
            any_reordered = True
            break
    assert any_reordered


# ---------------------------------------------------------------------------
# Gate-comparability: candidate feature set == base + [fit_score] exactly
# ---------------------------------------------------------------------------

def test_build_ingredients_adds_exactly_one_new_column():
    """H0's feature set is the moves_corpus columns as-is; H1's is that SAME
    set plus exactly one new column (fit_score). This is the structural
    comparability assertion the V2 spec requires: no other feature may
    differ between H0 and H1."""
    moves = pd.DataFrame({
        "player_name": ["Russell Westbrook", "Eric Bledsoe"],
        "season_pre": ["2020-21", "2020-21"],
        "season_post": ["2021-22", "2021-22"],
        "team_pre": ["WAS", "NOP"],
        "team_post": ["LAL", "LAC"],
        "bpm_pre": [3.7, -2.0],
        "bpm_post": [-1.6, -0.8],
        "bpm_delta": [-5.3, 1.2],
    })
    season_table = pd.DataFrame({
        "player_name": ["Russell Westbrook", "Eric Bledsoe", "LeBron James"],
        "team": ["WAS", "NOP", "LAL"],
        "season": ["2020-21", "2020-21", "2020-21"],
        "usg_pct": [30.2, 18.5, 31.6],
        "ts_pct": [0.509, 0.533, 0.605],
        "three_par": [0.221, 0.35, 0.25],
        "ast_pct": [48.6, 20.1, 38.0],
        "orb_pct": [4.9, 2.1, 3.0],
    })
    h0_cols = set(moves.columns)
    h1 = build_ingredients(moves, season_table)
    h1_cols = set(h1.columns)
    assert h1_cols - h0_cols == {"fit_score"}
    assert h0_cols - h1_cols == set()
