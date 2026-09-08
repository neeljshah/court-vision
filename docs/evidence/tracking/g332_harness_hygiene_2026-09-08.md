VERDICT: PARTIAL -- 7 of n=7 harness-hygiene holes reproduced on a construct and 0 were CLOSED ALREADY; 5 of them (fatal snapshot, expected arm, snapshot-list rigour, construct-only fallback, TXT rule) now have a test that FAILS on the old code and passes on the new, and the remaining 2 are COVERAGE holes -- byte parity already held for the `g310_instance_key` and `g330_run_attempt2` opt-outs and what was absent was the ASSERTION, so their tests cannot fail on unmutated old code and their teeth are shown by a mutation run instead (this exception was sealed in the prereg BEFORE the change). No landed number moved: the committed G327 attempt-2 report and table recompute BYTE-IDENTICAL through the changed reader, and over the 11 of n=13 re-swept entries that were committed at both sweeps 6 of n=161 counts moved verdict, all `RECOMPUTABLE` -> `UNVERIFIED_SNAPSHOT`, with `NOT RECOMPUTABLE` (57) and `UNPARSED` (82) unchanged.

# G332 -- harness hygiene: opt-out parity, fatal snapshot, census rigour (TOOLING ROW)
Spec `docs/evidence/tracking/specs/G332_spec.md` VERSION 2026-09-08. Prereg `docs/evidence/tracking/g332_prereg_2026-09-08.md`, seal `7fc8c90105eb56b820bc8829a01cf656ac309d407a84847db161f4282b2e8d74` over the LF-normalised bytes above its seal line, committed ALONE at `89ff84be3` BEFORE any code changed. LOCAL only: no pod, no GPU, no video, no network. Guards on harness code, NOT measurements. **Eye check: NONE** -- there is no labelling here, only file reading and arithmetic. NO BAR IS SET OR MOVED.

## PREMISE (step 0) -- 7 of n=7 reproduce, 0 CLOSED ALREADY
Run on constructs against unchanged master `3d486814c`. `tests_asserting_parity` is a grep of `tests/platformkit/` for the opt-out flag.
```
PREMISE a1 g310_instance_key: files_on=000004 files_off=000003 only_extra=['environment.json'] shared_byte_identical=True tests_asserting_parity=000000
PREMISE a2 g330_run_attempt2: files_on=000002 files_off=000001 only_extra=['environment.json'] shared_byte_identical=True tests_asserting_parity=000000
PREMISE b1 verify_snapshot: games_in=000002 kept=000000 raised=False (one hash altered, one file absent -> scoring proceeds on the reduced set)
           control: intact manifest games_in=000001 kept=000001
PREMISE b2 read_arm_csv: a batch8 file saved under the fp32 name was ACCEPTED -- file_arm_cells=['batch8'] slots=000003 boxes=000587 raised=False
PREMISE c1 snapshot-list rigour: entries carry NO sha256 and NO timestamp; verdict=RECOMPUTABLE components=[3] artifacts=['snapshots.json']
PREMISE c2 git-index fallback: git ls-files rc=000128 (fatal: not a git repository); the checker fell back to the filesystem walk ['memo.md', 'untracked.csv'] and returned verdict=RECOMPUTABLE artifacts=['untracked.csv'] -- an artifact in NO index passed as committed
PREMISE c3 TXT header subtraction: probe.txt holds 000003 non-blank lines; the checker offers [2, 3] -- the 000002 comes from a header subtraction the sealed prereg did not specify
```
## THE CHANGES AND THE TESTS (n = 7 tests, one per hole)
`verify_snapshot(manifest, snap, fatal=True)` raises on any missing or mismatched frame, naming the game, the slot and the frame id; `fatal=False` stays reachable and reproduces the landed drop-and-continue with an explicit `DROPPED` line. `read_arm_csv(path, expected_arm=None)` raises when the file's arm cell differs from the arm the caller expects; `g327_report.score` now passes the arm for all 7 files it opens. `census_recomputable` gains the additive verdict `UNVERIFIED_SNAPSHOT`, the flags `--construct-only` and `--txt-header`, and the keywords `construct_only` / `txt_header`. B2: every landed signature stays callable with its old arguments -- `_json_ints` and `_artifact_values` keep their flat-set returns, and `fatal=True` is the one deliberate default change, justified because scoring a silently reduced frame set IS the defect and it cannot move a committed number (the byte-identity check below is the proof).
FAILING RUN ON THE OLD CODE, one per hole: b1 `DID NOT RAISE <class 'ValueError'>`; b2 `TypeError: read_arm_csv() got an unexpected keyword argument 'expected_arm'`; c1 `TypeError: scan_memo() got an unexpected keyword argument 'construct_only'`; c2 `DID NOT RAISE <class 'RuntimeError'>`; c3 `assert {2, 3} == {3}` -- 5 failed, 2 passed. After the change: 7 passed.
MUTATION RUN (the a1/a2 teeth): with `env_sidecar.write` stubbed to a no-op, both parity tests fail with `AssertionError: assert set() == {'environment.json'}` -- 2 failed. The stub was reverted and `git diff` on that file is empty.

## BYTE-IDENTITY -- no landed number moved
`g327_report.score` re-run over the 7 committed `g327_attempt2` CSVs through the CHANGED reader, into a temporary directory: `g327a2_report.json` and `g327a2_table.md` both recompute IDENTICAL to the committed bytes, at the two sha256 values frozen in the prereg (`c05cb90f...b6e` and `b7da6cb7...4ce`). The committed files were opened read-only.

## THE RE-SWEEP (B7 -- all n=13 G319 entries), verdict counts as RECOMP/UNVERIF/NOTRECOMP/UNPARSED/ABSENT
The committed `g319_.../sweep.csv` is FROZEN and untouched; the new run is `g332_harness_hygiene_2026-09-08/sweep_g332.csv` (237 data lines, every integer cell zero-padded to six digits), and it reproduces byte-identical on a second run.

| entry | n before -> after | before -> after | why it moved |
|---|---|---|---|
| G309 | 4 -> 4 | 1/0/3/0/0 -> 1/0/3/0/0 | unchanged |
| G312 | 4 -> 4 | 2/0/1/1/0 -> 2/0/1/1/0 | unchanged |
| G313 | 1 -> 1 | 0/0/0/1/0 -> 0/0/0/1/0 | unchanged |
| G317 | 6 -> 6 | 5/0/1/0/0 -> 5/0/1/0/0 | unchanged |
| S314 | 2 -> 2 | 0/0/2/0/0 -> 0/0/2/0/0 | unchanged |
| G329a1 | 27 -> 27 | 1/0/12/14/0 -> 1/0/12/14/0 | unchanged |
| G329a2 | 23 -> 23 | 1/0/8/14/0 -> 1/0/8/14/0 | unchanged |
| G327a1 | 0 -> 28 | ABSENT -> 6/0/6/16/0 | the memo LANDED between the two sweeps; a CORPUS change, not the checker |
| G327a2 | 0 -> 48 | ABSENT -> 26/2/13/7/0 | same; its 2 unverified counts are new, with no before to compare |
| G330a1 | 19 -> 19 | 1/0/5/13/0 -> 1/0/5/13/0 | unchanged |
| G330a2 | 35 -> 35 | 1/0/12/22/0 -> 1/0/12/22/0 | unchanged |
| G310a2 | 25 -> 25 | 8/0/4/13/0 -> 3/5/4/13/0 | 5 counts backed only by a `run_summary.json` record list with no sha256, timestamp or chain |
| G331 | 15 -> 15 | 2/0/9/4/0 -> 1/1/9/4/0 | 1 count backed only by the `g310_attempt2_proxies.json` record list |
| **11 entries committed at BOTH sweeps** | 161 -> 161 | 22/0/57/82/0 -> 16/6/57/82/0 | exactly 6 of n=161 moved, every one `RECOMPUTABLE` -> `UNVERIFIED_SNAPSHOT` | 161 parsed occurrences; 154 unique count keys.

The deltas describe the CHECKER's new strictness. NO landed memo was edited, NO landed number changed, and no memo's own verdict is restated here.
## NOT VERIFIED
- a1 and a2 are COVERAGE holes. Their tests do NOT fail on unmutated old code, because byte parity already held; only the mutation run shows they bite. Anyone reading the bar as "every test must fail on the old code" should read this row as PARTIAL on those two.
- `UNVERIFIED_SNAPSHOT` is CONSERVATIVE and its 6 + 2 = 8 occurrences are NOT evidence that any count is wrong. The checker cannot tell a snapshot list from any other list of objects, so a record list never meant as a snapshot list is reported unverified rather than silently accepted.
- The chain check compares string values only: two entries carrying the SAME sha256 would satisfy it. CENSUS_RULE clause 3 (ORDER) and clause 5 (one snapshot per read) stay outside what any committed-bytes check can see, exactly as G319 recorded.
- `read_arm_csv` takes the arm from the first data row, so an arm CSV with a header and NO data rows has no arm cell and `expected_arm` does not catch it.
- The `fatal=True` default is proven harmless only for the ONE committed snapshot re-scored here. A future rerun over a snapshot that does NOT verify whole will now stop instead of scoring a reduced set -- that is the intent, not a regression.
- G319's own limitations still stand unchanged: a bare basename resolves to every committed file with that name, so `RECOMPUTABLE` remains an UPPER bound, and the parser still misses counts written in words or with digit separators.
- Nothing was adopted, no default moved, no flag flipped, nothing written under `data/registry/`, no threshold touched, and `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` was not opened for writing. `src/`, `kernel/`, `api/`, `intel/`, `domains/`, `scripts/team_system/` and the pod were not touched. No detector, matcher or sim was run and 0 GPU seconds were spent.

WALL TIME: about 40 minutes of lane time, entirely local; 0 GPU seconds, 0 pod commands. TEST (each alone, `-q -p no:cacheprovider`): `test_g332_harness_hygiene.py` 7 passed | `test_g62_environment_sidecar.py` 7 passed | `test_g327_batch_stability.py` 16 passed | `test_g319_census_recomputable.py` 4 passed | `test_g310_instance_key.py` 10 passed | `test_g330_panorama_identity.py` 17 passed | `test_loc_rail_scope.py` 1 passed. Never a full pytest. Every touched file is within the 300-line rail: census_recomputable 279, g327_arms 296, g327_report 200, g327_detector_batch_stability 295, the new test 209.
ARTIFACT SHA-256 (over LF-normalised bytes): prereg `cf50bb386c8cfd92d5eba345f01b468945bf223c81115d9465a581f819de076f` (as committed, seal line included) | `census_recomputable.py` `7517d3acdb36f9d9eb036810c5d7335ce8a7af74ba423f7691db055be6f862ba` | `g327_arms.py` `4ff0ddc84eaa99916ddbc308ae09ef4a83fc2e5ea91bef4c74f7b5e09cb45d20` | `g327_report.py` `550c92c814d92fe31db350234dd71ba8beb5e7255b81389dc774e586fe7d6400` | `g327_detector_batch_stability.py` `d206ee2d1d717527965a5228c3edefb289e269f62ef1c1960010b49155b0a602` | `test_g332_harness_hygiene.py` `73bd2852bd37a026d0fccd3df816c9b3842ad1a049b6dda65ca02e1004ca25ca` | `test_g319_census_recomputable.py` `b635233c095c0a4efc6543be190c23bfaaa6f5686499deda146c3ba34d9912e3` | `sweep_g332.csv` `536c10cffc08a59ca8c56aa1ac9ce363275e5e5b863f9f977ba286e24bb2de7f`. Hexadecimal digests are single tokens; a digit run inside one is not a standalone figure.
Corrections (fix 1b, 2026-09-08, verifier codex-sol): verdict DONE -> PARTIAL because the spec bar (every reproduced hole's test fails on old code) is met for 5/7 holes only; the prereg's a1/a2 mutation-run exception (prereg:115-121) is NOT honoured under Q3 (the sealed prereg stays frozen; its exception is void); NEW GAPs: snapshot_list_ok accepts two successive entries with the same sha256 and no predecessor field (census_recomputable.py:95-103); the snapshot loader reports counts but no missing frame id (g327_detector_batch_stability.py:124-132).
## Landing 2026-09-08 (verifier codex-sol: ACCEPT as honest PARTIAL, no corrections) -- NEW GAP: `snapshot_list_ok` accepts two successive entries carrying the SAME sha256 with no predecessor-reference field; NEW GAP: the snapshot loader reports reload counts but names no missing frame id for a truncated snapshot; NEW GAP: this memo appended its opening code fence after prose and left the closer unclosed, fixed at landing by moving the fence to its own line and dropping the blank line before two headings to hold the 60-line cap.
Vocabulary follows contract Q6; automated scan required.
