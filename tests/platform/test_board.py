"""tests/platform/test_board.py — unit tests for scripts.platformkit.frontend.board.

Coverage:
  - HONEST_NOTE constant present and contains no edge-claim language.
  - build_board with a synthetic adapter returns well-formed rows.
  - Row schema: all expected keys present.
  - model_prob / market_fair_prob in [0,1] or None.
  - edge_vs_market is a dict labeled 'DIAGNOSTIC', value is float or None.
  - build_board with absent corpus returns [].
  - build_all_board returns dict keyed by sport IDs.
  - to_json writes valid JSON; round-trip matches.
  - No banned edge-claim words anywhere in the output.
  - Real corpus smoke test (skipped when corpus absent).

Run:  python -m pytest tests/platform/test_board.py -q
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from scripts.platformkit.frontend.board import (
    HONEST_NOTE,
    LINE_SHOP_NOTE,
    _bundle_to_rows,
    _SPORT_REGISTRY,
    build_all_board,
    build_board,
    to_json,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = {
    "sport",
    "date",
    "home",
    "away",
    "model_prob",
    "market_fair_prob",
    "edge_vs_market",
    "best_book",
    "best_line",
    "line_shop_note",
    "clv_placeholder",
    "calibration_tag",
    "honest_note",
}

_BANNED_WORDS = (
    "guaranteed",
    "beat the market",
    "+EV edge",
    "profit",
    "lock",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Synthetic FeatureBundle helper
# ---------------------------------------------------------------------------


def _make_bundle(
    n: int = 5,
    has_market: bool = True,
    has_closing: bool = True,
) -> Any:
    """Return a minimal FeatureBundle-like object for offline tests."""
    rng = np.random.default_rng(42)
    sig = rng.uniform(0.35, 0.65, size=n)
    tgt = rng.integers(0, 2, size=n).astype(float)
    dates = [f"2024-0{i+1}-01" for i in range(n)]
    lines = rng.uniform(0.40, 0.60, size=n) if has_market else None
    closing = rng.uniform(0.41, 0.59, size=n) if has_closing else None

    bundle = MagicMock()
    bundle.signal_col = sig
    bundle.target = tgt
    bundle.dates = dates
    bundle.lines = lines
    bundle.closing = closing
    return bundle


# ---------------------------------------------------------------------------
# HONEST_NOTE tests
# ---------------------------------------------------------------------------


def test_honest_note_present():
    assert isinstance(HONEST_NOTE, str) and len(HONEST_NOTE) > 20


def test_honest_note_no_edge_claims():
    note_lower = HONEST_NOTE.lower()
    for word in _BANNED_WORDS:
        assert word.lower() not in note_lower, (
            f"HONEST_NOTE contains banned phrase: {word!r}"
        )


def test_honest_note_contains_no_model_edge():
    assert "no model edge" in HONEST_NOTE.lower()


# ---------------------------------------------------------------------------
# _bundle_to_rows unit tests
# ---------------------------------------------------------------------------


def test_bundle_to_rows_schema():
    bundle = _make_bundle(n=3)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    assert len(rows) == 3
    for row in rows:
        assert _EXPECTED_KEYS == set(row.keys()), (
            f"Missing keys: {_EXPECTED_KEYS - set(row.keys())}; "
            f"Extra keys: {set(row.keys()) - _EXPECTED_KEYS}"
        )


def test_bundle_to_rows_model_prob_in_range():
    bundle = _make_bundle(n=10)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        mp = row["model_prob"]
        if mp is not None:
            assert 0.0 <= mp <= 1.0, f"model_prob {mp} out of [0,1]"


def test_bundle_to_rows_market_prob_in_range():
    bundle = _make_bundle(n=10)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        mfp = row["market_fair_prob"]
        if mfp is not None:
            assert 0.0 <= mfp <= 1.0, f"market_fair_prob {mfp} out of [0,1]"


def test_bundle_to_rows_market_prob_none_when_no_market():
    bundle = _make_bundle(n=4, has_market=False, has_closing=False)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        assert row["market_fair_prob"] is None


def test_bundle_to_rows_edge_vs_market_is_diagnostic():
    bundle = _make_bundle(n=5)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        ev = row["edge_vs_market"]
        assert isinstance(ev, dict), "edge_vs_market must be a dict"
        assert "label" in ev, "edge_vs_market must have a 'label' key"
        assert "DIAGNOSTIC" in ev["label"], (
            "edge_vs_market label must contain 'DIAGNOSTIC'"
        )
        assert "value" in ev


def test_bundle_to_rows_edge_value_is_float_or_none():
    bundle = _make_bundle(n=5)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        val = row["edge_vs_market"]["value"]
        assert val is None or isinstance(val, float), (
            f"edge value must be float or None, got {type(val)}"
        )


def test_bundle_to_rows_edge_value_when_market_absent():
    bundle = _make_bundle(n=3, has_market=False, has_closing=False)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        assert row["edge_vs_market"]["value"] is None


def test_bundle_to_rows_clv_placeholder_none():
    bundle = _make_bundle(n=3)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        assert row["clv_placeholder"] is None


def test_bundle_to_rows_calibration_tag():
    bundle = _make_bundle(n=2)
    rows = _bundle_to_rows("my_sport", bundle, "calibrated")
    for row in rows:
        assert row["calibration_tag"] == "calibrated"
        assert row["sport"] == "my_sport"


def test_bundle_to_rows_honest_note_embedded():
    bundle = _make_bundle(n=2)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        assert row["honest_note"] == HONEST_NOTE


def test_bundle_to_rows_line_shop_note_embedded():
    bundle = _make_bundle(n=2)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    for row in rows:
        assert row["line_shop_note"] == LINE_SHOP_NOTE


def test_bundle_to_rows_no_banned_words_in_output():
    bundle = _make_bundle(n=5)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    serialized = json.dumps(rows).lower()
    for word in _BANNED_WORDS:
        assert word.lower() not in serialized, (
            f"Board output contains banned phrase: {word!r}"
        )


# ---------------------------------------------------------------------------
# build_board — absent corpus → [] (graceful)
# ---------------------------------------------------------------------------


def test_build_board_absent_corpus_returns_empty(tmp_path):
    rows = build_board("basketball_nba", repo_root=tmp_path)
    assert rows == []


def test_build_board_unknown_sport_returns_empty(tmp_path):
    rows = build_board("cricket_unknownsport", repo_root=tmp_path)
    assert rows == []


# ---------------------------------------------------------------------------
# build_all_board — returns dict over all registered sports
# ---------------------------------------------------------------------------


def test_build_all_board_returns_dict_of_known_sports(tmp_path):
    board = build_all_board(repo_root=tmp_path)
    assert isinstance(board, dict)
    for sport_id in _SPORT_REGISTRY:
        assert sport_id in board, f"Missing sport {sport_id!r} in build_all_board result"


def test_build_all_board_absent_corpus_all_empty(tmp_path):
    board = build_all_board(repo_root=tmp_path)
    for sport_id, rows in board.items():
        assert rows == [], f"Expected [] for absent corpus {sport_id!r}, got {rows[:1]}"


# ---------------------------------------------------------------------------
# to_json — writes valid JSON; round-trip faithful
# ---------------------------------------------------------------------------


def test_to_json_writes_valid_json(tmp_path):
    bundle = _make_bundle(n=4)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    board = {"test_sport": rows}
    out = tmp_path / "board.json"
    to_json(board, out)
    assert out.exists()
    with open(out, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert "test_sport" in loaded
    assert len(loaded["test_sport"]) == 4


def test_to_json_round_trip_preserves_edge_label(tmp_path):
    bundle = _make_bundle(n=2)
    rows = _bundle_to_rows("test_sport", bundle, "calibrated")
    board = {"test_sport": rows}
    out = tmp_path / "board.json"
    to_json(board, out)
    with open(out, encoding="utf-8") as fh:
        loaded = json.load(fh)
    for row in loaded["test_sport"]:
        assert "DIAGNOSTIC" in row["edge_vs_market"]["label"]


# ---------------------------------------------------------------------------
# Real corpus smoke test (skip if absent — CI-friendly)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sport_id", list(_SPORT_REGISTRY.keys()))
def test_build_board_real_corpus_if_present(sport_id):
    reg = _SPORT_REGISTRY[sport_id]
    corpus_dir = _REPO_ROOT / reg["corpus_dir"]
    primary = corpus_dir / reg["primary_parquet"]
    if not primary.exists():
        pytest.skip(f"Corpus absent for {sport_id}: {primary}")

    rows = build_board(sport_id, repo_root=_REPO_ROOT)
    assert len(rows) > 0, f"build_board({sport_id!r}) returned no rows despite corpus"

    for row in rows:
        assert _EXPECTED_KEYS == set(row.keys())
        mp = row["model_prob"]
        mfp = row["market_fair_prob"]
        if mp is not None:
            assert 0.0 <= mp <= 1.0
        if mfp is not None:
            assert 0.0 <= mfp <= 1.0
        ev = row["edge_vs_market"]
        assert isinstance(ev, dict)
        assert "DIAGNOSTIC" in ev["label"]

    serialized = json.dumps(rows).lower()
    for word in _BANNED_WORDS:
        assert word.lower() not in serialized
