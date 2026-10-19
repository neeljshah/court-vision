# EXECUTION 2.0: measured audit of the paper execution chain and the row plan (2026-09-29)

Opus execution 2.0 lead. PAPER ONLY: nothing here places, routes or authenticates an order, and no Kalshi auth or key is touched. Execution-quality and calibration language only (markouts, adverse selection, fill realism, inventory, quote uptime). Nothing below claims more than execution quality; every sign is a measured cents-per-contract markout with a game-cluster interval. Register ids S550-S559 are reserved for this plan.

The owner's order (make execution ten times better and connect every part for the best paper betting) is translated into four measurable targets: (1) fills per unit of adverse selection, (2) fee-inclusive markout per filled contract at +60 s, (3) cancels that land before the book reprices on a state event, (4) quote uptime on served games. Each row states which target it moves; a measured null is an acceptable result.

Coordination: orchestrator 4 owns the live shadow recorder and its fill receipt (S515-S519, `LIVE_PAPER_BETTING_PLAN_2026-09-29.md`). Nothing here rebuilds those. The EXECUTION 2.0 rows are an archive diagnostic (S550), an offline policy comparison (S551) and deferred policy functions; S515 does not read trades, so any tape-driven rule reaching the live recorder needs that owner's interface agreement first.

## Status of the numbers

This is an EXPLORATORY audit of an already-inspected development week (09-22..09-29). It anchors design, not a confirmatory comparison. r1 (commit 6638c394d) had measurement defects found by the two critiques below; every number here is r2. The r1 receipt is kept as `exec2_audit_2026-09-22_2026-09-29.json` for the record; r2 is `exec2_audit_r2_2026-09-22_2026-09-29.json`.

## Probe (reproducible, read-only)

- Scripts (tracked): `docs/evidence/harness/exec2/exec2_audit_probe.py` (streaming loaders), `exec2_audit_measure.py` (measurements), `exec2_audit_cluster.py` (phase-independent control, game bootstrap).
- Command: `python docs/evidence/harness/exec2/exec2_audit_measure.py 2026-09-22 2026-09-23 2026-09-24 2026-09-25 2026-09-26 2026-09-29` (days with a served schedule; 09-27 and 09-28 have none). Peak working set 82 MB, 11 s.
- Conventions: YES cents. Timestamps via `venue_time.parse_venue_time` (r1 used `datetime.fromisoformat`, which on Python 3.10 rejects short fractional seconds and dropped about 10 pct of prints). Book and marks = focus `snapshot` rows only (depth, ~5.2 s cadence); a mark is the first snapshot in [t+h, t+h+10 s]. Tape = `trade` rows deduplicated by trade_id; venue `created_time` for matching; `taker_side == "no"` fills a resting YES bid, `"yes"` a resting YES ask (both critics confirmed this against the book). In-game window = first live state CHANGE (first play) to the final row, capped at 6 h. State events typed score / period / play on the MLB source clock `last_play_ts` (receipt fallback counted separately).
- Controls: clock-grid instants every 30 s with a seeded random phase, the same prior-book rule (book <= 10 s old), the same horizon censoring (a coverage gap > 10 s censors that instant for that horizon) and, for the before-receipt test, lags drawn from the event lag distribution.
- Intervals: 90 pct game-cluster bootstrap (2,000 draws, seed 7), pooled per sport, INSUFFICIENT under 3 games. Per-game sufficient statistics are in the receipt.

## Measured baseline (MLB; NFL is INSUFFICIENT: 1 game, no source clock, no tape)

### Coverage

| Served entries 09-22..09-29 | 22 |
|---|---|
| with live state | 12 (09-23 and 09-26 served games have none: capture down) |
| with depth snapshots in-game | 11 |
| with in-game prints (OK) | 8; TAPE_MISSING: 09-22 MIL@PHI, the MNF game, 09-29 PHI@ATL |
| depth minutes per OK game | 31-60 of 134-360 live minutes (one game 131) |
| tape receipt lag (capture time - created_time), per-game p50 | 259 s to 3,981 s |

- Depth exists only for about the first hour of each game (focus window; heartbeat `focus_tick_s 5`, `maximum_scheduled_games_per_hour 2`). After that only `snapshot_bulk` rows (no depth, ~20 min apart) exist.
- Every in-game print reaches the archive through the trade backfill, minutes to hours after it happened. A live policy cannot see the tape in time with the current capture; any tape-driven trigger is replay-only until the capture delivers prints in near real time.
- Live status rows start 14-22 min before the first pitch; one game has no final row (6 h cap); NFL state carries no source clock.

### Where the current policy stands (zero-inventory construction baseline, not a lifecycle)

- Clock-grid decisions: 1,032; quoted 922, pulled `state_change` 61, `stale_book` 49.
- Distance of the engine price behind the touch: 2c at a 1c spread (1,634 sides), 1c at 2-3c spreads (192), 0c at 4-5c spreads (18). At qty 1 the repo fee function charges 1c at every interior price (`venue_fees.fee_kalshi_maker(1, p) = 0.01`), so `half = 1c fee + 1c padding`. The per-contract fee at larger sizes depends on account precision and rounding rules that are not verified (`venue_fees.py:8`); no sizing conclusion is drawn from it.

### State events vs the book

| P(mid moves >= 1c within w), pct | 5 s | 15 s | 30 s | 60 s |
|---|---|---|---|---|
| Control (clock grid, 10 games) | 14.1 [11.1, 16.7] | 34.8 [30.4, 38.5] | 52.6 [48.9, 56.1] | 72.8 [69.4, 76.3] |
| After a play (n = 997) | 24.0 [18.8, 28.2] | 41.3 [35.7, 45.6] | 63.8 [57.8, 68.5] | 85.7 [80.7, 89.3] |
| After a score (n = 28) | 17.9 [9.3, 30.4] | 39.3 [29.7, 54.6] | 46.4 [36.4, 58.8] | 64.3 [48.4, 80.0] |
| After a half-inning change (n = 119) | 21.0 [15.4, 27.9] | 27.6 [19.9, 36.5] | 43.0 [34.0, 52.7] | 65.1 [56.6, 75.5] |

- The state receipt lags the play by p50 21.4 s (p10 13.0, p90 33.5), mostly our state poll interval.
- The book moved between the play and our receipt after 50.4 pct [44.5, 55.5] of plays vs 42.9 pct [39.1, 46.5] at control instants with the same lag distribution: an excess of about 7.5 points. A cancel keyed on our state receipt is late relative to the reprice about half the time; the fix is mostly state capture cadence (S556), and book-driven triggers in the replay (S551).

### Adverse selection (fee excluded, cents per contract, maker perspective, 7-8 MLB games with tape)

| Every print as a maker fill at its price | +5 s | +30 s | +60 s | +120 s |
|---|---|---|---|---|
| print-weighted | +0.39 [+0.12, +0.56] | +0.28 [-0.09, +0.59] | +0.24 [-0.18, +0.65] | +0.14 [-0.42, +0.73] |
| contract-weighted | -0.03 [-0.55, +0.30] | -0.13 [-0.74, +0.28] | -0.28 [-0.84, +0.13] | -0.24 [-0.74, +0.11] |

| Independent 1-contract joins, clock grid | fill in 60 s | fill in 300 s | through-print share of fills | price vs mid at fill | price vs mid at fill +60 s |
|---|---|---|---|---|---|
| At the touch, displayed size ahead | 33.6 pct [25.0, 42.4] | 60.4 pct [45.3, 76.9] | 92.6 pct | +0.40c | -0.67c [-0.86, -0.50] |
| Engine price (0-2c behind) | 13.5 pct [10.3, 16.0] | 40.9 pct [31.6, 50.5] | 93.6 pct | +1.52c | -0.15c [-0.61, +0.31] |

- Large prints are more adverse than small ones (contract-weighted below print-weighted at every horizon).
- About 93 pct of simulated fills come from prints trading THROUGH the resting price (the displayed queue ahead is 10^4-10^5 contracts), so the join fills are dominated by sweeps and are adverse by construction; the after-fill move is about -1.1c at the touch and about -1.7c for the engine price. These joins overlap and can share prints; they describe opportunities, not a policy's throughput.
- No monotone gradient by seconds since the last state event was found at this n (r1 buckets; not repeated in r2).

## EXECUTION 2.0 rows (S550-S559), revised after both critiques

Each built row is a pure function or an offline archive replay under `scripts/platformkit/execution/` (<= 300 LOC per file), with construct tests plus a real-row fixture of verbatim captured records. None starts a process, flips a flag, or edits a capture, S515-S519 or paper_desk_* file.

1. **S550 EXECUTION-QUALITY AUDIT RECEIPT (build).** Productionize r2 as `exec_quality_audit.py` (+ io helper): versioned estimand definitions, input shas, parse/exclusion denominators, the coverage census per game (OK / TAPE_MISSING / NO_DEPTH / NO_LIVE_STATE), horizon-censored denominators, the phase-independent control with matched lags, print- and contract-weighted markouts, through vs depletion fill split, per-game sufficient statistics, INSUFFICIENT below 3 games per pool. Deterministic content only (runtime memory goes to a side file). Receipt `docs/evidence/forward/exec_quality/<first>_<last>.json`. Moves no target by itself; it is the ruler.
2. **S551 OFFLINE CANCEL-POLICY REPLAY WITH A SEALED PREREGISTRATION (build machinery now, score later).** Stateful replay with a causal ordering contract: book observations at capture receipt, state at receipt, tape at its capture receipt (so tape triggers are replay-labelled); per instant, matching runs first while the order rests, then the policy decides, then submission and cancel latency (>= one snapshot interval + round trip) apply; fills during a pending cancel count; replacement loses priority. Arms: static touch, static engine, cancel-on-book-move (opposite touch moves to or through the quote), cancel-on-state-receipt, and both. Queue scenarios: through-only and displayed-depletion. Primary metric: fee-inclusive markout at fill +60 s per filled contract, reported with fill rate, quote uptime and the adverse tail on a shared eligible opportunity set; paired by game. The preregistration (arms, grid, clocks, latency, queue scenarios, fees, horizons, censoring, weighting, minimum 20 tape-complete games, multiplicity) is sealed BEFORE any scored run and scores only games after the seal date. It reuses `tape_fill_sim` / `markout_causal` primitives where their contracts fit, so numbers agree with S516.
3. **S552 TAPE FILL-PROBABILITY MODEL (deferred).** Only after S551 accrues tape-complete games; expanding chronological folds with embargo, train-only baselines stratified by distance and spread, a frozen target (any fill vs full fill), reliability curves. Labels are about 93 pct trade-throughs today.
4. **S553 PER-SPORT EVENT-LATENCY TABLE (descriptive).** Per sport: source-to-receipt lag split into poll cadence and source delay, the book-response curve vs the phase-independent control, provenance-stratified. It sets no policy parameter until one is derived on a training window and validated prospectively.
5. **S554 CALIBRATION-BOUNDED SKEW (deferred, stays OFF).** Revised direction: permitted skew SHRINKS as the calibration uncertainty grows, with an absolute tick cap, a frozen model, past-only calibration evidence and minimum band support; the mid stays the default anchor (`quote_engine.py:3-5`). Waits for a calibrated in-game probability (S519 / the S540 block).
6. **S555 SIZE AND INVENTORY LADDER (deferred).** Depends on S552; must keep `quote_engine.py:170` (never raise size only to change fee rounding) and needs verified account fee precision first.
7. **S556 CAPTURE COVERAGE FOR EXECUTION (owner: the capture owner, orchestrator 1).** Registered, not built here: tape arrives minutes to hours late (backfill), the one-hour focus window, focus lost while a served game is live (09-29 PHI@ATL, last focus snapshot 18:59:58Z), live status before the first play, a missing final row, no NFL source clock, and the 09-23/09-26 capture gaps. Capture completeness should gate any confirmatory execution measurement.
8. S557-S559 reserved.

Build order now: S550, then S551 (machinery + sealed prereg). S553 after S551. S552/S554/S555 deferred with stated preconditions. S556 handed to its owner.

## Risk gate (prediction-market-risk-review)

Applied to every row: no venue client, auth, key, order route or executor import (a test asserts the import closure); no network; read-only over the capture archive; outputs under `docs/evidence/forward/exec_quality/` or the replay ledger path; no feature flag; no long-running process; execution-quality wording only (the preflight vocabulary gate runs on every file). Shadow -> live promotion is out of scope.

## Critiques folded in (AMENDMENT 1, 2026-09-29 ~20:1xZ)

Both critics returned REVISE on r1. Verdicts: `docs/evidence/harness/exec2/critique_astra_r1.md` (codex gpt-6-astra, 24 findings) and `critique_opus_r1.md` (Opus adversarial, re-derived numbers with its own scripts).
- Fixed in r2: the base-rate control sat on snapshot timestamps (the r1 "17x" line is retracted; the lift is about 1.7x at 5 s and 1.2x at 15-30 s); the before-receipt share now has a matched-lag null; TAPE_MISSING games no longer count as zero fills (touch fill in 60 s: r1 22.7 pct, r2 33.6 pct); the Python 3.10 timestamp parser dropped about 10 pct of prints; horizon censoring; contract weighting; through vs depletion split; marks from focus snapshots only; the window starts at the first play; per-sport pools; per-game sufficient statistics; deterministic seeds.
- Folded into the rows: tape look-ahead (prints arrive by backfill; replay-labelled triggers only), the causal ordering and latency contract for S551, the sealed prereg on untouched games, S552 chronological folds, the S554 bound direction, the S555 fee-precision premise and size rule, S553 derivation discipline, the S515/S516 interface boundary, S556 evidence items.
- Kept as NOTES: the engine distance at wider spreads; the r1 time-since-event buckets used the source clock (look-ahead for a policy; r2 uses the receipt clock for the engine); the join proxy is an opportunity description, not policy throughput.
