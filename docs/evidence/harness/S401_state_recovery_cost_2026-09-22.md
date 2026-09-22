# S401 state capture: per-item full-shard recovery

Candidate implemented; local CONSTRUCT and fixture checks only. Independent acceptance pending.
No production process, archive, lock or STOP sentinel was touched by this lane.

## Binding before-condition (before edits)

Every line number in the spec is correct on master. `scripts/platformkit/ingame/local_state_capture.py`
lines 95-110 on master:

```python
                  clock: Callable, writer: StateWriter) -> tuple[list, list, int]:
    day, nowc = iso(now)[:10], clock()
    if state.get('day') != day:
        for name in ('last_state', 'last_polled', 'mlb_games', 'sport_status', 'known_games'):
            state[name] = {}
        state.pop('mlb_disc_ts', None)
        state['day'] = day
    if not state.get('initialized'):
        state['last_state'].update({k: v for k, v in writer.recover_states(now, sports).items()
                                    if v[0] != 'final'})
        state['initialized'] = True
    errors = state.setdefault('adapter_errors', {})
    last_polled, last_state = state['last_polled'], state['last_state']
    mlb_games, known = state['mlb_games'], state['known_games']
    rows, finals = [], []
    tasks = []
```

Lines 160-180 on master (line 172 is the per-item call named by the spec):

```python
            statuses = {g.get('status') for g in items}
            state['sport_status'][sport] = next((s for s in ('live', 'pre', 'delayed', 'final')
                                                  if s in statuses), 'none')
        for item in items:
            receipt = item.get('receipt') or getter.last_receipt
            if not receipt or receipt.get('http_status') != 200:
                client.metrics.drop(sport, 'missing_successful_receipt')
                continue
            item = dict(item, receipt=receipt)
            key = sport + ':' + str(item['game_key'])
            previous = {key: last_state[key]} if key in last_state else {}
            if not previous:
                recovered = writer.recover_states(now, [sport]).get(key)
                if recovered is not None:
                    previous[key] = recovered
            record = _build_row(sport, item, receipt['request_start_utc'], receipt['response_end_utc'],
                                iso(now), previous)
            rows.append(record)
            last_state[key] = previous[key]
            if sport == 'mlb':
                mlb_games[str(item['game_key'])] = {k: v for k, v in item.items() if k != 'raw'}
```

`scripts/platformkit/ingame/local_state_capture_io.py` on master, `recover_states` (line 153) and the
head of `recover_rows` (line 164); this file is NOT edited by S401:

```python
    def recover_states(self, now, sports: list[str]) -> dict:
        """Recover the latest unambiguous state at or before now under the lock."""
        states, latest = {}, {}
        for row in self.recover_rows(now, sports):
            key = row['sport'] + ':' + str(row['game_key'])
            stamp = _receipt_time(row['response_end_utc'])
            if key not in latest or stamp > latest[key]:
                latest[key] = stamp
                states[key] = (row['status'], row['state'])
        return states

    def recover_rows(self, now, sports: list[str]):
        """Yield valid as-of receipts in time order; refuse conflicting identities."""
        cutoff = _receipt_time(now.isoformat())
        ...
        for day in (now - timedelta(days=1), now):
            for sport in sorted(set(sports)):
                path = self.root.path / sport / (day.strftime('%Y-%m-%d') + '.jsonl')
                if not path.exists():
                    continue
                try:
                    with path.open(encoding='ascii') as stream:
```

Each `recover_states` call therefore opens every existing shard of the requested sports exactly once
and re-reads it in full.

Per-file tests on master, before any edit:

| Test file | Result |
|---|---|
| `tests/platformkit/ingame/test_local_state_capture.py` | `17 passed in 1.10s` |
| `tests/platformkit/ingame/test_state_capture_io.py` | `13 passed in 0.79s` |

## recover_rows call count, before and after

`test_recover_rows_calls_are_one_at_init_and_none_inside_a_tick` builds one synthetic shard of 2000 rows
(50 keys times 40 receipts, all `final`, so the init recovery keeps none of them in `last_state`) and
counts `StateWriter.recover_rows` calls during ONE tick that polls all 50 keys. Only that one shard
exists, and `recover_rows` opens each existing shard once per call, so calls equal shard opens.

- BEFORE (master source, the new test run against it): the assertion failed with
  `assert [['nba'], ['n... ['nba'], ...] == [['nba']]` and
  `Left contains 50 more items, first extra item: ['nba']` -- that is 51 shard opens in one tick:
  one init recovery plus one per unseen key, the 50 per-item opens the spec predicts.
- AFTER (fixed source, FIX 1b): 1 call, the init call; the test passes on `assert calls == [['nba']]`.

The companion test `test_recover_rows_calls_are_one_at_rollover_and_none_inside_a_tick` counted three
calls on master for a tick with two unseen keys
(`assert [['nba'], ['nba'], ['nba']] == [['nba'], ['nba']]`) and counts exactly one after FIX 1b (the
init call), plus exactly one further call for the day-rollover rebuild and none inside either tick.
Both tests count `StateWriter.recover_rows` CALLS; one call re-reads both of a sport's shards in full.

## Measured production facts (recorded, not reproduced by this lane)

On the supervised relaunch of 2026-09-22 15:39Z from master: after 25 minutes the child (pid 30528)
held 914 CPU-seconds and a 1.0 GB working set with zero rows written and no heartbeat for any sport.
The tennis shards it re-reads are 162 MB (2026-09-21) plus 52 MB (2026-09-22) for 391 tracked games.
A UTC day rollover resets `last_state` and would repeat the storm during tonight's games, so the
frozen bar "maximum state receipt gap <= 30 s" (S362 AMENDMENT 2, Q-2) cannot survive it.

## Change

Owned files: `scripts/platformkit/ingame/local_state_capture.py` (253 to 265 lines),
`tests/platformkit/ingame/test_local_state_capture.py` (263 to 300 lines) and the new
`tests/platformkit/ingame/test_local_state_capture_differential.py` (112 to 160 lines, added by FIX 1b
under AMENDMENT 2(b) because the existing test file is at the 300-line rail). All ASCII, all <= 300 lines.
`scripts/platformkit/ingame/local_state_capture_io.py` is byte-identical to master.

1. `state['recovered']` holds the FULL recovered map, finals included, built by one
   `writer.recover_states(now, sports)` per process start and one per day rollover. It is never pruned
   within the day; `_prune_game` still prunes `last_state` only, and `last_state` keeps its unchanged
   non-final seeding at init and stays empty immediately after a rollover, exactly as on master, so the
   mlb discovery branch that tests `key in last_state` keeps its master semantics.
2. The per-item path reads `last_state` first, then `state['recovered']`, and nothing else. A key in
   neither map has no archived state, so no `recover_states` call is made inside a tick at all. The
   module now holds exactly one `recover_states` call site, at line 108, in the init/rollover block.
   (CORRECTED by FIX 1b: the round-1 candidate rescanned here. See the FIX 1b section.)
3. Every row written also updates `state['recovered'][key]`, so for every key this process has written
   the map holds the state of the newest row it wrote, committed or about to be committed by this tick.
   Under the single-writer archive lock that is the newest state the archive can hold, which is what
   makes the map authoritative and the rescan unnecessary. That keeps the previous-state semantics
   identical to master EXCEPT where the archive itself would refuse the row: two differing rows for
   one key in one poll share a receipt, `recover_rows` drops that identity, so the map drops the key
   too (FIX 1c). A recovered previous state is still carried per field and `state_changed` is computed
   against it; `_build_row` is unchanged, so row fields and their order are unchanged.

Byte-identity evidence is indirect: all 17 pre-existing tests in the file pass unchanged, including the
ones asserting exact `state_changed` sequences across restarts, finals, pruning and the day boundary
(`test_archive_recovery_yesterday_then_last_today`, `test_final_repeat_compares_archive_after_pruning`,
`test_final_and_day_boundary_prune_all_event_maps`, `test_unseeded_restart_has_null_baseline`).

## FIX 1b (AMENDMENT 2, after the Opus verifier round 1 REJECT)

Round 1 was REJECTed on the per-tick rescan. AMENDMENT 2 removes it; this section records the fix and
its evidence. Worktree `harness-h62` at `009880081`.

**BLOCKING finding (resolved).** The round-1 candidate ran
`recovered.update(writer.recover_states(now, [sport]))` inside the tick for the first key absent from
both maps. That re-read the archive, which does not yet hold the rows this tick has built (the commit
happens after `_prepare_tick`), so it CLOBBERED entries mirrored earlier in the same tick. A game that
finalizes in tick T is pruned from `last_state`, so tick T+1 read the clobbered stale entry and wrote a
different row than master. FIX 1b deletes the rescan (and the `rescanned` set): the recovered map is
authoritative after init and after the rollover rebuild, and a key absent from both maps has no
archived state.

**Verifier 3-tick reproduction** (nba; tick 1 `[A live]`, ticks 2 and 3 `[A final, B new]`;
`(game_key, status, state_changed)` per written row):

| Row | master | BEFORE (round-1 candidate) | AFTER (FIX 1b) |
|---:|---|---|---|
| 1 | `('A', 'live', None)` | `('A', 'live', None)` | `('A', 'live', None)` |
| 2 | `('A', 'final', True)` | `('A', 'final', True)` | `('A', 'final', True)` |
| 3 | `('B', 'live', None)` | `('B', 'live', None)` | `('B', 'live', None)` |
| 4 | `('A', 'final', False)` | `('A', 'final', True)`  DIFFERS | `('A', 'final', False)` |
| 5 | `('B', 'live', False)` | `('B', 'live', False)` | `('B', 'live', False)` |

BEFORE, reversing the tick's item order to `[B, A]` made the candidate match master, so the emitted row
depended on scoreboard item order. AFTER, both orders match master and each game's
`(status, state_changed)` sequence is identical in either order. This case ships as
`test_final_pruned_in_the_tick_a_new_key_appears_then_repolled`.

**Differential test** (AMENDMENT 2(b)), `tests/platformkit/ingame/test_local_state_capture_differential.py`:
`master_expected` reimplements master's per-item lookup from the master lines quoted at the top of this
memo -- `last_state` if present, else the latest COMMITTED archive row for the key, else no previous --
together with master's commit-then-prune-finals order. It is scored against the rows the candidate
actually writes, over randomized scoreboards: 60 seeds, 4 games, 8 ticks, both item orders
(as-polled and reversed) = 120 runs. Games appear late, advance, finalize, then keep re-reporting that
same final state, and drop out of the scoreboard at random. Every non-timestamp field is compared
(`game_key, status, state, date, home_abbr, away_abbr, source_ts, scheduled_start_utc, date_reason,
sport, state_changed, http_status, capture_version`); `raw_sha256` is excluded because it hashes the
receipt body and cannot depend on the lookup.

- RESULT: `seeds=60 runs=120 rows_compared=2890 divergences=0`.
- POWER CHECK (the differential can fail): with the rescan temporarily restored in the same worktree,
  the identical run reported `seeds=60 runs=120 rows_compared=2890 divergences=15` and the
  pruned-then-repolled case failed with `At index 3 diff: ('A', 'final', True) != ('A', 'final', False)`.
  The rescan was then removed again and both tests pass.
- The `compared >= 2000` assertion in the test keeps a vacuous pass from reading as a clean one.

**Open-count test renamed** (AMENDMENT 2(c)). `test_one_shard_open_per_tick_for_fifty_unseen_finals` ->
`test_recover_rows_calls_are_one_at_init_and_none_inside_a_tick`, and
`test_unknown_keys_and_rollover_recover_once_per_sport` ->
`test_recover_rows_calls_are_one_at_rollover_and_none_inside_a_tick`. Both count
`StateWriter.recover_rows` CALLS, and they now assert exactly one call at init, exactly one at the day
rollover, and none inside a tick (`calls == [['nba']]` after the first tick, `calls[1:] == [['nba']]`
after the rollover tick).

**Correction to this memo.** The round-1 Change item 3 claimed the map "mirrors the newest archived
state for every key this process wrote". That was false on the rescan path, where the rescan overwrote
mirrored entries with older archived rows. Item 3 above is rewritten; the claim now rests on the
single-writer lock and on the rescan being gone, and is measured by the differential run quoted above.

**Verifier NOTE 4 (the rescan was a guaranteed-useless full re-read).** Accepted and acted on: that is
exactly what AMENDMENT 2(a) removes.

## FIX 1c (after the Opus verifier round 2 ACCEPT WITH CORRECTIONS)

Round 2 accepted the shape of FIX 1b and named two corrections, applied here verbatim and alone.
`local_state_capture_io.py` is still byte-identical to master (`git diff master` on it is empty).

**CORRECTION 1 -- a key duplicated inside one poll must DROP its mirrored baseline**
(`local_state_capture.py:183` before this fix). Every item in one poll shares one receipt, so two rows
for one `game_key` in a tick land in the archive under one identity `(sport, key, stamp)` with differing
state; `recover_rows` (`local_state_capture_io.py:195-200`) records an `archive_receipt_conflicts` drop
and refuses that identity, so master has NO baseline for the key. The round-2 candidate mirrored the
second row into `state['recovered']`, so the next tick read a baseline the archive would never return.
The fix mirrors master's rule in about five lines: a per-tick `written` map holds the last row emitted
per key, and when the new row differs from it and shares its `response_end_utc` the key is POPPED from
`recovered` instead of written to it. `last_state[key] = previous[key]` is unchanged. Reproduction
(nba; tick 1 the duplicated pair, tick 2 `[D final score 9]`; `(score, state_changed)` per written row):

| Order | master | BEFORE (round-2 candidate) | AFTER (FIX 1c) |
|---|---|---|---|
| as polled `[D final 5, D final 9]` | `[(5, None), (9, True), (9, None)]` | `[(5, None), (9, True), (9, False)]` DIFFERS | `[(5, None), (9, True), (9, None)]` |
| reversed `[D final 9, D final 5]` | `[(9, None), (5, True), (9, None)]` | `[(9, None), (5, True), (9, True)]` DIFFERS | `[(9, None), (5, True), (9, None)]` |

Master's rows are the verifier's; the third row has no baseline because of the receipt conflict, not a
missing archive row. Ships as `test_duplicate_key_in_one_poll_leaves_no_baseline_like_the_archive`. Its
control `test_duplicate_live_key_control_keeps_its_last_state_baseline` duplicates a LIVE key: never
pruned, so `last_state` still supplies the baseline and the rows are `[(5, None), (9, True), (9, False)]`
BEFORE and AFTER -- the new rule does not disturb the live path. `master_expected` is NOT extended to
model the receipt conflict; its docstring now records that it assumes at most one row per key per tick,
which `random_ticks` guarantees.

**CORRECTION 2 -- a caller resuming with `initialized=True` and no `recovered` key ran blind**
(`local_state_capture.py:103,115` before this fix). The guard was
`if rolled or not state.get('initialized'):`, so such a caller skipped the archive pass and the
`state.setdefault('recovered', {})` at line 115 handed the tick an empty map that never recovers. The
guard is now `if rolled or 'recovered' not in state:` (one token); the `initialized` test inside the
block still gates the non-final seeding of `last_state`, so seeding semantics are untouched.
Reproduction: archive row `C live` in yesterday's shard, `state = dict(day=today, initialized=True,
last_state={}, ...)`, poll `[C live]`. Master writes `state_changed False`; BEFORE the candidate wrote
`None` (`assert None is False`); AFTER it writes `False`. Ships as
`test_resume_with_initialized_state_and_no_recovered_map_recovers`. The shipped differential, re-run on
the FIX 1c source: `seeds=60 runs=120 rows_compared=2890 divergences=0`.

## Results (this session)

Each file ran separately with `-q -p no:cacheprovider`.

| Test file | Passed | Failed |
|---|---:|---:|
| `tests/platformkit/ingame/test_local_state_capture.py` | 19 | 0 |
| `tests/platformkit/ingame/test_state_capture_io.py` | 13 | 0 |
| `tests/platformkit/ingame/test_state_capture_sources.py` | 73 | 0 |
| `tests/platformkit/ingame/test_state_capture_recovery.py` | 25 | 0 |
| `tests/platformkit/ingame/test_state_capture_commit.py` | 11 | 0 |
| `tests/platformkit/ingame/test_local_state_capture_differential.py` | 5 | 0 |

Total: 146 passed, zero failed across six individual invocations, all re-run on the FIX 1c source.
The full suite was never run. `tests/platformkit/test_loc_rail_scope.py` passed 1/0 in the FIX 1b
session and was not re-run by FIX 1c; the LOC rail is re-checked by the line counts below.
`python -m scripts.platformkit.ingame.local_state_capture --help` exited 0 with its usage text.
The shared LOC rail (A12) needed no allowlist change: `local_state_capture.py` is 265 lines, is not in
`ALLOWLIST`, and the rail's 300-line cap covers non-test PlatformKit modules only.

## NOT VERIFIED

- No production relaunch, live smoke, real archive, network, pod or restart was exercised. Whether the
  fixed capture writes its first row within the 30 s bar tonight is unproven here; the relaunch is the
  orchestrator's next step and is recorded in NOW.md. No STOP sentinel was written by this lane.
- The differential compares the candidate against a REIMPLEMENTATION of master's lookup in the test,
  not against master's module executed, and over CONSTRUCT scoreboards, not real archive inputs. If the
  reimplementation misreads master, the differential inherits that error; it is quoted from the master
  lines at the top of this memo and no other master behaviour is modelled.
- The 914 CPU-second, 1.0 GB, 162 MB, 52 MB and 391-game figures are quoted from the spec's record of
  the 15:39Z relaunch. This lane did not re-measure them and did not open the running capture's files.
- No test covers more than one sport in a tick: the init and rollover calls are exercised for `nba`
  only, the differential is `nba` only, and the mlb discovery interaction with the recovered map is not
  directly tested.
- Memory growth of `state['recovered']` across a long day (it is deep-copied per tick with the rest of
  the state) is not measured; it is bounded by the tracked-game count and reset at the rollover.
- Concurrent writers to the same shard are out of scope: the mirror in item 3 assumes this process is
  the only writer, which the archive lock enforces but which no test here asserts.
- Row S393 (worktree h52) also edits this module. Per AMENDMENT 1 S401 lands FIRST and h52 rebases
  afterwards; this worktree is on master as of 009880081 and no rebase against S393 was performed.
- The FIX 1c pop is not sticky: three rows for one key in one poll whose last two are identical would
  re-add a baseline that `recover_rows` still refuses. That is the verifier's fix as written, no test
  here constructs it, and no archive this lane read contains it. The CORRECTION 2 reproduction uses a
  CONSTRUCT state dict, not a state restored from a real process; no resumed capture was exercised.
