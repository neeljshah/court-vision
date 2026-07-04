"""domains.baseball_npb.elo_config -- Elo + walk-forward constants for ratings.py.

NPB-calibrated values, mirroring domains/basketball_wnba/elo_config.py (thin,
sport-specific config; the replay engine itself lives in ratings.py).

Fit method (walk-forward grid search on the REAL 2022-2023 npb_results.parquet
corpus, 648 non-tied games after excluding 14 draws -- train-past-only at
every step, ratings updated AFTER scoring so no peeking forward is possible):
grid K in {10,15,20,25,30} x HFA in {10,20,30,40,50} x SEASON_REGRESS in
{0.25,0.35} (the WNBA-lane grid shape), scored by mean walk-forward log-loss.
Run 2026-07-04 on that grid:
  argmin = K=10, HFA=30, SEASON_REGRESS=0.35 -> walk-forward logloss 0.69502
  baselines on the SAME 648-game corpus: coin-flip (p=0.5) logloss 0.69315,
  home-prior-only (constant p=0.54167, the corpus home-win rate) logloss
  0.68967.

HONEST RESULT ON THE FIT WINDOW: Elo LOSES to BOTH baselines on this grid
(0.69502 > 0.69315 > 0.68967) -- opposite of the WNBA outcome. A follow-up
wider sweep (K down to 2, HFA 0-30, REGRESS up to 1.0) found the true
unconstrained argmin at K=2, HFA=30, REGRESS=1.0 -> logloss 0.69019, which
STILL trails home-prior (0.68967) and only barely edges coin-flip.
Interpretation: at K=2 the model has nearly stopped learning team strength
altogether (SEASON_REGRESS=1.0 means a full reset every season) -- the search
is telling us there is no separable persistent-team-strength signal in this
648-game window that Elo can exploit beyond the constant home-rate prior.
This module keeps the WNBA-grid argmin (K=10/HFA=30/REGRESS=0.35) as the
shipped constants (not the degenerate K=2 unconstrained optimum) since a K=2
config would make the Elo signal indistinguishable from a constant.

HELD-OUT GATE RESULT (2026-07-04, see pregame_gate_verdict.json): scored with
THESE shipped constants on 2024 (336 games, 9 ties excluded) and 2025+2026
combined (507 games, 16 ties excluded) -- corpora the grid search was NOT fit
on -- Elo actually BEATS both coin-flip and home-prior on both corpora
(logloss 0.69036 vs 0.69315/0.69210 on 2024; 0.68892 vs 0.69315/0.68966 on
2025+2026) -> verdict CALIBRATION_BASELINE_OK. This is consistent with the
2022-2023 fit-window result being a genuinely noisy 648-game sample (the
narrow fit-window loss to baselines does not reproduce on the larger held-out
corpora) rather than the constants being mistuned. Both results are recorded
honestly: the grid search itself found no clear win on its own fit window,
but the resulting constants generalize acceptably out-of-sample.
"""
from __future__ import annotations

# K-factor: grid-search argmin on the WNBA-shaped grid (see module docstring).
# NPB plays a ~143-game season (MLB-like length) -- K=10 sits at the LOW end
# of the searched range; the wider unconstrained sweep pushed even lower
# (K=2), which is itself evidence of weak separable team-strength signal in
# the 2022-2023 fit window (see the HONEST RESULT note above). The held-out
# 2024/2025/2026 gate run with K=10 beats both baselines regardless.
ELO_K: float = 10.0

# Prior mean Elo for an unseen franchise (same convention as NBA/WNBA/MLB:
# 1500 anchor).
ELO_MEAN: float = 1500.0

# Home-court advantage in Elo points. Grid-search argmin on the 2022-2023
# corpus (home_win rate ~54.2% among non-tied games).
ELO_HFA: float = 30.0

# Between-season regression toward ELO_MEAN. Grid-search argmin on the
# 2022-2023 corpus.
SEASON_REGRESS: float = 0.35
