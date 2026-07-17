"""Per-file tests for shooter_composite_v2_claims (basketball-smart
"best shooter" composite family).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_shooter_composite_v2_claims.py -q

Acceptance:
  1. Qualification floor: fg3a_per_game < 4.0 excluded (Dee); ==4.0 included
     (Cara, boundary >=).
  2. Weight redistribution: a qualified player missing one ingredient
     (Bob, gravity_score) gets its weight redistributed pro-rata across the
     ingredients it DOES have -- hand-computed against compute_snapshot.
  3. <4/6 ingredients present -> excluded even though the volume floor
     passed (Eve).
  4. Percentile math: rank(pct=True)*100 within the qualified pool only.
  5. Validator round-trip VERIFIED on a synthetic snapshot fixture.
  6. Honest caveats: weights verbatim + weights_frozen_note, no forbidden
     edge-claim words, edge_claimed False.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import shooter_composite_v2_claims as scv2

# player_id, player_name, games, fg3a_per_game, fg3_pct, pullup_combined_freq,
# unassisted_share_3pm, gravity_score, ft_reliability
_NAN = float("nan")
_FIXTURE_ROWS = [
    (1, "Alice", 70, 8.0, 0.40, 0.30, 0.20, 0.05, 0.85),   # all 6 present, best on every axis
    (2, "Bob", 68, 6.0, 0.35, 0.25, 0.15, _NAN, 0.80),      # gravity missing -> redistribute
    (3, "Cara", 60, 4.0, 0.30, 0.20, 0.10, 0.02, 0.75),    # exactly the floor -- included
    (4, "Dee", 65, 3.9, 0.50, 0.50, 0.50, 0.50, 0.90),      # just below the floor -- excluded
    # clears the volume floor (5.0 >= 4.0) but only 1/6 ingredients present
    # (fg3a_per_game itself) -> excluded on the ingredient-count floor, a
    # DIFFERENT reason than Dee's. All-NaN on the rest so Eve does not
    # perturb any OTHER player's within-pool percentile.
    (5, "Eve", 55, 5.0, _NAN, _NAN, _NAN, _NAN, _NAN),
]
_COLS = [
    "player_id", "player_name", "games", "fg3a_per_game", "fg3_pct",
    "pullup_combined_freq", "unassisted_share_3pm", "gravity_score", "ft_reliability",
]


def _raw() -> pd.DataFrame:
    return pd.DataFrame(_FIXTURE_ROWS, columns=_COLS)


@pytest.fixture()
def snap() -> pd.DataFrame:
    return scv2.compute_snapshot(_raw())


def test_floor_boundary_include_and_exclude(snap):
    by_name = snap.set_index("player_name")
    assert by_name.loc["Cara", "fg3a_per_game"] == 4.0
    assert not pd.isna(by_name.loc["Cara", "shooter_composite_v2"])  # included: floor is >=
    assert pd.isna(by_name.loc["Dee", "shooter_composite_v2"])       # excluded: 3.9 < 4.0


def test_min_ingredients_present_excludes_even_when_floor_passes(snap):
    by_name = snap.set_index("player_name")
    assert by_name.loc["Eve", "fg3a_per_game"] >= scv2.FG3A_PER_GAME_FLOOR
    assert by_name.loc["Eve", "n_present"] == 1
    assert pd.isna(by_name.loc["Eve", "shooter_composite_v2"])


def test_percentile_within_qualified_pool_only(snap):
    by_name = snap.set_index("player_name")
    # fg3a_per_game: Eve (5.0) clears the volume floor too, so the
    # within-pool percentile ranks all 4 qualified rows: Cara(4.0) < Eve(5.0)
    # < Bob(6.0) < Alice(8.0) -> 25/50/75/100.
    assert by_name.loc["Cara", "pctl_fg3a_per_game"] == pytest.approx(25.0)
    assert by_name.loc["Eve", "pctl_fg3a_per_game"] == pytest.approx(50.0)
    assert by_name.loc["Bob", "pctl_fg3a_per_game"] == pytest.approx(75.0)
    assert by_name.loc["Alice", "pctl_fg3a_per_game"] == pytest.approx(100.0)
    # fg3_pct: Eve is NaN here, so only Alice/Bob/Cara form the pool.
    assert by_name.loc["Cara", "pctl_fg3_pct"] == pytest.approx(100 / 3)
    assert by_name.loc["Bob", "pctl_fg3_pct"] == pytest.approx(200 / 3)
    assert by_name.loc["Alice", "pctl_fg3_pct"] == pytest.approx(100.0)
    # Dee never qualified -> percentile columns stay NaN, never leak in
    assert pd.isna(by_name.loc["Dee", "pctl_fg3a_per_game"])


def test_weight_redistribution_hand_computed(snap):
    by_name = snap.set_index("player_name")
    # Alice tops every ingredient -> percentile 100 on all 6 -> composite 100.0
    assert by_name.loc["Alice", "shooter_composite_v2"] == pytest.approx(100.0)
    # Bob (gravity_score missing, n_present=5): fg3a_per_game pctl=75, and
    # fg3_pct/pullup/unassisted/ft_reliability all pctl=66.6667 (Bob sits at
    # the exact middle of the 3-player pool on each). gravity_score's 0.15
    # weight is redistributed pro-rata (proportional to declared weight)
    # across the other 5 present ingredients (present_weight=0.85):
    #   (0.25/0.85)*75 + (0.60/0.85)*66.6667 = 69.1176
    assert by_name.loc["Bob", "n_present"] == 5
    expected_bob = round((0.25 / 0.85) * 75.0 + (0.60 / 0.85) * (200 / 3), 4)
    assert by_name.loc["Bob", "shooter_composite_v2"] == pytest.approx(expected_bob, abs=1e-4)
    # Cara: fg3a_per_game pctl=25, fg3_pct/pullup/unassisted/ft pctl=33.3333,
    # gravity_score pctl=50 (better of the two present gravity values) --
    # all 6 present so no redistribution, hand-computed weighted sum = 33.75.
    expected_cara = round(
        0.25 * 25.0 + 0.25 * (100 / 3) + 0.10 * (100 / 3) + 0.10 * (100 / 3) + 0.15 * 50.0 + 0.15 * (100 / 3), 4,
    )
    assert expected_cara == pytest.approx(33.75)
    assert by_name.loc["Cara", "shooter_composite_v2"] == pytest.approx(expected_cara, abs=1e-4)
    assert by_name.loc["Alice", "shooter_composite_v2"] > by_name.loc["Bob", "shooter_composite_v2"] > by_name.loc["Cara", "shooter_composite_v2"]


def test_build_claim_contract_and_counts(snap):
    claim = scv2.build_claim(snap, season="fixture", snapshot_path=scv2._SNAPSHOT_PATH)
    assert claim["kind"] == "ranking"
    assert claim["criteria"]["entity_key"] == "player_id"
    assert claim["criteria"]["formula"] == "shooter_composite_v2"
    assert claim["criteria"]["min_sample"] == {
        "fg3a_per_game": scv2.FG3A_PER_GAME_FLOOR, "n_present": scv2.MIN_INGREDIENTS_PRESENT,
    }
    assert claim["n_considered"] == 5
    assert claim["n_excluded_below_floor"] == 2  # Dee (volume floor) + Eve (<4 present)
    names = [r["player_name"] for r in claim["ranking"]]
    assert names == ["Alice", "Bob", "Cara"]
    ranks = [r["rank"] for r in claim["ranking"]]
    assert ranks == [1, 2, 3]


def test_validator_independently_reverifies(snap, monkeypatch, tmp_path):
    snapshot_path = tmp_path / "snap.parquet"
    monkeypatch.setattr(scv2, "REPO_ROOT", tmp_path.parent)
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path.parent)
    scv2._write_snapshot(snap, snapshot_path)
    claim = scv2.build_claim(snap, season="fixture", snapshot_path=snapshot_path)
    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_honest_caveats_weights_verbatim_no_forbidden_words(snap):
    claim = scv2.build_claim(snap, season="fixture", snapshot_path=scv2._SNAPSHOT_PATH)
    raw_text = " ".join(claim["caveats"] + [claim["question"]]).lower()
    assert claim["edge_claimed"] is False
    assert "weights_frozen_note" in raw_text
    # weights verbatim: every ingredient name + its declared weight value
    # appears in the caveats text (checked as plain substrings, not a
    # re-serialized JSON blob, so quoting style never breaks the check).
    for k, v in scv2.FROZEN_WEIGHTS.items():
        assert k in raw_text
        assert str(v) in raw_text
    assert "descriptive" in raw_text
    blob = json.dumps([claim["caveats"], claim["question"]]).lower()
    for word in ("roi", "pnl", "$", "bankroll", "edge claim"):
        assert word not in blob
