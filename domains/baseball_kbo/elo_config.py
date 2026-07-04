"""domains.baseball_kbo.elo_config -- Elo + walk-forward constants for ratings.py.

KBO-calibrated values, mirroring domains/baseball_npb/elo_config.py (thin,
sport-specific config; the replay engine itself lives in ratings.py).

Fit method (walk-forward grid search on the REAL 2022-2023 kbo_results.parquet
corpus, 1,405 non-tied games after excluding 23 draws -- train-past-only at
every step, ratings updated AFTER scoring so no peeking forward is possible):
grid K in {10,15,20,25,30} x HFA in {10,20,30,40,50} x SEASON_REGRESS in
{0.25,0.35} (the same WNBA/NPB-lane grid shape), scored by mean walk-forward
log-loss. Run 2026-07-04 on that grid:
  argmin = K=10, HFA=10, SEASON_REGRESS=0.35 -> walk-forward logloss 0.68497
  baselines on the SAME 1,405-game corpus: coin-flip (p=0.5) logloss 0.69315,
  home-prior-only (constant p=0.51317, the corpus home-win rate) logloss
  0.69280.

HONEST RESULT ON THE FIT WINDOW: Elo BEATS both baselines on this grid
(0.68497 < 0.69280 < 0.69315) -- unlike the NPB lane, where the fit-window
grid search lost to both baselines. KBO's home-win rate in this window
(51.3%) is much closer to 50% than NPB's/MLB's typical ~54%, so HFA=10 (the
low end of the searched range) winning the grid is consistent with a
genuinely weaker home-field effect in this corpus, not a search artifact.

HELD-OUT GATE RESULT (2026-07-04, see pregame_gate_verdict.json): scored with
THESE shipped constants on 2024 (709 games, 8 ties excluded) and 2025+2026
combined (1,113 games, 30 ties excluded) -- corpora the grid search was NOT
fit on -- verdict is PARTIAL, not CALIBRATION_BASELINE_OK: 2024 alone beats
both coin-flip (brier 0.24983 vs 0.25) and home-prior (0.24983 vs 0.24985)
but its Brier-skill-vs-coin (0.00069) trips the BSS_MIN=0.003 degenerate-base
guard -- too little separable signal in that corpus alone to trust. The
2025+2026 corpus beats both baselines cleanly and non-degenerate (brier
0.24701 vs coin 0.25 vs home-prior 0.24971; bss_vs_coin=0.01197). Recorded
honestly as PARTIAL, not upgraded to a clean pass.
"""
from __future__ import annotations

# K-factor: grid-search argmin on the WNBA/NPB-shaped grid (see module
# docstring). KBO plays a ~144-game season (MLB-like length) -- K=10 sits at
# the LOW end of the searched range, same as NPB's shipped constant.
ELO_K: float = 10.0

# Prior mean Elo for an unseen franchise (same convention as NBA/WNBA/MLB/NPB:
# 1500 anchor).
ELO_MEAN: float = 1500.0

# Home-court advantage in Elo points. Grid-search argmin on the 2022-2023
# corpus -- lower than NPB's (30) because the KBO fit-window home-win rate
# (51.3%) is closer to 50% than NPB's/MLB's typical ~54%.
ELO_HFA: float = 10.0

# Between-season regression toward ELO_MEAN. Grid-search argmin on the
# 2022-2023 corpus.
SEASON_REGRESS: float = 0.35
