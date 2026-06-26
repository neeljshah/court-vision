"""domains.mlb.totals_sp_park_eval -- Leak-free eval: park factor + SP RA-asof on MLB totals.

QUESTION
--------
Does adding a leak-free PARK factor and STARTING-PITCHER runs-allowed-as-of to the
walk-forward run-rate total-runs projection improve held-out total-runs prediction vs
the run-rate-only baseline?

Context: SP-form was REJECTED for moneyline/win-prob (subsumed by team Elo). TOTALS is
a distinct unanswered question. Expected outcome is likely also a small/neutral REJECT
because the market is efficient -- this module measures the REAL number either way.

DESIGN
------
- v0 baseline: linear fit on the walk-forward lam_v0 alone (from _build_wf_lambdas).
- v1 combo:  linear fit on lam_v0 + park_c + sp_comb_c (centered on TRAIN half only).
- Planted-null check: permute park_c + sp_comb_c with fixed seed; if the true lift
  is only as good as noise, the signal is not real.
- SHIP only if rmse_delta <= -0.05 runs AND null_delta >= rmse_delta + 0.03.
  (Deliberately strict; market efficiency makes REJECT the expected honest result.)

HONEST: calibration only. REJECT is a SUCCESS. No edge claimed. No $ field anywhere.
INVARIANTS: build only under domains/mlb/; never edit src/ kernel/ api/; <=300 LOC.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from domains.mlb.totals_sigma_wf import _build_wf_lambdas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = _REPO_ROOT / "data" / "domains" / "mlb"
_GATE_DIR = _REPO_ROOT / "data" / "frontend" / "funnel"
_GATE_FILE = _GATE_DIR / "mlb_totals_sp_park_gate.json"

_REQUIRED_SP_STARTS = 3   # minimum prior starts before a row is valid
_SHIP_DELTA_THRESH = -0.05  # rmse_delta must be <= this to SHIP (negative = combo better)
_NULL_MARGIN = 0.03        # null_delta must exceed rmse_delta by this margin
_NULL_SEED = 0             # fixed seed for planted-null permutation


# ---------------------------------------------------------------------------
# Public: load corpus
# ---------------------------------------------------------------------------

def load_corpus() -> pd.DataFrame:
    """Load and join games + asof_park + asof_features; sort by (date, event_id).

    Returns a DataFrame with columns:
      event_id, date, season, home_team, away_team, home_runs, away_runs,
      park_factor, home_sp_ra_asof, away_sp_ra_asof,
      home_sp_starts_prior, away_sp_starts_prior.
    """
    games = pd.read_parquet(_DATA_ROOT / "games.parquet")
    park = pd.read_parquet(_DATA_ROOT / "asof_park.parquet")
    feats = pd.read_parquet(_DATA_ROOT / "asof_features.parquet")

    df = (
        games
        .merge(park[["event_id", "park_factor"]], on="event_id", how="left")
        .merge(
            feats[[
                "event_id",
                "home_sp_ra_asof", "away_sp_ra_asof",
                "home_sp_starts_prior", "away_sp_starts_prior",
            ]],
            on="event_id",
            how="left",
        )
    )

    sort_cols = ["date", "game_seq"] if "game_seq" in df.columns else ["date", "event_id"]
    df = df.sort_values(sort_cols).reset_index(drop=True)

    keep = [
        "event_id", "date", "season", "home_team", "away_team",
        "home_runs", "away_runs",
        "park_factor", "home_sp_ra_asof", "away_sp_ra_asof",
        "home_sp_starts_prior", "away_sp_starts_prior",
    ]
    return df[keep]


# ---------------------------------------------------------------------------
# Internal: OLS helpers
# ---------------------------------------------------------------------------

def _fit_ols(X_train: np.ndarray, y_train: np.ndarray) -> np.ndarray:
    """Fit OLS (with intercept prepended in X_train). Returns coef array."""
    coef, _, _, _ = np.linalg.lstsq(X_train, y_train, rcond=None)
    return coef


def _rmse(pred: np.ndarray, actual: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - actual) ** 2)))


def _mae(pred: np.ndarray, actual: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - actual)))


# ---------------------------------------------------------------------------
# Public: evaluate
# ---------------------------------------------------------------------------

def evaluate() -> Dict:
    """Run the full leak-free eval and return a results dict.

    Steps
    -----
    1. Load corpus; build walk-forward lambdas (aligned to corpus row order).
    2. Define valid-feature mask (finite park_factor, sp_ra_asof, min starts>=3).
    3. Split: first 50% of rows by date = TRAIN; last 50% = TEST.
    4. Center park_c and sp_comb_c using TRAIN mean (no test-set leak).
    5. Fit v0 (lam only) and v1 (lam + park_c + sp_comb_c) on TRAIN subset.
    6. Score both on TEST subset (valid rows only).
    7. Planted-null: permute park_c + sp_comb_c, refit v1_null, score.
    8. Apply SHIP/REJECT thresholds and write gate JSON.
    """
    df = load_corpus()
    n_total = len(df)

    # Walk-forward lambdas -- aligned to df row order (df already sorted by date)
    lam_v0, actual = _build_wf_lambdas(df)

    # Valid-feature mask
    park_f = df["park_factor"].to_numpy(dtype=float)
    h_ra = df["home_sp_ra_asof"].to_numpy(dtype=float)
    a_ra = df["away_sp_ra_asof"].to_numpy(dtype=float)
    h_starts = df["home_sp_starts_prior"].to_numpy(dtype=float)
    a_starts = df["away_sp_starts_prior"].to_numpy(dtype=float)

    valid_mask = (
        np.isfinite(park_f)
        & np.isfinite(h_ra)
        & np.isfinite(a_ra)
        & (h_starts >= _REQUIRED_SP_STARTS)
        & (a_starts >= _REQUIRED_SP_STARTS)
    )

    # Chronological 50/50 split (indices into df)
    mid = n_total // 2
    train_idx = np.arange(mid)
    test_idx = np.arange(mid, n_total)

    train_valid = valid_mask[train_idx]
    test_valid = valid_mask[test_idx]

    # Build raw features for all rows (centering applied after)
    sp_comb = h_ra + a_ra  # combined SP runs-allowed-as-of

    # Center using TRAIN mean (train_valid subset only)
    park_train_mean = float(np.mean(park_f[train_idx][train_valid]))
    sp_train_mean = float(np.mean(sp_comb[train_idx][train_valid]))

    park_c = park_f - park_train_mean
    sp_comb_c = sp_comb - sp_train_mean

    # TRAIN arrays (valid rows only)
    lam_tr = lam_v0[train_idx][train_valid]
    act_tr = actual[train_idx][train_valid]
    park_tr = park_c[train_idx][train_valid]
    sp_tr = sp_comb_c[train_idx][train_valid]

    # TEST arrays (valid rows only)
    lam_te = lam_v0[test_idx][test_valid]
    act_te = actual[test_idx][test_valid]
    park_te = park_c[test_idx][test_valid]
    sp_te = sp_comb_c[test_idx][test_valid]

    n_test = int(len(act_te))
    coverage = float(valid_mask.mean())

    # --- v0: actual ~ 1 + lam_v0 ---
    X_v0_tr = np.column_stack([np.ones(len(lam_tr)), lam_tr])
    X_v0_te = np.column_stack([np.ones(len(lam_te)), lam_te])
    coef_v0 = _fit_ols(X_v0_tr, act_tr)
    pred_v0_te = X_v0_te @ coef_v0

    rmse_base = _rmse(pred_v0_te, act_te)
    mae_base = _mae(pred_v0_te, act_te)

    # --- v1: actual ~ 1 + lam_v0 + park_c + sp_comb_c ---
    X_v1_tr = np.column_stack([np.ones(len(lam_tr)), lam_tr, park_tr, sp_tr])
    X_v1_te = np.column_stack([np.ones(len(lam_te)), lam_te, park_te, sp_te])
    coef_v1 = _fit_ols(X_v1_tr, act_tr)
    pred_v1_te = X_v1_te @ coef_v1

    rmse_combo = _rmse(pred_v1_te, act_te)
    mae_combo = _mae(pred_v1_te, act_te)
    rmse_delta = rmse_combo - rmse_base

    # --- Planted-null: permute park_c and sp_comb_c on TRAIN, refit v1 ---
    rng = np.random.default_rng(_NULL_SEED)
    n_tr = len(lam_tr)
    perm = rng.permutation(n_tr)
    park_tr_null = park_tr[perm]
    sp_tr_null = sp_tr[perm]

    X_null_tr = np.column_stack([np.ones(n_tr), lam_tr, park_tr_null, sp_tr_null])
    coef_null = _fit_ols(X_null_tr, act_tr)
    # Test features stay un-permuted (we're testing the null fit's predictive power)
    pred_null_te = X_v1_te @ coef_null
    rmse_combo_null = _rmse(pred_null_te, act_te)
    null_delta = float(rmse_combo_null - rmse_base)

    # --- SHIP/REJECT ---
    real_lift = bool(rmse_delta <= _SHIP_DELTA_THRESH)
    null_separation = bool(null_delta >= rmse_delta + _NULL_MARGIN)
    verdict = "SHIP" if (real_lift and null_separation) else "REJECT"

    if verdict == "SHIP":
        reason = (
            f"rmse_delta={rmse_delta:.4f} runs (<= {_SHIP_DELTA_THRESH}) "
            f"and null_delta={null_delta:.4f} clearly exceeds real lift."
        )
    else:
        reason = (
            f"park+SP_RA combo rmse_delta={rmse_delta:.4f} runs "
            f"(threshold <= {_SHIP_DELTA_THRESH}); "
            f"planted_null_delta={null_delta:.4f}; "
            f"market efficiency subsumes this feature combination."
        )

    result: Dict = {
        "layer": "mlb_totals_sp_park",
        "design": (
            "leak-free WF run-rate lambda baseline vs +park_factor+SP_RA_asof OLS blend; "
            "single chronological 50/50 split; "
            "honest single-fold (not yet cross-corpus/DM)"
        ),
        "n_games": int(n_total),
        "n_test": n_test,
        "rmse_base": round(float(rmse_base), 5),
        "rmse_combo": round(float(rmse_combo), 5),
        "rmse_delta": round(float(rmse_delta), 5),
        "mae_base": round(float(mae_base), 5),
        "mae_combo": round(float(mae_combo), 5),
        "planted_null_delta": round(float(null_delta), 5),
        "coverage": round(coverage, 4),
        "verdict": verdict,
        "reason": reason,
        "vs_close": "UNPROVEN -- CALIBRATION only; no $ field",
        "proposal_only": True,
        "scouting_only": (verdict == "REJECT"),
        "force_fed": False,
    }

    # Atomic write to gate file
    _GATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(_GATE_DIR), prefix="mlb_totals_sp_park_", suffix=".json.tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="ascii") as fh:
            json.dump(result, fh, indent=2)
        os.replace(tmp_path, str(_GATE_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return result


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    r = evaluate()
    print("=" * 54)
    print("MLB Totals: park + SP-RA-asof vs run-rate baseline")
    print("=" * 54)
    print(f"  n_test         : {r['n_test']}")
    print(f"  coverage       : {r['coverage']:.3f}")
    print(f"  rmse_base      : {r['rmse_base']:.4f} runs")
    print(f"  rmse_combo     : {r['rmse_combo']:.4f} runs")
    print(f"  rmse_delta     : {r['rmse_delta']:.4f} runs")
    print(f"  null_delta     : {r['planted_null_delta']:.4f} runs")
    print(f"  mae_base       : {r['mae_base']:.4f} runs")
    print(f"  mae_combo      : {r['mae_combo']:.4f} runs")
    print("-" * 54)
    print(f"  VERDICT        : {r['verdict']}")
    print(f"  reason         : {r['reason']}")
    print("=" * 54)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
