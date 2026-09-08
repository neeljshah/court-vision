SUPERSEDED by `g303_production_resolution_recall_2026-09-07.md` (fix pass 1b). This candidate was REJECTED at `e82b702fc` (`G303_VERIFY_2026-09-07.md`): its arms ran at conf 0.22 instead of the registered 0.3, its two secondary denominators recycled the primary numerator, it reported four tolerances where three are registered, and it rendered no eye check. Everything below is retained only as the rejected record and must not be quoted as current.

# G303 -- recall at the production route's MEASURED detector input vs a native arm

VERDICT: MEASURED, two results. (1) The route does not feed what the source constant implies: it hands the model a 1020x1920 TOPCUT-cropped array at conf 0.22, and the tensor the network runs on is `[1, 3, 352, 640]` -- 0.225 MP against native 2.07 MP, a 9.2x AREA reduction of an already-cropped frame. (2) On the clip-wide two-pass set the native arm gains +0.1512 recall at 50 px (95% CI +0.0781..+0.2222; McNemar exact p = 0.000977), LESS THAN HALF the +0.3357 G298 reported, so G298's headline was substantially span-specific. No production default is changed, no bar is moved, and NEITHER input size is adopted.

## Machine, inputs, code identity (A9, A11)
Detection on the pod RTX 3090, compute-only scratch `/workspace/wt/a12/jobs/20260907183845_214575_4150`; arithmetic and tests local in `C:/Users/neelj/nba-track-a12`, branch `track-a12`. Inputs are the 24 COMMITTED G296A JPEGs (`g296a_located_players_artifact/frames/`, 1920x1080, per-file SHA-256 in `g303_detect.json`); the source video is NOT opened. They are JPEG re-encodes -- G296 measured paired MAD 0.7363-0.8908 grey levels against the pod decode versus 34.79-77.21 for an adjacent-index control. Weights: the DEPLOYED `yolov8n.pt`, SHA-256 `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36`, staged read-only and never overwritten. Python 3.12.3, torch 2.8.0+cu128, ultralytics 8.4.143, cv2 4.14.0, half=True, device 0.

## Step 0 -- the binding premise, MEASURED not read
Printed at run time: `BEFORE-CONDITION input_size=640 lt_1920=True` -- PASS. Instrumented from OUTSIDE `src/` by proxying the detector's model object and wrapping the ultralytics predictor `preprocess`; `src/` is imported and run, never edited, and 0 of 96 calls raised downstream.

| what the route actually does | measured |
| --- | --- |
| array handed to the model | `(1020, 1920, 3) uint8` -- `frame[TOPCUT:]`, TOPCUT = 60 |
| kwargs at the call site | `classes=[0], conf=0.22, imgsz=640, half=True, device=0` |
| tensor the network runs on | `[1, 3, 352, 640] torch.float16` |
| pose branch | ACTIVE; serves frames 0 and 113758 at a FIXED `pose_imgsz=640` |

Three things nobody had instrumented: the frame is CROPPED before detection; confidence is `advanced_tracker._fill_conf_threshold` = 0.22, NOT the 0.3 in `FeetDetector.get_players_pos` that G298 used; and 640 is a LONG-SIDE budget, so the short side lands at 352 after letterbox. ARM P therefore follows the MEASURED route, and G298's ARM A described a SETTING, not the route.

## Ground truth, every denominator named
PRIMARY is the G303 spec's own step-2 rule: the CONSENSUS set from the PRE-EXISTING, UNMODIFIED `g296_merge_locators.py` at its committed `MATCH_RADIUS_PX = 60.0` (read, never moved), midpoint of each pair. Reproduced from master: **86 consensus points over 15 frames**, jaccard 0.4914, median pass-to-pass offset 23.968 px, p90 42.720 px, 45 A-only, 44 B-only. (`agreement()` reports 16 frames with points in both passes; one yields no pair inside 60 px, so the set spans 15.) SECONDARY denominators, recomputed here and matching the G296 merge memo: **pass-A-only 131**, **pass-B-only 130**. The 113-point ADJUDICATED set is NOT used -- it is not on master, its candidate REJECTED at `eba2dc34d` on the Q6 language rail (all other B/Q checks passed); the harness takes it via an optional `--ground-truth` if it lands.

## Arms -- one difference, and determinism
All arms run the UNEDITED `AdvancedFeetDetector` as the pipeline constructs it. The ONLY difference between P and R is `_infer_imgsz`: same weights, classes, conf, half, device, crop and decoded pixels. ARM P ran TWICE and the detection CSVs are **byte-identical: True**, checked before any recall arithmetic. R and M have ONE draw each; their repeatability is NOT VERIFIED. ARM M (1280) is a sensitivity arm, not the headline.

## Recall (one-to-one Hungarian, primary rule) and cost -- denominator 86 consensus points / 15 frames
| tol px | ARM P (route, 352x640) | ARM R (1920) | ARM M (1280) |
| ---: | --- | --- | --- |
| 25 | 51/86 = 0.5930 [0.4643, 0.7045] | 65/86 = 0.7558 [0.6190, 0.8617] | 66/86 = 0.7674 |
| 40 | 58/86 = 0.6744 [0.5494, 0.7778] | 70/86 = 0.8140 [0.6795, 0.9011] | 72/86 = 0.8372 |
| **50** | **60/86 = 0.6977 [0.5783, 0.8033]** | **73/86 = 0.8488 [0.7222, 0.9383]** | 74/86 = 0.8605 |
| 100 | 63/86 = 0.7326 [0.6049, 0.8452] | 76/86 = 0.8837 [0.7500, 0.9684] | 76/86 = 0.8837 |
| boxes / 24 frames (per frame) | 289 (12.04) | 1156 (48.17) | 757 (31.54) |
| boxes on the 15 scored frames | 210 | 1020 | 664 |
| median nearest px / precision LOWER BOUND @50 | 19.94 / 0.2857 | 16.01 / 0.0716 | 15.74 / 0.1114 |
| peak torch VRAM MiB / ms per call | 80.7 / 550.7 | 370.5 / 619.9 | 212.5 / 555.2 |

Against the SECONDARY denominators at 50 px: ARM P 60/131 pass-A-only and 60/130 pass-B-only; ARM R 73/131 and 73/130. CIs are 95% percentile bootstrap over FRAMES, 10000 draws, seed 20260907. The many-to-one NEAREST rule (G298-comparable) gives P 64, R 77, M 78 at 50 px. ARM R buys its gain by emitting **4.0x** the boxes while its precision lower bound falls 4.0x; ARM M equals or beats R at EVERY tolerance with 65% of R's boxes, so on this set the gain SATURATES below 1920. Timing is ONE draw and DESCRIPTIVE ONLY -- the spec declares timing out of scope, and the warm-up spread between P (550.7 ms) and its byte-identical repeat (291.1 ms) EXCEEDS the P-to-R difference, so these numbers cannot separate the arms and nothing here says a larger input is practical.

## Paired comparison, delta = ARM R minus ARM P (positive = R finds more)
| tol px | delta recall | 95% CI (paired, same frame resample) | McNemar lost/gained/discordant | nominal p |
| ---: | ---: | --- | --- | ---: |
| 25 | +0.1628 | [+0.0745, +0.2500] | 2 / 16 / 18 | 0.001312 |
| 40 | +0.1395 | [+0.0625, +0.2165] | 3 / 15 / 18 | 0.007538 |
| 50 | +0.1512 | [+0.0781, +0.2222] | 1 / 14 / 15 | 0.000977 |
| 100 | +0.1512 | [+0.0680, +0.2353] | 1 / 14 / 15 | 0.000977 |

McNemar is used because both arms observe the SAME points on the SAME frames, so the samples are DEPENDENT and an unpaired two-proportion test would be WRONG. All p are NOMINAL; NO multiplicity correction across the four tolerances or the two matching rules; points within a frame are not independent and no clustering adjustment is made.

## Against G298: SMALLER, and NOT a replication
At 100 px G298 measured 0.1748 -> 0.5105, delta +0.3357; here the same-tolerance delta is +0.1512 and ARM P's baseline is 0.7326 rather than 0.1748. The resolution effect on the clip-wide two-pass set is therefore **SMALLER**, which WEAKENS G298's headline as a general attribution and supports it being specific to its 15 frames inside 19599-23399 -- a span G278 measured friendlier than its own clip (0.836 vs 0.656, p = 0.0078). This compares two different frame sets, two locator sets, two denominators (86 consensus vs 143 single-locator), two matching rules (one-to-one vs nearest) and two route settings (conf 0.22 cropped vs conf 0.3 full-frame). It is NOT a replication and must not be called one. Resolution still matters; it matters LESS.

## The pose branch -- an unpredeclared observation, not a re-scored metric
Frame 0 carries 5 of the 86 consensus points and is served by the POSE model at a fixed 640 in EVERY arm. It scores **0/5 in all four arms**, so those points depress both arms equally and cannot contribute to the delta. No exclusion was pre-declared and no figure above is restated without them.

## ACCEPTANCE RULE, line by line
- metric -- PASS. Measured input shape verbatim; merge output (jaccard 0.4914, median 23.968, p90 42.720, consensus 86, A-only 45, B-only 44); both arms' exact settings with the single-difference design stated; ARM P determinism True; recall at 25/50/100 (plus 40) against the named consensus denominator with both secondaries; McNemar exact with nominal p and the no-correction statement; per-arm totals, per-frame counts and median nearest distance; and the SMALLER verdict against G298 with its not-a-replication caveat.
- before -- PASS. G298's attribution rested on 15 single-locator frames in one measurably friendly span, and the route's actual detector input had never been instrumented. Both are now measured, and the second falsifies the `imgsz=640 on 1920x1080` reading of the route.
- bar -- N/A by the spec's own words: NO pass bar. A gain was found and it is smaller than G298's; that is reported as plainly as the gain.
- n -- PASS, stated: 24 frames detected, 15 scored; 86 consensus points primary with 131 and 130 secondary; 3 arms plus 1 repeat; 4 tolerances; 1 clip; 1 draw per arm; 2 MODEL locators.
- must not move -- PASS. `g296_merge_locators.py` still reads `MATCH_RADIUS_PX = 60.0`; nothing under `src/`, `domains/`, `api/` or `kernel/` was edited; no default, threshold, filter or flag changed; `yolov8n.pt` never overwritten; nothing under `data/` written; `track_daemon` never signalled.

## Honest limitations
Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS, and both can be wrong in the same way; no human has checked these frames. G296b rated only 26/163 = 0.160 of its own player locations `confident`, and G291 measured two model raters at Cohen's kappa 0.283 on an easier task, so this is an approximately-positioned basis. The passes agree on only 86 of 131 and 130 eligible points, and the 60 px consensus radius is WIDER than the 25 px tolerance scored. A detector that finds a player the locators missed is scored WRONG here, which bounds every recall figure from above and below; the precision figures are LOWER BOUNDS for the same reason. ONE clip, one shot per frame, one draw per arm; 24 frames is clip-wide but thin. Recall is not precision. This row measures the route and two alternative input sizes and ADOPTS NONE.

## Evidence, tests, pod log
Harness `scripts/platformkit/tracking/g303_recall_vs_resolution.py` (300 lines). Prereg `g303_prereg_2026-09-07.md`, seal SHA-256 `86e2ccad77a8fc452d329d6026f21f5ac4c422240e7458fca439e64c0a23d1ce` over LF-normalized bytes above the seal line, committed ALONE at `8c223275e` before any distance was computed and re-verified by recomputation from that commit. Artifact `g303_artifact/`: `P.csv`, `P_repeat.csv`, `R.csv`, `M.csv`, `g303_detect.json` (step 0, per-frame JPEG SHA-256, probes, per-arm summaries), `g303_report.json` (every figure above), `per_frame_recall.csv` (the per-unit series behind every CI, Q9). Tests: `tests/platformkit/test_g303_recall.py` **6 passed**; `tests/platformkit/test_loc_rail_scope.py` **1 passed**. Pod log tail: `G303 detect done; P_repeat byte-identical=True` / `POD_RUN_DONE job=20260907183845_214575_4150 rc=0`. Probes recorded verbatim in `g303_detect.json`: `nvidia-smi` 4740 MiB used of 24576 at gate time (>= 8 GB free required), `dd conv=fsync` rc=0. `du -sm /workspace` returned empty under a 115 s timeout = **UNKNOWN**, never 0 and never a stop. No corpus source and neither bridge partial download was deleted.

## NOT VERIFIED
- Human correctness of any ground-truth point; every coordinate is model-located.
- That the consensus set is the complete on-court set; a player both passes missed, or both placed badly, cannot be recovered by an agreement procedure.
- Repeatability of ARM R and ARM M; only ARM P was run twice.
- Any recall figure against the 113-point adjudicated set; that set is not on master.
- Whether ARM R's extra 867 boxes are players or false positives; this row cannot tell them apart, and the precision figures are lower bounds, not a resolution of that question.
- Anything outside this one WNBA clip, and any end-to-end tracking, registration or harness consequence: this row ran SINGLE-FRAME DETECTION, not the tracking route.
