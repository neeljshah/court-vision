# S693 cloud result -- 2026-09-30

Row: S693, the venue-semantics paper execution model. The one-off override in
AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 3a pinned this row, and the row text is in
that file's section 2. Branch: `cloud/S693-2026-09-30`, cut from trunk bb34a09c. Commits:
- 7e83cc03: spec + AMENDMENT 1
- 9d03075a: build
- f0e2e8e3: contract-tier corrections
- f69063eb: adversarial-tier corrections
- 3058843a: this memo
- (next commit): re-verify corrections + memo update

Machine: cloud clone, Ubuntu, Python 3.11.15. Fixtures only: there is no data/ directory, and no
venue or sports host was contacted. PAPER ONLY. This memo uses execution-quality language only
(fill counts, filled contracts, queue position, reason counts). There are no fees, no valuation
and no scored comparison.

## Status: BUILT, VERIFIED (ACCEPT WITH CORRECTIONS on both tiers, corrections applied). Not landed.

The register and DESK_STATE.md were not edited on this branch (run rules b and 7).

Reviewers: codex is not available here. The pre-build critic and each verifier tier were
**separate, independent Opus sub-agents**. None of them built the code, and each read the
repository cold. A fourth independent Opus sub-agent re-checked the correction delta once; its
verdict is in the "Re-verify" section below. (A first re-verify run was lost to a container restart; it was re-run from scratch.)

## Premise (Q8): CONFIRMED on trunk bb34a09c

- fill_realism.py:267 declares submit and cancel latency of 0 s.
- exec_cancel_policy.py:22 declares 6.0 s, the sealed S551 value.
- tape_fill_sim.py:220-235 lowers queue_ahead only on prints.
- A grep of scripts/platformkit/execution/ for post_only, expiration or self_trade finds 0 hits.
- S671 is not landed; it exists only as the cloud branch cloud/S671-2026-09-30. Per the
  override, the minimal rule functions are therefore built inside the new package
  (`venue_rules.py`).
- **If S671 lands before this branch merges, reconcile venue_rules.RULES with the rule ids and
  URLs in fill_model_venue_rules.RULES before the merge** (spec A1-21).

## Change: new files only (`git diff --name-status trunk..HEAD` is all A)

`scripts/platformkit/execution/core/` is a standalone pure package that S691 can call:

- `paper_exec_model.py` (300 LOC)
  - `PaperExecModel` exposes submit, amend, cancel, on_book, on_print, flush, header and receipt,
    and `run()` handles a batch.
  - The input contract is in the module docstring: book snapshot, resting order, amend, cancel,
    tape print, and latency parameters.
  - Inputs must arrive in venue-time order. At equal venue_us, actions apply first, then prints,
    then books. A streaming caller buffers up to a watermark, and that buffering is S691's job.
- `queue_model.py` (68 LOC)
  - The print-netted level table and the two queue models.
  - risk_averse: queue ahead falls only on prints.
  - shrink: queue ahead also scales by a displayed-size drop that prints do not explain (rounded
    up to whole contracts), then is capped at the displayed size. Cancels ahead therefore shrink
    the queue.
- `venue_rules.py` (87 LOC)
  - 8 RULES rows: post_only_cross, cross_is_taker, self_trade_prevention, amend_priority,
    expiry_only_amend_keeps_place, decrease_order, expiration_time, venue_delay.
  - Each row cites a docs.kalshi.com api-reference URL (create-order, amend-order or
    decrease-order), taken from the S671 research.
  - **Every row is UNVERIFIED and acts as a declared modelling parameter.** The docs host is
    blocked, and no tracked quote of the rule text exists.
- `latency.py` (95 LOC) and `latency_declared.json` (sha256 in the grid header). There are four
  SEPARATE declared integer parameters:
  - market_feed_latency_us: UNMEASURED, declared 0. It shifts receipt-only book and print stamps
    and dates the desk's view of the book.
  - state_feed_latency_us: taken from the S550 STATE-feed source-to-receipt lag, p10 12.934 /
    p50 21.228 / p90 33.311 s (S550_exec_quality_audit_2026-09-29.md:32). It never shifts book or
    print stamps.
  - order_latency_us: UNMEASURED. The declared points are 0 (the fill_realism assumption) and
    6.0 s (the sealed S551 assumption).
  - venue_delay_us: UNVERIFIED. The declared points are 0, 3 and 6 s.
  - All four are declared from their cited sources and never fitted to an outcome.
- `fixture_night.py` (128 LOC): a synthetic seeded night plus the grid runner.

tape_fill_sim.py, fill_realism.py, exec_cancel_policy.py, exec_policy_replay.py, PREREG_S551.json,
every seal-pinned file and everything under src/ kernel/ api/ intel/ scripts/team_system/ data/
vault/ are unchanged. The diff contains new files only, and the core imports none of these
modules; a test guards the imports.

Deviations, each stated:
1. **Queue at arrival.** The queue at live, and after a BACK amend, is the latest applied book less
   the prints at that level since that book. tape_fill_sim instead reads the book at submit, with
   no print netting. A level absent from an applied book counts as 0 (full depth assumed, which is
   UNVERIFIED); tape_fill_sim treats an absent level as unknown.
2. **Grid location.** The grid JSON lives at `docs/evidence/S693_fixture_grid_2026-09-30.json`,
   not under harness/. The harness/*.json path is gitignored (.gitignore:588) and this run forbids
   force flags.
3. **Taker fills are out of scope.** A non-post-only order that would cross is REJECTED as
   cross_taker_out_of_scope, the same choice S671 made.
4. **Print exactly at live.** It depletes that order's queue ahead but never fills it; the fill
   window stays strictly live < print. This came from contract finding 13.

## Acceptance (spec + AMENDMENT 1): every case passes, 0 violations

- **Enumerated cases:** 17 test functions carrying about 32 tagged case ids (CONSTRUCT). Some
  checks are untagged: the header, the fractional shrink, feed-moves-book and the terminal no-ops.
  UNCHANGED_FILES is proven by git diff, not by a test. On top of these come 3 x 200
  single-order monotone cases, each run at 6 order latencies x 3 venue delays. An earlier draft
  said "36 named case ids"; the re-verify counted about 32, and this corrected count replaces it.
- **(a) Amend priority**, all with exact values:
  - AMEND_KEEP: ahead stays at 5 while the level grows to 9.
  - AMEND_BACK_PRICE resets ahead to 4, and AMEND_BACK_UP resets it to 9.
  - AMEND_EXPIRY_KEEP keeps the queue place.
  - AMEND_TO_FILLED ends in CANCELLED.
  - AMEND_CROSS_REJ: the amend is rejected and the order is unchanged.
  - BACK_PRIORITY: no fill at the effect time, and no second venue delay.
- **(b) Post-only.**
  - POSTONLY_REJ and TAKER_REJ: REJECTED, counted, 0 fills. Tested at the exact 55 + 45 = 100
    boundary.
  - STALE_VIEW: a cross that was absent from the desk's view is counted separately.
- **(c) Self-trade prevention.**
  - STP_TAKER rejects the incoming order; STP_MAKER cancels our resting order. Both are counted
    and both give 0 fills after the check.
  - Every fill comes from a tape print.
- **(d) Expiry.**
  - EXPIRE_NOFILL: no fill at or after expiration_us.
  - EXPIRE_BEFORE_LIVE: the order never rests.
  - CANCEL_IN_DELAY: the cancel takes effect at live, giving 0 fills.
- **(e) Monotonicity.** Filled contracts are non-increasing in both order latency and venue delay:
  - shrink: 200 cases on tapes with cancels, plus 200 on tapes whose levels drop only through
    prints.
  - risk_averse: 200 cases on tapes whose levels drop only through prints, with a book before
    the earliest arrival.
  - The named exclusions E_CANCEL, E_CROSS, E_RA_DROP and E_RA_NOBOOK each show the excluded
    behaviour. For example, under E_RA_DROP risk_averse gives [0, 3] where shrink gives [3, 3].
- **(f) HEADER.** Every key listed in A1-15 is present and equal to the run value.
- **(g) GRID_DELAYS.** The grid below.
- **(h) SHRINK_VS_RA.** shrink gives 4, 5 and a fractional ceil of 3; risk_averse gives 10.
- **(i) LAT_SPLIT.** Market feed alone moves converted stamps and the chosen book while live stays
  unchanged. Order latency alone moves live while stamps stay unchanged.
- **Other cases:** PARTIAL (2 / 3 / 5, then FILLED), TIE_AT_LIVE, TIE_RANK, PARTIAL_CANCEL,
  THROUGH_KEEPS_QUEUE, SHARED_PRINT, VENUE_WINS, terminal no-ops, and DETERMINISM (the grid JSON
  is byte-identical on rerun).
- **UNCHANGED_FILES** is proven by `git diff --name-status trunk..HEAD`, which shows new files
  only. The contract tier accepted this proof. The adversarial tier asked for a sha pin inside the
  test, and I declined: a sealed-file hash in a unit test would break at a legitimate re-seal.

### Grid on the synthetic fixture night (descriptive counts, not a bar)

The tape has 480 books, 512 prints, 88 orders, 20 cancels and 40 amends; STP mode is
taker_at_cross; grid sha256 e2dac94d...8ab4. The night includes cancels, amends and crosses,
which are all excluded from (e), so the cells need not be monotone.

| cell | filled contracts | fills | FILLED orders | post-only rejects | STP rejects | EXPIRED | shrink events |
|---|---|---|---|---|---|---|---|
| risk_averse, order 0 s, delay 0 s | 584 | 97 | 56 | 16 | 1 | 8 | 0 |
| risk_averse, order 0 s, delay 3 s | 543 | 93 | 52 | 15 | 1 | 11 | 0 |
| risk_averse, order 0 s, delay 6 s | 509 | 91 | 51 | 15 | 1 | 12 | 0 |
| risk_averse, order 6 s, delay 0 s | 575 | 100 | 54 | 15 | 1 | 12 | 0 |
| risk_averse, order 6 s, delay 3 s | 547 | 98 | 54 | 15 | 0 | 10 | 0 |
| risk_averse, order 6 s, delay 6 s | 517 | 89 | 54 | 15 | 0 | 11 | 0 |
| shrink, order 0 s, delay 0 s | 584 | 97 | 56 | 16 | 1 | 8 | 26 |
| shrink, order 0 s, delay 3 s | 550 | 94 | 52 | 15 | 1 | 11 | 42 |
| shrink, order 0 s, delay 6 s | 516 | 95 | 51 | 15 | 1 | 12 | 51 |
| shrink, order 6 s, delay 0 s | 585 | 103 | 56 | 15 | 1 | 10 | 49 |
| shrink, order 6 s, delay 3 s | 554 | 100 | 54 | 15 | 0 | 10 | 38 |
| shrink, order 6 s, delay 6 s | 524 | 92 | 54 | 15 | 0 | 11 | 43 |

## Verdicts

- **Pre-build critic** (independent Opus sub-agent): REVISE with 21 items. All 21 were folded
  into the spec as AMENDMENT 1 before the build.
- **CONTRACT tier** (independent Opus sub-agent, on 9d03075a): ACCEPT WITH CORRECTIONS.
  - A7: the result memo was missing. This memo fixes that.
  - Printed case count: fixed.
  - Fractional shrink ceil: now pinned by a test.
  - Market feed moving the chosen book: now asserted.
  - model_version: now asserted in the header test.
  - Finding 13, a print at live left the queue undepleted: fixed in code, with a test.
  - Its NEW GAP on terminal no-ops: covered by a test.
- **ADVERSARIAL tier** (independent Opus sub-agent, on 9d03075a and re-run on f0e2e8e3):
  ACCEPT WITH CORRECTIONS.
  - Mutants: 49 in total. 38 were killed by a named case test, 11 only by the committed grid JSON,
    and 7 survived.
  - Probes found 0 violations: 1,200 general fuzz runs, 2,000 expiry runs and 1,876 monotone
    cases (7 order latencies x 4 venue delays each). grid() was byte-identical under three hash
    seeds.
  - After f69063eb I re-ran every mutant that had survived or had been killed only by the grid
    JSON. With the grid test deselected, all 17 are now killed by a named test.
  - M19 (amend expiry <= vs <) is near-equivalent and remains.
  - Its correction on the grid-header latency source is fixed.
- **Re-verify** (independent Opus sub-agent, correction delta on 3058843a): ACCEPT WITH
  CORRECTIONS, nothing blocking.
  - C1 (a print at live depletes the queue without filling) is correct.
  - A fuzz with prints exactly at every live instant ran 720 cases with 0 monotonicity
    violations; every fill had venue_us > live_us.
  - All new case values were recomputed by hand and match. The grid is byte-identical. C5
    constraints hold. It accepted the decision not to byte-pin must-not-move files.
  - Mutants: all 18 requested were killed by a named test, and 7 of its own 9 were killed. Two
    remained: the live_us time-priority tie-break was untested (survived everything), and the
    not-in-view counter could be counted even when the cross was in view (killed only by the grid
    JSON).
  - Both got a named assertion in the final commit, and both mutants are now killed by named
    tests (builder re-run, grid test deselected).
  - The memo was corrected for the missing section and the case count.
  - Per the one-re-verify limit, no further tier was run.

## Test commands (one file per process, repo root)

- `python3 tools/desk_bin/run_files.py . tests/platformkit/execution/test_s693_paper_exec_model.py`:
  17 passed.
- `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py`: 1 passed.
- `python3 -m scripts.platformkit.execution.core.fixture_night`: reproduces the committed grid JSON
  byte for byte.
- On trunk bb34a09c the new test file fails at collection, because the module is absent. The
  construct test therefore fails on the old code.

## NOT VERIFIED

- Measured order latency and market-feed latency (S663). The declared points stand in for them.
- Rule text against the Kalshi documentation: all 8 rules are UNVERIFIED because the host is
  blocked.
- Whether the capture books are full depth, which the level-absent-means-0 rule assumes.
- Held-out or recorded nights. The only night run here is synthetic; the archive lives on the
  laptop.
- A Windows re-test.
- S691 wiring: the watermark buffering for a receipt-ordered stream is not built.
- Reconciliation with S671 if that branch lands.
- Any use in a scored series. That would need a PROPOSED prereg sealed alone, and this model is
  never a sealed arm.

NEW GAP (from the tiers): byte-pin option for must-not-move files (declined here, reason above);
S671 RULES reconciliation; watermark adapter for streaming callers (S691).

PORTABLE: yes.
