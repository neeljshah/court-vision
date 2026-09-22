# S362 qualification harness - 2026-09-21
Status: PREPARE ONLY; frozen qualification implemented; local fixture/construct validation only.
Amendment 1 supersedes the original scoring mode. No scoring entry point exists.
## Binding before-condition (before coding)
Command: `ls scripts/platformkit/execution/forward_replay.py`
Exit code: 1. Output:
```text
ls : Cannot find path 'C:\Users\neelj\nba-harness-h39\scripts\platformkit\execution\forward_replay.py' because it does
not exist.
At line:2 char:1
+ ls scripts/platformkit/execution/forward_replay.py
+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : ObjectNotFound: (C:\Users\neelj\...rward_replay.py:String) [Get-ChildItem], ItemNotFound
   Exception
    + FullyQualifiedErrorId : PathNotFound,Microsoft.PowerShell.Commands.GetChildItemCommand
```
## Landed interfaces read before coding
The landed execution interfaces read and used are venue_time.parse_venue_time;
capture_book_adapter.to_quote_book, to_fill_snapshot and to_mark_tick;
quote_reservation.ReservationLedger, reserve, make_quotes_reserved and submit;
quote_engine.make_quotes; tape_fill_sim.simulate_fills; tape_fill_adapters.from_s341_trade;
replay_units.fill_to_ledger_event and fill_to_markout_fill; and
fee_time_certification.clock_skew_report. Qualification retains only clock counts.
Construct causal inputs use the markout_causal.resolve_marks input contract.
Master position_ledger API inspected for authoritative recorded order ids:
```python
def read_events(path: Path) -> List[Dict[str, Any]]:
def append_event(path: Path, event: Dict[str, Any]) -> bool:
def new_event(event: str, *, order_id: str, ticker: str, side: str,
              game_id: str, idempotency_key: str, qty: int | str, ...) -> Dict[str, Any]:
```
The quote engine currently converts fees through floats. Its fees are not consumed
by this row. The simulator also returns float fees; constructs never trust those
as certified Decimal fees. Qualification does not simulate executions or evaluate
causal marks. Adapter outputs and reserved quote events remain available in memory
for the construct seam test, outside the counts-only report.
R1 inspection: `scripts/platformkit/ingame/s359_four_arm_trial.py` is absent.
The actual helper is `scripts/platformkit/eval_gate/backtest_runner.py`:
```python
def canonical_ledger_path() -> Path:
    return _repo_root().joinpath(*CANONICAL_LEDGER_PARTS)
def assert_canonical_ledger(ledger_path: Path, allow_noncanonical: bool) -> bool:
def _charge_ledger(path: Path, spec: str, sport: str, start: str, end: str, *,
                   family: str | None = None, hypothesis_hash: str | None = None,
                   tier: str | None = None, prereg_sha256: str | None = None,
                   trial_prereg_sha256: str | None = None) -> dict:
```
Its path comparison is `Path(ledger_path).expanduser().resolve() == canonical.resolve()`.
Qualification never accepts a charge-ledger path and never charges a trial.
The named four-arm runner and its guard cannot be quoted because they are absent.
The available `ingame/baseline_four_arm.py:36` instead exposes:
```python
def validate_inputs(corpus_dir: Path, manifest: Path, prereg: Path | None,
                    *, census_only: bool = False, loaded: tuple | None = None) -> dict:
```
That guard checks sealed, committed prereg bytes; it has no canonical-path guard.
No substitute scoring runner was introduced.
Historical rebuild: the worktree spec had no numeric qualification bar. FIX 1b
below supersedes that limitation using Amendment 2 read directly from master.
The mandatory S365 interface was read before implementation:
```python
class FamilyWeekLedger:
    def __init__(self, path: Path, families_path: Path, *, as_of: str | None = None):
    def records(self) -> list[dict]:
    def append(self, row: dict) -> None:
    def streak(self, family: str) -> int:
```
It requires family declarations and completed-week evidence, including distinct
qualified game sets. FIX 1c delegates through temporary counts-only records under
the frozen four-game floor; no production weekly ledger is written.
S364 integration retains only `clock_skew_report(...)["counts"]`; its duration
summaries and fee fixture values never enter the qualification report.
## Implementation and construct coverage
- R1: only `--qualify` exists. Caller ledger-path/configuration overrides are
  rejected. S372 owns reservations; the fixed S362 position journal persists
  declarations through the landed API, separate from the charged-trial ledger.
- R2: prices, displayed queues and causal tick inputs go through all three S373
  adapters. Refusals retain their reasons. The adapter alone interprets raw
  levels. Every valid converted snapshot supplies downstream inputs,
  even when reservation capacity blocks another quote.
- R3: S372 issues room from its owned snapshot digest; only its `submit` records
  resting orders. Tests invalidate real tokens by changing the owner revision or
  clock. Both paths abstain and count the reason. No room override is accepted.
- R4: identifiers contain UTC day, explicit run nonce and increasing counter.
  Reusing a nonce recorded in the authoritative target journal raises before processing.
  A new nonce gives disjoint identifiers with the same qualification counts.
- R5: as-of filtering precedes schema checks and duplicate decisions. Receipt
  ties process gaps and state before books. State recovery selects maximum visible
  receipt, independent of row order. Nanoseconds are retained for ordering; input
  precision unsupported by the landed downstream modules is refused and counted.
- R6: game and ticker counts include snapshot conversion/refusal, reservations,
  quote opportunities, print coverage, raw touch availability, fixed cadence and
  state-receipt-age buckets, clock diagnostics and overlapping quote windows.
  Every numeric leaf is a strict integer count or millisecond duration. No evaluator runs.
- Expiry timers advance at every receipt and the final as-of time. Cancellation
  retains occupied room until its latency ends. Freshness and closing deadlines
  limit the lifetime. An uninterpretable gap blocks later opportunities for that
  ticker. Later-received gap records flag overlapping prepared quote windows.
Declared design assumptions, not fitted values: `forward_replay_policy.py` defaults
to one contract, one-second submit/cancel delays, three-second quote expiry and a
two-second reservation TTL. Unit uncertainty/inventory multipliers and a ten-second
flatten deadline remain explicit. The observed midpoint is the anchor, with zero
anchor uncertainty by default. The state-change pull window is two seconds. These
policy assumptions do not replace the frozen qualification thresholds below.
`forward_replay_io.py` uses descriptive upper buckets of one, five, ten, thirty and
120 seconds. Configuration magnitudes outside the declared numeric domain refuse;
positive timing inputs below one millisecond or above one day also refuse.
The first test reads these tracked fixtures and adds an explicitly transformed
trade construct in memory (JSONL; media resolution not applicable):
- `C:/Users/neelj/nba-harness-h39/tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl`: 30974 bytes, six rows.
- `C:/Users/neelj/nba-harness-h39/tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl`: 5184 bytes, eight rows.
The first fixture chain uses one selected fixture ticker and a constructed live
state. Its additional real-fixture trade copy moves venue/receipt time to two
seconds after book availability and moves complementary prices through the ask.
The source trade quantity and identity linkage remain intact; its id is unique.
This produces tape-supported construct fills, persisted ledger fill events and
Decimal causal inputs. Original fixture rows remain unchanged on disk. The
explicit Decimal fee is a construct input, not simulator fee certification.
No numerical mark evaluator runs.
Readers stream lines; chronological merging buffers the visible set because shards
may be unsorted. Exact duplicate snapshots collapse; conflicting snapshots at one receipt are refused. Duplicate
trade identities anywhere in the visible set are all refused. A future record
cannot create a visible duplicate. State rows need an explicit captured game
identity; provider-only identifiers remain unmatched, never guessed.
## Reproduction and handoff

Local only; no network, archive, pod or measured comparison was used.

```text
python -m pytest tests/platformkit/execution/test_forward_replay.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_forward_replay_qualification.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.forward_replay --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/execution/forward_replay.py scripts/platformkit/execution/forward_replay_io.py scripts/platformkit/execution/forward_replay_policy.py scripts/platformkit/execution/forward_replay_qualification.py tests/platformkit/execution/test_forward_replay.py tests/platformkit/execution/test_forward_replay_qualification.py docs/evidence/harness/S362_forward_replay_harness_2026-09-21.md --base master --spec docs/evidence/tracking/specs/S362_spec.md
```

Initial rebuild verification: 41 tests passed (CONSTRUCT/fixture), CLI help passed,
nine preflight checks passed. FIX 1b validation is recorded below. No landed module
was edited; the new helper and additional per-file tests remain in this worktree.

Finisher command template, intentionally not executed on an archive:

```text
python -m scripts.platformkit.execution.forward_replay --qualify --books data/cache/ingame_books_local/kalshi/mlb/2026-09-21.jsonl --state data/cache/ingame_books_local/state/mlb/2026-09-21.jsonl --as-of 2026-09-22T00:00:00Z --run-nonce FINISHER_UNIQUE_NONCE --global-cap 1 --reservation-ttl-s 5 --schedule PROSPECTIVE_SCHEDULE.json
```

The cap is an explicit conservative design input, passed to the landed reservation
owner. The schedule must be selected before the game, with no inferred ticker.
The explicit five-second reservation TTL is a design input, not a changed bar.

## FIX 1b - frozen Amendment 2

Authority: `git show master:docs/evidence/tracking/specs/S362_spec.md`, read in this
session. The local spec predates Amendment 2 and is deliberately unchanged. The
preflight spec scan finds no labelled THRESHOLD/BAR lines; it does not certify the
numeric bars. Boundary constructs check the values below independently.

One constant source: `scripts/platformkit/execution/forward_replay_qualification.py`.
Frozen values quoted from Q-1 through Q-3: book age <= 5 s; state age <= 15 s;
window = 3600 s; coverage >= 90 percent; qualified distinct decisions >= 480;
book gaps median <= 45 s, p95 <= 90 s, maximum <= 120 s; state gap maximum <= 30 s;
qualified games per complete sport/family ISO week >= 4; qualified games per sport
>= 30; fill-bearing games before interval reading >= 30. Subsequent authorized
horizons remain 30 / 120 / 300 s, with first same-ticker observation in the inclusive
[fill + h, fill + h + 30 s] window. This row never evaluates those horizons or reads
execution counts. Interval reading remains NOT_AUTHORIZED.

`--schedule` names a prospective JSON list of game_id, ticker, sport, family,
scheduled_start and selected_at. Selection must be no later than scheduled_start;
duplicate games/tickers refuse. No receipt determines the schedule or canonical
ticker. Every scheduled game, including an absent stream, receives the full
3600000 ms denominator. Completed ISO weeks are UTC, assigned by scheduled start;
missing weeks contribute zero and break the stratum streak. Sports and families
are separate; failures stay in scheduled counts. Weekly records are temporary.

Freshness uses response_end receipts only. Refused books do not refresh the clock.
Coverage ends at the next decision, either freshness expiry, reservation expiry,
observed invalidation or window end. Intervals merge before measurement; exact
arithmetic controls verdicts, reported covered milliseconds round down and gap
milliseconds round up. Gap quantiles use nearest rank and include uncovered
boundaries. An absent stream has one 3600 s gap. Duplicate rows add no decisions or
coverage; conflicting ties refuse deterministically. Every applicable decision
reason is counted; individual abstentions do not automatically fail a whole game.
Any positive overlap with a declared trade_gap or host_gap fails the whole game.

Tape proof is an explicit `tape_watermark` record with event_ticker, ticker,
response_end_ts, covered_from_ts, closed_through_ts and pagination_complete=true.
The interval must be receipt-visible, correctly linked and completely paginated;
merged closure intervals must cover the entire window through its closing time.
The capture's latest-trade timestamp is not this proof. Missing proof fails
TAPE_INCOMPLETE, including on a quiet tape. A quiet tape with complete proof is
valid; no outcome, execution or mark value is consulted for qualification.

The closed reason set is BOOK_STALE, STATE_STALE, ADAPTER_REFUSED, LINKAGE_INVALID,
NOT_LIVE, RESERVATION_INVALID, COVERAGE_LOW, DECISIONS_LOW, BOOK_CADENCE, STATE_GAP,
TRADE_GAP, HOST_GAP, TAPE_INCOMPLETE. R2 raw adapter refusal diagnostics remain
separate. All counts reject bool, float, numeric string and Decimal input counts.
Every exception path counts a refusal or propagates; quantities remain Decimal.
The default reservation TTL remains two seconds. A prospective five-second TTL
is explicit in the finisher template and synthetic complete-window construct.
Unmeetable observed bars remain CLOSED AT LIMIT under Q3; improve capture only.

FIX 1b validation (local, synthetic/fixture only): test_forward_replay.py: 41
passed; test_forward_replay_qualification.py: 71 passed (112 total). CLI --help:
one passed. Full owned-file contract preflight: nine PASS, zero FAIL. All seven
owned files are new, ASCII and <= 300 lines. The full-window actual reservation
construct yields PASS, 720 decisions and 3600000 / 3600000 covered / total ms,
with numerical evaluators patched to raise and no trade executions. Review found
and fixed missing state-linkage diagnostics; its regression passes. No actual
archive was opened. The independent landing verifier has not accepted this row.

## FIX 1c

Binding source: master S362 spec, Amendments 1-3; verdict findings 1-7.
All reproductions and regressions use fixtures or constructs only.

1. Missing schedule/state reproduced `quotes_submitted: 2`,
   `label: BOOK_ONLY_ABLATION`, `reservation_grants: 1`. Schedule selection and
   fresh linked live state now gate every Policy.consider call. Missing evidence
   remains FAIL, with LINKAGE_INVALID / NOT_LIVE; ablation never submits.
   Regression: missing schedule variants forbid Policy.consider entirely.
2. Raw-reader Bomb reproduced `OUTSIDE_ADAPTER_READ:yes_bid_dollars`.
   Removed all candidate raw book-value inspection. Touch presence comes from
   accepted adapter ladders at adapter touch prices. Bomb regression now submits
   through stub adapter outputs without touching raw values.
3. Quantity reproduction: `Decimal('1') invalid_count`; integer input yielded
   `quote qty type str`. Quantities now use finite Decimal parsing, including
   trade quantities. Candidate quotes, event quantities, fees and causal inputs
   retain Decimal; landed JSON/event API boundaries use exact decimal strings.
   Decimal/string/integer quantity regressions pass. Fractional order maxima
   remain exact and abstain at the landed whole-order interface, never rounded.
4. Duplicate runs reproduced the same `2026-09-21:repeat:2` and `:3` ids.
   Removed ledger_events input. Nonce checks load recorded order ids using
   position_ledger.read_events from one fixed vault/S362/position_events.jsonl
   journal; append_event persists declarations, expiry and construct fills.
   Other runs provide nonce history only, never current replay inventory.
   A run lock serializes S362 runs. Fresh owners with reused nonces now raise
   reused_run_nonce; new nonces yield disjoint ids and identical fixture counts.
   All checks here replace the target with a temporary construct journal.
5. Original fixture reproduction: `quotes_considered: 6`, `quotes: 8`,
   `fills: 0`, `fill_ledger_events: 0`. The first fixture test now explicitly
   transforms a real fixture print as described above and asserts positive
   tape fills, persisted ledger fills and causal-input counts.
6. Interface spy reproduced `FamilyWeekLedger.streak calls: 0`,
   `returned streak: 1`, `AssertionError: FamilyWeekLedger interface bypassed`.
   Completed-week records now delegate append validation, records and streak to
   FamilyWeekLedger. The same spy passes with one call and returned value 7.
   Temporary declarations/records preserve sport/family isolation and missing
   weeks. Declared outage spans supply required continuity diagnostics; malformed
   intervals conservatively cover the window. Fill evidence stays unassessed.
7. Amendment 3 explicitly owns four modules and two test files plus this memo;
   consolidation is superseded. No landed module or frozen bar changed.

FIX 1c validation: 49 + 72 = 121 tests passed (per-file only); CLI --help: PASS.
Contract preflight: 9 PASS, 0 FAIL. All seven files are ASCII and <= 300 lines.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1d
Authority: root verifier verdict and master S362 Amendments 1-3.
1. BLOCKING crossed derived quotes: reproduced
   `{'submitted': 1, 'quotes': [('yes', 60), ('no', 60)]}`.
   Policy.consider now requires active YES bid < active YES ask before submit;
   crossed and locked pairs raise counted invalid_derived_quote refusals.
   Regression patches the engine inside the real reservation chain and spies on
   submit: crossed 60/40 and locked 50/50 must make zero calls/submissions;
   valid 49/51 and either single active side retain their existing behavior.
2. BLOCKING canonical ticker diagnostics: selected T / book U / game G reproduced
   zero quotes, noncanonical_ticker: 1, and no LINKAGE_INVALID reason.
   Qualification.decision now increments LINKAGE_INVALID before mismatch exit.
   The missing-schedule/linkage regression asserts exactly one such reason,
   FAIL, zero considered quotes and zero submissions for both cases.
3. NOTE: the seven prior corrections require no changes; their constructs remain.
Before fixes, the per-file regression run returned `3 failed, 76 passed`:
`AssertionError: assert 1 == 0` for crossed and locked submission-call counts;
`KeyError: 'LINKAGE_INVALID'` for the canonical ticker mismatch.
After fixes, both minimal reproductions PASS: crossed submissions 0, quotes [],
invalid_derived_quote: 1; wrong ticker quotes 0, LINKAGE_INVALID: 1.
Final per-file validation: test_forward_replay.py 49 passed;
test_forward_replay_qualification.py 79 passed (128 total); CLI --help 1 PASS.
Temporary test storage uses this worktree via TMP, TEMP and TMPDIR; no archives,
network, pod or production ledger is used. Blank lines alone were removed from
existing test/memo text where needed to retain the 300-line cap.

## NOT VERIFIED

- Actual archives, live provider normalization/identity joins, network behavior,
  capture cadence, and any production qualification verdict were not exercised.
- No actual game qualification or completed-week archive evidence was measured.
  The numeric bars are implemented from master Amendment 2, without changing them.
- Execution statistics, numerical causal marks, charged trials and settlement
  marks are disabled. No simulator or causal evaluator runs in qualification.
- Landed fee arithmetic has float paths. Construct handoffs do not certify those
  paths; S370/S378 behavior and actual fee certification are not exercised.
- Persisted position-ledger crash recovery, concurrent writers and short writes
  are not exercised against a production ledger. Only temporary journals ran.
- The original tape precedes the books. The transformed post-arrival fixture
  print is a construct; no observed execution claim is made.
- Large-archive memory use and source timestamps absent from state payloads were
  not exercised. State-age buckets describe receipt age, not unknown provider age.
- Independent verifier acceptance and a committed SHA remain outstanding.
