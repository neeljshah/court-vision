# S435 event response candidate

NOT VALIDATED pending independent verification. Construct metric: before = 0, bar = all 8 pass, n = 8 (CONSTRUCT), after = 8 passing acceptance cases.
The focused test files pass 24 tests (13 in test_event_response.py, 11 AMENDMENT-3/4 regressions split into test_event_response_1c.py to keep the main file at the 300 LOC cap). Local Windows CPU execution only.
No archive was opened. Real-run event counts are NOT MEASURED. See "FIX 1b (AMENDMENTS 1-2)", "FIX 1c (AMENDMENT 3)" and "FIX 1d (AMENDMENT 4)" below for the round-1 through round-3 corrections on top of the original build described in this memo.

## Binding before-condition

Read S435 first, then inspected the named sources before creating modules.
The spec supplies code/data premises rather than an executable command.
The local probe used AST signatures, file existence, schedule JSON length,
SHA-256, git show master, and git ls-files. Its output included:

```text
event_response_absent=True
event_latency_census_absent=True
served_schedule_rows=3
paired_rows_tracked=False
archive_census=NOT_RUN (fixture-only lane)
```

The whole-archive census in part (b) was not repeated: the task explicitly
restricts this builder to constructed fixtures. No replacement count is asserted.
The source inspections confirmed keyed linkage, native_rows materialization,
the two fitted model arms, the per-period loss contrast, and the S412 direction.
The required schedule and absent residual are retained as specified.

The initial raw-byte master comparisons printed `master_identical=False` for
all eight protected files. The checkout uses CRLF and git stores LF. A follow-up
probe printed `git_show_exit 0`, `master_blob_bytes 1972`, and
`lf_normalized_equal True` for venue_time. `git diff master --` over all eight
protected paths was empty. Final normalized comparisons printed:

```text
scripts/platformkit/execution/forward_capture_bridge.py master_content_equal=True
scripts/platformkit/ingame/game_market_link.py master_content_equal=True
scripts/platformkit/execution/venue_time.py master_content_equal=True
scripts/platformkit/execution/entry_timing/study.py master_content_equal=True
scripts/platformkit/ingame/baseline_four_arm.py master_content_equal=True
scripts/platformkit/ingame/baseline_four_arm_eligibility.py master_content_equal=True
scripts/platformkit/ingame/baseline_four_arm_features.py master_content_equal=True
scripts/platformkit/ingame/baseline_four_arm_period.py master_content_equal=True
```

The working-file hashes below also match their before-coding hashes exactly.
No pre-existing module was edited.

## Imported interfaces read before coding

These exact landed signatures were read in their complete modules:

```python
def _links(book_rows: list, state_rows: list, schedule: list, counts: Counter) -> dict:
def parse_venue_time(value: object) -> float | None:
def venue_time_reason(value: object) -> str | None:
def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500,
                    seed: int = 7) -> tuple[float | None, float | None]:
```

The indirect book-index interface, also read in full before coding, is:

```python
def index_kalshi_events(rows: List[Dict[str, Any]], metrics: Optional[Metrics] = None,
                        source: str = "linker") -> Dict[str, Dict[str, Any]]:
```

The report imports only the linkage, timestamp validation, bootstrap, and its new
detector helper. It never invokes native_rows, load_native, or a fitted model.
The helper has no CLI. The report CLI requires every argument named by S435.

## Implementation and refusal accounting (as fixed in FIX 1b -- see below)

1. The helper detects score, period/inning-half, possession, pitcher, and
   status changes between consecutive state dictionaries for each linked
   identity, using the per-sport field names the capture actually writes
   (MLB score_home/score_away/inning/half/pitcher_id; NBA home_score/
   away_score/period, possession only from the sibling state_enrichment
   block; NFL home_score/away_score/period/possession_team). Missing
   fields are counted by type, retain the prior per-kind baseline (never
   reset it), and cannot create a transition through a default.
2. Both daily shards (D and D+1) of each root are read; a missing shard is
   counted (missing_shard) and named in inputs with bytes/sha256 null, and
   that sport prints a NO_SHARD summary row instead of a silent zero. State
   files are loaded whole. Books are read line by line twice. The first
   pass retains distinct metadata tuples and receipt identities for
   duplicate exclusion (first copy kept, the rest counted). The second
   retains receipt and Decimal mid for selected tickers, also keeping only
   the first copy of a duplicate identity; its own sha256 is checked
   against the first pass.
3. Event measurements use an inclusive pre-event boundary (a quote AT E is
   the pre-quote) and a strict post-event boundary, the last quote within
   each horizon, first differing post-event mid, and overlap pairs counted
   per DISTINCT state receipt (several event types on one receipt are one
   instant, not several). A horizon with no quote in its window is
   window_censored_<h> when the window end exceeds as_of or the ticker's
   last visible receipt, else no_quote_<h> (a true mid-stream gap). Missing
   observations remain absent. Every residual is null with
   model_not_reconstructible; its reason is counted once per event.
4. Each sport/type group has event and game counts, Decimal mean/median
   moves, mean bootstrap intervals by game, strict-int lag_n/lag_n_games,
   and median lag. The bootstrap is the only conversion of moves to floats,
   as required by the imported interface. Sparse horizons use their own
   observed game count. Sign agreement has count = 0, n = 0, a null
   interval, and INSUFFICIENT.
5. Linkage is look-ahead-safe: each (sport, game_key) freezes its ticker at
   the earliest of its own receipt cutoffs where the landed `_links` first
   resolves it, using fresh row copies so trial resolutions never mutate
   the shared rows; a later, conflicting state row can no longer erase or
   change an already-established event (the real per-day accounting counts
   still come from one authoritative whole-day `_links` call). Visibility
   filtering precedes schema and duplicate checks. Ordering uses the
   maximum prior timestamp per identity; regressions are counted. Future
   rows are skipped and counted. Output is sorted ASCII JSON with
   allow_nan=False, a unique temporary file, flush, fsync, and atomic
   replace, and echoes as_of.

Declared refusal bounds: counts are strict integers in [0, 2**63 - 1]; scores
are at most 10000, innings/periods at most 1000; probabilities are in [0, 1]
with bid <= ask, at most 1000 digits and no exponent below -1000. These are
input guards, not measured thresholds. Arithmetic uses sufficient Decimal
precision and checks the midpoint result. Every instant is an integer
microsecond count from the shared parser only (int(round(parse_venue_time(v)
* 1_000_000))); no separate fraction is reconstructed, so two receipts whose
fractions differ only below a microsecond collapse to the same instant. A
Decimal conversion failure on a price is counted invalid_price, never under
an exception-class key. Fractional numeric scheduled-start metadata is
refused and counted because the landed linkage cannot consume it exactly.

A sign-agreement share describes this corpus and licenses nothing.
There is no available residual series from which to calculate such a share.

## Construct evidence and reproduction

The first test includes the verbatim first served-schedule entry and constructs
its state/book rows. The spec supplies no verbatim state/book REAL ROW.
It runs the CLI twice, compares complete output bytes, and verifies every input
path, byte count, and SHA-256. Fixtures live in the test source; temporary inputs
and outputs are removed after tests, so reproduction recreates them.

| Case | Test | Result |
|---|---|---|
| 1 | Last quote at or before the horizon, CLI twice | PASS |
| 2 | Empty horizon does not carry an earlier quote forward (a true gap) | PASS |
| 3 | Event at end of game -- all horizons window_censored, not no_quote | PASS |
| 4 | Two events within 5 seconds, both measured with exact moves, overlap = 1 | PASS |
| 5 | Unavailable residual and zero sign-agreement denominator | PASS |
| 6 | Under five observed game clusters | PASS |
| 7 | Five-game ordering permutations and bootstrap | PASS |
| 8 | Duplicate (first copy kept) and out-of-order receipts counted and refused | PASS |

Case 7 reverses game/event iteration with unchanged source files and compares
complete serialized reports. It also reverses file game groups and schedule
entries and compares the entire measurement payload. Provenance changes when
source bytes change; that manifest is intentionally not asserted identical.
The five-game fixture also exercises a four-game horizon and a five-game horizon.
Additional probes exercise count types, exact JSON decimals, microsecond
truncation and boundary inclusion, naive timestamps, all event kinds per
sport, missing fields, no pre-event quote, unchanged mids, unlinked games,
future malformed rows, numeric time precision, invalid prices, no-look-ahead
linkage, baseline retention, overlap boundaries, lag_n/lag_n_games, D+1 shard
reads, a missing-shard fixture, the interim-detector marker, and interrupted
fsync/replace while preserving the previous report.

```text
python -m pytest tests/platformkit/ingame/test_event_response.py -q -p no:cacheprovider
13 passed
python -m pytest tests/platformkit/ingame/test_event_response_1c.py -q -p no:cacheprovider
11 passed
python -m scripts.platformkit.ingame.event_response --help
exit 0
```

Final mechanical checks: 9 PASS, 0 FAIL. All five owned files are ASCII and at or under 300 lines: report module 291, detector 222, main tests 300, 1c regression tests 189, memo under 300. The only CLI supplied by these modules passed its --help check (1/1).

The CLI reproduction itself is in test_01, using --books-root, --state-root,
--schedule, --date, --sports, and --out against constructed shards.
The contract preflight command is:

```text
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/event_response.py scripts/platformkit/ingame/event_response_events.py tests/platformkit/ingame/test_event_response.py tests/platformkit/ingame/test_event_response_1c.py docs/evidence/harness/S435_event_response_2026-09-24.md --base master --spec docs/evidence/tracking/specs/S435_spec.md
```

```text
PASS vocab clean over 5 files
PASS crlf no index-side CRLF over 5 file(s); 5 untracked, core.autocrlf normalizes on add
PASS loc all .py <= 300 LOC
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold 2 literal(s) matched
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 4 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

Contract review: additive files only; no changed bar, trial, fit, scored corpus,
deployment, flag, registry, or shared module. B1-B11 and Q1-Q9 were reviewed for
this construct-only report. Reproduction replaces the eye check. Exact source
provenance in "FIX 1c" below supports A9; the local-only execution and counted
fields support S1, S2, and S4. Independent verification remains required.

## FIX 1b (AMENDMENTS 1-2)

Interim-detector sentence (AMENDMENT 1c, repeated here): event_response_events.py
duplicates scripts.platformkit.ingame.event_latency_census's own event definitions
(S431); replace this module with that import once S431 lands with identical
per-sport field definitions. S431 has not landed as of this fix.

Identities as of this round are SUPERSEDED by the FIX 1c fast-forward below
(base commit changed from 464c201ac to the FIX 1c base sha); see "FIX 1c
(AMENDMENT 3)" for the current candidate-file and must-not-move-file table.
The eight must-not-move files listed in "Binding before-condition" remained
byte-identical to master at this round too.

Each amendment item, its fix location, and the test that covers it:

| Item | Fix (file:function) | Test |
|---|---|---|
| A1a no look-ahead in linkage | event_response.py:`_asof_links` | test_linkage_and_baseline_and_summary_amendments |
| A1b/A2c invalid row never pops the baseline | event_response_events.py:`detect_events` | test_linkage_and_baseline_and_summary_amendments |
| A1c interim detector marker | event_response_events.py:`INTERIM_NOTICE` | test_shards_marker_and_lazy_streaming |
| A1d worktree fast-forwarded, identities refreshed | this section | n/a (memo-only) |
| A1e exact 5/30/120s moves, incl. a positive 120s and overlap moves | event_response.py:`_measure` | test_01, test_04 |
| A1f strict-int lag_n/lag_n_games, mixed present/absent | event_response.py:`_summary` | test_linkage_and_baseline_and_summary_amendments |
| A2a microseconds from the shared parser only | event_response_events.py:`instant` | test_strict_counts_and_time_and_price_refusals |
| A2b censored horizons, as_of echoed | event_response.py:`_measure`, `report` | test_02 (true gap), test_03 (censored) |
| A2c = A1b (invalid rows) | see A1b | see A1b |
| A2d overlap per distinct receipt, exactly-5s inclusive, multi-type is one instant | event_response.py:`_count_overlaps` | test_linkage_and_baseline_and_summary_amendments |
| A2e per-sport field names, NBA possession via state_enrichment, NFL possession_team | event_response_events.py:`_FIELDS`, `_value` | test_all_kinds_per_sport_and_missing_state |
| A2f D and D+1 shards, missing shard is NO_SHARD and named | event_response.py:`report` | test_shards_marker_and_lazy_streaming |
| A2g pre-quote at-or-before E, duplicates keep first copy, status is an event kind, pitcher_id None carries no information | event_response.py:`_measure`; event_response_events.py:`unique_rows`, `detect_events` | test_08, test_all_kinds_per_sport_and_missing_state, test_linkage_and_baseline_and_summary_amendments |
| A2h counts partition (invalid_price no exception-class key), pass-2 sha256 checked, streaming proved | event_response.py:`_mid`, `report` | test_strict_counts_and_time_and_price_refusals (prices); test_shards_marker_and_lazy_streaming (streaming); pass-2 sha256 check runs on every fixture but has no dedicated failure-case test |
| A2i memo identities and interim sentence restated | this section | n/a (memo-only) |

Known gap (round 1, closed in FIX 1c): the pass-2 sha256-vs-pass-1 integrity
check named in A2h was not yet implemented in `report()` as of this round;
see FIX 1c item (c) below.

## FIX 1c (AMENDMENT 3)

Round 2 (codex sol REJECT, six blockers). Base sha (`git rev-parse --short
HEAD`): aac8a5b86. All eight must-not-move files remain byte-identical to
this tip (`git diff master -- <8 paths>` is empty; reverified after edits).

| Item | Fix (file:function) | Regression test |
|---|---|---|
| 3a censorship decided before horizon-quote selection, using ANY visible receipt (valid or invalid mid), not just the valid tape | event_response.py:`report` (`last_seen`), `_measure` | test_event_response_1c.py:test_amendment3a_censorship_decided_before_selection; also fixed test_02, test_07, test_08, and two test_all_kinds_per_sport_and_missing_state cases that had relied on the old stale-quote bug |
| 3b linkage time-gated for BOTH streams (book metadata `_first_seen`, not just state visibility) | event_response.py:`report` (`first_seen`, `reduced`), `_asof_links`; event_response_events.py:`detect_events` (`link_not_yet_established`) | test_event_response_1c.py:test_amendment3b_linkage_time_gated_for_both_streams; also fixed test_event_response.py's exactly-5s-overlap case (now needs book(0)) |
| 3c pass-2 integrity: bytes+sha256 per shard compared against pass 1; mismatch fails with shard_changed_between_passes, nothing written | event_response.py:`report` (`book_hashes`) | test_event_response_1c.py:test_pass2_integrity_mutation_fails_the_run |
| 3d out-of-order excluded BEFORE frequency accounting (never also duplicate_instant); a duplicated-only metadata receipt still yields a link | event_response_events.py:`rows`; event_response.py:`report` (`reduced` no longer filtered by frequency) | test_event_response_1c.py:test_amendment3d_out_of_order_replay_not_also_duplicate, test_amendment3d_duplicated_only_metadata_still_yields_link |
| 3e mutant-complete tests: 5/30/120s incl. positive 120s, both overlapping events' exact moves, state_changed tallies, a D+1 book row used by an event, the pass-2 mutation, lag_n vs lag_n_games with two games | event_response.py:`_measure`, `_summary` (unchanged logic, new coverage) | test_01 (120s move), test_04 (overlap, unchanged), test_event_response_1c.py:test_state_changed_tallies, test_d1_book_row_used_in_event_move, test_pass2_integrity_mutation_fails_the_run, test_lag_n_vs_lag_n_games_with_two_games |
| 3f identities regenerated at verify time; stale duplicate table removed | this section; FIX 1b's own table above replaced with a pointer here | n/a (memo-only) |

Fresh sizes/sha256 as of this round: SUPERSEDED by FIX 1d's table below (base sha moved from aac8a5b86 to bcbb81730; event_response.py, event_response_events.py, test_event_response_1c.py and S435_spec.md all changed bytes again in FIX 1d).

## FIX 1d (AMENDMENT 4)

Round 3 (codex sol REJECT, two blockers). Base sha (`git rev-parse --short HEAD`): bcbb81730. AMENDMENTS 1-3 confirmed unchanged; only the two round-3 items below were touched.

| Item | Fix (file:function) | Regression test |
|---|---|---|
| 4a last-visible receipt = every parseable receipt: pass 1 extends `last_seen` per (sport, ticker) as soon as ticker+instant+record_type parse, before the out-of-order/count/http_status/other checks; `_measure` still consumes the same map | event_response_events.py:`rows` (`last_seen` update, before the out-of-order check); event_response.py:`report` (map now built during pass 1, threaded into `_measure`) | test_event_response_1c.py:test_amendment4a_invalid_row_extends_visibility |
| 4b first-copy/refusal partition: right after the out-of-order check, a repeated identity is rejected in `rows` itself via the shared `frequencies` counter (first copy claims it, retained whether it later fails or not; a later copy is never yielded); the pass-2 `seen`/aggregate workaround and the post-hoc `unique_rows` helper are both removed; one `frequencies` counter spans both pass-2 shards | event_response_events.py:`rows` (dedup claim; `unique_rows` deleted); event_response.py:`report` (state loop and pass-2 loop consume the shared counter directly) | test_event_response_1c.py:test_amendment4b_invalid_first_copy_then_valid_duplicate, test_amendment4b_conflicting_metadata_duplicate_first_wins |

Net effect: event_response.py 291 LOC (was 298), event_response_events.py 222 LOC (was 221, `unique_rows` deleted and folded into `rows`). test_event_response.py 13 passed (unchanged); test_event_response_1c.py 8 -> 11 passed (3 new AMENDMENT-4 regressions). Contract preflight rerun this round: 9 PASS, 0 FAIL. All eight must-not-move files remain byte-identical to master (`git diff --stat master -- <8 paths>` empty, reverified this round).

Fresh sizes/sha256 (this tree, after the FIX 1d edits):

| Full path | size_bytes | sha256 |
|---|---:|---|
| scripts/platformkit/ingame/event_response.py | 14263 | c92c7a5ecc6c8d3feec20d7bb51c89b03cb4353f3ccb75dc6716282bc8df2f84 |
| scripts/platformkit/ingame/event_response_events.py | 10205 | cb1feff68f45caf34a9ce6fcbba4bf43eaaffd8a869a2050a112fd1927d58dd8 |
| tests/platformkit/ingame/test_event_response.py | 18997 | b8a88a7c753f7f61e91567cb02da64244a0e2939840f38172c2dcf97f5a00e21 |
| tests/platformkit/ingame/test_event_response_1c.py | 9330 | 7119fe2fe5b9deda42a09f22d9da4a464cf6caaf179339912b3f090d22658e13 |
| docs/evidence/tracking/specs/S435_spec.md | 15023 | d2de126ca5b83b1917c175fa5135d64cf45eed141f6c9c21c8183560bc1ce854 |
| docs/evidence/tracking/specs/S412_spec.md | 17633 | fbb4ec97a65503344c9dae1bf62916d611f631af3f15186f459d9d8cca21a6a3 |
| scripts/platformkit/execution/forward_capture_bridge.py | 14657 | 568a5f19a9a3c2c482bcd5b401ba1a0714f46a1120b379d18b18b4c2f222d7ff |
| scripts/platformkit/ingame/game_market_link.py | 9410 | 800b82ea07b2d8a06f5f49c5751e3a0dd0ab1405e59dd798353541da8f55f8dc |
| scripts/platformkit/execution/venue_time.py | 2029 | 651d80edc0ef0788ea543b2cf3e9f4ae8c1d5114e67211cf7fcd6047eade79f8 |
| scripts/platformkit/execution/entry_timing/study.py | 8325 | 95e97820786a878581b3c420d7202ab940a22078c43c53111715dfba09ce12d4 |
| scripts/platformkit/ingame/baseline_four_arm.py | 17746 | ee821a457d5a3eb63583f36fec01872301ba0f7eb55c57279266831ab84465db |
| scripts/platformkit/ingame/baseline_four_arm_eligibility.py | 11924 | c4c50ec7055179cb5dd0866493d421b142a0e594ad83a0af3534c17fa7f57595 |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 15557 | 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647 |
| scripts/platformkit/ingame/baseline_four_arm_period.py | 17174 | 7e97352e63d412dfe10a553a9de89ece16184a1fbe397510b00e129988a6e592 |

This memo's own hash is not listed (self-reference at write time is circular). None of the eight must-not-move files changed bytes this round.

## NOT VERIFIED

- No real archive census, served-game event count, or event response was measured.
- No real residual or nonzero sign-agreement denominator is reconstructible here.
- No network, pod, GPU, fitted model, or runtime integration was exercised.
- No real non-MLB provider data was exercised; the NBA/NFL per-sport field
  mapping is proven only against CONSTRUCT fixtures, not a captured shard.
- No concurrent input mutation, storage exhaustion, or physical power loss was
  exercised; interruption tests simulate fsync and replace failures. The
  pass-2 integrity regression mutates the shard via a monkeypatched `rows`
  call between passes, not a genuine concurrent OS-level write.
- No independent verifier decision or commit was created in this build lane.

## REAL RUN 1 -- 2026-09-22 MLB served games (orchestrator, host; started 2026-09-24 22:53Z, finished 2026-09-25 01:2xZ)

Artifact: docs/evidence/forward/event_response/2026-09-22_mlb_event_response.json (85186 bytes, status REPORT_ONLY, units probability_units). Roots: the kalshi/ and state/ subdirectories (the first attempt with the archive roots refused with missing_shard -- the S435 CLI resolves <root>/<sport>/<day>.jsonl, unlike the S431 census, which takes the archive roots; both conventions now recorded). Schedule docs/evidence/forward/schedules/2026-09-22_maker_forward.json (TORBAL 824785, MILPHI 823412, MIACHC 824624).
Runtime: 9321.7 s wall on the host for 343 + 155 MB of book shards and 7 + 11 MB of state shards (streaming, regex per line, Decimal arithmetic).
Events: 159 rows; by type: {"period": 89, "pitcher": 49, "score": 16, "status": 5}.
Counts: {"LINKAGE_INVALID": 1, "conflicting_state_linkage": 1, "event_type_unavailable": 7107, "missing_directional_team_evidence": 30, "model_not_reconstructible": 159, "no_quote_120": 55, "no_quote_30": 62, "no_quote_5": 65, "no_quote_change": 13, "overlap_5s": 0, "period_event_type_unavailable": 939, "pitcher_event_type_unavailable": 939, "possession_event_type_unavailable": 4290, "score_event_type_unavailable": 939, "state_changed_false": 3240, "state_changed_null": 3, "state_changed_true": 1047, "state_key_conflicted": 1, "state_rows_missing_start": 0, "unconsumed_books_records": 228842, "unlinked_state_row": 21094, "window_censored_120": 13, "window_censored_30": 13, "window_censored_5": 13}.

Descriptive reading (counts only, no probability claim): the 159 events split 89 period / 49 pitcher / 16 score / 5 status, the SAME tallies the S431 census found on these shards (the per-type unavailable counters are per-row non-events, not a schema mismatch); every event is model_not_reconstructible (the served MLB in-game number is the pregame carry -- S447), so no residual is measurable on this corpus; quote availability at 5 / 30 / 120 s after an event is missing for 65 / 62 / 55 events.

DEFECTS SURFACED BY THE REAL RUN (landed module; NEW GAP S457 allocated). CORRECTION 2026-09-25 01:3xZ: an earlier draft of this section claimed the MLB event fields did not match the state rows; the artifact tallies refute that (89 / 49 / 16 typed events) and the claim is withdrawn -- the two defects below stand.
- Unbounded Decimal precision: summary means are serialised with up to 2106 characters (a Decimal division carried out at an unbounded context precision); the artifact should quantise every reported statistic (integer microseconds or probability units at a fixed exponent).
- Runtime: 9321.7 s for one served day is not operable nightly; the row needs a streaming pass that pre-filters by served ticker / game_key before regex parsing.

NOT VERIFIED here: the hand recompute of two events against the raw shards (owed); no second corpus (the 2026-09-24 served games are not yet settled). Nothing served changes; no flag, no threshold, no registry write.
