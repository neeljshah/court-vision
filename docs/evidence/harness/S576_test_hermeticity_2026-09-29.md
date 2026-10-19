# S576 -- test hermeticity (eight test files isolated from gitignored local state)

Row: S576. Spec: docs/evidence/tracking/specs/S576_spec.md (body + AMENDMENTS 1 and 2, binding).
Scope: test-side only. No production module, no file under data/, and no other test file was edited.
Worktree: nba-harness-h245 (branch harness-h245, base 6611e9ab1). Correction (AMENDMENT 2 item 4): the
worktree has a PARTIAL tracked data/ (60 tracked files: README, models/ metrics, maps), not "no data/".
None of the gitignored local state these tests read is present there, so a worktree run is the
"without the local state" environment. The worktree also holds gitignored debris
data/cache/improve/artifacts/nba/v0001-v0008 (19:31-20:06 local, 09-29) written by pre-fix ratchet runs
before fix round 1; fix-round-1 runs did not add to it (see Fix round 1).

## Owned files and what changed

| file | lines after | change |
|---|---|---|
| tests/platformkit/improve/test_daemon_seen_ids_no_candidate.py | 79 | autouse fixture points `PF.SENTINEL_PATH` at `tmp_path/"ABSENT"` |
| tests/platformkit/improve/test_selfimprove_ratchet_sandbox_proof.py | 300 | module-scoped sentinel fixture; `_stat_real()` / `_REAL_STATE` replace every `not _REAL_SENTINEL.exists()` in place; every run_cycle passes `store_root=str(tmp_path / "store")` |
| tests/platformkit/improve/test_prop_line_distance_calib.py | 522 | test_none_input passes a tmp `oof_path`; asserts row count and INSUFFICIENT_DATA |
| tests/platformkit/foundry/test_foundry_runner_s16.py | 202 | `_isolate` records `tiers.load_gate_corpus` calls and returns them |
| tests/platformkit/foundry/test_tiers.py | 278 | T0/T1 test records the T0 corpus load |
| tests/platformkit/live_edge/test_compose.py | 140 | real-slice smoke replaced by the orchestrator test on the synthetic frame, writing to out_dir=tmp_path |
| tests/platformkit/live_edge/test_shadow.py | 151 | replay reads a tiny tmp store in the real schema (not the 8.4M-row real store) |
| tests/platformkit/live_edge/test_tick_replay.py | 160 | B1 filter/parse on a tmp claims fixture; presence skip on the real-baseline check |

## Before (cited from the spec and AMENDMENT 1, measured on main with data/)

- daemon: `2 failed in 1.40s`. ratchet: `4 failed in 4.45s` (:131 via :145 and :207, :246, :283).
- Cause of both: the real `data/cache/improve/PIPELINE_ENABLED` is armed (361 B, Jun 19 20:58). An armed
  NO_CANDIDATE cycle is a genuine decline and advances the cursor; the tests assumed the flag was inert.
- prop_line_distance_calib: test_none_input read cwd-relative `data/cache/pregame_oof.parquet` into the
  O(n^2) rolling sigma and hit the 300 s timeout.
- foundry: `3 failed, 16 passed in 25.49s`, each a `StaleCorpusError` from the nba gate-corpus cache.
  Without data/ the same call raises "no cached corpus", so these three were red in both environments.
- compose: the real-slice smoke loaded real POSSESSIONS/BOX parquet (>1.5 GB) and overwrote
  `data/omni/live_edge/compose/COMPOSE_REPORT.*`.
- shadow: the replay read the whole real nba_price_series.parquet twice. It went over the RSS cap with
  data/ present and was silently skipped without it.
- tick_replay: see "Real-data finding" below. The baseline check was red without data/ (unguarded read).

Before, in the no-data worktree, on `git show HEAD:` copies of the original files:

- daemon: `2 passed`. ratchet: `4 passed`. Both are green only because the sentinel is absent there.
- tick_replay: `2 failed, 7 passed`.
- shadow: `5 passed, 1 skipped`. The replay was silently skipped.

The foundry scratch copies failed for a location reason: `ROOT = parents[3]` of a temp path cannot
find the spec file. Those copies are not quoted as evidence; the spec's own foundry quote stands.

## Why the sentinel fixture uses its own MonkeyPatch

The ratchet test 4 calls `monkeypatch.undo()` (:290 before the edit). If the fixture used the
`monkeypatch` fixture, that undo would also undo the ABSENT patch and re-expose the real armed file at
the next line (`pipeline_enabled() is False`). The fixture therefore uses
its own `pytest.MonkeyPatch.context()` (AMENDMENT 1 item 2). Fix round 1 (AMENDMENT 2 item 2) makes it
MODULE-scoped (`scope="module"`, `tmp_path_factory.mktemp("s576") / "ABSENT"`): tests/conftest.py
autouse fixtures request `monkeypatch`, so a function-scoped context tore down BEFORE the test's
`monkeypatch` and that later teardown re-applied the stale tmp ABSENT path after the module. With the
module scope every function `monkeypatch` restores ABSENT and the module context restores the real
path after the last test. `_REAL_SENTINEL` is captured at import, before any patch.

**Disclosed property change (AMENDMENT 1 item 4).** "Inert on the real path" can no longer be proven
on this host, because the real sentinel IS armed. Test 3 now proves "inert whenever the flag reads an
absent sentinel", plus "the real sentinel is unchanged" (size, sha256, mtime_ns), checked at every
former `not exists()` site. The docstrings were rewritten to match. This is forced by host state and
is not a weakened assertion: every original assertion site is still there.

## Builder-patch disclosure (compose) and retired real-data unit tests

- compose: only `cp.build_team_frame` and `cp.build_player_frame` are patched. Both return
  `_frame_dict(_synthetic_tagged_team_frame(n_teams=4, n_games_per_team=200))`, the file's existing
  helper. `run_one_observable`, `_write_report` and `write_text_atomic` run for real. Both observables
  must be non-blocked with a verdict, both report files must exist under tmp_path, and the real report
  (size, mtime_ns), resolved from the repo root, must be equal before and after. The real-data smoke is
  retired as a unit test because a real run_compose is a >1.5 GB job. It was renamed to
  `test_run_compose_orchestrates_and_writes_report_to_out_dir`.
- shadow: the tmp store uses the real dtypes (ts int64 epoch seconds, game_date string, prob float64,
  traded bool). It holds an early pair, a last pre-cutoff pair (game_date 2026-04-27, the UTC-rollover
  trap) and one post-cutoff pair. A new assertion checks that `prob_home_devig` equals the last
  pre-cutoff devig, which proves the cutoff excluded the post-cutoff pair. The real-data replay is
  retired as a unit test. The presence skipif and the `_STORE`/`_REPO_ROOT` constants were removed
  (they would otherwise be unused).
- Orphan check (B6): before the rename, `git grep` for `test_run_compose_real_slice_smoke` and
  `test_real_claims_file_has_b1_situational_survivors` hit only their own test files and the spec, so
  no reference is orphaned. The shadow test id is unchanged.

## Real-data finding (out of scope, follow-up to file)

The AMENDMENT 1 item 10 probe of the local `data/omni/claims/claims.parquet` found that
`load_b1_survivors()` returns 41 rows. Rows 0-1 are structural claims. Rows 2-40 are
escalation-intake children with `effect_json == {}`, so `parse_claim` returns None on iloc[0] and raises
KeyError 'delta' on the rest. The test now runs on a tmp fixture: 3 testable rows, 2 structural rows
and 2 distractors. It does not assert the real 41, and it does not pin the KeyError.

Follow-up row to file: "validate_claims.load_b1_survivors now selects escalation-intake children with
empty effect_json; parse_claim raises KeyError on effect {}".

Also to file: "splitting test_prop_line_distance_calib.py (522 lines) -- no row yet".

## Pre-existing red found, not in scope

`test_prop_line_distance_calib.py::TestNeverRaises::test_empty_stats_list` fails at the unmodified base
too: `assert 21 == 0`. It was run from `git show HEAD:` in a scratch copy with the same result. The
cause is `prop_line_distance_calib.py:222` (`list(stats) if stats else list(NBA_STATS)`), which treats
an empty stats list as "all stats". This is production behaviour, not hermeticity. The test was left
unchanged because changing it would weaken an assertion. That file is therefore 19 passed, 1 failed,
with no change caused by S576. It is red on master independent of data (since 0d6db3cfc/b1f55adc6);
S576 lands with this ONE pre-existing red disclosed (AMENDMENT 2 item 3). The follow-up needs a NEW
register id (the quality block is exhausted).

## After

Results in the no-data worktree (run_file, max_rss_mb=500 where listed):

| file | summary | peak RSS |
|---|---|---|
| daemon | 2 passed in 0.73s | - |
| ratchet | 4 passed in 2.74s | - |
| prop_line_distance_calib | 1 failed, 19 passed in 2.49s (the pre-existing test_empty_stats_list only) | 160 MB |
| foundry s16 | 7 passed in 16.52s | - |
| foundry tiers | 12 passed in 3.09s | - |
| compose | 6 passed, 1 warning in 76.89s | 184 MB |
| shadow | 6 passed in 5.83s | 182 MB |
| tick_replay | 8 passed, 1 skipped in 1.34s (the skip is test_real_discovery_baseline_is_finite: SKIPPED, not green) | 106 MB |

Simulated armed host: a plugin in the OS temp dir points `PF.SENTINEL_PATH` at an existing tmp
file before collection. Results: daemon 2 passed, ratchet 4 passed. The fixed test_none_input with
cwd = main (real OOF present) gave `1 passed in 3.13s`, peak 151 MB.

**On main WITH data/ (contract-tier verification run, AMENDMENT 2 item 4):** daemon 2 passed,
ratchet 4 passed, tick_replay 9 passed, s16 7 passed, tiers 12 passed, shadow 6 passed,
prop_line_distance_calib 19 passed + 1 failed (the pre-existing test_empty_stats_list). DURING THAT RUN
THE LIVE ARTIFACT STORE CHANGED: the pre-fix ratchet run_cycle SHIPs had no store_root, fell back to
artifact_store.DEFAULT_ROOT (<repo>/data/cache/improve/artifacts, served via served_recal_adapter.py:6),
wrote nba/v0005 + v0006 and moved current.json to 6 (payload byte-identical to v0004). Fixed in
fix round 1 below; that live state was NOT reverted by this row.

## Fix round 1 (AMENDMENT 2 items 1, 2)

Canary plugin (OS temp dir, loaded with `-p`, PYTHONPATH = worktree + plugin dir only; it asserts the
main checkout is NOT on sys.path and that artifact_store resolves from the worktree): at
pytest_configure it points `artifact_store.DEFAULT_ROOT` at an empty canary tmp dir and records
`PF.SENTINEL_PATH`; at pytest_sessionfinish (after all module teardowns) it lists the canary and
compares `PF.SENTINEL_PATH` with the recorded value.

| run | result | canary | SENTINEL_PATH restored |
|---|---|---|---|
| PRE-fix ratchet (scratch copy + tests/conftest.py copy) | 4 passed | 3 entries: nba/, nba/current.json, nba/v0001.json | False (left at pytest-.../test_enabled_shrink_yields_no_0/ABSENT) |
| POST-fix ratchet (worktree) | 4 passed in 2.11s | 0 | True |
| daemon | 2 passed in 0.86s | 0 | True |
| tick_replay | 8 passed, 1 skipped in 6.32s | 0 | True |
| foundry s16 | 7 passed in 26.23s | 0 | True |
| foundry tiers | 12 passed in 3.80s | 0 | True |
| prop_line_distance_calib (run_file 480 s / 500 MB) | 1 failed, 19 passed (pre-existing only), peak 161 MB | 0 | - |
| shadow (run_file) | 6 passed in 2.86s, peak 170 MB | 0 | - |
| compose (run_file) | 6 passed, 1 warning in 128.50s, peak 184 MB | 0 (cumulative, after all runs) | - |

Live state of the MAIN checkout, read-only, before and after all fix-round-1 runs: IDENTICAL (diff of
the two captures empty). artifacts/nba = current.json (14 B, `{"version": 6}`, sha256 6292bb7b...6788)
+ v0001-v0006 (256 B each); PIPELINE_ENABLED 361 B, mtime 2026-06-19 20:58:55.468045800 -0500.

## Mutations (each red under the mutation, green after revert)

1a. Autouse removed, armed host simulated: daemon `2 failed`, ratchet `2 failed, 2 passed` (test 3
precondition and test 4 post-undo).
1b. The simulated real sentinel is rewritten after capture: ratchet `4 failed`.
2. `oof_path` dropped, cwd = main: run_file `timeout after 60 s`, peak 318 MB.
3. The T0 `load_gate_corpus` line is deleted in tiers.py (worktree only): s16 `2 failed, 5 passed`
and tiers `2 failed, 10 passed`. Reverted with `git -C <wt> checkout -- scripts/platformkit/foundry/tiers.py`.
4. `rc._OUT_DIR` points at a second tmp dir and `out_dir` is dropped: `1 failed`. The failure is at the
reports-exist assertion.
5a. The post-cutoff pair is moved before the cutoff: `0.3960... == 0.2673...` red on the
prob_home_devig assertion.
5b. The `_STORE_DIR` patch is dropped (no-data worktree): `assert None is not None`.
6. One testable claim is made structural: `assert 3 == 2`.

## Stat table (real files; read-only stat, sha256 for the small ones)

Taken after every builder run (the spec quotes match: sentinel 361 B Jun 19 20:58, compose report
3838/2009 B Jul 14 14:18):

| path | size | mtime_ns | sha256 |
|---|---|---|---|
| data/cache/improve/PIPELINE_ENABLED | 361 | 1781920735468045800 | e96a582f3f78ff00653aea73ea98f1d7529b237463429304adb1480005b4f56d |
| data/cache/pregame_oof.parquet | 4184929 | 1779924750464126700 | - |
| data/omni/live_edge/compose/COMPOSE_REPORT.json | 3838 | 1784056689548339100 | f320b0407faaee749639b95c69176d9dd6870c67d05ca35ef62e9600cd14f62c |
| data/omni/live_edge/compose/COMPOSE_REPORT.md | 2009 | 1784056689552339400 | c6d164c8a9dc7ae2245000447ccde1f5b82eadada450634050e00603ef6d79b2 |
| data/cache/inplay_odds/nba_price_series.parquet | 25140428 | 1783578631625083600 | - |
| data/omni/claims/claims.parquet | 8272084 | 1784079542358545800 | - |
| data/cache/ingame/sim2_possessions.parquet | 4405872 | 1783613637529667400 | - |
| data/cache/improve/artifacts/nba/current.json | 14 | 1790730489395843000 (fix round 1) | 6292bb7b1b7efbe51d34065ac34f623ecf1fe9fec7ae2f07d1af910ad1a66788 |
| data/cache/improve/artifacts/nba/ listing | v0001-v0006, 256 B each | v0005 1790729959.97 s, v0006 1790730489.39 s | - |

## Identities

- Candidate: built on 6611e9ab1; landed onto master b6e7d8827 by cherry-pick (landing sha recorded in the register row S576). AMENDMENT 3 (fix round 2): the SHIP assertion also requires tmp store/nba/current.json; store_root-drop mutation -> 1 failed (canary received artifacts), clean -> 4 passed, canary empty.
- Verification base = master at landing (`git rev-parse master` then; b71de346d at fix round 1), not
  55ad80d31 (AMENDMENT 2 item 4). The build base is 6611e9ab1f2733dabdc0d21531c0dea285350143.
- A9 identities (LF-normalised) are to be recomputed from disk by the verifier as the last edit.

## NOT VERIFIED

- The real nba gate-corpus rebuild was not attempted. Whether the real caches stay stale is register
  state.
- The production flag, OOF and corpus code paths were not changed.
- The artifact-store change from the round-0 verification run (v0005/v0006, current.json -> 6) is not
  reverted here (live state; owner decision).
- test_empty_stats_list stays red for a production cause (see above).
