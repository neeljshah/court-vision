# S667 cloud result -- 2026-09-30 (risk_limits: sealed limit table + seven risk scopes after AMENDMENT 3)

Branch `cloud/S667-2026-09-30`, cut FROM `cloud/S666-2026-09-30` (38812e7b). S666 (risk_delta) is
BUILT and verified on its branch but not yet on trunk, so this branch carries S666's commits
underneath; no S666 file was modified. Land S666 first (or together). Routine: desk-improve,
ONE-OFF OVERRIDE pinned to S667 (slate `QUANT_GRADE_BUILD_SLATE_2026-09-30.md` section 3a). Paper
only; execution-quality language only (contracts; points = contracts x cents against the mark).
No register or DESK_STATE edit on the branch; nothing landed; nothing pushed to trunk.
`git ls-remote --heads origin 'cloud/S667*'` was empty before the build.

## Verdicts

| Tier | Who | Verdict |
|---|---|---|
| Pre-build critic | independent Opus sub-agent (codex not available in the cloud) | REVISE, 13 items, all folded as spec AMENDMENT 1 |
| CONTRACT round 1 (A/B/Q + spec + A1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (5 test-strength gaps + memo) |
| ADVERSARIAL round 1 (probes + mutants) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS: F1 material (stacked reduce orders unbounded), 3 surviving mutants |
| Fix | builder | AMENDMENT 2 (pure-reduction definition tightened) + tests for every gap |
| CONTRACT round 2 (the one re-verify) | same sub-agent | ACCEPT WITH CORRECTIONS (memo/spec line only: A2.1 supersedes one A1.1 case -- added) |
| ADVERSARIAL round 2 | same sub-agent | ACCEPT WITH CORRECTIONS (refusal-ordering test could not see a wrong sort -- fixed; the sort-by-post mutant now fails a test) |

Codex was NOT used. The critic and both verifier tiers were separate Opus sub-agents; none wrote
the build. Round 2 is the single allowed re-verify; both corrections after it are test/spec text
only (no code change after round 2).

## Premise (Q8)

Re-measured: `check_caps` returns exactly {reducing, per_order, per_game, correlated, global,
permitted, max_permitted_qty}; unknown cap keys (per_sport, slate) are ignored and a 100-contract
order passes (`test_premise_and_committed_table_pinned`). No per-sport / settlement-hour / slate
scope exists and no scope reads a netted worst cell. Premise holds.

## What was built (new files only)

- `scripts/platformkit/execution/risk_limits.py` (256 lines after AMENDMENT 3; pure, Decimal, floats refused).
  `check_limits(snapshot, table, *, order_id, ticker, game_id, side, qty, leg_map, marks_cents,
  game_meta, draws_possible=None, pin=None)`. The proposed order is reserved as open unfilled qty
  (a new order_id, or a top-up of the same open order_id), so every fill scenario counts. Scopes:
  per_ticker_contracts (check_caps' per_game scope, unchanged), per_game_worst_cell_points (S666
  worst cell, unclamped), per_game_net_delta_contracts (max |lo|,|hi| over every leg-mapped
  ticker whatever its mark or grid status, so GRID_OVERFLOW or a missing mark cannot hide
  delta), per_sport_points / per_family_points / per_settle_hour_points / slate_points (sums of max(0, worst cell);
  games never offset each other). Missing game_meta -> UNKNOWN buckets. Report: permitted,
  reducing, refusals (sorted by scope, key), breaches, scopes {key, current, post, cap,
  breached}, table_seal, table_version. No sizing, no runtime caller (PREPARE only).
- `scripts/platformkit/execution/risk_limit_table.json`: schema s667_limit_table_v1, version 2,
  seal 8ea6a3c70555cfab5d05af7f5cfa765c3066de1f9224fe8aad40184dfdd7e74b (canonical as
  PREREG_S551), pinned as TABLE_SEAL. DECLARED values, not fitted to any window: per ticker 5
  contracts; per game worst cell 1000 points; per game net delta 5 contracts; per sport 3000; per family 3000;
  per settlement hour 2000; slate 5000 points. Rationale: round numbers above the desk's current
  1-contract paper quoting. Changes only by amendment (version + amendments entry + new
  TABLE_SEAL). Refusal codes seal_mismatch / not_pinned / schema, each reached by a test.
- AMENDMENT 2: a pure reduction is check_caps' `reducing` AND qty + resting same-side open qty
  <= |net|. Without it, 30 stacked NO 1 orders on net +1 were each "reducing" and lifted
  per_ticker to 29 against cap 5 (adversarial probe P1). This tightens a definition; no bar moved.
- `tests/platformkit/execution/test_risk_limits.py` (300 lines, 27 tests after AMENDMENT 3),
  and `test_risk_limits_family.py` (one family construct test at that point).

## Tests (one file per process, Python 3.11.15, Ubuntu cloud clone)

- `python3 -m pytest tests/platformkit/execution/test_risk_limits.py -q -s` -> 26 passed (~37 s)
- `python3 -m pytest tests/platformkit/execution/test_risk_delta.py -q` -> 26 passed (S666, unchanged)
- Property line (seed 667, 10,000 sequences x 8 steps, <= 3 games, 2 sports, 3 hours, one in four
  sequences with a game lacking meta): `{"cancels": 6395, "elapsed_s": 37.0, "fills": 15622,
  "permitted_inc": 38921, "red_over": 3, "red_raise": 124, "reducing": 2778, "refused":
  {"per_game_net_delta_contracts": 1781, "per_game_worst_cell_points": 11120,
  "per_settle_hour_points": 2796, "per_sport_points": 1255, "per_ticker_contracts": 866,
  "slate_points": 345}}`. Bars: (1a) every permitted non-reducing step leaves every key <=
  max(cap, pre); (1b) fills and cancels never raise any key; (1c) with reductions disabled every
  key stays <= cap; (2) no reducing order refused. Reducing steps are counted, not excluded:
  124 raised a netted measure (e.g. selling one leg of a hedge), 3 of those above a cap.
  The oracle recomputes every key from risk_delta, exposure_book and its own delta sum on the
  post-submit ledger snapshot (position_reducers.positions), not from check_limits' report.
- Mutation: round 2 adversarial table -- every targeted mutant killed except three that are
  behaviour-identical or redundant (drop parse_float, which _float_free still catches; drop the
  per_ticker breached override, which is the same comparison as check_caps); the refusal-sort
  mutants that survived round 2 are now killed by the corrected ordering test.
- Must-not-move: `git diff 38812e7b HEAD --stat` = the four S667 files plus this memo;
  position_caps, position_exposure, position_decimal, position_reducers, quote_engine,
  paper_maker, paper_account, risk_delta byte-identical; no PREREG*.json under
  docs/evidence/forward names a changed path (S519 code_identity included).

## NOT VERIFIED

- The row's bar "replay of archived nights never exceeds any cap": CLOSED AT LIMIT in this clone
  (no data/, no receipt logs). Needs a laptop run on real paper_account logs.
- Real leg map, marks and game_meta for venue tickers (no mapping source exists; every real
  ticker is UNMAPPED until one is supplied, and enters the worst cell at 100 x W).
- Mark moves: a mark move can raise a worst cell with no order; that is S668 (breakers), not here.
- Sport / hour buckets trust the caller's game_meta: omitting or relabelling meta puts a game in
  a fresh bucket; only the slate cap cannot be dodged that way (adversarial probe P4).
- Per-family cap: SUPERSEDED by AMENDMENT 3 (2026-10-02); family is supplied in game_meta.
- Top-up of an open order_id is an enumerated case only (the ledger refuses order_id reuse, so the
  property generator cannot produce it).
- "One commit per table amendment" is a process rule, not testable here.
- Wiring and Windows re-run: no runtime caller; the laptop lander should re-run all three candidate
  test files (`test_risk_delta.py`, `test_risk_limits.py`, `test_risk_limits_family.py`)
  on Windows and land S666 first, from the commit sha (not a working tree).

PORTABLE: yes (pure Python; construct tests run on Ubuntu with Python 3.11).
