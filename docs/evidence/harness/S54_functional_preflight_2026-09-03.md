# S54 -- functional preflight probes (importable is not usable)

**Date:** 2026-09-03 | **Verdict:** ACCEPT (6/6 probes OK on the pod, exit 0)
**Commit:** 243ee4773 | **Language:** calibration only; nothing scored, priced,
promoted or charged; no data/registry write, no bar moved, no flag flipped on.

## Premise (reproduced)

`pod_bootstrap_check.py` reported `IMPORTS (/usr/local/bin/python): 14/14 OK`
after the 2026-09-03 container restart while every parquet read failed, because
the restart wiped pyarrow: `import pandas` succeeds without it and
`pd.read_parquet` does not. An import-only gate cannot see that. The runbook
records the same fact at `docs/operations/runpod-runbook.md` step 2 of "After a
CONTAINER RESTART".

## Change (additive)

`--functional`: six named probes, each run in ONE child of `--python` with a
hard 60 s timeout, each printed `OK`/`FAIL <name> <one-line cause>`. A FAIL adds
`N functional probe(s) FAILED` to the RESULT line and makes the exit nonzero.
Without the flag the module behaves exactly as before (same output, same exit).
The probes run under `--python`, not under the checker's own interpreter, so
they measure the interpreter that actually boots the stack.

| probe | what it exercises |
|-------|-------------------|
| `parquet_mlb_games` | `pd.read_parquet(_corpus_path(None))`, rows + cols printed -- the defect above |
| `mlb_predictor_init` | `MLBPredictor()` constructs (full leak-free replay), n_games/teams/r_home |
| `produce_mlb_dry` | `produce_sport('mlb')` -- the BUILDER `produce_once()` wraps; never reaches `store.save`, so `latest.json` is untouched |
| `espn_live_state_mlb` | `ingame_live_state.live_states('mlb')`, the call `inplay_capture_loop` uses; fail-open `[]` means an empty slate is OK, FAIL only on a raise |
| `boot_packages` | fastapi / sklearn / pyarrow / statsmodels / xgboost import with versions printed |
| `supervisor_lock_env` | supervisor pid from `/proc` cmdline (self-excluded), both capture flags present in THAT pid's `/proc/<pid>/environ`, singleton lock file present |

`pod_bootstrap.sh` step 3 keeps the blocking import gate, then runs
`--functional` REPORTED-ONLY (`|| echo ... booting anyway`): on a cold restart
there is no supervisor yet, so `supervisor_lock_env` FAILs by construction and
must not stop the boot that step 4 is about to perform.

## Pod run (2026-09-03, 213.192.2.83:40193, /usr/local/bin/python 3.12.3)

Deployed by `git archive HEAD <one file> | ssh ... 'tar -x --no-same-owner'`;
CRLF-normalised md5 parity local vs pod `e9b245f3c2c3418a2b45c46c463bf089`
(the pod copy is 13,028 bytes to the blob's 12,728 = 300 CRLF endings, content
identical). Nothing killed, started or restarted; every pid read from `/proc`.

```
IMPORTS (/usr/local/bin/python): 14/14 OK
FUNCTIONAL (/usr/local/bin/python, 60s each):
  OK   parquet_mlb_games    rows=27983 cols=10
  OK   mlb_predictor_init   n_games=27983 teams=34 r_home=4.198
  OK   produce_mlb_dry      status=ok predictions=46 markets=152
  OK   espn_live_state_mlb  live_games=0
  OK   boot_packages        fastapi=0.141.1 sklearn=1.8.0 pyarrow=25.0.1 statsmodels=0.15.0 xgboost=3.4.1
  OK   supervisor_lock_env  pid=19236 lock_exists=True flags=CV_CAPTURE_POD,CV_MLB_BOOK_ARCHIVE_LIVE
RESULT: OK -- imports clean, no probe failed
EXIT=0
```

The pod is healthy today: pyarrow 25.0.1 is installed, so the probe that would
have caught the restart defect passes. The contrast the ENV block already shows
is the point of probe 6 -- the checking shell reports all five required flags
MISSING (it is not the booted process), while pid 19236's own `/proc` environ
carries both capture flags. Reading the flags off the supervisor's environ is
the only reading that says anything about the running stack.

## Tests

`tests/platformkit/ops/test_pod_bootstrap_check.py` -- 4 passed, 4.46 s (per-file
run, never the tree). The S54 case uses FAKE probe snippets only, no network and
no corpus: two printing probes -> 0 failures; adding one `raise ValueError` ->
exactly 1 FAIL with `ValueError: pyarrow gone` in the printed cause; a
`time.sleep(30)` probe at `timeout=0.5` returns `timeout after ...` rather than
blocking; `main(--functional)` with the registry monkeypatched to the failing
set exits 1 and to the passing set exits 0 (`check_imports` stubbed so the case
is offline). Two structural asserts pin the six probe names and that no probe
snippet mentions `produce_once` or `store.save`.

## NOT VERIFIED

- The probes were run ONCE, on a healthy pod. The failing branch was never
  exercised against a REAL wiped pyarrow -- only against fake raising probes.
- `--functional` was not run through `pod_bootstrap.sh`; the shell wiring is
  read, not executed. Only `pod_bootstrap_check.py` was deployed; the `.sh`
  change is local (a shell script shipped by `git archive` from this Windows
  checkout would carry CRLF, so it was deliberately NOT deployed).
- 60 s is a chosen bound, not a measured one; no probe's real wall time was
  recorded, so a slower pod could time out a probe that is merely slow.
- `produce_mlb_dry` reaching `status=ok` with 46 predictions is a LIVENESS
  reading only -- nothing here says the snapshot is correct, calibrated, fresh
  or complete, and no number in it was scored.
- `espn_live_state_mlb` observed `live_games=0`, so the non-empty path is
  untested; `live_states` is fail-open, so a silently-broken ESPN fetch returns
  `[]` and passes this probe.
- Probe 6 reads the FIRST `-m supervisor` pid only; two supervisors would not be
  reported (the singleton lock is checked for existence, not for ownership).
- The six probes cover MLB only; no NBA / soccer / tennis path is exercised.
