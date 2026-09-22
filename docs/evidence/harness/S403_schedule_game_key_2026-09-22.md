# S403 the prospective schedule writer emits game_key

BUILD candidate. Local worktree `C:/Users/neelj/nba-harness-h64`, branch
harness-h64, master-based at 009880081. Specification read directly from
`docs/evidence/tracking/specs/S403_spec.md`. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q. The pod is
OFF and no provider request was made. This memo makes no sampled or scored
claim.

## BINDING BEFORE-CONDITION (quoted from master)

(a) `forward_schedule_writer.build_schedule` signature and the entry
construction at master lines 234-235:

```
def build_schedule(day: str, sports: list[str], books_root: Path, state_root: Path,
                   family: str, now: str | None = None, *, schedule_source: str = "live",
                   opener: Callable | None = None) -> tuple[list[dict], dict]:
    """Return six-field schedule entries and deterministic per-sport diagnostics."""
...
                candidates.append((dict(game_id=event, ticker=ticker, sport=sport, family=family,
                                        scheduled_start=game["scheduled_start_utc"], selected_at=selected), rule))
```

(b) `forward_capture_bridge.py` lines 55-90, the game_key requirement and the
linkage test:

```
            grouped[(_text(row, "sport"), _text(row, "game_key"))].append(row)
...
    for game in schedule:
        options = candidates[(game["sport"], game["game_id"])]
        key = game.get("game_key")
        if (isinstance(key, str) and key.strip() and len(options) == 1
                and game["ticker"] in options[0][1] and key == options[0][0]):
            links[(game["sport"], options[0][0])] = game["game_id"]
        else:
            counts["LINKAGE_INVALID"] += 1
```

The schedule entry's key is compared for equality with the key the state rows
were grouped by, so it must equal the state capture's key exactly.

(c) `local_state_capture_sources.py` game_key provenance per sport, the five
sites that construct it:

```
line  63  mlb_discover:            "game_key": str(game["gamePk"]),
line 100  mlb_poll:                "game_key": str(game_pk),
line 122  _espn_scoreboard_states: "game_key": str(event.get("id") or f"{row.get('away_abbr')}@{row.get('home_abbr')}"),
line 175  tennis_poll:             "game_key": f"{league}:{rows[0]['comp_id']}",
line 215  _nfl_league_poll:        "game_key": row.get("espn_event_id"),
```

`nba_poll` and `soccer_poll` both call `_espn_scoreboard_states`, so line 122
is the NBA and soccer rule: the ESPN **event** id, with an `away@home`
fallback. `domains/nfl/ingest_nfl_states.py` line 200 sets
`"espn_event_id": ev.get("id")`, the ESPN event id again, so NFL and NCAAF
share that rule. Line 175 is tennis (`TENNIS_LEAGUES`, `_tennis_parse_scoreboard`),
and `domains/tennis/ingest_espn.py` line 131 sets `comp_id = str(comp.get("id", ""))`,
the competition id. The spec's before-condition text labels the
`league:comp_id` rule "soccer"; the code places it in `tennis_poll`. This
candidate follows the code.

(d) `capture_scheduler.schedule_rows` (line 107) validates only
`game_id`, `ticker`, `sport`, `family` as nonempty strings plus
`selected_at` / `scheduled_start` as timestamps, and returns `deepcopy(row)`;
`forward_replay_qualification.Qualification.__init__` (lines 102-115) checks
the same four identity fields and stores `meta=dict(row)`. Neither enumerates
allowed keys, so both carry a seventh key through untouched. **No spec
conflict: neither refuses a seventh key.** Both were left unedited and both
landed suites were run.

(e) `forward_schedule_sources.py` at master yielded, per sport:
`mlb` -> `raw.get("gamePk")`; every other sport -> `comp.get("id")`, the ESPN
**competition** id, with tennis prefixed `f"{tour}:{key}"`. MLB and tennis
already agreed with the state capture. NBA, soccer, NFL and NCAAF did not:
they used the competition id where the state capture uses the event id.

## CHANGE as built

1. `forward_schedule_sources._game` now records the key and its provenance
   label together: MLB `raw.get("gamePk")` / `mlb_game_pk`; tennis
   `comp.get("id")` prefixed by tour / `espn_competition_id`; every other
   ESPN-backed sport `raw.get("id")`, the event id / `espn_event_id`. The
   `away@home` fallback of line 122 is deliberately NOT reproduced: a key that
   cannot be derived from the live source now raises
   `ValueError("game_key_unavailable")`, which `_fetch_schedule` counts under
   that exact name and turns into a `{"_refusal": "game_key_unavailable"}` row.
   The former `missing_game_id` reason no longer exists in this module. A game
   with no derivable key therefore reaches no entry and is counted, never
   given a placeholder.
2. `forward_schedule_writer.build_schedule` validates the key with the
   existing `_text` trust-boundary helper before it counts the game as linked,
   emits `game_key=key` as the seventh entry field, and records the key source
   per entry in the new census field `game_key_sources` (key -> source label).
   In archive mode the games are state-capture rows themselves and the label
   is `state_archive`. The docstring now says seven-field.

Both modules stay at or under the rail: writer 300 lines, sources 157 lines.

## Tests

`tests/platformkit/execution/test_forward_schedule_writer.py` (owned,
MODIFIED, 288 lines): the canonical-rules test now asserts the full
seven-field entry including `game_key="provider-game"`, and adds
`schedule_rows(rows, writer._stamp(NOW), writer.Counter()) == rows` beside the
existing `Qualification(rows, NOW).games[EVENT]["meta"] == rows[0]`. That pair
is the construct proof that the landed scheduler and the landed replay loader
both accept an entry carrying the seventh key. All other tests in the file are
unchanged and pass.

`tests/platformkit/execution/test_forward_schedule_game_key.py` (NEW, 70
lines): the spec allocated the key-parity and refusal tests to the writer's
test file, which stood at 285 of the 300 allowed lines and could not hold
them. This lane followed the module's own precedent
(`test_forward_schedule_fix1f.py`, `test_forward_schedule_team_set.py` are
per-amendment companions to the same writer) and put them in a companion
module rather than break the LOC rail. It holds:

- `test_game_key_equals_state_capture_key[mlb]` and `[soccer]`: one constructed
  payload is fed to `sources.fetch_schedule` through an injected opener and to
  the state capture's own `capture.mlb_discover` / `capture.soccer_poll`
  through an injected `get`. The two key lists must be equal and nonempty, and
  the recorded source label must be `mlb_game_pk` / `espn_event_id`. The
  soccer fixture is real-shaped: ESPN repeats the event id on its single
  competition, so `id` appears at both levels.
- `test_unavailable_key_is_refused_and_counted`: the same soccer payload with
  `id` deleted yields `[{"_refusal": "game_key_unavailable"}]` and
  `Counter({"game_key_unavailable": 1})`.
- `test_writer_writes_no_entry_for_an_unavailable_key`: the same payload driven
  through `build_schedule` in live mode yields no entries,
  `refused_by_reason == {"game_key_unavailable": 1}` and an empty
  `game_key_sources`.

No network, no pod, no real archive, no measured number. The clock inside
`forward_schedule_sources` is frozen by an autouse fixture and `urlopen` is
replaced with a failing stub.

### Per-file results (one file per invocation)

```
tests/platformkit/execution/test_forward_schedule_game_key.py   4 passed in 0.74s
tests/platformkit/execution/test_forward_schedule_writer.py    45 passed in 1.64s
tests/platformkit/execution/test_forward_replay.py             49 passed in 2.02s
tests/platformkit/ingame/test_capture_scheduler.py            151 passed in 3.39s
tests/platformkit/execution/test_forward_schedule_fix1f.py     13 passed in 0.73s
tests/platformkit/execution/test_forward_schedule_sources.py    6 failed, 57 passed in 1.11s
tests/platformkit/execution/test_forward_schedule_team_set.py   2 failed, 21 passed in 1.02s
```

`python -m scripts.platformkit.execution.forward_schedule_writer --help`:
exit 0. No separate self-check option exists. Preflight:
`python -m scripts.platformkit.tracking.contract_preflight --paths <the four
owned code and test files> --base master --spec
docs/evidence/tracking/specs/S403_spec.md` returned 9 PASS and zero FAIL,
including `loc all .py <= 300 LOC` and `vocab clean over 4 files`.

## Two landed test files this row cannot own

Both failures are in files outside this row's ownership list and both are
fixture pinning, not defects in the change. Each was reproduced on a
throwaway copy with the proposed one-line edit applied; the copies were
deleted and both then passed in full. The edits themselves are NOT applied.

1. `tests/platformkit/execution/test_forward_schedule_sources.py` line 44, the
   `espn()` helper, returns `dict(id="event-id", ..., competitions=[dict(id=key, ...)])`.
   That is not the real ESPN shape: a real scoreboard event repeats its id on
   its single competition, and distinct events carry distinct ids. Under the
   event-id rule all three constructed events collapse to `event-id`. Proposed
   edit: `id="event-id"` -> `id=key`. Probe copy: 63 passed.
2. `tests/platformkit/execution/test_forward_schedule_team_set.py` line 75
   asserts the six-field entry dict. Proposed edit: add `game_key="123"` to
   that expected dict, the same gamePk its own `link_paths` assertion already
   pins. Probe copy: 23 passed.

## Observation on the hand-patched 2026-09-22 schedule

`docs/evidence/forward/schedules/2026-09-22_maker_forward.json` carries
`game_key` equal to `game_id`, the Kalshi event ticker, for all three entries.
Its own census file `link_paths` is keyed by the MLB gamePk
(`823328`, `823412`, `824624`, `824709`, `824785`, `824867`), and the state
capture writes `str(gamePk)` as the state row's game_key. Under the bridge's
`key == options[0][0]` test those entries would count LINKAGE_INVALID. This
row's writer emits the gamePk, so a schedule regenerated by the writer would
not have that shape. This is an observation from reading two committed files;
this lane ran no bridge and measured nothing.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## FIX 1b (2026-09-22, fix lane; AMENDMENT 1 owned files)

AMENDMENT 1 extended this row's ownership to the two sibling test files named
in "Two landed test files this row cannot own" and accepted the companion file
`tests/platformkit/execution/test_forward_schedule_game_key.py`. Both proposed
fixture corrections are now APPLIED; that section's "the edits themselves are
NOT applied" is superseded by this one.

### The event-id finding

Master's `forward_schedule_sources._game` took the COMPETITION id
(`comps[0]["id"]`) as the key for every non-MLB sport, while the state capture
keys ESPN-backed sports by the EVENT id
(`scripts/platformkit/ingame/local_state_capture_sources.py:122`). The two ids
are the same value in a real ESPN scoreboard event, so the divergence was
invisible until a fixture separated them. The build moved the writer to the
event id, which is the state capture's rule; tennis keeps the competition id
because its key is a competition inside a grouping. `espn()` at line 44 of
`test_forward_schedule_sources.py` had pinned the opposite arrangement
(`id="event-id"` with the competition carrying the real key), so six cases
read `event-id` as the game_key and, in the three-event ordering case, all
three constructed events collapsed to one key and were refused as duplicates.
The fixture pinned a shape no provider emits; it was the fixture that was
wrong, not the rule.

### The two fixture corrections

1. `tests/platformkit/execution/test_forward_schedule_sources.py:44` --
   `id="event-id"` -> `id=key`, with a one-line comment naming the real shape.
   The competition id stays `key` (a real event repeats its id on its single
   competition, and the tennis case reads that competition id). No assertion
   text changed: `test_urls_shapes_receipts_and_strict_counts` still pins
   `rows[0]["game_key"] == "101"` for nfl, ncaaf, nba and soccer and
   `{"atp:101", "wta:101"}` for tennis; `test_week_order_duplicates_and_errors`
   still pins one written row from three distinct events plus two
   `duplicate_schedule_game` refusals once the first event is repeated; and
   `test_nfl_date_comes_from_exact_archived_event_id` (renamed in FIX 1c) still pins
   archived row (`game_key="101"`) supplying the missing date. The
   event-id-versus-competition-id discrimination is not weakened by the fixture
   now carrying one id: it lives in the companion file
   `test_forward_schedule_game_key.py`. FIX 1c CORRECTS the claim made here at
   build time -- the companion file's own ESPN fixture ALSO repeated the id, so
   a reverted writer passed its parity test too. The companion fixture now
   carries a distinct competition id and the discrimination is probe-proved
   rather than asserted; see FIX 1c below.
2. `tests/platformkit/execution/test_forward_schedule_team_set.py:75` --
   `game_key="123"` added to the expected entry dict, the same gamePk the
   test's own `link_paths` assertion two lines below already pins
   (`stats["link_paths"] == {"123": "team_set"}`). Nothing else in that
   assertion changed.

The bridge, the capture scheduler and the replay were not edited by this lane.

### Per-file results after the fix (one file per invocation)

```
tests/platformkit/execution/test_forward_schedule_sources.py    63 passed in 0.83s
tests/platformkit/execution/test_forward_schedule_team_set.py   23 passed in 0.59s
tests/platformkit/execution/test_forward_schedule_writer.py     45 passed in 6.29s
tests/platformkit/execution/test_forward_schedule_game_key.py    4 passed in 0.57s
tests/platformkit/execution/test_forward_schedule_fix1f.py      13 passed in 0.49s
tests/platformkit/execution/test_forward_replay.py              49 passed in 3.90s
tests/platformkit/ingame/test_capture_scheduler.py             151 passed in 8.76s
```

## FIX 1c (2026-09-22, fix lane 1c; Opus verifier round 1 ACCEPT WITH CORRECTIONS)

Three items, nothing else. No production behaviour changed except item 3.

### 1. CORRECTION -- the companion parity fixture could not distinguish the rules

`test_forward_schedule_game_key.py:15-17` built its ESPN event with the event id
and the competition id set to the SAME value (`"704321"`), which is the real
provider shape but makes the event-id rule and master's competition-id rule
indistinguishable: a writer reverted to `comp.get("id")` still passed
`test_game_key_equals_state_capture_key`. The fixture now gives the competition
a DIFFERENT id (`id="COMP-NOT-KEY"`) while the event keeps `id="704321"`, so the
state-capture parity comparison can only succeed under the event-id rule.
`test_forward_schedule_sources.py`'s `espn()` helper keeps the real repeated-id
shape from FIX 1b; the separation lives only in this companion file, whose job
is exactly this discrimination.

Revert probe (temporary, then restored; the probe replaced
`forward_schedule_sources.py:69` with master's `key = comp.get("id")`):

```
$ python -m pytest tests/platformkit/execution/test_forward_schedule_game_key.py -q -p no:cacheprovider
.FFFF                                                                    [100%]
>       assert captured and [row["game_key"] for row in rows] == captured
E       AssertionError: assert (['704321'] and ['COMP-NOT-KEY'] == ['704321']
E         At index 0 diff: 'COMP-NOT-KEY' != '704321'
FAILED ...::test_game_key_equals_state_capture_key[soccer-payload1-<lambda>-espn_event_id]
FAILED ...::test_unavailable_key_is_refused_and_counted
FAILED ...::test_a_late_receipt_never_masks_the_earlier_refusal
FAILED ...::test_writer_writes_no_entry_for_an_unavailable_key
4 failed, 1 passed in 1.00s
```

The one case that still passed is the MLB parametrization, which reads no ESPN
id. After restoring the event-id rule (`grep` confirms line 69 is
`key = comp.get("id") if sport == "tennis" else raw.get("id")` and that no probe
text remains in the file):

```
$ python -m pytest tests/platformkit/execution/test_forward_schedule_game_key.py -q -p no:cacheprovider
.....                                                                    [100%]
5 passed in 0.58s
```

### 2. NOTE -- test renamed to name the id it actually pins

`test_forward_schedule_sources.py:213`
`test_nfl_date_comes_from_exact_archived_competition_id` ->
`test_nfl_date_comes_from_exact_archived_event_id`. The archive join key is the
event id since the build; only the function name changed, no assertion.

### 3. NOTE -- a late schedule receipt no longer masks the earlier refusal reason

`forward_schedule_writer.py:208` assigned `game["_refusal"] =
"schedule_response_after_cutoff"` unconditionally, overwriting any reason the
source had already recorded on that game (for example `game_key_unavailable` or
`duplicate_schedule_game`), so the census reported the cutoff instead of the
real cause. It now uses `game.setdefault("_refusal", ...)`, which keeps the
FIRST reason; the cutoff still lands in `record_counts`, so a late response is
never silently dropped. The edit is net zero lines and the writer stays at
exactly 300.

The paired test in the companion file,
`test_a_late_receipt_never_masks_the_earlier_refusal`: an ESPN event with no id,
fetched under a cutoff earlier than the frozen receipt clock, asserting
`refused_by_reason == {"game_key_unavailable": 1}` and
`record_counts["schedule_response_after_cutoff"] == 1`. Probed non-vacuous --
with the assignment temporarily restored the test fails with
`Left contains 1 more item: {'schedule_response_after_cutoff': 1}`, then the
`setdefault` was restored.

### Per-file results after FIX 1c (one file per invocation)

```
tests/platformkit/execution/test_forward_schedule_game_key.py     5 passed in 0.60s
tests/platformkit/execution/test_forward_schedule_sources.py    63 passed in 0.70s
tests/platformkit/execution/test_forward_schedule_team_set.py   23 passed in 0.55s
tests/platformkit/execution/test_forward_schedule_writer.py     45 passed in 1.58s
tests/platformkit/execution/test_forward_schedule_fix1f.py      13 passed in 0.62s
tests/platformkit/execution/test_forward_replay.py              49 passed in 1.75s
tests/platformkit/ingame/test_capture_scheduler.py             151 passed in 3.34s
```

## NOT VERIFIED

- No live provider request, no real archive read, no pod run, no full test tree.
- No real MLB, NBA, soccer, NFL, NCAAF or tennis payload was fetched; every
  payload in these tests is constructed, so the claim that a real ESPN event
  repeats its id on its competition is read from the adapters and from the
  spec, not measured against a provider response today.
- The bridge (`forward_capture_bridge.py`) was read but never executed here:
  that a writer-produced entry actually links a captured state row end to end
  is untested in this lane.
- NFL, NCAAF and tennis key parity with the state capture is reasoned from the
  quoted provenance; only MLB and soccer are covered by a parity test.
- The `away@home` fallback the state capture uses when an ESPN event has no id
  is NOT reproduced by the writer. If a real event ever lacks an id, the state
  capture keeps the game under a fallback key and this writer refuses it. That
  divergence is deliberate per CHANGE item 1 and is unmeasured.
- The archive-mode `state_archive` source label is exercised only by the
  existing archive-mode tests; no test pins the label itself.
- The two sibling-test edits were proposed and probe-verified on copies at
  build time; SUPERSEDED by FIX 1b above -- both are applied and all 8 of those
  cases now pass in the tree as delivered.
- FIX 1b changed test fixtures only; it measured no provider response, ran no
  bridge and re-ran no pod work, so every other limitation in this list
  stands unchanged.
- FIX 1c changed one fixture, one test name and one writer line, and added one
  test. It measured no provider response, ran no bridge and re-ran no pod work,
  so every limitation above stands unchanged. The revert probes above are
  construct-only evidence about these tests, not about live behaviour.
- No commit, no push, no independent verifier acceptance, no lane_commit.
