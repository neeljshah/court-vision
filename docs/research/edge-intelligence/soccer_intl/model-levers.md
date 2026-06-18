# soccer_intl -- MODEL LEVERS (every lever + SHIP / REJECT / PENDING / HYPOTHESIS verdict)

_Part of the edge-intelligence corpus. Every modeling lever in the WC prop stack with an honest
verdict + the artifact that earns it, then a prioritized queue. Verdicts mirror the real leak-free
gate (proof-standards.md); single-fold/in-sample lifts are recorded as REJECT. Grounded in
domains/soccer/ code + prop_calibration.json + recal_eval. ASCII only._

## Lever ledger

| # | Lever | Code | Verdict | Evidence / artifact |
|---|---|---|---|---|
| 1 | Empirical-Bayes per-90 rate shrink (SHRINK_K=3 toward position baseline) | player_rates.py:255 | **SHIP** (load-bearing) | The spine; leak-free (`_prior_rows` date<as_of, player_rates.py:62). Overall bss +0.11 with it. Without shrink, 1-match players are pure noise. |
| 2 | Club-season prior blend (CLUB_WEIGHT_CAP=20, n_eff>=5 = non-thin) | player_rates.py:203-224 | **SHIP** (the unlock) | Lifts 960/1241 WC players to non-thin rates (espn_club_priors.parquet, 960 players). Without it the board produces ~0 reliable edges (04 sec 4). Real data, capped so it can't swamp WC matches. |
| 3 | Expected-minutes from own priors (start_prob*85 + sub_min) | player_minutes.py:29 | **SHIP but WEAK / UNMEASURED on live board** | Correct degrade-not-fabricate (unknown->no bet). BUT backtest feeds REALIZED minutes (props_eval.py loop), so its live error is UNMEASURED -> reported calibration is optimistic (04 sec 5). Biggest hidden error. |
| 4 | NB dispersion widening (phi=var/mean, r=lam/(phi-1), two-pass) | dispersion.py:129/180, prop_edge.py:154-165 | **SHIP** | Prevents too-tight Poisson fabricating tail edges (proof-standards trap). Honest caveat: with _MIN_N=40 and ~1k rows, several stats ride PRIOR phi, not a fit -- safe direction, unvalidated. |
| 5 | Opponent-adjustment multiplier (team_defense allowed-attribution) | team_defense.py:193 | **REJECT (measured NULL)** | Fully built + wired, but per-opponent table ~1-3 matches deep -> shrinks to ~1.0; cache mode "+opp-adj" still only bss +0.11. No demonstrated calibration lift (04 sec 5). Keep wired, re-test as data grows. |
| 6 | Isotonic P(over) recalibration | prop_recal.py, recal_eval.py | **REJECT / DEFERRED (overfit)** | recal_eval verdict: "MIXED: improves OOS ECE (-0.00115) but NOT Brier (+0.00393); in-sample Brier -0.00610 vs OOS +0.00393 -> gap +0.01003 overfit tell." prop_recal.json exists but board does NOT apply it (cut-list CUT 5). |
| 7 | Tiered-evidence ranking (proven>marginal>weak, raw-EV can't jump tier) | prop_tiering.py:113/167 | **SHIP** | Structural honesty: a weak-stat EV blowup can never top a proven row. Demotes Cards/Assists/Goals correctly. |
| 8 | Position baseline pooling (single pooled per-90 per position) | player_rates.position_baseline (player_rates.py:93) | **PENDING refinement** | Works; but keepers vs outfielders clearly need separate dispersion+baseline (04 sec 6 #6). Position is granular in data (CD-R/CM-L/AM/G/SUB). Low-risk OOS-gated split. |
| 9 | Club-prior point-in-time correctness (single as_of snapshot) | ingest_espn_athlete.py | **PENDING (known mild lookahead)** | club-augmented mode carries documented lookahead; shipped cache uses strict leak-free mode (correct call). Needs a true PIT series to validate the club path leak-free. |
| 10 | per_start->per90 denominator (uses starts, ignores sub apps) | ingest_espn_athlete.py | **PENDING fix (biased)** | Mild OVER-estimate -> nudges lam up for rotation players (04 sec 5; inefficiency-catalog S6). Fix = use appearances; expected to REMOVE spurious OVER edges. |
| 11 | Minutes projection with lineup signal | (not built) | **HYPOTHESIS (highest-ceiling)** | Biggest unmeasured live error lives here (04 sec 6 #9). Needs predicted-lineups source. |
| 12 | Joint / correlated props (Shots+SOT, G+A copula / shared latent) | (not built) | **HYPOTHESIS (bigger bet)** | Engine emits independent marginals only. Validate full stat-pair surface (04 sec 6 #10). |
| 13 | Hierarchical / partial-pooling rate model (player<position<league) | (not built) | **HYPOTHESIS** | Replace capped linear EB blend with a proper hierarchy so thin players borrow strength more principledly (04 sec 6 #8). |
| 14 | CLV capture / closing-line snapshot | prop_line_history.py (built, ~1 row) | **PENDING ops fix (CRITICAL)** | Code exists; not being ticked to kickoff -> 0 CLV (06 sec 5 #3). Not a model lever per se but gates every edge claim. |
| 15 | In-game / live repricing for props | (not built; team in-game = area 05) | **HYPOTHESIS** | Books lag realized state (P2). For props, in-game saves/shots reprice as the match unfolds -- decisive combinable lever, but unbuilt for the prop stack. |

## Prioritized lever queue (do in this order)

1. **#14 CLV capture (ops).** Highest leverage, lowest effort, lowest risk. Without it nothing
   graduates. Schedule prop_line_history to tick to kickoff. Validate: prop_line_history.jsonl
   accrues > 1 row; clv_summary reports n_with_real_close > 0.
2. **#3/#11 Minutes -- measure then improve.** First run the backtest with PROJECTED (not realized)
   minutes to MEASURE the true live calibration gap (04 sec 6 #5) -- this is a measurement, expected
   to re-tier some stats downward honestly. Then add a coarse predicted-lineups flag. Validate: OOS
   Brier with projected minutes; ship only if non-regressing per the gate ratchet.
3. **#10 per_start->per90 fix.** Cheap correctness fix; removes spurious OVER edges. Validate:
   re-run props_eval --cache; a null/negative delta is the success (proof-standards: REJECT/NULL =
   success).
4. **#8 position-conditioned dispersion + baseline (keepers vs outfielders).** Low-risk, OOS-gated.
   Validate: per-stat OOS Brier improves on >=2 matchdays.
5. **#5 opponent-adjust re-test (data-bound).** Re-run +opp-adj each matchday; ship only if it
   improves OOS Brier on >=2 matchdays (currently null).
6. **#6 isotonic recal re-test (data-bound).** Re-run recal_eval as N grows; the overfit gap must
   close OOS before re-enabling.
7. **#12/#13/#15 bigger bets (joint props, hierarchy, in-game).** Only worth it once the cheaper
   levers + data depth land; each needs full-surface / multi-corpus validation.

## What the queue is NOT
No lever here promises a $-edge. Every "ship" is a calibration / correctness ship; the bar for a
profit claim is forward CLV (lever #14 must land first), and even then only Saves is a plausible
candidate (00-edge-map.md).
