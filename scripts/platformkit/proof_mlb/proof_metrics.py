"""scripts.platformkit.proof_mlb.proof_metrics — Pure metric functions for the MLB moneyline proof.

All functions are stdlib + numpy + sklearn only.  No src.* or domains.* imports.

Design discipline (SECOND_DOMAIN_PROOF.md §4.3):
  - brier / ece / reliability_slope: evaluate raw-Elo calibration quality.
  - isotonic_calibrate: fit IsotonicRegression on train season, evaluate on held-out.
  - clv_sign_invariants: mechanical wiring checks (NOT edge claims).  The two
    invariants this checks are:
      (a) betting the close against itself → CLV ≡ 0 to float precision.
      (b) two-sided CLV is approximately anti-symmetric after devig.
    Both are PLUMBING correctness checks that guard the known sign-bug class
    (feedback_clv_sign_record_clv_backwards.md).  A passing result carries
    zero edge meaning.

Side convention: side A = home team / side B = away team (moneyline).

Re-exports the canonical sport-blind implementations from
kernel.validation.proof_metrics (kernel promotion, W-PROOFSWAP-001).
"""
from __future__ import annotations

from kernel.validation.proof_metrics import (  # noqa: F401
    brier,
    ece,
    reliability_slope,
    isotonic_calibrate,
    clv_sign_invariants,
    devig2 as _devig2,
)

__all__ = [
    "brier", "ece", "reliability_slope", "isotonic_calibrate",
    "_devig2", "clv_sign_invariants",
]
