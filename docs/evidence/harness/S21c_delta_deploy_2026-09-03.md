# S21c -- delta parity deploy of the harness-owned code (2026-09-03)

Lane P, S21 follow-up to S21b. Calibration language only. Nothing here is a
performance, profit or edge claim: this row measures FILE PARITY, IMPORTABILITY
and the paper preflight between local master HEAD and the pod, plus which pod
child was bounced.

Why this row exists: S21b pinned the pod to `4ff779286` by shipping the FULL
tracked tree (3,427 files). Master has moved since. This lane ships only the
DELTA `4ff779286..HEAD` so the pod tracks master without a second full-tree
transfer, and without touching code two other live lanes are measuring.

Local HEAD at deploy: **`277bfa90b`** (HEAD moved to `75b63144d` while this lane
ran; see section 2) (`git archive HEAD` -- committed content
only; the working tree had unrelated uncommitted edits, which were NOT shipped).

Pod reached with `ssh -o BatchMode=yes -o ConnectTimeout=20 -F ~/.ssh/config.pod pod`
(port resolved from the alias, today 40193 -- it drifts; never hardcode). Every
pid below was read from `/proc` cmdlines with the reading shell self-excluded,
never `pgrep`/`ps`. No git ran on the pod. Overwrite only -- nothing deleted.

## 1. ACCEPTANCE RULE (as applied)

    metric        = files whose CRLF-normalised md5 is identical local-vs-pod
                    / every file in the deploy set
    before        = pod pinned at 4ff779286 (S21b) + the three S14/S60/S54
                    singles; 40 of the 50 delta files were absent or stale
    bar           = 100 pct md5 identical; pod_bootstrap_check --profile paper
                    --functional 14/14 imports + 6/6 probes with EXIT 0
    n             = 50 (CONSTRUCT, every file in the delta after the three
                    named exclusions) + 31 (CONSTRUCT, every non-test module
                    of the set, import-checked)
    eye check     = n/a (S-row); REPRODUCTION = the one-liner in section 7
    must not move = supervisor pid 19236, track daemon pid 4035, mlb capture
                    pids 21620/21622, foundry runner pid 165812 (S16 pod-hour
                    lane, live); no harness threshold or gate value is touched

RESULT: **PASS** -- 50/50 md5 identical, imports 31/31 OK, preflight 14/14 +
6/6 EXIT 0 both before and after the bounce, all must-not-move pids unchanged.

NON-TAUTOLOGY: the denominator is the delta list minus three ownership/liveness
exclusions written BEFORE any md5 was taken. No file was dropped after seeing a
mismatch. The 10 files already identical are counted in the denominator.

## 2. Deploy set construction

    git diff --name-only 4ff779286..HEAD -- scripts/platformkit supervisor \
      predict_service config/boot \
      docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md \
      docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md

-> **56** paths. Content shipped is `git archive HEAD` of the surviving list,
not the working tree.

| step | n | note |
|---|---|---|
| raw delta | 56 | |
| minus DELETED on master | -1 | STALE-ON-POD, section 4 |
| minus foundry (live measurement) | -5 | DEFERRED, section 3 |
| minus tracking-owned | -0 | the S21b rules matched nothing in this delta |
| minus S57-owned | -0 | not in HEAD at archive time; see the HEAD-MOVED note |
| **deploy set** | **50** | 43 `.py` (31 non-test + 12 `test_*.py`) + 5 json + 1 md + 1 sh |

`docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md` is not in the delta
(unchanged since the baseline); `FWER_FAMILIES_SPEC_2026-09-03.md` is, and shipped.

HEAD MOVED MID-LANE (measured, not assumed). The archive was taken at
`277bfa90b`; by the time this memo was committed HEAD was `75b63144d` and the
same delta command returned **61** paths, not 56. The 5 new paths were re-checked
against the exclusion rules already written and every one falls into an existing
exclusion class, so the deploy set is unchanged at 50:

| new path | class |
|---|---|
| `scripts/platformkit/eval_gate/gate_manifest.py` | DEFERRED (S57, now committed) |
| `scripts/platformkit/mcp_server/artifact_refresh.py` | DEFERRED (S57, now committed) |
| `scripts/platformkit/mcp_server/intelligence_producers.py` | DEFERRED (new S57 sibling; `artifact_refresh` imports it, so shipping one without the other is meaningless) |
| `scripts/platformkit/tracking/test_harness_additive_metrics.py` | tracking-owned (`tracking/**`) |
| `scripts/platformkit/tracking_harness.py` | tracking-owned (basename rule) |

Deferred total is therefore **8**, not 5: the 5 foundry files plus these 3 S57
files. The pod is at `277bfa90b` content for the 50 deployed files and behind
master for all 8 deferred ones.

## 3. DEFERRED -- 5 files, not shipped

The S16 pod-hour lane is measuring the foundry LIVE on this pod (runner pid
**165812**, ppid 165807, `-m scripts.platformkit.foundry_runner --db
data/cache/eval_gate/hypotheses.sqlite`). Overwriting its modules mid-run would
change the code under a running measurement, so all five are deferred to a
follow-up row after that lane lands:

| file | reason |
|---|---|
| `scripts/platformkit/foundry/promotion.py` | S16 pod-hour lane measuring live |
| `scripts/platformkit/foundry/results_db.py` | S16 pod-hour lane measuring live |
| `scripts/platformkit/foundry/seed_queue.py` | S16 pod-hour lane measuring live |
| `scripts/platformkit/foundry/tiers.py` | S16 pod-hour lane measuring live |
| `scripts/platformkit/foundry_runner.py` | S16 pod-hour lane measuring live |

`scripts/platformkit/eval_gate/gate_manifest.py` and
`scripts/platformkit/mcp_server/artifact_refresh.py` are also deferred (the S57
lane owns them). MEASURED: neither appeared in the delta at archive time
(`277bfa90b`) -- both were still uncommitted working-tree edits -- so the deferral
cost 0 files at that moment. S57 committed during this lane and all three S57
files (those two plus the new `mcp_server/intelligence_producers.py`) are in the
delta at `75b63144d` and remain DEFERRED here, unshipped.

## 4. STALE-ON-POD -- 1 file, deliberately not deleted

`scripts/platformkit/baseball_funnel_probe.py` was DELETED from master by S61
(retired probe). This lane overwrites only and deletes nothing on the pod, so
the file survives there:

    -rw-rw-rw- 1 root root 8637 Sep  2 14:41 \
      /workspace/nba-ai-system/scripts/platformkit/baseball_funnel_probe.py

It is orphaned, not live: no supervisor child imports it (section 6). A separate
row may remove it; this one does not.

## 5. Parity result -- 50 / 50 = 100 pct

Pre-deploy pod state, measured BEFORE the tar: **14 ABSENT**, **26 stale**,
**10 already identical** -> 40 files changed by this deploy.

Post-deploy: **0 ABSENT**, and the sorted local md5 list diffed against the
sorted pod md5 list gives **0 lines of difference**. `tar -x --no-same-owner`
exited 0.

Local md5s were taken from the extracted `git archive HEAD` tree (HEAD content,
immune to the dirty working tree), pod md5s from the live files, both
CRLF-normalised with `tr -d '\r'`.

| file | md5 (CRLF-normalised, first 12) | pre-deploy state |
|---|---|---|
| `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md` | 6ebb01c419a0 | IDENTICAL |
| `predict_service/test_app_ready_probe.py` | 308bcbe1cbaa | UPDATED |
| `scripts/platformkit/analytics_showcase/mechanism_close_effect.py` | 886f182656ae | NEW |
| `scripts/platformkit/analytics_showcase/mechanism_foundry.py` | 194fa7ec48a2 | UPDATED |
| `scripts/platformkit/analytics_showcase/mechanism_wiring.py` | 1c32cc10ca3d | UPDATED |
| `scripts/platformkit/analytics_showcase/mechanism_wiring_soccer.py` | ba7569a4f515 | NEW |
| `scripts/platformkit/analytics_showcase/mechanism_wiring_tennis.py` | 06aaa63e272e | NEW |
| `scripts/platformkit/analytics_showcase/out/mechanism_exposure.json` | a51a6683f804 | UPDATED |
| `scripts/platformkit/analytics_showcase/out/mechanism_wiring_prereg_soccer.json` | 7c9920754b65 | NEW |
| `scripts/platformkit/analytics_showcase/out/mechanism_wiring_prereg_tennis.json` | 77a6ef441395 | NEW |
| `scripts/platformkit/analytics_showcase/out/mechanism_wiring_soccer.json` | 831929a0fd40 | NEW |
| `scripts/platformkit/analytics_showcase/out/mechanism_wiring_tennis.json` | 83bb1082c66f | NEW |
| `scripts/platformkit/analytics_showcase/test_mechanism_close_effect.py` | 09f03eb7224d | NEW |
| `scripts/platformkit/autonomy/_monitor_merge_helpers.py` | f11204f293d7 | IDENTICAL |
| `scripts/platformkit/combo/corpus_cache.py` | 9a9e8fe2a7e5 | IDENTICAL |
| `scripts/platformkit/combo/fwer_budget.py` | 8eaba5b19832 | IDENTICAL |
| `scripts/platformkit/combo/test_corpus_cache_soccer_enrich.py` | 58d3a64f53e6 | NEW |
| `scripts/platformkit/data_frontier/_politeness.py` | ae783d1616b3 | IDENTICAL |
| `scripts/platformkit/eval_gate/calibration_report.py` | 5e42d7ed0e31 | UPDATED |
| `scripts/platformkit/eval_gate/close_join.py` | 1649b5fed051 | IDENTICAL |
| `scripts/platformkit/eval_gate/close_join_mlb.py` | 627fac1b67bd | IDENTICAL |
| `scripts/platformkit/eval_gate/family_bars.py` | 9a3fe9282718 | UPDATED |
| `scripts/platformkit/eval_gate/gen_golden.py` | de4b478bb20f | UPDATED |
| `scripts/platformkit/eval_gate/golden_loader.py` | f58329d626d2 | UPDATED |
| `scripts/platformkit/eval_gate/ingame_calibration_report.py` | 359205183746 | NEW |
| `scripts/platformkit/eval_gate/run_gate.py` | a44ba855f2d9 | UPDATED |
| `scripts/platformkit/eval_gate/s58_e2_slice_trial.py` | 99c6fa633338 | NEW |
| `scripts/platformkit/eval_gate/test_behind_is_not_blocked.py` | 3c7e3079a3e0 | UPDATED |
| `scripts/platformkit/eval_gate/test_calibration_report.py` | b375b16631b4 | UPDATED |
| `scripts/platformkit/eval_gate/test_close_join_mlb.py` | f954de4492ed | IDENTICAL |
| `scripts/platformkit/eval_gate/test_close_join_tennis.py` | 34b1ab78025e | UPDATED |
| `scripts/platformkit/eval_gate/test_family_bars.py` | fe3fee47da44 | NEW |
| `scripts/platformkit/eval_gate/test_gate.py` | 2d1fc5ded974 | UPDATED |
| `scripts/platformkit/eval_gate/test_ingame_calibration_report.py` | 721e72d319b4 | NEW |
| `scripts/platformkit/eval_gate/test_ledger_schema_s13.py` | 57d85c720945 | UPDATED |
| `scripts/platformkit/gate_coverage_report.py` | a66f72bea7ca | UPDATED |
| `scripts/platformkit/gate_coverage_report_compute.py` | 3aaa2c881a2b | UPDATED |
| `scripts/platformkit/improve/_market_metrics.py` | 7c517f808592 | IDENTICAL |
| `scripts/platformkit/intel_query/ask_families.py` | 32e056b65fa4 | UPDATED |
| `scripts/platformkit/intel_query/ask_fit.py` | 538fe46bdd72 | UPDATED |
| `scripts/platformkit/obs/drift_report_compute.py` | 1ed07f8d470e | UPDATED |
| `scripts/platformkit/ops/pod_bootstrap.sh` | 8d1aff44a424 | UPDATED |
| `scripts/platformkit/ops/pod_bootstrap_check.py` | e9b245f3c2c3 | IDENTICAL |
| `scripts/platformkit/overlay_render.py` | 642e4d6b25dd | UPDATED |
| `scripts/platformkit/paper/window_strategy_spec.py` | 627a23204d33 | UPDATED |
| `scripts/platformkit/reforecast_refit.py` | 7c0e91657868 | UPDATED |
| `scripts/platformkit/seqmodel/__init__.py` | a301295c78e7 | NEW |
| `scripts/platformkit/seqmodel/nba_gru_winprob.py` | 971650e68109 | UPDATED |
| `supervisor/health.py` | daa6f51f3aa0 | UPDATED |
| `supervisor/test_health.py` | ba047ce17f73 | UPDATED |

## 6. Import check on the pod -- 31 / 31 OK

Denominator: every non-test `.py` in the deploy set (43 `.py` minus 12
`test_*.py`) = **31**. No module was excluded. Run with `/usr/local/bin/python`
(the interpreter the supervisor uses), each module in its own subprocess with a
90 s timeout, 6 at a time, driver kept at `/tmp/s21c_impcheck.py` and NOT
written into the repo tree (B5).

    IMPORTS 31/31 OK

**0 FAIL.** Notable: the three `_`-prefixed helpers S21b reported as permanently
undeployable under `.gitignore:342` are now TRACKED and shipped, and all three
import on the pod --
`scripts.platformkit.autonomy._monitor_merge_helpers`,
`scripts.platformkit.data_frontier._politeness`,
`scripts.platformkit.improve._market_metrics`. S21b's first NEW GAP is therefore
CLOSED by this deploy, measured, not assumed. The S21b master-level import
failures in this set also now import on the pod: `gate_coverage_report`,
`gate_coverage_report_compute`, `intel_query.ask_families`, `intel_query.ask_fit`,
`obs.drift_report_compute`, `overlay_render`, `paper.window_strategy_spec`,
`reforecast_refit`, `seqmodel.nba_gru_winprob` -- the S61 repair landed.

## 7. Paper preflight -- 14/14 imports, 6/6 functional, EXIT 0

    cd /workspace/nba-ai-system && PYTHONPATH=/workspace/nba-ai-system \
      /usr/local/bin/python scripts/platformkit/ops/pod_bootstrap_check.py \
      --profile paper --functional --python /usr/local/bin/python

    PROFILE: paper (source=file, manifest=paper) -- 14 python services
    IMPORTS (/usr/local/bin/python): 14/14 OK
    FUNCTIONAL (/usr/local/bin/python, 60s each):
      OK   parquet_mlb_games    rows=27983 cols=10
      OK   mlb_predictor_init   n_games=27983 teams=34 r_home=4.198
      OK   produce_mlb_dry      status=ok predictions=46 markets=152
      OK   espn_live_state_mlb  live_games=1
      OK   boot_packages        fastapi=0.141.1 sklearn=1.8.0 pyarrow=25.0.1
                                statsmodels=0.15.0 xgboost=3.4.1
      OK   supervisor_lock_env  pid=19236 lock_exists=True
                                flags=CV_CAPTURE_POD,CV_MLB_BOOK_ARCHIVE_LIVE
    RESULT: OK -- imports clean, no probe failed
    EXIT=0

Run twice: once after the tar (pre-bounce) and once after the bounce. Identical
both times. `boot_packages` shows `statsmodels=0.15.0` -- S21b's second NEW GAP
(statsmodels absent on the pod) is CLOSED, measured here.

`ENV (required flags)` again printed MISSING for all five. That is the ssh login
shell's own environment, exactly as S21b and S47 recorded; the running supervisor
holds `CV_CAPTURE_POD,CV_MLB_BOOK_ARCHIVE_LIVE` (see `supervisor_lock_env`). No
flag was flipped on by this lane.

## 8. Processes -- one child bounced

For each of the 14 profile children the module file and every one-hop import
that resolves to a file in the deploy set were parsed with `ast` and intersected
with the 50-file set. **Exactly one hit:**

| child | module | pid | file in the deploy set |
|---|---|---|---|
| m1_api_paper | `predict_service.app` | 24212 | `supervisor/health.py` (was stale: pod `2ee6ded3d11b` vs HEAD `daa6f51f3aa0`) |

The other 13 had no deploy-set file on their module or any one-hop import and
were left alone. No file under `predict_service/` (other than a test),
`supervisor/` (other than `health.py` and its test) or `config/boot/` changed.

**Bounced: 24212 -> 203573.** `kill 24212` only; the supervisor respawned it 7 s
later. Confirmed from `/proc`: new pid 203573, ppid **19236**, start ctime
1788367484 vs kill at 1788367477 (old pid ctime 1788358710). Readiness confirmed
live on the new process: `curl http://127.0.0.1:8001/ready` -> **200** (ports
8000 and 8080 return nothing; 8001 is the served port).

`m1_api_paper` declares no heartbeat probe in the manifest (11 of 14 do), so the
`/ready` 200 plus the fresh ppid-19236 process IS the respawn evidence for this
child; the neighbouring `m1_producer` heartbeat
`data/frontend/predict_service/_heartbeat.json` was re-read and is live.

Unchanged after the lane, each re-read from `/proc` at the end: **19236**
supervisor, **4035** track daemon, **21620 / 21622** mlb capture, **165812**
foundry runner (S16 lane). Nothing else was killed, nothing was started, no
`data/` write and no ledger write was made by hand, and no git ran on the pod.

## 9. NOT VERIFIED

- Importability is not correctness. No per-file test was run on the pod; the 12
  `test_*.py` in this set were deployed so that becomes possible, none executed.
- The 5 DEFERRED foundry files leave the pod running foundry code at the
  `4ff779286` baseline while master has moved. That is deliberate (a live
  measurement is in flight) but it means the pod is NOT at master for
  `scripts/platformkit/foundry*` until a follow-up row ships them.
- `gate_manifest.py` / `artifact_refresh.py` were deferred by instruction; the
  measured fact is only that they are absent from THIS delta. Their state on the
  pod versus S57's in-progress edit was not measured.
- `baseball_funnel_probe.py` is knowingly stale on the pod. Its absence from any
  supervisor child's one-hop import set was checked; deeper reachability was not.
- Only the ONE child whose one-hop import set changed was bounced. A two-hop or
  transitive change could leave a child running stale code; one-hop is the rule
  applied, stated rather than assumed complete.
- The import sweep's side-effect footprint on `data/` could not be isolated: 14
  daemons write `data/cache/**` continuously, so there is no clean control.
- Master can move again after this lane; the pod is pinned to `277bfa90b` for
  the 50 deployed files only.
- The tracking-owned exclusion rules were applied and matched nothing in this
  delta -- that is a measured 0, not a claim that tracking code is in sync.

## 10. Reproducible one-liner

    # 1. list = delta minus deleted, minus foundry, minus S57-owned
    git diff --name-status 4ff779286..HEAD -- scripts/platformkit supervisor \
        predict_service config/boot \
        docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md \
        docs/evidence/harness/FACTORY_TIERS_SPEC_2026-09-03.md > /tmp/s21c/raw.txt
    awk '$1=="D"{print $2}' /tmp/s21c/raw.txt > /tmp/s21c/stale.txt        # -> 1
    awk '$1!="D"{print $2}' /tmp/s21c/raw.txt \
      | grep -vE '^scripts/platformkit/(foundry/|foundry_runner[.]py|eval_gate/gate_manifest[.]py|mcp_server/artifact_refresh[.]py)' \
      | grep -vE '^scripts/platformkit/(tracking|detection)/' \
      | grep -vE '/(track_daemon|tracking_harness|tracking_schema|footage_)[^/]*$' \
      | grep -vE '^scripts/platformkit/(baseball_scale_probe|football_|tennis_|basketball_)[^/]*$' \
      | sort > /tmp/s21c/deploy.txt                                        # -> 50

    # 2. ship HEAD content (overwrite only, never delete)
    git archive HEAD $(tr "\n" " " < /tmp/s21c/deploy.txt) \
      | tar -x --no-same-owner -C /tmp/s21c/tree
    tar -c -C /tmp/s21c/tree -T /tmp/s21c/deploy.txt \
      | ssh -F ~/.ssh/config.pod pod "tar -x --no-same-owner -C /workspace/nba-ai-system"

    # 3. parity: local md5 vs pod md5, both CRLF-normalised -> 0 diff lines
    (cd /tmp/s21c/tree && while IFS= read -r f; do \
       printf "%s  %s\n" "$(tr -d "\r" < "$f" | md5sum | cut -d" " -f1)" "$f"; \
     done < /tmp/s21c/deploy.txt) | sort > /tmp/s21c/local.md5
    ssh -F ~/.ssh/config.pod pod "cd /workspace/nba-ai-system && while IFS= read -r f; \
       do printf '%s  %s\n' \"\$(tr -d '\r' < \"\$f\" | md5sum | cut -d' ' -f1)\" \"\$f\"; \
       done < /tmp/s21c_list.txt | sort" | diff /tmp/s21c/local.md5 -

    # 4. preflight
    ssh -F ~/.ssh/config.pod pod "cd /workspace/nba-ai-system && \
      PYTHONPATH=/workspace/nba-ai-system /usr/local/bin/python \
      scripts/platformkit/ops/pod_bootstrap_check.py --profile paper --functional \
      --python /usr/local/bin/python"

## 11. New gaps (not rejections)

- NEW GAP: 8 files are pinned behind master on the pod -- 5 foundry (a live S16
  measurement holds them) and 3 S57 files that landed while this lane ran. A
  follow-up delta row must ship them, or the pod silently runs old code.
- NEW GAP: master moves faster than a delta deploy completes. This lane's delta
  grew 56 -> 61 between `git archive` and commit. A deploy row can never be
  "at master"; it can only state the sha it shipped. A deploy that recorded its
  archive sha into a pod-side file would make the pod's true baseline readable
  without re-running a full parity sweep.
- NEW GAP: this lane deletes nothing, so every file retired from master
  accumulates on the pod (1 so far: `baseball_funnel_probe.py`). There is no
  mechanism that retires a pod file; the orphan set only grows.
- NEW GAP: `m1_api_paper` declares no heartbeat probe, so a bounce of that child
  can only be confirmed by an out-of-band HTTP probe. 3 of the 14 paper services
  have no heartbeat; a manifest-declared probe for each would make the bounce
  check uniform.
