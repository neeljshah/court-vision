# S459 -- feasible late-game focus close under a per-night admission capacity cap

**BUILD RESULT (FIX 1e): 61 passed (33/9/17/2), preflight 9/9 PASS, artifact
sha256 `0bea24ee428c8ea9469d0c973860e5cfebc8bdeab327e8ebafd220f2c2d9ce2f`
(7753 bytes), must-not-move empty over all seven paths.**

Status: REPORT-ONLY PLANNING MODULE, opt-in, flag OFF. No scheduler, profile,
limiter or threshold is changed. `admit_and_close` has zero PRODUCTION callers
(capture_scheduler.py, local_capture_runner.py, any service or CLI outside this
row's own files); its callers are tests and this row's own report-only replay
CLI. Adoption is a later, owner-visible relaunch row.

Candidate HEAD (this worktree, after `git merge --ff-only master` at this
lane's start) = `git rev-parse HEAD`: `fda71b87f0452513059b4fa933af7967b6e76ff1`
Verification-base master (current, at memo time) = `git rev-parse master`:
`fda71b87f0452513059b4fa933af7967b6e76ff1`
**EQUAL** -- this lane's own fast-forward brought the worktree to the current
master tip before any FIX 1f edit; the candidate files themselves remain
untracked/uncommitted.

## A9 -- exact source inputs (path, bytes, sha256, resolution)

Regenerated fresh this session (LAST edit) by a throwaway script
(`raw.replace(b"\r\n", b"\n")` then sha256) -- byte-identical to every prior round.

| Input | Path (repo-relative) | Bytes (raw, on disk) | SHA-256 | Resolution |
|---|---|---|---|---|
| 2026-09-22 census | `docs/evidence/forward/observation_support/2026-09-22_census.json` | 601773 | `6547a2090aa9bc8b394a53d3cb388ff8c986f344822e9bfcc88fc7c322280aa6` | LF-normalised (worktree is LF, master is CRLF -- landing lesson 33); repo-relative path |
| 2026-09-24 census | `docs/evidence/forward/observation_support/2026-09-24_census.json` | 334435 | `c88a0474c7eb2e33651e8eb5a214c238119b7dccf317adf02353641f9c094f83` | LF-normalised; repo-relative path |
| S446 proposal text | `docs/evidence/harness/S446_PROPOSAL_focus_profile_2026-09-24.md` | 5718 | `7c201a7339cd3a758d9219dfd4a94c2a967f698a6985f8ce79c6dee2ba78725b` | LF-normalised; repo-relative path |

AMENDMENT 4(f): the Resolution column states the normalisation explicitly (the
house rule -- raw byte digests are not required). Schema/identity notes
(unchanged from FIX 1c): both censuses share the same top-level/row schema,
`duration_unit=integer_microseconds`, 3/4 game rows; the proposal references
amendments 1(j), 3(b), 4(a), 9(a), 9(b), 10(b).

`git diff --stat master --` over all seven must-not-move paths (below) is
empty (re-confirmed this session against current master).

## K derivation, step by step, reusing `concurrent_focus_fit` (never re-derived)

`_capacity_for_rate(rate)` calls `observation_support_census.concurrent_focus_fit(1, 1,
MARKETS_PER_GAME=2, tick_s, rate, focus_percent)`, `capture_scheduler.py`'s own
integer budget math (:147, :179) verbatim. `tick_s=5`, `focus_percent=45`, read
live from `forward_capture_profile.json`.

| rate | budget_per_tick = floor(rate*5) | allocated_per_tick = floor(budget*45/100) | K = floor(allocated/2) |
|---|---|---|---|
| 3.0 (AIMD CEILING) | floor(15) = 15 | floor(6.75) = 6 | 3 |
| 2.0 (AIMD start_rate) | floor(10) = 10 | floor(4.5) = 4 | 2 |
| 0.5 (AIMD FLOOR) | floor(2.5) = 2 | floor(0.9) = 0 | 0 |

`_capacity_for_rate` refuses `focus_percent` outside 0-100 and rates above the
3.0 ceiling or boolean rates; covered by tests.

## Construct tests

`test_focus_capacity_cap.py`: **33 passed**. `test_focus_capacity_cap_1c.py`:
**9 passed** (was 7; +2 this round: the AST one-public-callable construct,
the focus_percent=0 zero-allocation regression). `test_focus_capacity_replay.py`:
**17 passed** (unchanged pass count; permutation test tightened, CLI construct
strengthened, wait literals reformatted -- see FIX 1e below).
`test_focus_capacity_replay_1e.py`: **2 passed** (NEW file: construct W --
reporting snapshot at census as_of; the touching-window construct).
**Total: 61 passed** (was 57).

## Dry-run replay: one merged decision record per game per rate (AMENDMENT 4(a))

CLI: `python -m scripts.platformkit.ingame.focus_capacity_replay --census docs/evidence/forward/observation_support/2026-09-22_census.json --census docs/evidence/forward/observation_support/2026-09-24_census.json --out docs/evidence/forward/focus_capacity_cap/2026-09-25_dry_run.json`
Output SHA-256 BEFORE this round (FIX 1d): `9801a5df115b442c586eda9ccc1636f2d4c9490adf678d2afde7e785d2c4c331`
(7693 bytes). AFTER this round (FIX 1e, two runs, byte-identical):
`0bea24ee428c8ea9469d0c973860e5cfebc8bdeab327e8ebafd220f2c2d9ce2f` (7753 bytes;
+60 bytes, entirely AMENDMENT 5(e)'s six-decimal-place `capacity_wait_s`
formatting on every zero-wait entry -- `"0.0"` -> `"0.000000"`; every
disposition tally, coverage tally and non-zero wait verified unchanged, see
FIX 1e below). Record shape otherwise unchanged from FIX 1d: one record per
`by_rate[rate]["games"][game_id]` carrying `decision_reason`,
`capacity_wait_s`, `planned_close`, `observation_end` and `coverage_status`
together. `disposition_tally` and `admitted_after_capacity_wait` are
unchanged, derived from the merged records.

**The real numbers do not move** (locked literals, re-verified this round):

### 2026-09-22 (3 served games: 823412, 824624, 824785)

| rate | K | disposition | capacity_wait_s (non-zero only) |
|---|---|---|---|
| 3.0 | 3 | all 3 admitted_and_closed | none |
| 2.0 | 2 | all 3 admitted_and_closed | 824624 waits 6197.047936 s behind 823412's close |
| 0.5 | 0 | all 3 capacity_dropped | n/a (none ever admitted) |

### 2026-09-24 (4 served games: 822842, 823411, 824707, 824866)

| rate | K | disposition | capacity_wait_s (non-zero only) |
|---|---|---|---|
| 3.0 | 3 | all 4 admitted_and_closed | none |
| 2.0 | 2 | all 4 admitted_and_closed | 824866 waits 6589.620704 s behind 823411's close |
| 0.5 | 0 | 3 capacity_dropped (823411, 824707, 824866) + 1 expired (822842) | n/a |

822842 stays `expired` under the AMENDMENT 4(b) overlap clause: it closes at
21:12:29.857231Z, hours before the other three even open (22:03/22:43/23:13Z),
and no other game's `[open_at, close_hint)` window ever overlaps its own.
FIX 1e correction (Opus round 4, finding 3): the real archived data exercises
ONLY the no-overlap -> `expired` branch (822842); the overlap ->
`capacity_dropped` branch (a
game that genuinely loses a real capacity contest) has no real-archive
exercise and is covered by the AMENDMENT 4(b) A/B/C/D construct alone
(`test_never_admitted_overlapping_window_is_capacity_dropped_not_expired`).

## Coverage status: "uncovered" (AMENDMENT 2(b), unchanged this round)

A resolved close with zero post-final support is `uncovered`, never `partial`.
2026-09-22 `coverage_tally`: `partial: 1, unresolved: 2`, matching the census
exactly. 2026-09-24: `uncovered: 4`, matching the census exactly. Both checked
against their own census in `test_focus_capacity_replay.py`. A future
`observation_end` is excluded (`future_observation_end`), never certifying
`covered` from data that had not happened yet; `as_of > now` never changes
admission, only reporting. FIX 1e (AMENDMENT 5(d)): the per-game coverage
fields (`planned_close`, `observation_end`, `coverage_status`) now come from
one extra `admit_and_close` call at `now=ticks[-1]`, `as_of=census["as_of"]`
(`focus_capacity_replay.py:152-159`) rather than the last tick's own call
(`as_of=tick`), so an `observation_end` later than the night's final tick is
no longer dropped as `future_observation_end`. Both real archives' own
`observation_end` values precede their night's final tick, so neither
coverage tally above moves; the new behaviour is proven only by construct W
(`test_reporting_snapshot_uses_census_as_of_not_last_tick`).

## Theoretical capacity vs. actual requests; call signature; integration seam

`_capacity_for_rate` computes a THEORETICAL budget from rate/profile shares
only; `total_requests` stays `None` in every census row, so every game in
every dry-run is `request_budget_unmeasured` (3 on 2026-09-22, 4 on 2026-09-24).
`admit_and_close(games, *, rate, now, as_of=None, admitted=(), tick_s=None,
focus_percent=None) -> dict`. Not called by `capture_scheduler.py`,
`local_capture_runner.py`, or any service/runner (unchanged); adoption is a
later, owner-visible relaunch row.

## FIX 1b / FIX 1c / FIX 1d -- prior rounds, condensed (full detail superseded by FIX 1e)

FIX 1b (round 1): chronological tick-by-tick walk replaces the old one-snapshot
design (822842 no longer lands in no bucket); input validation hardened
(`focus_percent`, market pairs, duplicate ids, hindsight guard); `uncovered`
status added; `capacity_reduced`/`capacity_dropped` double-counting fixed.

FIX 1c (round 2): `_receipt_dt` refuses float/bool instead of silently
truncating; `_hint` moved onto the shared venue parser (4-/5-digit fractions);
`markets=None`/unhashable entries refuse `incomplete_market_pair` instead of
crashing; the `expired` class added (AMENDMENT 3(a), 822842 case); `games_out`
built over `sorted(parsed)` for permutation-stable bytes; `test_03`/`test_19`
tautology and cwd-dependence fixed.

FIX 1d (round 3): one merged per-game decision record (`decision_reason` +
`capacity_wait_s` + close/coverage fields together, was three parallel maps);
the `expired`/`capacity_dropped` overlap clause (`_overlaps_any_other`); one
shared `scheduled_start` parser between the planning module and the replay (a
7+-digit fraction refuses `invalid_scheduled_start`); the whole-CLI-run
fail-closed receipt-refusal scope documented and tested; a replay-level
census-row permutation BYTES test and naive/offset `scheduled_start` coverage
added.

## FIX 1e -- every FIX-1d-round verifier finding and what changed (this round)

**Tier 1 (sol), round 4: 2 BLOCKING, 1 CORRECTION:**
1. BLOCKING -- AST inspection of `focus_capacity_cap.py`'s public names
   returned `['scheduled_start_epoch', 'admit_and_close']`, two callables
   against the spec's ONE. Fix: renamed to `_scheduled_start_epoch`
   (`focus_capacity_cap.py:114`, used at `:184`); `focus_capacity_replay.py`
   imports and calls the private name (`:58-59`, `:110`). Test
   `test_module_has_exactly_one_public_callable` (AST construct,
   `test_focus_capacity_cap_1c.py`).
2. BLOCKING -- the AMENDMENT 4(d) CLI construct
   (`test_cli_refuses_float_terminal_receipt_s_no_artifact`) proved only a
   missing single output, not the refusal JSON or the absence of a *combined*
   two-night artifact. Fix: the test now runs one valid census plus one
   float-receipt census in a single CLI call, asserts exit 3, stdout EXACTLY
   `{"refused": 1, "reason": "invalid_receipt_microseconds"}` (`capsys`), and
   `not out.exists()` for the combined `--out` path
   (`test_focus_capacity_replay.py:223-244`). No code change -- `main()`
   already aborts the whole run on the first refusal; only the test was weak.
3. CORRECTION -- `focus_percent=0` (a documented valid 0-100 input) was
   rejected as `invalid_capacity_input` because the delegated (must-not-move)
   `concurrent_focus_fit` refuses `focus_percent<=0` outright. Repro
   reproduced pre-fix: `capacity=0, capacity_fit=None,
   refusal_counts={'invalid_capacity_input': 1}`. Fix: `_capacity_for_rate`
   (`focus_capacity_cap.py:88-111`) special-cases `focus_percent==0` by
   probing the delegated function at 100% (where its own formula reduces to
   `budget_per_tick` exactly, still validating `rate`/`tick_s`) and
   recomputing only the percent-dependent fields with that SAME mirrored
   formula for the real 0%, never re-deriving it and never editing the
   must-not-move module. Post-fix: `capacity=0, refusal_counts={}`. Test
   `test_focus_percent_zero_is_valid_zero_allocation_no_refusal`.

**Tier 2 (Opus), round 4: 3 CORRECTIONS, 4 NOTES:**
1. CORRECTION -- the per-game coverage fields came from the LAST tick's own
   `admit_and_close` call (`as_of=tick`), so an `observation_end` later than
   the night's final tick was dropped as `future_observation_end` and a
   covered game reported `uncovered`. Repro (construct W: start
   2026-09-22T20:00:00Z, terminal 22:00:00Z, POST_FINAL receipt 22:10:00Z,
   rate 3.0) pre-fix: `observation_end: None, coverage_status: "uncovered"`.
   Fix: one extra `admit_and_close` call at `now=ticks[-1]`,
   `as_of=census["as_of"]` (`focus_capacity_replay.py:152-159`) supplies the
   snapshot; admission itself is untouched (the HINDSIGHT GUARD already
   bounds `as_of > now` to reporting only). Post-fix: `coverage_status:
   "covered", observation_end: <22:10:00Z>`. No real number moves (see
   Coverage status section above). Test
   `test_reporting_snapshot_uses_census_as_of_not_last_tick`.
2. CORRECTION -- the memo did not open with the build result. Fix: this
   file's first line after the title now states the pass counts, preflight,
   artifact sha256 and must-not-move status.
3. CORRECTION -- the overlap-clause wording claimed real archives exercise
   the clause without distinguishing branches. Fix: reworded under the
   2026-09-24 real-numbers table above -- only the no-overlap branch (822842)
   is real-archive-exercised; the overlap branch is construct-only.
4. NOTE -- the stale `n = 19+` in NOT VERIFIED. Fixed below to the real count.
5. NOTE -- the replay-level permutation test serialised with `sort_keys=True`,
   masking a genuine dict-order dependence. Fix: `sort_keys` dropped
   (`test_focus_capacity_replay.py:247-255`); still passes, confirming
   `replay_night`'s own `dict(sorted(...))` calls already make it
   order-independent.
6. NOTE -- touching-window semantics (half-open intervals: two windows
   touching at one instant do not overlap) were unlocked by any test. Fix:
   `test_touching_windows_are_not_overlapping_both_expired_at_rate_05`
   (`test_focus_capacity_replay_1e.py`) -- X closes exactly when Y opens,
   both come out `expired`, never `capacity_dropped`.
7. NOTE -- `capacity_wait_s` printed `"0.0"` for a zero wait versus six-place
   fractions for non-zero ones. Fix: every wait is now
   `.quantize(Decimal("0.000001"))`-formatted (`focus_capacity_replay.py:182`);
   the artifact and all four locked wait-literal dicts in
   `test_focus_capacity_replay.py` updated to `"0.000000"`.

## FIX 1f -- corrections applied this round (memo-only; code semantics unchanged)

Round 5: codex sol ACCEPT (0 corrections, 3 NOTEs); Opus tier 2 ACCEPT WITH
CORRECTIONS (1 CORRECTION, 5 NOTEs). Both verdicts bind the code as accepted;
nothing below changes `admit_and_close`'s behavior or its numbers.

1. CORRECTION -- header (was lines 13-17): the candidate HEAD / verification-base
   master shas were stale and self-contradictory (labelled EQUAL while showing
   two different shas, with prose still describing a pre-rebase divergence).
   Fix: this lane's own `git merge --ff-only master` brought HEAD to
   `fda71b87f0452513059b4fa933af7967b6e76ff1`, identical to master; both shas
   above are printed exactly as `git rev-parse` returned them this round, the
   stale divergence prose is removed, and the NOT VERIFIED sha bullet below
   now agrees.
2. NOTE -- was lines 107-109: "plus the new touching-window construct X/Y/Z"
   dropped from the real-archive parenthetical; the sentence now claims only
   that real archived data exercises the no-overlap branch (822842). The
   touching-window construct is still covered (FIX 1e item 6 above) -- it was
   never real-archive data.
3. NOTE -- `focus_capacity_cap.py` gained an explicit
   `__all__ = ["admit_and_close"]` (no other change), matching the
   AST-verified single-public-callable claim (AMENDMENT 5(a)).
4. NOTE -- `test_focus_capacity_replay_1e.py:34`'s float-derived expectation
   (`str(us / 1_000_000)`) replaced with the literal `"1790115000.0"` it
   already evaluated to; no behavior change.

## NEW GAPS (for the register, not this row)

- No test ties the zero-percent mirror in `_capacity_for_rate`
  (`focus_capacity_cap.py:102-109`, `allocated = 1 if budget_per_tick == 1
  else 0`) to `capture_scheduler.py:179`'s own formula; if `:179` changes,
  this mirror drifts silently (Opus round 5 finding 3).
- Carried from AMENDMENT 5: the overlap-to-`capacity_dropped` branch has no
  real-archive coverage; games first admitted after start+3600 (both real
  rate-2.0 waits) are still reported `admitted_and_closed`.

## NOT VERIFIED

- No production integration: `admit_and_close` is not wired into
  `capture_scheduler.py` or any runner (intentional; see integration seam above).
- The real, un-replayed exposure is an AIMD RATE CHANGE mid-window: each rate
  here is held fixed for the whole night, so a crunch strictly between two
  schedule-event ticks cannot arise for a fixed rate (the event-tick caveat),
  but a live AIMD rate change between instants was never replayed.
- The replay's `markets` pair is SYNTHESIZED (`ticker`, `ticker + ":paired"`);
  `incomplete_market_pair` is exercised only by construct tests. `expired`
  (the no-overlap branch) IS exercised by real archived data (822842); the
  overlap -> `capacity_dropped` branch has no real-archive exercise and is
  covered by the AMENDMENT 4(b) construct alone (FIX 1e, carried as a NEW GAP
  per AMENDMENT 5's closing line).
- `total_requests` is `None` for every real game in both archives; no real
  request-sufficiency comparison against the AIMD rate was possible.
- No walk-forward, no CPCV, no ledger, no scored metric: `n = 61` (CONSTRUCT,
  the real total test count this round, replacing the stale `n = 19+`), not a
  sampled or scored measurement; Q4/Q5 do not apply.
- `git rev-parse HEAD` and `git rev-parse master` are EQUAL (see header, this
  round's own fast-forward); this has not been re-checked against whatever
  master tip exists at actual landing time.
- Must-not-move (all seven, confirmed empty this round): `capture_scheduler.py`,
  `local_capture_limiter.py`, `observation_support_census.py`,
  `observation_support_phases.py`, `scripts/platformkit/execution/venue_time.py`,
  `docs/evidence/forward/observation_support/2026-09-22_census.json`,
  `docs/evidence/forward/observation_support/2026-09-24_census.json`.
- No real multi-receipt archive (repeated finals, differing states) or
  multi-market-row archive was exercised; `final_receipt_conflict` and the
  consistent-repeated-receipt path remain construct-only.
