S465 | FIX LANE 1e | worktree C:/Users/neelj/nba-harness-h119

BUILD RESULT: round 4 (codex sol REJECT, two blockers; Opus tier 2 ACCEPT
WITH CORRECTIONS, five corrections + four notes) reconciled into AMENDMENT
4, items (a)-(f). Metric: before FIX 1d = 2 of 14 (the two round-3 defects
were regressions on the already-fixed cases 1/2/8/9/11, not fresh 0/14
territory); the AMENDMENT 4 items are refinements WITHIN the same 14 cases
(strict schema, Windows paths, the stat except, a portable snapshot, one new
integration construct) rather than new cases -- after FIX 1e (this round,
re-verified) = 14 of 14 still, now proven against every AMENDMENT-4
reproduction below plus one new construct (4(e)).

STEP 0 PREMISE CHECK (every item reproduced against the pre-edit worktree
this session, one line each; full commands/output in the session)
- Owned-file baseline before any edit: 39 / 51 / 16 / 14 / 4 / 2 / 43 passed
  (test_paper_night.py / test_paper_night_steps.py / test_paper_night_
  steps_1d.py / test_paper_night_scoreboard_step.py / _1c / _1d /
  test_ingame_scoreboard.py) -- matches the lane prompt's expected counts.
- `_read_artifact` on `{}` and on `{"ticks": [{}], "counts": {}}` both
  returned the payload unchanged (ticks/counts/arms silently defaulted);
  `{"ticks": [], "counts": {"schedule_refused": nan}}` also returned
  unchanged (sol#1 repro, reproduced directly against _read_artifact).
- `_valid_training_rows` returned True for `foo\..\bar\{date}.jsonl`,
  `\abs\{date}.jsonl`, and `\\server\share\{date}.jsonl` against a
  same-day-different-date scoreboard_out (sol#2 repro); and True for a
  backslash-alias and a case-only alias of scoreboard_out (Opus#1 repro).
- `scoreboard_row_updates` with `out.stat()` raising OSError returned
  normally (reason != "stale_output") instead of propagating (Opus#4 repro,
  test_scoreboard_row_updates_transient_stat_error_is_not_stale passed).
- fixtures/s465_case1_legacy_snapshot.json's three rows all carried
  peak_method "windows_peak_wset_polled+post_exit" -- os.name baked in, not
  portable to a POSIX host (Opus#5 repro, confirmed via the fixture itself).
- test_paper_night_scoreboard_step.py's four_budget comment (starting line
  52, a 3-line block) still cited the old
  "~76MB idle / ~52MB headroom" theory the FIX 1c OSError hardening had
  excused, not the corrected ~81MB/128MB flake analysis (Opus#2 repro).
- Memo SHA block (pre-edit): HEAD=master=950c3e446 but stated "master has
  since advanced to 950c3e446" (same sha) and a stale tail line "HEAD=
  master=51aa5d9f4" -- self-contradictory (Opus#3 repro).

FIX 1d (every AMENDMENT 3 item, file:line, and its test)
| item | finding | fix | test |
|---|---|---|---|
| 3(a) | fail-open (OSError, ValueError) catch around the artifact read let an unreadable/malformed output complete as RAN/A_ONLY/errors=0/COMPLETE; `[]`/malformed `arms` raised AttributeError out of main() with the lock held | paper_night_steps.py: new `_read_artifact()` (104-133) -- no catch around the read; only PermissionError retried (3x0.1s bounded, then re-raised); payload/tick/arms/counts validated as dicts or raises ValueError("output_malformed"). scoreboard_row_updates (136-169) calls it directly -- any raise propagates to _run's own except (paper_night.py:207-209, unchanged), giving errors+=1 and reason="child_nonzero_exit" | test_scoreboard_row_updates_unreadable_output_propagates_for_counted_refusal (steps.py:274, the renamed test at the old :251 slot -- now asserts pytest.raises(OSError) instead of degrade-to-A_ONLY); test_read_artifact_retries_permission_error_then_succeeds / _exhausts_... (steps_1d.py); test_scoreboard_row_updates_malformed_output_raises_valueerror_not_attributeerror x5 params (steps_1d.py); full-pipeline repro above (both `{not json` and the two AttributeError payloads) |
| 3(b) | training_label attached before the missing/stale/schedule-refused checks, so a REFUSED row still carried one; non-finite B counted as reconstructible; the "absent" flag name overstated the warmup-filtered case | scoreboard_row_updates (paper_night_steps.py:136-169) reordered: missing -> stale -> schedule_refused checks return immediately with NO training_label; only a row that falls through to the end (implicitly RAN/reason=None) gets one. New `_finite_probability()` (86-88) gates `_reconstructible_training_rows` (91-101) to a finite [0,1] value. Flag renamed training_history_absent -> no_fitted_arm (168) | test_scoreboard_row_updates_missing_output_refused / _schedule_rows_refused (both now assert "training_label" not in updates); test_scoreboard_row_updates_a_only_label_when_no_reconstructible_ticks / _fitted_label_... (renamed key); test_scoreboard_row_updates_non_finite_or_out_of_range_probability_not_reconstructible x7 params (steps_1d.py) |
| 3(c) | `_valid_training_rows` used a substring count(`{date}`)==1 check -- `{{date}}.jsonl` (a format-escape, zero real fields) passed and formatted to a constant path; raw string `!= scoreboard_out` missed `out/../out/{date}.json` and `./a/{date}.json` aliasing | Rewritten (paper_night_steps.py:184-214) with string.Formatter().parse() for exactly one field named `date`; two-different-dates-give-two-different-paths check; PurePosixPath absolute/`..`-component refusal; posixpath.normpath comparison against scoreboard_out's own rendered path (new `_rendered_scoreboard_out` helper, 172-181) | test_validate_declared_invalid_training_rows_refused (+5 new params: `{{date}}.jsonl`, 2x absolute, 2x `..`); test_validate_declared_training_rows_dotdot_alias_of_scoreboard_out_refused / _dot_prefix_... (steps_1d.py) |
| 3(d) | `_normalize_rows` in test_paper_night_scoreboard_step.py kept only name/argv/step_status/reason, dropping exit_code/artifacts/errors/every other field; the case-1 fixture pinned argv[0] to this host's absolute python.exe path | Rewritten (test_paper_night_scoreboard_step.py:21-40) to keep every row field, blanking only started_utc/wall_s/peak_working_set_bytes/free_ram_at_start_bytes (a live psutil sample, same nondeterminism class as peak_working_set_bytes -- not in the amendment's literal 5-item list but required for the stated "portable" goal, since it is measured fresh every run) / root prefix in argv / argv[0]-><PYTHON>; artifacts[].bytes+sha256 also blanked (the CHILD stub embeds a real time.time_ns() timestamp, so its digest is never reproducible run-to-run, let alone host-to-host) and independently re-verified fresh via new `_assert_fresh_digests()` (43-48). Fixture regenerated ONCE from blob 3af3aa343 + master's paper_night_budget.json (both == the pre-change state; this row's own edits are still uncommitted, confirmed via `git hash-object` matching 3af3aa343 exactly) | test_legacy_budget_through_main_steps_none_three_steps (asserts the full normalized comparison AND _assert_fresh_digests) |
| 3(e) | case 13 ran `git show master:...paper_night.py` -- a tautology once this row lands (master becomes the candidate) and fails in a checkout with no local master ref | test_paper_night_scoreboard_step_1c.py: `git cat-file -p 3af3aa343` (the diff's own index line) in place of `git show master:...`; module/var names updated from "master_*" to "pre_change_*" for honesty | test_steps_legacy_flag_off_matches_master_directly (same test, fixed source) |
| 3(f) | case 4 checked only `len(artifacts)==1 and present is True`, never the digest | Added `_assert_fresh_digests(root, [row])` call | test_scoreboard_artifact_digest_no_sidecar |
| 3(g) | memo | this rewrite |

FIX 1e (every AMENDMENT 4 item, file:line, and its test)
| item | finding | fix | test |
|---|---|---|---|
| 4(a) | `_read_artifact` (steps.py:127-132) defaulted missing ticks/counts/arms to empty containers via `.get(..., default)`, so `{}` and `{"ticks": [{}], "counts": {}}` completed as A_ONLY; counts values were never type/sign-checked (NaN accepted) | Rewritten (steps.py:104-134): ticks/counts REQUIRED via `"ticks" not in payload`/`"counts" not in payload`, each tick's `arms` REQUIRED via `"arms" not in t`; counts values checked `type(v) is int and v >= 0` (rejects NaN/inf/negative/float/bool); RecursionError from json.loads mapped to ValueError("output_malformed") | test_scoreboard_row_updates_malformed_schema_refused-equivalent params added to test_scoreboard_row_updates_malformed_output_raises_valueerror_not_attributeerror (steps_1d.py, now 13 params incl. missing-ticks/counts/arms and NaN/inf/negative/non-int counts); test_read_artifact_recursion_error_maps_to_output_malformed (steps_1d.py); the old missing-ticks acceptance test removed from steps.py |
| 4(b) | `_valid_training_rows` (steps.py:184-214) only checked PurePosixPath absolute/`..` and raw-string equality against scoreboard_out -- backslash forms and UNC paths passed, and a case-only or separator-only alias of scoreboard_out passed | Rewritten (steps.py:172-205): `"\\" in value` refuses outright (covers all 3 backslash/UNC constructs with no filesystem lookup); added PureWindowsPath absolute/`..` check alongside PurePosixPath; comparison against scoreboard_out now `posixpath.normpath(...).casefold()` on both sides | test_validate_declared_windows_separator_training_rows_refused x3 params, test_validate_declared_training_rows_ntfs_alias_of_scoreboard_out_refused x2 params (new steps_1e.py) |
| 4(c) | `scoreboard_row_updates` (steps.py:152-155) wrapped the mtime stat in `except OSError: stale = False`, swallowing a transient stat failure as "not stale" | try/except removed -- the stat call is unguarded, so a failure propagates to _run's own counted except | test_scoreboard_row_updates_transient_stat_error_is_not_stale inverted to test_scoreboard_row_updates_transient_stat_error_propagates (asserts pytest.raises(OSError)) |
| 4(d) | test_paper_night_scoreboard_step.py's `_normalize_rows` compared peak_method verbatim, which bakes in `night.POLLED` (os.name) -- the case-1 fixture fails on a POSIX host | `_normalize_rows` (scoreboard_step.py:21-27) now does `row["peak_method"].replace(night.POLLED, "<POLLED>")`, keeping the +post_exit/_lower_bound suffix compared; fixture regenerated (see A9) by running the pre-change blob 3af3aa343 through the SAME legacy-budget/archive-fixture setup as case 1, then applying this candidate's fixed _normalize_rows to the raw result | test_legacy_budget_through_main_steps_none_three_steps (unchanged test, now passes against the regenerated fixture); processes_already_exited stays compared exactly (stable 8/8 across repeated runs this session, per AMENDMENT 3(g)/Opus NOTE 8 -- unblanked, will be blanked if it ever flakes) |
| 4(e) | AMENDMENT 3(a) was proven only by unit-level raises on _read_artifact/scoreboard_row_updates, never through the real `_run()`/main() pipeline end to end | New test_paper_night_scoreboard_step_1e.py: a malformed writer-child (exits 0, writes `{not json`) driven through the REAL `_run()` via `invoke()`/`main()` | test_malformed_writer_child_through_run_gives_partial_one_error -- asserts code==3, payload["status"]=="PARTIAL", row["errors"]==1, row["reason"]=="child_nonzero_exit" |
| 4(f) | memo stale/wrong (this document, pre-edit) | this rewrite: FIX 1e section, corrected flake-analysis paragraph below, corrected the four_budget comment at test_paper_night_scoreboard_step.py line 52, single SHA block, A9 regenerated last | -- |

FIX 1f (round 5: codex sol REJECT on one memo-only blocker + Opus ACCEPT
WITH CORRECTIONS on four items, reconciled): paper_night_steps.py
`_valid_training_rows` (:207-208) gained a raw-template shape check --
`":" in value` or any `/`-segment not equal to its own `.rstrip(". ")` --
refusing an NTFS ADS suffix or trailing-dot/space alias of scoreboard_out in
training_rows before any spawn. test_paper_night_steps_1e.py's NTFS-alias
parametrize grew from 2 to 5 cases. Memo-only: the flake-analysis paragraph,
a merged SHA block, the case-9 RIPPLE reword, and two new NEW GAPS entries.

RIPPLE FROM 4(a) (not an amendment item): the generic `fake()` CHILD double
writes `{start,end,status,refused}` -- no ticks/counts -- so a scoreboard row
built with `fake("scoreboard")` now refuses output_malformed instead of
completing RAN/A_ONLY. Three existing tests needed a schema-compliant double
instead: test_injected_five_step_list_is_count_agnostic (case 3),
test_scoreboard_artifact_digest_no_sidecar (case 4), and
test_child_failure_does_not_block_other_steps (case 10), all switched to a
new `fake_scoreboard()` helper (test_paper_night_scoreboard_step.py) that
writes `{"ticks": [], "counts": {}}`. `_fake_children` (used by cases 1/2,
which drive the REAL `_steps()` builder through a Popen spy) was similarly
updated to redirect the scoreboard call specifically to `fake_scoreboard`'s
script instead of the generic CHILD, keyed on `steps_mod.SCOREBOARD_MODULE
in argv`. Cases 5-8/11/12 and the _1c free-RAM-floor case never reach
`_read_artifact` (skip/refused/killed paths short-circuit first) and needed
no change. Case 9 DOES reach `_read_artifact` (the real module child exits 0
and writes a schema-valid artifact) -- its refusal comes from the POST-READ
schedule_refused check inside `scoreboard_row_updates`, not from 4(a)'s
schema gate, so it is unaffected by this round's changes. Verified by the
full per-file pass counts below.

LOC OVERFLOW (not an amendment item, a consequence of 3(a)-(f) adding real
lines to files already at/near their caps): test_paper_night_steps.py hit
300 exactly after the in-place fixes: the net-new cases (2x training_rows-
alias tests, 7x non-finite-probability params, 2x PermissionError-retry
tests, 5x malformed-payload params) moved to a NEW sibling
test_paper_night_steps_1d.py (same pattern as test_paper_night_scoreboard_
step_1c.py). test_paper_night_scoreboard_step.py similarly hit 300 after the
_normalize_rows/_assert_fresh_digests growth; case 14
(test_validate_refuses_scoreboard_without_required_keys_via_main) and
test_unknown_declared_step_named_refusal moved to a NEW
test_paper_night_scoreboard_step_1d.py (imports _low_ceiling_template from
the sibling). Both new files are construct-only, no archive/network, same
fixtures as their sibling files -- consistent with the lane prompt's
explicit "new cases here or in a NEW test_paper_night_scoreboard_step_1d.py,
authorised" precedent already set by _1c in the prior round.

FIX 1e LOC: paper_night_steps.py grew to 291/300 from 4(a)/(b)/(c) in place
(room left). test_paper_night_steps.py stayed at the 300 cap -- the 4(a)
in-place fixes were net-neutral (counts={} added inline, no new lines; one
test removed, one inverted in place); the new 4(a)/4(b) construct cases went
to test_paper_night_steps_1d.py (77->95, room left) and a NEW
test_paper_night_steps_1e.py (37 lines) per the lane prompt's explicit
"...or a NEW test_paper_night_steps_1e.py, authorised". test_paper_night_
scoreboard_step.py stayed at the 300 cap after 4(d)'s _normalize_rows/
four_budget-comment/_fake_children growth by trimming existing comments to
fit (no test logic removed); the 4(e) integration construct went to a NEW
test_paper_night_scoreboard_step_1e.py (24 lines). FIX 1f (round 5, this
round) grew paper_night_steps.py to 293/300 (room left) and
test_paper_night_steps_1e.py to 41 lines (3 new parametrize cases, room
left).

MUST-NOT-MOVE (re-verified after every edit, this session)
`git diff --stat master` for ingame_scoreboard.py, ingame_scoreboard_rules.py,
baseline_four_arm*.py, paper_night_lock.py, paper_night_peak.py -> empty.
paper_night.py was NOT edited this round either (FIX 1e touched only
paper_night_steps.py and test files) -- its diff vs master is unchanged from
FIX 1c/1d (20 insertions/19 deletions, the single declared `if name ==
"scoreboard":` hunk at :206 plus the AMENDMENT 3(a) override-detection-
before-validation comment at :253-255, both pre-existing). runner_lock and
the four sealed producer-constant checks at _validate:228-231 remain
byte-identical (file untouched). Case 1's frozen-snapshot equality (now
against the regenerated fixture) and case 13's direct _steps() equality
against the pre-change blob both independently prove the other three steps
are byte-for-byte what the pre-change module produces. The budget's five
pre-existing keys (ceiling_bytes.{qualification,fill_realism,week},
free_ram_margin_bytes, poll_interval_s, plus the original 10 producer_args
keys) are unchanged -- `git diff master -- paper_night_budget.json` shows
only additive new keys.

LOC (all thirteen owned files; ASCII; no CRLF introduced)
paper_night.py 300 (cap, unchanged) | paper_night_steps.py 293 |
paper_night_budget.json 23 (unchanged) | test_paper_night.py 299 (unchanged)
| test_paper_night_steps.py 300 (cap) | test_paper_night_steps_1d.py 95 |
test_paper_night_steps_1e.py 41 (grew this round) | test_paper_night_scoreboard_step.py
300 (cap) | test_paper_night_scoreboard_step_1c.py 91 (unchanged) |
test_paper_night_scoreboard_step_1d.py 41 (unchanged) |
test_paper_night_scoreboard_step_1e.py 24 (new) |
fixtures/s465_case1_legacy_snapshot.json 142 lines (regenerated, peak_method
now <POLLED>) | this memo <= 300.

TEST RESULTS (per-file, one at a time, no full suite; construct fixtures, no
archive read, no network, no concurrent children)
test_paper_night.py 39 | test_paper_night_steps.py 50 | test_paper_night_
steps_1d.py 25 | test_paper_night_steps_1e.py 8 (grew this round from 5) |
test_paper_night_scoreboard_step.py 14 | test_paper_night_scoreboard_
step_1c.py 4 | test_paper_night_scoreboard_step_1d.py 2 |
test_paper_night_scoreboard_step_1e.py 1 (new) | test_ingame_scoreboard.py
43 (must-not-move, unchanged). Total scoreboard-step-family cases:
14+4+2+1=21 integration, 50+25+8=83 unit. `python -m scripts.platformkit.
execution.paper_night --help` parses cleanly (unchanged, paper_night.py not
edited this round).

CASES (14 named; post FIX 1e; + one new AMENDMENT 4(e) integration construct
outside the 14, since 4(e) strengthens case 3(a)'s proof rather than adding
a 15th contract case)
1->test_legacy_budget_through_main_steps_none_three_steps (frozen-snapshot
   eq against the blob-3af3aa343-derived fixture, REGENERATED this round for
   4(d)'s <POLLED> normalisation, + independent fresh-digest check).
2->test_four_step_budget_through_main_steps_none_scoreboard_last (_fake_
   children now redirects the scoreboard call specifically to
   fake_scoreboard's schema-compliant double, 4(a) ripple).
3->test_injected_five_step_list_is_count_agnostic (fake("scoreboard") ->
   fake_scoreboard(), 4(a) ripple).
4->test_scoreboard_artifact_digest_no_sidecar (asserts the fresh digest;
   fake("scoreboard") -> fake_scoreboard(), 4(a) ripple).
5->test_not_landed_scoreboard_only (unchanged).
6->test_archive_absent_state_subtree_missing (unchanged).
7->test_archive_absent_missing_daily_shard (unchanged).
8->test_missing_prereg_real_module_child_nonzero_exit + control (unchanged).
9->test_malformed_served_schedule_real_module_refuses_schedule_rows (unchanged).
10->test_child_failure_does_not_block_other_steps (fake("scoreboard") ->
    fake_scoreboard(), 4(a) ripple).
11->test_missing_output_refused_not_silently_complete + test_stale_output_
    refused_not_silently_complete (unchanged -- argv overridden before the
    generic fake() artifact would ever be written, so 4(a) doesn't reach
    these two).
12->test_ceiling_exceeded_reuses_existing_kill_path + test_free_ram_floor_
    scoreboard_reuses_existing_refusal_path (_1c, unchanged -- both short-
    circuit before _read_artifact is ever called).
13->test_steps_legacy_flag_off_matches_master_directly (_1c, pinned to blob
    3af3aa343) + case 1.
14->test_validate_declared_scoreboard_missing_required_keys_refused (unit,
    steps.py) + test_validate_refuses_scoreboard_without_required_keys_via_
    main (_scoreboard_step_1d.py).
+(4e)->test_malformed_writer_child_through_run_gives_partial_one_error
    (NEW, _scoreboard_step_1e.py): a real malformed child through the
    unmodified _run() -- PARTIAL, errors==1, reason==child_nonzero_exit.

NEW GAPS (disclosed, not fixed here -- unchanged from FIX 1c/1d plus the
three AMENDMENT 4 additions (h)-(j) and the two round-5 additions (k)-(l))
(a) No producer writes a training_rows-shaped JSONL yet -- every real night
    is A_ONLY (the label's source, ordering, and finite-probability gate are
    now all correct; there is just nothing to read yet).
(b) missing/stale-output and schedule_rows_refused checks are scoreboard-
    only; the week step at :199 parses its own output the same unguarded way
    -- a malformed week artifact is not covered by this row.
(c) Any producer_args path that fails `_local` in `_steps` raises uncaught
    out of main -- `_validate` does not check paths; training_rows is the
    one path template this row validates (3(c)/4(b)), the rest are not.
(d) MISSED GAP 2 / S470 (per-step wall-time deadline): deferred.
(e) S460's registry scorer is a named future fifth step through this same
    mechanism; unknown_declared_steps refuses it by name until it lands.
(f) The training-row-accepted signal (finite B/C/D on a tick) is an
    INFERENCE from ingame_scoreboard's own output shape, not a dedicated
    counts:: key -- no_fitted_arm documents this as a proxy, out of scope.
(g) ADOPTION (orchestrator): the standalone 03:07Z scoreboard cron and this
    step share one --out; retire the cron or re-point it at landing.
(h) AMENDMENT 4: the Windows-separator/case-alias hardening in 4(b) covers
    training_rows only -- _validate checks no other producer_args path
    (scoreboard_out/prereg/served_schedule/etc.), same as (c) above.
(i) AMENDMENT 4: `_reconstructible_training_rows` counts a tick FITTED when
    ANY single arm (B/C/or D) is a finite probability -- a NaN on a sibling
    arm of the same tick is silently ignored rather than refusing the tick.
(j) AMENDMENT 4: RecursionError is now mapped inside `_read_artifact`
    specifically, but is not in `_run`'s own except tuple -- any OTHER
    json.loads call added to a future step would still escape uncaught.
(k) round 5: NTFS trailing-dot, trailing-space, alternate-data-stream (":")
    and 8.3 short-name aliases apply to every producer_args path
    (scoreboard_out/prereg/served_schedule/week/etc), not just
    training_rows -- `_validate` normalises none of them; training_rows is
    the one path this row's shape check now covers (same scope note as (h)).
(l) round 5: processes_already_exited in the case-1 fixture (sourced from
    psutil.NoSuchProcess on Windows) may not be portable to POSIX, where an
    unreaped zombie child could still be found by psutil (WNOWAIT), giving a
    different count -- blank the field in `_normalize_rows` if case 1 ever
    fails on the pod.

Q6: calibration language only; vocab/retracted-figure scan clean
(contract_preflight PASS, no exemption flag) across all thirteen owned
files and this memo.

A9 IDENTITIES (regenerated from disk as the LAST edit, LF-normalised bytes+sha256)
- scripts/platformkit/execution/paper_night.py: 300 lines, 15458 bytes, sha256(LF)=06a27a6a590bd39abf553e2ee86efc1a064bfaed6d0eb59fd5326add93beef20 (UNCHANGED -- not edited)
- scripts/platformkit/execution/paper_night_steps.py: 293 lines, 14942 bytes, sha256(LF)=3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 (grew this round: FIX 1f's _valid_training_rows shape check)
- scripts/platformkit/execution/paper_night_budget.json: 23 lines, 1288 bytes, sha256(LF)=c0c92b5ae897ace2e91a3708442566c69c1e543fabdba4e0f5da4dd9f5fe2755 (UNCHANGED -- not edited)
- tests/platformkit/execution/test_paper_night.py: 299 lines, 17001 bytes, sha256(LF)=2f472c67a5822578f1b0601d38d0c0988e9fa218f1d720e15f410059ede7f3bd (UNCHANGED -- not edited)
- tests/platformkit/execution/test_paper_night_steps.py: 300 lines, 14112 bytes, sha256(LF)=e9f0cc39371bc1325fbe5986ec396a74c4c8f8384df934b7293627c83c6db2e3
- tests/platformkit/execution/test_paper_night_steps_1d.py: 95 lines, 4511 bytes, sha256(LF)=b22f9b67dbe2058228f95ab6daeac20076a1a53dc71175f2f33693b733223ff9
- tests/platformkit/execution/test_paper_night_steps_1e.py: 41 lines, 2348 bytes, sha256(LF)=330150ab367f207701613d9c945fe7c1ec389898a305fc10e6f65651a51a5d84 (grew this round: 3 new NTFS-alias params)
- tests/platformkit/execution/test_paper_night_scoreboard_step.py: 300 lines, 15971 bytes, sha256(LF)=0bf3dfc8134ab0f82510b3eab92adc5487582a9e1173361cdc9a7f4e09e5dd9c
- tests/platformkit/execution/test_paper_night_scoreboard_step_1c.py: 91 lines, 4800 bytes, sha256(LF)=53a68b19c78beced717e122b8d63b39fc723972b9d34ed9265c2a77f70cc3f31 (UNCHANGED -- not edited)
- tests/platformkit/execution/test_paper_night_scoreboard_step_1d.py: 41 lines, 2147 bytes, sha256(LF)=1c92d1faffd9dc799957da97af29e499da83afbd20419655815629b6e53a473d (UNCHANGED -- not edited)
- tests/platformkit/execution/test_paper_night_scoreboard_step_1e.py: 24 lines, 1255 bytes, sha256(LF)=e8d9c87342324927bf6bffd61725a5908d113ceb70f9efae7ad8cc9b43db719e (new)
- tests/platformkit/execution/fixtures/s465_case1_legacy_snapshot.json: 142 lines, 4274 bytes, sha256(LF)=46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3 (regenerated this round: pre-change blob 3af3aa343's own main() run through the same legacy-budget/archive-fixture setup as case 1, then this candidate's fixed _normalize_rows applied -- STILL UNTRACKED; the landing pathspec must include it)
- docs/evidence/forward/scoreboard/PREREG_2026-09-24.json (resealed prereg, reference only -- must-not-move, unchanged this lane): 5046 bytes, sha256(LF)=6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b
- night artifact: none, no real night was run this session.

FLAKE ANALYSIS (round-5 CORRECTION 2, was missing -- table row 4(f) above
points here): the real ingame_scoreboard module peaked near 81 MB under the
128 MB test-time ceiling this session; the 256 MB test-only ceiling stands
unchanged (production uses 1572864000, per NOT VERIFIED below). The FIX 1c
OSError hardening around the stat/read path was the WRONG fix for that
flake and was reverted under AMENDMENT 3(a) (3(a)'s `_read_artifact`
rewrite carries no try/except OSError) -- the actual fix is 3(a)'s strict
schema plus 4(c)'s unguarded stat call, not a memory-headroom change.

SHA: NOT CREATED (sandbox); files ready for lane_commit.
HEAD   = 0daa0acd4531b421d0399dc81e8f1c3caea914bb
master = 0daa0acd4531b421d0399dc81e8f1c3caea914bb
EQUAL -- FIX 1f's `git merge --ff-only master` at the START of this session
returned "Already up to date"; a landing session must fast-forward again and
re-run contract_preflight + the must-not-move diff against the final
committed tree before this row ships.

NOT VERIFIED (final, stated plainly -- this is the LAST section of this memo)
- No real paper night was run; every case is a construct/fixture test, or a
  real-module invocation against synthetic (not archive) files.
- Cases 8/9 and the control assert stdout_last_line content and the fresh
  artifact's own counts, but not the FULL breadth of ingame_scoreboard's own
  refusal taxonomy -- that stays test_ingame_scoreboard.py's job (43 passed
  unchanged, confirmed above).
- The training-row-accepted signal is an inference (NEW GAP f), unverified
  against any real training corpus since none exists yet to construct one from.
- peak_method's night.POLLED (os.name) component is now normalised to
  <POLLED> in the case-1 fixture (4(d)), so the fixture no longer bakes in a
  Windows-only value; it was NOT regenerated ON a POSIX host this session
  (only re-derived, on this Windows host, from the pre-change blob through
  the fixed _normalize_rows) -- a POSIX run of case 1 is still unverified.
  processes_already_exited stays compared exactly, unblanked (stable 8/8
  runs here; will be blanked if it ever flakes, per AMENDMENT 4(d)).
- NEW GAPS (a)-(l) above are none of them fixed in this row.
- The placeholder scoreboard memory ceiling (1572864000 production; 256MB
  test) is carried over/estimated -- the ~81MB peak cited in 4(f) is this
  session's own measurement of the real module's import-time RSS, not a
  profiled bound under real production load.
- contract_preflight (9/9 PASS, no exemption flag) and the must-not-move
  diff were run in this sandbox against HEAD=0daa0acd4/master=0daa0acd4 --
  EQUAL; no commit was made, so a landing session must re-run both against
  the final committed tree before this row ships.
