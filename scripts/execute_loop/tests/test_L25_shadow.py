"""Tests for scripts/execute_loop/L25_ab_shadow.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L25_shadow.py -v
"""
from __future__ import annotations

import json
import math
import os
import sys
import types
from pathlib import Path

import pytest
import pandas as pd

# ---------------------------------------------------------------------------
# Project root on sys.path; stub heavy imports before loading the module
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

import scripts.execute_loop.L25_ab_shadow as L25  # noqa: E402

# ---------------------------------------------------------------------------
# Helper: redirect all I/O to tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_shadow(tmp_path, monkeypatch):
    """Redirect _SHADOW_ROOT and ledger paths to tmp directories."""
    shadow_root = str(tmp_path / "shadow")
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(L25, "_SHADOW_ROOT", shadow_root)
    monkeypatch.setattr(L25, "_REGISTRY_FILE", Path(shadow_root) / "_registry.json")
    monkeypatch.setattr(L25, "_LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(L25, "_BETS_FILE", ledger_dir / "bets.parquet")
    monkeypatch.setattr(L25, "_BETS_CSV", ledger_dir / "bets.csv")
    yield shadow_root, ledger_dir


# ---------------------------------------------------------------------------
# Helpers to build synthetic data
# ---------------------------------------------------------------------------
STATS = ["pts", "reb", "ast"]
GAMES = [f"00225{i:05d}" for i in range(50)]
PLAYERS = ["nikola jokic", "lebron james"]


def _make_bets_df(
    n_per_stat_player: int = 30,
    prod_noise: float = 0.0,
    actuals: dict | None = None,
) -> pd.DataFrame:
    """Build a synthetic bets DataFrame (mimicking L07 ledger)."""
    rows = []
    for stat in STATS:
        true_val = actuals[stat] if actuals else {"pts": 25.0, "reb": 10.0, "ast": 5.0}[stat]
        for i in range(n_per_stat_player):
            game_id = GAMES[i % len(GAMES)]
            rows.append({
                "game_id": game_id,
                "player": "nikola jokic",
                "stat": stat,
                "market": f"player_prop_{stat}",
                "actual_value": str(true_val),
                "model_q50": str(true_val + prod_noise),
                "status": "WON",
            })
    return pd.DataFrame(rows)


def _write_bets(ledger_dir: Path, df: pd.DataFrame) -> None:
    if L25._HAS_PARQUET:
        df.to_parquet(ledger_dir / "bets.parquet", index=False)
    else:
        df.to_csv(ledger_dir / "bets.csv", index=False)


def _dummy_predictor():
    pass


# ---------------------------------------------------------------------------
# Test 1 — round-trip: start → 60 record_predictions across 50 games → settle
# ---------------------------------------------------------------------------
def test_round_trip(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    run = L25.start_shadow("variant_rt", _dummy_predictor, n_games=50)
    assert run.variant_name == "variant_rt"
    assert run.n_games_target == 50

    # 60 predictions, cycling across 50 distinct game_ids
    for i in range(60):
        gid = GAMES[i % 50]
        L25.record_prediction("variant_rt", gid, "nikola jokic", "pts", float(25 + i * 0.1))

    preds = L25._load_predictions("variant_rt")
    assert len(preds) == 60

    # Build synthetic prod ledger — 50 games, actual=25, prod_q50=26 (prod MAE=1.0)
    bets = _make_bets_df(n_per_stat_player=50, prod_noise=1.0,
                         actuals={"pts": 25.0, "reb": 10.0, "ast": 5.0})
    _write_bets(ledger_dir, bets)

    summary = L25.settle_shadow("variant_rt")
    assert summary.n_predictions == 60
    assert len(summary.mae_per_stat) > 0, "mae_per_stat must be non-empty after settle"
    assert "pts" in summary.mae_per_stat


# ---------------------------------------------------------------------------
# Test 2 — PROMOTE: variant strictly closer to actuals than prod on all stats
# ---------------------------------------------------------------------------
def test_promote_verdict(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    ACTUALS = {"pts": 25.0, "reb": 10.0, "ast": 5.0}
    # prod_q50 is off by 2.0 on every stat
    bets = _make_bets_df(n_per_stat_player=40, prod_noise=2.0, actuals=ACTUALS)
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_promote", _dummy_predictor, n_games=30)

    # Shadow predictions: closer to actual (offset 0.5 < 2.0)
    for stat in STATS:
        true_val = ACTUALS[stat]
        for i in range(40):
            gid = GAMES[i % len(GAMES)]
            L25.record_prediction("v_promote", gid, "nikola jokic", stat, true_val + 0.5)

    result = L25.compare_to_prod("v_promote")
    assert result.verdict == "PROMOTE", (
        f"Expected PROMOTE but got {result.verdict}. per_stat={result.per_stat}"
    )
    for stat, row in result.per_stat.items():
        assert row["delta"] < 0, f"stat={stat} delta={row['delta']} should be negative"


# ---------------------------------------------------------------------------
# Test 3 — REJECT: one stat has variant_mae > prod_mae with n >= 30
# ---------------------------------------------------------------------------
def test_reject_verdict(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    ACTUALS = {"pts": 25.0, "reb": 10.0, "ast": 5.0}
    # prod_q50 off by 1.0
    bets = _make_bets_df(n_per_stat_player=40, prod_noise=1.0, actuals=ACTUALS)
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_reject", _dummy_predictor, n_games=30)

    for stat in STATS:
        true_val = ACTUALS[stat]
        for i in range(40):
            gid = GAMES[i % len(GAMES)]
            if stat == "pts":
                # worse than prod: offset 3.0 vs prod 1.0
                pred = true_val + 3.0
            else:
                # better than prod: offset 0.3 < 1.0
                pred = true_val + 0.3
            L25.record_prediction("v_reject", gid, "nikola jokic", stat, pred)

    result = L25.compare_to_prod("v_reject")
    assert result.verdict == "REJECT", (
        f"Expected REJECT but got {result.verdict}. per_stat={result.per_stat}"
    )


# ---------------------------------------------------------------------------
# Test 4 — INCONCLUSIVE: mixed signs + small n
# ---------------------------------------------------------------------------
def test_inconclusive_verdict(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    ACTUALS = {"pts": 25.0, "reb": 10.0, "ast": 5.0}
    # Only 10 rows per stat — below n=30 threshold
    bets = _make_bets_df(n_per_stat_player=10, prod_noise=1.0, actuals=ACTUALS)
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_inc", _dummy_predictor, n_games=50)

    for stat in STATS:
        true_val = ACTUALS[stat]
        for i in range(10):
            gid = GAMES[i]
            L25.record_prediction("v_inc", gid, "nikola jokic", stat, true_val + 0.5)

    result = L25.compare_to_prod("v_inc")
    assert result.verdict == "INCONCLUSIVE", (
        f"Expected INCONCLUSIVE but got {result.verdict}"
    )


# ---------------------------------------------------------------------------
# Test 5 — predictor errors: 6 None records → registry status = "unstable"
# ---------------------------------------------------------------------------
def test_predictor_errors_mark_unstable(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    L25.start_shadow("v_errs", _dummy_predictor, n_games=50)

    for i in range(6):
        L25.record_prediction("v_errs", GAMES[i], "nikola jokic", "pts", None)

    registry = L25._load_registry()
    assert registry["v_errs"]["status"] == "unstable", (
        f"Expected unstable, got {registry['v_errs']['status']}"
    )
    assert registry["v_errs"]["error_count"] >= 5


# ---------------------------------------------------------------------------
# Test 6 — name collision: second start_shadow with same name → ValueError
# ---------------------------------------------------------------------------
def test_name_collision_raises(isolated_shadow):
    L25.start_shadow("v_dup", _dummy_predictor, n_games=20)
    with pytest.raises(ValueError, match="already exists"):
        L25.start_shadow("v_dup", _dummy_predictor, n_games=20)


# ---------------------------------------------------------------------------
# Test 7 — isolation: no writes to data/ledger/bets.parquet
# ---------------------------------------------------------------------------
def test_isolation_no_ledger_writes(isolated_shadow, tmp_path):
    shadow_root, ledger_dir = isolated_shadow

    # Create the bets file so it has a known mtime before any shadow activity
    bets_parquet = ledger_dir / "bets.parquet"
    bets_csv = ledger_dir / "bets.csv"

    bets_df = _make_bets_df(n_per_stat_player=5, prod_noise=1.0)
    _write_bets(ledger_dir, bets_df)

    # Record mtime before shadow operations
    if bets_parquet.exists():
        mtime_before = bets_parquet.stat().st_mtime
        watch_path = bets_parquet
    else:
        mtime_before = bets_csv.stat().st_mtime
        watch_path = bets_csv

    # Perform shadow operations
    L25.start_shadow("v_iso", _dummy_predictor, n_games=5)
    for i in range(10):
        L25.record_prediction("v_iso", GAMES[i % 5], "nikola jokic", "pts", 25.0)
    L25.settle_shadow("v_iso")

    mtime_after = watch_path.stat().st_mtime
    assert mtime_after == mtime_before, (
        f"Ledger file was modified during shadow ops! "
        f"before={mtime_before} after={mtime_after}"
    )

    # Also confirm predictions land in the shadow dir
    pq = Path(shadow_root) / "v_iso" / "predictions.parquet"
    csv = Path(shadow_root) / "v_iso" / "predictions.csv"
    assert pq.exists() or csv.exists(), "Shadow predictions file not found"


# ---------------------------------------------------------------------------
# Extra: settle returns INCONCLUSIVE without writing summary.json when n < target
# ---------------------------------------------------------------------------
def test_settle_inconclusive_no_summary_written(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    bets = _make_bets_df(n_per_stat_player=5, prod_noise=1.0)
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_partial", _dummy_predictor, n_games=50)
    for i in range(5):
        L25.record_prediction("v_partial", GAMES[i], "nikola jokic", "pts", 25.5)

    summary = L25.settle_shadow("v_partial")
    assert summary.promotion_recommendation == "INCONCLUSIVE"

    # summary.json should NOT exist yet
    summary_path = Path(shadow_root) / "v_partial" / "summary.json"
    assert not summary_path.exists(), "summary.json must not be written for INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Extra: empty join after settle → INCONCLUSIVE with reason
# ---------------------------------------------------------------------------
def test_settle_empty_join_inconclusive(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    # Prod ledger has game_id "99999" — shadow has game_id "00001" (no overlap)
    bets_rows = [{
        "game_id": "99999", "player": "nikola jokic", "stat": "pts",
        "market": "player_prop_pts", "actual_value": "25.0",
        "model_q50": "26.0", "status": "WON",
    }]
    bets_df = pd.DataFrame(bets_rows)
    _write_bets(ledger_dir, bets_df)

    L25.start_shadow("v_nooverlap", _dummy_predictor, n_games=5)
    for i in range(5):
        L25.record_prediction("v_nooverlap", "00001", "nikola jokic", "pts", 25.0)

    summary = L25.settle_shadow("v_nooverlap")
    assert summary.promotion_recommendation == "INCONCLUSIVE"
    assert "no_overlap_with_prod" in str(summary.vs_production_mae_delta)


# ---------------------------------------------------------------------------
# Extra: NaN predicted_q50 is recorded but skipped in MAE computation
# ---------------------------------------------------------------------------
def test_nan_prediction_skipped_in_mae(isolated_shadow):
    shadow_root, ledger_dir = isolated_shadow

    bets = _make_bets_df(n_per_stat_player=35, prod_noise=1.0,
                         actuals={"pts": 25.0, "reb": 10.0, "ast": 5.0})
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_nan", _dummy_predictor, n_games=30)

    for i in range(35):
        gid = GAMES[i % len(GAMES)]
        if i < 5:
            # NaN predictions — should be excluded from MAE
            L25.record_prediction("v_nan", gid, "nikola jokic", "pts", float("nan"))
        else:
            L25.record_prediction("v_nan", gid, "nikola jokic", "pts", 25.5)

    summary = L25.settle_shadow("v_nan")
    assert "pts" in summary.mae_per_stat
    # MAE should be ~0.5 (from the non-NaN rows), not inf/nan
    assert not math.isnan(summary.mae_per_stat["pts"])
    assert summary.mae_per_stat["pts"] < 5.0


# ---------------------------------------------------------------------------
# Test v2: atomic write — summary.json written via tmp + replace (no partial)
# ---------------------------------------------------------------------------
def test_settle_summary_json_atomic(isolated_shadow):
    """summary.json must exist after settle and be valid JSON (atomic write)."""
    shadow_root, ledger_dir = isolated_shadow

    ACTUALS = {"pts": 25.0, "reb": 10.0, "ast": 5.0}
    bets = _make_bets_df(n_per_stat_player=35, prod_noise=1.0, actuals=ACTUALS)
    _write_bets(ledger_dir, bets)

    L25.start_shadow("v_atomic", _dummy_predictor, n_games=30)
    for stat in STATS:
        true_val = ACTUALS[stat]
        for i in range(35):
            gid = GAMES[i % len(GAMES)]
            L25.record_prediction("v_atomic", gid, "nikola jokic", stat, true_val + 0.3)

    summary = L25.settle_shadow("v_atomic")
    assert summary.promotion_recommendation in {"PROMOTE", "REJECT", "INCONCLUSIVE"}

    summary_path = Path(shadow_root) / "v_atomic" / "summary.json"
    assert summary_path.exists(), "summary.json must be written after settle with n >= target"

    # Must be valid JSON and contain expected keys
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "variant_name" in data
    assert "promotion_recommendation" in data
    assert "mae_per_stat" in data

    # No leftover .tmp file
    tmp_path = summary_path.with_suffix(".tmp.json")
    assert not tmp_path.exists(), ".tmp.json should not remain after atomic write"


# ---------------------------------------------------------------------------
# Test v2: shadow_compare_from_l41 — happy path with PROMOTE verdict
# ---------------------------------------------------------------------------
def test_shadow_compare_from_l41_promote(isolated_shadow):
    """shadow_compare_from_l41 surfaces PROMOTE when challenger beats prod on all stats."""
    shadow_root, ledger_dir = isolated_shadow

    ACTUALS = {"pts": 25.0, "reb": 10.0, "ast": 5.0}
    # prod is off by 2.0 — challenger off by 0.5 → challenger wins every stat
    bets = _make_bets_df(n_per_stat_player=40, prod_noise=2.0, actuals=ACTUALS)
    _write_bets(ledger_dir, bets)

    # Register both champion and challenger variants
    L25.start_shadow("champ_v1", _dummy_predictor, n_games=30)
    L25.start_shadow("chall_v2", _dummy_predictor, n_games=30)

    for stat in STATS:
        true_val = ACTUALS[stat]
        for i in range(40):
            gid = GAMES[i % len(GAMES)]
            # champion: same as prod (off by 2.0)
            L25.record_prediction("champ_v1", gid, "nikola jokic", stat, true_val + 2.0)
            # challenger: closer (off by 0.5)
            L25.record_prediction("chall_v2", gid, "nikola jokic", stat, true_val + 0.5)

    harness_report = {
        "champion_variant": "champ_v1",
        "challenger_variant": "chall_v2",
        "game_ids": list(GAMES[:40]),
    }
    result = L25.shadow_compare_from_l41(harness_report)

    assert result["challenger_variant"] == "chall_v2"
    assert result["champion_variant"] == "champ_v1"
    assert result["verdict"] == "PROMOTE", (
        f"Expected PROMOTE but got {result['verdict']}. "
        f"challenger_compare={result.get('challenger_compare')}"
    )
    assert result["challenger_compare"] is not None
    assert "per_stat" in result["challenger_compare"]


# ---------------------------------------------------------------------------
# Test v2: shadow_compare_from_l41 — no challenger → NO_CHALLENGER
# ---------------------------------------------------------------------------
def test_shadow_compare_from_l41_no_challenger(isolated_shadow):
    """shadow_compare_from_l41 returns NO_CHALLENGER when report has no challenger."""
    shadow_root, ledger_dir = isolated_shadow

    harness_report = {"champion_variant": "champ_only"}
    result = L25.shadow_compare_from_l41(harness_report)

    assert result["verdict"] == "NO_CHALLENGER"
    assert result["challenger_variant"] is None
    assert result["challenger_compare"] is None
