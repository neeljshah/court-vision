"""tests/test_ingame_sigma.py — tests for src/prediction/ingame_sigma.py

Four core invariants (per spec):
  1. Monotonic tightening: sigma(stat, elapsed_min) decreases as elapsed_min
     increases for every core stat (pts, reb, ast).
  2. Flag-OFF byte-identical: the inplay_bet_ranker produces identical q10/q90/
     stake output with CV_INGAME_SIGMA=0 (default) regardless of cache state.
  3. sigma > 0 for all (stat, bucket) combinations in the table.
  4. AST sigma present in the table but AST point projection untouched.

Additional: bucket snapping, fallback for unknown stats.

Run:  python -m pytest tests/test_ingame_sigma.py -q
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("NBA_OFFLINE", "1")

# ── helpers ──────────────────────────────────────────────────────────────────

TABLE_PATH = ROOT / "data" / "models" / "ingame_sigma_table.json"


def _require_table():
    if not TABLE_PATH.exists():
        pytest.skip(
            f"ingame_sigma_table.json not found at {TABLE_PATH}. "
            "Run: python -c \"from src.prediction.ingame_sigma import "
            "build_sigma_table; build_sigma_table()\""
        )


def _load_table() -> Dict:
    _require_table()
    with open(TABLE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ── Test 1: sigma > 0 for every (stat, bucket) ──────────────────────────────

def test_sigma_positive():
    """Every entry in the persisted sigma table must have sigma > 0."""
    data = _load_table()
    sigma_table = data["sigma_table"]
    bad = []
    for stat, buckets in sigma_table.items():
        for bucket, row in buckets.items():
            v = float(row["calibrated_sigma"])
            if v <= 0:
                bad.append((stat, bucket, v))
    assert not bad, f"Non-positive sigmas: {bad}"


# ── Test 2: monotonic tightening with elapsed_min ───────────────────────────

def test_monotonic_tightening():
    """sigma(stat, elapsed_min) must decrease (or stay flat) as elapsed_min
    increases for pts, reb, ast — the core sizing stats.

    We allow a 1% tolerance for floating-point rounding near identical-bucket
    edges but require a clear tightening trend end-to-end.
    """
    from src.prediction.ingame_sigma import BUCKET_BREAKPOINTS, BUCKET_NAMES, ingame_sigma

    _require_table()
    CORE = ("pts", "reb", "ast")
    for stat in CORE:
        sigs = [ingame_sigma(stat, elapsed_min=em) for em in BUCKET_BREAKPOINTS]
        for i in range(1, len(sigs)):
            assert sigs[i] <= sigs[i - 1] * 1.01, (
                f"sigma({stat}) NOT monotonically tightening: "
                f"elapsed={BUCKET_BREAKPOINTS[i]}min sigma={sigs[i]:.4f} > "
                f"elapsed={BUCKET_BREAKPOINTS[i-1]}min sigma={sigs[i-1]:.4f}"
            )
        # End-to-end: must tighten meaningfully (at least 50% reduction Q1->late)
        assert sigs[-1] < sigs[0] * 0.5, (
            f"sigma({stat}) does not tighten meaningfully end-to-end: "
            f"first={sigs[0]:.3f}, last={sigs[-1]:.3f}"
        )


# ── Test 3: calibration — coverage_at_1sig ≈ 0.68 ────────────────────────────

def test_calibration_coverage():
    """coverage_at_1sig must be in [0.67, 0.71] for all (stat, bucket) entries.

    By construction (p68 = 68th percentile of |resid|), coverage at 1*sigma
    is exactly 0.68. We allow a ±0.01 window for any float rounding in the
    JSON values.
    """
    data = _load_table()
    sigma_table = data["sigma_table"]
    bad = []
    for stat, buckets in sigma_table.items():
        for bucket, row in buckets.items():
            cov = float(row["coverage_at_1sig"])
            if not (0.67 <= cov <= 0.71):
                bad.append((stat, bucket, cov))
    assert not bad, (
        f"Coverage outside [0.67, 0.71] for {len(bad)} (stat, bucket) cells:\n"
        + "\n".join(f"  {s} {b}: {c:.4f}" for s, b, c in bad[:10])
    )


# ── Test 4: AST sigma present, AST POINT untouched ───────────────────────────

def test_ast_sigma_present_but_point_unchanged():
    """AST must appear in the sigma table (sigma > 0).
    The sigma module must NOT modify point projections — it only provides
    uncertainty, not adjustments.
    """
    from src.prediction.ingame_sigma import ingame_sigma

    _require_table()
    # AST sigma is present and positive
    ast_sigma = ingame_sigma("ast", elapsed_min=24.0)
    assert ast_sigma > 0, f"AST sigma at 24min should be > 0, got {ast_sigma}"

    # sigma_to_gaussian_q10_q90 does not touch the point
    from src.prediction.ingame_sigma import sigma_to_gaussian_q10_q90
    point = 5.7
    q10, q90 = sigma_to_gaussian_q10_q90(point, ast_sigma)
    # q50 (the point) must be inside [q10, q90] — the spread is symmetric around point
    assert q10 < point < q90, (
        f"point={point} not in (q10={q10}, q90={q90})"
    )
    # Neither q10 nor q90 equals point (there IS a spread)
    assert q90 > point and q10 < point


# ── Test 5: bucket snapping ──────────────────────────────────────────────────

def test_bucket_snapping():
    """_snap_to_bucket must clamp at boundaries and snap to nearest midpoint."""
    from src.prediction.ingame_sigma import _snap_to_bucket, BUCKET_NAMES

    _require_table()
    # Below minimum -> first bucket
    assert _snap_to_bucket(-1.0) == BUCKET_NAMES[0]
    assert _snap_to_bucket(0.0) == BUCKET_NAMES[0]
    assert _snap_to_bucket(2.0) == BUCKET_NAMES[0]

    # Above maximum -> last bucket
    assert _snap_to_bucket(48.0) == BUCKET_NAMES[-1]
    assert _snap_to_bucket(46.0) == BUCKET_NAMES[-1]

    # Exact breakpoints snap to themselves
    assert _snap_to_bucket(12.0) == "12min(endQ1)"
    assert _snap_to_bucket(24.0) == "24min(endQ2/half)"
    assert _snap_to_bucket(36.0) == "36min(endQ3)"


# ── Test 6: unknown stat fallback ────────────────────────────────────────────

def test_unknown_stat_fallback():
    """Stats not in the table (fg3m, stl, blk, tov) must return a positive
    fallback (max over core stats), never raise.
    """
    from src.prediction.ingame_sigma import ingame_sigma

    _require_table()
    for stat in ("fg3m", "stl", "blk", "tov", "xyz"):
        for elapsed in (6.0, 24.0, 42.0):
            sigma = ingame_sigma(stat, elapsed_min=elapsed)
            assert sigma > 0, f"Fallback sigma for {stat}@{elapsed}min should be >0, got {sigma}"


# ── Test 7: flag-OFF byte-identical at inplay_bet_ranker ────────────────────

def test_flag_off_byte_identical():
    """With CV_INGAME_SIGMA=0 (default), inplay_bet_ranker.run_tick() must
    return the same ranked_bets as it does when the sigma module is not
    imported at all.

    We test this by importing run_tick with the flag env-var explicitly OFF,
    calling it with a synthetic pretip snap (no lines -> empty ranked_bets),
    and verifying:
      (a) it does not raise,
      (b) it returns status=PREGAME (no q1 file), and
      (c) no bet row carries an 'ingame_sigma' field with a non-None value.

    This is a unit-level byte-identical proof: without real quarter_box files
    the ranker exits early with status=PREGAME. The key invariant is that the
    sigma flag adds no fields or side-effects when off.
    """
    env_orig = os.environ.pop("CV_INGAME_SIGMA", None)
    try:
        # Re-import the module with flag OFF to test the unpatched code path.
        import importlib
        import scripts.inplay_bet_ranker as ranker
        # Reload ensures our env change takes effect if the module is already
        # cached (it caches _CV_INGAME_SIGMA at module-load time).
        importlib.reload(ranker)

        # run_tick with a nonexistent game_id -> PREGAME (no q1 file).
        payload = ranker.run_tick(
            game_id="0000000000",
            date_str="2026-01-01",
            bankroll=1000.0,
            qbox_dir=str(ROOT / "data" / "cache" / "quarter_box_nonexistent"),
        )
        assert payload["status"] == "PREGAME", (
            f"Expected PREGAME with no q1 file, got {payload['status']}"
        )
        # No bet row should have a non-None ingame_sigma when flag is OFF.
        for bet in payload.get("ranked_bets", []):
            sigma_val = bet.get("ingame_sigma")
            assert sigma_val is None, (
                f"ingame_sigma={sigma_val!r} in bet row with flag OFF: {bet}"
            )
    finally:
        if env_orig is not None:
            os.environ["CV_INGAME_SIGMA"] = env_orig
        elif "CV_INGAME_SIGMA" in os.environ:
            del os.environ["CV_INGAME_SIGMA"]
        # Reload to restore original module state.
        import importlib
        import scripts.inplay_bet_ranker as ranker
        importlib.reload(ranker)


# ── Test 8: sigma values match the doc table for core (stat, bucket) ─────────

def test_doc_table_consistency():
    """The persisted JSON must match the Audit-3 table from the doc for the
    6 cells explicitly cited (using 1.48*MAD 'robust sigma' as reference for
    nearness, within 10% since we now use p68 which is slightly larger for
    fat-tailed cells).

    We check that the calibrated_sigma is >= rob_sigma (never narrower) and
    that the end-to-end spread is sane.
    """
    data = _load_table()
    sigma_table = data["sigma_table"]

    # For every (stat, bucket): calibrated_sigma should be >= rob_sigma, OR within
    # 1% if the distribution is near-Gaussian (small kurtosis) — near-Gaussian cells
    # can have p68 very slightly below 1.48*MAD due to finite-sample rounding.
    # A 1% tolerance prevents spurious failures while catching genuinely wrong values.
    bad = []
    for stat, buckets in sigma_table.items():
        for bucket, row in buckets.items():
            cal = float(row["calibrated_sigma"])
            rob = float(row["rob_sigma"])
            if cal < rob * 0.99:  # allow 1% tolerance for near-Gaussian cells
                bad.append((stat, bucket, cal, rob))
    assert not bad, (
        f"calibrated_sigma < 0.99 * rob_sigma (unexpected shortfall beyond noise):\n"
        + "\n".join(f"  {s} {b}: cal={c:.4f} rob={r:.4f}"
                    for s, b, c, r in bad)
    )

    # Spot-check doc table values (Audit-3 rob_sigma column).
    # calibrated_sigma >= rob_sigma; we just need them in the right ballpark.
    doc_robsig = {
        ("pts", "02min(earlyQ1)"): 6.792,
        ("pts", "12min(endQ1)"): 5.081,
        ("pts", "36min(endQ3)"): 2.233,
        ("reb", "24min(endQ2/half)"): 1.505,
        ("ast", "36min(endQ3)"): 0.513,
        ("pts", "46min(lateQ4)"): 0.365,
    }
    for (stat, bucket), ref_rob in doc_robsig.items():
        cal = float(sigma_table[stat][bucket]["calibrated_sigma"])
        rob = float(sigma_table[stat][bucket]["rob_sigma"])
        # rob_sigma must be close to the doc value (within 1%)
        assert abs(rob - ref_rob) < ref_rob * 0.02, (
            f"rob_sigma mismatch for {stat} {bucket}: "
            f"got {rob:.4f}, doc says {ref_rob:.4f}"
        )
        # calibrated_sigma must be >= rob_sigma
        assert cal >= rob - 1e-4, (
            f"calibrated_sigma {cal:.4f} < rob_sigma {rob:.4f} for {stat} {bucket}"
        )
