# S438 schedule pointer candidate

FIX 1c: AMENDMENT 1 (a)-(i) -- folding the Opus tier 2 REJECT and the codex sol
REJECT of FIX 1b -- is now landed on top of FIX 1b in this worktree
(C:/Users/neelj/nba-harness-h93). All 14 originally enumerated acceptance
cases still pass, plus 11 new AMENDMENT 1 regressions in
`test_capture_schedule_pointer_1c.py` (see FIX 1c below and Verification).
This remains a LOCAL CONSTRUCT-LEVEL result only: no commit, no push, HEAD
unmoved, no live relaunch. Ends NOT VERIFIED; see the final section.
The binding spec is docs/evidence/tracking/specs/S438_spec.md.
Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md, sections B and Q.
The alternative docs/evidence/VERIFIER_CONTRACT.md path supplied in the request is absent.

## Scope conflict (RESOLVED by this fix lane)

The prior candidate's build prompt said "edit no pre-existing module", which
blocked the spec-required additive edits. This fix lane was explicitly
authorized to make exactly the additive edits CHANGE 1/2/3 and the
ORCHESTRATOR ADJUSTMENTS name, and nothing else. capture_schedule_loader.py,
local_capture_runner.py, polymarket_live_capture.py and schedule_d1.py are now
edited, additively only -- see FIX 1b and FIX 1c below and the A9 identities.
No registry, running capture, feature flag, other worktree, network service
or pod was changed. No commit, no push; `git rev-parse --short HEAD` =
aac8a5b86 (unmoved across FIX 1b and FIX 1c; the worktree's base advanced to
this commit -- the master tip at FIX 1c time -- between the two fix sessions,
outside this row's control).

## Binding before-condition

Executed before coding using a local Python read-only probe over all six named
landed files: print HEAD, len(text.splitlines()), SHA256, relevant source lines,
and whether the heartbeat function contains pointer identity. Output verbatim:

```text
BINDING BEFORE-CONDITION (local checkout)
HEAD=afccd1a52b697296bbb9e9f6782cbc325559c5ca
scripts/platformkit/ingame/capture_schedule_loader.py: LOC=35 SHA256=c3bfbd84fb67fc19cb8b7b4ea01fdb1ce8558e5420f79df807c64919bd566c5d
20: if "schedule_path" not in state or clock_value - state.get("schedule_read_at", -float("inf")) < 60: return
21: state["schedule_read_at"] = clock_value
24: raw = Path(state["schedule_path"]).read_bytes()
scripts/platformkit/ingame/local_capture_runner.py: LOC=300 SHA256=c8e84178c93eeb6f3e44fa9575847c5234d0436389220014023967ff39f09452
245: if scheduler_enabled and schedule is not None: state["schedule_path"] = Path(schedule)
259: if scheduler_enabled and schedule is not None: state["schedule_path"] = Path(schedule)
278: parser.add_argument("--schedule", type=Path, default=argparse.SUPPRESS, help="Prospective schedule JSON list")
scripts/platformkit/ingame/capture_scheduler.py: LOC=300 SHA256=0f959fd63f79c12823c00afeb2c92befffb1f6c0d2d5d7a75b5d52d1892abf59
99: if not isinstance(rows, list): raise ValueError("schedule must be a list")
heartbeat_fields pointer identity absent=True
scripts/platformkit/ingame/polymarket_live_capture.py: LOC=269 SHA256=ac417ddc2ae396c03330162d5a3a6924aa7d833181dda4f92d701d5f6811aae7
227: state = {"prospective": load_prospective(schedule, client.metrics.errors)}
249: parser.add_argument("--schedule", type=Path, help="S386 prospective schedule JSON list")
scripts/platformkit/execution/schedule_d1.py: LOC=258 SHA256=0f37ae7b9051a837ffe211fd15bde80da175d6a22b821297aea2b45149027c87
173: full = args.out_dir / f"{day}_{args.family}_full_selection.json"
174: served = args.out_dir / f"{day}_{args.family}.json"
176: note_path = Path(str(served) + ".capacity_note.json")
177: run_path = args.out_dir / f"{day}_run.json"
scripts/platformkit/execution/forward_schedule_writer.py: LOC=297 SHA256=db5c35fd16cdcfb4f53510520cb6702344d70dec30c49e5ec630b80e89aeaefa
284: parser.add_argument("--schedule-source", choices=("live", "archive"), default="live")
PREMISE CONFIRMED: fixed paths; separate pointer format needed; loader gate 60s; both books files at cap.
```

The spec's older reference HEAD differs from this checkout; the substantive
fixed-path premise still holds. Historical test counts quoted in the spec were
not re-run: only the newly created per-file test was run, as requested.

## Interfaces read before coding

The following landed modules were read in full before the new code was written.
The exact signatures used by the new modules and construct test are:

```python
# scripts/platformkit/ingame/capture_schedule_loader.py
def _forward_config(state: dict, now, clock_value, writer, metrics) -> None:
# scripts/platformkit/ingame/capture_scheduler.py
def timestamp(value: object) -> Decimal:
def count(value: object) -> int:
def schedule_rows(rows: list, now, errors: Counter) -> list:
def plan_tick(now, rate_per_sec, markets, focus_state, params) -> TickPlan:
# scripts/platformkit/ingame/local_capture_time.py
def iso(value: Optional[datetime] = None) -> str:
# scripts/platformkit/execution/venue_time.py, used through timestamp
def parse_venue_time(value: object) -> float | None:
```

timestamp delegates grammar checking to parse_venue_time and reconstructs
nanoseconds as Decimal from the input string. The helper fixes precision at 40
for timestamp validation. No quantities, prices, sizes or fees are consumed by
the new modules. Counters use the landed strict-int count validator.
All runtime input files are temporary constructed JSON, with no video resolution
applicable. The spec supplies no REAL ROW. The first test consumes the constructed
schedule fixture through the unchanged loader end to end with the flag off.

## Candidate behavior and remaining wiring

scripts/platformkit/ingame/schedule_pointer.py validates a separate pointer,
checks its target hash, validates visible schedule rows, retains open focus
windows, and exposes a Polymarket refresh helper at a sixty-second cadence.
Future written_at values precede pointer schema checks; future selected_at rows
precede row identity/duplicate checks. Refusals retain previous state. Identical
rows across old/new selections form the specified union; conflicting overlaps
and duplicate records within a selection are refused.

scripts/platformkit/execution/schedule_pointer_writer.py provides write_pointer
and a CLI. It validates paths and supplied digests, writes a unique temporary
file, checks the write length, flushes, fsyncs, and atomically replaces the pointer.
A failure before replacement leaves an existing pointer intact.

A separate --schedule-pointer flag is required because schedule_rows accepts a
bare list, whereas the pointer has exactly four metadata keys. Reusing --schedule
for the pointer would change the served-file format relied upon by existing readers.
The helper supplies both the draft's schedule_pointer_* heartbeat field names and
the amendment's pointer_* names; both are merged into the on-disk heartbeat by
FIX 1c (see below).

local_capture_runner.py remains at 299 lines (1 under the cap) after FIX 1c's
one-line heartbeat-merge change (net 0 LOC). The S429 --write-pointer call runs
after the served/run files exist, at a pointer path under the local capture
root (see FIX 1c item h).

## FIX 1b (integrations)

| Spec item | File:line | Test |
|---|---|---|
| CHANGE 1 (loader) | `scripts/platformkit/ingame/capture_schedule_loader.py:7` new import `schedule_pointer`; `:26` `pointer_hit = bool(state.get("schedule_pointer_path")) and schedule_pointer.read_schedule_pointer(...)`; `:34-35` `if not pointer_hit: state["forward_schedule"] = scheduler.schedule_rows(...)` (the plain re-read no longer clobbers a pointer-unioned result); `:40` `state["schedule_sha256"] = digest` | `test_capture_schedule_pointer.py::test_01,02,03_to_09,10,12,13` |
| CHANGE 2 / ORCH (i) Kalshi runner | `scripts/platformkit/ingame/local_capture_runner.py:231` heartbeat merge `state["hb"][sport].update(state.get("schedule_pointer_heartbeat", {}))` inside `_scheduled_tick`; `:234,242` new `schedule_pointer=None` kwarg + seed line in `capture_once`; `:248,257` same pair in `run_local_capture`; `:277` new `--schedule-pointer` argparse entry | `test_capture_schedule_pointer.py::test_11,12` (heartbeat/rollover through the shared loader); `test_local_capture_runner.py` and `test_capture_scheduler.py` re-run unchanged (flag-off proof, see Verification) |
| ORCH (i) Polymarket capture | `scripts/platformkit/ingame/polymarket_live_capture.py:14` new import `schedule_pointer as pointer_hub`; `:145-146` `if state.get("schedule_pointer_path"): pointer_hub.refresh_polymarket_pointer(state, now, clock(), client.metrics.errors)` at the top of `capture_once`; `:214` heartbeat merge `value.update(state.get("schedule_pointer_heartbeat", {}))` in `_publish`; `:221,233` kwarg + seed line in `run_capture`; `:256,268` `--schedule-pointer` argparse entry + `main()` wiring | `test_capture_schedule_pointer.py::test_polymarket_refresh_cadence_and_refusal`; `test_polymarket_live_capture.py` re-run unchanged (flag-off proof) |
| ORCH (iii) writer | `scripts/platformkit/execution/schedule_d1.py:17` new import `write_pointer`; `:143-144` `--write-pointer` argparse flag; `:249-255` after `os.replace` makes served/run live, `write_pointer(pointer_path, served, day, sha256=files[served.as_posix()]["sha256"], now=completed)` and the pointer path is appended to the WRITTEN status when the flag is set | `test_schedule_d1.py` re-run unchanged (flag off by default; no dedicated `--write-pointer` case exists yet -- see NOT VERIFIED) |
| ORCH (ii) midnight in-flight | shared union logic in `scripts/platformkit/ingame/schedule_pointer.py::union_open_rows`, exercised end-to-end through the loader | `test_capture_schedule_pointer.py::test_11_rollover_preserves_focus_until_close` |

### LOC-cap trim (local_capture_runner.py)

`local_capture_runner.py` was at 300 LOC (the cap) before this fix. An existing
landed test, `test_capture_scheduler.py::test_fix1b_runner_unrelated_source_unchanged`,
source-compares `_unique_tickers`, `_markets`, `_book`, `_bulk`, `_trade`, `_tick`,
`_Deadline`, `_discover_page` and `main` against master byte-for-byte, so the
cosmetic trim was restricted to the three untouched-by-that-test callables that
also carry the new wiring: `_scheduled_tick`, `capture_once`, `run_local_capture`
(three short `if`/`except` blocks in `_scheduled_tick` joined onto fewer physical
lines with `;` and single-line `if cond: stmt`, no other file touched). AST
equality of the whole file (docstrings stripped, `ast.dump` compared) between the
before-copy at
`C:/Users/neelj/AppData/Local/Temp/claude/C--Users-neelj-nba-ai-system/bb506bbc-d9b2-4cd2-8c67-c64911a671a9/scratchpad/local_capture_runner.BEFORE.py`
and a trim-only reconstruction (same scratch dir,
`local_capture_runner.TRIMONLY.py`, wiring not yet applied) is **True** --
verified before any wiring line was added. The file is 299 LOC after both the
trim and the wiring (`wc -l`), 1 line under the cap.
`test_fix1b_runner_unrelated_source_unchanged` was re-run after the full edit
and passes (see Verification), confirming the nine protected callables are
still byte-identical to master.

## Verification (re-run after FIX 1c, this session)

Each command run singly, per-file only (never the full suite):

```text
test_capture_schedule_pointer.py            -> 35 passed   (2 fixtures amended for day-validation, see FIX 1c)
test_capture_schedule_pointer_1c.py         -> 11 passed   (NEW, all AMENDMENT 1 regressions)
test_capture_scheduler.py                   -> 151 passed  (includes test_fix1b_runner_unrelated_source_unchanged)
test_local_capture_runner.py                -> 8 passed
test_local_state_capture_schedule.py        -> 367 passed
test_polymarket_live_capture.py             -> 18 passed
test_polymarket_live_json.py + _link + _relink + _rows + _trades -> 146 passed (combined)
test_schedule_d1.py                         -> 46 passed    (unchanged count from the before-condition)
test_local_capture_fix1c.py                 -> 24 passed   (unrelated S341 file; sanity re-run only, not in this row's scope)
```

All fourteen originally enumerated acceptance cases still pass inside
`test_capture_schedule_pointer.py` (35/35, no case rewritten or deleted, two
fixtures' input data amended -- see FIX 1c). The eleven AMENDMENT 1
regressions in `test_capture_schedule_pointer_1c.py` cover items (a), (b),
(c) x2, (d), (e), (f), (g) x4.
`test_fix1b_runner_unrelated_source_unchanged` (in `test_capture_scheduler.py`)
passing is the flag-off byte-identical proof for the nine protected callables
in `local_capture_runner.py`; the other five re-run suites above
(526 tests across `test_local_capture_runner.py`,
`test_local_state_capture_schedule.py`, `test_capture_scheduler.py`, and
`test_polymarket_live_capture.py`) call `capture_once` / `run_local_capture` /
`run_capture` without the new `schedule_pointer` kwarg and are the flag-off
byte-identical proof for `capture_once`, `run_local_capture`,
`_scheduled_tick`, `run_capture` and `_publish` -- none of these tests, or the
production callables they exercise, were changed, and all still pass.
No dedicated construct exercises `schedule_d1.py --write-pointer` itself
(flagged below).

CLI help smoke check, all exit 0 and now show the new flags:

```text
python -m scripts.platformkit.ingame.local_capture_runner --help      # --schedule-pointer present
python -m scripts.platformkit.ingame.polymarket_live_capture --help   # --schedule-pointer present
python -m scripts.platformkit.execution.schedule_d1 --help            # --write-pointer present
```

Preflight re-run with --base master and the S438 spec, over all eight edited/new
files (including the new `test_capture_schedule_pointer_1c.py`): **9 PASS, 0
FAIL** (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed,
removed_artifact, row_duplication).

`git diff --stat HEAD` (HEAD = aac8a5b86, unmoved) touches exactly the four
authorized files: `capture_schedule_loader.py` (+21/-2 lines changed vs the
FIX-1b tip), `local_capture_runner.py` (net 0 LOC, one line changed),
`polymarket_live_capture.py` (one line changed), `schedule_d1.py` (+4 lines:
`POINTER_ROOT` constant + mkdir + the changed pointer-path source). `git
status --short` shows those four modified plus five untracked candidate
files (`schedule_pointer.py`, `schedule_pointer_writer.py`,
`test_capture_schedule_pointer.py`, `test_capture_schedule_pointer_1c.py`,
this memo); nothing else. `git diff --stat master` additionally lists
unrelated docs/spec files that differ between this worktree's HEAD and the
current `master` ref (`master` has advanced to a different, newer commit than
this worktree's HEAD since FIX 1b, from other lanes) -- not touched by this
fix, confirmed by the clean `git diff --stat HEAD` above.

### A9 identities (bytes + sha256, this session, regenerated from the tree)

```text
HEAD = aac8a5b86 (unmoved)
capture_schedule_loader.py      LOC=50  bytes=3350  sha256=2118549432ef87403e7c2a2befc0fbe757aebbc162039f29755a2e2930fb59ca
local_capture_runner.py         LOC=299 bytes=18288 sha256=aba3a145b79b08522f9cb625611c0062a8d2a3157653eb2bb43761e267c8a091
polymarket_live_capture.py      LOC=276 bytes=15122 sha256=593592a4f3615b984f1c28edaefedcbf81cd63a61a5dd1c524e89365ce9a6a5c
schedule_d1.py                  LOC=270 bytes=13591 sha256=2e97bbdc574c017c5c7420f5e3d44df29c48c89d52454697a6a72848b9a82318
schedule_pointer.py             LOC=187 bytes=8880  sha256=12cc8f5af225e2ad6cfe783826c9210c4ede9e35cefe40b196fd1c31d6927541
schedule_pointer_writer.py      LOC=70  bytes=2975  sha256=094d6f951e2c5afcb3deaee9f85cf923090673b6c6f77c7e86ba44b0bc2a7c91   (unchanged from FIX 1b)
test_capture_schedule_pointer.py LOC=238 bytes=10551 sha256=a690ab21e7c734c485b43f301c2173572253188b734d7f1d655a030c3caf3d62 (2 fixtures amended, see FIX 1c)
test_capture_schedule_pointer_1c.py LOC=170 bytes=7877 sha256=95ed40864e0d60ce14ce0ca82d5fe3b8b5f6e2828988dd3c9b7f7693be57aa40 (NEW)
```

## FIX 1c (AMENDMENT 1)

Every AMENDMENT 1 item (a)-(i) is landed on top of FIX 1b, additively, in the
same four authorized files plus `schedule_pointer.py` (candidate set, not
capacity-limited the way the four landed files are).

| Item | File:line | Test |
|---|---|---|
| (a) carry, no lower bound | `schedule_pointer.py:82-94` `union_open_rows`: `carry = [r for r in prior if at < instant(r["scheduled_start"]) + 3600]` (the old `start - 120 <=` lower bound is gone -- a not-yet-open row is carried no matter how far ahead it starts; a row past `start + 3600` is never carried, so a closed row is never resurrected) | `test_capture_schedule_pointer_1c.py::test_far_future_prior_row_survives_afternoon_pointer` (pointer written 8h before D's start) |
| (b) refusal never destroys the union | `capture_schedule_loader.py:21-22` `has_source` gate now admits pointer-only state; `:31-36` `pointer_hit` is `True` once `schedule_pointer_ever_resolved` is set, even on a refused attempt, so the `if not pointer_hit:` plain re-read at `:44` is skipped and `forward_schedule` keeps the last resolved union; `schedule_pointer.py:165` sets `schedule_pointer_ever_resolved=True` on success | `test_capture_schedule_pointer_1c.py::test_refusal_after_switch_keeps_union_until_close` (refusal mid-window keeps D+N; a later successful resolve past D's close drops D) |
| (c) bootstrap from the pointer alone | `capture_schedule_loader.py:21` `has_source` is true on `schedule_pointer_path` alone (no `schedule_path` needed); `:35-36` `if not pointer_hit and "schedule_path" not in state: return` -- an unresolved bootstrap is a named, counted refusal, never a silent, unrecorded no-op | `test_capture_schedule_pointer_1c.py::test_bootstrap_from_pointer_alone_seeds_schedule_path`, `::test_bootstrap_never_silent_when_pointer_unresolved` |
| (d) cross-midnight capacity | `schedule_pointer.py:65-79` `_admit_capacity`: carried rows seed `accepted` unconditionally; each NEW candidate is trial-added and only dropped (counted `pointer_capacity_refused`) if it alone breaks `capture_scheduler.schedule_rows`'s two-games-per-hour rule -- that landed function is called, never edited | `test_capture_schedule_pointer_1c.py::test_cross_midnight_capacity_refuses_only_failing_new_rows` (D carried + 2 new within the hour -> 1 new admitted, 1 refused) |
| (e) day validated | `schedule_pointer.py:42,55-58` `_rows(..., day)`: every visible row's `scheduled_start` UTC calendar date must equal the pointer's declared `day`, else `pointer_day_mismatch`; `:139-144` the reason is threaded out of the nested `_rows` call distinctly from the generic `pointer_schedule_refused` bucket | `test_capture_schedule_pointer_1c.py::test_day_mismatch_named_refusal`; required two pre-existing `test_capture_schedule_pointer.py` fixtures to gain an explicit matching `scheduled_start` (see below) |
| (f) heartbeat truth | `schedule_pointer.py:155-160` (failure) and `:166-168` (success) write `state["schedule_pointer_health"]` = `{schedule_pointer_refusals_total, schedule_pointer_last_reason, pointer_read_at}` every attempt, `pointer_ok_at` only on success (carried forward otherwise); `local_capture_runner.py:231` and `polymarket_live_capture.py:214` merge `schedule_pointer_health` into the on-disk heartbeat alongside the existing `schedule_pointer_heartbeat` (single-line change, net 0 LOC in the runner) | `test_capture_schedule_pointer_1c.py::test_heartbeat_health_tracks_every_attempt_and_last_success` |
| (g) CLI/writer constructs | `local_capture_runner.py` `capture_once`/`run_local_capture` (unchanged seed lines, already landed in FIX 1b); `polymarket_live_capture.py` `run_capture` (unchanged seed line); `schedule_d1.py:253,255` pointer write after served/run exist | `test_capture_schedule_pointer_1c.py::test_capture_once_seeds_schedule_pointer_path`, `::test_run_local_capture_seeds_schedule_pointer_path`, `::test_polymarket_run_capture_seeds_schedule_pointer_path`, `::test_schedule_d1_write_pointer_after_served_and_run_exist` (asserts the served file and `<D1>_run.json` already exist at the moment `write_pointer` is called, plus a correct sha256) |
| (h) pointer lives outside tracked evidence | `schedule_d1.py:27` `POINTER_ROOT = ROOT / "data" / "cache" / "schedule_pointers"` (a sibling of `local_capture_runner.ARCHIVE_ROOT`, never `args.out_dir`); `:253` pointer path now built from `POINTER_ROOT`, not `args.out_dir`; `:255` `pointer_path.parent.mkdir(parents=True, exist_ok=True)` only when `--write-pointer` is set | `test_capture_schedule_pointer_1c.py::test_schedule_d1_write_pointer_after_served_and_run_exist` asserts `"docs" not in str(pointer_root)`; no real write under `data/` occurred in this session -- the test monkeypatches `schedule_d1.POINTER_ROOT` to a `tmp_path` |
| (i) memo | this file: stale FIX-1b-era sentences removed, this section added, A9/verification regenerated below | n/a |

**Not implemented from (c):** the literal sub-clause "argparse errors when
neither [`--schedule` nor `--schedule-pointer`] is given" was NOT added to
`local_capture_runner.parse_args`. The already-landed, protected
`test_capture_scheduler.py::test_cli_default_scheduler_and_legacy_option`
calls `runner.main(["--output-root", ..., "--max-ticks", "1"])` with neither
flag and scheduler enabled by default, and that file must pass unchanged
(candidate-set rule). Adding a `parser.error` there would break it. The rest
of (c) -- bootstrap seeding schedule_path from the pointer alone, and never a
silent no-op -- is landed and tested (see above). Flagged again below.

**Two pre-existing `test_capture_schedule_pointer.py` fixtures updated for (e):**
`test_future_before_schema_and_future_rows_before_duplicates` and
`test_duplicates_refuse_without_switch` built their `row("N")` fixture rows
with the helper's *default* `scheduled_start` (2026-09-24), while the pointer
in both tests declares `day="2026-09-25"`. That mismatch was harmless before
day validation existed; under (e) it now raises `pointer_day_mismatch` before
the tests' actual assertions (future-row-before-duplicate ordering / duplicate
detection) run. Both were changed to pass an explicit
`row("N", "2026-09-25T01:00:00Z")`, matching the convention the fixture's own
`target` file already used; no assertion in either test was changed. All 35
of that file's tests still pass (see Verification).

## FIX 1d (AMENDMENT 2)

Round 2 codex sol REJECT named three blockers and one correction against FIX
1c; all four are landed here, additively, in `schedule_pointer.py` alone plus
one new test file. None of the four authorized landed files (`capture_schedule_loader.py`,
`local_capture_runner.py`, `polymarket_live_capture.py`, `schedule_d1.py`) were
touched by this fix -- confirmed by the unchanged sha256 values in the A9 table
below (byte-identical to FIX 1c). Base sha for this fix (`git rev-parse
--short HEAD`, unmoved): **ef7248901**.

| Item | File:line | Test |
|---|---|---|
| (a) exclusive close for incoming rows too | `schedule_pointer.py:82-100` `union_open_rows`: both `prior` and the newly-parsed `rows` are filtered through the same `_open(r) = at < instant(r["scheduled_start"]) + 3600` predicate before anything else runs (`carry = [r for r in prior if _open(r)]`, `incoming = [r for r in rows if _open(r)]`); previously only `prior` was filtered, so a closed row present in the CURRENT pointer target leaked straight into `candidates` and was admitted. The never-resurrected sentence in FIX 1c's "Candidate behavior" section is now true for the incoming side as well: a closed row present in the current pointer target is never re-added (`now` = 00:50Z, D started 23:50Z -> `[]`) | `test_capture_schedule_pointer_1d.py::test_incoming_closed_row_is_not_readmitted_construct` (direct `union_open_rows` call), `::test_same_pointer_close_kalshi_path` (through `capture_schedule_loader._forward_config`), `::test_same_pointer_close_polymarket_path` (through `schedule_pointer.refresh_polymarket_pointer`) -- same-pointer close proven on both capture paths |
| (b) identity sets do not mix fields | `schedule_pointer.py:88-90` `carried_game_ids = {r["game_id"] for r in carry}` and `carried_tickers = {r["ticker"] for r in carry}` are now two separate sets (previously one merged `carried_ids = game_ids \| tickers`); the candidate-exclusion test at `:98-99` checks `r["game_id"] not in carried_game_ids and r["ticker"] not in carried_tickers` -- a value shared between a carried game id and a carried ticker (cross-field) can no longer drop a valid new row | `test_capture_schedule_pointer_1d.py::test_new_ticker_equal_to_carried_game_id_is_not_dropped`, `::test_new_game_id_equal_to_carried_ticker_is_not_dropped` -- both collision directions |
| (c) the persisted heartbeat construct | no source change (AMENDMENT 1(g)/1(f) code was already correct; this closes the missing test named by the round-2 REJECT) -- exercises the REAL on-disk writer path: `local_capture_runner.py:232` `writer.atomic(lrow.heartbeat_path("kalshi", sport, writer.root), state["hb"][sport], "heartbeat")` and `polymarket_live_capture.py:217` `writer.atomic(path, value, "heartbeat")`, both via a real `ArchiveWriter`/`PolymarketWriter`, no mock | `test_capture_schedule_pointer_1d.py::test_persisted_kalshi_heartbeat_tracks_pointer_health` (drives `local_capture_runner.capture_once(scheduler_enabled=True, schedule_pointer=...)` end to end through `_scheduled_tick`, reads back `<root>/kalshi/mlb/_heartbeat.json`), `::test_persisted_polymarket_heartbeat_tracks_pointer_health` (drives `polymarket_live_capture.capture_once` end to end, reads back `<root>/polymarket/mlb/_heartbeat.json`) -- both assert `schedule_pointer_refusals_total`, `schedule_pointer_last_reason` and the `pointer_read_at` vs `pointer_ok_at` distinction from the file on disk, not from in-memory state |
| (d) memo | this section; A9 table regenerated below; base sha stated above | n/a |

No network was used to reach the real writer path: the Kalshi construct seeds
`state["scheduled_cache"]` directly (the pattern `test_capture_scheduler.py`
already uses) and the Polymarket construct reuses that file's own fixture
JSON through a fake `requests`-free session; both are construct-only,
consistent with this row's WHERE (local, stubbed clock/filesystem, no network).

### Verification (FIX 1d, this session)

```text
test_capture_schedule_pointer_1d.py (NEW)   -> 7 passed
test_capture_schedule_pointer.py            -> 35 passed (unchanged)
test_capture_schedule_pointer_1c.py         -> 11 passed (unchanged)
test_capture_scheduler.py                   -> 151 passed (unchanged)
test_local_capture_runner.py                -> 8 passed (unchanged)
test_local_state_capture_schedule.py        -> 367 passed (unchanged)
test_polymarket_live_capture.py             -> 18 passed (unchanged)
test_polymarket_live_json/_link/_relink/_rows/_trades -> 19+22+16+57+32 = 146 passed (unchanged)
test_schedule_d1.py                         -> 46 passed (unchanged)
```

`contract_preflight --base master --spec docs/evidence/tracking/specs/S438_spec.md`
over all ten candidate/landed paths: **9 PASS, 0 FAIL** (vocab, crlf, loc,
schema, head_slice, spec_threshold, proposed, removed_artifact,
row_duplication). `git diff --stat master` lists only the four authorized
landed files as changed (`schedule_pointer.py`, `schedule_pointer_writer.py`
and every `test_capture_schedule_pointer*.py` file are untracked, so a plain
`git diff` never shows them); the same pre-existing, unrelated spec-doc
divergence from other lanes noted under FIX 1c is still present and still out
of this row's scope.

### A9 identities (bytes + sha256, this session, regenerated from the tree)

```text
HEAD = ef7248901 (unmoved)
capture_schedule_loader.py      LOC=50  bytes=3350  sha256=2118549432ef87403e7c2a2befc0fbe757aebbc162039f29755a2e2930fb59ca (unchanged)
local_capture_runner.py         LOC=299 bytes=18288 sha256=aba3a145b79b08522f9cb625611c0062a8d2a3157653eb2bb43761e267c8a091 (unchanged)
polymarket_live_capture.py      LOC=276 bytes=15122 sha256=593592a4f3615b984f1c28edaefedcbf81cd63a61a5dd1c524e89365ce9a6a5c (unchanged)
schedule_d1.py                  LOC=270 bytes=13591 sha256=2e97bbdc574c017c5c7420f5e3d44df29c48c89d52454697a6a72848b9a82318 (unchanged)
schedule_pointer.py             LOC=196 bytes=9353  sha256=8f9dbae90ff2597a96d17b83f6c5f8b7b98e731ddaf76b86aba02b8abb8aebf0 (AMENDMENT 2 a/b)
schedule_pointer_writer.py      LOC=70  bytes=2975  sha256=094d6f951e2c5afcb3deaee9f85cf923090673b6c6f77c7e86ba44b0bc2a7c91 (unchanged)
test_capture_schedule_pointer.py LOC=238 bytes=10551 sha256=a690ab21e7c734c485b43f301c2173572253188b734d7f1d655a030c3caf3d62 (unchanged)
test_capture_schedule_pointer_1c.py LOC=170 bytes=7877 sha256=95ed40864e0d60ce14ce0ca82d5fe3b8b5f6e2828988dd3c9b7f7693be57aa40 (unchanged)
test_capture_schedule_pointer_1d.py LOC=112 bytes=5994 sha256=290433d2cfab5dceb3136cb2cfe76824940d867d0bab4a089da2fd47d3b2129a (NEW)
```

## NOT VERIFIED

- No live relaunch happened; adoption = an owner-visible relaunch of the books
  runner and/or the Polymarket capture with `--schedule-pointer` pointed at a
  real S429 output, and a `schedule_d1.py --write-pointer` run observed across
  a real UTC midnight, per the spec's REAL RUN paragraph.
- AMENDMENT 1(c)'s literal "argparse errors when neither [flag] is given"
  sub-clause is NOT implemented in `local_capture_runner.parse_args`: the
  already-landed, protected `test_capture_scheduler.py` calls `runner.main`
  with scheduler enabled and neither `--schedule` nor `--schedule-pointer`,
  and that file must keep passing unchanged. The rest of (c) -- bootstrap
  seeding `schedule_path` from the pointer alone, never a silent no-op -- is
  landed and tested.
- `test_schedule_d1_write_pointer_after_served_and_run_exist` (new, FIX 1c)
  exercises `schedule_d1.py --write-pointer` through `main()` itself,
  including ordering (served + run files must already exist) and the digest;
  it does not exercise a REAL forward_schedule_writer census or a real
  archive tree (it reuses `test_schedule_d1.py`'s own mocked-writer fixture).
- No test exercises a real archive, real network requests, or a running
  supervisor; `socket.socket.connect` is mocked to raise in the pointer test
  fixture (network forbidden by construction). The FIX 1c CLI/writer
  constructs stub `_scheduled_tick` / `capture_once` to isolate the seeding
  lines from the full tick machinery, rather than driving a real tick end to
  end with a pointer (the existing `test_11_rollover_preserves_focus_until_close`
  and the new `test_far_future_prior_row_survives_afternoon_pointer` /
  `test_refusal_after_switch_keeps_union_until_close` exercise the real
  `capture_scheduler.plan_tick` and `_forward_config` machinery instead).
- No process termination or power loss was injected against the new CLI
  wiring itself (the writer's own fsync/replace-failure cases were already
  covered before this fix).
- The default pointer root (`data/cache/schedule_pointers`, AMENDMENT 1(h))
  was never actually written to in this session -- every test monkeypatches
  `schedule_d1.POINTER_ROOT` to a `tmp_path`, per this row's "never write
  under any data/ directory" constraint. The directory does not exist on disk.
- This worktree's `git diff --stat master` carries pre-existing, unrelated
  docs/spec divergence from other lanes (`master` has moved to a newer commit
  than this worktree's HEAD since FIX 1b; not from this fix; `git diff --stat
  HEAD` is clean of it) -- not reconciled here, out of this row's scope.
- Independent verification, a commit, a push, adoption and deployment have not
  occurred.
