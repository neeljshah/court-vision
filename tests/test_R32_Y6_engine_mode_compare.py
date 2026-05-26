"""tests/test_R32_Y6_engine_mode_compare.py — R32_Y6 mode-compare coverage.

Exercises scripts/compare_engine_modes.py against synthetic predictions +
lines fixtures so the tests run in <1s with no real-data dependency.

Coverage:
  1. Both modes produce non-empty recs against a fixture.
  2. The compare payload structure is correct (overlap buckets, shared_bets,
     only_in_multi5 / only_in_mlp, top_multi5 / top_mlp).
  3. Jaccard math (the pure helper) handles known cases + edge cases.
  4. Empty-in-one-mode is handled gracefully (no crash, correct overlap=0).
  5. Repeating compare_modes with the same date/bankroll/top is reproducible
     (deterministic against identical inputs).
  6. The engine reads M2_FAMILY_USE_MLP fresh from os.environ at call time
     (verified via the engine's `_m2_family_use_mlp()` helper).
  7. top_overlap_k controls the buckets emitted in the overlap dict.
  8. Side-by-side compare against a synthetic mode where the MLP path
     produces an entirely DIFFERENT set of recs returns the expected
     jaccard / new / dropped counts.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts import compare_engine_modes as cem  # noqa: E402
from scripts.compare_engine_modes import (  # noqa: E402
    _bet_key,
    compare_modes,
    jaccard,
    overlap_deltas,
    topk_overlap,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
DATE = "2099-02-20"  # synthetic, far-future


def _mk_pred(player: str, stat: str, q50: float, q10: float, q90: float,
             team: str = "AAA") -> dict:
    return {
        "player_id": hash(player) % 10_000_000,
        "player_name": player,
        "team": team,
        "stat": stat,
        "q10": q10, "q50": q50, "q90": q90,
        "sigma": (q90 - q10) / (2 * 1.2816),
        "computed_at": "2099-02-20T12:00:00+00:00",
    }


def _mk_line(player: str, stat: str, line: float,
             over_price: int = -110, under_price: int = -110,
             book: str = "bov") -> dict:
    return {
        "captured_at": "2099-02-20T18:00:00",
        "book": book,
        "game_id": "synthetic",
        "player_id": "",
        "player_name": player,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": "2099-02-20T20:00:00",
    }


def _write_preds(dir_, rows: List[dict]) -> str:
    path = os.path.join(str(dir_), f"predictions_cache_{DATE}.parquet")
    df = pd.DataFrame(rows)
    df.to_parquet(path)
    return path


def _write_lines(dir_, book: str, rows: List[dict]) -> str:
    os.makedirs(str(dir_), exist_ok=True)
    path = os.path.join(str(dir_), f"{DATE}_{book}.csv")
    cols = ["captured_at", "book", "game_id", "player_id", "player_name",
            "stat", "line", "over_price", "under_price", "start_time"]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df[cols].to_csv(path, index=False)
    return path


@pytest.fixture
def tmp_dirs(tmp_path):
    cache_dir = tmp_path / "cache"
    lines_dir = tmp_path / "lines"
    cache_dir.mkdir()
    lines_dir.mkdir()
    return {
        "cache": str(cache_dir),
        "lines": str(lines_dir),
        "preds_path": os.path.join(
            str(cache_dir), f"predictions_cache_{DATE}.parquet"
        ),
        "injury_path": os.path.join(str(cache_dir), "no_inj.parquet"),
    }


def _seed_fixture(tmp_dirs) -> None:
    """Three high-edge prop bets that pass min_edge=0.03 — same on both
    modes because predictions_cache doesn't depend on the m2_family flag."""
    _write_preds(tmp_dirs["cache"], [
        _mk_pred("Alpha One",  "pts", 28.0, 22.0, 34.0, team="AAA"),
        _mk_pred("Bravo Two",  "reb",  9.0,  6.0, 12.0, team="BBB"),
        _mk_pred("Charlie Tre", "ast", 7.0, 4.0, 10.0, team="CCC"),
    ])
    _write_lines(tmp_dirs["lines"], "bov", [
        _mk_line("Alpha One", "pts", 18.5, over_price=-110, under_price=+100),
        _mk_line("Bravo Two", "reb",  5.5, over_price=-110, under_price=+100),
        _mk_line("Charlie Tre", "ast", 4.5, over_price=-110, under_price=+100),
    ])


# --------------------------------------------------------------------------- #
# Test 1: Both modes produce non-empty recs.                                   #
# --------------------------------------------------------------------------- #
def test_both_modes_produce_recs(tmp_dirs):
    _seed_fixture(tmp_dirs)
    cmp_payload = compare_modes(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.03,
        top_overlap_k=(5, 10),
        predictions_path=tmp_dirs["preds_path"],
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=tmp_dirs["injury_path"],
    )
    assert cmp_payload["multi5"]["n_recs"] >= 1
    assert cmp_payload["mlp"]["n_recs"] >= 1
    assert isinstance(cmp_payload["top_multi5"], list)
    assert isinstance(cmp_payload["top_mlp"], list)
    assert len(cmp_payload["top_multi5"]) >= 1
    assert len(cmp_payload["top_mlp"]) >= 1


# --------------------------------------------------------------------------- #
# Test 2: Comparison payload structure is correct.                             #
# --------------------------------------------------------------------------- #
def test_compare_payload_structure(tmp_dirs):
    _seed_fixture(tmp_dirs)
    cmp_payload = compare_modes(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.03,
        top_overlap_k=(5, 10, 20),
        predictions_path=tmp_dirs["preds_path"],
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=tmp_dirs["injury_path"],
    )
    # Top-level keys
    for k in (
        "generated_at", "date", "bankroll", "top", "min_edge",
        "top_overlap_k", "multi5", "mlp", "overlap", "shared_bets",
        "only_in_multi5", "only_in_mlp", "top_multi5", "top_mlp",
        "operator_would_change_bets",
    ):
        assert k in cmp_payload, f"missing key {k}"
    # Overlap buckets
    assert "top_5"  in cmp_payload["overlap"]
    assert "top_10" in cmp_payload["overlap"]
    assert "top_20" in cmp_payload["overlap"]
    for bucket in cmp_payload["overlap"].values():
        for k in ("k", "n_a", "n_b", "overlap", "jaccard"):
            assert k in bucket
        assert 0.0 <= bucket["jaccard"] <= 1.0
    # Shared bets aggregates
    for k in (
        "n_shared", "mean_edge_delta", "mean_abs_edge_delta",
        "mean_kelly_delta", "mean_abs_kelly_delta",
        "total_stake_delta", "total_abs_stake_delta", "per_bet",
    ):
        assert k in cmp_payload["shared_bets"]


# --------------------------------------------------------------------------- #
# Test 3: Jaccard math (pure helper).                                          #
# --------------------------------------------------------------------------- #
def test_jaccard_math():
    # Identical sets -> 1.0
    assert jaccard([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    # Disjoint -> 0.0
    assert jaccard([1, 2, 3], [4, 5, 6]) == pytest.approx(0.0)
    # Partial overlap: |{1,2,3} ∩ {2,3,4}| = 2, |∪| = 4 -> 0.5
    assert jaccard([1, 2, 3], [2, 3, 4]) == pytest.approx(0.5)
    # Empty / empty -> 1.0 (degenerate but consistent)
    assert jaccard([], []) == pytest.approx(1.0)
    # One empty, one non-empty -> 0.0
    assert jaccard([1], []) == pytest.approx(0.0)
    # Dedup behavior (sets)
    assert jaccard([1, 1, 2], [2, 2, 1]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Test 4: Empty in one mode handled gracefully.                                #
# --------------------------------------------------------------------------- #
def test_empty_one_side_is_graceful(tmp_dirs):
    # Build a fixture with NO predictions cache so both modes return zero
    # recs — the comparison must still produce a valid payload.
    missing_preds = os.path.join(tmp_dirs["cache"], "does_not_exist.parquet")
    cmp_payload = compare_modes(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.03,
        top_overlap_k=(5, 10),
        predictions_path=missing_preds,
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=tmp_dirs["injury_path"],
    )
    assert cmp_payload["multi5"]["n_recs"] == 0
    assert cmp_payload["mlp"]["n_recs"] == 0
    # No bets in either side -> set algebra both empty, jaccard=1.0 by convention.
    assert cmp_payload["overlap"]["top_5"]["jaccard"] == pytest.approx(1.0)
    assert cmp_payload["overlap"]["top_5"]["overlap"] == 0
    # Manually constructed asymmetric case via topk_overlap.
    bucket = topk_overlap(
        [{"player": "X", "stat": "pts", "side": "OVER",
          "book": "bov", "line": 10.5}],
        [],
        5,
    )
    assert bucket["jaccard"] == pytest.approx(0.0)
    assert bucket["overlap"] == 0
    assert bucket["n_a"] == 1 and bucket["n_b"] == 0


# --------------------------------------------------------------------------- #
# Test 5: Same date/bankroll/top -> reproducible.                              #
# --------------------------------------------------------------------------- #
def test_compare_is_reproducible(tmp_dirs):
    _seed_fixture(tmp_dirs)
    kw = dict(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.03,
        top_overlap_k=(5, 10),
        predictions_path=tmp_dirs["preds_path"],
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=tmp_dirs["injury_path"],
    )
    a = compare_modes(**kw)
    b = compare_modes(**kw)
    # Drop the non-deterministic `generated_at` timestamp.
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    # JSON-roundtrip to normalise tuple-vs-list distinctions.
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(
        b, sort_keys=True, default=str
    )


# --------------------------------------------------------------------------- #
# Test 6: Env-flag inheritance is fresh-per-call (engine reads os.environ).    #
# --------------------------------------------------------------------------- #
def test_env_flag_inherited_per_call(monkeypatch):
    from src.prediction.game_models import _m2_family_use_mlp
    monkeypatch.delenv("M2_FAMILY_USE_MLP", raising=False)
    assert _m2_family_use_mlp() is False
    monkeypatch.setenv("M2_FAMILY_USE_MLP", "1")
    assert _m2_family_use_mlp() is True
    monkeypatch.setenv("M2_FAMILY_USE_MLP", "0")
    assert _m2_family_use_mlp() is False
    monkeypatch.setenv("M2_FAMILY_USE_MLP", "true")
    assert _m2_family_use_mlp() is True
    monkeypatch.setenv("M2_FAMILY_USE_MLP", "")
    assert _m2_family_use_mlp() is False


# --------------------------------------------------------------------------- #
# Test 7: top_overlap_k drives the buckets emitted.                            #
# --------------------------------------------------------------------------- #
def test_top_overlap_k_controls_buckets(tmp_dirs):
    _seed_fixture(tmp_dirs)
    cmp_payload = compare_modes(
        bankroll=1000.0, top=10, date=DATE, min_edge=0.03,
        top_overlap_k=(3, 7),
        predictions_path=tmp_dirs["preds_path"],
        lines_dir=tmp_dirs["lines"],
        injury_parquet_path=tmp_dirs["injury_path"],
    )
    assert set(cmp_payload["overlap"].keys()) == {"top_3", "top_7"}
    assert cmp_payload["top_overlap_k"] == [3, 7]


# --------------------------------------------------------------------------- #
# Test 8: Side-by-side compare against synthetic divergent rec lists.          #
# --------------------------------------------------------------------------- #
def test_synthetic_divergent_recs_quantify_change():
    # Two disjoint sets of recs; verify topk_overlap + overlap_deltas math.
    recs_a = [
        {"player": "P1", "stat": "pts", "side": "OVER",  "book": "bov",
         "line": 18.5, "edge": 0.05, "kelly_pct": 0.02, "stake_dollars": 20.0},
        {"player": "P2", "stat": "reb", "side": "OVER",  "book": "bov",
         "line":  5.5, "edge": 0.04, "kelly_pct": 0.02, "stake_dollars": 18.0},
    ]
    recs_b = [
        {"player": "P1", "stat": "pts", "side": "OVER",  "book": "bov",
         "line": 18.5, "edge": 0.08, "kelly_pct": 0.03, "stake_dollars": 28.0},
        {"player": "P3", "stat": "ast", "side": "UNDER", "book": "fd",
         "line":  4.5, "edge": 0.06, "kelly_pct": 0.025, "stake_dollars": 24.0},
    ]
    # topk_overlap@5 -> 1 shared (P1/pts/OVER/bov/18.5), 3 union, J = 1/3.
    bucket = topk_overlap(recs_a, recs_b, 5)
    assert bucket["overlap"] == 1
    # topk_overlap rounds jaccard to 4 decimals — widen tolerance accordingly.
    assert bucket["jaccard"] == pytest.approx(1.0 / 3.0, abs=1e-4)
    # overlap_deltas captures the edge / stake delta on the shared bet.
    deltas = overlap_deltas(recs_a, recs_b)
    assert deltas["n_shared"] == 1
    assert deltas["mean_edge_delta"] == pytest.approx(0.03, abs=1e-4)
    assert deltas["total_stake_delta"] == pytest.approx(8.0, abs=1e-6)
    assert deltas["per_bet"][0]["player"] == "P1"
    # _bet_key normalises case + rounds line.
    k1 = _bet_key({"player": "Alpha", "stat": "PTS", "side": "over",
                    "book": "BOV", "line": 18.499999})
    k2 = _bet_key({"player": "alpha", "stat": "pts", "side": "OVER",
                    "book": "bov", "line": 18.5})
    assert k1 == k2
