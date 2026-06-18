# TENNIS -- MODEL LEVERS (ship/reject/pending log + prioritized queue)
_Every modeling lever for tennis with a verdict from the real gate/proofs where one exists, else an
honest HYPOTHESIS. Grounded in domains/tennis/ + scripts/platformkit/proof_tennis/. ASCII.
Verdicts: SHIP (in the live predictor) / REJECT (measured worse or null) / PENDING (built, not gated)
/ HYPOTHESIS (not built/measured). Single-fold lifts are artifacts (proof-standards) -> never SHIP._

## SHIPPED (in domains/tennis/predictor.py today)
| Lever | Verdict | Evidence |
|---|---|---|
| Surface-blended Elo, SURFACE_BLEND=0.3 (ATP) | SHIP | `beat_the_close_ml` uses this exact blend; it is the best ATP win-prob we have (Brier 0.2177, matches the predictor). elo_core._blended_diff. |
| K-decay K=250/(m+5)^0.4 (Kovalchik) | SHIP | Standard tennis Elo decay; elo_core._k. Not separately ablated here but a vetted parameterisation. |
| Leak-free walk-forward Elo (replay, strict-prior) | SHIP | elo_core.replay + walk_forward_blend; the leak guard is the whole point (winner-ordered score never touched). |
| ATP pregame Platt-on-logit recal (train_year_max=2022) | SHIP | predictor._platt; calibration housekeeping. Falls back to raw if NaN. |
| As-of HOLD% prior shaping serve dominance | SHIP | asof_hold.parquet -> predictor._hold_levels -> serve_probs_from_winprob. Calibration input, NOT a match-win edge (asof_hold.py: "NO market edge claimed"). |
| W156 in-game Platt-on-logit recal (after-set match-win) | SHIP | predictor._ingame_platt; ECE 0.043->0.006 on the held-out TRAIN/EVAL split (ingame_calib). CALIBRATION-PROVEN sharpness. |
| In-game race-to-N set conditional (analytic, not re-sim) | SHIP | repricer.py; deliberately analytic to dodge the MAE-vs-RMSE median-shift artifact. Brier-graded. |

## REJECT / NULL (measured, honest failures = successes)
| Lever | Verdict | Evidence |
|---|---|---|
| WTA surface blend > 0 | REJECT | `wta_recal`: best_blend = 0.0 (surface component does not help WTA). Do not force a positive WTA surface weight. |
| WTA isotonic/temperature recal as an improvement | REJECT (data-limited) | `wta_recal` HONEST FAIL: recal ECE 0.0546 > 0.025 threshold across all min_prior filters; recal_brier >= raw_brier. Thin data; do not ship a WTA recalibrator (cut-list CUT-5). |
| ATP pregame match-win as a $-edge lever | REJECT | `beat_the_close_ml`: Elo BEHIND Pinnacle by +0.0149 Brier, n=7374. Efficient. Keep as decision-support only. |
| After-set-2 @ 1-1 in-game conditioning | REJECT-ish (marginal) | ingame_accuracy: 0.254 -> 0.245 Brier (n=2566). Real but small; 1-1 is near coin-flip. Surface, don't over-invest. |

## PENDING (built but NOT gated on real CLV / real lines)
| Lever | Verdict | Evidence / what's missing |
|---|---|---|
| Coherent full market surface (games/sets/hcap/set-score) | PENDING | markets.price_all prices them coherently, but NO scraped line to score against -> calibration-only, untested vs a close. |
| bo5 in-game conditioning | PENDING | `ingame_bo5.py` exists; not in the headline ingame_accuracy readout above. Run + record verdict. |
| Tennis live odds / CLV channel | PENDING | repricer reprices after each set, but no live tennis odds are scraped -> no CLV accrues. The gating channel for T1. |
| Fusion model (Elo + match-stats features) | PENDING | `fusion_tennis.py` exists in proof_tennis; needs a leak-free OOS verdict vs the pure Elo before any SHIP. Expect MATCH (cut-list: features won't beat the close). |

## HYPOTHESIS (not built; the queue below prioritizes them)
| Lever | Tier | Note |
|---|---|---|
| As-of ACE-RATE builder + NegBinom ace prop model | HYPOTHESIS | Ingredients on disk (match_stats p1_ace/svpt/1stIn). The single most promising NEW model. Mirror asof_hold.py. |
| Per-point serve model (deuce/ad chain) | HYPOTHESIS | Unlocks tie-break Y/N + within-set games (POINT_MODEL_GAPS). Medium build; only if a scraper proves those lines are soft. |
| Fatigue / minutes-load prior (3-set escape, days-rest) | HYPOTHESIS | matches.parquet has minutes + dates; a leak-free trailing-load feature. Likely small (cut-list: form as a rate input, fine; as a bet driver, gate hard). |
| Retirement/walkover hazard | HYPOTHESIS | postmortem retirement rate 3.41%; could refine totals tails. Niche. |
| WTA odds ingest -> WTA beat-the-close | HYPOTHESIS | Unblocks POCKET T5 testability. |

## Prioritized lever queue (do in this order)
1. **Run the in-game CALIBRATION SCOREBOARD** for tennis (ingame_accuracy + ingame_bo5) and PIN the
   table (after-set-1/2, bo3/bo5) into the evidence packet. Converts the strongest result from
   scattered to documented. Validate: leak-free Brier(conditional) vs Brier(pregame) + ECE. (Days.)
2. **Build the as-of ACE-RATE feature** (new builder under domains/tennis/, mirror asof_hold.py;
   no-future-leak assert). Then a NegBinom ace model. Validate: leak-free walk-forward BSS of P(over)
   vs realized aces on match_stats (>=100 independent matches). (Days-weeks.) This is the highest-
   upside NEW intelligence and is fully buildable from on-disk data.
3. **Add a keyless tennis MONEYLINE live-odds channel** (ESPN pickcenter; deep-dive 03) + start
   prop_line_history capture so a tennis CLV ledger finally accrues. Validate: forward CLV. (Days.)
4. **Add a keyless tennis PROP scraper** (PrizePicks/Underdog tennis league) + extend prop_edge to
   tennis. Validate: P(over) calibration + realized ROI at fixed payout. Gate hard. (Weeks.)
5. **Gate fusion_tennis vs pure Elo** on the leak-free OOS; record the (expected MATCH) verdict.
6. **Build wta_odds ingest** -> run WTA beat-the-close (POCKET T5 testability). (Weeks.)
7. (Only if 4 shows soft within-set lines) build the per-point serve model.

## Discipline notes
- Every new lever clears proof-standards: leak-free + walk-forward + >=2 corpora/folds + cluster-
  robust DM + (for $) forward CLV. Single-fold lifts are artifacts.
- Count-stat props (aces, DF): NB + dispersion, FLAG implausible |EV| (the too-tight-Poisson trap).
- Tennis pregame match-win effort is CAPPED by cut-list logic -- do not chase the 0.0149 gap.
