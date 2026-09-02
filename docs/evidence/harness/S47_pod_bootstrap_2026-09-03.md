# S47 -- pod bootstrap after a container restart (2026-09-03)

Lane O. Calibration language only. Nothing here is a performance, profit or edge
claim: this row measures PACKAGE + FILE + IMPORT readiness of the pod paper
stack, and whether a re-run of the bootstrap correctly SKIPS what already runs.

Pod reached with `ssh -o BatchMode=yes -F ~/.ssh/config.pod pod` (port resolved
from the alias, today 40193 -- it drifts; never hardcode). Every pid below was
read from `/proc` cmdlines. Nothing was killed and nothing was started.

## 0. PREMISE (Q8) -- re-measured before any work, all four TRUE

| claim | measured on the pod today | verdict |
|---|---|---|
| `eval_gate/spa_test.py` absent | ABSENT | TRUE |
| `eval_gate/cpcv_engine.py` absent | ABSENT | TRUE |
| `eval_gate/deflated_metrics.py` absent | ABSENT | TRUE |
| `pm_trading/clv_beatrate_rollup.py` stale | present, md5 `3e5e9b90...`, `grep -c _row_exec_mode` = 0 | TRUE |
| `xgboost` not installed | `ModuleNotFoundError: No module named 'xgboost'` under `/usr/local/bin/python` (3.12.3) | TRUE |

## 1. ACCEPTANCE RULE (as applied)

    metric        = paper-profile python modules that import on the pod
                    / the 14 kind=="py" ProcSpecs of config/boot/paper.json
    before        = not measurable (no tool existed); the adjacent S21 denominator
                    was 15/20 harness modules, 5 named failures
    bar           = 14/14 modules import AND both boot guards report SKIP
    n             = 14 (CONSTRUCT, every profile service enumerated)
                    + 3 (CONSTRUCT) test cases
    eye check     = n/a (S-row); reproduction = re-run the exact command in 3.
    must not move = supervisor pid 19236, track daemon 4035, mlb capture 21622;
                    no harness threshold or gate value is touched by this row

RESULT: **PASS** -- 14/14 import, both guards SKIP, all three pids unchanged.

NON-TAUTOLOGY: the denominator is the profile's own service allowlist read from
disk, not a list chosen after seeing which modules import. No module was
excluded. The two modules that still fail (section 4) are OUTSIDE this
denominator and are reported as failures rather than dropped.

## 2. What was done on the pod (the safe subset)

**Packages.** `pip install --break-system-packages xgboost` under
`/usr/local/bin/python` -> **xgboost 3.4.1**. One package; nothing else installed.

**Modules deployed** -- `git archive HEAD <4 paths> | ssh ... 'tar -x -C
/workspace/nba-ai-system'`, all four long-landed in master. CRLF-normalised md5,
local `git show HEAD:$f` vs pod file: **4/4 identical**.

| file | md5 (local == pod) |
|---|---|
| scripts/platformkit/eval_gate/spa_test.py | d08aeb6f900c7454e73e575c7f38daf3 |
| scripts/platformkit/eval_gate/cpcv_engine.py | caa83f861e870c707419f803488f3603 |
| scripts/platformkit/eval_gate/deflated_metrics.py | a5ae7ba099c0a314febae00b6196e97a |
| scripts/platformkit/pm_trading/clv_beatrate_rollup.py | 4be31aef4ae57f8de75c06eef57eec44 |

`pod_bootstrap_check.py` itself was **NOT** deployed into the repo tree (B5 --
it is unverified at the time of running). It was run from
`/tmp/s47chk/x/y/z/pod_bootstrap_check.py` with `--repo /workspace/nba-ai-system`,
which is why the `--repo` option exists. Nothing under
`/workspace/nba-ai-system` gained a file from this lane except the four modules
above.

## 3. `pod_bootstrap_check.py --profile paper` on the pod

    cd /workspace/nba-ai-system && PYTHONPATH=/workspace/nba-ai-system \
      /usr/local/bin/python /tmp/s47chk/x/y/z/pod_bootstrap_check.py \
      --profile paper --python /usr/local/bin/python --repo /workspace/nba-ai-system

    PROFILE: paper (source=file, manifest=paper) -- 14 python services
    IMPORTS (/usr/local/bin/python): 14/14 OK
    PROC (self-excluded):
      -m supervisor    pid 19236  /usr/local/bin/python -u -m supervisor --profile paper
      run_pod_capture  pid 21620  bash -c cd /workspace/nba-ai-system && CV_CAPTURE_POD=1 ...
      run_pod_capture  pid 21622  python -c from ...mlb_book_capture import run_pod_capture ...
    HEARTBEATS: m2_inplay 8s, m12_pm_paper_tick 10s, m33_http_wedge_reaper 19s,
      m2_inplay_capture 21s, m1_paper 61s, m1_bankroll 80s, m17_kalshi_scan 1220s,
      m43_settle_sweep 1281s, m44_exec_evidence 1281s, m1_producer 1285s,
      m18_pm_close_capture 380s   (11 of the 14 declare a heartbeat probe)
    RESULT: OK -- all modules importable
    EXIT=0

The `ENV (required flags)` section printed MISSING for all five. That is the
**ssh login shell's own** environment, which is the environment a bootstrap
launch would inherit -- exactly what the check is for. Measured separately, the
flags are live where they matter: `/proc/19236/environ` carries
`CV_CAPTURE_POD=1` and `CV_MLB_BOOK_ARCHIVE_LIVE=1`, and supervisor child 19238
carries all five (`NBA_AI_SUPERVISED=1`, `CV_PROP_MAX=0`, `CV_WC_PROP_MAX=0`
injected from the profile's `global_env`). No flag was flipped on; the `.sh`
passes the two capture flags explicitly because `run_pod_capture` refuses to
start without them (S21 memo section 7).

## 4. The five S21 import failures -- 3 fixed, 2 deeper than diagnosed

Re-run on the pod under `/usr/local/bin/python` after the deploy + install:

| module | before (S21) | now |
|---|---|---|
| eval_gate/romano_wolf.py | no module spa_test | **OK** |
| eval_gate/student_gate.py | no module deflated_metrics | **OK** |
| pm_trading/clv_daily_readout.py | stale clv_beatrate_rollup | **OK** |
| eval_gate/stacker.py | no module cpcv_engine | still FAIL -- `cannot import name '_SETTLED_DENY' from ...eval_gate.walkforward` |
| ingame/run_gap_arms_real_corpus.py | no xgboost | still FAIL -- `cannot import name 'drop_unparsed' from ...mlb_state_features` |

**3/5.** Both remaining failures are the SAME defect class one layer deeper: the
pod copy of a sibling predates master. Measured:

| file | pod md5 | local md5 | symbol on pod | landed in master |
|---|---|---|---|---|
| eval_gate/walkforward.py | 3a927f6091741fe4d4a8ce7f84065004 | 9eff8f0db70677e7ecfa260af08173ac | `_SETTLED_DENY` grep = 0 | 112c995d7, 2026-09-02 |
| mlb_state_features.py | 22473745789f95b186dae75017f7c177 | cb89bb67cb02035ca7e533bb7c010a60 | `drop_unparsed` grep = 0 | 725a45aab, 2026-08-31 |

Neither is in this lane's authorised deploy set, so neither was shipped (B5).
They are filed as a new gap in section 7 -- and they are the direct evidence for
why the bootstrap ships the FULL tracked trees instead of a diff since a guessed
baseline: enumerating the missing files by hand found 4, and the true set was at
least 6.

## 5. Skip logic -- both boot guards fired

The `.sh` boots a process only when `/proc` shows none. Proved without booting
anything: the `proc_pids` function was extracted **verbatim** from
`scripts/platformkit/ops/pod_bootstrap.sh` (awk range `^proc_pids\(\) \{` ..
`^\}$`, md5 `5ec82130347530a60909d7a1edd1247b`) and run on the pod with the two
`if [ -n "$(proc_pids ...)" ]` guard expressions byte-identical to the file; only
the two launch bodies were replaced by `echo WOULD-LAUNCH`.

    probe pid $$ = 31191
    probe cmdline = sh /tmp/pod_bootstrap_guard_probe.sh run_pod_capture
    --- step 4 guard
      already running (pids: 19236 ) -- SKIP
    --- step 5 guard
      already running (pids: 21620 21622 ) -- SKIP

Both branches took SKIP, so a re-run boots nothing. The probe's own cmdline
CONTAINS the string `run_pod_capture` and its pid 31191 is absent from both
result sets -- self-exclusion (`$$` plus the `*pod_bootstrap*` marker) works, so
the scan can never match the checking command (runbook step 5).

## 6. Processes -- unchanged

`ALIVE 19236` supervisor (14 children), `ALIVE 4035` track daemon,
`ALIVE 21622` mlb book capture. Same pids as before the lane. No kill, no start,
no `data/` write, no ledger write, no git on the pod.

## 7. NOT VERIFIED

- The `.sh` has NEVER been executed end to end. Steps 1, 2, 4, 5 are unexercised:
  the pip lines, the caller's `git archive | tar -x`, and both launch branches
  were never run (the guards took SKIP, which is the point, but it means the
  launch commands are reviewed, not measured). Only the preflight (step 3), the
  guard expressions and the final state print (step 6) ran on the pod.
- `sh -n` was not run against `pod_bootstrap.sh`; the extracted `proc_pids` and
  the two guards are the only parts proven to execute.
- Importability is not correctness: no per-file test was run on the pod.
- The two stale siblings in section 4 were diagnosed, NOT repaired.
- The pod tree remains pinned to whatever each file's last deploy carried; only
  the four files in section 2 were refreshed to master `1b5dc3260`. A full-tree
  parity count local-vs-pod was not taken.
- The 30-pass S19 cadence measurement is still not started; `n_live_games` was
  not re-read this lane.
- The check reports the INVOKING shell's env; it cannot see a flag that exists
  only inside an already-running process (measured separately here, by hand).
- `--repo` is exercised on the pod only; the local test covers the default root.

## 8. New gaps (not rejections)

- NEW GAP: the pod copies of `scripts/platformkit/eval_gate/walkforward.py`
  (master 112c995d7, 2026-09-02) and `scripts/platformkit/mlb_state_features.py`
  (master 725a45aab, 2026-08-31) predate master, so `eval_gate/stacker.py` and
  `ingame/run_gap_arms_real_corpus.py` still cannot import on the pod even with
  the four S21 dependency files deployed and xgboost installed. Hand-enumerating
  the missing set found 4 of at least 6.
- NEW GAP: `pod_bootstrap.sh` steps 1/2/4/5 have no executed evidence. Arming
  them needs either a disposable container or a `--dry-run` mode on the `.sh`
  itself that prints each command instead of running it.
