# S343 causal, fee-complete markout (astra round 10 rank 3)

Verdict: NOT VALIDATED. The strict-scoring path is implemented and verified on
construct tests only. No number is measured on any archive (no fill tape
exists yet for this channel), so no live acceptance claim is made.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Spec: `docs/evidence/tracking/specs/S343_spec.md`.

This memo covers the ORIGINAL build plus TWO FIX ROUNDS after an independent
verifier (codex gpt-5.6-sol) rejected earlier commits: lane 1b (four blocking
findings plus one correction) and lane 1c (one remaining blocker, where the
lane 1b fix itself diverged from the spec's window definition). Each is
addressed below and re-verified by the test run in this file.

## Before-condition (re-run, quoted)

```text
$ grep -n "or 0.0" scripts/platformkit/execution/markout.py
49:    cost = _f(fill.get("fee_units") if fee is None else fee) or 0.0

$ grep -n "NO LOOK-AHEAD is the CALLER" scripts/platformkit/execution/markout.py
87:    NO LOOK-AHEAD is the CALLER's responsibility and is NOT enforced here: this
```

Both confirmed present and unchanged. `markout.py` still turns a missing fee
into `0.0` and still delegates the no-look-ahead rule to its caller.

## What was built

`scripts/platformkit/execution/markout_causal.py` (298 LOC) plus a split file
`scripts/platformkit/execution/markout_causal_windows.py` (134 LOC, pulled
out in the lane 1b fix round to keep the first file under the 300 LOC rail),
both stdlib + in-repo reuse only, additive beside `markout.py` -- that
module's `markout()` and `markout_summary()` are untouched (byte-identical;
see test run below).

- `resolve_marks(fill, ticks, horizons_s=(30,120,300), max_wait_s=30.0)` --
  per horizon, picks the first tick in that horizon's window that is
  same-game, not suspended/terminal/stale, and carries a usable mid. A tick
  is never scored twice.
- `markout_strict(fill, mark)` -- returns `MarkoutResult(value, reason,
  exit_fee_units, remaining_inventory_qty)`. `value` is `None` (never a
  fabricated `0.0`) with a reason code when the fee is missing/non-finite, the
  `fee_schedule_version` field is absent, `fill_ts` or the mark's `ts` is
  missing/non-finite, or the mark is not strictly after the fill
  (`mark_ts <= fill_ts`). `exit_fee_units` and `remaining_inventory_qty` are
  always reported as separate fields, never folded into `value`: at mark time
  no exit fill has occurred, so an exit fee is genuinely unknown (not zero)
  and the fill's whole quantity is still open inventory.
- `summary_strict(fills, ticks, ..., n_intents=None, intents=None)` --
  `n_intents`, `n_fills`, `n_scored`, `n_unscored`, `n_fill_horizon_observations`,
  `n_unscored_by_reason`, then per horizon: `n`, `n_clusters`, `mean_units`, a
  game-clustered 95% CI (reuses `entry_timing.study.cluster_boot_ci`),
  `verdict`, `leave_one_game_out_range_units`, and `largest_single_game_share`.
- `_demo()` assert-based self-check; runs clean (`python -m
  scripts.platformkit.execution.markout_causal` -> `markout_causal self-check
  OK`).

**Sign convention** (identical to `markout.py`, restated here because
`markout_strict` reimplements the arithmetic under its own stricter gates):
side `"yes"` scores `later_mark_mid - fill_price`; side `"no"` scores
`(1 - later_mark_mid) - fill_price`; the entry fee is then subtracted as a
magnitude, so it can only ever reduce the number. Units are probability
points per contract, never anything else.

## Fix round 1b -- every verifier finding

1. **BLOCKING, overlapping/order-dependent windows.** Fixed in
   `markout_causal_windows.validate_horizons` (sorts horizons ascending,
   rejects non-unique/non-positive/non-finite ones with `ValueError`) and
   `partition_windows` (window `k` is
   `[fill_ts + h_k, min(fill_ts + h_k + max_wait_s, fill_ts + h_{k+1}))` --
   capped at the next horizon's start, so consecutive windows satisfy
   `hi_k <= lo_(k+1)` and never overlap). `resolve_marks` now keys off this
   validated, sorted tuple regardless of the order `horizons_s` was passed
   in. Tests: `test_windows_never_overlap_regardless_of_horizon_order`
   (reversed `(40.0, 30.0)` vs `(30.0, 40.0)` produce an identical result),
   `test_tick_exactly_at_horizon_start_belongs_to_that_horizon`,
   `test_tick_exactly_at_next_horizon_start_belongs_to_the_next_horizon`,
   `test_duplicate_or_bad_horizons_raise_value_error`.
2. **BLOCKING, non-finite values scored.** `markout_causal_windows.finite()`
   is now the ONE shared numeric gate (`math.isfinite`, rejects bool, NaN,
   +inf, -inf) used for every timestamp (via `_epoch`), fee, price and mid in
   both `resolve_marks` and `markout_strict`. Tests:
   `test_non_finite_fee_is_unscored`, `test_non_finite_fill_ts_is_unscored`,
   `test_non_finite_mark_ts_is_unscored`, `test_non_finite_price_is_unscored`,
   `test_non_finite_mid_is_unscored` -- each loops NaN/+inf/-inf and asserts
   an unscored result with the matching reason code.
3. **BLOCKING, fabricated n_intents.** `summary_strict` no longer sets
   `n_intents = len(fills)`. It now accepts an optional `n_intents` count or
   an `intents` sequence to count; with neither supplied it returns `None`.
   The scored denominator is separately labelled
   `n_fill_horizon_observations` (`= n_scored + n_unscored`, one per
   fill-per-horizon pair, not one per fill) -- an ADDED key; `n_scored` /
   `n_unscored` / `n_fills` are unchanged. Tests:
   `test_n_intents_uses_explicit_count_or_sequence_never_a_fill_count_stand_in`,
   `test_n_fill_horizon_observations_is_the_true_denominator` (folded into
   `test_summary_strict_aggregates_per_horizon_with_clustered_ci`).
4. **BLOCKING, collapsed reasons.** `resolve_marks` now returns one of
   `suspended_mark`, `terminal_mark`, `stale_mark`, `cross_game_mark`,
   `mid_unusable_mark`, `no_tick_in_window`, `bad_fill`, `fill_ts_missing`,
   `ticker_missing` per rejected horizon (see `reason_for_tick` in the
   windows file for the fixed check order used when one candidate fails more
   than one test). `summary_strict` was changed to read `entry["reason"]`
   directly when `resolve_marks` found no mark, instead of always calling
   `markout_strict(fill, None)` first (which returned the generic
   `mark_missing` and discarded the specific resolver reason). Tests:
   `test_cross_game_tick_reason_is_specific`,
   `test_suspended_tick_reason_is_specific`,
   `test_terminal_game_state_reason_is_specific`,
   `test_stale_repeated_tick_reason_is_specific`,
   `test_mid_out_of_range_tick_reason_is_specific`,
   `test_summary_strict_counts_unscored_by_specific_reason` (asserts
   `n_unscored_by_reason == {"suspended_mark": 1}`, not `{"mark_missing": 1}`).
5. **CORRECTION, memo order.** This file now ends with NOT VERIFIED; "New
   files" moved above it.

## Fix round 1c -- the one remaining blocker

The lane 1b fix made every window `[lo, hi)` half-open, which was the
ORCHESTRATOR's own fix instruction, not the spec. The spec wins: a mark is
valid when `ts >= fill_ts + horizon AND ts <= fill_ts + horizon + max_wait_s`
-- both ends inclusive. Half-open rejected a tick exactly at an uncapped
upper bound, and an infinite `max_wait_s` would have made the final horizon's
window unbounded (never actually reachable before this fix, since nothing
validated `max_wait_s`).

Fixed in `markout_causal_windows.py`:
- `validate_max_wait_s(max_wait_s)` -- the same `finite()` gate as
  `validate_horizons`, plus `>= 0`; raises `ValueError` otherwise. Called from
  both `resolve_marks` and `summary_strict` before any window math.
- `partition_windows` now returns `(lo, hi, hi_inclusive)` per horizon: the
  upper end `fill_ts + h_k + max_wait_s` is INCLUSIVE by default; it is
  capped at the next horizon's start, and only THEN made EXCLUSIVE, when it
  would coincide with or pass that start. The last horizon (nothing to cap
  against) is always inclusive at its own bound -- safe now that
  `max_wait_s` is guaranteed finite. `resolve_marks`'s window-membership
  check reads that third element (`lo <= ts <= hi` vs `lo <= ts < hi`)
  instead of assuming `<`.

This is a pure boundary-condition fix: horizons still partition the timeline
with no overlap and no double-assignment (a coincidentally-capped bound is
still exclusive on exactly one side), so every lane 1b guarantee still holds.

Tests: `test_tick_exactly_at_uncapped_endpoint_scores` (a tick exactly at
`fill_ts+h+max_wait_s` with nothing to cap it now scores, where it was
dropped before), `test_tick_one_past_uncapped_endpoint_is_out_of_window`,
`test_tick_exactly_at_next_horizon_start_belongs_to_the_next_horizon`
(re-affirms the still-exclusive capped case), `test_bad_max_wait_s_raises_value_error`
(NaN, +inf, -1 each raise), `test_zero_max_wait_s_accepts_only_the_exact_horizon_tick`
(`max_wait_s=0` scores a tick exactly at `fill_ts+h_k` and rejects one 1ms
early or late).

## Tests and reproduction

Codex's sandbox could not run pytest (no writable temp dir in its read-only
sandbox); the runs below, from this worktree, are the only test evidence for
this row.

```text
$ python -m pytest tests/platformkit/execution/test_markout_causal.py -q -p no:cacheprovider
..............................
30 passed in 0.80s

$ python -m pytest tests/platformkit/execution/test_markout.py -q -p no:cacheprovider
.............
13 passed in 0.54s
```

The second run is the pre-existing suite, unmodified, confirming `markout.py`
was not touched. The new suite (30 tests, up from 16 at the original commit)
covers the happy path for both sides, the separate
`exit_fee_units`/`remaining_inventory_qty` fields, every astra
suspicion-list injection with its exact reason code, the
deterministic/order-independent window partition including the lane 1c
inclusive/exclusive boundary cases, horizon- and `max_wait_s`-validation
errors, all four non-finite-number categories, and `summary_strict`'s
`n_intents`/`n_fill_horizon_observations`/reason-tally behavior.

`git status --porcelain` in this worktree shows `markout_causal.py`,
`markout_causal_windows.py` and `test_markout_causal.py` modified (across
both fix rounds, on top of the lane 1b commit that first added
`markout_causal_windows.py`); `markout.py` and `test_markout.py` show no diff.

## Contract self-check

- B1: no metric excludes rows that would fail it; construct-only.
- B2: `markout()`/`markout_summary()` signatures and behavior unchanged, test
  run above confirms it. `summary_strict`'s new `n_fill_horizon_observations`
  key is additive; no existing key was removed or renamed.
- B3-B6: no gate, deploy, move, retirement, import, or module reference
  changed.
- B7-B9: the test suite enumerates every listed injection case, not a head
  slice; nothing is scored against its own fitting set; no denominator is
  recycled.
- B10: no threshold moved (none exists in this row).
- Q1, Q2, Q4, Q5, Q9: no prereg-sealed comparison, charged trial, OOS model,
  AHEAD verdict, or paired-loss archive claim is made; nothing is scored
  against real data.
- Q6: automated case-insensitive substring scan for the four contract Q6
  restricted terms over all three new source files returned 0 hits.

  Vocabulary follows contract Q6; automated scan required.
- Q7: all counts in the new tests are `n = <k> (CONSTRUCT)` enumerations of
  hand-built fixtures, not sampled or scored data.
- Q8: the premise (the two before-condition greps) was re-measured first and
  confirmed still true.
- No pod contact, no `data/` read or write, no flag changed, no `--force` used.

## New files

- `scripts/platformkit/execution/markout_causal.py` (298 LOC)
- `scripts/platformkit/execution/markout_causal_windows.py` (134 LOC)
- `tests/platformkit/execution/test_markout_causal.py` (262 LOC)
- `docs/evidence/harness/S343_causal_markout_2026-09-21.md` (this file)

## NOT VERIFIED

- No live fill tape exists for this channel yet, so `resolve_marks` /
  `markout_strict` / `summary_strict` have never scored a real fill or a real
  tick stream -- construct tests only.
- `paper_maker._fill_record` (human-gated, not edited here) does not stamp a
  `fee_schedule_version` field today. Every real fill from that path will
  therefore read as unscored with reason `fee_schedule_version_missing` until
  that field is added there -- a change this row deliberately did not make.
- `n_intents` has no real source yet: this channel only ever materializes a
  fill record once an order actually fills, so a never-filled intent is not
  observable at this layer. Passing `n_intents`/`intents` requires an
  upstream intent feed that does not exist yet; absent one, callers get
  `None`, never a fabricated count.
- The stale-tick check reuses `quote_freshness.freshness_mask`'s syntactic
  definition (identical to the immediately preceding tick of the same game);
  it has not been validated against a real tick stream's actual repeat-rate
  for this channel.
- `is_suspended`/`is_terminal` in `markout_causal_windows.py` are a
  hand-mirrored copy of `paper_maker._market_suspended`'s private logic (that
  module is human-gated and was not imported from); the two have not been
  cross-checked against each other on real data and could drift if one
  changes.
- The default `max_wait_s = 30.0` and default horizons `(30, 120, 300)` are
  unvalidated choices carried over from the spec's example; no latency
  distribution for this channel has been measured to justify them.
- `leave_one_game_out_range_units` and `largest_single_game_share` are
  diagnostics with no prior usage in this codebase to compare against.
- `reason_for_tick`'s fixed check order (suspended, then terminal, then
  stale, then mid-range) for a candidate failing more than one test at once
  has not been cross-checked against how a real venue feed actually combines
  these conditions -- it is a deterministic tie-break, not a claim about
  which failure is most common or most important.
- The lane 1c inclusive-uncapped/exclusive-capped window boundary is a
  construct-test-only reading of the spec sentence; it has not been checked
  against how a real venue's tick clock resolution (whole seconds vs
  sub-second) would actually interact with an exact-equality boundary.
