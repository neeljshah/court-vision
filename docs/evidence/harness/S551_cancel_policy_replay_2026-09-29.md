# S551 -- offline causal cancel-policy replay + sealed preregistration (build memo, 2026-09-29)

Status: BUILT on the worktree, FIX ROUND 1a (AMENDMENT 2) applied, per-file tests green, NOT independently
re-verified. PAPER / ARCHIVE-READ ONLY;
execution-quality and calibration wording only (cents per contract, fill rate, quote uptime, adverse tail).
Spec: docs/evidence/tracking/specs/S551_spec.md INCLUDING AMENDMENT 1 and AMENDMENT 2; AMENDMENT 1 makes
docs/evidence/harness/exec2/prebuild/S551_prebuild_opus.md (B1-B6, N1-N9, "Minimal v1 scope") binding.

## BINDING BEFORE-CONDITION (re-run this session, quoted)

(a) `grep -n "pull(\|cancel" fill_realism.py fill_realism_night.py forward_replay_qualification.py`:

```
fill_realism.py:23:  'quote_cancel_ts_invalid replacement_refused duplicate_trade_ids unscored_prints '
fill_realism.py:169:                if old['cancel_ts'] > at:
fill_realism.py:170:                    old['cancel_ts'] = at
fill_realism.py:180:                     cancel_ts=min(at+int(ttl*NS), int((stamp(row['close_time'])-origin)*NS)),
fill_realism.py:217:            active = q['submit_ts'] < t.ts < q['cancel_ts']
fill_realism.py:220:            reason = ('outside_quote_life' if not q['submit_ts'] < t.ts < q['cancel_ts'] else
fill_realism.py:234:        quote_life_expiry=sum(filled[q['quote_id']] < 1 and q['cancel_ts'] == ...
fill_realism.py:236:        unmodelled_cancel_rejection='UNMODELLED', markout_by_class=marks)
fill_realism.py:268:                assumptions={'requested_units': 1, 'submit_latency_s': 0, 'cancel_latency_s': 0,
```

The decision-bearing lines are still only :169-170 (unconditional replace at every new book row) and :180 (TTL);
the other hits are life-window checks, counters and assumptions, none reads a price move. The spec's "only
:169-170 and :180" is therefore true of DECISIONS, not of every grep hit (disclosed).
(b) forward_replay.py:108-110 `if row.get("state_changed") is True: changes[game] = at; policy.pull(game)`;
`grep -n "best_bid\|best_ask\|touch" forward_replay.py forward_replay_policy.py` -> only :27, :61, :146-150,
:175, :232 (quote construction and touch-size bookkeeping), never a cancel. Correction stands: a state-receipt
cancel exists as ONE fixed policy; no book-driven cancel and no arm-versus-arm comparison exist.
(c) exec2_audit_r2_2026-09-22_2026-09-29.json: source_receipt_lag_s {p10 12.977, p50 21.388, p90 33.54};
mlb ev_play|before_receipt {mean 0.5041, ci90 [0.4448, 0.5549], games 10, n 982}; ctl|before_matched_lag
{mean 0.4289, ci90 [0.3907, 0.4649], games 10, n 1203}.
(d)/(e) not re-measured here; the risk-gate test re-runs the import closure in a fresh process (below).
Before: `ls tests/platformkit/execution | grep -c s551` printed 0 at the spec; it prints 3 now.

## What was built (v1 scope, AMENDMENT 1)

Five pre-authorised modules under scripts/platformkit/execution/, each <= 300 LOC:
- exec_cancel_policy.py -- `decide(resting, book_obs, state_obs, params)`, pure; arms static_touch (baseline),
  cancel_on_book_move, cancel_on_state_receipt. static_engine and both are DEFERRED to a v2 prereg.
- exec_policy_replay.py -- integer-microsecond clock, equal-receipt batches, shared eligibility (N6),
  phase 1 (decisions from observations only), phase 2 = ONE simulate_fills call per (arm, scenario, game) (B3),
  tape completeness (B6).
- exec_policy_prereg.py -- build / --write / --check of PREREG_S551.json, canonical seal, attest-based first
  commit, D_seal and the first eligible date (D_seal + 1 day).
- exec_policy_stats.py -- fees + marks per fill, per-game sufficient statistics, paired 5,000-draw seed-7
  game bootstrap, Holm over the family of 4, symmetric decision rule (B5), floor 30 PAIRED games (B4).
- exec_policy_report.py -- CLI, S550 streaming loaders, S550 census, cumulative pooling of prior sidecars (B1),
  append-only ledger, atomic receipt, exits 0/2/3/4/5.
The sealed PREREG_S551.json is NOT created on the real path (orchestrator commits it alone after landing);
a test-only prereg is committed in tmp git repos inside the tests, and its canonical bytes are pinned in
tests/platformkit/execution/fixtures/s551_prereg_fixture.json (sha256 in s551_seal.json).

## Decisions the spec left open (each chosen, stated here)

1. S550 landed loader names (open question 1): there is no `iter_book_rows` / `iter_state_rows` /
   `iter_trade_rows` / `census_games`. Imported by their LANDED names: exec_quality_audit_io.stream (books,
   byte-prefiltered, RSS-checked every 10,000 lines), .load_state, .load_schedule; exec_quality_audit.events_for
   (in-game window) and .game_record (census status ladder) fed by exec_quality_audit_pool.parse_snapshot /
   parse_trade over the same streamed rows (one pass, nothing re-parses a shard).
2. Touch source: capture rows carry a separately requested, lagging `raw_market`; with it, 55 of 74 fixture
   snapshots refuse `inconsistent_touch`. The replay strips `raw_market` before the three adapters, exactly as
   landed live_shadow_quoter.py:125 does; the touch then comes from the row's own top-of-book + orderbook.
3. Refresh = cancel (end t + C) plus a same-instant resubmit at the own touch carrying `replaces`; after an
   `opposite_touch_reached` cancel the book-move arm also rejoins the touch at the same instant (C <= S keeps
   arrival >= previous end). Any new order's arrival is never earlier than the previous order's end (N4).
4. Eligible seconds per side = sum over eligible grid instants of min(gap to next grid instant, 10 s); quote
   uptime = each order's [arrival, end) credited only inside its side's eligible spans [t, t + min(gap, 10 s))
   (the same > 10 s gap cap, AMENDMENT 2 item 6), over eligible seconds, so uptime is in [0, 1] (fills do not
   shorten it). Orders on one (game, side) never overlap (N4), so quoted <= eligible per side.
5. Tape completeness (B6): no drain watermark at all = PROVISIONAL (the unmodified S550 fixture is PROVISIONAL);
   an unparseable watermark or gap time is counted and makes the game PROVISIONAL, never complete.
6. `verdict_look` = CONFIRMATORY only for a scored receipt that first reaches the floor in every cell with no
   earlier CONFIRMATORY receipt; every other receipt (INSUFFICIENT included) is DESCRIPTIVE.
7. Latencies: S and C must be finite, in (0, 600] s, and C <= S (exit 2); scored mode refuses any latency other
   than the sealed 6.0 / 6.0 (sensitivity reruns deferred; the plumbing is exploratory-only).
8. Fees: simulate_fills' cumulative-ceiling increment per fill is used as given (0 on later slices of one order
   is legitimate); a negative or non-finite fee is refused `fee_invalid`. Game mean = (sum(qty x gross) -
   sum(fee_units)) / sum(qty) in cents (N5); gross comes from markout_strict with fee 0 and the fee is
   subtracted exactly once; the per-fill 10th percentile is contract-weighted.
9. Reused real rows: the orchestrator override replaces the spec's s551_real/ slice with the LANDED S550
   fixture (read-only); a tape-complete variant appends one trade_backfill_closed row in tmp_path. The
   .gitattributes line for s551_real/** is added as specified although no such directory exists.

## Fix round 1a (AMENDMENT 2; both Opus tiers REJECT r1)

1. Older-snapshot queue: a row that to_quote_book accepts and to_fill_snapshot refuses is counted
   `fill_snapshot_refused`; the quote still decides at that instant and phase 2 passes a level-less snapshot
   {ticker, ts, yes: [], no: []} for it, so tape_fill_sim._queue returns the UNKNOWN sentinel instead of an older
   decision instant's queue. Refused mark ticks are counted `mark_tick_refused`. Both counters are zero-initialised
   in every receipt. Construct test = the verifiers' probe (duplicated level, conflicting sizes): the later quote
   does not fill at the touch under displayed_depletion; the earlier valid snapshot still reads queue "5".
2. Non-tautology: the case-27 oracle now also re-derives, without any S551 module, the per-fill fee
   (venue_fees.fee_kalshi_maker cumulative increments, compared with simulate_fills' fee_units), the fill rate,
   and the +60 s fee-inclusive contract-weighted mean and missing share (to_mark_tick + resolve_marks +
   markout_strict called directly), and compares them with the pinned static_touch|through_only cell. Construct
   pins on hand-computed inputs: game_cell / primary / summarize on the 49c two-slice example (0.5 + 0.5 fills,
   fee 0.01, YES mid 0.52: +2.00 per contract long YES, -2.00 on the NO bid; per-fill 1 / 3 and -3 / -1), a
   missing mark (mark_no_tick_in_window, missing share 0.5, MARKS_INCOMPLETE), primary None with no marked
   contract, and wquantile.
3. Exclusions: `pair_no_fill` (an arm has no fill in the game) and `pair_no_mark60` (both arms fill, an arm has
   no +60 s mark) are counted separately and both receipted in every comparison.
4. Tape-trigger power: case 21 now shifts every injected trade's receipt (+17 s plus 0-60 s) as well as its
   created time, and asserts that every arm's exact cancel (instant, reason) list and quote list equal a tape-free
   reference phase 1 on books + state only (which has >= 1 state_receipt cancel). Mutants M2a / M2b die.
5. Holm BEHIND: case 31 adds a family where one cell's unadjusted p_behind (0.018396) is below 0.05 and its Holm
   p_behind (x 4) is not: the verdict is NULL. Mutant M8 dies.
6. Uptime: see decision 4; a construct test with a 30 s capture gap asserts the 15-35 s gap is not credited and
   uptime <= 1.
7. Memory (exploratory 2026-09-24 real day, adversarial verifier's measurement): peak RSS 335.8 MiB for one day
   (import baseline 24 MiB). load_day holds every served ticker's rows for D and D+1 at once, about 78 MiB per
   served game, so a day with >= 5 served games exits 5 with no receipt (fail-closed, not silent); priors read only
   the small sidecars, so there is no multi-day growth. Window end: the submit window ends at the final-row
   receipt (or the last state row when no final row exists); it is derived from the whole day's state rows, is the
   same for every arm and only trims submissions at the tail; case 20 passes that full-data window to its
   truncated runs.
s551_expected.json was regenerated only through the fixed code. Cells that changed: quote_uptime of
static_touch (0.937160 -> 0.930953) and cancel_on_book_move (0.955346 -> 0.949139) in both scenarios, in both
`cells` and `cells_including_provisional`, and the matching per-game quoted_us (729906208 -> 725071812 and
744070848 -> 739236452), all from item 6; new keys `pair_no_mark60` = 0 in the four comparisons (item 3) and
`fill_snapshot_refused` = 0, `mark_tick_refused` = 0 in refusals (item 1). cancel_on_state_receipt uptime, every
fill, markout, fee, fill rate and verdict are unchanged.

## Case map (v1: n = 29 = the spec's 31 minus cases 22 and 24; bar 29 of 29)

test_s551_cancel_policy.py: cases 1-8 + state-arm semantics + sealed parameters.
test_s551_replay.py: 9 (both permutations), 10, 11-14 (four boundaries through the real simulate_fills),
15 (refresh re-reads the displayed queue: fill at touch_queue with queue_ahead "3"), 16 (C > S, zero, negative,
NaN, inf; CLI exit 2), 17, 18, 19 (29.999 vs 30.0), 20 (truncation at EVERY instant of the real fixture, all
three arms), 21 (every trade row replaced: quote and cancel ledger rows identical, fill rows differ), 23 (shared
set incl. a 2/3 book where only the NO side is eligible), time contract, exit 5 (memory cap), exit 3 (prior
receipt prereg_changed / unreadable), 600 s latency bound; AMENDMENT 2: refused fill snapshot reads the
UNKNOWN queue (item 1), case 21 against a tape-free reference (item 4), uptime with a 30 s gap (item 6).
test_s551_cancel_policy.py also: game_cell / primary / summarize 49c pins, pair_no_fill vs pair_no_mark60 split,
wquantile (items 2 and 3).
test_s551_prereg_report.py: 25 (seal mismatch, body mismatch, uncommitted bytes), 26 (committer
2026-09-30T23:59:59Z -> 2026-10-01; 2026-10-01T00:00:00Z -> 2026-10-02; game_on_or_before_seal), 27-29 on the
real rows (27 = replay equals s551_expected.json AND static_touch x through_only fills equal an independent
oracle that calls make_quotes + simulate_fills directly; 28 = two fresh processes, PYTHONHASHSEED 1 and 2,
byte-equal receipts, strict JSON, second run exits 4; 29 = TAPE_MISSING game + NaN line + malformed
state_changed: counted, run continues, no NaN in output), 30, 31 (29 vs 30 paired; mixed cells; AHEAD, BEHIND,
NULL, fill ratio 0.49, Holm turns an unadjusted BEHIND into NULL), scored-mode pooling (B1: K, pooled_dates, duplicate_game_across_dates, tampered prior
sidecar exits 3), B6 completeness, risk gate (fresh-process import closure deny-list + AST scan), seal record.
ACCEPTANCE RULE of the spec (before 0 of 31, bar 31 of 31, n = 31) is superseded by AMENDMENT 1's v1 cut:
before 0 of 29, bar 29 of 29, n = 29; every case above is exercised.

## Results (this session)

- Fix round 1a: test_s551_cancel_policy.py 20 passed, test_s551_replay.py 14 passed,
  test_s551_prereg_report.py 10 passed (round 1: 17 / 12 / 10).
- Mutants (verifier's s551adv_mut.py, rerun on the fixed candidate): M1-M9 including M2a, M2b and M8 all die.
  Fix-round mutants reverting each fix (older-snapshot queue, uncounted refusal, merged exclusions, depth-clipped
  uptime, fee not subtracted) all die.
- `--help` exits 0 for both CLIs (exec_policy_report, exec_policy_prereg).
- contract_preflight --base master --spec S551_spec.md over the 12 owned files + this memo (rerun in fix round
  1a, spec copy carrying AMENDMENT 2): 0 FAIL (vocab, crlf,
  loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication all PASS).
- .gitattributes patterns added: `tests/platformkit/execution/fixtures/s551_real/** text eol=lf`,
  `tests/platformkit/execution/fixtures/s551_*.json text eol=lf`, `docs/evidence/forward/exec_policy/* text eol=lf`.
- An EXPLORATORY run on the real 2026-09-22..09-29 archive (2026-09-24 only) was made by the builder into the
  session scratchpad; it is not committed and no number from it is claimed here.

## Floor statement (B4)

The floor is 30 PAIRED games in EVERY (arm, scenario) cell. At about 1 tape-complete MLB game per day (an
estimate from the 09-22..09-29 census, not a measurement) and a single postseason, this floor is not expected
before the 2027 regular season unless capture coverage (S556) improves. Until then every receipt is INSUFFICIENT.

## MANDATORY DISCLOSURES

- S = C = 6.0 s, TTL 60.0 s and cool-down R 30.0 s are declared assumptions, never measured; 6.0 s is a
  conservative margin (decisions are already at receipt), not a modelled delay.
- Queue depth is unknown (sentinel 1,000,000) or displayed-only at the decision instant; cancellations ahead are
  ignored and the direction of that bias is unknown.
- Equal-instant rules are exact only at binary-representable instants (tape_fill_sim compares floats); the
  boundary tests use whole and half seconds and ISO strings from integer microseconds.
- The book capture cadence (~5.2 s) bounds every timing claim; the state poll is ~36 s per row on this game.
- Tape arrives late, so no arm decides from tape; tape rows reach only phase 2 and the ledger.
- The plan/register statement about existing cancels is corrected (before-condition b).
- One sport (mlb), one contiguous window; no scored game exists until after the seal commit; the development
  week 2026-09-22..09-29 is EXPLORATORY only.
- Phase 1 cannot see fills: a filled order still occupies its side until its end, and cancels of already
  filled orders are counted `cancel_after_full_fill` (N4). Arms issuing more orders pay more fee ceilings per
  contract; that is modelled from venue_fees, not measured (N5).
- The seal commit's committer date is self-asserted; push the seal commit to private/trunk the same day and
  record its sha and the remote ref (N7). Scored runs must run from a checkout that holds the seal commit.

## Inventory (generated by a script from the candidate files)

```
verification base (worktree HEAD, full): 4b9661123db7a664d6c8f3dc5fd9714e01bbca1e
candidate commit: NOT CREATED (sandbox) -> candidate vs base: NOT EQUAL is undecidable until lane_commit
owned file | LOC | bytes (LF) | sha256 (LF) | test functions
scripts/platformkit/execution/exec_cancel_policy.py | 120 | 5400 | c8fca14d5cc59bb1c8e56419777ab6cea838b9e88eef41322610dfd4c8b58805 | -
scripts/platformkit/execution/exec_policy_replay.py | 244 | 12274 | 8ffa20e41e8c487481a67f7f24cc133157b7896b0ba7ef5c7cb17177dc3264c6 | -
scripts/platformkit/execution/exec_policy_prereg.py | 178 | 8959 | a7b9c30a821dc12dbb2ac16d1e499932ca34c2c47bf8bdaa798e5ce56a752ec3 | -
scripts/platformkit/execution/exec_policy_stats.py | 245 | 12120 | 9f26e4f97bf987d071122388f64dda04385e5fda19d7559e9ea29c13dd36fb05 | -
scripts/platformkit/execution/exec_policy_report.py | 283 | 15501 | 430df7a6fb67d2cd9f9d365addd2f0da674ee4ec072388250464ba7910041419 | -
tests/platformkit/execution/test_s551_cancel_policy.py | 174 | 9404 | c16b920af8ff0087cbc1b7fe4f03e88b9440a2d80680b5f89893dbf2a7999fcc | 14
tests/platformkit/execution/test_s551_replay.py | 256 | 14439 | d20978fa8b8e3d5d1da12eec4fdf2574b0ebdffbd1fc2a40056e23fe190ba46a | 14
tests/platformkit/execution/test_s551_prereg_report.py | 300 | 19772 | e93ff20bf392aec9555b48859585ceeaf13c15f368a6787dcba2afdce9320870 | 10
tests/platformkit/execution/fixtures/s551_expected.json | 1084 | 23544 | 552acb955112bfc22e3917b8efcc08446076b544de9f211bbc4d8c09076fca4f | -
tests/platformkit/execution/fixtures/s551_prereg_fixture.json | 67 | 2646 | ca522ad9e80a0e96b2179c9de47c3eaef65000c1355f6e9c64f0df3c3d800371 | -
tests/platformkit/execution/fixtures/s551_seal.json | 32 | 3389 | 5e049fbf32514dc8bba44185c07143ef5bfa4e35c791f8fa0c407ff858bd8170 | -
.gitattributes | 43 | 2589 | 0dc09e4cd8343b33d0c366eebac8d6664db879bf98a3be5e2beda29fc0e964cf | -
reused real-row fixture (S550, read-only) | bytes | sha256
tests/platformkit/execution/fixtures/s550_real/kalshi/mlb/2026-09-24.jsonl | 1011636 | e71009c769e140d9c285dc5c2f8d6bb8f136263617cc689835c9382621f7a72a
tests/platformkit/execution/fixtures/s550_real/state/mlb/2026-09-24.jsonl | 9840 | 12a0e971380bbc7b29b6e50f21c1a0adee6b4fd5ba16907a188246f39ef94813
tests/platformkit/execution/fixtures/s550_real/schedules/2026-09-24_maker_forward.json | 237 | e28ae960e15f9be1e6ed16fde5cadc95a9f53a3d0f93c356d5fc1f56ac69b095
```

## LANDING NOTE (orchestrator, round 2)
- Verified round 2 by two Opus tiers (codex down): contract ACCEPT WITH CORRECTIONS, adversarial ACCEPT (docs/evidence/harness/exec2/verify/S551_verify_*_r2.md).
- C1: the inventory above was generated at base 4b9661123; the worktree was fast-forwarded to fb59f6fff0b2c5e51cbca9904d05607159d46728 before landing (docs/spec/ops commits only; .gitattributes now master's lines plus the 3 s551 lines). File shas of the owned modules are unchanged by the fast-forward.
- C2: forward_replay_io.py (a pinned must-not-move file) changed on master after base (S496, 27ae6b756). S551 does not import it; the seal test pins base blobs at the recorded base sha, so it stays green.
- N1 (adversarial r2, follow-up): two snapshots with the same receipt time and touch but different ladders are deduplicated first-wins (order-dependent); 0 occurrences in the fixture and on 2026-09-24.

## NOT VERIFIED

- No independent verifier has run; no commit exists (SHA: NOT CREATED (sandbox); files ready for lane_commit).
- The real sealed PREREG_S551.json path, its commit and `--check` against the real repo were never exercised
  (tests use tmp git repos only).
- Scored mode on real archive days was never run (no game can be scored before the seal).
- s551_expected.json was produced by the replay itself; for static_touch x through_only the fills, fees, fill
  rate and +60 s mean and missing share are re-derived independently; the other five arm x scenario cells (and
  the other horizons, uptime and p10) are pinned regressions, not independent checks.
- The frequency of malformed ladders (fill_snapshot_refused) in the live archive is not measured here (0 of 7073
  accepted snapshots on 2026-09-24 per the adversarial verifier).
- Prints parsed by tape_fill_adapters truncate sub-microsecond created_time digits (the S551 time contract
  refuses them only for book and state receipts).
- Gross markouts pass through markout_strict's float value (repr-exact Decimal afterwards).
- A crash between the ledger writes and the receipt leaves complete ledger lines and no receipt; a rerun
  exits 4 until the partial ledger is inspected and moved (no automatic recovery path is tested).
- Python 3.12 (RunPod) was not exercised; built and tested on 3.10.
- The two-days-per-date as-of cutoff (start of D+2 UTC) and multi-sport schedules were exercised only on
  construct and fixture rows.
