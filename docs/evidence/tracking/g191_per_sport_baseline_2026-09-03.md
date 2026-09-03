# G191 per-sport route baseline

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), self-checked against
section B before reporting. Measurement only: no source, threshold, gate,
coordinate contract, verdict, daemon, keeper, or corpus was changed. `src/` was
executed only through the existing `scripts/run_clip.py` route and was not edited.

## Result

This is the mandated three-run distributional baseline for the unchanged bounded
route, not a quality score or a pass/fail gate. G189 established that this route
is non-deterministic, so no summary below treats one run as a property of a
sport. The eligible denominator is always named **distinct attempted gameplay
frames**: unique `frame` values directly recounted from that run's
`ball_tracking.csv`; it is never the `--frames 1200` argument.

The 18 G191 commands were issued in one serial pod session, each with a newly
created `mktemp -d` `--data-dir` under `/tmp`. No G191 command overlapped another.
An independently owned G193 WNBA route appeared later and overlapped football and
MLB; that external overlap is recorded under NOT VERIFIED and limits interpretation
of their pod-occupancy wall times.

## Premise recheck and source selection

Before the first run, a read-only `stat` plus `ffprobe` scan of all ten supplied
pod files matched every supplied byte size, decoded resolution, and metadata frame
count. The six selected sources are named in full below, as required by A9.

| Sport | Full pod source path | Bytes | Resolution | Metadata frames | Selection note |
|---|---|---:|---|---:|---|
| wnba | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 | Required 1080p WNBA source. |
| ncaa_basketball | `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 3,580,059,573 | 1920x1080 | 205,444 | Required 1080p NCAA source. |
| soccer | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_dnR5C6WLJI4.mp4` | 3,373,680,742 | 1920x1080 | 250,200 | Required 1080p soccer source. |
| baseball | `/workspace/nba-ai-system/data/footage_corpus/baseball__kbo_06.mp4` | 642,203,161 | 1920x1080 | 53,196 | G191 specifies `kbo_06`; it is a 1080p baseball source, avoiding the lower-resolution NPB alternatives. |
| football | `/workspace/nba-ai-system/data/footage_corpus/football__football_Z8Ezd95NnjM.mp4` | 2,493,550,705 | 1280x720 | 288,230 | Listed football source; no 1080p football source is in this corpus. |
| mlb | `/workspace/nba-ai-system/data/footage_corpus/mlb__mlb_nLoG6gvC-Nk.mp4` | 1,066,801,340 | 1280x720 | 220,624 | Listed MLB source. |

Non-run confound retained for later comparisons:
`/workspace/nba-ai-system/data/footage_corpus/baseball__npb_02.mp4` is
895,692,406 bytes, **640x360**, and 411,191 metadata frames. It was not run;
its resolution is not comparable with `kbo_06` without an explicit design choice.

## Three-run distributions

Every min/median/max below is over exactly the three listed records for that
sport. `image_px 3/3` is a distribution of the declared field across all three
runs, not a calibration or quality claim. `absent 3/3` means preflight exited
before `tracking_data.csv` existed, so no `coordinate_space` was declared.

Pod-occupancy wall time is reconstructed independently as the fresh directory
birth timestamp (immediately before the run-start snapshot and command) to the
final `run.log` write timestamp. For completed routes it includes preflight plus
the runner-reported total time; for preflight exits it is the only available wall
time. It is reported to milliseconds only because both filesystem timestamps had
that precision, not as a sustained-performance claim.

| Sport | Player rows, min/median/max | Distinct player-row frames, min/median/max | **Eligible denominator: distinct attempted gameplay frames**, min/median/max | Declared `coordinate_space` over 3 runs | Pod-occupancy wall s, min/median/max |
|---|---:|---:|---:|---|---:|
| wnba | 1,240 / 1,284 / 1,400 | 400 / 400 / 400 | 400 / 400 / 400 | `image_px` 3/3 | 121.939 / 122.182 / 128.384 |
| ncaa_basketball | 88 / 555 / 787 | 59 / 148 / 343 | 400 / 400 / 400 | `image_px` 3/3 | 134.551 / 141.463 / 146.760 |
| soccer | 173 / 185 / 1,010 | 139 / 147 / 336 | 400 / 400 / 400 | `image_px` 3/3 | 160.395 / 162.943 / 178.454 |
| baseball | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | absent 3/3 | 8.606 / 8.839 / 8.925 |
| football | 543 / 633 / 656 | 226 / 227 / 254 | 280 / 280 / 280 | `image_px` 3/3 | 104.316 / 132.712 / 141.391 |
| mlb | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | absent 3/3 | 7.500 / 7.797 / 7.883 |

Total observed G191 pod occupancy is **1,725.040 s** (28 m 45.040 s), the sum
of all 18 reconstructed per-run walls. It is a total for this exact measurement,
not a throughput or utilization estimate.

## Per-run records

These are B13 records, retained so the distribution above can be recomputed.
They are individual observations, not sport-level claims. All success counts and
the eligible denominator were independently recounted from the retained CSVs.
The source path for every run is the corresponding full source path in the source
table; each `data_dir` was newly allocated by `mktemp -d`.

| Sport / run | Pod data directory | Start UTC (directory birth) | End UTC (final `run.log` write) | Exit | GPU util, memory at run start | Player rows | Distinct player-row frames | **Eligible denominator: distinct attempted gameplay frames** | `coordinate_space` | Runner total s / pod wall s |
|---|---|---|---|---:|---|---:|---:|---:|---|---:|
| wnba 1 | `/tmp/cx_g191_per_sport_baseline_20260903_wnba_run1_8C9VqZ` | 21:06:52.409Z | 21:08:54.348Z | 0 | NOT ARCHIVED | 1,400 | 400 | 400 | `image_px` | 114.1 / 121.939 |
| wnba 2 | `/tmp/cx_g191_per_sport_baseline_20260903_wnba_run2_761mne` | 21:08:56.168Z | 21:11:04.552Z | 0 | NOT ARCHIVED | 1,284 | 400 | 400 | `image_px` | 120.1 / 128.384 |
| wnba 3 | `/tmp/cx_g191_per_sport_baseline_20260903_wnba_run3_iFWSPX` | 21:11:06.456Z | 21:13:08.638Z | 0 | NOT ARCHIVED | 1,240 | 400 | 400 | `image_px` | 114.1 / 122.182 |
| ncaa_basketball 1 | `/tmp/cx_g191_per_sport_baseline_20260903_ncaa_basketball_run1_ir3lb5` | 21:13:10.292Z | 21:15:37.052Z | 0 | NOT ARCHIVED | 787 | 343 | 400 | `image_px` | 138.9 / 146.760 |
| ncaa_basketball 2 | `/tmp/cx_g191_per_sport_baseline_20260903_ncaa_basketball_run2_pKCfVE` | 21:15:38.727Z | 21:17:53.278Z | 0 | NOT ARCHIVED | 88 | 59 | 400 | `image_px` | 126.7 / 134.551 |
| ncaa_basketball 3 | `/tmp/cx_g191_per_sport_baseline_20260903_ncaa_basketball_run3_HTpDwA` | 21:17:54.979Z | 21:20:16.442Z | 0 | NOT ARCHIVED | 555 | 148 | 400 | `image_px` | 133.0 / 141.463 |
| soccer 1 | `/tmp/cx_g191_per_sport_baseline_20260903_soccer_run1_cGXqwa` | 21:20:18.422Z | 21:23:16.876Z | 0 | NOT ARCHIVED | 1,010 | 336 | 400 | `image_px` | 170.2 / 178.454 |
| soccer 2 | `/tmp/cx_g191_per_sport_baseline_20260903_soccer_run2_E7eH1o` | 21:23:18.775Z | 21:25:59.170Z | 0 | NOT ARCHIVED | 173 | 139 | 400 | `image_px` | 151.8 / 160.395 |
| soccer 3 | `/tmp/cx_g191_per_sport_baseline_20260903_soccer_run3_1SFcZT` | 21:26:02.245Z | 21:28:45.188Z | 0 | NOT ARCHIVED | 185 | 147 | 400 | `image_px` | 154.3 / 162.943 |
| baseball 1 | `/tmp/cx_g191_per_sport_baseline_20260903_baseball_run1_3sU3ic` | 21:28:47.585Z | 21:28:56.510Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 8.925 |
| baseball 2 | `/tmp/cx_g191_per_sport_baseline_20260903_baseball_run2_Wqk9aQ` | 21:28:58.261Z | 21:29:07.100Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 8.839 |
| baseball 3 | `/tmp/cx_g191_per_sport_baseline_20260903_baseball_run3_gPdiZH` | 21:29:08.837Z | 21:29:17.443Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 8.606 |
| football 1 | `/tmp/cx_g191_per_sport_baseline_20260903_football_run1_V3AxuM` | 21:29:19.215Z | 21:31:40.606Z | 0 | NOT ARCHIVED | 656 | 254 | 280 | `image_px` | 133.8 / 141.391 |
| football 2 | `/tmp/cx_g191_per_sport_baseline_20260903_football_run2_xAFego` | 21:31:43.856Z | 21:33:28.173Z | 0 | NOT ARCHIVED | 543 | 226 | 280 | `image_px` | 92.3 / 104.316 |
| football 3 | `/tmp/cx_g191_per_sport_baseline_20260903_football_run3_ckkh2K` | 21:33:31.341Z | 21:35:44.053Z | 0 | NOT ARCHIVED | 633 | 227 | 280 | `image_px` | 121.0 / 132.712 |
| mlb 1 | `/tmp/cx_g191_per_sport_baseline_20260903_mlb_run1_UD9xYr` | 21:35:45.846Z | 21:35:53.729Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 7.883 |
| mlb 2 | `/tmp/cx_g191_per_sport_baseline_20260903_mlb_run2_1HABA7` | 21:35:55.363Z | 21:36:03.160Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 7.797 |
| mlb 3 | `/tmp/cx_g191_per_sport_baseline_20260903_mlb_run3_riRk09` | 21:36:04.826Z | 21:36:12.326Z | 4 | NOT ARCHIVED | 0 | 0 | 0 | absent | absent / 7.500 |

The wrapper queried `nvidia-smi --query-gpu=utilization.gpu,memory.used` at each
run start, but its stdout was not retained when the long remote transport detached.
The six groups of start snapshots are therefore explicitly **NOT ARCHIVED**. A
current GPU query cannot recreate historical run-start state, so none is
substituted here.

### Failure console records: baseball and MLB

All three runs of each sport exited through the route's preflight branch, before
the tracking or ball CSVs were created. There is no Python traceback because the
existing route deliberately prints the following console record and calls its
documented exit 4 branch:

```text
[preflight] Sampling 10 frames for person detection...

[PREFLIGHT FAIL] Median person count = 1 (threshold: 3)
Video appears to be non-broadcast footage (app UI, overlays, no court).
This is a YOLO detection check -- if the video is a real broadcast,
re-download from a different source and retry.
```

The console was identical in each of the three baseball and three MLB `run.log`
records. It is reported as the existing route's reason for this result, not as a
judgment about the footage or a reason to retry.

## What each sport currently produces, and the first scorable blocker

- **wnba:** Across three runs it emits an `image_px` player table with a 400 / 400 / 400 eligible denominator; the first blocker is that declared image-pixel coordinates are not a scorable coordinate contract.
- **ncaa_basketball:** Across three runs it emits an `image_px` player table with a 400 / 400 / 400 eligible denominator; the first blocker is likewise the declared image-pixel coordinate space, before any scoring assessment.
- **soccer:** Across three runs it emits `image_px` preservation rows with a 400 / 400 / 400 eligible denominator; G185 establishes that configuration selects the uncalibrated preservation route, so that route selection is the first blocker, not a quality conclusion.
- **baseball:** Across all three runs it produces no rows and no eligible denominator because preflight exits 4 at median person count 1; that preflight exit is the first blocker. G185's baseball preservation-route finding is not reached by these runs.
- **football:** Across three runs it emits `image_px` preservation rows with a 280 / 280 / 280 eligible denominator; G185 establishes that configuration selects that uncalibrated route, the first blocker, rather than establishing any quality result.
- **mlb:** Across all three runs it produces no rows and no eligible denominator because preflight exits 4 at median person count 1; that preflight exit is the first blocker. The baseball-family route is not reached by these runs.

## VERIFIER_CONTRACT self-check: section B

- **B1 CIRCULAR METRIC:** Clear. Every data row in each existing
  `tracking_data.csv` was counted and every parseable `frame` in each existing
  `ball_tracking.csv` was used for the named eligible denominator. Preflight exits
  are retained as three full records per affected sport.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No field, schema, status, or reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. No gate, queue, or quarantine behavior changed;
  the existing route's preflight exits are reported rather than suppressed.
- **B4 RE-CLAIM LOOP:** Clear. No ownership, daemon, keeper, or claim behavior changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No repository file was copied or deployed
  to the pod. Only the existing checkout was executed into fresh `/tmp` data dirs.
- **B6 ORPHANS:** Clear. No module, import, command, test, or path was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear for this counts-and-routes baseline. The fixed
  `--frames 1200` bounded command and all six source choices were prescribed; no
  render or head-slice quality claim is made.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model, residual, or independent
  performance result is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. The denominator is directly recounted unique
  attempted-gameplay `frame` values from the ball table, not a recycled track ID,
  player-row count, or the command cap. Preflight exits explicitly have no ball table.
- **B10 MOVED BAR:** Clear. No threshold, default, coordinate contract, verdict,
  crop, or other bar was changed.

## NOT VERIFIED

- The six required run-start GPU utilization and memory snapshots: queried by the
  wrapper but not archived by the detached remote transport. They cannot be
  reconstructed after the fact.
- Uncontended pod occupancy for football and MLB. A separately owned G193 WNBA
  `run_clip.py` process was observed alongside football runs 1-3 and MLB runs 1-3.
  G191 itself remained serial, and no other workload was modified.
- Whether `image_px` rows cover players, preserve identities, have usable geometry,
  or are otherwise accurate. This row measures counts and declared routes only.
- Why the route's preflight median was 1 on the selected baseball and MLB clips;
  no detector setting, source, or threshold was changed to investigate it.
- Whether the observed distributions generalize beyond these six specified files,
  18 bounded runs, current pod state, and this existing route.
- Any calibration, coordinate conversion, or scorable result. In particular, G185's
  uncalibrated-preservation finding is used only for soccer and football route
  selection, not as a quality claim.

## Evidence-path check (A7)

At commit time, this memo and the cited contract exist in this worktree:
`docs/evidence/tracking/g191_per_sport_baseline_2026-09-03.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Orchestrator verification and analysis at landing

**A2, recounted independently from the surviving pod CSVs rather than the lane's
table:** ncaa run1 787 rows / 343 frames / 400 ball; run2 88 / 59 / 400; run3
555 / 148 / 400; wnba run1 1,400 / 400 / 400. All reproduce exactly.

### The non-determinism is SPORT-DEPENDENT and far worse than I have been quoting

| sport | rows min -> max over 3 identical runs | spread |
|---|---|---:|
| wnba | 1,240 -> 1,400 | **1.13x** |
| football | 543 -> 656 | 1.21x |
| soccer | 173 -> 1,010 | **5.8x** |
| ncaa_basketball | 88 -> 787 | **8.9x** |

**I have been quoting "9 pct" as the route's instability since G189. That is a
WNBA-specific figure and it does not generalise.** On ncaa_basketball the same
command on the same file returns anywhere from 88 to 787 player rows, and distinct
player-row frames swing 59 to 343 against a constant eligible denominator of 400.
Corrected here and to be carried forward: quote the sport, or quote the range.

This makes G193's question (does tuner-off fix the whole route) considerably more
important than it looked, and it means any future basketball quality measurement
without a determinism fix is close to meaningless.

### Baseball and MLB never reach tracking at all

Both exit **4** in about 8 seconds, before any CSV exists, on the route's own
preflight branch:

    [preflight] Sampling 10 frames for person detection...
    [PREFLIGHT FAIL] Median person count = 1 (threshold: 3)

**So their zeros are a ROUTE GATE, not a tracking result** -- an even earlier gate
than the coordinate contract that G185 identified. Ten sampled frames with a
median of one person is entirely plausible for baseball broadcast, which is mostly
pitcher/batter framing. This strengthens the NO-BENCHMARK classification for these
sports with a second, independent mechanism: they are rejected before tracking
begins, so nothing downstream of preflight has ever been exercised for them.

### What is consistent with the landed record

All four sports that do run declare `image_px` on 3 of 3 runs, exactly as G185
established from `adapter_run.py:47`. Nothing here contradicts that row.

### Honest gap the lane reported rather than papered over

The per-run GPU snapshots were queried but their stdout was lost when the remote
transport detached, and the lane recorded them **NOT ARCHIVED** rather than
substituting a current query that could not represent historical state. That is
the right call and it is why A11-style archiving needs to be in the harness, not
in the operator's hands.
