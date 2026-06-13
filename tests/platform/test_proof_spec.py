"""Tests for scripts/platformkit/proof_common/spec.py — ProofSpec contract."""
from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable so proof_common can be found via the
# scripts/platformkit path on sys.path.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_PLATFORM = REPO_ROOT / "scripts" / "platformkit"
if str(SCRIPTS_PLATFORM) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PLATFORM))

from proof_common.spec import EvalWindow, ProofSpec  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(*_args: Any, **_kwargs: Any) -> Any:
    return None


def _noop_df(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
    return pd.DataFrame()


def _noop_tuple(*_args: Any, **_kwargs: Any) -> Tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(), pd.DataFrame()


def _noop_str(*_args: Any, **_kwargs: Any) -> str:
    return ""


def _noop_dict(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {}


def _make_minimal_spec() -> ProofSpec:
    """Build the smallest possible valid ProofSpec using trivial values."""
    return ProofSpec(
        hyp_v1_name="V1-TEST",
        hyp_v1_statement="Model is calibrated on held-out windows.",
        hyp_v4_name="V4-TEST",
        train_seasons=[2020, 2021],
        eval_windows=[
            EvalWindow("2022", [2022]),
            EvalWindow("2023", [2023], "some-note"),
        ],
        all_seasons=[2020, 2021, 2022, 2023],
        signal_defs=[],
        close_a_col="close_a",
        close_b_col="close_b",
        open_a_col=None,
        open_b_col=None,
        model_prob_col="model_prob",
        market_brier_key="market_brier",
        market_beats_key="market_beats_model",
        v2_note="CLV data present.",
        v2_absent_note="CLV data absent.",
        v2_skip_note_fmt="Skipping row: {row}",
        load_market_frame=_noop,
        outcome_market=_noop,
        outcome_v4=_noop,
        bundle_kwargs=_noop_dict,
        filter_v4_eval=_noop_df,
        filter_v2_odds=_noop_df,
        get_frames_v4=_noop_tuple,
        book_filename=_noop_str,
    )


# ---------------------------------------------------------------------------
# Pinned field names — editing spec.py to rename/add/remove a field will fail
# this test, surfacing the change for review.
# ---------------------------------------------------------------------------
_PINNED_PROOF_SPEC_FIELDS = frozenset(
    {
        "hyp_v1_name",
        "hyp_v1_statement",
        "hyp_v4_name",
        "train_seasons",
        "eval_windows",
        "all_seasons",
        "signal_defs",
        "close_a_col",
        "close_b_col",
        "open_a_col",
        "open_b_col",
        "model_prob_col",
        "market_brier_key",
        "market_beats_key",
        "v2_note",
        "v2_absent_note",
        "v2_skip_note_fmt",
        "load_market_frame",
        "outcome_market",
        "outcome_v4",
        "bundle_kwargs",
        "filter_v4_eval",
        "filter_v2_odds",
        "get_frames_v4",
        "book_filename",
    }
)

_PINNED_EVAL_WINDOW_FIELDS = frozenset({"label", "seasons", "regime_note"})


# ===========================================================================
# Tests: EvalWindow
# ===========================================================================


class TestEvalWindow:
    def test_frozen(self) -> None:
        """EvalWindow must be a frozen dataclass."""
        assert EvalWindow.__dataclass_params__.frozen is True  # type: ignore[attr-defined]

    def test_mutation_raises(self) -> None:
        w = EvalWindow("2023-24", [2023, 2024])
        with pytest.raises(dataclasses.FrozenInstanceError):
            w.label = "changed"  # type: ignore[misc]

    def test_default_regime_note_is_none(self) -> None:
        w = EvalWindow("2023-24", [2023, 2024])
        assert w.regime_note is None

    def test_regime_note_preserved(self) -> None:
        w = EvalWindow("x", [1], "note")
        assert w.regime_note == "note"

    def test_regime_note_empty_string_preserved(self) -> None:
        w = EvalWindow("x", [1], "")
        assert w.regime_note == ""

    def test_field_names_pinned(self) -> None:
        actual = {f.name for f in dataclasses.fields(EvalWindow)}
        assert actual == _PINNED_EVAL_WINDOW_FIELDS

    def test_seasons_roundtrip(self) -> None:
        seasons = [2022, 2023, 2024]
        w = EvalWindow("window", seasons)
        assert w.seasons == seasons
        assert w.label == "window"


# ===========================================================================
# Tests: ProofSpec
# ===========================================================================


class TestProofSpec:
    def test_frozen(self) -> None:
        """ProofSpec must be a frozen dataclass."""
        assert ProofSpec.__dataclass_params__.frozen is True  # type: ignore[attr-defined]

    def test_mutation_raises(self) -> None:
        spec = _make_minimal_spec()
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.hyp_v1_name = "mutated"  # type: ignore[misc]

    def test_constructible_with_all_fields(self) -> None:
        """All required fields are accepted without error."""
        spec = _make_minimal_spec()
        assert spec is not None

    def test_field_names_pinned(self) -> None:
        actual = {f.name for f in dataclasses.fields(ProofSpec)}
        assert actual == _PINNED_PROOF_SPEC_FIELDS

    def test_identity_fields_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert spec.hyp_v1_name == "V1-TEST"
        assert spec.hyp_v1_statement == "Model is calibrated on held-out windows."
        assert spec.hyp_v4_name == "V4-TEST"

    def test_season_fields_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert spec.train_seasons == [2020, 2021]
        assert spec.all_seasons == [2020, 2021, 2022, 2023]

    def test_eval_windows_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert len(spec.eval_windows) == 2
        assert spec.eval_windows[0].label == "2022"
        assert spec.eval_windows[1].regime_note == "some-note"

    def test_market_columns_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert spec.close_a_col == "close_a"
        assert spec.close_b_col == "close_b"
        assert spec.open_a_col is None
        assert spec.open_b_col is None
        assert spec.model_prob_col == "model_prob"

    def test_result_key_names_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert spec.market_brier_key == "market_brier"
        assert spec.market_beats_key == "market_beats_model"

    def test_note_strings_roundtrip(self) -> None:
        spec = _make_minimal_spec()
        assert "CLV data present" in spec.v2_note
        assert "CLV data absent" in spec.v2_absent_note
        assert "{row}" in spec.v2_skip_note_fmt

    def test_leaf_callables_are_callable(self) -> None:
        spec = _make_minimal_spec()
        callable_fields = [
            "load_market_frame",
            "outcome_market",
            "outcome_v4",
            "bundle_kwargs",
            "filter_v4_eval",
            "filter_v2_odds",
            "get_frames_v4",
            "book_filename",
        ]
        for name in callable_fields:
            assert callable(getattr(spec, name)), f"{name} must be callable"

    def test_leaf_callable_invocable(self) -> None:
        """Verify the trivial lambdas don't raise when called."""
        spec = _make_minimal_spec()
        spec.load_market_frame()
        spec.outcome_market(None)
        spec.outcome_v4(None)
        spec.bundle_kwargs(None)
        spec.filter_v4_eval()
        spec.filter_v2_odds()
        spec.get_frames_v4(None)
        spec.book_filename(None)

    def test_open_cols_can_be_strings(self) -> None:
        """open_a_col and open_b_col accept string values (non-None case)."""
        spec = dataclasses.replace(
            _make_minimal_spec(), open_a_col="open_a", open_b_col="open_b"
        )
        assert spec.open_a_col == "open_a"
        assert spec.open_b_col == "open_b"


# ===========================================================================
# Importability / no forbidden tokens in spec.py
# ===========================================================================


class TestSpecModule:
    def test_importable(self) -> None:
        """proof_common.spec must be importable (catches syntax errors)."""
        mod = importlib.import_module("proof_common.spec")
        assert hasattr(mod, "ProofSpec")
        assert hasattr(mod, "EvalWindow")

    def test_spec_py_has_no_sport_tokens(self) -> None:
        """spec.py must contain zero sport-specific tokens."""
        spec_path = SCRIPTS_PLATFORM / "proof_common" / "spec.py"
        text = spec_path.read_text(encoding="utf-8").lower()
        forbidden = [
            "nba",
            "tennis",
            "soccer",
            "mlb",
            "basketball",
            "baseball",
            "football",
            "hockey",
        ]
        found = [tok for tok in forbidden if tok in text]
        assert not found, f"Sport tokens found in spec.py: {found}"
