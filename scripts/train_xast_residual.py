"""
train_xast_residual.py — A3 xAST residual head v2 trainer (EARLY STOP stub).

This script is the intended trainer for the xAST residual head.
It was NOT executed because build_xast_v2.py triggered the early-stop criteria:

  1. corr(potential_assists_l5_prior, target_ast) = -0.1284 to -0.0264
     across all threshold cuts. Recipe requires >= 0.20. FAIL.
  2. Fold-4 holdout coverage at n_cv_prior>=5 = 6.3%.
     Recipe requires >= 25%. FAIL.

The early-stop is definitive: no reformulation as a residual head corrects a
broken input signal. See vault/Intelligence/INT-51_xAST_residual.md.

If CV data expands to 500+ games with verified potential_assists attribution,
re-run build_xast_v2.py first. If corr >= 0.20, uncomment and run the trainer
below.

Usage (when unblocked):
    conda activate basketball_ai
    python scripts/train_xast_residual.py
"""
from __future__ import annotations

import logging
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

EARLY_STOP_REASON = (
    "corr(pa_l5_prior, target_ast) = -0.1284 < 0.20 threshold (recipe early-stop). "
    "CV potential_assists has negative correlation with target AST at n=241 games. "
    "Fold-4 coverage at n_cv_prior>=5 = 6.3% < 25% required by ship gate."
)


def main() -> None:
    log.error("EARLY STOP — training blocked.")
    log.error(EARLY_STOP_REASON)
    log.info("See vault/Intelligence/INT-51_xAST_residual.md for full analysis.")
    log.info("Re-run build_xast_v2.py after CV data expands to 500+ games.")
    sys.exit(0)


# ── Trainer stub (uncomment when unblocked) ──────────────────────────────────
# The recipe below is preserved for future use when the data constraint is lifted.

"""
RECIPE (preserved for future implementation):

Target: AST residual = target_ast - oof_ast_pred
  - If OOF parquet exists at data/models/prop_pergame_oof.parquet, use it.
  - Otherwise fall back to mean(l5_ast, ewma_ast) as base prediction.

Features (all strictly time-ordered, no leakage):
  CV last-5 prior (n_cv_prior >= 5):
    - potential_assists_l5 (mean of last 5 prior games)
    - touches_per_game_l5
    - paint_dwell_pct_l5
    - possession_duration_avg_l5
    - pa_per_touch = potential_assists_l5 / max(touches_per_game_l5, 0.1)  [safe-div]

  Player atlas priors (from player_fingerprints.parquet):
    - archetype one-hot: top 5 archetypes by NAME string (not cluster ID)
      ["Versatile Forward", "Off-Ball Forward", "Versatile Perimeter Player",
       "Versatile Big", "Perimeter Shooter (Contested)"]
    - dist_from_centroid (from player_fingerprints)

  Streak/drift (from streak_signatures.parquet, archetype_drift.parquet):
    - z_ast: AST z-score from streak_signatures (shift(1) to avoid leakage)
    - consistency_score from archetype_drift

  Context (NBA priors — all shift(1)):
    - is_home, rest_days, opp_def_ast, bbref_ast_pct, l5_min, ewma_min

Training:
  - LGB-q50 (alpha=0.5 pinball loss)
  - 4-fold WF, expanding train, contiguous holdout
  - Sort by game_date ascending

Ship gate:
  1. >= 3/4 WF folds positive (mae_cv < mae_base, delta < -0.001)
  2. AST MAE <= 1.3509 (strictly below 1.3559 by 0.005)
  3. Fold-4 coverage >= 25% non-default
  4. No regression >0.5pp on {pts, reb, fg3m, stl, blk, tov}
"""

if __name__ == "__main__":
    main()
