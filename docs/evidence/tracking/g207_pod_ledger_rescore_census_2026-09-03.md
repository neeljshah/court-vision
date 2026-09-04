# G207: pod ledger rescore census on evaluated-frame padding

This is a read-only arithmetic census of the live pod tracking tree on
2026-09-03. No video was opened, decoded, probed, or inferred over. No route,
daemon, keeper, source corpus, production file, threshold, coordinate contract,
denominator definition, or verdict label was changed.

## Result

**Zero rows pass.** The construct denominator is 34 complete canonical tables
from 38 tracking directories. Thirty-two could be scored with a durable decoded
count and stamped source FPS; 29 of those 32 exit first at
`coordinate_contract`. The three coordinate-valid tennis rows instead exit
first at `jump_max`, `median_track_len`, and duplicate frame-track rows. No
row has coverage as its first failure head.

More strongly, no row reaches an *enforced* coverage gate in the current
daemon-equivalent call. The 29 coordinate-contract rows return before coverage.
For the three tennis rows, evaluated-frame-padded coverage is measurable but
the harness receives no explicit `attempted_frames`, so its gated
`coverage_attempted_frames_pct` is `None` and it ultimately carries
`attempted_frames unavailable`. This is reported, not repaired.

## Construct, enumeration, and exclusions

The pod root was `/workspace/nba-ai-system/data/tracking`. The exhaustive
snapshot found 38 direct tracking directories and 38 files named
`tracking_data.csv`. A complete canonical table is a readable, nonempty CSV
whose header contains all of `frame`, `track_id`, `cls`, `x`, and `y`.

This produces the requested eligible construct denominator: **34 / 38
directories**. Four directories are excluded from that construct, with no
silent drop:

| Directory | Full pod table path | Rows | Exclusion |
|---|---|---:|---|
| `mlb_gDv5xF2AA2E` | `/workspace/nba-ai-system/data/tracking/mlb_gDv5xF2AA2E/tracking_data.csv` | 0 | Empty CSV; all five canonical columns absent. |
| `ncaa_basketball_IB-_u4gW3ds` | `/workspace/nba-ai-system/data/tracking/ncaa_basketball_IB-_u4gW3ds/tracking_data.csv` | 271 | Missing `cls`, `track_id`, `x`, and `y`. |
| `wnba_01` | `/workspace/nba-ai-system/data/tracking/wnba_01/tracking_data.csv` | 3,377 | Missing `cls`, `track_id`, `x`, and `y`. |
| `wnba_02` | `/workspace/nba-ai-system/data/tracking/wnba_02/tracking_data.csv` | 4,171 | Missing `cls`, `track_id`, `x`, and `y`. |

Two tables remain inside the 34-table canonical construct but are explicitly
unscorable, rather than assigned an estimated denominator:

| Directory | Full pod table path | Rows | Why it is unscorable |
|---|---|---:|---|
| `g172_cv2_environment_gap_20260903_a5` | `/workspace/nba-ai-system/data/tracking/g172_cv2_environment_gap_20260903_a5/tracking_data.csv` | 6,511 | No durable `harness_verdict.json` with `csv_fsynced=true`, hence no persisted decoded count. |
| `tennis_smoke` | `/workspace/nba-ai-system/data/tracking/tennis_smoke/tracking_data.csv` | 1,861 | No durable `harness_verdict.json` with `csv_fsynced=true`, hence no persisted decoded count. |

Thus the complete-table construct is 34, the scored population is 32, and the
two named canonical rows are not hidden in either number. The committed
[per-row CSV](g207_pod_ledger_rescore_rows_2026-09-03.csv) names the full pod
path and row count for all 38 directories.

## Method

For each scorable table, the read-only process used the current pod source
files, whose SHA-256 values at the snapshot were:

```text
scripts/platformkit/tracking_harness.py  59f60428c5e82460f13e009a04db05d0b27e4a567aff33a324fb7b40bea87f1d
scripts/platformkit/track_daemon_done.py 76294ea8be34b7d6d10baa58ce8abc542c3a2e6a269dd9dc60163dc967f37804
```

It read `decoded_frames` from the table's already-published
`harness_verdict.json` and the one stable `source_fps` value stamped in the
CSV. It then used the daemon's unchanged calculation and padding order:

```text
stride = sampling_plan(source_fps).stride
evaluated source indices = range(0, min(decoded_frames, stride * 30000), stride)
evaluated-frame denominator = len(indices)
input to evaluate = emitted CSV plus daemon filler rows for missing indices
```

This reproduces the G179 daemon-path denominator without calling
`adjudicate()`: calling that wrapper would invoke its decoded-frame counter and
violate this task's no-decode/no-ffprobe constraint. It invokes the frozen
`evaluate()` implementation only; there is no tracking rerun or route rerun.

The pod checkout has an import-only inconsistency: `tracking_harness.py`
imports `evaluated_frames_from_tracking_table`, which its sibling source file
does not contain. A fresh import otherwise fails before `evaluate()` is
available. The read-only interpreter supplied a process-local no-op symbol for
that direct-CSV helper, then invoked the unchanged `evaluate()` code. That
helper is not called by this daemon-equivalent DataFrame scoring path. No pod
file, bytecode, service, or running daemon process was modified. This is a
limitation of the fresh-process reproduction, not a code change or a claim
that the pod source is internally consistent.

The existing sidecars had `evaluated_frames: null`; this census therefore
derives the G179 value from their durable decoded counts and their table-stamped
FPS using the exact frozen function above. It never substitutes emitted rows,
table spacing, gameplay frames, or a ball table as a denominator.

## Per-row score table

`coverage` and `ball validity` below are the values on daemon-padded evaluated
frames. `NOT_REACHED` means a coordinate-contract early return; it is not a
zero coverage measurement. All table paths and exact row counts are in the
committed per-row CSV linked above.

| Directory | Sport | Rows | Evaluated frames | Coverage | Ball validity | Verdict | First failure head |
|---|---|---:|---:|---|---|---|---|
| `football_Z8Ezd95NnjM` | football | 136,911 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `football_wHZt1eY3A9s` | football | 258,248 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `football_yahhMkUWd7c` | football | 147,019 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `g172_cv2_environment_gap_20260903_a5` | unclassified | 6,511 | unavailable | unavailable | unavailable | UNSCORABLE | durable denominator absent |
| `kbo_01` | kbo | 63,497 | 11,529 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_02` | kbo | 39,744 | 8,085 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_03` | kbo | 39,254 | 7,830 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_04` | kbo | 54,914 | 11,952 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_05` | kbo | 53,295 | 8,781 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_06` | kbo | 47,317 | 8,866 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_07` | kbo | 49,366 | 9,030 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `kbo_08` | kbo | 76,995 | 11,923 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_03d78bee` | mlb | 39,998 | 6,311 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_08b16ce9` | mlb | 49,132 | 8,225 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_0f36e8cc` | mlb | 54,537 | 8,180 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_10893dca` | mlb | 32,380 | 6,506 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_1c6706c6` | mlb | 42,691 | 6,703 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_2143de43` | mlb | 46,570 | 7,261 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_2b814fad` | mlb | 46,490 | 6,697 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_3a02d9b3` | mlb | 35,882 | 6,155 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_7e8080e5` | mlb | 48,816 | 6,839 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_2026-08-30_f8812b72` | mlb | 60,952 | 9,959 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_A5AkcaXA2fk` | mlb | 79,013 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `mlb_gDv5xF2AA2E` | mlb | 0 | excluded | excluded | excluded | EXCLUDED | noncanonical empty CSV |
| `mlb_nLoG6gvC-Nk` | mlb | 118,535 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `ncaa_basketball_IB-_u4gW3ds` | ncaa_basketball | 271 | excluded | excluded | excluded | EXCLUDED | noncanonical columns |
| `npb_01` | npb | 140,965 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `npb_02` | npb | 154,016 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `npb_03` | npb | 139,970 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `soccer_c1mzmBGHQr4` | soccer | 182,403 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `soccer_dnR5C6WLJI4` | soccer | 237,203 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `soccer_kSgNjoaqCpI` | soccer | 230,794 | 30,000 | NOT_REACHED | NOT_REACHED | FAIL | coordinate_contract |
| `tennis_01` | tennis | 19,437 | 30,000 | 0.2794 (not gated) | 0.0890 (not gated) | FAIL | jump_max 108.39 > 8.00 |
| `tennis_02` | tennis | 1,637 | 30,000 | 0.0251 (not gated) | 0.0044 (not gated) | FAIL | median_track_len 1.00 < 3.00 |
| `tennis_ref01` | tennis | 1,861 | 9,591 | 0.0745 (not gated) | 0.0449 (not gated) | FAIL | duplicate frame-track rows 4 |
| `tennis_smoke` | tennis | 1,861 | unavailable | unavailable | unavailable | UNSCORABLE | durable denominator absent |
| `wnba_01` | wnba | 3,377 | excluded | excluded | excluded | EXCLUDED | noncanonical columns |
| `wnba_02` | wnba | 4,171 | excluded | excluded | excluded | EXCLUDED | noncanonical columns |

## Aggregate by acquisition sport

The body is grouped by the source/acquisition sport labels, with the harness
alias visible in the per-row CSV. `Eligible` is the complete-table construct,
not merely the scorable subset.

| Sport | Directories | Eligible canonical | Scored | Unscorable | Excluded | PASS | First-head distribution among scored rows |
|---|---:|---:|---:|---:|---:|---:|---|
| football | 3 | 3 | 3 | 0 | 0 | 0 | coordinate_contract 3 |
| kbo | 8 | 8 | 8 | 0 | 0 | 0 | coordinate_contract 8 |
| mlb | 13 | 12 | 12 | 0 | 1 | 0 | coordinate_contract 12 |
| ncaa_basketball | 1 | 0 | 0 | 0 | 1 | 0 | none |
| npb | 3 | 3 | 3 | 0 | 0 | 0 | coordinate_contract 3 |
| soccer | 3 | 3 | 3 | 0 | 0 | 0 | coordinate_contract 3 |
| tennis | 4 | 4 | 3 | 1 | 0 | 0 | duplicate_frame_track_rows 1; jump_max 1; median_track_len 1 |
| wnba | 2 | 0 | 0 | 0 | 2 | 0 | none |
| unclassified G172 artifact | 1 | 1 | 0 | 1 | 0 | 0 | none |
| **Total** | **38** | **34** | **32** | **2** | **4** | **0** | **shown below** |

The three baseball acquisition labels together feed the same baseball harness:
23 scored rows, all 23 first failing `coordinate_contract`.

## Aggregate by first failure head

This aggregate intentionally uses only the 32 rows that had enough durable
pre-tracking facts to score. It does not recode a later failure as first.

| First failure category | Rows | Share of scored rows |
|---|---:|---:|
| coordinate_contract | 29 | 90.625% |
| jump_max | 1 | 3.125% |
| median_track_len | 1 | 3.125% |
| duplicate_frame_track_rows | 1 | 3.125% |
| coverage gate | 0 | 0.000% |
| **Total scored** | **32** | **100.000%** |

The decision-relevant answer is therefore not that the coverage gate rejects
the program body. It is that coverage is preempted by `coordinate_contract`
for 29/32 scored rows, while the three coordinate-valid rows still have no
enforced corrected-denominator coverage adjudication in the current daemon
call. This is a measured current-state baseline, not a threshold-change
recommendation.

## Validation and non-interference checks

- No harness was added or changed, so no new harness test was required and no
  full test suite was run. This commit contains evidence files only; no LOC
  allowlisted source file grew.
- The committed CSV has 38 data rows, matching the exhaustive directory
  enumeration; it contains 34 `SCORED` or `UNSCORABLE` canonical rows, 32
  `SCORED`, 2 `UNSCORABLE`, 4 `EXCLUDED`, and 0 `passed=true`.
- The scored first-head counts sum to 32: 29 + 1 + 1 + 1. The sport table's
  directory, eligible, scored, unscorable, excluded, and pass totals sum to
  38, 34, 32, 2, 4, and 0 respectively.
- The remote process used `python3 -B` with `PYTHONDONTWRITEBYTECODE=1`, read
  only CSV/JSON/code text, and emitted compact summaries. It copied no corpus
  table back to this worktree.

## NOT VERIFIED

- This is a snapshot of a live tree, not a filesystem-atomic global snapshot;
  a later daemon completion can legitimately change the directory body.
- The tracking route is non-deterministic (G189, G195, G198). Each row is one
  sample from a distribution, not a reproducible fixed property of its clip.
- G198's uncorrected misalignment remains in force: detections are attributed
  to the next processed frame. Every number here measures the current system
  including that defect, and is a baseline to improve against, not a statement
  of what the tracker could achieve.
- This is not directly comparable with G176's 18-row pre-correction ledger
  survey: both the body and the scoring construct have changed.
- The two canonical but unscorable rows might score differently if they later
  acquire durable decoded-denominator provenance. No count was guessed.
- The four noncanonical rows were not transformed or relabeled. Their data may
  still be useful in another construct, but it is not a canonical harness input
  here.
- A fresh unshimmed pod import cannot currently load the harness due to the
  missing direct-path helper. This report validates the unchanged `evaluate()`
  source through the narrow process-local compatibility setup described above,
  not a clean fresh import of the full pod checkout.
- No claim is made about physical tracking accuracy, calibration correctness,
  real-time behavior, or how any table would score after a rerun.
