# MLB GET-TO-EDGE PLAN -- the prioritized path to a PROVEN result
_Part of the edge-intelligence corpus. Concrete, ordered steps from today's n=0 prop corpus to a
defensible CALIBRATION result (the realistic ceiling) and, where a pocket cracks, toward CLV. Each step:
approach + how it is VALIDATED. Markets are efficient; the honest target on team markets is MATCHES_CLOSE,
and the only credible prop lift is in the soft/DFS per-opportunity pocket once data lands. ASCII only._

## The current state (honest)
- Team model: leak-free, coherent, MATCHES_CLOSE -- the genuine asset, EFFICIENT as $-source.
- Prop engine: correct machinery, **n=0 scored predictions** (`prop_calibration.json` verified empty
  2026-06-18) on a **17-day** gamelog corpus (6,558 rows, median 6 games/player). ~0% of its ceiling.
- SP lever: validated leak-free, NOT delivered live. Ratchet: INSUFFICIENT_DATA (mlb n=12 < 60).

## STAGE 0 -- Unblock (the single prerequisite, DAYS)
**Step 0.1 -- Backfill the player gamelog corpus to >=1 full season (ideally 2022-2025).**
Approach: `domains/mlb/ingest_player_stats.ingest_range(start, end)` (keyless statsapi, `:219`). Run
season-by-season; verify against the INSERT-OR-REPLACE / scale-guard backfill gaps (re-count rows + span,
spot-check a known player-game). This is pure data acquisition -- no gated-code edit.
Validate: `player_gamelogs.parquet` spans full seasons, median games/player >> 6, and
`props_eval_mlb.backtest_calibration_mlb` returns **n > 0**.

## STAGE 1 -- First honest calibration verdict (DAYS, quick wins)
**Step 1.1 -- Run `props_eval_mlb --cache` and publish the per-stat Brier/ECE/BSS scoreboard.**
Approach: the leak-free walk-forward already exists; feeds realized exposure so it tests RATE/shape
calibration. Validate: per-stat BSS + ECE (sharpness-paired). Expect Ks/Hits/Walks/Outs reasonable,
TB/RBIs/Runs poor -- report either way. A negative BSS is a SUCCESS (tells us where to stop).
**Step 1.2 -- Demote the rough stats to "shape-uncalibrated, display-only"** in the engine output based
on 1.1 (TB/RBIs/Runs/H+R+RBI/HR/SB). Validate: `prop_tiering.classify` tier per stat; these stay
unmeasured/weak -> never paper-bet (cut-list CUT 4).
**Step 1.3 -- Fit a per-stat NegBinom r from realized outcomes; set as default `dispersion`.**
Approach: MoM on realized per-stat counts (mirror `negbinom_engine.fit_dispersion_first_half`), leak-free.
Validate: OOS ECE / tail calibration on Ks beats pure Poisson; no regression on the sound stats.

## STAGE 2 -- Deliver the validated team lever (WEEKS)
**Step 2.1 -- Wire the SP-Elo offset into `MLBPredictor`** (gated path: PROPOSE the diff, do not edit
`domains/mlb/predictor.py` autonomously). Approach: promote `sp_elo_offset` (`p=sigmoid(elo_logit+w*z_sp)`,
w fitted leak-free) so the live win-prob reflects who is pitching.
Validate: re-score the SP-adjusted predictor vs the devigged close (BSS + cluster-robust DM clustered by
game, `eval_gate/dm_test.py`); SHIP only if no regression vs the frozen Elo baseline. This makes the live
number reflect the biggest game variable -- a calibration win, not necessarily an edge.

## STAGE 3 -- Structural rate depth (WEEKS-MONTHS)
**Step 3.1 -- Add park + opposing-SP + platoon factors to the prop rate.** Approach: multiply the per-PA
rate by leak-free park (`asof_park.py`), opponent-SP, and L/R platoon factors. Validate: per-stat BSS
improves OOS on the sound stats; full-surface check (not just one stat).
**Step 3.2 -- Season-prior shrink target.** Approach: pull statsapi season per-PA/per-BF + splits as a
low-variance prior to shrink toward, replacing the coarse all-rows league pool. Validate: lower rate
variance + better early-game calibration OOS.
**Step 3.3 -- Compound model for Total Bases (then H+R+RBI).** Approach: hit-count x base-value mixture or
per-event 1B/2B/3B/HR categorical. Validate: tail calibration beats single-Poisson OOS.

## STAGE 4 -- Forward proof toward CLV (MONTHS, data-bound)
**Step 4.1 -- Give the prop engine a delivery path** (a `props_read` analog of
`scripts/platformkit/live_read.py`) so it is exercised on live slates and feeds a paper ledger
(`prop_paper` + `prop_line_history.log_board_lines`). Validate: `prop_line_history.jsonl` accrues > 1 row
(it has 1 today); DFS-line movement + realized P(over) calibration captured.
**Step 4.2 -- Accrue forward settled outcomes until the ratchet engages** (n >= 60, then DM n >= 200 of
INDEPENDENT player-games). Approach: run the paper loop over a live season window; closing-line capture up
to first pitch. Validate: `self_improve.improve_cycle('mlb')` leaves INSUFFICIENT_DATA; per-stat realized
ROI at fixed DFS payout (pick'em has no two-way close -> CLV undefined; use movement + P(over) instead);
for team markets, real positive CLV with cluster-robust CI > 0 before any CLV-PROVEN claim.

## Honest target by surface
- **Per-opportunity DFS props (Ks/Hits/Walks/Outs):** the only place an edge is plausible. Target:
  CALIBRATION-PROVEN (BSS>0, n>=100 independent) -> then realized-ROI/movement evidence. Tier today: HYPOTHESIS.
- **Team mainlines / totals:** target MATCHES_CLOSE (BSS~0). That IS the win; do not chase $.
- **Multi-outcome props:** target an honest demotion to display-only until a compound model earns its place.
- **In-game:** the static number is CALIBRATION-PROVEN (NULL recal); any edge is timing/execution-bound,
  provable only forward on a fast feed.

## What would falsify the plan (kill criteria)
- If, after a full-season backfill, the sound per-opportunity stats still show BSS <= 0 OOS -> the prop
  engine matches the lazy line too; demote MLB props to decision-support and reallocate (a clean NULL).
- If the SP lever does not beat pure Elo vs the close -> SP signal is already in the close; keep it as a
  feature, claim calibration only, no edge.
