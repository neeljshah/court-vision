VERDICT: PARTIAL -- detection >= 0.80 is not met for A5_BALL_SHIFT (13/34 = 0.382 at FULL); every other bar in G358_spec.md:60-74 holds.

# G358 full-section image-space gate execution v2 -- fix 1c (complete eligible set, standard statistics)

Row G358 | worktree `/workspace/wt/a12` (pod) | Spec `docs/evidence/tracking/specs/G358_spec.md` VERSION 2026-09-08. Prereg `g358_prereg_2026-09-08.md` (seal `28e3c5e7...`, unedited) plus amendment `g358_prereg_fix1c_2026-09-08.md` (seal `bd92bab4...`, commit bb54870d4), both sealed before this run. Supersedes fix 1b (candidate 713413a96), REJECTed in `G358_VERIFY_2026-09-08.md`. Eye check: NONE.

## Premise, re-measured read-only on the pod
`frames_distribution.csv`: 71 sections PRESENT; 68 eligible (>= 150 unique frames) across 19 games; 2 G346_LIVE + 66 POST_EPOCH; eligible unique-frame distribution min=392, p10=470.0, median=946.5, p90=1000.0, max=1000, n=68. Premise holds far above the >= 6 sections / >= 4 games bar.

## Sealed selection -- even, never a head slice (closes B7 / Q7)
Amendment rule: n = 68 > 40, so k = floor(68 / 30) = 2 and every 2nd section is taken from the fixed (game_id, section_name) order starting at index 0 -> 34 sections across 17 games (1 G346_LIVE, 33 POST_EPOCH). Sealed in `sealed_sections_fix1c.csv` (commit 0292a9db5, before any gate ran) with path, sha256, bytes and rows for BOTH `tracking_data.csv` and `ball_tracking.csv`. Reproduced this session: the even sample recomputed from the census matches the 34 sealed section names exactly (diff empty). Every sealed digest re-verified at load; a mismatch raises.

## Gate x arm x duration (`gates.csv`, `duration.csv`; 34 sections x 6 arms x 4 durations x 18 gates = 432 cells)
FULL-section `any_gate`, denominator 34 sections in every cell:
    A0 (unchanged)    false rejection  13/34 = 0.382353   Wilson 0.239-0.550
    A1_FROZEN         detection        34/34 = 1.000000   Wilson 0.898-1.000
    A2_ID_MERGE       detection        34/34 = 1.000000   Wilson 0.898-1.000
    A5_BALL_SHIFT     detection        13/34 = 0.382353   Wilson 0.239-0.550   -- below the 0.80 bar
    A3_SCALE_TRANSLATE / A4_MIRROR: UNIDENTIFIABLE by construction, reached_n 000000 at every duration, reported not counted.
A5_BALL_SHIFT equals A0 in EVERY aggregate cell at FULL and at 30s (all 18 gates; reached, evaluated and rejected counts identical); the two arms differ only at 10s and 2s and only in the ball gates. On this evidence the FULL A5 figure is the A0 false-rejection baseline, not a measured response to the planted shift.
A0 `any_gate` across durations: 2s 34/34 = 1.000, 10s 7/34 = 0.206, 30s 9/34 = 0.265, FULL 13/34 = 0.382.
Of the 18 gates, 10 are evaluable leaf gates at FULL (evaluated_n 34): 6 clear 0.05, 4 exceed it. 7 leaf gates report reached_n 34 with evaluated_n 0 (NOT_APPLICABLE / MEASURED_NO_BAR) -- visible only after the fix-1c reached_n correction.

## Diagnosis (`diagnosis.csv`; FULL, arm A0, share > 0.05; corrected statistics)
Median = numpy.median (the mean of the two middle values when n is even); p90 = numpy.quantile(values, 0.9) under numpy default linear interpolation; both computed with the identical `pandas.Series.median()` / `pandas.Series.quantile(0.9)`. This replaces the fix-1b select-by-index computation.
    zero_step_share          n=34  share 0.294118  median 0.750378  p90 0.968011  threshold 0.883869  THRESHOLD_MISCALIBRATED
    distinct_position_ratio  n=34  share 0.264706  median 0.224620  p90 0.532783  threshold 0.108915  THRESHOLD_MISCALIBRATED
    stationary_track_share   n=34  share 0.088235  median 0.000000  p90 0.100000  threshold 0.149     THRESHOLD_MISCALIBRATED
    median_step_distance     n=34  share 0.058824  median 0.000000  p90 2.236068  threshold 8.408436  THRESHOLD_MISCALIBRATED
Reseal PROPOSAL only, in this memo: 0 thresholds moved, 0 `src/` edits, every adapter output row `scorable=False` (asserted in the passing adapter test).

## Sign convention of every delta
`rejection_share` = rejected_n / evaluated_n, with evaluated_n counting PASS and REJECT only. On A0 a HIGHER share is WORSE (false rejection, bar <= 0.05). On A1 / A2 / A5 a HIGHER share is BETTER (detection, bar >= 0.80). Wilson bounds are 95 pct and are stored as additive integer per-mille columns, permille = round(1000 * share). `reached_n` counts PASS / REJECT / NOT_APPLICABLE / MEASURED_NO_BAR and never enters a share.

## Tests (each file alone, pod python3)
`test_g358_gate_execution.py` 7 passed; `test_g358_production_schema_adapter.py` 5 passed; `test_g353_image_space_gates.py` 4 passed; `test_g353_production_translation.py` 1 passed.

## Wall time
Sealed 34-section loop on the pod: 80 s (launch 17:45:46 -> `gates.csv` written 17:47:06). The three result tables reproduce the earlier PC run byte-identically (`cmp` clean on all three).

## SHA-256 (as stored)
`g358_gate_execution.py`=`92f4bfba01d283f20418bd41b0c43ed23364b55e203ccfed1276b270d03852e5`; `production_schema_adapter.py`=`dabc1070de4c531299fe1f59fdfae8c8436bff5179039ffa6bb227aafe73be02` (unchanged); `test_g358_gate_execution.py`=`e96974d3284b2b982da66604650fb36746ed2c8dabf8c710efa47f33069a084f`; `test_g358_production_schema_adapter.py`=`62190f86710f7653a0ea7d632cbd0b6d4cf155256e9b76b8a0c70c65767195c5` (unchanged); `sealed_sections_fix1c.csv`=`05c9267ef9827f85d819dddff4ea6177a61a567f11cebadaa5959f67f1a0be1a`; `frames_distribution.csv`=`14f5ace56682ed7479f946c0a4d411978a200cdf269a064ceb0f1467ec09595c`; `gates.csv`=`e29d610fad0eb6aa7b7564b10e55b96ae35a642acbec46d7b0d6abedc7c23383`; `duration.csv`=`68473bd7e3856ac39f29eb3473e043a7b0861822b764a1bba4680bff9bc282b5`; `diagnosis.csv`=`46c8c63b58c40a5aed1c166b44d1689bc51d554af8c4ef17f9cf509016e0487c`.

Vocabulary follows contract Q6; automated scan required.
SCAN (patterns assembled from single characters at run time, word-boundary; run over this memo, the three result tables, the sealed list, the census, the module, its test, and the appended register line):
    python3 /workspace/g358_scan.py <the 9 files above>
SCAN OUTPUT (verbatim, exit 0):

## NOT VERIFIED
Detection >= 0.80 for A5_BALL_SHIFT at any duration (measured FULL 0.382, 30s 0.265, 10s 0.206, 2s 0.941). Whether A5_BALL_SHIFT is detected at all at FULL, as opposed to its 13/34 being A0 false rejections: the two arms are identical in every FULL and 30s cell and no per-section pairing was archived to separate them. Whether the 4 gates above 0.05 would clear it on a different corpus snapshot. Containment: `frame_size_source` is absent on every section (no sidecar), so `g325_wholly_off_frame`, `oob`, `jump_max`, `jump_p95`, `coordinate_contract`, `attempted_frames` and `coverage_attempted_frames` never reached a bar. Any court-geometry certification: image-space gates are necessary, never sufficient. Any claim beyond these 34 sections; the corpus and the register both rotate and this is one snapshot.

Fix 1c closes: A5 medians, B7/Q7 even full-set sampling (n=34), B2 ledger append, Q6 wording.
