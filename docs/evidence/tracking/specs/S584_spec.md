GAP S584 | sport mlb (live shadow midnight) | worktree aN (assigned at dispatch; Opus build, two Opus verify tiers, codex down) | log cx_s584_live_shadow_midnight
# Each UTC day's live shadow receipt is self-contained: the recorder writes a continuation run row at the head of every new day shard it writes to (same nonce, same identity), the shard key is the exact UTC day of t_epoch, and the receipt owns a quote by its DECISION day, so every quote side is owned by exactly one receipt and D's receipt already reads enough of D+1 to finish it
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B1-B10, Q1-Q9 (S-row) -- self-check every line. Template: CODEX_SPEC_TEMPLATE.md, both S-row adjustments. Sources: fault case 36 (S581, worktree nba-harness-h250, scripts/platformkit/ops/system_fault_cases_ops2_b.py:179-247); S515_spec.md items 8, 9 + AMENDMENTS 1-4; S516_spec.md item T (:9), B1b (:32), B3c (:46), AMENDMENTS 1-4; S516 memo; LIVE_PAPER_BETTING_PLAN_2026-09-29.md. Citations re-read against master 1a96f54e6; h250's live_shadow* modules are byte-identical to master (git diff empty). RE-READ AT DISPATCH.
WHERE THIS ROW RUNS: construct tests only (tmp_path roots, injected clock/sleep/free-RAM, no network, no data/ read, no real-row fixture, no .gitattributes change). Probes, if any, stream line by line and self-exit past 400 MB RSS. The first real post-midnight receipt is ORCHESTRATOR-run after landing. Per-file pytest only.

SINGLE PROBLEM (verified): live_shadow_cli.py:85-99 builds the kind 'run' row and writes it ONCE (`writer.append([run_row], first_t)` :92) into the shard of first_t; Writer.append (live_shadow_io.py:172) names the shard per call from t (`days_at(t, (0,))` :174, path :175), so after UTC midnight a still-running process writes arm rows into <D+1>.jsonl with no run row there. The D+1 receipt reads shadow shards D+1 and D+2 only (live_shadow_fills_io.py:162); pass 1 (`_runs`, live_shadow_fills.py:57-79) finds no run row for the nonce and every arm row raises run_row_missing (:143-144; S516 B1b :32). Separately, ownership is `owned = 0 <= t+submit_ns < 86400*NS` (:176, S516 item T): a quote decided in [D+1 - 2 s, D+1) sits in shard D but starts on D+1, so D does not own it and D+1 never reads shard D -- owned by no receipt, no counter. Third: refusals of D+1 rows that D reads as lookahead are counted and listed in refused_quote_ids by BOTH receipts (:213-220 are not gated by ownership). Fourth: days_at uses datetime.fromtimestamp, which rounds to the microsecond, so t = 1790380799.9999998 (23:59:59.9999998Z on 09-25) lands in the 09-26 shard while its t_epoch is on 09-25 (measured this session). The owner launcher (docs/operations/relaunch_live_shadow_2026-09-29.ps1, untracked, read-only) runs `--every-s 15 --until 2099-01-01T00:00:00Z` under a supervisor, and MLB night games cross UTC midnight.
BINDING BEFORE-CONDITION (ran this session, h250 3d97455be): `cd /c/Users/neelj/nba-harness-h250 && python -m scripts.platformkit.ops.system_fault_matrix --root C:/Users/neelj/nba-harness-h250/data/cache/fault_matrix/s584_spec_1 --case 36` -> "36 | shadow_state_gap | DEFECT | ... midnight: arm rows D=18 D+1=14, run rows per day [('2026-09-29', 1), ('2026-09-30', 0)], row_ids unique=True ...; receipt D FINAL/None refusals {'p0_ignored': 1}; receipt D+1 PROVISIONAL/no_intervals refusals {'books_prefiltered': 7, 'run_row_missing': 14, 'shard_missing': 2}; quote sides in no receipt: D+1 file 28/28, D file 4/36." / "SUMMARY PASS=0 DEFECT=1 ERROR=0". (The 4/36 are the 23:59:59Z tick's two arms x two sides.)

CONSOLIDATED CONTRACT (supersedes S516 item T's "START instant" ownership and B1b's ownership clause; the simulated start instant stays submit + S exactly as landed):
 O1 SHARD KEY: the writer names the shard from floor(t) (math.floor on the same float t that decide stamps as t_epoch = str(t); floor(float) == floor(Decimal(str(t))) because repr round-trips), so every row in <D>.jsonl has Decimal(t_epoch) in [D 00:00:00, D+1 00:00:00). 23:59:59.9999998Z -> shard D (today: D+1); 00:00:00.000000Z -> D+1.
 O2 CONTINUATION RUN ROW: the Writer remembers the first durably written kind 'run' row (unstamped content, its row_id, and the set run_days = {its shard day}). Before the first row it writes into a shard whose day is not in run_days, it writes one continuation row = the original content + `continues_row_id` = the ORIGINAL run row's row_id (same run_nonce, argv, every_s, tail_bytes, freshness_bars, sha256, inventory_policy, ignored_dimensions; own row_id/emitted_ts/seq), os.write + os.fsync complete BEFORE any arm/p0 row of that call is written; then adds the day to run_days and counts `run_continuations`. Failure (short write, OSError, fsync error): repair per _repair, count write_errors and `run_continuation_errors`, write NO row to that shard this call and return [] (open intents lapse by expiry; the next append retries). Invariant: no arm or p0 row of a nonce precedes that nonce's run row in any shard. A clock step back into a day already in run_days writes no second continuation. Idle and low-RAM ticks write nothing, so a day with no rows gets no continuation.
 O3 OWNERSHIP: receipt D owns an arm row iff 0 <= (Decimal(t_epoch) - origin_D) * NS < 86400 * NS (decision instant, half-open); by O1 these are exactly the arm rows of shard D, read in full (index 0 never stops early, fills_io.py:86). Rows with t >= D+1 (the D+1 lookahead, fills_io.py:70-92) only close D intervals: never an interval, never n_rows, never refused_quote_ids; any refusal they raise after t is parsed is counted ONCE as `diag:unowned_refused`. Owned rows keep every existing refusal name and listing. Rows refused before t parses (identity_invalid, time_not_exact, emitted_invalid, future_records) have no owning day and stay counted by reason in each receipt that reads them (disclosed; they can never be an interval or a listed side id).
 O4 D READS ENOUGH: a D-owned quote has t < D+1 and expires_at = t + 2*every_s; its end is the earliest of the next same-group row, expiry, a later live nonce's first arm row (S516 item 3), all of which lie before D+1 00:10:00 whenever every_s <= 600 (launcher: 15) because the next tick is at most every_s later and a skipped tick is bounded by expiry; shadow_rows reads D+1 while any group's expiry exceeds the newest t (fills_io.py:86); trades, marks and drains come from books D and D+1 (fills_io.py:174). every_s > 600 is disclosed as unproven, not changed.
 O5 RUN CLASSIFICATION: `_runs` counts a same-mode run row carrying a non-empty str `continues_row_id` as `diag:run_continuation` (not diag:duplicate_run); a same-mode row without it stays diag:duplicate_run; a mode conflict stays refused duplicate_run. Receipt assumptions key `start_ownership` is replaced by `ownership: 'decision_instant_utc_day'` (fills_io.py:201).
 BOUNDARY TABLE (live run, S = 2 s, every_s 15; D = 2026-09-25): decided 23:59:57.999999Z -> shard D, owned D (start 23:59:59.999999, both rules agree); 23:59:58.000000Z -> owned D (old rule: nobody); 23:59:59.999999Z -> owned D, live_start = emitted + 2 s on D+1, closed by the 00:00:14.999999Z row read from shard D+1, and a through print at 00:00:05Z in books D+1 fills it in D's receipt; 00:00:00.000000Z -> shard D+1, owned D+1, and in D's receipt it only closes the open 23:59:45 quote at 00:00:00; run started 23:59:59Z -> run row + first tick in D, continuation then arm rows in D+1 at 00:00:14Z, both receipts 0 run_row_missing; one process across two midnights -> continuations in D+1 and D+2, both carrying the D run row's row_id, each receipt self-contained; restart after midnight (A's last row 23:59:50Z in D, B's run row and rows from 00:02:00Z in D+1, new nonce) -> D owns A's rows ending at expiry 00:00:20Z (B's first arm row is later), D+1 owns B's, 0 run_row_missing; A killed at 00:00:30Z after its D+1 continuation -> A's D+1 rows owned by D+1 and closed by B's first arm row. EXACTLY ONCE: over receipts D and D+1, every yes/no quote side id in both shards appears in exactly one of (live or replay intervals, refused_quote_ids) -- never two, never zero.

CHANGE (OWNED; LOC measured on master: live_shadow_io.py 253, live_shadow_fills.py 260, live_shadow_fills_io.py 278; each stays <= 300; no companion module needed. live_shadow_cli.py is NOT modified):
1. scripts/platformkit/execution/live_shadow_io.py (MODIFIED): Writer O1 + O2 only.
2. scripts/platformkit/execution/live_shadow_fills.py (MODIFIED): O3 (:176 and the refusal/listing paths :213-220 gated by ownership) and O5 (_runs).
3. scripts/platformkit/execution/live_shadow_fills_io.py (MODIFIED): the one assumptions label of O5. Nothing else.
4. tests/platformkit/execution/test_s584_shadow_midnight.py (NEW; the name must NOT match the S516 inventory globs `test_live_shadow_fills*.py` / `live_shadow_fills*.py`).
5. tests/platformkit/execution/test_live_shadow_fills_memo.py (MODIFIED, S501 landing lesson): test_case22_inventory keeps its case-list and <= 300 LOC assertions permanently; its memo-table byte comparison (a fixed-sha check that goes red on any later legitimate edit of live_shadow_fills*.py) runs only when env S516_MEMO_LANDING_CHECK=1. The S516 memo is NOT rewritten.
6. nba-harness-h250 (after S581 lands on master, else in the S581 tree): tests/platformkit/ops/test_system_fault_matrix.py DEFECT_ROWS drops `36: "S584"`.
7. memo docs/evidence/harness/S584_live_shadow_midnight_2026-09-29.md, inventories (case list, per-file LOC and LF sha256, test pass counts, before/after of case 36) generated by a `write_memo()` in the new test file that pytest does not call; no permanent test compares fixed shas.
MUST-NOT-MOVE: live_shadow_quoter.py, live_shadow_cli.py, live_shadow_fills_books.py, live_shadow_fills_report.py, every S515/S516 fixture, s516_seal.json, .gitattributes, the S515 and S516 memos and specs, tape_fill_sim.py and the rest of the s516_seal set (pinned there), the owner launcher. `git diff --stat` at landing shows only the owned paths.

CASES (n = 12, CONSTRUCT; enumeration exhaustive): (1) O2 writer: injected-clock live run with ticks 23:59:44, 23:59:59, 00:00:14 -> shard D [run, arms...], shard D+1 first line kind run, same run_nonce, continues_row_id == D run row_id, identity fields equal, row_id prefix D+1; exactly one run row per (nonce, shard); (2) two midnights + a clock step back -> one continuation in D+1, one in D+2, none extra in D; (3) continuation failure injected at os.write and at os.fsync -> zero rows in D+1 that tick, run_continuation_errors 1, next tick continuation then arms, no arm row before its run row in any shard; (4) O1 floor: t = 1790380799.9999998 -> shard 2026-09-25, t = 1790380800.0 -> 2026-09-26; (5) BOUNDARY TABLE ownership via reduce_rows on synthetic rows (the four decision instants, the closing row, owned set per receipt); (6) D reads enough: the 23:59:59.999999 quote fills from a D+1 books print in D's receipt, absent from D+1's; (7) lookahead refusals (emitted_late, side_price_invalid on D+1 rows) -> named refusal + refused_quote_ids in D+1 only, diag:unowned_refused 1 in D; (8) run started 23:59:59Z; (9) restart after midnight, both variants; (10) END-TO-END through the landed callers: the landed S515 CLI in a FRESH subprocess (`python -m scripts.platformkit.execution.live_shadow_quoter --replay-start 2026-09-25T23:59:29.999999Z --every-s 15 --max-ticks 4 --min-free-mb 0 ...` over construct roots; ticks 23:59:29.999999, 23:59:44.999999, 23:59:59.999999, 00:00:14.999999) and an in-process LIVE run with an injected clock (emitted_ts within 60 s) write strict JSON shards; then FRESH subprocesses run `python -m scripts.platformkit.execution.live_shadow_fills --date 2026-09-25` and `--date 2026-09-26` with --out; the test re-reads both receipts from disk: 0 run_row_missing in both, EXACTLY ONCE holds for every side id in the shards, the 23:59:59.999999 sides are in the 09-25 receipt; also a malformed (non-object) line and a torn trailing line in the D+1 shard are counted and change nothing else; (11) O5 labels: continuation -> diag:run_continuation, a plain same-mode duplicate -> diag:duplicate_run, mode conflict -> refused duplicate_run, assumptions.ownership == 'decision_instant_utc_day'; (12) S581 case 36 verdict PASS through `python -m scripts.platformkit.ops.system_fault_matrix --case 36` and the updated DEFECT_ROWS pin.
ACCEPTANCE RULE: metric = cases passing / cases enumerated; before = 0 of 12 (case 36 DEFECT above; cases 1-11 fail on master by construction: no continuation row, :176 start ownership, ungated lookahead refusals, fromtimestamp rounding); bar = 12 of 12; n = 12 (CONSTRUCT); eye check = n/a (S-row); reproduction = rerun test_s584_shadow_midnight.py alone, then the case-36 matrix command above (after-condition: "SUMMARY PASS=1 DEFECT=0 ERROR=0", D+1 file 0/N and D file 0/N sides unowned); must not move = the MUST-NOT-MOVE list. NON-TAUTOLOGY: case 10's exactly-once oracle counts side ids straight from the shard files, not from the new code.
EVIDENCE: memo with the generated inventory, the before/after case-36 lines, and the green runs of every existing file, one at a time: tests/platformkit/execution/test_live_shadow_quoter.py, test_live_shadow_io.py, test_live_shadow_cli.py, test_live_shadow_fills.py, test_live_shadow_fills_b3.py, test_live_shadow_fills_b4.py, test_live_shadow_fills_io.py, test_live_shadow_fills_memo.py, plus tests/platformkit/ops/test_system_fault_matrix.py. MANDATORY DISCLOSURES (condensing may not drop): ownership moved from start instant to decision instant (supersedes S516 item T / B1b ownership clause; the S516 case-14 oracle at test_live_shadow_fills_io.py:64 still encodes the start rule and agrees on its fixture because no replay tick falls in [23:59:58, 24:00)); a quote decided in D can fill on D+1 and is reported in D; O4 exactness holds for every_s <= 600 only; pre-ownership refusals may be counted in both receipts (never as an interval or side id); the S516 memo-table byte check is landing-gated, not deleted; continuation-write failure drops that tick's rows (intents lapse by expiry); calibration language only (Q6). NOT VERIFIED (last): no live post-midnight night, no supervised restart across midnight, no full-night RSS.
NOT IN SCOPE: the S581 case file's `expected` wording (still says start ownership; S581 owner), S517 supervision, other sports, any quoter/decide change, receipt statistics, reading real archives, writing data/registry or docs/evidence/forward.
DEPENDENCY: S515 and S516 landed (057cec920, fa99c29cd); item 6 needs S581 landed (its test file exists only in nba-harness-h250 today). TEST: per file only, never the suite. COMMIT: explicit pathspec in the worktree, no push; report the sha.
AMENDMENT 1 (PRE-BUILD) (appended verbatim by the system-test lead from s584_critic_r1.md):
AMENDMENT 1 (PRE-BUILD) -- binding; supersedes the spec text where they differ
 A1 PRE-EXISTING REDS (measured by the critic on master f21480627, per file):
    - tests/platformkit/execution/test_live_shadow_fills.py: 1 failed, 15 passed. test_case21_seal (:291-296) fails because
      forward_replay_io.py hashes b8749925... but the seal pins b2ec0afa... . The cause is S496 27ae6b756, which changed only
      _native_input; stamp and iso are untouched.
    - tests/platformkit/execution/test_live_shadow_fills_memo.py: test_case22_inventory fails at :51 because the
      .gitattributes row reads (2234, 37, fe57154c...) in the S516 memo but (3004, 50, 2e5e19f9...) now. S541, S551 and S560
      all edited .gitattributes.
    - Green on master: test_live_shadow_fills_b3 11, _b4 7, _io 5, test_live_shadow_io 31, test_live_shadow_cli 27,
      test_live_shadow_quoter 83.
    Binding: item 5 stands as written. Gate ONLY the table parse and compare (:43-51) under S516_MEMO_LANDING_CHECK=1. The
    case list (:40), the <= 300 LOC check (:41) and the header regex (:42) stay permanent.
    ADD owned item 5b: tests/platformkit/execution/test_live_shadow_fills.py (MODIFIED, currently 296 lines, must stay <= 300).
    In test_case21_seal:
      - keep `len(base_sha) == 40 and len(immutable) == 10` permanent;
      - add a permanent assert that no S584 owned path and no live_shadow*.py path appears in seal['immutable'];
      - run the digest loop only under S516_SEAL_LANDING_CHECK=1.
    Both gates are the S501 landing-lesson form: fixed-base identity checks move to landing time. That is not a B10/Q3 moved
    bar, because the 22/22 case bar and the LOC bar stay byte-identical and permanent.
    The memo records, verbatim:
      - both failing assertion lines before the change;
      - both files green after;
      - that either gate is expected RED today if enabled, for the named drift (S496, .gitattributes) and not for S584;
      - that stamp/iso are unchanged by S496 (git show 27ae6b756 touches only _native_input).
    EVIDENCE then reads "every existing file green after; the two reds above were red before, for the named causes".
 A2 O2 PRECISION (live_shadow_io.py Writer):
    (a) Write a continuation only when an original run row has been remembered. A fresh Writer appending arm or p0 rows with
        no prior run row behaves exactly as today. test_live_shadow_io.py:130-141, :207-218 and :220-240 call append on a
        fresh Writer and must stay green unedited.
    (b) Remember the original only after that call's final os.fsync succeeds; its shard day seeds run_days. The first-row
        retries at live_shadow_cli.py:90-99 remember whichever attempt succeeded.
    (c) Failure split:
        - os.write raises or writes short: _repair runs as today, which leaves a b"\n" or a terminated torn line (bad_line 1 in
          every receipt that reads it).
        - _repair itself fails: it keeps raising ValueError('unrepaired_output'), so the process exits 5 via
          live_shadow_cli.py:70-73. It does NOT return [].
        - os.fsync fails: no repair. The continuation line is present, but its day is NOT added to run_days, so the next
          append writes a second continuation.
        - Short-by-one (count == len-1): treated as a failure, as run rows are today (io.py:199). The line is complete after
          repair, so a duplicate continuation follows.
        Every failure counts write_errors and run_continuation_errors and writes no arm or p0 row that call.
    (d) Case 3 expectations, replacing "zero rows in D+1 that tick":
        - write variant: D+1 line 1 is b"\n", then continuation, then arms on the next tick;
        - fsync variant: D+1 holds a complete continuation, then a second continuation plus arms on the next tick; the D+1
          receipt shows diagnostics run_continuation 1;
        - both variants: 0 run_row_missing in either receipt, no arm or p0 row before the nonce's first run row in any shard,
          run_continuation_errors 1.
    (e) days_at (io.py:46-49) is NOT changed; load_schedules :55 and load_inputs :135 keep it. Only the Writer derives its day
        from math.floor(t) (e.g. datetime.fromtimestamp(math.floor(t), timezone.utc)).
    (f) Disclose: the first append into a new day fsyncs twice. That supersedes S515 item 8's "os.fsync once per tick per
        shard" (S515_spec.md:18) for that append only.
 A3 O3 PRECISION (live_shadow_fills.py reduce_rows):
    (a) Compute `owned = 0 <= t < 86400*NS` immediately after t parses (:126), before any later raise, and use the same
        variable at :176-181 and :211.
    (b) Unowned rows keep every shared-state side effect: pending cancels :131-133, live_nonces :145-150, seen_rows :157,
        tickers and previous :175, quote_ids :200, the pending append :210. Only counts, n_rows, events, replay_stamped_rows
        and refused_quote_ids are gated.
    (c) diag:unowned_refused counts at most ONCE PER ROW, even when both side refusals fire.
    (d) Pre-parse refusals (identity_invalid at :125 and time_not_exact at :126) KEEP today's :220 listing in every receipt
        that reads the row: listed possibly twice, never an interval. The spec's "never a listed side id" is withdrawn,
        because it would leave such side ids in zero receipts.
        A row whose t parsed but whose emitted_ts is invalid: the emitted_invalid count at :109 stays in both receipts (as the
        spec says); its side ids are listed only by the owner.
    (e) EXACTLY ONCE scope, restated: every yes/no side id of an arm row whose t_epoch parses and that is not skipped as
        future_records (:104-106, :127-130; those skip without listing, pre-existing).
    (f) NEW counter diag:prior_day_rows for arm rows with a parsed t < 0. These exist in shards written before the S584 writer
        restart: fromtimestamp rounding (io.py:48) put t in [D+1 - 0.5 us, D+1) into shard D+1. Without the counter they are
        silent in the D+1 receipt. Case 5 adds one such row to shard D+1: owned by D when D's lookahead reads it,
        prior_day_rows 1 in D+1.
    (g) O3's "by O1 these are exactly the arm rows of shard D" holds only for shards written by the new writer; say so.
 A4 O4 CORRECTION:
    - Exactness is unconditional only for every_s <= 300. There 2*every_s <= 600, so every D-owned quote expires by
      D+1 00:10:00 = cap (fills_io.py:72), and every closing row (next same-group row, or a later nonce's first arm row,
      fills.py:145-150) has t <= expiry <= cap. Such rows are read, because the stop rule fills_io.py:86 keeps reading while
      any expiry exceeds max(latest, t).
    - For 300 < every_s <= 600 the spec's argument is wrong. live_shadow_cli.py:144-145 sleeps every_s AFTER the tick's work,
      so the next tick lands at t + every_s + latency. A restart can also land after the cap. A closing row after 00:10:00Z
      is then never read, and the interval silently runs to expiry (overstated).
    - Disclosure text becomes: "exact for every_s <= 300 (launcher 15); above that a closing row after D+1 00:10:00Z is not
      read and the interval runs to expiry". No code change.
 A5 O5 / B2:
    - Do NOT remove assumptions.start_ownership: B2 forbids a removal without an alias. git grep finds it only in
      fills_io.py:201 and this spec, and docs/evidence/forward/live_shadow does not exist.
    - Emit ownership='decision_instant_utc_day' AND start_ownership='superseded_by_ownership'.
    - Case 11 asserts both.
 A6 CASE 10 FEASIBILITY:
    - The Writer stamps emitted_ts from the real time.time() (io.py:185). The in-process LIVE run must therefore patch
      scripts.platformkit.execution.live_shadow_io.time.time (monkeypatch, restored) to the injected clock plus <= 60 s.
      Otherwise every live row is refused emitted_late (fills.py:167-168).
    - Put the malformed line and the torn trailing line at the END of the D+1 shard.
    - Versus a clean twin run: the D+1 receipt gains exactly bad_line 1 and unterminated_tail 1. The D receipt's D+1 source has
      stopped_early True, and its refusals equal the clean twin's.
 A7 OPERATIONAL:
    - The live recorder (launcher --until 2099) keeps OLD code until its child process restarts.
    - Post-landing orchestrator step (NOT a builder step; recorded under NOT VERIFIED): stop the live_shadow child so the
      supervisor restarts it. Record the first UTC day whose run rows carry the landed live_shadow_io.py sha256.
    - Receipts over earlier shards still refuse run_row_missing on D+1 rows of a pre-restart process. That is disclosed, not
      repaired.
 A8 DISCLOSE t_iso:
    - live_shadow_quoter.py:36 (must-not-move) rounds t_iso to the microsecond. A row decided within 0.5 us of midnight
      therefore sits in shard D with t_iso D+1T00:00:00.000000.
    - fills.py:158 accepts it (<= 1000 ns tolerance).
    - Case 36's `placed` check uses t_iso[:10] and is unaffected on its integer-second ticks.
 A9 CASE 36 AFTER-CONDITION (critic prototype, in memory, h250 3533792c3):
    - Output: "run rows per day [('2026-09-29', 1), ('2026-09-30', 1)] ... receipt D FINAL/None refusals {'p0_ignored': 1};
      receipt D+1 FINAL/None refusals {'shard_missing': 2}; quote sides in no receipt: D+1 file 0/28, D file 0/36." /
      "SUMMARY PASS=1 DEFECT=0 ERROR=0".
    - The builder's run must match this before-to-after shift.
    - The case's `expected` text still states start ownership. That belongs to the S581 owner and is noted in the memo.
AMENDMENT 2 (2026-09-30 ~03:0xZ; round 1 = Opus CONTRACT ACCEPT WITH CORRECTIONS + Opus ADVERSARIAL ACCEPT WITH CORRECTIONS, 0 blocking; 186 kill/restart combinations of the real CLI across midnight all exactly-once; verdicts scratchpad s584_verify_contract_r1.md / s584_verify_adv_r1.md; binding for fix r1, overrides AMENDMENT 1 where they differ):
(1) PIN THE SURVIVING MUTANTS with tests (new tests may go in a NEW owned file tests/platformkit/execution/test_s584_shadow_midnight_a2.py if the main test file would pass 300 lines): (a) A2(b): the run row is remembered only after that call's final fsync succeeds (a failing fsync on the first run-row write leaves the day not done and the next append writes a fresh run row; the continuation of a later day points at the successful retry's run row); (b) a continuation write that returns short (even by one byte) is a failure: the line is repaired, nothing is glued to the next row, both error counters +1, and the next tick retries the continuation; (c) a failed repair still raises unrepaired_output (exit 5), never swallowed; (d) n_rows and replay_stamped_rows are counted only for rows the receipt owns; (e) an empty or non-str continues_row_id is refused (not accepted as a continuation).
(2) MEMO (regenerate with write_memo() from the fix-r1 candidate; base = harness-h250 HEAD): update the stale sha / line counts / matrix result (40 passed, cases 3 and 4 no longer red); disclose: a rounded prior-day row left by the OLD writer (pre-S584 shards) near midnight can be owned by no receipt (D's lookahead stops before it and D+1 counts it only as diag:prior_day_rows); a shard path over MAX_PATH fails at a mkdir outside the try (pre-existing, same length every day); the memo-table landing check (S516_MEMO_LANDING_CHECK=1) is red on S584's own required edits as well as .gitattributes (A1's "not for S584" wording does not hold for that gate).
(3) LANDING ORDER: S584 lands only after S581 (its test file imports the S581 case helpers).
