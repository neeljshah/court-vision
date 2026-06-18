# NBA GET-TO-EDGE PLAN -- the prioritized path to a PROVEN edge

_Sport = NBA. The concrete, ordered path from today's state to a CALIBRATION-PROVEN (and
eventually CLV-PROVEN) edge in the beatable pockets, CUTTING the efficient ones. Each step:
approach + exactly how it is validated. Grounded in the deep-dives + the model-levers queue.
Honest framing: most steps prove CALIBRATION; $ is gated on forward paper CLV only. ASCII._

## State today (one line)
We can PRICE the whole NBA market surface coherently (marginal prop stack + MC sim joint) and
we MATCH the devigged close on team markets (CLV~0). We have NO keyless prop-line feed, NO
same-day freshness feed, and the in-game blend OOS is still SYNTHETIC. The pockets are
identified; the blockers are DATA + a few un-grafted but already-validated signals.

## STEP 0 (blocker) -- Wire a keyless PLAYER-PROP line feed  [TOP PRIORITY]
- WHY: props are the P1 pocket, but EV-vs-line is meaningless without lines. This is the single
  thing standing between "we can price props" and "we can find prop edges."
- APPROACH: scrape PrizePicks / Underdog public JSON + ESPN keyless prop pages into
  `prop_lines_<book>.parquet` keyed (date, player_id, stat, line, payout), snapshotted with a
  timestamp. Build under a SAFE dir (`scripts/platformkit/_scrapers/` or `domains/basketball_nba/`)
  -- propose a diff for any human-gated path, never auto-edit `src/`.
- VALIDATE: row coverage vs the slate; join rate to `player_boxscores.parquet` player_id; that
  the line snapshot timestamp < tip (leak-free). No edge claim yet -- this is plumbing.

## STEP 1 (quick win) -- Re-prove the AST prop edge leak-free, RAW
- WHY: AST is the ONE documented near-durable model divergence (~+7%, both directions). It must
  be re-measured on the current corpus, not asserted from history.
- APPROACH: `prop_pergame.predict_pergame('ast',...)` (kept OFF q50/isotonic on purpose) vs the
  AST prop line; rank by |model - line| on primary-creator roles; use `ast_edge_decomposition.py`.
- VALIDATE: leak-free WF P(over) calibration vs the devigged AST prop close -> BSS>0
  (CALIBRATION-PROVEN). Regular-season ONLY (exclude playoffs -- the edge dies there). >=2
  seasons (have 2024-25 + 2025-26 = 27,816 player-games). Then forward paper CLV vs the AST
  closing line -> CLV-PROVEN bar. NEVER reprint a historical ROI as current.

## STEP 2 (quick win) -- Graft the 5 already-VALIDATED signals
- WHY: `signal_lab_registry.parquet` has 5 signals that ALREADY passed the honest gate
  (pbp_origin_transition, rest_x_age, shot_clock_leverage, opp_position_defense_reb, oreb_matchup)
  but are NOT in the served schema (DEAD FUNNEL). These are the highest-probability real point wins.
- APPROACH: reviewed graft into the prop_pergame training schema -> retrain the relevant per-stat
  heads -> re-gate. (Human-gated path: propose the diff.)
- VALIDATE: re-run the leak-free WF gate (all-folds-improve + null-shuffle z>=3 + ablation-vs-FULL
  + FDR). Ship ONLY if it does not regress the frozen baseline AND beats it OOS. Verify
  `pkl.n_features_in_` == meta after retrain (pkl integrity check).

## STEP 3 (quick win) -- Inflate prop interval sigma per-stat
- WHY: intervals are overconfident on EVERY stat (blk ~x1.86); the domains baseline uses only a
  sigma FLOOR, which does nothing about a too-tight LEARNED sigma. Pure calibration win.
- APPROACH: re-fit a per-stat multiplicative inflation so the 80% interval covers 80% on holdout;
  wire into conformal/quantile/uncertainty emission, NOT the point estimate.
- VALIDATE: empirical coverage check (80% interval -> 80% realized) on holdout via
  `audit_quantile_crossing` + a coverage script. No point-MAE change expected.

## STEP 4 (medium) -- Same-day freshness feed -> the only real accuracy lever
- WHY: the close prices minutes/lineup/scratch we cannot see; this is the documented decisive
  lever (07/08/09 ceilings all converge here). The sim already has the `out_ids` hook.
- APPROACH: keyless scrape of projected starters + injury/scratch at slate lock -> feed
  `TeamModel.from_cache(out_ids=...)` and a minutes-prior. Wire in BOTH train + inference builders
  (parity -- the most expensive bug class). Snapshot per-date so backtests see real history (do
  NOT repeat the atlas single-snapshot leak-guard mistake).
- VALIDATE: leak-free WF lift of the freshness-adjusted prediction vs the CLOSE (not vs prior
  model). The OUT-feed timestamp must be < tip. CALIBRATION-PROVEN if BSS>0 vs the close; this is
  the one place we might genuinely BEAT, not just match, the close. Then forward paper CLV.

## STEP 5 (medium) -- Joint-calibration-prove the SGP (P5 structural pocket)
- WHY: the shared-pie sim's emergent correlation is the system's structurally unique asset; books
  price legs independently. But ROI is unproven and same-player corr is patched.
- APPROACH: `sgp_from_sim.validate_joint_calibration` against realized box scores leak-free
  (rates built as-of each game, excluding the graded game -- fixes the in-sample mild leak).
  Prioritize same-player pts+reb / pts+ast (positive corr books underprice).
- VALIDATE: joint hit-rate vs predicted (CALIBRATION-PROVEN on the joint). $ claim ONLY after real
  SGP price capture (none on disk) -> forward CLV/ROI. Until then, joint calibration is the claim.

## STEP 6 (medium) -- End the in-game blend SYNTHETIC->REAL OOS
- WHY: the flagship in-game lever ships with `REAL_OOS_VALIDATION_PENDING=True` on a synthetic
  corpus -- the real-data calibration gain is unproven.
- APPROACH: wire `ingame_blend_eval` to the real 1313-game `linescores.parquet`; fit weight
  surface on season A, eval on B (+ B->A).
- VALIDATE: per-quarter Brier/ECE + game-id-clustered Diebold-Mariano vs pregame-only. Record the
  honest verdict (BSS<=0 / market-efficient is a SUCCESS). $-ceiling ~0 (a live book sees the
  score too) -- claim calibration, not profit.

## STEP 7 (bigger bet) -- Extend sim depth to all 30 teams
- WHY: recency/PBP/team_defense exist ONLY for NYK/SAS (39/30/2 rows); the sim's deepest signal
  is a 2-team artifact for every other matchup.
- APPROACH: re-run `build_recency_rates.py` / `build_pbp_knowledge.py` / `build_team_defense.py`
  over the FULL game cache (generalize the game-list source off `nyk_sas_games.json`).
- VALIDATE: leak-free WF of the sim's PROP predictions per team-set (Brier/pinball/CRPS) vs
  realized; cross-season stability of the defense/dispersion/rating constants (reuse gate_def_supp pattern).

## STEP 8 (bigger bet, data-bound) -- In-game props as a repricer output
- WHY: realized minutes/usage massively cut per-player variance; in-play prop markets are
  thinner/slower than the moneyline -> the highest in-game upside.
- APPROACH: extend the per-sport repricer to emit calibrated prop DISTRIBUTIONS conditioned on
  realized minutes; needs a live minutes/possession feed (box snapshots see less than a book).
- VALIDATE: cross-corpus RMSE+signed-bias (NEVER MAE -- the shrink artifact), leak-free on the
  linescore+box corpus. Distributions, not point picks.

## CUT (do NOT spend here -- reallocate to the above)
Pregame ML/spread/total $ hunting (CUT 1/2, CLV~0); STL props (R2 0.11, non-bettable); momentum
signals (CUT 3, worse than random); the atlas point-feature funnel (DEAD, MAE worse); more
historical features/seasons (17 reverts, recency>volume); CV identity for props (jersey 2.3%
wall, coverage-blocked -- only the BLK contest-geometry head is a long-shot candidate after the
scoreboard-OCR fix). Keep all of these as calibrated decision-support + a CLV yardstick only.

## Sequencing logic
Steps 0 + 4 are DATA blockers and gate the biggest pockets -- start the scrapers immediately and
in parallel. Steps 1/2/3 are pure-software quick wins on data we already have (do them now).
Step 5/6 convert "built" assets to "measured." Steps 7/8 are the depth investments. Every step's
honest exit is a calibration verdict; real money is gated on forward paper CLV, nothing sooner.
