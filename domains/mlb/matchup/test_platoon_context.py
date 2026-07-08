"""Per-file tests for platoon_context. Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/matchup/test_platoon_context.py -q

Acceptance criteria:
  1. _fine_platoon applies the min_pa_per_hand floor on the (entity, hand)
     MARGINAL (all pitch types summed), not per fine cell.
  2. Qualifying cells' pitch-type breakdown sums back to the marginal.
  3. Real on-disk corpus smoke test (2022 only, for speed): plenty of
     qualifying (batter, p_throws) cells now that the corpus is full-season
     (platoon_split_index.py's docstring, written against an 18-day sample,
     found ZERO qualifiers -- this module's floor is on ONE hand only, and
     the full-season file changes that outcome; asserted here, not assumed).
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.matchup import platoon_context as pc


def _fixture_pa_rows() -> pd.DataFrame:
    # batter 1 vs p_throws='R': 3 PA (2 FF, 1 SL) -> below the floor of 100
    # when min_pa_per_hand=3 is NOT set that low; use a small floor for the test.
    return pd.DataFrame({
        "batter": [1, 1, 1, 2, 2],
        "pitcher": [10, 10, 11, 12, 12],
        "stand": ["R", "R", "R", "L", "L"],
        "p_throws": ["R", "R", "R", "L", "L"],
        "pitch_type": ["FF", "FF", "SL", "FF", "SL"],
        "events": ["single", "strikeout", "walk", "field_out", "strikeout"],
    })


def test_fine_platoon_applies_floor_on_marginal():
    df = _fixture_pa_rows()
    df["on_base"] = df["events"].isin(pc._ON_BASE_EVENTS).astype(int)
    df["is_k"] = df["events"].isin(pc._K_EVENTS).astype(int)
    # floor=3: batter 1 has 3 PA vs R -> qualifies; batter 2 has 2 PA vs L -> excluded
    fine, report = pc._fine_platoon(df, "batter", "p_throws", min_pa_per_hand=3)
    assert report["n_hand_cells_considered"] == 2
    assert report["n_hand_cells_qualifying"] == 1
    assert set(fine["batter"]) == {1}


def test_fine_platoon_pitch_type_rows_sum_to_marginal():
    df = _fixture_pa_rows()
    df["on_base"] = df["events"].isin(pc._ON_BASE_EVENTS).astype(int)
    df["is_k"] = df["events"].isin(pc._K_EVENTS).astype(int)
    fine, _ = pc._fine_platoon(df, "batter", "p_throws", min_pa_per_hand=3)
    assert fine["n_pa"].sum() == 3  # batter 1's 2 FF + 1 SL


def test_real_corpus_batter_platoon_pitch_has_qualifiers():
    """Smoke test against the REAL 2022 corpus -- confirms the full-season
    file yields qualifying (batter, p_throws) cells (unlike
    platoon_split_index.py's documented zero-qualifier finding on the
    18-day sample its docstring describes)."""
    pa_rows = pc.load_pa_rows(seasons=(2022,))
    fine, report = pc.build_batter_platoon_pitch(pa_rows)
    assert report["n_hand_cells_qualifying"] > 0
    assert len(fine) > 0
    assert fine["on_base_rate"].between(0, 1).all()
    assert fine["k_rate"].between(0, 1).all()
