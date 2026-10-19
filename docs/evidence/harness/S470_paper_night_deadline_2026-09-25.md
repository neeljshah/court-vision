# S470 -- paper-night per-step wall-time deadline

BUILD (2026-09-25), worktree `nba-harness-h122`, governed by
`docs/evidence/tracking/specs/S470_spec.md` (DISPATCH NOTE + AMENDMENTS 1-2).
Construct-only throughout: fake children (`python -c` sleeps/spawners) and
process doubles; no real night, no archive read, no network, no measured
number. SINGLE PROBLEM (spec): pre-S470 `_run` polled only a memory ceiling (no
wall-time bound), so one hung below-ceiling child blocked every later step
forever. CHANGE: the poll loop and both process-cleanup finally paths were
extracted verbatim out of `_run` (unchanged, no-deadline case) into new
`paper_night_deadline.py` (`poll_step`, `terminate_tree`,
`_kill_via_popen_handle`, `deadline_ns`, `exceeded`, `validate_deadline`),
replacing the old descendants-first, no-timeout `_kill` with a parent-first,
bounded `terminate_tree`; `paper_night_budget.json` gained one additive
`deadline_s` key (table below). Round-1 (`_verdict_s470_1b.md`, AMENDMENT 1)
applied below as FIX 1b. Round-2 (`_verdict_s470_1c.md`, AMENDMENT 2) applied
as FIX 1c (every owned/unchanged test file re-run to green;
`deadline_override`, no caller, deleted). Round-3 (`_verdict_s470_1d.md`: codex
down, TIER 1 an independent Opus critic reading the codex prompt, TIER 2 Opus,
both ACCEPT WITH CORRECTIONS) needed no amendment, applied as FIX 1d
(fixture/test/memo only). One round-1 fix: cases 3-5's fake-child marker writes
are flushed + fsynced before the child does anything else that could get it
killed, with a bounded polling reader (`_read_marker`) on the test side.

## HEAD vs master

The lane built at `b45883fdac1b3f2149833d5007a92e6ebae0ab5c` (EQUAL to master
then, prior round). FIX 1b's memo recorded HEAD == master ==
`ac10cd6ed3db8e87ebb823d7e9c31f655e9a1973` after a fast-forward (only the S462
landing + register row in between), EQUAL (prior round). FIX 1c's own
fast-forward picked up one unrelated two-line `S468_spec.md` commit; HEAD ==
master == `9340b0e34b88984f84153b532f936a3f283d455f`, EQUAL (prior round). FIX
1d ran `git merge --ff-only master` at its start: already up to date, a no-op.
HEAD == master == `954323c99ba9a7741f98545d8ccc35b5eb6e72c6`, EQUAL. Drift on
`master` after this point is not a finding for this row.

## The setup-inclusive clock boundary

`start = time.monotonic_ns()` stays at its original, unedited call site in
`_run` (before the temp log file and before `Popen`). `poll_step` compares
`time.monotonic_ns() - start_ns` against the limit via `exceeded()` on every
poll, so a step's measured deadline includes its own `Popen` setup cost.

## Exact deadline values (NOT PROFILED)

`paper_night_budget.json`'s new `deadline_s` declares all four steps this
budget already declares in `ceiling_bytes`; every other key/value is
byte-identical to master. NOT PROFILED: no real producer runtime was measured
for any of the four; these are conservative round placeholders.

| step | deadline_s | one-line rationale |
|---|---|---|
| qualification | "900" | reads the fullest schedule + capture-root shards; heaviest single read of the four |
| fill_realism | "600" | scoped to one day's already-narrowed book/state shards |
| week | "300" | a rollup over already-written daily artifacts, lightest of the four |
| scoreboard | "900" | reads training history plus the served schedule and fits per-tick models (S465) |

## Per-case before/after (n = 14, CONSTRUCT)

"before" = measured on the S465-landed blob (`fd5211c96`) where applicable; N/A
= the deadline mechanism did not exist pre-row, per the spec's own instruction
not to claim that as a pass of this row.

| # | case | before (pre-S470) | after (candidate) | test |
|---|---|---|---|---|
| 1 | legacy budget, no `deadline_s` | 3-step rows | byte-identical vs a PINNED fixture, no new keys, deterministic Popen/process/running/finish doubles (FIX 1c) | `test_legacy_budget_run_matches_pre_change_snapshot`; the override predicate is a SEPARATE test, `test_legacy_budget_without_deadline_s_is_override_refused` + `_refused_through_main` (1c) |
| 2 | sleeps past a short deadline | runs to completion (no bound) | KILLED / `step_deadline_exceeded`, 1 termination event, `wall_s` bounded | `test_deadline_kill_within_bound` |
| 3 | grandchild dies with the killed parent | grandchild survives | both dead, `processes_killed == 2` | `test_grandchild_dies_with_killed_parent` (1b, handshake) |
| 4 | supervising child respawns | respawns forever | no survivor (parent killed first) | `test_supervising_child_respawn_leaves_no_survivor` (1b, handshake) |
| 5 | AccessDenied on a descendant kill | N/A | counted, step returns bounded, later step RAN | `test_access_denied_descendant_counted_and_step_returns` (1b, handshake) |
| 6 | two-step night, first deadline-killed | N/A | first KILLED, second RAN, `complete=False`, one reason | `test_first_step_deadline_killed_second_still_runs` |
| 7 | two timed-out steps | N/A | two KILLED rows, one deduplicated reason | `test_two_timed_out_steps_two_rows_one_reason` |
| 8 | fast child, generous deadline | RAN, reason None (already worked) | RAN, reason None, no new keys | `test_fast_child_under_generous_deadline_ran` |
| 9 | elapsed == limit / limit + 1ns | N/A | `False` / `True` (pure function) | `test_exceeded_boundary_exact_and_one_ns_over` |
| 10 | NaN/inf/-1/0/1.5/1/True/10-decimal/list/unknown name | N/A | every one refuses `budget_invalid_deadline`, zero spawns | `test_invalid_deadline_value_refuses_before_spawn` + `test_unknown_deadline_name_refuses` |
| 11 | ceiling + deadline both exceeded, same poll | N/A | `ceiling_exceeded`, exactly 1 termination event | `test_ceiling_and_deadline_together_ceiling_wins` |
| 12 | exit on the same poll the deadline would fire | classified by exit (pre-existing) | classified by exit (RAN), never KILLED | `test_exit_wins_over_already_expired_deadline_same_poll` |
| 13 | deadline for one step, none for another | N/A | only the named step bounded; other RAN | `test_deadline_bounds_only_the_declared_step` |
| 14 | default budget deadlines validate; one override detected | N/A | through `main(steps=None)`: default never refused; a `week` override IS `budget_override_refused` | `test_default_budget_deadlines_validate_and_override_detected` |

Disclosure (case 1, kill-path byte-identity): the fixture only proves the
COMPLETION path byte-identical; a legacy budget's KILL paths still gain
`termination_events`/`processes_killed`/`kill_access_denied`/`kill_survivors`
under this row by design (the spec's own termination count), never hidden.

Fixture provenance (FIX 1c, AMENDMENT 2(c)): regenerated from `git show
dc20faab7:.../paper_night.py` (S465 LANDING, not the fd5211c96 register commit
the "before" column above still cites for the measurement baseline) under the
same frozen clocks/doubles, with a psutil.Process double
(`_DeterministicProcess`, imported into case 1's own test from
`test_paper_night_deadline_1c.py`). Byte-equal 3360/3360 across 3 runs.

Disclosure (AMENDMENT 2(b)): an AccessDenied at identity CAPTURE falls back to
the raw Popen handle, which cannot enumerate or kill descendants -- a
grandchild of a capture-denied parent is left alive, uncounted, the same gap an
AccessDenied from `children()` already leaves; NEW GAP for the register, not
fixed by this row.

## Per-file pass counts (each run alone, `-q -p no:cacheprovider`, never the suite)

| file | passed |
|---|---|
| `tests/platformkit/execution/test_paper_night_deadline.py` (case 1 doubles + byte-comparison, FIX 1c) | 20 (x3 runs, identical) |
| `tests/platformkit/execution/test_paper_night_deadline_1b.py` (is_running() doubles, case 5 bound tightened, FIX 1c) | 9 (x3 runs, identical) |
| `tests/platformkit/execution/test_paper_night_deadline_1c.py` (new: capture-AccessDenied regression + case 1's override-predicate tests + case 1's doubles) | 3 (x3 runs, identical) |
| `tests/platformkit/execution/test_paper_night.py` (line 34 revert only; unchanged this round) | 39 (x3 runs, identical) |
| `test_paper_night_steps.py` / `_1d` / `_1e` (unchanged) | 50 / 25 / 8 |
| `test_paper_night_scoreboard_step.py` / `_1c` / `_1d` / `_1e` (unchanged) | 14 / 4 / 2 / 1 |
| **total** | **175 passed, 0 failed** |

## FIX 1b -- every AMENDMENT 1 item, file:line, one-line reproduction

Governed by `_verdict_s470_1b.md` + spec AMENDMENT 1 (history; FIX 1d (3) below
re-points citations FIX 1c's own edits later moved).
- **(a)** identity-bound, once-counted cleanup -- `terminate_tree` (105-177),
  `poll_step` capture block (237-246); counts come only from `wait_procs`
  gone/alive, never double-counted. Self-caught `UnboundLocalError` there
  fixed, caught by
  `test_poll_step_survives_a_pid_gone_before_identity_capture`.
- **(b)** `validate_deadline` checks the CANDIDATE's own `ceiling_bytes`, runs
  before override detection -- `paper_night_deadline.py:53-102`;
  `paper_night.py:224-237` (`gate_budget` patch removed). Repro:
  `deadline_s={"scoreboard":"1"}` outside `ceiling_bytes` now REFUSED (was
  ACCEPTED); `week=1.5` with `steps=None` exits 2 `budget_invalid_deadline`
  (was `budget_override_refused`).
- **(c)** case 1 frozen/snapshot/byte-level vs a committed fixture --
  `fixtures/s470_case1_legacy_snapshot.json` + `test_paper_night_deadline.py`.
- **(d)** cases 2/5/14 as specified -- `test_paper_night_deadline.py`,
  `test_paper_night_deadline_1b.py`.
- **(e)** `test_paper_night.py:34`'s `deadline_s` pop reverted. **(f)**
  readiness handshake (`_Clock` double + fsynced marker wait, so a kill can
  never land before the child's first scheduler slice) --
  `test_paper_night_deadline_1b.py`. **(g)** A9 recomputed from disk each
  round. **(h)** two full SHAs with an EQUAL statement above; NOT VERIFIED
  last.

## FIX 1c -- every AMENDMENT 2 item, file:line, one-line reproduction

Governed by `_verdict_s470_1c.md` (VERDICT 1: codex sol REJECT, four BLOCKING +
one NOTE; VERDICT 2: Opus ACCEPT WITH CORRECTIONS, four corrections + four
notes) + spec AMENDMENT 2 (history; FIX 1d (3) below re-points citations this
round's own line drift touched).
- **(0)** identity check uses `proc.is_running()`, never stale `create_time()
  == create_time` -- `terminate_tree` (:134-139). Repro: psutil caches
  `create_time()`, so a `create_time+100` shim still passed the old comparison
  and was killed; `_1b.py:208`'s reused-pid construct now drives
  `_FakeProc(..., alive=False)`.
- **(a)** the S465 inherited-value exemption is WHOLE-MAP equality narrowed to
  the exact legacy three-name ceiling shape, never per-pair --
  `validate_deadline`, `_LEGACY_THREE_NAMES` (:35). Repro: ceiling
  `[fill_realism, qualification, week]` with `deadline_s={"scoreboard": "900"}`
  now REFUSES (was ACCEPTED). `deadline_override` deleted; docstring (:1-15)
  corrected.
- **(b)** identity capture moves INSIDE `poll_step`'s own try/finally, catches
  every `psutil.Error`, falls back to `_kill_via_popen_handle` (:180-204) when
  capture itself fails. Repro: `AccessDenied` shimmed at capture (`_1c.py:120`)
  now still kills the child within `TERMINATE_TIMEOUT_S`; before, the exception
  escaped `poll_step` and the child leaked -- a regression from master.
  Fallback `wait()` is bounded; `finish()`'s later untimed `wait()` is
  separate.
- **(c)** case 1 runs on deterministic Popen/process/running/finish doubles
  (`_DeterministicChildPopen`/`_DeterministicProcess`, `_1c.py:17-63`), never a
  real child; asserts BYTE equality (`json.dumps(...,
  sort_keys=True).encode("ascii")`). The override predicate is a separate pair
  of tests (`_1c.py:66-95`): `production_override` True under the new GATES /
  False under the pre-S470 three-gate predicate, and `main(steps=None)` exits 2
  `budget_override_refused` -- i.e. a legacy budget without `deadline_s`
  validates ONLY on the construct path, never in production (re-stated
  explicitly this round, FIX 1d (3)). Fixture provenance: see the disclosure
  above the pass-count table.
- **(d)** case 5's bound (`_1b.py:124`) is `poll_interval_s +
  TERMINATE_TIMEOUT_S + 0.5s` (minimal precision allowance), not the previous
  `+5s` slack. Case 2's wall bound already had zero slack.
- **(e)** S427 flakiness note below names
  `test_immediate_exit_peak_never_zero`; two full SHAs with EQUAL above; A9
  regenerated from disk as the last edit; NOT VERIFIED last; memo at or under
  300 lines.

## FIX 1d -- verdict findings, file:line, one-line reproduction

Governed by `_verdict_s470_1d.md`, round 3: TIER 1 (codex down, an independent
Opus critic reading the codex prompt) and TIER 2 (Opus), BOTH ACCEPT WITH
CORRECTIONS; no AMENDMENT written -- fixture/test/memo corrections only, this
row's own modules unedited this round.
- **(1)** case-1 fixture portability: `peak_method` was pinned literal
  `windows_peak_wset_polled+post_exit` (3x; POSIX uses `POLLED =
  "rss_polled"`). Repro: `grep -c windows_peak_wset_polled
  .../s470_case1_legacy_snapshot.json` = 3 (confirmed). Fix: case 1's
  normalisation loop now also replaces `deadline_mod.POLLED` with `<POLLED>`
  (S465's own mechanism, `test_paper_night_scoreboard_step.py:36`); fixture
  rewritten to `<POLLED>+post_exit` x3 -- no Windows-only value remains.
- **(2)** exact counts: `_1c.py`'s `kill_access_denied >= 1` and `_1b.py` case
  5's `kill_access_denied >= 1 and kill_survivors >= 1` loosened deterministic
  counts; fixed to `== 1` (`_kill_via_popen_handle` runs once per `poll_step`
  call; the SPAWN_GRANDCHILD tree has exactly one descendant).
- **(3)** memo citations corrected in FIX 1b (a)/(b) and FIX 1c (c) above.
- **(4)** disclosed, NOT code-fixed (NOTE-level, no BLOCKING/CORRECTION): a
  capture failure counts `kill_access_denied` only when cleanup runs -- a
  capture-denied child exiting normally first leaves the row RAN, no new keys
  (tier 2 finding 3). `_kill_via_popen_handle` (:190-204, verdict cite
  `:194-200`) counts `processes_killed` even for a child already exited before
  `kill()` ran (tier 1 finding 3). Unprobed: `is_running()`'s fresh
  `Process(pid)` re-read could itself raise `AccessDenied`, uncaught past
  `NoSuchProcess` at `:138`, leaving live descendants uncounted (tier 1 NOT
  VERIFIED). NEW GAPS for the register, unfixed.
- **(5)** `merge --ff-only master` at this round's start: already up to date;
  HEAD == master == `954323c99ba9a7741f98545d8ccc35b5eb6e72c6`, EQUAL. **(6)**
  this section; four owned test files re-run twice each, identical (20/9/3/39);
  seven unchanged S465 suites re-run once (50/25/8/14/4/2/1);
  `contract_preflight` 9/9 PASS; must-not-move empty; A9 regenerated last; NOT
  VERIFIED kept last.

## `--help` / `contract_preflight` / must-not-move

`python -m scripts.platformkit.execution.paper_night --help` exits 0.
`contract_preflight --paths <9 owned paths> --base master --spec
docs/evidence/tracking/specs/S470_spec.md`: PASS on all nine checks (vocab /
crlf / loc / schema / head_slice / spec_threshold / proposed / removed_artifact
/ row_duplication); `_1c.py` has no master baseline (new). Must-not-move
(`ingame_scoreboard.py`, `ingame_scoreboard_rules.py`, `paper_night_steps.py`,
`paper_night_lock.py`, `paper_night_peak.py`) diff-empty against master --
read, never written, by this row.

## A9 -- exact source identities (LF-normalised for the CRLF-tracked files
under `core.autocrlf`; header says so; recomputed from disk as the last edit)

| path | bytes (LF) | lines | sha256 (LF-normalised) |
|---|---|---|---|
| `scripts/platformkit/execution/paper_night_deadline.py` | 14592 | 293 | `df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b` |
| `scripts/platformkit/execution/paper_night.py` | 15420 | 285 | `52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a` |
| `scripts/platformkit/execution/paper_night_budget.json` (CRLF in worktree) | 1389 | 24 | `f6f287b5a8889152051a85de70f2ab6b386917c360448c474859bc04a05b0bc3` |
| `tests/platformkit/execution/test_paper_night_deadline.py` (FIX 1d: peak_method normalised, case 1) | 15810 | 299 | `3d28704d5c2826aafe8351c8e1a6871616a6e72ed71ed764dec500c5fb4002d6` |
| `tests/platformkit/execution/test_paper_night_deadline_1b.py` (FIX 1d: case 5 exact counts) | 13769 | 268 | `fd797e953540e37770d7211c480608b9cc4ea7228887995782851111bdca98e9` |
| `tests/platformkit/execution/test_paper_night_deadline_1c.py` (FIX 1d: exact count) | 6688 | 145 | `7e3c1b52be69925c4722500581ae579cc2d4b5a8e38085d0fac71a9bf723535c` |
| `tests/platformkit/execution/test_paper_night.py` (CRLF in worktree) | 17139 | 300 | `43b1f8bf59ad916e16ab43717d02bb30baa5492db65f34613cdb26dc718afaac` |
| `tests/platformkit/execution/fixtures/s470_case1_legacy_snapshot.json` (FIX 1d: peak_method portable) | 3312 | 97 | `5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084` |

(This memo is not self-hashed since its own bytes change with this table.)

## Owned-path list for the landing pathspec

```
scripts/platformkit/execution/paper_night_deadline.py
scripts/platformkit/execution/paper_night.py
scripts/platformkit/execution/paper_night_budget.json
tests/platformkit/execution/test_paper_night_deadline.py
tests/platformkit/execution/test_paper_night_deadline_1b.py
tests/platformkit/execution/test_paper_night_deadline_1c.py
tests/platformkit/execution/test_paper_night.py
tests/platformkit/execution/fixtures/s470_case1_legacy_snapshot.json
docs/evidence/harness/S470_paper_night_deadline_2026-09-25.md
```

`git status --short` shows exactly these nine paths (three modified, six
new/untracked); nothing else changed. `SHA: NOT CREATED (sandbox); files ready
for lane_commit.`

## NOT VERIFIED (honest, last)

- No real night was run and no real hang was observed on a genuine production
  step; every child in every test is a `python -c` fake.
- The four deadline values (900/600/300/900 s) are NOT PROFILED.
- Case 14's production-validates half runs `main(steps=None)` with `_steps`
  replaced by an all-skipped fake list, not a real spawn through the actual
  ~1.5 GB default ceilings -- construct-only, no real end-to-end run.
- `terminate_tree`'s parent-first order closes the respawn race the spec names,
  but a narrower race (a fresh descendant spawned in the instant between
  `children()` enumeration and the parent kill) is inherent to any signal-based
  teardown and not further bounded here; not observed, not exhaustively ruled
  out.
- Parent-only memory sampling (`_sample_peak`, pre-existing) still excludes
  descendant memory from the ceiling check -- a pre-existing register gap.
- Only the Windows kill/wait path (`os.name == "nt"`) was exercised; the POSIX
  branch in `paper_night_peak.py` (`running`/`finish`, unedited, unowned) was
  not exercised here -- on POSIX, `wait_procs` reaping the Popen parent would
  also lose `wait4`'s exit code and post-exit peak.
- The "never call unbounded `finish()`" guard is proven with a synthetic double
  that never exits, not a real genuinely-unkillable process (impractical to
  construct portably in a construct-only test).
- The readiness handshake still depends on real wall-clock patience for the
  marker poll (5 s) and a 15 s thread-join timeout; the deadline FIRING is
  fully clock-controlled and cannot race scheduling, but the readiness wait
  itself remains a real-time bound (not observed to time out in 3/3 runs).
- Case 5's cleanup-time bound is FIX 1c-tightened to `poll_interval_s +
  TERMINATE_TIMEOUT_S + 0.5s` (a minimal clock-precision allowance, corrected
  from the earlier `+ 5s` slack); still not measured-tight against a genuinely
  loaded host.
- The three pre-existing S427 load-sensitive legacy tests named by AMENDMENT
  1(f) -- `test_ceiling_kill_next_considered`,
  `test_post_exit_peak_catches_spike_between_polls`,
  `test_immediate_exit_peak_never_zero` (AMENDMENT 1(f)'s third test, corrected
  this round from the wrongly-named `test_runner_busy_across_dates` -- all in
  the unedited `test_paper_night.py`) -- are the likely source of any transient
  host flakiness reported for this row; they were not touched or clock-doubled
  here and remain a NEW GAP for the register.
- `git commit` was denied in this sandbox for the whole of this row; no commit
  was attempted -- files are left on disk for `lane_commit`.
- `TERMINATE_TIMEOUT_S = 2.0` is a fixed constant, not budget-configurable; no
  case in this row's 14 measured a survivor that needed the full timeout window
  (case 5's AccessDenied survivor is counted immediately).
