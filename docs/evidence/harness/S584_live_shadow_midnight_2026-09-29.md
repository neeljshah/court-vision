# S584 live shadow midnight -- self-contained daily receipts (2026-09-29)

Row S584 (spec docs/evidence/tracking/specs/S584_spec.md with AMENDMENTS 1 and 2). Fix round 1 candidate in worktree
nba-harness-h253 on 67529d35c (harness-h250 HEAD, S581 fault harness on top of master). S584 lands only after S581:
tests/platformkit/execution/test_s584_shadow_midnight.py imports the S581 case helpers
(scripts/platformkit/ops/system_fault_cases_shadow.py) and case 12 runs the S581 matrix. Paper only; calibration and
ops wording only.

## What changed

- O1 (live_shadow_io.py Writer): the shard day is `datetime.fromtimestamp(math.floor(t), timezone.utc)`, so every
  row in `<D>.jsonl` has Decimal(t_epoch) in [D 00:00:00, D+1 00:00:00). `days_at` is unchanged (A2e);
  load_schedules and load_inputs keep it.
- O2 (Writer): the first durably written kind 'run' row is remembered only after that call's final os.fsync (A2b);
  its shard day seeds run_days. Before the first row of a call into a day not in run_days, the Writer writes one
  continuation row = the original content + `continues_row_id` (own row_id/emitted_ts/seq), os.write + os.fsync
  before any arm/p0 row, then counts `run_continuations`. A fresh Writer with no remembered run row behaves exactly
  as before (A2a). Failure split (A2c): a raised or short os.write (short-by-one included) runs `_repair` and returns
  []; a failed `_repair` still raises `unrepaired_output` (exit 5 via live_shadow_cli.py); a failed os.fsync is not
  repaired, the line stays and the day stays out of run_days, so the next append writes a second continuation.
  Every failure counts write_errors and run_continuation_errors and writes no arm or p0 row that call.
- O3 (live_shadow_fills.py reduce_rows): `owned = 0 <= t < 86400*NS` is computed right after t parses (A3a).
  Unowned rows keep every shared-state side effect (A3b); only counts, n_rows, events, replay_stamped_rows and
  refused_quote_ids are gated. A refusal raised by an unowned row after t parses counts `diag:unowned_refused`
  once per row (A3c). Pre-parse refusals keep today's listing (A3d). New `diag:prior_day_rows` counts arm rows with
  a parsed t < 0 (A3f).
- O5: `_runs` counts a same-mode run row with a non-empty str `continues_row_id` as `diag:run_continuation`; a plain
  same-mode duplicate stays `diag:duplicate_run`; a mode conflict stays refused `duplicate_run`. Receipt assumptions
  carry `ownership='decision_instant_utc_day'` AND `start_ownership='superseded_by_ownership'` (A5, B2 alias).
- live_shadow_cli.py is NOT modified.

## Fault case 36 before and after

Before (measured at b4b6eaec2 on the pre-fix modules; the contract verifier reproduced the same lines on 67529d35c;
`python -m scripts.platformkit.ops.system_fault_matrix --root .../s584_before --case 36`):

    midnight: arm rows D=18 D+1=14, run rows per day [('2026-09-29', 1), ('2026-09-30', 0)], row_ids unique=True, post-midnight mid quotes priced off the new shard's 66/68 book (65/69) 7/7; receipt D FINAL/None refusals {'p0_ignored': 1}; receipt D+1 PROVISIONAL/no_intervals refusals {'books_prefiltered': 7, 'run_row_missing': 14, 'shard_missing': 2}; quote sides in no receipt: D+1 file 28/28, D file 4/36.
    SUMMARY PASS=0 DEFECT=1 ERROR=0

After (same command; fix-r1 rerun on 67529d35c with root .../s584_fix1_36 printed the identical lines):

    midnight: arm rows D=18 D+1=14, run rows per day [('2026-09-29', 1), ('2026-09-30', 1)], row_ids unique=True, post-midnight mid quotes priced off the new shard's 66/68 book (65/69) 7/7; receipt D FINAL/None refusals {'p0_ignored': 1}; receipt D+1 FINAL/None refusals {'shard_missing': 2}; quote sides in no receipt: D+1 file 0/28, D file 0/36.
    SUMMARY PASS=1 DEFECT=0 ERROR=0

This matches the A9 after-condition. Cases 9, 15, 16, 26, 27 and 36 run together: SUMMARY PASS=6 DEFECT=0 ERROR=0.
DEFECT_ROWS in tests/platformkit/ops/test_system_fault_matrix.py drops `36: "S584"`. The case's `expected` text still
states start ownership; that wording belongs to the S581 owner (NOT IN SCOPE).

## Cases (n = 12, CONSTRUCT)

1 continuation row; 2 two midnights plus clock step back; 3 continuation failure at os.write and at os.fsync (A2d);
4 floor shard day; 5 boundary-table ownership via reduce_rows (plus one rounded prior-day row in D+1, A3f);
6 the 23:59:59.999999 quote fills from a D+1 books print in D's receipt only; 7 lookahead refusals (emitted_late,
side_price_invalid on both sides); 8 run started 23:59:59Z; 9 restart after midnight, both variants; 10 end to end
through the landed callers in fresh processes (S515 quoter replay subprocess, in-process LIVE run with the Writer
clock patched to t + 0.2 s per A6, fills receipts as subprocesses, malformed and torn lines at the end of the D+1
shard against a clean twin); 11 O5 labels and the assumptions keys; 12 fault case 36 PASS plus the DEFECT_ROWS pin.
The exactly-once oracle counts side ids straight from the shard files (non-tautology).
Before = 0 of 12 on the pre-fix modules (measured: 14 of 15 test functions red; the one green is case 9 variant 1,
a restart with a new nonce, which is already self-contained before the fix; case 9 is red through variant 2).
After = 12 of 12.

Power check (each mutation applied alone, then restored): start-instant ownership -> cases 5, 6, 7 (both), 8, 10 red;
outer lookahead refusals ungated -> case 7 emitted_late red; inner side refusals ungated -> case 7
side_price_invalid red; per-side unowned count -> case 7 side_price_invalid red; prior_day_rows off -> case 5 red;
continuation label off -> cases 3 fsync and 11 red; fromtimestamp rounding -> case 4 red; no continuation ->
cases 1, 2, 3 (both), 8, 9 variant 2, 10 red; fsync failure marking the day done -> case 3 (both) red.

AMENDMENT 2 pins (tests/platformkit/execution/test_s584_shadow_midnight_a2.py), each killing a mutant that survived
round 1 (in-memory mutants via the round-1 verifier harness, candidate files untouched): run row remembered before
the final fsync -> test_a2a red (the D+1 continuation must name the successful retry's row_id); short-by-one
continuation write accepted -> test_a2b[1] red (repaired line, nothing glued, both error counters +1, retry next tick);
failed repair swallowed -> test_a2c red (unrepaired_output must raise, write_errors 2); n_rows ungated and
replay_stamped_rows ungated -> test_a2d red (each counts a row only in its owning receipt); `continues_row_id is not
None` accepted as a continuation -> test_a2e[''] red (empty or non-str is diag:duplicate_run). The near-equivalent
prior_day_rows kind guard (verifier F13, optional in the verdict) is left unpinned.

## Pre-existing reds (AMENDMENT 1 A1)

Before this row, two S516 checks were red for drift that is not S584's:

- tests/platformkit/execution/test_live_shadow_fills.py:296
  `assert hashlib.sha256((root/path).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest`
  failed with `AssertionError: assert 'b8749925a78d...da6eaec4ac246' == 'b2ec0afa9d8b...d8675281c5962'`
  (forward_replay_io.py, changed by S496 27ae6b756; `git show 27ae6b756` touches only `_native_input` and its call in
  `native_rows`, so `stamp` and `iso` are unchanged).
- tests/platformkit/execution/test_live_shadow_fills_memo.py:51
  `assert {norm(k):v for k,v in table.items()}==fresh`
  failed on `.gitattributes`: memo (2234, 37, fe57154c...) against (3162, 53, ba49812a...) now (S541, S551, S560
  edited .gitattributes).

Both are now landing-gated (the S501 lesson form): the seal digest walk runs only under
S516_SEAL_LANDING_CHECK=1; the memo-table parse and compare run only under S516_MEMO_LANDING_CHECK=1. The 22-case
list, the <= 300 LOC check, the header regex, `len(base_sha) == 40 and len(immutable) == 10` stay permanent, and a
new permanent assert says no S584 owned path and no live_shadow*.py path is in the seal's immutable set. Both files
are green after. Enabled today, the seal gate is red for the S496 drift only. The memo-table gate is red for the
.gitattributes drift AND for S584's own required edits of live_shadow_fills.py, live_shadow_fills_io.py,
test_live_shadow_fills.py and test_live_shadow_fills_memo.py (measured); this is the case spec item 5 names (a
fixed-sha check that goes red on any later legitimate edit of live_shadow_fills*.py). The S516 memo is not rewritten.

Correction to AMENDMENT 1 A1's wording: for the memo-table gate, "red for the named drift and not for S584" does
not hold; enabled, that gate is red on S584's own required edits as well as on .gitattributes (above).

## Mandatory disclosures

- Ownership moved from the start instant to the decision instant. This supersedes S516 item T (S516_spec.md:9);
  B1b keeps START = t_epoch + S. The S516 case-14 oracle at test_live_shadow_fills_io.py:64 still encodes the start
  rule and agrees on its fixture because no replay tick falls in [23:59:58, 24:00).
- A quote decided in D can fill on D+1 and is reported in D's receipt.
- O4 exactness: exact for every_s <= 300 (launcher 15); above that a closing row after D+1 00:10:00Z is not read
  and the interval runs to expiry (A4). No code change.
- Pre-ownership refusals (identity_invalid, time_not_exact, emitted_invalid counts, future_records) may be counted
  in both receipts that read the row; pre-parse side ids stay listed by each such receipt (A3d), never as an
  interval. A row whose t parsed but whose emitted_ts is invalid is listed only by its owner.
- EXACTLY ONCE scope (A3e): every yes/no side id of an arm row whose t_epoch parses and that is not skipped as
  future_records.
- O3's "the arm rows of shard D are exactly the D-owned rows" holds only for shards written by the new writer
  (A3g); older shards can carry rounded prior-day rows, now counted diag:prior_day_rows.
- A rounded prior-day row left by the OLD writer (pre-S584 shards) near midnight can be owned by no receipt: D's
  lookahead stops before it when no D interval is open, and the D+1 receipt counts it only as diag:prior_day_rows
  (and diag:unowned_refused when it refuses), listing its side ids nowhere. Shards from the new writer never hold
  such a row (O1).
- A shard path over MAX_PATH fails at `path.parent.mkdir` outside the Writer's try (pre-existing; the path length
  is the same every day, so it is not midnight-specific; in the CLI it surfaces as run_row_failed, exit 4).
- The S516 memo-table byte check and the seal digest walk are landing-gated, not deleted.
- A continuation-write failure drops that tick's rows; open intents lapse by expiry.
- The first append into a new day fsyncs twice; this supersedes S515 item 8's "os.fsync once per tick per shard"
  (S515_spec.md:18) for that append only (A2f).
- t_iso (A8): live_shadow_quoter.py:36 rounds t_iso to the microsecond, so a row decided within 0.5 us of midnight
  sits in shard D with t_iso D+1T00:00:00.000000; fills.py accepts it (<= 1000 ns tolerance). Case 36's `placed`
  check uses t_iso[:10] and is unaffected on its integer-second ticks.
- A7: the live recorder (launcher --until 2099) keeps the OLD code until its child process restarts; receipts over
  shards written before that restart still refuse run_row_missing on D+1 rows of a pre-restart process (disclosed,
  not repaired).
- Construct rows reuse the S581 helpers in scripts/platformkit/ops/system_fault_cases_shadow.py moved to D =
  2026-09-25 by offset; hand-built rows keep that module's 2026-09-29 row_id prefix, which the reducer ignores.
  Case 10's live run skips one tick after midnight (00:01:00Z) so D's lookahead stops before the appended junk.

## Inventory (generated by write_memo in tests/platformkit/execution/test_s584_shadow_midnight.py)

<!-- inventory -->
Cases (17 functions: 12 enumerated + 5 AMENDMENT 2 pins): test_a2a_run_row_remembered_only_after_fsync, test_a2b_short_continuation_write_is_a_failure, test_a2c_failed_repair_raises_unrepaired_output, test_a2d_row_counters_only_for_owned_rows, test_a2e_empty_or_non_str_continues_row_id_is_a_duplicate, test_case01_continuation_row, test_case02_two_midnights_and_step_back, test_case03_continuation_failure, test_case04_floor_shard_day, test_case05_boundary_table_ownership, test_case06_decision_day_reads_enough, test_case07_lookahead_refusals, test_case08_run_started_2359_59, test_case09_restart_after_midnight, test_case10_end_to_end_fresh_processes, test_case11_run_labels_and_ownership_assumption, test_case12_fault_case_36_passes

| file | lines | sha256 (LF) |
|---|---|---|
| scripts/platformkit/execution/live_shadow_io.py | 284 | c2dbbae340dd3a3395907802ad18a51fc75e95eb0c4f8c34b17c6e16a9114ab6 |
| scripts/platformkit/execution/live_shadow_fills.py | 272 | 12dae77ea4e033cc597978ae27b08bad9d1b81903265e6b6ae25add295cd6b22 |
| scripts/platformkit/execution/live_shadow_fills_io.py | 279 | 630e7c254b3644e390ee80788a5adc7fae7858f0ad67baffb98dbd2493d01c12 |
| tests/platformkit/execution/test_s584_shadow_midnight.py | 298 | 005ce0ae308daa12c1776f82471943a5ad49ef4a36bab17d45e2e2b1752381a2 |
| tests/platformkit/execution/test_live_shadow_fills_memo.py | 157 | 6880bc6e581dc234c9cd619fb1e8c530872a8ee8094b902728a35c8782476497 |
| tests/platformkit/execution/test_live_shadow_fills.py | 297 | 30dc524291cc84c0699b2e6a5a9fb070756c71d57ab3d98740701f952d2633f1 |
| tests/platformkit/ops/test_system_fault_matrix.py | 159 | 92265b0123efeca1e9ebe7c1089e0c49d96e9cc3ea21d5e43bca743b80681626 |
| tests/platformkit/execution/test_s584_shadow_midnight_a2.py | 101 | a7afbc2d9bf01bb313685d25d759c52b167c741174b7fe61e4eea0d47a715cdc |

Per-file test runs:

    tests/platformkit/execution/test_s584_shadow_midnight.py: 15 passed in 4.76s
    tests/platformkit/execution/test_s584_shadow_midnight_a2.py: 8 passed in 0.63s
    tests/platformkit/execution/test_live_shadow_quoter.py: 1 failed, 82 passed in 1.57s
    tests/platformkit/execution/test_live_shadow_io.py: 31 passed in 3.44s
    tests/platformkit/execution/test_live_shadow_cli.py: 27 passed in 2.77s
    tests/platformkit/execution/test_live_shadow_fills.py: 16 passed in 1.39s
    tests/platformkit/execution/test_live_shadow_fills_b3.py: 11 passed in 1.01s
    tests/platformkit/execution/test_live_shadow_fills_b4.py: 7 passed in 7.97s
    tests/platformkit/execution/test_live_shadow_fills_io.py: 5 passed in 4.42s
    tests/platformkit/execution/test_live_shadow_fills_memo.py: 1 passed in 0.63s
    tests/platformkit/ops/test_system_fault_matrix.py: 42 passed in 120.64s (0:02:00)
<!-- /inventory -->

- Landing note (2026-09-30): test_live_shadow_quoter.py has 1 red test on master before S584 (test_pinned_must_not_move_seal pins capture_watchdog.py, which S601/S607 legitimately changed); not an S584 file, reported to its owner in .planning/NOW.md.

- Acceptance (spec ACCEPTANCE RULE): before = 0 of 12 (cases 1-11 fail on master by construction: no continuation row, the fills.py:176 start ownership, ungated lookahead refusals, fromtimestamp rounding; case 12 is the pin); bar = 12 of 12; the case-36 matrix command prints SUMMARY PASS=1 DEFECT=0 ERROR=0.

## NOT VERIFIED

- No live post-midnight night: the first real post-midnight receipt is orchestrator-run after landing, once the
  live_shadow child has been restarted and a UTC day's run rows carry the landed live_shadow_io.py sha256 (A7).
- No supervised restart across midnight.
- No full-night RSS.
