# S431 event latency census candidate

Verdict: candidate built; independent verification pending.
WHERE: local CPU in C:/Users/neelj/nba-harness-h91. Construct fixtures only.
Owned files: scripts/platformkit/ingame/event_latency_census.py,
tests/platformkit/ingame/test_event_latency_census.py, and this memo.

## Binding before-condition
The initial source probe confirmed all twelve named platformkit source files
exist and printed their byte sizes and SHA-256 values (inventory below).
It then exited 1 because the cited S213 JSON is absent in this worktree; only
the S213 ledger, docs/evidence/harness/S213_ingame_latency_ledger_2026-09-04.md,
is tracked on master (AMENDMENT 1(i)). The follow-up probe printed exactly:

```text
BEFORE module_absent = True
S213 cited artifact exists = False
ARCHIVE recount = NOT RUN (construct-only instruction)
```

The receipt producer uses response_end_ts for books and response_end_utc for
states. Book kinds are snapshot and snapshot_bulk; trade is separate. State
identity is the exact (sport, game_key), resolved to the schedule's ticker.
NBA possession is in the sibling state_enrichment block. MLB half is copied
verbatim from inningState/inningHalf, including Top, Bottom, Middle and End.
load_native materializes rows and is not called. The frozen constants remain
5.0 seconds and 95.0 percent; neither is used as a new census threshold.
The cited S213 artifact and archive distributions could not be reverified;
the authorized construct build does not require opening an archive.

Before coding, the three imported landed modules were read in full. The exact
public signatures relied on are:

```python
def parse_venue_time(value: object) -> float | None:
def cluster_boot_ci(values: list[float], clusters: list, n_boot: int = 500,
                    seed: int = 7) -> tuple[float | None, float | None]:
def nearest(values: list, percentile: int) -> D:
```

The shared parser validates every receipt instant. Its float result is the
ONLY source of a timestamp's value: instant() is int(round(seconds * 1e6)),
with no separate nanosecond reconstruction, for joins, duplicates, cutoff
comparisons and every window. Reported duration fields ending in _s contain
integer microseconds, declared by duration_unit. Rounding is nearest-microsecond
via the shared parser; update_receipt_us (renamed from update_receipt_ns)
preserves exact shared-update identity across DISTINCT state receipts only.
The bootstrap receives Decimal microseconds and bounds the mean, never a median.
Its defaults n_boot=500 and seed=7 are echoed. Fewer than five lag-bearing game
clusters produce INSUFFICIENT with null bounds. Prices never pass through float.

## Construct acceptance
Before: 0 of 9 (module absent). Bar: all 9 of 9 enumerated constructs.
1. First differing quote: unchanged receipt at +11; changed receipt at +25;
   state at +10 has 15,000,000 us lag and two receipts in its next 30 seconds.
2. Update beyond 300 seconds: null lag and no_update_300s=1.
3. Last state receipt: null next gap and state_next_absent=1.
4. Two changes in one book gap: both event rows retained and shared_update=1.
5. Duplicate receipt: first accepted copy retained; duplicate counter increments.
6. Earlier receipt in file order: refused and out_of_order increments.
7. Fewer than five clusters: INSUFFICIENT and null mean bounds.
8. D+1 bulk receipt: joins across midnight and reports snapshot_bulk.
9. Iteration-only open wrapper: no whole-shard read or readlines is permitted.

The first test consumes the verbatim TORBAL schedule entry from the committed
schedule. The spec supplies no verbatim real book/state JSON row. Receipt rows
are explicit constructs matching landed producer fields; no archive is read.
Additional cases cover strict count types, malformed JSON, exact Decimal quote
changes, provider half transitions, NaN/infinity, unsupported bounds, future
malformed rows in both positions, zoned microsecond boundaries, naive refusal,
all event types in three sports, missing enrichment, no prior quote, skipped
trade rows, five-cluster bootstrap, missing streams, schedule ambiguity, and
atomic output interruption. Interleaving different games in both orders leaves
events and summaries identical. Within a key, S431 explicitly requires file-order
refusal, so reordering that key's receipts can change accepted rows by design.

## Reproduction and validation
Run locally:

```text
python -m pytest tests/platformkit/ingame/test_event_latency_census.py -q -p no:cacheprovider
python -m scripts.platformkit.ingame.event_latency_census --help
python -m scripts.platformkit.tracking.contract_preflight --paths scripts/platformkit/ingame/event_latency_census.py tests/platformkit/ingame/test_event_latency_census.py docs/evidence/harness/S431_event_latency_census_2026-09-24.md --base master --spec docs/evidence/tracking/specs/S431_spec.md
```

The CLI fixture test invokes the CLI twice with identical inputs and compares
output bytes exactly. Every opened input is recorded with its absolute path,
streamed byte count and SHA-256; an absent shard has explicit MISSING status
with bytes null and sha256 null (fixed under FIX 1b, A2(b): it used to read
bytes=0). JSON resolution is records, not image dimensions. Request starts are
echoed as str; response ends alone determine receipt order. The fixture hash
test independently checks each input digest and byte count. Outputs include
every event and all refusal/skip counts. The output is ASCII, sorted JSON with
integer counts and integer microsecond durations throughout (no nanosecond
value anywhere). An fsync failure leaves an existing output intact and removes
its own temp file; atomic replacement occurs only after flush and fsync.

Final validation (post FIX 1e, AMENDMENT 5): 40 tests passed, including all 9
acceptance cases, the AMENDMENT 4 decode-level regression, and the AMENDMENT 5
n_window_censored summary assertion. CLI --help exited 0; all 9
contract_preflight checks passed over all 3 owned files. The
40/39/38/37/29-test passes (FIX 1d/1c/1b/round 1/pre-amendments) are
superseded by this run. Source is 300 lines; tests are 299 lines; all 3 owned
files are ASCII and at most 300 lines.

## Source inventory
Full source paths below are relative to C:/Users/neelj/nba-harness-h91;
resolution for each is source text. Sizes and hashes are bytes on disk.

- scripts/platformkit/ingame/local_capture_runner_row.py: 6901 bytes; SHA-256 7a962ee8fc1d6dcb46941d1fef0903a4721d57b510b83dcfb8736c91c61570a1.
- scripts/platformkit/ingame/local_capture_runner.py: 17793 bytes; SHA-256 c8e84178c93eeb6f3e44fa9575847c5234d0436389220014023967ff39f09452.
- scripts/platformkit/ingame/local_state_capture.py: 17829 bytes; SHA-256 129b12eb42895a5ae02cb8a6fd0c2df4e6860e7259f82a8dee0a969f846957c0.
- scripts/platformkit/ingame/baseline_four_arm_features.py: 15557 bytes; SHA-256 4cd95bb70b0578318ad04f7144455e083a754924c8b0ee2c6c596e38e9880647.
- scripts/platformkit/ingame/local_state_capture_sources.py: 20512 bytes; SHA-256 70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e.
- scripts/platformkit/ingame/ingame_gumbo_mlb.py: 10529 bytes; SHA-256 9dc6abdf1eb0f40b8375932845467ed61682ef5fb308cbe756653a974f317ec1.
- scripts/platformkit/ingame/nba_state_enrichment.py: 2990 bytes; SHA-256 daab09f81cbf99fcb294435fe67969761927ea527cbe4c1265d69ba3a4c21b50.
- scripts/platformkit/execution/forward_capture_bridge.py: 14657 bytes; SHA-256 568a5f19a9a3c2c482bcd5b401ba1a0714f46a1120b379d18b18b4c2f222d7ff.
- scripts/platformkit/execution/venue_time.py: 2029 bytes; SHA-256 651d80edc0ef0788ea543b2cf3e9f4ae8c1d5114e67211cf7fcd6047eade79f8.
- scripts/platformkit/execution/entry_timing/study.py: 8325 bytes; SHA-256 95e97820786a878581b3c420d7202ab940a22078c43c53111715dfba09ce12d4.
- scripts/platformkit/execution/forward_replay_qualification.py: 14837 bytes; SHA-256 0170676d9d4e17e1792deb8fb556a490afaeea2ae033369a4148392fcbf1c84e.
- scripts/platformkit/ingame/latency_scoreboard.py: 3707 bytes; SHA-256 f0d6ef45d724243461323553867761767d364d5abea6df5f1e6705f413f14afd.
- scripts/platformkit/ingame/capture_scheduler.py: 22143 bytes; SHA-256 0f959fd63f79c12823c00afeb2c92befffb1f6c0d2d5d7a75b5d52d1892abf59.
- domains/basketball_nba/live_state_nba.py: 10913 bytes; SHA-256 0162899b479339deb155df8187e784dc8e7e62d595fc8ed1e7cf5cfdcf6203ec.
- domains/nfl/ingest_nfl_states.py: 13537 bytes; SHA-256 a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb.
- docs/evidence/forward/schedules/2026-09-22_maker_forward.json: 849 bytes; SHA-256 10eb2e7b57a2917654caa57be3c8c6d3b1eaab22ade0bbaf530e6682002fa7d8.
- docs/evidence/tracking/specs/S431_spec.md: 16557 bytes; SHA-256 cca4d796b1da7524b1bd7670dc01fe5a815af2fed222a82d3cca297608f10353.

All rows above (including baseline_four_arm_features.py, added earlier) are
measured from this worktree at base commit 58658bba5, post FIX 1e; the spec
row (grown again by AMENDMENTS 4-5, unrelated to this candidate's own files)
is replaced in place above, not appended beside.

A read-only git diff against master for all fourteen producer/shared modules
returned no output. No pre-existing file was edited. No gate or frozen artifact
was changed. Contract self-check: B1-B11 and Q1-Q9 applied as construct scope;
there is no scored comparison, fitted model, trial charge, or deployment. Q9
per-event evidence and A2 deterministic reproduction are exercised. A9 inputs
carry byte/hash identities; S1 machine and S4 count fields are explicit above.
The reviewer caught provider-half vocabulary and asymmetric missing-stream
reporting defects before submission. Both were fixed and have passing fixtures.

## Real-run counts
NOT RUN. No real archive, network, GPU or remote machine was used. The intended
local orchestrator run and its count table remain pending; no real-run count is
represented as zero or inferred from constructs.

## FIX 1b (AMENDMENTS 1-2)
Applied every item of AMENDMENT 1 and AMENDMENT 2 to the round-1 codex build
(37 tests). All 38 tests pass locally; 9/9 contract_preflight checks pass.

- A2(a) = A1(h) MICROSECONDS ONLY: instant() (event_latency_census.py:25-30) now returns
  int(round(parse_venue_time(value) * 1_000_000)) with no nanosecond reconstruction; the NS
  constant and its regex-based fraction parsing are removed. update_receipt_ns is renamed
  update_receipt_us (events_for, :164-193) and every window/comparison (:168, :182, :186-188) is
  in microseconds. Test: test_microsecond_boundaries -- ".0000001" and ".0000009" fractions give
  the identical instant, and an update exactly at E + 300s is included (lag 300s,
  no_update_300s=0).
- A2(b) NO_SHARD: lines() (:38-51) now sets bytes=None/sha256=None while a shard is MISSING
  (previously bytes stayed 0). census() (:225-228) treats ANY missing_shard (either day, either
  stream) as NO_SHARD and skips events_for for that sport entirely, so it prints zero summaries
  instead of computing partial events off the one day that exists. Test: extended
  test_five_clusters_and_missing_streams with a one-day-only removal (kalshi/mlb/2026-09-23.jsonl
  deleted, 2026-09-22 kept) asserting reason NO_SHARD, events == [], and the missing path's
  bytes/sha256 are null.
- A2(c) = A1(a) DUPLICATE IDENTITY BEFORE AS-OF: schedule_rows() (:59-78) now checks every row's
  (sport, game_key) and ticker for duplicates in a first pass over the WHOLE schedule, before the
  selected_at > cutoff filter runs in a second pass (previously the after-cutoff continue skipped
  the duplicate check for any row selected after as_of). Test: the schedule duplicate case in
  test_cli_reproduction_refusal_and_atomic_failure now uses a second entry with the same identity
  but selected_at AFTER the cutoff, and still asserts exit 3.
- A2(d) = A1(b) FIRST COPY KEPT, PROVED: test_05_duplicate_first_kept rewritten so the duplicate
  book copies carry different quotes and the later update equals the DISCARDED copy's value (only
  keeping the first copy yields the asserted 15,000,000us lag), and the duplicate state copies
  carry different scores with a later state row equal to the FIRST copy (asserts no extra event; a
  wrongly-kept second copy would show a change).
- A1(c) STREAMING PROVED: test_09_streaming_no_whole_file_read now counts lines consumed per path
  as the wrapped file iterates, and asserts (via a patched decode()) that exactly 1 line was
  consumed by the time the first row reaches decode -- catching a list(stream)-style eager-
  materialization mutant that the old read()/readlines() trap alone would miss.
- A1(d) BOUNDARIES TESTED: test_boundaries_one_sided_and_censored asserts a book receipt exactly
  at E (quote 0.45) then 0.41 at E+15s gives quote_age_s=0, n_book_receipts_30s=1, lag exactly
  15,000,000us.
- A1(e) ONE-SIDED QUOTES: parse_quote_side() (:106-113) returns None for a None side instead of
  raising; collect() (:143-148) keeps the row, counts one_sided_quote, and only compares bid>ask
  when both sides are present. None removed from test_invalid_quotes_counted's bad-value list (no
  longer an error); test_boundaries_one_sided_and_censored asserts one_sided_quote is counted and
  a change to a one-sided book resolves a lag.
- A1(f) WINDOW_CENSORED: events_for (:164-193) adds a window_censored field; no_update_300s is now
  int(prior>=0 and update is None and not censored) (:187), window_censored is int(update is None
  and censored) (:188), where censored = cutoff < at + 300*US (:169). Test:
  test_boundaries_one_sided_and_censored with as_of = E + 100s asserts window_censored=1,
  no_update_300s=0, and a null lag.
- A1(g) ENCODING: new echo() helper (:33-35) stringifies every echoed raw field (request_start_ts,
  request_start_utc, response_end_utc) at ingestion so a Decimal (from a numeric raw value read
  via parse_float=Decimal) can never reach json.dump. main() (:250-278) now tracks the temp file
  name (temp_name, :257/:263) and removes it in the except branch on any failure (:270-271), so no
  tmp* file survives. Tests: test_decimal_echo_encoded_as_str (a float request_start_ts decodes to
  Decimal and is still echoed as str; json.dumps succeeds);
  test_cli_reproduction_refusal_and_atomic_failure asserts no tmp* file remains in the output
  directory after an injected fsync failure.
- A1(h) shared_update PER DISTINCT RECEIPT: census() (:236-241) now counts shared updates by
  (ticker, update_receipt_us, receipt_us) first, collapsing duplicate event rows from the SAME
  state receipt to one entry before counting how many DISTINCT receipts share an update. Test:
  added an assertion to test_mlb_all_types_and_exact_decimal that all 4 event types from one state
  receipt sharing one update all have shared_update == 0.
- A1(i) MEMO: the "Binding before-condition" section above now names
  docs/evidence/harness/S213_ingame_latency_ledger_2026-09-04.md (the tracked ledger) instead of
  only stating the cited JSON's absence.

A9 identity of the two owned Python files (final, post FIX 1e; replaces the
post-FIX-1d row above, not appended beside it):
- scripts/platformkit/ingame/event_latency_census.py: 300 lines, 15500 bytes,
  SHA-256 f3d0511ff4a8779e7e796eea66aabcbecd8195dae84a4b87ece65e6151937fe9.
- tests/platformkit/ingame/test_event_latency_census.py: 299 lines, 16645
  bytes, SHA-256 ac041fe65062b2695bbbbea3003a9d230b741f08bb3f16091b059660c9950141.

`git status --short` over the worktree shows only the three owned, untracked
paths; no landed module was touched. Worktree HEAD is 58658bba5 throughout.

## FIX 1c (AMENDMENT 3)
Applied round-2 sol REJECT (five blockers) to the post-FIX-1b build (38 tests).
39 tests pass locally; 9/9 contract_preflight checks pass. No real-run claim.

- (a) PARSER DECIDES THE TYPE: instant() (event_latency_census.py:25-30) no
  longer gates on isinstance(value, str); it calls parse_venue_time(value)
  directly for any type, then requires a finite float result before rounding
  to integer microseconds (None or non-finite -> invalid_time, unchanged).
  parse_venue_time itself already special-cases bool (rejected) and accepts
  finite int/float as epoch seconds (venue_time.py _parse). Test:
  test_instant_numeric_epoch_no_type_gate asserts instant(0) == 0 and
  instant(1.25) == 1_250_000.
- (b) NO_SHARD COMPLETE AND FIRST: census() (:225-227, :246) now checks
  no_shard BEFORE not-selected in the reason ternary, so NO_SHARD outranks
  NO_SERVED_GAME and every other reason; the summary field itself is renamed
  reason -> summary_reason (exact key) throughout. Every missing path stays
  listed in the existing `inputs` array (status MISSING, bytes/sha256 null),
  which already names every attempted D/D+1 path per stream. Tests:
  test_five_clusters_and_missing_streams now asserts nba's summary_reason is
  NO_SHARD (not NO_SERVED_GAME) when its shard is also absent, and adds a
  second-missing-shard case (state/mlb/2026-09-22.jsonl removed on top of the
  already-removed kalshi day) asserting summary_reason NO_SHARD, zero events,
  and exactly two MISSING inputs for that sport; test_one_missing_stream_reason
  updated to the summary_reason key name (AMENDMENT 3(b), 3(e)).
- (c) A QUOTE NEEDS BOTH FIELDS AND ONE FINITE SIDE: collect() (:143-150) now
  refuses (quote_fields_missing) a book row whose yes_bid or yes_ask key is
  absent, or where neither present side is finite, via the new finite_side()
  helper (:106-113) that never raises; one_sided_quote is reached only past
  that gate, so it is reserved for rows carrying both keys with exactly one
  side null. The reason is added to the classified-refusal tuple in collect()'s
  except block so it counts under its own name instead of parse_refused. Such
  a row is never appended to output[key], so it never becomes an update. Tests:
  test_boundaries_one_sided_and_censored gains a both-null case asserting
  quote_fields_missing == 1 and one_sided_quote == 0; new
  test_quote_fields_missing_neither_key deletes both keys entirely on the only
  book row and asserts quote_fields_missing == 1, accepted == 0, and the sole
  event is no_prior_book (no update was created).
- (d) CASE 5 EXPLICIT ASSERTIONS: test_05_duplicate_first_kept now also
  asserts quote_age_s == 10_000_000 (the age only the retained first book copy
  at t=0 produces against the state receipt at t=10) and event_type == 'score'
  (the sole retained event is the score transition at the first state copy's
  value, per the existing len(events) == 1 / lag == 15_000_000 proof that the
  duplicate state copy's score was discarded).
- LOC: both python files were compacted (blank lines between top-level defs
  removed in the test file; no logic lines removed, no acceptance case
  deleted) to stay at or under the 300-line cap while adding the AMENDMENT 3
  regressions: event_latency_census.py 278 -> 293 lines; the test file
  298 -> 283 lines despite adding 5 new/extended test bodies.

## FIX 1d (AMENDMENT 4)
Applied round-3 sol REJECT (one blocker, one correction) to post-FIX-1c (39
tests); 40 tests pass locally; contract_preflight unchanged.
- (a) decode() used parse_float=Decimal for numeric epochs; Decimal fails
  parse_venue_time's isinstance(value, (int, float)) gate, so a fractional
  epoch like response_end_ts: 1.25 was refused invalid_time on the real
  decode path (instant(1.25) called directly already worked). New _Num(float)
  (event_latency_census.py, by US) stores the source token in __init__ and
  returns it from __str__/__repr__; decode() now uses parse_float=_Num, so
  numeric tokens pass the isinstance gate via float(value) while str(value)
  keeps parse_quote_side's Decimal(str(side)) byte-exact. Test:
  test_decode_level_fractional_epoch_and_exact_quote decodes a raw shard with
  an unquoted 1.25/2.25 response_end_ts and two 90-digit yes_bid tokens
  (differing past double precision) through collect(), asserting
  1_250_000/2_250_000 us and unequal exact quote sides.
- (b) MEMO <= 300 LINES: blank line between each Source inventory entry
  removed; no row's text or evidence changed or deleted.

## FIX 1e (AMENDMENT 5)
window_censored joined the existing per-field n_ counter loop in summarize() (event_latency_census.py, no new line, cap held at 300); test_boundaries_one_sided_and_censored now asserts n_window_censored == 1 on the censored event's summary row. A9 identities above are regenerated from this tree at HEAD 58658bba5 (round-4 sol REJECT, two blockers, both closed).

## NOT VERIFIED
- The cited S213 JSON is absent; its fields and figures were not remeasured.
- No real archive throughput, full-day distribution, or real-run count was tested.
- No operating-system crash or power-loss recovery was tested; interruption was
  a constructed fsync exception. FIX 1b (A1(g)) removes the temp file on any
  caught failure, but an uncatchable crash (e.g. SIGKILL) between the write and
  the removal could still leave one behind; that path is not exercised.
- No external independent verifier has accepted this candidate yet.
- No git commit or deployment was performed.

## REAL RUN 1 -- 2026-09-22 MLB served games (orchestrator, host, 2026-09-24 2026-09-24T22:52:31)Z

Artifact: docs/evidence/forward/latency/2026-09-22_mlb_event_latency_census.json (150644 bytes). Inputs (path, bytes): 2026-09-22_maker_forward.json 849; 2026-09-22.jsonl 359982871; 2026-09-23.jsonl 163193337; 2026-09-22.jsonl 8369460; 2026-09-23.jsonl 12567521.
Schedule docs/evidence/forward/schedules/2026-09-22_maker_forward.json (3 served games: TORBAL 824785, MILPHI 823412, MIACHC 824624).
Stream diagnostics: kalshi {"accepted": 4980, "lines": 308200, "skipped_type:trade": 213683, "skipped_type:trade_backfill_closed": 14763, "skipped_type:trade_gap": 396, "unserved": 74378}; state {"accepted": 4290, "invalid_inning": 939, "invalid_pitcher_id": 939, "invalid_score": 939, "lines": 25384, "state_changed_False": 3240, "state_changed_None": 3, "state_changed_True": 1047, "unserved": 21094}.
Events: 159 rows over 3 games. Per type (status / n_events / n_games / n_no_update_300s / n_shared_update / lag_state_to_book median and p90 in integer microseconds):
- inning: INSUFFICIENT / 89 / 3 / 34 / 38 / 77554306 and 154813937
- pitcher_id: INSUFFICIENT / 49 / 3 / 20 / 19 / 16926644 and 84951688
- score: INSUFFICIENT / 16 / 3 / 7 / 3 / 88347838 and 287479002
- status: INSUFFICIENT / 5 / 3 / 4 / 1 / 66173891 and 66173891
Every interval is INSUFFICIENT, as the spec predicted for 3 clusters (< 5); the bootstrap CI is null by construction. Counts only: no price comparison, no model, no probability (the artifact notice). Durations are integer microseconds despite the _s key suffix (duration_unit field).
NOT VERIFIED here: the hand recompute of two events against the raw shards (owed to a later session); the 2026-09-24 served games are not yet settled so no second corpus exists.
