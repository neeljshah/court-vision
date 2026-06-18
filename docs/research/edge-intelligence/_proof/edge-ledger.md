# EDGE LEDGER -- the living proof-state of every candidate edge / lever

_Part of the edge-intelligence corpus (`_proof/`). This is the SINGLE table of every candidate
edge, signal, and lever across the whole system, each with its current EVIDENCE TIER, the
ARTIFACT that sets that tier, and what would ADVANCE it. Grounded in deep-dives 04/05/06/11 and
the live ledger artifacts inspected 2026-06-18. Honest by construction: a NULL / REJECT is a
SUCCESS (it tells us where to STOP). No $-edge is claimed anywhere. ASCII only._

> Tier ladder (from `_framework/edge-theory.md` + `proof-standards.md`):
> HYPOTHESIS -> CALIBRATION-PROVEN (leak-free OOS BSS>0, sharper than the devigged close) ->
> CLV-PROVEN (forward paper CLV>0 at meaningful N). A claim never jumps a tier without the
> artifact. Honest DOWNGRADES (opp-adjust -> NULL; isotonic recal -> overfit) are first-class.

> Bar reminders that gate this whole table: SHIP / BEATS_CLOSE need `dm.n>=200` independent
> settled outcomes (run_gate.py `_verdict`); `prop_tiering.classify` calls a stat "proven" only
> at `bss>=0.05 AND n>=100`; cold start `< 60 settled` -> INSUFFICIENT_DATA (self_improve.py).

---

## 0. The headline proof-state (read this first)

- **CLV-PROVEN tier is EMPTY.** Zero edges have accrued positive forward CLV. The code path to
  promote to CLV_PROVEN does not even exist yet (prop_tiering tops out at CALIBRATION_PROVEN --
  deep-dive 06 sec 5.4). `clv_ledger.jsonl` = 38 lines, 14 settled, **0 carry a real CLV**;
  `prop_line_history.jsonl` = **1 line**; `improve_ledger.jsonl` = 48 lines, **48/48
  INSUFFICIENT_DATA**. So every "edge" below is at best CALIBRATION-PROVEN, most are HYPOTHESIS,
  and the honest top of the ledger today is "well-calibrated, not yet shown to pay."
- **Exactly ONE stat clears the CALIBRATION-PROVEN bar:** WC **Saves** (bss +0.3365, n=662),
  and even that is flagged as a likely structural artifact (keeper saves ~ deterministic in
  shots faced). Everything else is HYPOTHESIS, marginal, or a measured REJECT.
- **The cleanest, most-principled calibration win is IN-GAME conditioning** (score-anchor
  Brownian collapse), but its flagship real-corpus OOS validation is still PENDING (synthetic).

---

## 1. THE EDGE LEDGER (master table)

Legend: tier in {CLV-PROVEN, CALIBRATION-PROVEN, HYPOTHESIS, REJECTED, NULL(measured-no-edge)}.
"Artifact" = the gate run / backtest / cache / null that sets the tier. file:line where useful.

| # | Edge / lever | Sport / market | TIER | Artifact (what sets it) | What would ADVANCE it |
|---|--------------|----------------|------|-------------------------|-----------------------|
| **CALIBRATION-PROVEN (leak-free OOS BSS>0; honest sharpness wins, NOT $)** |
| 1 | **Saves p(over)** | WC soccer prop | CALIBRATION-PROVEN (thin) | `prop_calibration.json` Saves bss **+0.3365**, n=662, brier 0.0176, ece 0.004 | CLV capture (`prop_line_history` has 1 row) + independent-MATCH N (662 is correlated player-rows over ~24 matches), + a 2nd tournament corpus. Caveat: likely structural (saves ~ f(shots faced)). |
| 2 | **In-game team win-prob conditioning** | NBA/MLB/soccer/tennis live | CALIBRATION-PROVEN (NBA only, single-corpus) | deep-dive 11 sec 7: NBA combined Brier ~**0.159 vs ~0.209** pregame on the cited 1313-game linescore corpus; score-anchor RMSE shrinks Q1~12.5 -> Q4~4.2 | End the `REAL_OOS_VALIDATION_PENDING=True` flag on `ingame_blend_eval.py` (still SYNTHETIC); multi-corpus replication; clustered-DM significance. NOT a $ edge (a live book sees the score too). |
| 3 | **In-game temperature recal (NBA)** | NBA live win-prob | CALIBRATION-PROVEN (in-sample-ish) | `predictor.predict_live` `live_temp`: ECE **0.059 -> 0.012** | Held-out multi-season ECE; wire into run_gate (CRPS/ECE block is stranded -- dd06 sec 5.7). |
| **HYPOTHESIS (plausible pocket/lever, not yet measured OOS -- the work queue)** |
| 4 | **AST pregame prop edge (NBA)** | NBA AST prop | HYPOTHESIS (historically the ONLY claimed real model edge) | MEMORY `feedback_ast_edge_is_real`: ~+7%, both directions, never playoffs, keep RAW. NOT in any current gate artifact; NBA off-season -> 0 settled. | Re-measure leak-free OOS BSS vs devigged close on a fresh NBA season; gate via signal-audit. Until then treat as historical hypothesis, not proven. |
| 5 | **MLB Pitcher-Ks / Hits / Outs / Walks p(over)** | MLB props | HYPOTHESIS | dd05: engine sound (per-BF/per-PA Bernoulli ~Poisson), BUT `prop_calibration.json` **n=0** (17-day corpus, every game skipped for lack of prior) | Backfill `player_gamelogs` to 1-2 seasons (`ingest_player_stats.ingest_range`, keyless) -> re-run `props_eval_mlb` -> first BSS per stat. The single highest-leverage MLB action. |
| 6 | **MLB SP-aware Elo offset** | MLB moneyline | HYPOTHESIS (validated in proof layer, NOT delivered) | dd05 sec 2.3: `sp_elo_offset` `p=sigmoid(logit+w*z_sp)`, w fitted leak-free; but NOT wired into `MLBPredictor` (pure MOV-Elo serves) | Wire into predictor, re-score vs devigged close to confirm it does not regress (deep-dive 05 plan item 5). Biggest single MLB game variable currently absent from the served number. |
| 7 | **Live / in-game player props (minutes-conditioned)** | all sports live props | HYPOTHESIS (highest-ceiling frontier) | dd11 sec 7: routed-ensemble player MAE **1.01 vs 1.87** prod on a single held-out grid; default-OFF behind `CV_INGAME_SBS` | Cross-corpus RMSE+bias proof (not single backtest); a live minutes/usage feed; promote per-(stat,game-time) cell only where it strictly beats prod. |
| 8 | **Correlated SGP / same-player joint props** | all sports | HYPOTHESIS | Books price legs independently (edge-theory P5); we have JointDistribution surfaces (`negbinom_sim.build_mlb_jd`, kernel sgp) but no measured joint-vs-marginal calibration | Build joint (copula / shared-latent), validate on the FULL stat-pair surface (MEMORY `retro_full_surface_validation`), not just the dominant pair. |
| 9 | **Prediction-market vs sportsbook divergence** | Kalshi/Polymarket vs books | HYPOTHESIS | edge-theory P4; `pm_trading/edge_signal.py` exists; no measured divergence-edge artifact | Log paired PM/book lines over time; measure realized convergence + CLV. |
| 10 | **Stale-line / soft-book line-shopping** | cross-sport execution | HYPOTHESIS (execution, model-free) | edge-theory P3; `odds_shop.py` devig + best-price exists | Forward log of best-price-vs-close; this is an EXECUTION edge, prove via realized CLV not a model. |
| 11 | **MLB season-priors rate layer** | MLB props rate model | HYPOTHESIS | dd05 plan item 9: statsapi season per-PA/per-BF as a strong low-variance prior (unlike NBA, MLB rewards volume) | Ingest season splits, shrink toward them, re-measure per-stat BSS. |
| 12 | **WC opponent-adjustment lever (re-test as data grows)** | WC soccer props | HYPOTHESIS (currently NULL, item 21) | dd04: re-run +opp-adj each matchday; ship only if it improves OOS Brier on >=2 matchdays | More matchdays so per-opponent allowed table is >1-3 matches deep. |
| **NULL -- MEASURED no-edge (a SUCCESS; stop spending here)** |
| 13 | **WC Shots-on-Target p(over)** | WC soccer prop | NULL | bss **+0.0049** (n=662) -- below PROVEN 0.05, ~ base rate | demote to model-view; needs structural shot-volume model, not more pooling. |
| 14 | **WC Shots p(over)** | WC soccer prop | NULL | bss **+0.0076** (n=662) | same as above. |
| 15 | **WC Fouls / Fouls Drawn** | WC soccer prop | NULL (marginal) | bss **+0.0339 / +0.026** (n=662) -- below PROVEN 0.05 | more data; position-conditioned dispersion. |
| 16 | **WC Goal+Assist** | WC soccer prop | NULL | bss **-0.0067** (n=662) | likely irreducible per-match noise; keep demoted. |
| 17 | **Opponent-adjustment (WC team_defense lever)** | WC soccer props | NULL (built, wired, measured null) | dd04 sec 5: overall +opp-adj bss only +0.11; per-opponent table ~1-3 matches deep -> shrinks back to 1.0 | only a data problem; re-test (= item 12). Honest plumbed-lever-awaiting-data. |
| **REJECTED -- measured negative / overfit / artifact (never bet; recorded as knowledge)** |
| 18 | **WC Cards p(over)** | WC soccer prop | REJECTED (negative skill) | bss **-0.1076** (n=662) -- worse than base rate | irreducible Bernoulli noise; do NOT paper-bet (cut-list CUT 4). |
| 19 | **WC Assists p(over)** | WC soccer prop | REJECTED | bss **-0.074** (n=662) | same. |
| 20 | **WC Goals / Offsides p(over)** | WC soccer prop | REJECTED | Goals **-0.0252**, Offsides **-0.0155** (n=662) | same; rare-event lumpy. |
| 21 | **Isotonic P(over) recalibration** | WC soccer props | REJECTED (OOS overfit -> DEFERRED) | `recal_eval.run_eval`: in-sample Brier delta **-0.0061** vs OOS **+0.0039** (overfit gap +0.0100); ECE helps but Brier worsens | refit only as data grows; never ship an in-sample-only recal (cut-list CUT 5). The DEFER is the system working. |
| 22 | **Momentum / hot-hand as a bet driver** | NBA (all) | REJECTED (worse than null) | INT-81 momentum z_vs_null **-1.75**; momentum-aligned bets perform WORSE than random | do not build bet signals on streak alignment (cut-list CUT 3). Form as a RATE input is fine. |
| 23 | **NBA pregame team markets as an edge source** | NBA pregame PTS/REB/team | REJECTED (at data ceiling) | 6 architectures + 4 levers REJECT; recency>volume (seasons HURT); 17 feature-add reverts | keep as calibrated decision-support only; redirect to freshness + props + in-game (cut-list CUT 2). |
| 24 | **Sharp pregame MAINLINES (h2h/spread/total)** | all major sports | REJECTED as $-edge (efficient) | full-season walk-forward: well-calibrated but does NOT beat the close; CLV ~ 0 (cleanest efficiency proof) | nothing advances a $-edge here; keep as a CLV yardstick only (cut-list CUT 1). |
| 25 | **Too-tight Poisson prop tails (multi-value stats)** | MLB TB/RBI/Runs/H+R+RBI | REJECTED (mis-specified shape) | dd05 sec 2.2/5.3: Poisson on a weighted sum fabricates fat-tail edges; |EV| flag | compound (count x base-value) or joint model; demote to display-only until then (cut-list CUT 4 analog). |
| 26 | **Arbitrage as a profit center** | cross-sport | REJECTED (fragile, limit-bound) | cut-list CUT 6: arbs rare, limit-constrained, not standing income | keep arb DETECTION as a free flag; do NOT architect around it. |
| **RETRACTED ARTIFACTS -- never reprint as current (documented measurement artifacts)** |
| R1 | "+18.38% pregame ROI" | NBA pregame | RETRACTED ARTIFACT | market-follow + in-sample + flat-payout + vig-ignored (no-edge-claims rule; proof-standards "market-follow trap") | -- (appears ONLY inside retraction context) |
| R2 | "endQ3 0.119 win-prob" | NBA in-game | RETRACTED ARTIFACT | a Q4 leak (no-edge-claims rule) | -- |
| R3 | "+54% / 78.11% in-play" | NBA in-play | RETRACTED ARTIFACT | an L5-proxy ceiling, not realized edge | -- |
| R4 | "8.94 / 54.57" | -- | RETRACTED ARTIFACT | inflated figures (no-edge-claims rule) | -- |

---

## 2. WHY THE WHOLE TABLE STALLS BELOW CLV-PROVEN (the binding constraints)

Three structural blockers, all honest, none algorithmic:

1. **Closing lines are not being captured.** `prop_line_history.jsonl` = 1 row; 0/14 settled
   team bets carry a real close. CLV is the bridge from "calibrated" to "would pay" and there is
   no signal yet (dd06 sec 5.3). FIX = ops/cadence: tick `prop_loop`/`pm_trading` up to kickoff
   so `log_board_lines` is actually reached. Highest leverage, lowest effort.
2. **Statistical power.** SHIP/BEATS_CLOSE require `dm.n>=200` independent settled outcomes;
   every sport is far below 60 (`MIN_RECAL_GAMES`). The ratchet can only HOLD/INSUFFICIENT_DATA
   until months of forward accrual land (dd06 sec 5.2, 5.6). 48/48 INSUFFICIENT_DATA is the
   honest current output.
3. **Thin / correlated calibration N.** "n=662" per WC stat is player-rows over ~24 correlated
   matches, not 662 independent events (dd04/06). "Proven" today = "promising, thin," never
   bankable. Add an independent-MATCH count to the proven bar (dd06 plan item 4).

---

## 3. WHAT TO ADVANCE NEXT (priority-ordered, ties the ledger to action)

1. **Capture closing lines** (item-wide unblock) -> turns every CALIBRATION-PROVEN row into a
   candidate for CLV-PROVEN. Pure ops.
2. **MLB gamelog backfill** (item 5/11) -> first MLB prop BSS scoreboard exists at all.
3. **End the NBA in-game blend PENDING flag on the real 1313-game corpus** (item 2) -> converts
   the flagship calibration win from "pattern proven" to "real-data measured."
4. **Re-measure the NBA AST edge** (item 4) on a fresh season via signal-audit -> confirm or
   retire the only historically-claimed model edge.
5. **Build the CLV_PROVEN top tier** in `prop_tiering` (dd06 plan item 7) -> so an edge can
   actually graduate once CLV accrues; reuse `diebold_mariano` on per-bet CLV clustered by match.

---

## 4. HONESTY FOOTER

- Markets are mostly efficient; the north star is CALIBRATION vs the devigged close, not a $.
- The CLV-PROVEN tier is empty and the code to reach it is partly unbuilt -- stated plainly.
- One genuinely proven calibration stat (Saves) carries a structural-artifact caveat.
- Every REJECT/NULL above is a recorded success that reallocates effort (see cut-vs-push-scorecard.md).
- Retracted artifacts (R1-R4) appear ONLY in retraction context, per `.claude/rules/no-edge-claims.md`.
