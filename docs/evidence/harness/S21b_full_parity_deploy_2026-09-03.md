# S21b -- full-tree parity deploy of the harness-owned code (2026-09-03)

Lane P, S21 follow-up. Calibration language only. Nothing here is a performance,
profit or edge claim: this row measures FILE PARITY, IMPORTABILITY and the paper
preflight between local master and the pod, plus which pod child was bounced.

Why this row exists: S21 built its deploy set as a diff since a GUESSED baseline
(`609d9c98f`) and S47 then found the true missing set was larger (hand-enumeration
found 4, the real number was at least 6 -- `walkforward.py` and
`mlb_state_features.py` were still stale). This lane replaces the diff method with
FULL-TREE parity at master HEAD.

**Archive baseline sha: `4ff779286`** (local HEAD at the moment of `git archive`).
The working tree had unrelated uncommitted edits; `git archive HEAD` ships the
committed content only, so the pod is pinned to HEAD, not to the dirty tree.

Pod reached with `ssh -o BatchMode=yes -o ConnectTimeout=20 -F ~/.ssh/config.pod pod`
(port resolved from the alias, today 40193 -- it drifts; never hardcode). Every pid
below was read from `/proc` cmdlines, never `pgrep`/`ps`. No git ran on the pod.

## 1. ACCEPTANCE RULE (as applied)

    metric        = files whose CRLF-normalised md5 is identical local-vs-pod
                    / every tracked-at-HEAD file in the deploy set
    before        = S21 deployed 132 files from a guessed-baseline diff; S47
                    measured that method as incomplete (2 stale siblings survived)
    bar           = 100 pct md5 identical; pod_bootstrap_check --profile paper
                    14/14 with EXIT 0
    n             = 3,427 (CONSTRUCT, every tracked file in the deploy set)
                    + 2,118 (CONSTRUCT, every non-test module import-checked)
    eye check     = n/a (S-row); REPRODUCTION = the one-liner in section 8
    must not move = supervisor pid 19236, track daemon pid 4035 (+ keeper),
                    mlb capture pids 21620/21622, /workspace/track_daemon.pid,
                    keep_track_daemon.sh; no harness threshold or gate value is
                    touched by this row

RESULT: **PASS** -- 3,427/3,427 md5 identical, preflight 14/14 EXIT 0, all
must-not-move pids unchanged.

NON-TAUTOLOGY: the denominator is the full tracked-at-HEAD file list minus a
tracking-ownership exclusion written BEFORE any md5 was taken. No file was dropped
after seeing a mismatch. The 49 import failures are reported, not excluded.

## 2. Deploy set construction

Source of truth = the tarball of `git archive HEAD <5 pathspecs>`, i.e. tracked
files AT HEAD (not the index -- `git ls-files` disagreed with HEAD on two files,
`eval_gate/close_join_mlb.py` and `eval_gate/test_close_join_mlb.py`, which are in
HEAD; HEAD wins).

Pathspecs: `scripts/platformkit supervisor predict_service config/boot
requirements-predictor.txt requirements-live-v2.txt` -> 3,501 files.

Tracking-ownership exclusions (74 files, never shipped, never deleted on the pod):

| rule | files |
|---|---|
| `scripts/platformkit/tracking/**` | 42 |
| `scripts/platformkit/detection/**` | 5 |
| basename `track_daemon*` | 4 |
| basename `tracking_harness*` / `tracking_schema*` | 2 |
| basename `footage_*` (platformkit root) | 3 |
| sport probes at platformkit root (`tennis_*` 10, `football_*` 3, `basketball_*` 4) | 17 |
| `baseball_scale_probe*` | 1 (inside tracking/) |

**Deploy set = 3,427 files**: 3,059 `.py` (940 `test_*.py` deliberately INCLUDED so
pod-side per-file tests can run, 2,119 non-test) + 368 non-py (168 jpg, 125 json,
21 tsx, 13 md, 8 sh, 8 ts, 7 csv, 5 txt, 4 jsonl, 2 js, 2 html, 1 each
yaml/tsv/ps1/gitignore/css).

## 3. Parity result -- 3,427 / 3,427 = 100 pct

Pre-deploy pod state, measured before the tar:

- **322** of the 3,427 were ABSENT on the pod
- **80** more were present but stale
- total changed by this deploy: **402**; the other 3,025 were already identical

Post-deploy: **0 ABSENT**, and the sorted local md5 list diffed against the sorted
pod md5 list gives **0 lines of difference** -- 3,427/3,427 identical.

Local md5s were taken from the extracted `git archive HEAD` tree (so they are HEAD
content, immune to the dirty working tree), pod md5s from the live files, both
CRLF-normalised with `tr -d '\r'`.

The first `tar -x` printed one `Cannot change ownership to uid 197610` warning per
file (a Windows->Linux uid mapping artifact) and exited non-zero; it still wrote all
3,427 files. It was re-run with `--no-same-owner`, which exits 0. The reproducible
form in section 8 carries that flag.

## 4. Import check on the pod -- 2,069 / 2,118 OK

Denominator: every non-test `.py` in the deploy set (2,119) minus
`supervisor/__main__.py` (the live supervisor entry point -- excluded by design so
the check can never launch a second supervisor) = **2,118**.

Run with `/usr/local/bin/python` (the interpreter the supervisor uses), each module
in its own subprocess with a 60 s timeout, 8 at a time, driver script kept at
`/tmp/s21b/impcheck.py` and NOT written into the repo tree (B5).

**2,069 / 2,118 import OK. 49 FAIL**, and the 49 split cleanly:

**(a) 11 failures reproduce LOCALLY at HEAD with a byte-identical cause** -- they are
pre-existing defects in master, not deploy defects. Re-run of the same 49 modules on
this machine: 38/49 OK, and the 11 that fail locally are exactly these:

| module | cause (identical local and pod) |
|---|---|
| baseball_funnel_probe | cannot import name `MOUND_TO_PLATE_FEET` from domains.baseball.tracking.adapter |
| gate_coverage_report | No module named `gate_surface_catalog` |
| gate_coverage_report_compute | No module named `gate_surface_catalog` |
| intel_query.ask_families | circular import, `FAMILY_BEST` |
| intel_query.ask_fit | circular import, `FAMILY_FIT` |
| obs.drift_report_compute | No module named `drift_report_metrics` |
| overlay_render | cannot import name `_draw_frame` from demo_render |
| paper.window_strategy_spec | cannot import name `candidate_dirs` from market_lag_study |
| reforecast_refit | cannot import name `discover_store` from wp_diag_oos |
| retrain_loop | cannot import name `discover_store` from wp_diag_oos |
| seqmodel.nba_gru_winprob | No module named `nba_gru_dataset` |

**(b) 38 failures are pod-only, in three named classes, none of them deployable by
this lane:**

| n | cause | class |
|---|---|---|
| 20 | `No module named 'statsmodels'` | pod package gap (same class as S47's xgboost) |
| 7 | `No module named 'src.prediction.bet_grades'` | `src/**` is human-gated; not in this deploy set |
| 10 | `No module named 'scripts.platformkit.<pkg>._<helper>'` (`data_frontier._politeness` 7, `improve._market_metrics` 2, `autonomy._monitor_merge_helpers` 1) | UNTRACKABLE: `.gitignore:342` `scripts/**/_*`; all three files exist locally, all three are untracked (`git check-ignore -v` confirms), so no `git archive` method can ship them |
| 1 | `paper_track_record` -> `IndexError: 1` | pod-environment difference; imports OK locally and its md5 is identical on both sides |

The third row of (b) is the important one for the register: three helper modules the
pod needs can NEVER reach it through `git archive` while `.gitignore:342` stands.
Filed as a new gap, not fixed here.

## 5. Paper preflight -- 14/14, EXIT 0

    cd /workspace/nba-ai-system && PYTHONPATH=/workspace/nba-ai-system \
      /usr/local/bin/python scripts/platformkit/ops/pod_bootstrap_check.py \
      --profile paper --python /usr/local/bin/python

    PROFILE: paper (source=file, manifest=paper) -- 14 python services
    IMPORTS (/usr/local/bin/python): 14/14 OK
    PROC (self-excluded): supervisor 19236, run_pod_capture 21620 / 21622
    HEARTBEATS: 11 of the 14 declare a probe; freshest m33_http_wedge_reaper 1s,
      m2_inplay 2s; oldest m43_settle_sweep / m44_exec_evidence 2648s
    RESULT: OK -- all modules importable
    EXIT=0

`ENV (required flags)` again printed MISSING for all five -- that is the ssh login
shell's own environment, which is what a bootstrap launch would inherit, exactly as
S47 recorded. No flag was flipped on.

## 6. Processes -- one child bounced

Pre-deploy `/proc` scan: supervisor **19236** with 14 python children, plus track
daemon **4035**, mlb capture **21620/21622**, a tracking-lane
`tennis_sequential_plan` run (35712/35714, another session's, untouched) and
jupyter 556.

Which children needed a bounce: for each of the 14 profile children I parsed its
module file and every one-hop import that resolves to a file in the deploy set, then
intersected with the 402 files this deploy actually changed. **Exactly one hit:**

| child | pid | changed file |
|---|---|---|
| m1_paper (`pm_trading.auto_loop`) | 19449 | `scripts/platformkit/pm_trading/scoreboard.py` |

The other 13 (`bankroll_daemon`, `inplay_runner`, `inplay_capture_runner`,
`pm_paper_tick_runner`, `kalshi_scan_runner`, `pm_close_capture_runner`,
`ingame_clv_verdict_daemon`, `ingame_paper_settle`, `http_wedge_reaper_runner`,
`settle_sweep_daemon`, `exec_evidence_daemon`, `predict_service.app`,
`predict_service.scheduler`) had no changed module on any one-hop import and were
left alone. No file under `predict_service/`, `supervisor/` or `config/boot/` changed at
all.

**Bounced: 19449 -> 152399.** `kill 19449` only; the supervisor respawned it 3 s
later. Confirmed from `/proc`: new pid 152399, ppid **19236**, started
14:55:02 UTC (old pid started 14:10:37 UTC). Heartbeat
`data/cache/daemon_heartbeats/m1_paper.txt` mtime moved 1788360668 -> **1788360913**,
i.e. it refreshed ~14 s after the respawn, well inside 90 s.

Self-match guard: the probe's own `bash -c` wrapper (pid 152379) contains the string
`pm_trading.auto_loop` and was excluded by inspecting ppid -- 152379's parent is the
ssh shell, 152399's parent is the supervisor.

Unchanged after the lane: **19236** supervisor, **4035** track daemon, **21620 /
21622** mlb capture. Nothing else was killed, nothing was started, no `data/` write
and no ledger write was made by hand, and no git ran on the pod.

## 7. NOT VERIFIED

- Importability is not correctness. No per-file test was run on the pod; the 940
  `test_*.py` files were deployed so that becomes possible, but none were executed.
- The 49 import failures were DIAGNOSED, not repaired. In particular the three
  `_*` helper modules cannot be shipped by any `git archive` method while
  `.gitignore:342` stands.
- The import sweep's own side-effect footprint on `data/` could not be isolated:
  14 daemons write `data/cache/**` continuously, so there is no clean control. What
  IS measured: `data/cache/eval_gate/` does not exist on the pod, so no gate ledger
  file was present to be touched.
- `supervisor/__main__.py` was deliberately not import-checked (1 of 2,119).
- Only the ONE child whose one-hop import set changed was bounced. A deeper
  (two-hop or transitive) change could in principle leave a child running stale
  code; the one-hop rule is the rule this lane applied, and it is stated, not
  assumed to be complete.
- Master can move again after this lane; the pod is pinned to `4ff779286` for the
  whole deploy set and will drift with the next landing.
- The tracking-owned 74 files are deliberately stale on the pod. Nothing was
  deleted there -- only overwrites were performed.
- The S19 30-pass cadence measurement is still not started; `n_live_games` was not
  re-read this lane.

## 8. Reproducible one-liner

Rebuild the list, ship, and re-verify parity (run from the repo root):

```bash
# 1. list = tracked-at-HEAD minus tracking-owned
git archive HEAD scripts/platformkit supervisor predict_service config/boot \
    requirements-predictor.txt requirements-live-v2.txt | tar -x -C /tmp/s21b/tree
(cd /tmp/s21b/tree && find . -type f | sed 's|^\./||' | sort) | awk -F/ \
 '{n=split($0,p,"/");b=p[n];
   if($0~/^scripts\/platformkit\/(tracking|detection)\//)next;
   if(b~/^(track_daemon|tracking_harness|tracking_schema|footage_)/)next;
   if(n==3&&b~/^(baseball_scale_probe|football_|tennis_|basketball_)/)next;print}' \
 > /tmp/s21b/deploy.txt          # -> 3427

# 2. ship (overwrite only, never delete)
tar -c -C /tmp/s21b/tree -T /tmp/s21b/deploy.txt | \
  ssh -F ~/.ssh/config.pod pod 'tar -x --no-same-owner -C /workspace/nba-ai-system'

# 3. parity: local md5 vs pod md5, both CRLF-normalised -> must be 0 diff lines
(cd /tmp/s21b/tree && while IFS= read -r f; do \
   printf '%s  %s\n' "$(tr -d '\r' < "$f" | md5sum | cut -d' ' -f1)" "$f"; \
 done < /tmp/s21b/deploy.txt) | sort > /tmp/s21b/local.md5
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && while IFS= read -r f; \
   do printf "%s  %s\n" "$(tr -d "\r" < "$f" | md5sum | cut -d" " -f1)" "$f"; \
   done < /tmp/s21b/list.txt | sort' | diff /tmp/s21b/local.md5 -

# 4. preflight
ssh -F ~/.ssh/config.pod pod 'cd /workspace/nba-ai-system && \
  PYTHONPATH=/workspace/nba-ai-system /usr/local/bin/python \
  scripts/platformkit/ops/pod_bootstrap_check.py --profile paper \
  --python /usr/local/bin/python'
```

## 9. New gaps (not rejections)

- NEW GAP: `.gitignore:342` (`scripts/**/_*`) makes three helper modules the pod
  needs permanently undeployable -- `data_frontier/_politeness.py`,
  `improve/_market_metrics.py`, `autonomy/_monitor_merge_helpers.py`. 10 of the 49
  pod import failures are this one cause. Either a `.gitignore` negation line or a
  rename off the `_` prefix; both are decisions, not lane work.
- NEW GAP: `statsmodels` is not installed on the pod, so 20 modules (the
  `interaction_factory` replication family, `mlb_winprob_v5/v6/v7`,
  `predictive_validity`, `autoloop.false_discovery_job`, `omni.funnel`) cannot
  import there. Same class as S47's xgboost; `pod_bootstrap.sh` should install it.
- NEW GAP: 7 modules (the four `proof_*` runners and `proof_common.paper`) import
  `src.prediction.bet_grades`, and `src/**` is human-gated so no ops lane may
  deploy it. Either the proof runners stop depending on `src/`, or the bootstrap
  needs an explicit human-approved `src/` deploy step.
- NEW GAP: 11 modules fail to import in MASTER on this machine at HEAD with the
  same cause as on the pod (section 4a) -- e.g. `wp_diag_oos.discover_store` and
  `demo_render._draw_frame` are referenced but absent. These are stale references
  in master, invisible until a full-tree import sweep was run.
- NEW GAP: `git ls-files` and `git archive HEAD` disagreed on two files
  (`eval_gate/close_join_mlb.py`, `eval_gate/test_close_join_mlb.py` are in HEAD but
  not listed by `git ls-files`). Any deploy tool that builds its set from
  `git ls-files` will silently miss them.
