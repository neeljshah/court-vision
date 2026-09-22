# S368 structural coherence scanner -- PREPARE

Vocabulary follows contract Q6; automated scan required.

Result: fixture construction complete; real archive NOT RUN. Local CPU only,
in C:/Users/neelj/nba-harness-h26. The pod is OFF. No network or data/ access
was performed. No pre-existing module was edited.

## Binding before-condition

Command: `ls scripts/platformkit/execution/coherence_scanner.py`

Exit code: 1. Output:

```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h26\scripts\platformkit\execution\coherence_scanner.py' because it
does not exist.
```

Read S368_spec.md first, then VERIFIER_CONTRACT.md sections B and Q, then
ASTRA_ROUND12_2026-09-21.md, including section 4 and section 6 row 9.
Read the landed coherence_audit and venue_fees modules before implementation.

## Build and reuse

- `scripts/platformkit/execution/coherence_scanner.py`: pure scan API and CLI.
- `scripts/platformkit/execution/coherence_scanner_inputs.py`: row-owned helper
  split for the 300-line cap; input validation, definitions, fee bounds and loader.
- `tests/platformkit/execution/test_coherence_scanner.py`: synthetic constructs.
- This memo.

The scanner imports coherence_audit._size_bucket for the existing set-size
classification. Its heuristic event grouping, alignment, float metrics and
silent-skip loader do not fit this contract and are not reused or copied.
The row-owned batch_fee_decimal adapter sources the canonical venue_fees
schedule coefficients and performs Decimal-only arithmetic. Kalshi applies
ROUND_CEILING once to the batch cent before dividing by the Decimal quantity.
Polymarket uses the canonical maker/taker rates without a cent ceiling.
L uses the bid fee; U uses the ask fee. Fees and bounds are in unit payout per
contract. The shared fee functions remain unchanged and are no longer called
by the scanner. A per-series applicability attestation is required.
The finisher output records the canonical fee module SHA-256.

Venue timestamps use only execution.venue_time.parse_venue_time for grammar
and timezone validation. Whole seconds are parsed separately and the raw
fraction is added as Decimal, retaining all nine supported digits. The scanner
uses the landed capture's tick_start_ts as the shared capture instant and
response_end_ts for each receipt. It refuses skew greater than 5 seconds,
including across pages of the same bulk retrieval. Missing receipts also
produce sync_failure. No nearest-neighbor or forward/backward quote reuse occurs.

Complete sets require explicit, mutually exclusive and exhaustive winner
membership, including the draw where applicable. No spread or total ladder is
accepted as a complete set. Both sides of sum(L) <= 1 <= sum(U) are checked.
Nested over totals compare the higher threshold's L to the lower threshold's U.
A strictly positive margin_above spread compares its L to its team's winner U.
Settlement identifiers must match and have explicit verification attestations;
unknown rules, incompatible units and missing attestations are not_comparable.
Missing comparison members produce incomplete_set, never a partial sum.

A residual is not an opportunity. Related contracts of one game are not
independent families. Outputs are MARKET-STRUCTURE MEASUREMENTS. Persistence
counts consecutive observed event capture instants; coherent or refused
comparisons reset it. Invalid capture times make that event's persistence
unresolved. Unreadable files or malformed JSON make all persistence unresolved.
Intervals with no captured row cannot be reconstructed as elapsed-time coverage.
Declared, observed, comparable and residual-bearing game counts are separate.
The incidence denominator includes every distinct game in the definitions,
including games with no captured rows. Multiple contracts never multiply games.
Every caught failure has a named counter. Rows, comparisons and refusals remain
accounted for; observations, source paths and counters have deterministic order.

## Explicit input contract

The CLI accepts --books JSONL paths/directories and --definitions a JSON list.
The latter is a reviewed semantic manifest, not inferred from ticker spelling.
Each event object requires event_id, game_id and a contracts object keyed by
ticker. Each contract requires:

- venue, event_ticker and series, matching the captured row exactly;
- kind: winner, total or spread; subject identifies the team or total statistic;
- winner outcome; total direction over and string threshold; spread direction
  margin_above and string positive threshold;
- settlement_rule (an explicit identifier encompassing period, ties, pushes and
  void rules), settlement_verified: true, payout_unit: unit_payout;
- string tick_size, string quantity, fee_mode maker/taker;
- fee_schedule: venue_fees:2026-09-01:standard and fee_schedule_verified: true,
  attesting applicability to this series and quantity under that dated schedule.

Each complete_sets entry requires set_id, members (ticker list),
mutually_exclusive: true and exhaustive: true. All expected outcomes must be
enumerated by the reviewer. Missing members in the capture are refused.
String quantities and prices are parsed directly as Decimal. The JSONL loader
also parses fixed-point numeric tokens directly as Decimal, preserving the
landed writer's format. Missing, nonfinite, crossed or off-grid prices and
nonpositive quantities are refused. JSON report Decimal values are strings.

The tracked test's event() and rows() constructs are the executable schema
example. Its raw-capture test imports the landed bulk_row and encode_json,
round-trips generated rows through temporary JSONL, and invokes the CLI. No
test imports a gitignored fixture. Input archive paths and byte sizes are
included in finisher output; definitions additionally carry a content hash.
The reviewed manifest may explicitly join multiple venue event_ticker values
under one canonical event_id; the scanner never invents that linkage.

## Reproduction and finisher

Commands run locally:

```text
python -m pytest tests/platformkit/execution/test_coherence_scanner.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.coherence_scanner --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/coherence_scanner.py scripts/platformkit/execution/coherence_scanner_inputs.py tests/platformkit/execution/test_coherence_scanner.py docs/evidence/harness/S368_coherence_scanner_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S368_spec.md
```

The initial candidate recorded 50 fixture passes and 9 preflight passes.
The independent verifier rejected that candidate on three blocking findings;
its test run encountered 50 setup errors before any test body ran. FIX 1b below
supersedes the initial implementation assessment and records fresh validation.

Finisher command, NOT RUN in PREPARE:

```text
python -m scripts.platformkit.execution.coherence_scanner --books data/cache/ingame_books_local --definitions "PATH_TO_REVIEWED_EVENT_DEFINITIONS.json"
```

The uppercase path is an explicit future input placeholder, not an existing
evidence artifact. Before that command, the finisher must supply reviewed
settlement, completeness, tick-grid, canonical linkage and series-fee metadata.
The archive is not present in this worktree. This build asserts no measured
calibration, fill or markout result. B/Q self-check: new files only; no changed
reader schema, deployment, sampling, scored claim, tuned threshold or trial.
Construct reproduction applies; no OOS or multi-corpus result is asserted.

## FIX 1b

Read _verdict_s368_1b.md first. Checked the local spec and the master version;
neither contains an AMENDMENT block. Changes stay in this row's input module,
test file and memo. The scanner's comparison formulas and refusal thresholds
are unchanged. All inputs below are CONSTRUCT fixtures.

1. BLOCKING: fee/quantity arithmetic crossed the shared float boundary.
   Minimal reproduction: interval with price="0.5", quantity="0.5714285714285715",
   tick_size="0.0001", Kalshi taker mode. Before output:

   ```text
   batch_fee_exact=0.02
   fee_per_contract_output=0.01749999999999999781250000000
   fee_per_contract_exact=0.03499999999999999562500000000
   L_output=0.4824000000000000021875000000
   L_exact=0.4649000000000000043750000000
   ```

   Exact fix: Decimal-only schedule adapter, imported canonical coefficients,
   sufficient product precision before Kalshi batch-cent ROUND_CEILING.
   After: fee_per_contract_output=0.03499999999999999562500000000 and
   L_output=0.4649000000000000043750000000; both equality assertions PASS.
   Regression: test_cent_boundary_fee_and_lower_bound; four venue/mode cases.
   Existing fee-reuse tests now instrument the Decimal adapter and coefficient.

2. BLOCKING: the timestamp float round trip lost a strict-boundary remainder.
   Minimal reproduction: receipts at 12:00:00Z and 12:00:05.0000001Z on
   2026-09-21, with the later receipt assigned to away, high and cover.

   ```text
   BEFORE skew=5.0, statuses=['violation', 'violation', 'violation']
   AFTER skew=5.0000001, statuses=['sync_failure', 'sync_failure', 'sync_failure']
   ```

   Exact fix: shared-parser validation plus exact raw fractional seconds.
   Regressions exercise 5.0000001 and 5.000000001 seconds, exactly five seconds,
   offset timestamps, full nine-digit fractions, and a pre-epoch timestamp.

3. BLOCKING: missing semantic fields silently removed comparisons.
   Minimal reproduction: delete event()["contracts"]["high"]["subject"].

   ```text
   BEFORE comparisons=['complete_set', 'spread_winner']
   AFTER manifest_failures=1, ValueError: missing semantic field: high.subject
   ```

   Exact fix: validate kind, subject, winner outcome, total/spread direction
   and finite threshold before enumeration; fail the manifest explicitly.
   Regression: 40 missing/null/blank-field cases plus CLI input_failure with
   errors={"ValueError": 1}. A missing semantic field cannot erase a comparison.

Validation ran locally with TEMP and TMP set to this worktree and
PYTHONDONTWRITEBYTECODE=1, avoiding the verifier's temporary-directory failure.
The command above runs the single test file covering both row modules.
Before implementation changes: 41 failed, 52 passed. After fixes: 93 passed.
Added venue/time variants initially returned 2 failed, 101 passed due to a
mistyped expected epoch; independent calendar arithmetic confirmed 1789992000
whole seconds, and the fixture expectation was corrected.
Final per-file result: 103 passed. All three original minimal reproductions
passed explicit assertions. CLI --help: exit 0; no separate self-check CLI exists.
Contract preflight: 9 PASS, 0 FAIL over the four candidate files only, excluding
the verifier verdict. All four files are ASCII and each is below 300 lines.
Generated pytest-of-neelj/ fixtures remain untracked: sandbox policy rejected
their cleanup with "blocked by policy". They are excluded from lane_commit.

## NOT VERIFIED

- Any real archive run, receipt coverage or real structural residual.
- Independent verification of the future manifest's settlement definitions,
  draw membership, completeness, game linkage, tick grids or series-fee scope.
- Real venue fractional-fee certification; the shared fee module is unchanged.
- Continuous coverage between observed instants or across absent capture ticks.
- Calibration, fills, markouts, independent families or production integration.
- Pod execution, deployment, lane_commit or a commit SHA.
- FWER ledger execution or a corpus evaluation.
