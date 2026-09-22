# S342 quote engine - 2026-09-21

Verdict: PREPARE-ONLY build checks PASS; runtime behavior NOT VERIFIED.
Vocabulary follows contract Q6; automated scan required.

Scope: three NEW files only in C:/Users/neelj/nba-harness-h1, branch harness-h1.
Machine: local Windows worktree; deterministic constructs need no remote compute.
No data/ access, parameter fitting, scoring, deployment, flag changes, or caller wiring.

## Premise

PowerShell Select-String was used because rg is unavailable. The equivalent
assignment-only search returned:

```text
scripts/platformkit/execution/paper_maker.py:39:_QTY = 1
scripts/platformkit/execution/paper_maker.py:48:_ASSUMED_HALF_SPREAD_CENTS = 1
```

Before construction, Test-Path scripts/platformkit/execution/quote_engine.py
returned False. The full unanchored search also matched comments at lines 27
and 201. The premise holds; paper_maker.py remains unchanged.

## Construction and configuration

The new module accepts a caller anchor in cents; None uses the current observed
book mid. Prices round outward on the one-cent grid, using the canonical maker
fee at each candidate's final price and actual whole-order size. Selection input
is per side. The existing adverse-drift constant INGAME_MAX_DRIFT_PCT from
scripts/platformkit/execution/thresholds.py:14 is the declared default proxy in
cents; it is not a fitted maker-selection estimate. No dedicated maker-selection
constant exists in that file. k_sd and k_inv are required caller parameters.

Inventory shifts both prices downward for a long position. The engine constrains
size by per-order, position, per-game, same-game correlated-contract, and global
rooms supplied by the external risk owner. Disabled sides have explicit reason
codes; remaining active sides use a common size. Size is never raised to change
fee rounding. Production must reserve capacity atomically and account for all
outstanding orders outside model output; this pure builder cannot certify that
its caller supplied accurate capacity.

Freshness uses scripts/platformkit/ingame/quote_freshness.py state-clock helpers.
Suspension markers mirror scripts/platformkit/execution/paper_maker.py:19-22,51-60
without importing its execution stack. Missing clocks and rooms are explicitly
unavailable input, not classified as stale evidence. State changes pull quotes.
Below the flatten deadline only reducing quotes remain, capped at existing
inventory. At expiry all quotes pull. Unresolved inventory remains visible on
every return; constructing a maker quote does not imply any fill.

## Reproduction

Run from C:/Users/neelj/nba-harness-h1 with PYTHONDONTWRITEBYTECODE=1 and
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 (no bytecode or third-party plugin side effects):

```text
python -m pytest tests/platformkit/execution/test_quote_engine.py -q -p no:cacheprovider
38 passed
python -m scripts.platformkit.execution.quote_engine
S342 quote_engine self-check PASS (CONSTRUCT; PREPARE ONLY)
```

The spec names one test path despite saying "two test files"; only that named
file was run. n = 38 (CONSTRUCT) collected tests, including exhaustive loops over
listed suspension statuses and the Cartesian grid of anchors, inventories,
order sizes, and observed touches. These are implementation checks, not sampled
or scored observations. No cases are excluded to compute a metric.

Contract B review: additive new API only; no existing readers, schema, claims,
queues, routes, or thresholds changed; no deployment, selection, scoring, or
retirement. Q1-Q5/Q9 scoring requirements are inapplicable to PREPARE constructs;
Q3 constants stay unchanged. Q6 automated scan covers all three new files;
Q7 construct enumeration is in the test file; Q8 premise was checked first.
ASCII and Q6 scans must report PASS before handoff. The scan rejects prohibited
prose tokens and retracted numeric strings, with the contract Q6 identifier
exception available but not needed for these files. No existing tracked diff.

## Handoff

Created paths:
- scripts/platformkit/execution/quote_engine.py
- tests/platformkit/execution/test_quote_engine.py
- docs/evidence/harness/S342_quote_engine_2026-09-21.md

No commit attempted: .git points to metadata under nba-ai-system, outside the
user-authorized write boundary. Register and ledger edits are deferred to landing
because this row permits NEW files only.
SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- Production integration, live order submission, and concurrent capacity reservation.
- Caller exposure accounting across games, correlated contracts, and outstanding orders.
- Calibration on observed corpora or any scored replay; a successor needs a sealed prereg.
- Selection proxy suitability and caller-supplied uncertainty/inventory coefficients.
- Queue position and true fill rates: scripts/platformkit/execution/book_replay.py:13-19
  documents that neither archive contains a per-trade price tape. Archives were
  not opened here; these remain unmodeled until capture records trades.
- Guaranteed flattening: maker-only quotes can leave unresolved inventory.
- Venue schedule exceptions beyond the existing canonical fee helper.
- Master-tree reproduction, landing, and commit creation.
