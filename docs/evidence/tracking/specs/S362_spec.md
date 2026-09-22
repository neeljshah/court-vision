GAP S362 | sport all captured (maker channel) | worktree harness-h20 (master-based) | log cx_s362_forward_replay_harness
# Forward maker-replay harness over the LOCAL capture archives: one chronological event loop wiring the four landed components

SINGLE PROBLEM: the quote engine (S342), tape-supported fills (S344 + S357 replay_units), the position ledger with worst-case
caps (S345 + S357) and the causal markout (S343 + S354 + S356) are landed but nothing connects them, and the historical July tape
did not qualify for a replay (ledger 2026-09-21: 0 events pass book cadence). The rebuilt capture (S341: books with touch sizes,
full trade tape, trade_gap records; S352 / S358: live state) is the only data a replay can honestly run on.

BINDING BEFORE-CONDITION (re-run, quote): `ls scripts/platformkit/execution/forward_replay.py` fails.

CHANGE (NEW files only; edit no landed module; PREPARE ONLY -- no real archive is read by the builder):
1. scripts/platformkit/execution/forward_replay_io.py (<= 300 LOC): streaming readers for the S341 archive
   (data/cache/ingame_books_local/kalshi/<sport>/<date>.jsonl: record_type snapshot / snapshot_bulk / trade / trade_gap) and the
   state archive (.../state/<sport>/<date>.jsonl); one merged chronological iterator keyed by AVAILABILITY time = response_end_ts
   (a record is visible to the policy only at or after that time; trades are additionally ordered by venue time for the fill
   simulator). trade_gap intervals are surfaced as events.
2. scripts/platformkit/execution/forward_replay.py (<= 300 LOC): `run(events, policy_params, fill_params, caps, horizons)` --
   for each book snapshot of a quoted ticker: build the quote_engine inputs from the OBSERVED book only (anchor = observed mid,
   touch sizes from raw_market yes_bid_size_fp / yes_ask_size_fp as displayed queue), call make_quotes, turn the result into quote
   events with a short lifetime (submit delay, cancel delay, expiry independent of new snapshots, all from fill_params); feed
   quotes + prints to tape_fill_sim in venue time; convert fills through replay_units; append to the position ledger; consult
   check_caps (worst-case, resting orders included) BEFORE every new quote; resolve marks with markout_causal on later snapshots
   of the SAME ticker. HARD RULES: no quote while a trade_gap covers the present or while the book is stale; a fill whose
   markout window overlaps a trade_gap or a capture gap is flagged gap_overlapped and excluded from scored sets with a count;
   state-change pulls are used ONLY when a state row is available by availability time, otherwise the run is labelled
   BOOK_ONLY_ABLATION in its output; settlement is never a mark; every abstention and exclusion is counted by reason.
   TWO MODES: `--qualify` (SCORE-BLIND: counts only -- per game and ticker snapshot cadence, print coverage, touch-size
   availability, gap overlap, state availability, number of quote opportunities; reads no price value beyond what is needed to
   count a valid two-sided book) and `--score`, which REFUSES to run without a sealed, committed prereg and a charge row, reusing
   the S359 runner pattern (scripts/platformkit/ingame/s359_four_arm_trial.py if present on master at build time; otherwise
   mirror scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py) -- in THIS row the score path is wired and tested on
   synthetic data only.
3. tests/platformkit/execution/test_forward_replay.py: synthetic archive -> no look-ahead (a snapshot stamped later is invisible
   earlier), quotes never cross, no quote inside a trade_gap, fills only from prints after arrival, caps refuse the second
   resting order, fractional fill flows to the ledger and the markout, gap_overlapped exclusion counted, BOOK_ONLY_ABLATION label,
   `--qualify` computes no markout (monkeypatch markout to raise), `--score` refuses without prereg + charge.
4. Memo docs/evidence/harness/S362_forward_replay_harness_2026-09-21.md incl. the finisher qualify command and a NOT VERIFIED list.

CONTROLS: no parameter is fitted; defaults are declared design assumptions with their source line. ACCEPTANCE: per-file test
passes; `--help` works; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble
retracted-figure literals from single digits. The pod is OFF.

AMENDMENT 1 (2026-09-21 evening; binding; REBUILD on a fresh master-based worktree harness-h39 -- the first candidate was REJECTED by
the verifier on four blocking findings and is discarded, not patched). Landed since the first build and now MANDATORY interfaces:
scripts/platformkit/execution/capture_book_adapter.py (row S373), quote_reservation.py (row S372), family_week_ledger.py (row S365),
fee_time_certification.py (row S364). In flight (do not depend on behaviour they remove; their public call shapes do not change):
S369 markout identity / first-tick rule, S370 fill-simulator fee validation before mutation, S371 one immutable declaration per
order id + short-write repair, S378 fee certification gate.
R1 CANONICAL LEDGER ONLY. Any scoring entry point resolves the ledger with the landed canonical-path helper used by
   scripts/platformkit/ingame (read backtest_runner._charge_ledger and the guard the four-arm runner uses; quote them) and refuses
   every caller-supplied ledger path, an absent ledger and an empty ledger. This row ships QUALIFICATION ONLY: `--qualify` computes
   counts and NO loss, fill-rate, markout or fee-netted number; a `--score` flag must not exist in this row at all.
R2 BOOKS ONLY THROUGH THE ADAPTER. Snapshots reach the policy exclusively through capture_book_adapter; forward_replay_io never
   reads a price or size key itself. The first test feeds the tracked real fixture
   tests/platformkit/execution/fixtures/s341_real_snapshots_2026-09-21.jsonl end to end (adapter -> quote engine -> reservation ->
   fill simulator with tests/platformkit/execution/fixtures/s341_real_trades_2026-09-21.jsonl -> position ledger -> causal markout
   inputs) and asserts a non-zero count of quotes considered; adapter refusals are counted by reason, never silently skipped.
R3 ROOM ONLY FROM A RESERVATION. Per-side room comes from quote_reservation against the position-ledger snapshot; a quote is
   submitted only under a live reservation bound to that snapshot digest; stale or expired reservations abstain and are counted.
   No caller-authored room, limit or cap shortcut exists anywhere in the row.
R4 ORDER IDS: UTC day + caller-supplied run nonce + monotonic counter; a nonce already present in the target ledger is refused;
   replaying the same input with a new nonce yields disjoint ids and identical counts.
R5 TIME: availability time = the capture's response_end receipt; every event is ordered by availability time with a deterministic
   tie-break; nothing stamped later than the decision time is visible (test: appending later records changes no earlier decision);
   fills use venue time through the landed simulator; marks use markout_causal only. Parse times only with venue_time.parse_venue_time.
R6 The qualification output lists, per game: snapshots seen / converted / refused by reason, reservation grants / refusals,
   quotes considered, book-cadence and state-age distributions as COUNTS in fixed buckets, and the qualification verdict against the
   cadence limits already stated in this spec. Strict-int counts; Decimal quantities end to end; order-independent; every except
   clause counts or re-raises. Files owned: forward_replay.py, forward_replay_io.py (+ one more NEW module if the 300-line cap
   needs it), tests/platformkit/execution/test_forward_replay.py, the memo. Edit no landed module.

AMENDMENT 2 (2026-09-21 23:0xZ; binding; FROZEN BARS under contract Q3 -- written and committed BEFORE any forward game has been
examined; they never move afterwards, in either direction). Source: astra design lane (Temp/cx_astra_qualify_out.md, archived in
docs/evidence/harness/ASTRA_QUALIFICATION_RULE_2026-09-21.md). Thresholds are inclusive. Qualification is score-blind: it reads no
outcome, no fill, no mark.
Q-1 PER DECISION at availability time t: book receipt age <= 5 s and state receipt age <= 15 s, both non-negative, measured on
    response_end receipts; future records are invisible; exact game linkage; an adapter-accepted two-sided book with touch sizes;
    live state; a valid reservation. A refused snapshot never refreshes the book timestamp. Any failure = abstain + increment every
    applicable reason count. A book-only ablation cannot qualify.
Q-2 PER GAME: one prospectively selected canonical ticker; the fixed observation window [scheduled_start, scheduled_start + 3600 s).
    The denominator is all 3600 wall-clock seconds -- stoppages, missing capture and delayed starts included; never trimmed to the
    records available. A qualified decision covers time from its receipt until the earliest of: the next decision, book freshness
    expiry, state freshness expiry, reservation expiry, observed invalidation, window end; overlapping intervals merge; duplicate
    records add neither decisions nor coverage. REQUIRE covered time >= 90 percent of the window AND >= 480 qualified decisions on
    distinct accepted book receipts. [ORCHESTRATOR DECISION, made before any forward game was examined: the design lane proposed 95
    percent and 600 decisions and itself flagged 95 as the number most likely to be regretted; the landed adapter refuses about 4 to
    5 percent of production snapshots as inconsistent touches BY CONSTRUCTION (two-call timing), and each refusal leaves 5 s
    uncovered, so a 95 percent bar would be failed by the refusal mechanism alone rather than by capture quality. 90 / 480 leaves
    about 5 percent for real gaps. This is recorded so that the choice is visible; it is now frozen.]
    Book receipt gaps (between usable receipts, including the uncovered leading and trailing boundaries; an absent stream is one
    3600 s gap; nearest-rank quantiles): median <= 45 s, p95 <= 90 s, maximum <= 120 s. Maximum state receipt gap <= 30 s.
    Any positive-duration overlap with a declared trade_gap or host_gap DISQUALIFIES THE GAME (excluding the window would let an
    informative outage improve coverage by shrinking the denominator). Trade pagination must have closed through the window's
    closing watermark; unresolved completeness disqualifies; a quiet tape is valid. A game with zero fills QUALIFIES when the
    above holds; it counts toward coverage and game totals and contributes no fill-conditional measurement. Mark availability does
    not affect game qualification; later authorized analysis qualifies the 30 / 120 / 300 s horizons independently using the first
    same-ticker observation in [fill + h, fill + h + 30 s].
Q-3 PER SPORT-WEEK: >= 4 distinct qualified games per frozen sport / family stratum per complete ISO week (Monday 00:00 UTC to the
    next Monday), assigned by scheduled start; fewer than 4 breaks that family's streak; no pooling across sports, no stitching of
    missing weeks. The separate floors stand: 30 qualified games per sport, and 30 fill-bearing games before any interval is read.
Q-4 A FAILED game publishes FAIL, strict-int diagnostic counts, covered / total milliseconds and every applicable reason code from
    the closed set {BOOK_STALE, STATE_STALE, ADAPTER_REFUSED, LINKAGE_INVALID, NOT_LIVE, RESERVATION_INVALID, COVERAGE_LOW,
    DECISIONS_LOW, BOOK_CADENCE, STATE_GAP, TRADE_GAP, HOST_GAP, TAPE_INCOMPLETE}; it computes no loss, fill rate, markout or
    fee-netted figure, and it stays in the scheduled denominators.
Q-5 If this bar proves unmeetable, the remedy is a better capture, never a moved bar: the row is CLOSED AT LIMIT under Q3.

AMENDMENT 3 (2026-09-21; binding; scope and interface clarifications after the rebuild's first verifier round). (a) Owned files
for the rebuild: forward_replay.py, forward_replay_io.py, forward_replay_policy.py, forward_replay_qualification.py (four
production modules, each <= 300 LOC), tests/platformkit/execution/test_forward_replay.py and test_forward_replay_qualification.py,
the memo. No further file. (b) Q-1 / Q-2 FAIL CLOSED: without a non-empty prospective schedule, a selected canonical ticker and a
fresh linked live state, no quote is ever considered -- the game is FAIL with NOT_LIVE / LINKAGE_INVALID, and a book-only ablation
is a labelled diagnostic that never qualifies and never submits. (c) R2 means NO candidate line reads any book price or size key:
validity, two-sidedness and touch availability come only from capture_book_adapter outputs. (d) Quantities (max order quantity,
quote quantity, fill quantity, inventory) are finite Decimal end to end; strict ints are for diagnostic counts only. (e) Nonce
uniqueness is checked against ONE authoritative registry that outlives a run (the target position ledger's recorded order ids,
read through the landed position_ledger API), never against caller-supplied event lists. (f) Completed-week validation and streak
computation delegate to the landed family_week_ledger.FamilyWeekLedger; no parallel implementation. (g) The first fixture test
must traverse the WHOLE chain on the tracked real fixtures: a post-arrival fixture print that crosses a submitted quote produces
>= 1 tape-supported fill, >= 1 ledger fill event and >= 1 causal-markout input row; counts asserted > 0.

