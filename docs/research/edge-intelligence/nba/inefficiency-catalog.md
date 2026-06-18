# NBA INEFFICIENCY CATALOG -- the specific beatable pockets + detection recipe + proof method

_Sport = NBA. Each entry: WHERE the crack is, the in-data DETECTION recipe, and the PROOF
method that would move it from HYPOTHESIS -> CALIBRATION-PROVEN -> CLV-PROVEN. Grounded in the
deep-dives + framework P1-P6 taxonomy. A null here is a SUCCESS. ASCII._

## POCKET N1 -- AST prop divergence (P1, the one near-durable model edge)
- WHERE: soft/standard books price assists off recent averages; our model diverges on
  high-playmaking roles, and that divergence has historically held (~+7%, both directions).
  It is fragile -- never in playoffs -- and kept OFF the q50/calibration path ON PURPOSE so
  the divergence is not pulled back to the mean (07:115,189).
- DETECTION: rank players by |model_ast - book_ast_line| using `prop_pergame.predict_pergame('ast',...)`
  vs the prop line; the edge lives where the model is CONFIDENTLY different AND the role is a
  primary creator (cross-check `player_roles.parquet` playmaking propensity). Decompose with the
  existing `scripts/ast_edge_decomposition.py` / `ast_edge_maximize.py`.
- PROOF: leak-free WF P(over) calibration vs the devigged AST prop close (BSS>0) on >=2 seasons;
  regular-season ONLY (exclude playoffs). Then forward paper CLV vs the AST closing line.
- TIER: HYPOTHESIS -> needs re-proof on the current corpus. Current corpus is 2024-25 + 2025-26
  (27,816 player-games) -- enough to re-run. DO NOT reprint any historical ROI as current.

## POCKET N2 -- Same-day freshness (P1-adjacent; the only unmodeled accuracy lever)
- WHERE: the close prices projected minutes / starting lineup / late scratch / load management
  that our historical box model cannot see. When a starter is OUT, usage/minutes re-route in
  ways recency averages lag for 1-2 games -- a window the soft line may also lag.
- DETECTION: at slate lock, diff tonight's projected-OUT list against each player's recency
  minutes; the beatable signal is teammates of a scratched starter (usage bump) and the
  scratched starter's own props going to ~0. Feed the OUT list into `TeamModel.from_cache(out_ids=...)`
  (08:88) and re-price; compare the freshness-adjusted prop to the (stale) book line.
- PROOF: leak-free WF lift of the freshness-adjusted prediction vs the CLOSE (not vs prior
  model), with the OUT feed snapshotted timestamp<tip and stored per-date so backtests see it.
  Train/inference parity is mandatory (wire in both builders).
- TIER: HYPOTHESIS. Blocked on the missing same-day feed (see data-sources.md). Highest-value lever.

## POCKET N3 -- Correlated SGP mispricing (P5; the sim's structural advantage)
- WHERE: books price SGP legs INDEPENDENTLY and misjudge the joint. Our shared-pie MC sim makes
  the correct (slightly negative) teammate correlation EMERGE (~-0.10) and the positive
  same-player pts-reb correlation (realized +0.2..0.35) -- the joint is right by construction
  (mostly; the same-player part is patched, 08:208).
- DETECTION: `sgp_from_sim.joint_prob(legs)` vs the product of `leg_prob`; the lift over the
  independence product IS the mispricing the book makes. `sgp_edge_scanner.py` wraps this.
  Largest cracks: same-player pts+reb / pts+ast (positive corr the book underprices), and
  cross-player game-script combos (a star's pts UP <-> teammate ast UP).
- PROOF: FIRST `validate_joint_calibration` vs realized box scores leak-free (joint hit-rate vs
  predicted), because the rates are full-season in-sample today (mild leak, 08:189). THEN, with
  REAL captured SGP prices (none on disk yet), forward CLV/ROI. Without price capture, joint
  calibration is the only honest claim.
- TIER: HYPOTHESIS. Joint-calibration-proof is the gating next step.

## POCKET N4 -- In-game lag (P2; calibration win, $-ceiling ~0)
- WHERE: the in-game forecast tightens on the realized score (RMSE Q1~12.5 -> Q4~4.2); a live
  book sees the same score, so the EDGE is forecaster QUALITY, not $ (11 binding frame).
- DETECTION: `NBARepricer.reprice(GameState)` (Gaussian score-anchor + Brownian variance
  collapse) vs the pregame prior; the gap is the conditioning gain. For props, the routed
  ensemble (`src/ingame/`) reduces player MAE (1.01 vs 1.87) once realized minutes are known.
- PROOF: end the SYNTHETIC PENDING flag -- run `ingame_blend_eval` on the REAL 1313-game
  linescore corpus (`linescores.parquet`), fit weight surface on season A, eval on B (+B->A),
  per-quarter Brier/ECE + game-id-clustered DM vs pregame-only (11 quick-win 1). For props,
  cross-corpus RMSE+bias (never MAE -- the shrink artifact).
- TIER: CALIBRATION-PROVEN partial (team win-prob, single corpus); blend OOS PENDING; props OFF.

## POCKET N5 -- DD/TD + milestone-ladder + alt-line mispricing (P1/P5)
- WHERE: soft books price thresholds/ladders/alt-lines independently of the marginal; our sim's
  count-stat recal fixes the zero-clumping (08:122) so our >=N CDF is sharper than a stale base.
- DETECTION: compare the sim CDF P(stat>=k) (read off the per-sim sample) to the book's implied
  ladder probabilities; flag where the ladder is non-monotone-consistent with our marginal.
- PROOF: leak-free calibration of P(DD)/P(TD)/P(>=k) vs realized box scores; then vs soft-book
  prices once a feed exists. Watch the too-tight-sigma trap (intervals overconfident, 07:209).
- TIER: HYPOTHESIS.

## POCKET N6 -- BLK via clean CV contest geometry (P1, data-blocked)
- WHERE: BLK is the single best-evidenced CV signal (3 features >=+0.15 corr, 10:158); blocks
  depend on rim-protection + contest geometry the box model misses.
- DETECTION: per-shot defender-distance / contest at the rim from CV, attributed to the correct
  shooter -- but TODAY this is blocked by jersey-OCR (2.3% read), the 10-slot ceiling (~75%
  player-games missing), and 30-50% defender-distance contamination (10 sec5).
- PROOF: requires the scoreboard-OCR -> PBP-anchoring fix FIRST (10 quick-win 1), then a
  leak-free null-controlled BLK head on >=2 corpora with coverage >~20%. Sigma inflation x1.86.
- TIER: HYPOTHESIS, coverage-blocked. Lowest near-term ROI; flagged for completeness.

## EXPLICIT NON-POCKETS (detected and rejected -- do not re-mine)
- **Momentum / hot-hand** (CUT 3): INT-81 z_vs_null=-1.75, momentum-aligned WORSE than random.
- **Atlas point features** (DEAD FUNNEL, 09): base+atlas MAE pts +0.174, reb +0.064, ast +0.008
  (all WORSE); only fg3m -0.003 marginal. Unread by served model anyway.
- **Opponent-adjust / rest-days -> pts** (`signal_lab_registry.parquet`): opp_def_matchup REJECTED
  (oos_rel +1.194%, unstable split-half); rest_days_pts REJECTED (oos_rel -0.161%).
- **Pregame team-strength as a $ edge** (CUT 1/2): season WF CLV~0; 17 feature reverts.

## How to use this catalog
Pre-commit to ONE pocket + its detection recipe before looking at outcomes (avoid the SELECTION
trap, proof-standards). Every detection must run on a leak-free as-of matrix. The 5 VALIDATED
signals in `signal_lab_registry.parquet` (pbp_origin_transition, rest_x_age, shot_clock_leverage,
opp_position_defense_reb, oreb_matchup) already passed the honest gate and are the most likely
real point-model wins -- promote them via reviewed graft + retrain + re-gate before chasing new pockets.
