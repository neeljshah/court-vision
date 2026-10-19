# S463 -- pointer hand-off at startup unions the --schedule rows (BUILD memo)

Build result: 45 owned passed (23+8+5+6+3), pre-existing 35/11/7/8/18 unchanged, both
runners' union 3+6=9, preflight 9/9.

Row: S463 | worktree: nba-harness-h113 (master-based) | date: 2026-09-25 | this file
supersedes and renames `S463_pointer_startup_union_order_2026-09-25.md` (Opus round-1
finding #8: file names must match the spec's own naming).

Candidate `HEAD` at this FIX 1f session's own `git merge --ff-only master` (run
first, before any edit): fast-forwarded from `950c3e4461241f01277c107afe3dc564d7485a28`
to `2b20cbd4fce5a7d9beb97b558e56d35ea5977662` (four S462/S465/S466/S467 spec-only
commits, confirmed by `git diff --name-only` to touch only
`docs/evidence/tracking/specs/`). `HEAD` = `2b20cbd4fce5a7d9beb97b558e56d35ea5977662`.
`master` = `2b20cbd4fce5a7d9beb97b558e56d35ea5977662`. **EQUAL** at that moment. Preflight,
must-not-move and A9 were all RUN against this `HEAD` after every edit this session,
most recently as the LAST edit (section 6). `master` has since advanced two further
commits (S450/S460 spec-only amendments, confirmed by `git diff --name-only` to touch
only `docs/evidence/tracking/specs/`) from other concurrent lanes; not re-merged
mid-session, per this session's own instruction to capture `HEAD`/`master` once.

## 1. Measured ordering defect (re-verified round 1, against the pre-edit tree; unchanged
by every fix round -- the underlying regression measurement is not in dispute)

- `scripts/platformkit/ingame/capture_schedule_loader.py` (pre-edit, 50 lines): `:24`
  `state.setdefault("forward_schedule", [])`; `:31-34` `pointer_hit =
  schedule_pointer.read_schedule_pointer(...) is not None`, or-ed with the sticky
  `schedule_pointer_ever_resolved`; `:44-45` `state["forward_schedule"] =
  scheduler.schedule_rows(...)` from `state["schedule_path"]` runs ONLY `if not
  pointer_hit`. The pointer attempt at `:33` always precedes the CLI read in source order;
  if `pointer_hit` is True on the first tick `forward_schedule` is ever touched, the CLI
  rows never enter the union, and because `pointer_hit` is sticky, never will.
- `scripts/platformkit/ingame/schedule_pointer.py` (pre-edit, 196 lines): `:154`
  `rows = union_open_rows(parsed, state.get("forward_schedule", []), now, errors)` inside
  `read_schedule_pointer` -- reads `forward_schedule` at the moment of the pointer call,
  before `capture_schedule_loader.py:44-45` could ever run.
- `scripts/platformkit/ingame/polymarket_live_capture.py` (pre-edit, 276 lines): `:231`
  `state = {"prospective": load_prospective(schedule, client.metrics.errors)}` --
  `run_capture` never assigned `state["schedule_path"]` anywhere, so nothing seeded the
  identity a startup union would need.

## 2. Durable evidence (spec's own BINDING BEFORE-CONDITION, quoted per Opus round-1
finding #9; `data/cache/capture_supervisor/*` is local-only/gitignored, absent from this
fresh construct-only worktree -- confirmed absent this session, cited from the spec's
own session-read quotes)

- `S463_spec.md:6`: child_start pid 17636 at `2026-09-25T13:5x:25.729895Z` (masked minute
  digit -- scanner-safe), child_exit (WinError5) at `2026-09-25T13:56:25.906106Z`,
  restart pid 8308 at `2026-09-25T13:56:26.942441Z`; child_start pid 16900 at
  `2026-09-25T14:49:58.832277Z`, child_exit run_seconds=10.14 at
  `2026-09-25T14:50:08.970356Z`, restart pid 12668 at `2026-09-25T14:50:10.069913Z`.
- `S463_spec.md:7`: "schedule observed sha256=50816c27..." at local 08:5x:26
  (= `2026-09-25T13:5x:26Z`, 3 games) then "...=d2d11baf..." at local 08:57:30
  (= `2026-09-25T13:57:30Z`, 6 games) -- the digest change is the FIRST pointer
  resolution of that process, landing AFTER the CLI digest was already logged, so
  `forward_schedule` already held the 3 CLI rows when the union ran.
- `S463_spec.md:8`: the restart at 14:50:10 logs "...=d2d11baf..." at local 09:50:11
  (= `2026-09-25T14:50:11Z`) as its FIRST schedule-observed line -- no prior CLI-digest
  line, so `forward_schedule` was still empty when this pointer resolution ran and the
  CLI rows were dropped.
- The exact `scheduled_games_total` 9-vs-6 split is orchestrator-observed from a live
  heartbeat that overwrites itself each tick, not durable, not re-fetchable this session.

## 3. What was built (owned files only; must-not-move verified byte-identical, section 8)

- `schedule_pointer.py`: `seed_cli_schedule` (round 1); public `sources_delta`;
  `refresh_polymarket_pointer` returns `bool` and unions `prospective_cli` back into
  `prospective`; `union_open_rows` keeps a re-selected row instead of refusing the whole
  pointer (AMENDMENT 2d). FIX 1d (this round): `sources_delta` takes an explicit
  `reselected_rows` parameter, always in its result, a strict int (schedule_pointer.py:22-35);
  `union_open_rows` gains an optional `telemetry` out-param so its own
  identity-comparison loop -- the only place that has BOTH the carried and the incoming
  row -- reports the count directly, instead of a caller re-inferring it from a
  before/after diff that cannot see a re-selection whose adopted value equals the
  carried row's own (schedule_pointer.py:106-147); `read_schedule_pointer` threads this
  through a transient `state["schedule_pointer_reselected_rows"]`, read once by the
  caller and never itself persisted (schedule_pointer.py:239-262).
- `capture_schedule_loader.py` / `polymarket_live_capture.py`: both call sites now
  REPLACE `schedule_sources` on every successful resolution (keeping only `cli_rows`
  from the previous value) instead of `dict.update`, so a stale `reselected_rows` from
  an earlier resolution can no longer survive a later one that re-selected nothing.
- `local_capture_runner.py` (`:232`): unchanged this round -- it already reads
  `state["schedule_sources"]` wholesale, so a caller-side replace is sufficient; no
  `dict.update` of this field exists at this layer to fix.
- FIX 1e (full detail folded into the FIX 1b/1c/1d/1e history section below): `schedule_
  pointer.py:170` creates `schedule_sources` with `"reselected_rows": 0` from the seed
  itself; both byte-identity tests seed a real market; the identical-union construct
  asserts the full `[1, 0]` sequence; `tmp_path` replaces `tempfile.mkdtemp()`.
- FIX 1f (this round; full detail in the FIX 1f section below): both byte-identity
  tests in `test_schedule_pointer_startup_union_1d.py` (now 272 lines) gained a
  deterministic `os.replace` monkeypatch (correction 1); `test_schedule_pointer_
  startup_union_1e.py` (now 69 lines) gained two tests asserting the PERSISTED
  heartbeat's `schedule_sources` on a malformed pointer at startup, both runners
  (note 3). `test_schedule_pointer_startup_union_1c.py` shrank from 198 to 96 lines
  in FIX 1d/1e (its two byte-identity tests moved into 1d).

## 4. The 8 acceptance cases (unchanged this round; see FIX 1b/1c/1d/1e history below for
the corrections that produced this form)

1-7: unchanged since FIX 1c (Kalshi/Polymarket union, delay, pointer-alone, flag-off,
loose-schema refusal -- see prior FIX history). 8. Both runners, heartbeat
`schedule_sources`: `test_case8_kalshi_schedule_sources_updates_each_successful_
resolution`, `test_kalshi_capture_once_persists_schedule_sources_in_heartbeat`,
`test_case8_polymarket_schedule_sources_in_published_heartbeat`,
`test_case8_polymarket_schedule_sources_absent_when_neither_ran`,
`test_polymarket_pointer_alone_publish_omits_schedule_sources` -- all now also assert
the field's ALWAYS-present `reselected_rows` (FIX 1d; `test_case8_polymarket_
schedule_sources_in_published_heartbeat`'s own construct dict updated in FIX 1e).

## schedule_sources definition (AMENDMENT 2e/3c; resolves the ":165 this paragraph"
pointer from the FIX 1c memo -- THIS is that paragraph)

`schedule_sources` is a per-resolution split, not a running total: `cli_rows` is fixed
the moment `seed_cli_schedule` runs (never touched again); `pointer_rows`,
`carried_rows` and `reselected_rows` are REPLACED on every successful pointer
resolution, changed or not. `reselected_rows` counts every full-identity
(`game_id`+`ticker`) match between the carried and incoming rows whose `selected_at`
differs, whichever row's value is kept -- it is a SUBSET of `carried_rows`, always a
strict int, 0 when no re-selection happened this resolution. Because a re-selected
identity is also a carried one, and `cli_rows` is never re-derived, `cli_rows +
pointer_rows + carried_rows` can legitimately EXCEED the schedule's own row count after
an identical union (for example `{3, 0, 9}` for a nine-row schedule once every CLI row
has also been carried through several resolutions). The counts stay FROZEN -- not
zeroed, not re-derived -- on a failed refresh or once the pointer file vanishes,
because the replace only happens on a successful resolution.

## FIX 1f -- round-5 correction and optional test gap

Round 5: codex sol ACCEPT WITH CORRECTIONS (one correction, no source change) and Opus
tier-2 ACCEPT WITH CORRECTIONS (one correction, three notes). Both tiers confirm the
candidate code is accepted and its semantics are unchanged by this round -- only tests
and this memo moved.

| Finding | Fix |
|---|---|
| Opus correction 1: `test_amendment3b_kalshi_raw_bytes_identical_to_base_commit`/`..._polymarket_...` (`test_schedule_pointer_startup_union_1d.py:219-231` and the Polymarket twin) are intermittently flaky -- Windows `os.replace` inside `local_capture_writer.atomic()` (`local_capture_writer.py:186-188`) can raise `PermissionError`, which the writer counts as `atomic_replace_retry` into the heartbeat's `error_counters` on whichever of old/new hits it, making the raw-byte comparison non-deterministic. Not a product defect. | `_deterministic_replace(monkeypatch)` (new helper, `test_schedule_pointer_startup_union_1d.py`): monkeypatches `scripts.platformkit.ingame.local_capture_writer.os.replace` with a wrapper that loops on `PermissionError` (bounded, 20 x 0.05s) without surfacing it, called at the top of both byte tests. `local_capture_writer.py` itself is untouched (must-not-move, section 8). Re-run 5 consecutive times this session: 6/6/6/6/6 passed (section 9). |
| Opus note 3 (optional test gap): the AMENDMENT 4(a) seed-creates-the-key behaviour (`schedule_pointer.py:170`) is proven only through `state` (`test_schedule_pointer_bootstrap_seed.py:41-52`, `test_schedule_pointer_startup_union_1e.py`'s own construct); no test reads the actually persisted `_heartbeat.json`. | Two new tests in `test_schedule_pointer_startup_union_1e.py`: a malformed pointer at startup alongside a valid `--schedule`, through the real `capture_once` (Kalshi) / `run_capture` (Polymarket) startup path on both runners, asserting the PERSISTED heartbeat's `schedule_sources` (`reselected_rows` present and 0, every count `type(value) is int`). |
| codex sol note (host-only): all ten authorized test files were blocked by an unrelated, transient `tmp_path` factory failure at round-5 verification time | Not reproduced this session; all ten files (5 owned + 5 pre-existing) pass individually this session (section 9). No source or test change. |

## FIX 1b/1c/1d/1e history (compacted; full round-1/2/3/4 finding tables are in this
file's git history at the FIX 1c/1d/1e commits -- every fix they describe is still in
place and unchanged except where a later round's table says otherwise)

FIX 1b (round 1, AMENDMENT 1): folded the Kalshi heartbeat telemetry into the existing
`:232` merge; gated both wrappers on `"schedule_sources" in state` so pointer-alone
stays byte-identical; made both runners call the shared `sources_delta` under the same
gate; unioned `prospective_cli` back into `prospective` every Polymarket resolution;
added the 8-case test file; fixed case 8 repeating case 1; corrected memo naming,
must-not-move paths and case 6/7 before-values; refused duplicate CLI keys; moved
`sources_delta` off a private Kalshi-loader import.
FIX 1c (round 2, AMENDMENT 2): authorised the second test file split; added the
Polymarket identical-union construct through real `capture_once`; a re-selected row
(same `game_id`+`ticker`, different `selected_at`) adopts the later value instead of
refusing the whole pointer, counted as `reselected_rows`; added (now superseded, see
FIX 1d/1e) byte-identity constructs against `BASE_SHA`; corrected a stale docstring.
FIX 1d (round 3, AMENDMENT 3): `union_open_rows` computes and exposes `reselected_
rows` itself via an optional `telemetry` out-param instead of a before/after diff
(which cannot see a re-selection whose adopted value equals the carried row's own);
both call sites REPLACE `schedule_sources` on every successful resolution instead of
`dict.update`, so a stale count cannot survive; byte identity compares raw
`encode_json` bytes (no `sort_keys`) through the real startup path, `BASE_SHA` the
full 40-hex sha; memo build result moved to line 3; the `schedule_sources definition`
section above resolved the `:165 this paragraph` pointer.
FIX 1e (round 4, AMENDMENT 4): `seed_cli_schedule` creates `schedule_sources` with
`reselected_rows: 0` from the first tick, not only on first success, so a malformed
pointer or a failed refresh before any success never leaves the key absent; both
byte-identity constructs seed a real market (`backfill.uuid4` pinned) so an archive
row and a checkpoint exist before comparing, not only a heartbeat; Polymarket runs
through the real `run_capture` (`max_ticks=1`) instead of `capture_once` alone; the
identical-union construct asserts the full `[1, 0]` sequence, not only the final
value; `tempfile.mkdtemp()` replaced with `tmp_path`.

## 5. Hunks (unified diff, this worktree vs `master`; reproducible with
`git diff master -- <path>`; full hunks -- regenerated this round (FIX 1f), byte-
identical to the prior round's content since no product file changed -- are in the
sibling `docs/evidence/harness/S463_startup_union_order_hunks_2026-09-25.md`, named
here per AMENDMENT 2(e) since inlining them would exceed this memo's 300-line rail)

| file | +/- (git diff --numstat vs master, re-verified this round) | last round with a product-code change |
|---|---|---|
| schedule_pointer.py | +110/-9 | `reselected_rows: 0` in the seed's own `schedule_sources` dict (:170) |
| capture_schedule_loader.py | +14/-0 | unchanged this round (FIX 1d) |
| polymarket_live_capture.py | +21/-1 | unchanged this round (FIX 1d) |
| local_capture_runner.py | +1/-1 | unchanged this round (FIX 1a) |

## 6. A9 identities (LF-normalised: this worktree checks out CRLF via `core.autocrlf`,
git's stored blob and the eventual `git add` are LF -- sha256/bytes computed after
stripping `\r`; regenerated from disk as the LAST edit this session, after every other
edit including the hunks sibling)

| path | lines | LF bytes | LF sha256 |
|---|---|---|---|
| scripts/platformkit/ingame/schedule_pointer.py | 297 | 14857 | 57acd6eac54d28b777c8c8f71eadbd9876618ca8548ac11230cbce16a72574bd |
| scripts/platformkit/ingame/capture_schedule_loader.py | 64 | 4375 | 84b81a18863ca17d41475a89f6bd9f578bd291b4a1f4a807a24f47691609f359 |
| scripts/platformkit/ingame/polymarket_live_capture.py | 296 | 16420 | c4dc1cabb191e451fd7ba1c5a2f26bf4600c0162dcb0ea83ae3b7f8dfdf03ec5 |
| scripts/platformkit/ingame/local_capture_runner.py | 300 | 18177 | 5dedfaaf962131a433b88b18aef04189d7ede880b94463f05c45f7e2f971cff4 |
| tests/platformkit/ingame/test_schedule_pointer_startup_union.py | 300 | 15149 | 3ff9b4a956e6746a7d447d84b03b21d49cb992983cf9280a2b0b6c7664716817 |
| tests/platformkit/ingame/test_schedule_pointer_bootstrap_seed.py | 170 | 9817 | 75cf52b9b80de40bfb08e2f2a183004d7209855acb7db3611a69516309f44653 |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1c.py | 96 | 5697 | a4fd9aeca05ba9f3263c5c53730215f5be829893b8133237f9562bd959e2c04f |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py | 272 | 13636 | f74a375edd19b11025e321a287793ac977d002231cd77d01a7346cbf6e892194 |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1e.py | 69 | 4315 | f4ae01ef4fb27bf68b268f302f0723b4b531a7439bde113e60e24229d0f864d7 |

Regenerated from disk as the LAST edit in this memo (FIX 1f), after every other edit
including the hunks sibling: `HEAD` = `2b20cbd4fce5a7d9beb97b558e56d35ea5977662` =
`master` at re-read time. **EQUAL** (see the header).

## 7. Build order

Lands after S461/S464 (both touch `local_capture_writer.py`'s / `schedule_pointer_
writer.py`'s neighbourhood; this row never touches either file -- confirmed
byte-identical, section 8). S464 must refresh its freeze baseline for
`schedule_pointer.py` and `capture_schedule_loader.py` after this row lands.

## 8. Must-not-move verification (real paths; this round's rail narrows the list to
`capture_scheduler.py` and `local_capture_writer.py`)

```
git diff --stat master -- scripts/platformkit/ingame/capture_scheduler.py \
  scripts/platformkit/ingame/local_capture_writer.py
```
-> empty (byte-identical, exit 0; re-run this FIX 1f session, after the fast-forward
described in the header and again after every edit).

## 9. Test results (per-file, run individually per the rails; never the full suite)

Pre-existing (unchanged pass counts, confirmed this session, before AND after this
round's edits):
- test_capture_schedule_pointer.py: 35 passed
- test_capture_schedule_pointer_1c.py: 11 passed
- test_capture_schedule_pointer_1d.py: 7 passed
- test_local_capture_runner.py: 8 passed
- test_polymarket_live_capture.py: 18 passed

Owned:
- test_schedule_pointer_startup_union.py: 23 passed (FIX 1e: one exact-dict assertion
  (:108) plus the case-8 construct's input/expected (:273,:281) gained
  `reselected_rows`; still 300 LOC)
- test_schedule_pointer_bootstrap_seed.py: 8 passed (FIX 1e: two exact-dict assertions
  (:35,:50) gained `reselected_rows`)
- test_schedule_pointer_startup_union_1c.py: 5 passed (unchanged this round)
- test_schedule_pointer_startup_union_1d.py: 6 passed (FIX 1f: both byte-identity tests
  gained the `_deterministic_replace(monkeypatch)` os.replace wrapper, correction 1;
  247 -> 272 lines). Re-run 5 consecutive times this session, each independently: 6, 6,
  6, 6, 6 passed.
- test_schedule_pointer_startup_union_1e.py: 3 passed (FIX 1f: two new tests, note 3 --
  the persisted `_heartbeat.json` `schedule_sources` on a malformed pointer at startup,
  both runners; 18 -> 69 lines)

Each CLI's `--help` (via `python -m ...`, the package-relative import form): exit 0 for
both `local_capture_runner` and `polymarket_live_capture`, re-run this session.

`python -m scripts.platformkit.tracking.contract_preflight --paths
scripts/platformkit/ingame/schedule_pointer.py
scripts/platformkit/ingame/capture_schedule_loader.py
scripts/platformkit/ingame/polymarket_live_capture.py
scripts/platformkit/ingame/local_capture_runner.py
tests/platformkit/ingame/test_schedule_pointer_startup_union.py
tests/platformkit/ingame/test_schedule_pointer_bootstrap_seed.py
tests/platformkit/ingame/test_schedule_pointer_startup_union_1c.py
tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py
tests/platformkit/ingame/test_schedule_pointer_startup_union_1e.py
docs/evidence/harness/S463_startup_union_order_2026-09-25.md --base master --spec
docs/evidence/tracking/specs/S463_spec.md`: all 9 checks PASS (vocab, crlf, loc, schema,
head_slice, spec_threshold, proposed, removed_artifact, row_duplication).

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## 10. NOT VERIFIED

- The exact `scheduled_games_total` 9-vs-6 split cited in the spec's before-condition is
  orchestrator-observed from a live heartbeat that overwrites itself each tick; it could
  not be re-fetched this session (the underlying `data/cache/capture_supervisor/*` files
  are absent from this fresh, local-only, construct-only worktree).
- Adoption: none of this changes an already-running capture process. Adoption = the next
  owner-visible relaunch of both capture children (`S463_spec.md:4`, unchanged here).
- This session's git operations were sandboxed for commit purposes: no commit was
  created (see the SHA line above); a `git merge --ff-only master` WAS run first and
  fast-forwarded from `950c3e446` to `d2945c427` (four spec-only commits, see the
  header); `lane_commit` still needs to run the actual `git add`/`git commit`.
- Section 2's timestamps are quoted with a masked minute digit (`13:5x:25` style), not
  verbatim: AMENDMENT 2(e) states this stands because the vocabulary scanner refuses the
  bare token, the exact instants live in the spec and the cited supervisor-journal
  lines, and sol's original verbatim demand is superseded by this amendment.
- AMENDMENT 3(b)'s byte-identity tests load the pre-S463 blob via `git show` at build
  time (a local, offline repo read, not network) and run the real Kalshi/Polymarket
  startup path with faked network sessions (no live request); they were not additionally
  cross-checked against a separately-generated, checked-in golden-fixture file (the
  spec's other permitted mechanism) -- both are not required together.
- `prospective_cli` identities still never expire (NEW GAP, unchanged this round); a
  format-only `scheduled_start`/timestamp difference between writers still refuses the
  whole pointer (NEW GAP, AMENDMENT 3); a CLI row whose `selected_at` is still in the
  future at startup is dropped for good, matching master's pointer-on behaviour today
  (NEW GAP, AMENDMENT 3); byte-identity constructs on Windows need a deterministic
  `os.replace` -- `local_capture_writer.atomic()`'s `atomic_replace_retry` counter
  (`local_capture_writer.py:186-188`) leaks a real, intermittent `PermissionError` retry
  into the raw heartbeat bytes on whichever side hits it, so any future raw-byte
  comparison needs the same monkeypatch this row's tests now carry, ideally as a shared
  fixture (NEW GAP, FIX 1f) -- register items for a future row, not this one. The
  running fleet and relaunch behaviour were not touched this session.
