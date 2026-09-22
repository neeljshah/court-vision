GAP S343 | sport all (maker channel) | worktree (claude sonnet, isolated) | log cx_s343_causal_markout
# Causal, fee-complete markout (astra round 10 rank 3)

SINGLE PROBLEM: scripts/platformkit/execution/markout.py cannot enforce its own measurement contract: line 49 turns a
MISSING fee into 0.0 (`_f(...) or 0.0`), and lines 86-89 delegate the no-look-ahead rule to the caller.

BINDING BEFORE-CONDITION (re-run, quote the output): `grep -n "or 0.0" scripts/platformkit/execution/markout.py` shows line 49;
`grep -n "NO LOOK-AHEAD is the CALLER" scripts/platformkit/execution/markout.py` hits.

CHANGE (ADDITIVE ONLY -- contract B2: markout() and markout_summary() keep their signatures and current behaviour; add beside them):
1. NEW scripts/platformkit/execution/markout_causal.py (<= 300 LOC, stdlib, ASCII, no writes):
   `resolve_marks(fill, ticks, horizons_s=(30,120,300), max_wait_s=...)` picks, per horizon, the FIRST tick of the SAME
   ticker/game with ts >= fill_ts + horizon and ts <= fill_ts + horizon + max_wait_s; non-overlapping bounded windows; a tick
   that is stale, suspended, terminal or from another game is never a mark; one tick is never reused for two horizons of one fill.
   `markout_strict(fill, mark)` returns None with a reason code (never 0.0) when the fee is missing/unknown, fill_ts or mark ts
   is missing, mark ts <= fill_ts, or the fee schedule version is absent. Entry fee netted; exit fee and remaining inventory
   reported as SEPARATE fields, never folded in.
   `summary_strict(...)` reports n_intents, n_fills, n_scored, n_unscored by reason, per-horizon mean + game-clustered CI
   (reuse entry_timing.study.cluster_boot_ci), leave-one-game-out range, largest single-game share.
2. tests/platformkit/execution/test_markout_causal.py: injections from the astra suspicion list -- missing fee, pre-decision
   timestamp, reused horizon observation, cross-game tick, stale/suspended mark -- EVERY case must come back unscored with a reason.
3. `_demo()` assert self-check.

CONTROLS: construct tests only; NO number is measured on any archive in this row (no tape with fills exists yet). Units are
probability points per contract. ACCEPTANCE: both per-file test runs pass; existing tests/platformkit/execution/test_markout.py
still passes untouched; diff = NEW files only. Vocabulary follows contract Q6; automated scan required. Memo (docs/evidence/harness/
S343_causal_markout_2026-09-21.md) ends with a NOT VERIFIED list.
