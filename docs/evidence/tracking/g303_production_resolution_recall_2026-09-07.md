VERDICT: MEASURED (fix pass 1b), three results. (1) The route does not feed what the source constant implies: it hands the detector a 1020x1920 TOPCUT-cropped array and the network tensor is `[1, 3, 352, 640]`, a 9.2x AREA reduction, and its own confidence is 0.22 where the spec registers 0.3. (2) At the REGISTERED conf 0.3, on the 113 adjudicated G296 points over 16 clip-wide frames, the native arm gains **+0.2124** recall at 50 px (95% CI +0.1176..+0.3058; McNemar exact nominal p 0.000019). (3) At the G298-comparable 100 px that gain is +0.2301 against G298's +0.3357, so the resolution attribution is **SMALLER** here but survives the move to a clip-wide two-pass adjudicated basis. Nothing is adopted, no production default is changed and no bar is moved. Secondary n = 86 / 131 / 130 (consensus / pass-A-only / pass-B-only). Ground truth here is two MODEL locators plus a MODEL adjudicator, not human labels.
## Why this is fix pass 1b
Candidate `e82b702fc` was REJECTED (`G303_VERIFY_2026-09-07.md`): the arms ran at the route's conf 0.22 rather than the registered 0.3; the two "secondary denominators" divided the PRIMARY numerator by 131 and 130, which measures nothing and is withdrawn in full; four tolerances were reported where three are registered; and the six mandated overlays were never rendered. Spec amendment `VERSION 2026-09-07b` (committed alone, `2abfd06aa`) and the sealed prereg SUPPLEMENT (committed alone, `fbab30157`, seal SHA-256 `aaf4751a1fb3d4cbc61e22ef5c23a1f8328ce0008de3e2a4296d161d3706c6aa` over the LF-normalized bytes above its seal line) fixed every estimator BEFORE this rerun. G296 has since LANDED (`ef3269572`), so the PRIMARY basis is now the 113 adjudicated points the spec asked for.
## Machine, inputs, code identity (A9, A11, S1)
Detection ran on the pod RTX 3090 in compute-only scratch `/workspace/wt/a12/jobs/20260907193544_288118_6674`; all arithmetic, the overlays and the tests are local in `C:/Users/neelj/nba-track-a12`, branch `track-a12`. Inputs are the 24 COMMITTED G296A JPEGs `docs/evidence/tracking/g296a_located_players_artifact/frames/frame_01..24.jpg` (1920x1080; per-file SHA-256 in `g303_detect.json`); the source video is NOT opened. Weights: the DEPLOYED `yolov8n.pt`, SHA-256 `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`, staged read-only and never overwritten. Python 3.12.3, torch 2.8.0+cu128, ultralytics 8.4.143, cv2 4.14.0, half=True, device 0. Probes verbatim: `nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader` -> `6344 MiB, 24576 MiB` (18232 MiB free against the harness's own 8000 MiB gate); `dd if=/dev/zero of=... bs=1M count=8 conv=fsync` rc=0, `8388608 bytes (8.4 MB, 8.0 MiB) copied, 0.277792 s, 30.2 MB/s`; launcher disk guard `POD /workspace 29309 MB used of 50000; /workspace/wt 13721 MB` followed by `WARNING /workspace/wt above 3 GB -- ping the tracking session`. Nothing was deployed to `/workspace/nba-ai-system`, nothing under `data/` was written, no pod process was signalled and no corpus source or bridge partial download was deleted.
## Step 0 -- the binding premise, MEASURED not read
Printed at run time: `BEFORE-CONDITION input_size=640 lt_1920=True route_conf=0.22 registered_conf=0.3` -- PASS. Instrumented from OUTSIDE `src/` by proxying the detector's model object and wrapping the ultralytics predictor `preprocess`; `src/` is imported and run, never edited, and 0 downstream calls raised in any arm.

| what the route actually does | measured |
| --- | --- |
| array handed to the model | `(1020, 1920, 3) uint8` -- `frame[TOPCUT:]`, TOPCUT = 60 |
| tensor the network runs on | `[1, 3, 352, 640] torch.float16` -- 0.225 MP against native 2.07 MP |
| the route's OWN confidence | `advanced_tracker._fill_conf_threshold = 0.22`, NOT the registered 0.3 |
| ARM P call kwargs (registered) | `classes=[0], conf=0.3, imgsz=640, half=True, device=0` |
| ARM P22 call kwargs (route as it runs) | `classes=[0], conf=0.22, imgsz=640, half=True, device=0` |
| pose branch | ACTIVE; serves frames 0 and 113758 at a FIXED `pose_imgsz=640` in EVERY arm |

640 is a LONG-SIDE budget, so the short side lands at 352 after letterbox. G298's ARM A described a SETTING, not the route. The conf conflict is recorded, not resolved: the spec registers 0.3 and every scored arm except P22 uses it.
## Ground truth -- four bases, each matched independently against its OWN points
PRIMARY: the **113 adjudicated** G296 points (`g296_ground_truth_2026-09-07.csv`, every row whose `source` is not `dropped`: 1 agreed + 28 adjudicated_A + 84 adjudicated_B) over **16** of the 24 frames. SECONDARIES, each re-matched from scratch: the **86 consensus** midpoints from the pre-existing UNMODIFIED `g296_merge_locators.py` at its committed `MATCH_RADIUS_PX = 60.0` (read, never moved) over 15 frames; **pass A's own 131** eligible on-court feet; **pass B's own 130**. Merge output reproduced locally: jaccard 0.4914, matched 86, median pass-to-pass offset 23.9679 px, p90 42.7200 px, 45 A-only, 44 B-only, 131 A and 130 B eligible. No numerator is carried between bases.
## Arms -- one difference between P and R, and determinism
All five arms construct the UNEDITED `AdvancedFeetDetector` as the pipeline does. The ONLY difference between P and R is `_infer_imgsz`; same weights, classes, conf, half, device, crop and decoded pixels. ARM P ran TWICE and the two CSVs are **byte-identical** (both SHA-256 `1bcf987704f521c5...`), checked before any arithmetic. R, M and P22 have ONE draw each and their repeatability is NOT VERIFIED. P22 is the route exactly as it runs and is REPORTED, never substituted for P.

| arm | imgsz | conf | boxes / 24 fr | per frame | boxes on the 16 scored frames | median nearest px | precision LOWER BOUND @50 | ms per frame | peak VRAM MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P | 640 | 0.3 registered | 217 | 9.04 | 166 | 29.55 | 0.3494 | 557.9 | 80.7 |
| P22 | 640 | 0.22 route | 288 | 12.00 | 226 | 27.66 | 0.2965 | 519.9 | 88.8 |
| R | 1920 | 0.3 registered | 868 | 36.17 | 803 | 22.14 | 0.1021 | 787.7 | 370.5 |
| M | 1280 | 0.3 registered | 564 | 23.50 | 510 | 22.36 | 0.1686 | 700.1 | 212.5 |

ARM R buys its gain by emitting **4.0x** ARM P's boxes (868 against 217) while its precision LOWER BOUND falls from 0.3494 to 0.1021 at 50 px; ARM M (1280) equals or beats R at every tolerance on the primary basis with 65% of R's boxes, so on this set the gain SATURATES below 1920. Precision here is a lower bound by construction: a correct detection of a real person outside the 113 accepted points is scored as a false positive. Timing is ONE draw and DESCRIPTIVE ONLY -- the spec puts timing out of scope, and the spread between ARM P (557.9 ms) and its byte-identical repeat (346.9 ms) EXCEEDS the P-to-R difference, so nothing here says a larger input is practical.
## Recall on the PRIMARY basis: 113 adjudicated points over 16 frames (one-to-one Hungarian)
| tol px | ARM P (route imgsz, conf 0.3) | ARM P22 (route as it runs, conf 0.22) | ARM R (1920, conf 0.3) | ARM M (1280, conf 0.3) |
| ---: | --- | --- | --- | --- |
| 25 | 41/113 = 0.3628 [0.2773, 0.4580] | 48/113 = 0.4248 [0.3333, 0.5175] | 62/113 = 0.5487 [0.4426, 0.6476] | 62/113 = 0.5487 |
| **50** | **58/113 = 0.5133 [0.4000, 0.6275]** | 67/113 = 0.5929 [0.4793, 0.6931] | **82/113 = 0.7257 [0.6154, 0.8148]** | 86/113 = 0.7611 |
| 100 | 67/113 = 0.5929 [0.4622, 0.7207] | 76/113 = 0.6726 [0.5478, 0.7857] | 93/113 = 0.8230 [0.7019, 0.9197] | 95/113 = 0.8407 |
## The SAME arms on the three SECONDARY bases -- matched, never recycled (cells are 25 / 50 / 100 px)
| basis (its own denominator) | ARM P | ARM P22 | ARM R | ARM M |
| --- | ---: | ---: | ---: | ---: |
| consensus-86, 15 frames (n = 86) | 47 / 54 / 57 | 51 / 60 / 63 | 65 / 71 / 74 | 65 / 73 / 75 |
| pass A's own eligible feet (n = 131) | 32 / 52 / 70 | 38 / 61 / 81 | 45 / 77 / 98 | 45 / 79 / 102 |
| pass B's own eligible feet (n = 130) | 57 / 69 / 76 | 61 / 74 / 83 | 84 / 101 / 109 | 84 / 104 / 109 |

Every one of those cells is a fresh one-to-one assignment against that basis's own points; the rejected candidate's `[60, 131]` and `[60, 130]` pairs were the primary numerator over foreign denominators and are withdrawn. R-minus-P at 50 px on each secondary: consensus-86 +0.1977 [+0.0959, +0.2921] p 0.000076; pass A +0.1908 [+0.1085, +0.2734] p 0.000011; pass B +0.2462 [+0.1579, +0.3309] p 0.0000004.
## Paired comparison on the primary basis, delta = ARM R minus ARM P (positive = R finds more)
| tol px | delta recall | 95% CI (paired frame resample) | McNemar lost / gained / discordant | nominal p |
| ---: | ---: | --- | --- | ---: |
| 25 | +0.1858 | [+0.0971, +0.2778] | 6 / 27 / 33 | 0.000324 |
| **50** | **+0.2124** | [+0.1176, +0.3058] | 4 / 28 / 32 | 0.000019 |
| 100 | +0.2301 | [+0.1321, +0.3303] | 2 / 28 / 30 | 0.000001 |

McNemar is used because both arms observe the SAME points on the SAME frames, so the samples are DEPENDENT and an unpaired two-proportion test would be WRONG. All p are NOMINAL; there is NO multiplicity correction across the three tolerances, the four bases or the two matching rules, and points within a frame are not independent (no clustering adjustment). CIs are 95% percentile bootstrap over FRAMES, 10000 draws, seed 20260907.
## Against G298: SMALLER, and NOT a replication
G298 measured 25/143 = 0.174825 -> 0.510490 at 100 px, delta +0.335664. Here the same-tolerance delta is +0.2301 and ARM P's baseline is 0.5929 rather than 0.1748. The resolution effect on the clip-wide adjudicated set is therefore **SMALLER**, which WEAKENS G298's headline as a general magnitude while leaving its direction and much of its size intact -- and it is markedly larger than the +0.1512 the rejected conf-0.22 candidate reported, so the conf the arms run at moves this number. This compares two different frame sets (15 frames inside 19599-23399 versus 24 clip-wide), two locator sets (one MODEL rater versus two plus a MODEL adjudicator), two denominators (143 versus 113) and two matching rules (nearest versus one-to-one). It is NOT a replication and must not be called one. G278 measured G298's span friendlier than its own clip (0.836 against 0.656, p = 0.0078).
## Eye check -- six EVENLY SPACED frames, no head slice
Sample positions 0, 5, 9, 14, 18 and 23 of the 24 sorted indices (`round(i*23/5)`, fixed in the prereg supplement before rendering), frames 0, 37919, 68255, 106174, 136510 and 174429, each with the adjudicated points, the consensus points and both arms' detection footpoints drawn, rendered headless and committed at `g303_artifact/eyecheck/` (261-292 KB each, all under the 300 KB cap). They come from the SAME run whose CSVs are committed (B11). Frame 0 is the pose-served frame: both arms emit 2 boxes there and neither is near any of its 6 adjudicated points, which is the pose branch's fixed 640, visible.
## ACCEPTANCE RULE, line by line
- metric -- PASS. Measured input shape verbatim; merge output with all counts; five arms' exact settings with the single-difference design stated; ARM P determinism byte-identical; recall at 25/50/100 against the named 113-point primary with all three secondaries independently matched; McNemar exact with nominal p and the no-correction statement; per-arm totals, per-frame counts and median nearest distance; the SMALLER statement against G298 with its not-a-replication caveat.
- before -- PASS. G298's attribution rested on 15 single-locator frames in one measurably friendly span, and the route's actual detector input had never been instrumented. Both are measured, and the second falsifies the `imgsz=640 on 1920x1080` reading of the route.
- bar -- N/A by the spec's own words: NO pass bar. A gain was found, it is smaller than G298's, and both halves are reported as plainly as each other.
- n -- PASS, stated: 24 frames detected, 16 scored; 113 adjudicated points primary, with 86, 131 and 130 as independently matched secondaries; 4 distinct arms plus 1 repeat; 3 tolerances; 1 clip; 1 draw per arm; ground truth is 2 MODEL locators and a MODEL adjudicator, not a human.
- eye check -- PASS. Six evenly spaced overlays committed with this memo.
- must not move -- PASS. `g296_merge_locators.py` still reads `MATCH_RADIUS_PX = 60.0`; nothing under `src/`, `domains/`, `api/` or `kernel/` was edited; no production default, threshold, filter or flag changed; `_infer_imgsz` and `_fill_conf_threshold` were set on this harness's OWN instances only; `yolov8n.pt` never overwritten; the deployed tree untouched; G296's and G298's counts and verdicts unchanged.
## Honest limitations
Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS, and both can be wrong in the same way; the adjudicator that produced the 113 points is a THIRD MODEL, so an accepted point is model located and model adjudicated. No human has checked these frames. G296b rated only 26/163 = 0.160 of its own player locations `confident`, and G291 measured two model raters at Cohen's kappa 0.283 on an easier task, so this is an approximately-positioned basis. The two passes agree on only 86 of 131 and 130 eligible points, and the 60 px consensus radius is WIDER than the 25 px tolerance scored. A detector that finds a player the locators missed is scored WRONG here, which bounds every recall figure from above and below. ONE clip, one shot per frame, one draw per arm; 24 frames is clip-wide but thin. Recall is not precision. This row measures the route and two alternative input sizes and ADOPTS NONE; it is a calibration measurement of a detector, not a claim about any downstream number.
## Evidence, tests, time
Harness `scripts/platformkit/tracking/g303_recall_vs_resolution.py` (248 lines, fix 1d adds the lazy re-export) and the split-out `scripts/platformkit/tracking/g303_report.py` (175 lines, fix 1d adds the legacy per-arm aliases and `basis`/`secondary_denominators`, fix 1e makes six of them compatibility-safe `.get()` reads); `scripts/platformkit/tracking/g303_overlay.py` (104 lines). Prereg `g303_prereg_2026-09-07.md` (seal `86e2ccad77a8fc452d329d6026f21f5ac4c422240e7458fca439e64c0a23d1ce`, `8c223275e`) plus the supplement above. Artifact `g303_artifact/` totals 1,951,231 bytes (was 1,906,951 at fix 1c; +44,280 added, 0 freed, entirely the extended report), SHA-256 first 16: `P.csv` 12539 B `1bcf987704f521c5`, `P_repeat.csv` 12539 B `1bcf987704f521c5`, `R.csv` 49186 B `636f251ffa91103b`, `M.csv` 33379 B `f1039cda99553e2b`, `P22.csv` 16794 B `854d77f532086f13`, `g303_detect.json` 23549 B `cc2aa3f3b65d7403`, `g303_report.json` (fix 1d regeneration, e82b702fc legacy per-arm/basis aliases added; COMMITTED blob bytes via `git hash-object`, checkout normalization NOT applied) 107845 B `0f4ee0f6d56bfe6b`, `per_frame_recall.csv` 349 B `6d31f885d5ab072d`, and the six overlays `b31cd2bc3a09386b`, `e5fb3d1175fdef59`, `073999fb78f6b71f`, `7184869a779a7401`, `78e081151423ed08`, `73643929d1214ec6`. Tests: `python -m pytest tests/platformkit/test_g303_recall.py -q` **15 passed** (fix 1e adds the pre-31a three-key META compatibility test); `tests/platformkit/test_loc_rail_scope.py -q` **1 passed**. Pod log tail: `G303 detect done; P_repeat byte-identical=True` / `POD_RUN_DONE job=20260907193544_288118_6674 rc=0`. TIME SPENT: about 1 h 5 min wall clock (2026-09-07 19:18-20:23 CDT), of which about 27 min was the launcher's `du` preamble, ship and pod queueing (19:35 launch, 19:54 remote start, 20:02 fetch back); fix 1d is local arithmetic only, no new pod run.
## NOT VERIFIED
- Human correctness of any ground-truth point; every coordinate is model located and model adjudicated.
- That the 113 accepted points are the complete on-court set; a player both passes missed, or both placed badly, cannot be recovered by an agreement procedure.
- Whether ARM R's extra 651 boxes are players or false positives; this row cannot tell them apart and the precision figures are lower bounds, not a resolution of that question.
- Which confidence the route SHOULD run at: the 0.22-versus-0.3 conflict is recorded, not adjudicated, and nothing here proposes a change to either.
- Repeatability of ARM R, ARM M and ARM P22 (only ARM P was run twice), and any timing conclusion: one draw per arm, and a warm-up spread wider than the between-arm difference.
- Anything outside this one WNBA clip, and any end-to-end tracking, registration or harness consequence: this row ran SINGLE-FRAME DETECTION, not the tracking route.

## Fix 1c (verifier corrections)
`G303_VERIFY_2026-09-07.md` REJECTed fix 1b (`61fa77b38`) on B2 backward compatibility plus
three NEW GAPs; the measurement itself PASSED (premise and headline both reproduced) and is
UNCHANGED here. No re-scoring and no new measurement were performed; every number above is
the same computation on the same committed inputs.
- CORRECTION 1 (B2): `g303_report.json` restores the legacy top-level `primary_denominator`,
  `primary_denominator_name`, `primary_frame_ids`, `arms` and `paired_R_vs_P` paths as
  compatibility ALIASES pointing at `bases[adjudicated_113]`'s own fields -- same objects,
  never recomputed. The new `bases`/`arm_cost` structure is unchanged and kept.
- CORRECTION 2 (B2): `--ground-truth` is optional again (`required=flag != "ground-truth"`),
  with the prior G296 consensus fallback for the PRIMARY basis when it is absent. A new
  legacy-CLI regression test invokes the module the old way (no `--ground-truth`) against the
  committed arm outputs and asserts the legacy fields exist and equal the new ones they alias.
- NEW GAP (LOC): the 336-line harness is split -- `g303_recall_vs_resolution.py` (236 lines:
  detection, footpoint, matching, `main`) and the new `g303_report.py` (134 lines: the four
  bases, the report writer, the legacy aliases) -- both under the 300-line rail with no
  allowlist entry; the A12 line for this file is removed from
  `tests/platformkit/test_loc_rail_scope.py`.
- NEW GAP (consensus artifact): `g303_artifact/consensus_points.csv` (86 points over 15
  frames) is committed, regenerated deterministically from the committed G296 pass-A/pass-B
  CSVs via the unmodified `g296_merge_locators.consensus()` at its committed 60 px radius --
  the same numbers already reported above and in `g303_recall_vs_resolution_2026-09-07.md`.
- NEW GAP (report hash): `g303_report.json` is regenerated with the alias writer from the
  committed arm outputs (`P`/`P_repeat`/`R`/`M`/`P22.csv`, `g303_detect.json`); every
  pre-existing field (`tolerances_px`, `registered_conf`, `step0`, `sign_convention`,
  `arm_P_byte_identical_repeat`, `arm_cost`, `bases`) reproduces byte for byte against the
  file committed at `61fa77b38`, checked by
  `test_report_regeneration_reproduces_every_pre_alias_field_byte_for_byte`; `git diff`
  against that commit shows a pure addition (330 insertions, 0 deletions) -- the aliases are
  appended, nothing existing moved. The evidence line above is corrected to the COMMITTED
  blob's bytes and SHA-256 (via `git hash-object`, checkout normalization NOT applied), which
  is why it now differs from the file size a plain checked-out read would show on this
  CRLF-checkout Windows worktree.
Tests: `python -m pytest tests/platformkit/test_g303_recall.py -q` -> 13 passed;
`tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed.

## Fix 1d (verifier corrections)
`G303_VERIFY_2026-09-07.md` REJECTed fix 1c (`997746109`) on B2 backward compatibility being
checked only against fix 1b (`61fa77b38`) rather than the ORIGINAL `e82b702fc` candidate, plus
two NEW GAPs; the measurement itself PASSED again and is UNCHANGED here. No re-scoring and no
new pod run were performed; every number above is the same computation on the same committed
inputs, now written through the extended report writer.
- CORRECTION 1 (ACCEPT n): this memo's verdict line (top) now states the secondary n =
  86/131/130 and that ground truth is two MODEL locators plus a MODEL adjudicator, not human
  labels.
- CORRECTION 2 (B2): `g303_report.py` adds the remaining `e82b702fc` legacy top-level paths
  `basis` and `secondary_denominators`, and seven per-arm legacy aliases --
  `total_detections_24_frames`, `detections_per_frame_24`, `ms_per_frame`, `peak_vram_mib`,
  `pose_served_frames`, `downstream_errors` and `precision` -- all populated from the SAME
  numbers already computed, never recomputed. The two `matched_over_pass_A_only` /
  `matched_over_pass_B_only` recall fields are also restored, but with the CORRECTED
  basis-specific matched count (each arm scored fresh against pass A's own 131 points and pass
  B's own 130), not the primary numerator the original `e82b702fc` candidate had recycled into
  both slots; each carries a sibling `_note` key saying so.
- CORRECTION 3 (B2 test): the compatibility test is now RECURSIVE against the `e82b702fc`
  legacy JSON (every dict key path, walked via `git show`, skipping the "40" tolerance this
  candidate deliberately dropped per B10) instead of a fixed field list against the immediate
  prior candidate; a second assertion confirms the no-`--ground-truth` run's `basis` alias
  reads `"consensus"`, matching what `e82b702fc` itself was (a no-ground-truth, consensus-basis
  run).
- NEW GAP (re-export): `g303_recall_vs_resolution.py` adds a module `__getattr__` (PEP 562)
  that lazily re-exports `score`/`score_basis`/`bootstrap_ci` from `g303_report.py` on first
  access, so `from g303_recall_vs_resolution import score` keeps working for any caller that
  has not moved to importing `g303_report` directly -- without a module-load-time circular
  import (`g303_report` already imports FROM this module at its own top).
- NEW GAP (memo drift): the evidence line above is corrected to the measured LOC split (248 +
  170 lines) and test count (14) and the COMMITTED artifact total recomputed from the
  committed blobs (1,951,231 B), replacing the stale 336-line/11-test/1,892,778 B figures the
  prior verify cycle flagged as already wrong even for fix 1c.
Tests: `python -m pytest tests/platformkit/test_g303_recall.py -q` -> 14 passed;
`tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed.

## Fix 1e (verifier corrections)
`G303_VERIFY_2026-09-07.md` REJECTed fix 1d (`31a32717c`) on B2: `score_basis` read the six new
per-arm cost keys straight off `meta[arm]`, so the pre-31a legacy three-key META call
(imgsz/conf/conf_source only, no cost fields) raised `KeyError: total_detections`; the changed
test fixture had grown all six keys and so never exercised the legacy call. No re-scoring and no
new pod run were performed; the measurement is UNCHANGED, only the writer's compatibility
handling and its tests.
- CORRECTION 1 (B2): the six `meta[arm]` reads backing `total_detections_24_frames`,
  `detections_per_frame_24`, `ms_per_frame`, `peak_vram_mib`, `pose_served_frames` and
  `downstream_errors` are now `.get(key, None)` in `g303_report.py::score_basis`; the legacy
  three-key META call succeeds again and the six aliases come back JSON `null` rather than a
  fabricated `0`/`[]`. `imgsz`/`conf`/`conf_source` stay required direct reads (they were
  already part of the pre-31a legacy contract). `tests/platformkit/test_g303_recall.py` restores
  the pre-31a minimal `LEGACY_META` fixture as a fixture SEPARATE from the full `META` used by
  the alias-value tests, and a new
  `test_score_basis_still_accepts_the_pre_31a_three_key_meta` asserts the three-key call still
  succeeds and returns the legacy `imgsz`/`conf`/`conf_source`/`recall` fields plus the six null
  aliases.
- NEW GAP (waiver walker): the recursive `e82b702fc` compatibility walker used to `continue` past
  any `"40"` dict key without recording it, so the one intentional schema drop (B10 PASS: this
  candidate registers 25/50/100 px, the rejected 40 px column is gone) was never actually
  checked, only assumed. `_walk_legacy_paths` now yields every path unfiltered; the test --
  renamed `test_legacy_schema_paths_present_except_the_rejected_40px_branch_waiver` -- partitions
  the missing paths and asserts the waived set is non-empty and exactly the paths containing a
  `"40"` segment, with every other legacy path still present.
- NEW GAP (git-unavailable path): the same test silently `return`ed (a vacuous pass) when `git
  show` failed instead of reporting anything; it now calls `pytest.skip("git unavailable")` so a
  broken git toolchain shows as SKIPPED, not a false PASS.
Tests: `python -m pytest tests/platformkit/test_g303_recall.py -q` -> 15 passed;
`tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed.
