"""
train_xreb_residual.py — A4 xREB residual head trainer (EARLY STOP stub).

This script is the intended trainer for the xREB residual head.
It was NOT executed because build_xreb_v2.py triggered the early-stop criteria:

  1. Fold-4 holdout coverage at n_cv_prior>=5 = 4.0%.
     Recipe requires >= 25%. FAIL.
  2. opp_paint_pct_allowed_z could not be joined (no opp_team tricode in
     prop_pergame rows); corr_opp_paint_z_vs_reb = N/A (treated as FAIL).

  Note: corr(paint_dwell_l5, target_reb) at n_cv_prior>=5 = 0.1514,
  which marginally PASSES the 0.15 threshold. However, this is computed
  on n=511 rows (0.5% global coverage) — a coverage that cannot support
  a meaningful LGB-q50 WF experiment.

The early-stop is definitive at this CV data scale.
See vault/Intelligence/INT-59_xREB_residual.md.

If CV tracking expands to cover 500+ games (fold-4 n_cv_prior>=5 >= 25%),
re-run build_xreb_v2.py first. If both probe gates pass, uncomment the
trainer recipe below.

Usage (when unblocked):
    conda activate basketball_ai
    python scripts/train_xreb_residual.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

EARLY_STOP_REASON = (
    "Fold-4 holdout coverage at n_cv_prior>=5 = 4.0% < 25.0% required by ship gate. "
    "Global coverage at n_cv_prior>=5 = 0.5% (n=511 rows / 101765 total). "
    "corr(paint_dwell_l5, target_reb) = 0.1514 (marginally above 0.15 threshold, "
    "but on a 511-row subset that cannot support 4-fold WF). "
    "opp_paint_pct_allowed_z join failed (no opp_team tricode in prop_pergame rows)."
)


def main() -> None:
    log.error("EARLY STOP — training blocked.")
    log.error(EARLY_STOP_REASON)
    log.info("See vault/Intelligence/INT-59_xREB_residual.md for full analysis.")
    log.info("Re-run build_xreb_v2.py after CV data expands to 500+ games.")
    sys.exit(0)


# ── Trainer recipe (preserved for future use when data gate is lifted) ────────
"""
RECIPE (preserved — implement when fold-4 n_cv_prior>=5 >= 25%):

Target: REB residual = target_reb - oof_reb_pred
  - If OOF parquet exists at data/models/prop_pergame_oof.parquet, use it.
  - Otherwise fall back to mean(l5_reb, ewma_reb) as base prediction.

Training filter:
  n_cv_prior >= 5 AND player_id in player_fingerprints

Features (all strictly time-ordered, no leakage):
  CV rolling (shift(1), last-N=5):
    - paint_dwell_pct_l5
    - touches_per_game_l5
    - shot_zone_paint_pct_l5
    - avg_off_ball_distance_l5  (if available)
    - avg_spacing_l5
    - n_cv_prior

  Player atlas (from player_fingerprints.parquet):
    - archetype one-hot by NAME string (not cluster ID):
      ["Versatile Big", "Off-Ball Big", "Stretch Big",
       "Versatile Forward", "Off-Ball Forward"]
    - dist_from_centroid

  C4 join (from opp_paint_allowance.parquet via get_opp_paint_allowance):
    - opp_paint_pct_allowed_z
    - opp_paint_dwell_pct_allowed_z
    - opp_paint_data_density (one-hot: high/med/low/league_prior)

  NBA priors (shift(1)):
    - is_home, rest_days, opp_reb_rate (opp_def_reb_l5), l5_min, ewma_min
    - bbref_height_inches (if available)

Training:
  - LGB-q50 (alpha=0.5 pinball loss)
  - 4-fold WF, expanding train, contiguous holdout
  - Sort by game_date ascending

Ship gate (all required):
  1. >= 3/4 WF folds positive on REB (mae_cv < mae_base)
  2. REB MAE <= 1.8993 (strictly < 1.9023 by >= 0.003)
  3. Fold-4 coverage >= 25%
  4. No regression >0.5pp on {PTS, AST, FG3M, STL, BLK, TOV}
  5. Null control (X3a): rerun WF with xreb_residual = zeros -> must give same
     or worse delta. If zeros give equal delta, REJECT (signal adds no info).
  6. PKL integrity: model.n_features_in_ MUST match meta JSON feature count.
  7. Train/inference parity: assert feature list identical in build and predict paths.

PKL integrity check pattern (do not skip):
  assert model.n_features_in_ == len(feature_names), (
      f"PKL integrity: model expects {model.n_features_in_} features, "
      f"meta has {len(feature_names)}"
  )
"""


if __name__ == "__main__":
    main()
