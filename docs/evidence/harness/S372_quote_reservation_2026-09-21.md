# S372: atomic snapshot-to-quote reservations

Implemented locally in C:/Users/neelj/nba-harness-h30 on 2026-09-21.
Machine: local Windows CPU; deterministic CONSTRUCT tests require no accelerator.
The pod is OFF. No archive, network, venue submission, or scoring was used.
Vocabulary follows contract Q6; automated scan required.

Authority: docs/evidence/tracking/specs/S372_spec.md;
docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md, finding 2;
docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.
S343, S344, S345, S354, S356 and S357 specs and their amendments remain binding.
Only the two NEW owned Python files and this explicitly required memo are added.
The spec says "No landed module is edited"; no existing module was changed.

## Exact audit finding

> 2. **BLOCKING ? quote rooms are not derived from or reserved in the cap engine.** [quote_engine.py:147](/C:/Users/neelj/nba-ai-system/scripts/platformkit/execution/quote_engine.py:147), [position_caps.py:27](/C:/Users/neelj/nba-ai-system/scripts/platformkit/execution/position_caps.py:27). Repro: with an open resting YES 8 and global cap 10, `check_caps(... YES 3)` returned `permitted=False`; manually supplied rooms let `make_quotes` emit bid qty `"3"`. **Fix:** add one atomic snapshot-to-side-room/reservation boundary; quote submission must consume a reservation produced by `check_caps`, not caller-authored room dictionaries.

The quoted paths are the audit's identifiers, not write destinations.
Finding 2 is the only audit defect assigned to S372; findings 1 and 3-8 belong
to other rows. They were not changed or claimed resolved here.

## Before and after, reproduced

Before any implementation, an inline Python construct built one submit event:
order old, ticker T, game G, side yes, qty "8", price_cents 49.
It folded that event with positions and called check_caps with global "10",
new order, side yes, qty "3". The quote input used max_order_qty "3",
max_position "100", and all three caller-authored bid/ask room maps "100".
Book 49/51 and matching aware timestamps were fresh; the state-change window
was clear. The assertion required either a permitted order or an absent bid.
Actual failing output (exit 1):

```text
CONSTRUCT audit finding 2: permitted=False bid_cents=48 qty='3'
AssertionError: FAIL: caller-authored rooms bypass resting-order cap
```

The permanent test test_audit_finding_two_fixed retains that legacy contrast,
then uses the owned snapshot, reservation and wrapper. Actual passing output:

```text
CONSTRUCT audit finding 2 fixed: bid_room='2' qty='2' submitted=True
```

Reproduce both assertions and that output without selecting an archive:

```python
import runpy
tests = runpy.run_path('tests/platformkit/execution/test_quote_reservation.py')
tests['test_audit_finding_two_fixed']()
```

## Boundary and limitations of the implementation

ReservationLedger owns one ordered harness event log. All fills and other
events enter through record; all quote submissions enter through submit.
Both share the same RLock. snapshot returns immutable serialized positions,
a revision and their canonical digest. Detached position dictionaries are
refused because they cannot identify the current owner. Mapping insertion
order and permutations of independent orders do not change rooms or digests;
chronological lifecycle event order remains meaningful, as in S345 replay.

reserve takes that snapshot, cap configuration, ticker and game_id. A bounded
integer search calls check_caps for each candidate side. It returns the
largest permitted whole quantity, never negative; the cap engine accounts
for resting and uncertain-cancel orders. All applicable per-order, per-game,
correlated and global limits constrain it. No finite applicable limit means
refusal, not invented capacity. Missing fields are not replaced by zero;
an absent ticker in a complete owned ledger is known to have no filled inventory.

Quantities and cap arithmetic use Decimal from strings or exact integers,
never float quantities. Shared parse_venue_time handles clocks; wrapper book
times are normalized to aware ISO strings before the legacy quote call.
Nonfinite inputs are refused. Exceptions propagate, except the test's counted
concurrent loser. No existing reason codes or public signatures were changed.

Each token carries its reservation ID, digest, immutable side rooms and expiry.
Generated order IDs contain the UTC day and a random nonce. Explicit fresh
bid/ask IDs support the cap engine's keyed per_order configuration. The default
30-second TTL is an ASSUMPTION, configurable on the ledger, not an observation.

make_quotes_reserved is the single harness entry point. It rejects room maps
in caller quote parameters and supplies rooms and inventory from the token.
It records the exact returned quote; submission cannot reactivate a pulled
side, alter price, substitute identity, or change size. Re-preparing a token
replaces its previously issued quote. Prepare alone does not send or fill it.

submit checks issuance, identity, quantity, expiry and current snapshot while
holding the owner lock. It validates both sides as one resting batch and
commits both events together. YES asks become complementary NO bids. It
checks expiry again immediately before commit. A fill or successful sibling
submission invalidates prior tokens. A replayed token cannot spend room again.
Existing breaches do not block genuine reductions: batch exposure may stay
at the prior worst case, but cannot worsen beyond both that case and the cap.
The concurrent construct gives exactly one success from two competing tokens.

This is one in-process harness authority with no file or venue writes. It is
not a lock around position_ledger.append_event or an external mutable ledger.
A harness must route every event for a portfolio through this owner; independent
owners do not coordinate. Restart requires event replay and fresh reservations.

## Caller census

Calling make_quotes directly with hand-written rooms is a contract violation
for harness execution. The legacy API remains callable under S372 ownership
and B2; existing construct-only tests and its self-check deliberately exercise it.
Recursive Python-source search found no production caller or aliased import.
Excluded trees: data, vault, .git, node_modules, environments and Python caches.
Before-change references, with every call site:

- scripts/platformkit/execution/quote_engine.py:192,195: construct _demo.
- tests/platformkit/execution/test_quote_engine.py:31,190,193: tests; line 31
  is the quote helper used by the remaining cases; import at line 9.
- tests/platformkit/execution/test_fractional_chain.py:86,188,198,200,203,237,241:
  construct/public-fixture tests; import at line 12.

- scripts/platformkit/execution/quote_reservation.py:216: new wrapper.
- tests/platformkit/execution/test_quote_reservation.py:57: deliberate legacy reproduction.

## Validation

Every command used one file: python -m pytest <path> -q -p no:cacheprovider.
Actual final output counts:

| Test file under tests/platformkit/execution/ | Passing output |
| --- | --- |
| test_quote_reservation.py | 45 passed |
| test_quote_engine.py | 38 passed |
| test_position_caps.py | 42 passed |
| test_position_reducers.py | 40 passed |
| test_position_ledger.py | 83 passed |
| test_fractional_chain.py | 26 passed |
| test_venue_time.py | 65 passed |

Total: 339 passed across seven separate per-file runs. No whole-suite run.
The new file includes a fully enumerated 30-state cap comparison, both sides
checked against permitted integer quantities; concurrency, fractional fill,
expiry-at-commit, tampering, every cap scope and malformed-input regressions.

The first test run returned "1 failed, 42 passed": its resting-NO-20 fixture
incorrectly expected an unchanged worst case to fail. With held YES 20, existing
NO 30 and new NO 20, the corrected fixture increases worst-case exposure from
20 to 30 and is refused. Static review also found the need to bind prepared
quotes; the deadline-side mutation regression now verifies that refusal.

Contract B: additive files only, no schema removal, no claim queue, no deploy,
no removed readers, no sampling, fitting, scoring, or changed thresholds.
Contract Q: infrastructure constructs only; no scored claim or charged trial.
Automated preflight command:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/quote_reservation.py tests/platformkit/execution/test_quote_reservation.py docs/evidence/harness/S372_quote_reservation_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S372_spec.md
```

## Source identity

All primary inputs are text; resolution is not applicable. Constructs are fully
defined in the new test file. The existing fractional-chain test reads the
listed public fixture; no real archive was opened. Sizes are bytes on disk.

| Full local path | Bytes |
| --- | --- |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S372_spec.md | 2642 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S343_spec.md | 2496 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S344_spec.md | 7876 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S345_spec.md | 7574 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S354_spec.md | 3366 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S356_spec.md | 3860 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/specs/S357_spec.md | 4433 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md | 6704 |
| C:/Users/neelj/nba-harness-h30/docs/evidence/tracking/VERIFIER_CONTRACT.md | 12532 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/quote_reservation.py | 12374 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/quote_engine.py | 9744 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/position_caps.py | 6938 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/position_exposure.py | 1401 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/position_decimal.py | 2371 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/position_ledger.py | 10317 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/position_reducers.py | 10644 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/venue_time.py | 2029 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/venue_fees.py | 8935 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/replay_units.py | 3420 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/paper_maker.py | 13261 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/markout_causal.py | 15519 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/markout_causal_windows.py | 7524 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/tape_fill_sim.py | 9965 |
| C:/Users/neelj/nba-harness-h30/scripts/platformkit/execution/executor/lifecycle.py | 13312 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_quote_reservation.py | 11822 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_quote_engine.py | 8219 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_position_caps.py | 9380 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_position_reducers.py | 13480 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_position_ledger.py | 11481 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_fractional_chain.py | 11428 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/test_venue_time.py | 2889 |
| C:/Users/neelj/nba-harness-h30/tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl | 5184 |

File checks: quote_reservation.py 270 lines; test_quote_reservation.py 282 lines.
Both Python files are ASCII. The memo is also ASCII and below 300 lines.

Actual automated preflight output (exit 0):

```text
PASS vocab clean over 3 files
PASS crlf no index-side CRLF over 3 file(s); 3 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold no THRESHOLD/BAR/ACCEPTANCE RULE lines in spec
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

## NOT VERIFIED

- Integration into any production harness; existing callers remain unchanged.
- Coordination with independently mutated file ledgers or multiple processes.
- Durable reservation persistence or recovery without event replay.
- Live archive completeness, venue execution, queue ordering or cancellations.
- Fixes for the audit's other findings; no module assigned to another row changed.
- Any observed market result, pod behavior, or cross-version execution.
- Commit creation and master-tree verification by lane_commit.
