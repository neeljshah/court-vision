"""Per-file tests for platoon_split_index + platoon_split_claims (LANE
platoon-index, program v2 build rank 2).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/mlb/test_platoon_split_index.py -q

Acceptance criteria:
  1. load_pa_rows keeps only events-notna (PA-ending) rows, stamps season.
  2. build_platoon_snapshot pivots to one row per batter with all four
     pa_vs_l/on_base_vs_l/pa_vs_r/on_base_vs_r columns present (0-filled).
  3. build_platoon_index's min-sample floor actually excludes a batter who
     clears one hand but not the other; platoon_delta correct on a fixture
     engineered to clear the floor on BOTH hands.
  4. The real on-disk 2022+2023 corpus: build_ranking_claim's claim is
     independently re-verified by claims_validator.validate_claim. Given the
     documented honest data-scale finding (0 batters clear >=100 PA vs BOTH
     hands on this 18-day-per-season corpus), the correct verdict is
     UNVERIFIABLE with the "no rows survive min_sample floors" reason -- this
     test asserts that HONEST outcome, not a fabricated VERIFIED.
"""
from __future__ import annotations

import pandas as pd

from domains.mlb import platoon_split_index as psi
from scripts.platformkit.intel_validation import platoon_split_claims as psc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_pa_rows() -> pd.DataFrame:
    """Engineered PA-ending rows: batter 1 clears >=5 PA vs BOTH hands (our
    test floor), batter 2 clears vs R only, batter 3 has a non-PA row
    (events NaN) that must be dropped before aggregation."""
    return pd.DataFrame({
        "batter": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
                   2, 2, 2, 2, 2,
                   3],
        "p_throws": ["L"] * 5 + ["R"] * 5 + ["R"] * 5 + ["L"],
        "events": (
            ["single", "walk", "field_out", "strikeout", "double"]
            + ["home_run", "field_out", "field_out", "strikeout", "walk"]
            + ["single", "field_out", "strikeout", "field_out", "walk"]
            + [None]
        ),
        "season": [2022] * 16,
    })


def test_load_pa_rows_drops_non_pa_and_flags_on_base(monkeypatch, tmp_path):
    df = _fixture_pa_rows()
    p22 = tmp_path / "s2022.parquet"
    p23 = tmp_path / "s2023.parquet"
    df[df["season"] == 2022].drop(columns=["season"]).to_parquet(p22)
    pd.DataFrame(columns=df.columns).drop(columns=["season"]).to_parquet(p23)
    monkeypatch.setattr(psi, "_STATCAST_2022", p22)
    monkeypatch.setattr(psi, "_STATCAST_2023", p23)

    pa_rows = psi.load_pa_rows()
    # the one events=None row (batter 3) must be dropped
    assert len(pa_rows) == 15
    assert pa_rows["events"].notna().all()
    # on_base flag: single/walk/double/home_run -> 1, field_out/strikeout -> 0
    on_base_events = pa_rows[pa_rows["events"].isin(["single", "walk", "double", "home_run"])]
    assert (on_base_events["on_base"] == 1).all()
    off_base_events = pa_rows[pa_rows["events"].isin(["field_out", "strikeout"])]
    assert (off_base_events["on_base"] == 0).all()


def test_build_platoon_snapshot_wide_pivot_zero_fills_missing_hand():
    pa_rows = _fixture_pa_rows()
    pa_rows = pa_rows[pa_rows["events"].notna()].copy()
    pa_rows["on_base"] = pa_rows["events"].isin(psi._ON_BASE_EVENTS).astype(int)

    wide, report = psi.build_platoon_snapshot(pa_rows)
    assert set(wide["batter"]) == {1, 2}
    row1 = wide[wide["batter"] == 1].iloc[0]
    assert row1["pa_vs_l"] == 5 and row1["pa_vs_r"] == 5
    row2 = wide[wide["batter"] == 2].iloc[0]
    # batter 2 never faced L -> zero-filled, not dropped/NaN
    assert row2["pa_vs_l"] == 0 and row2["on_base_vs_l"] == 0
    assert row2["pa_vs_r"] == 5
    assert report["n_batters_considered"] == 2


def test_build_platoon_index_floor_excludes_single_hand_qualifier(monkeypatch):
    monkeypatch.setattr(psi, "MIN_PA_PER_HAND", 5)
    monkeypatch.setattr(psi, "_GAMELOGS", psi._REPO_ROOT / "__does_not_exist__.parquet")
    pa_rows = _fixture_pa_rows()
    pa_rows = pa_rows[pa_rows["events"].notna()].copy()
    pa_rows["on_base"] = pa_rows["events"].isin(psi._ON_BASE_EVENTS).astype(int)

    qualifiers, report = psi.build_platoon_index(pa_rows)
    # batter 1: 5 PA vs L (2 on_base: single+double... wait double not in _ON_BASE_EVENTS? it is) and 5 vs R -> qualifies
    # batter 2: 0 PA vs L -> excluded even though 5 PA vs R
    assert set(qualifiers["batter"]) == {1}
    assert report["n_qualifying_batters"] == 1
    assert report["n_batters_excluded_below_floor"] == 1
    row1 = qualifiers.iloc[0]
    # vs L: single, walk, double -> on_base; field_out, strikeout -> not. 3/5 = 0.6
    assert abs(row1["rate_vs_l"] - 0.6) < 1e-9
    # vs R: home_run -> on_base; field_out, field_out, strikeout, walk -> walk is on_base too. 2/5 = 0.4
    assert abs(row1["rate_vs_r"] - 0.4) < 1e-9
    assert abs(row1["platoon_delta"] - 0.2) < 1e-9


def test_real_platoon_split_claim_honest_empty_or_verified():
    """Cross-module check against the REAL on-disk 2022+2023 corpus. Given
    the documented data-scale finding (0 batters clear >=100 PA vs BOTH hands
    on this 18-day-per-season corpus), the honest verdict is UNVERIFIABLE
    with the min_sample-floor reason. If a fuller corpus is ever swapped in
    and qualifiers appear, VERIFIED is also an acceptable outcome -- this
    test never accepts a silent MISMATCH."""
    claim = psc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict in ("VERIFIED", "UNVERIFIABLE"), verdict.reason
    if verdict.verdict == "UNVERIFIABLE":
        assert "min_sample" in verdict.reason or "no rows survive" in verdict.reason
        assert claim["ranking"] == []
