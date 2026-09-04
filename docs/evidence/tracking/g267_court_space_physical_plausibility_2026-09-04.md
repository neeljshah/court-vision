# G267: Court-space physical plausibility through the validated G233d map

## Verdict

**ACCEPT (measurement only): 4,090 / 29,973 = 0.136 same-ID court-space steps exceed 40 ft/s.** The p99 is 700.118 ft/s and the maximum is 100,457.241 ft/s. Those are objective error signals in a basketball tracking chain, not athletes. This is the requested end-to-end quality measurement of detection, association, and projection together; it needs no eye gate and proposes no production change, gate, or threshold.

Denominator: one non-deterministic draw on one WNBA clip, one published G233d map, one arena and camera shot, source frames 19599--23399 inclusive (3,801 frames), 30,071 finite class-0 detector-box feet, 98 emitted association IDs, and 29,973 consecutive same-ID observation steps. These are **detector boxes / associated observations, not authenticated players**. Officials, bench personnel, spectators, and duplicate boxes can be in the population; G225 directly showed 19 raw boxes with only two visibly on-court people in one frame.

This measurement follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It did not change a source, label, court model, threshold, coordinate contract, `src/`, `domains/`, daemon, keeper, corpus, or bridge partial.

## Frozen map, source, and one-shot span

The source opened through the scratch tree's read-only data link resolved to `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`: 2,931,985,407 bytes, 1920x1080, 174,430 declared frames at 30 fps. No complete decode was written. G233d's published image-to-WNBA-court map was used unchanged from seed frame 19599, with the same fixed paint inputs and direct-to-seed propagation route; it was not re-fit or relabelled.

```text
[[0.050071754999888064, 0.01225404716365722, 2.3351407383547964],
 [-0.0047586809476217904, 0.1153980129798286, -44.493666860263815],
 [3.054485397744623e-05, 0.0011147252900901028, 1.0]]
```

G241b reproduced G233d's first 1,200 direct geometry records exactly and located its first shot-cut candidate at about distance 3,876. G267 therefore uses distance 0 through 3,800 only: source frames 19599 through 23399. The end is 76 frames (2.533 s) before that first candidate, so the entire declared span is inside G241b's pre-cut camera shot. All 3,801 frames retained a finite direct-to-seed map. This is reliance on G241b's shot inventory, not a new eye check.

Route SHA-256 values recorded by the run: G267 harness `5c6e24ad34dd30e2846cc5d596de2e2ad01a3f77258de9f0e06d0727eb5c72f2`; G196 court model `76ddb96f37982f24fd1a606d6b61b840863ffc973e94c0a0cc65342981b14d53`; G215 direct propagation `b3eb085fa0b57af006af19ff29f1e5d2f2bf5b61addc649940b998cc52b6442a`; detector `src/tracking/player_detection.py` `532389342b93e259e01f2d177ea34ccb1f52dc1c4b9b7f62aed2bf07c7df785a`; association `domains/basketball/tracking/adapter.py` `1ecf483df26b19c44d1fa25297caed845e5952fbfdd9b704f95a6125f4366c15`.

## G252 pixel error in local court feet

G252's 5 px median and 19 px p90 are image-space offsets. A fixed px-to-ft factor would be false here. For each named court point, the table gives the two singular values of the local image-to-court Jacobian: a one-pixel shift can map anywhere in that directional range. The 5 px and 19 px columns are therefore ranges, not a claim that either G252 offset has one known direction.

`Near` and `far` sideline are camera-relative on this seed: the near-side point is lower in the image. `x=0` projects just beyond the left image edge and mid-court projects below the 1080-pixel frame; those two rows are mathematically local homography extrapolations, not directly observed G252 line locations.

| Court location | Court ft `(x,y)` | Projected image px | Local ft / px, min--max direction | 5 px error, ft min--max | 19 px error, ft min--max |
|---|---|---|---:|---:|---:|
| Near sideline (`x=50`) | `(50,19)` | `(1670.283, 768.549)` | 0.021--0.056 | 0.106--0.281 | 0.403--1.068 |
| Far sideline (`x=0`) | `(0,19)` | `(-208.665, 662.076)` | 0.029--0.055 | 0.145--0.274 | 0.552--1.042 |
| Near-baseline midpoint | `(25,0)` | `(589.450, 409.874)` | 0.033--0.079 | 0.163--0.397 | 0.618--1.508 |
| Mid-court | `(25,47)` | `(949.044, 1545.447)` | 0.016--0.025 | 0.079--0.126 | 0.300--0.478 |

Thus even the stated G252 image error is position- and direction-dependent in court feet. It conditions this measurement but does not identify which observed velocity errors arise from calibration rather than detection or association.

## Court-space speed result

Each class-0 box's bottom-centre was direct-projected through the finite G233d map for that frame. The unchanged `BasketballAdapter` nearest-centre association supplied an emitted ID. For each ID, consecutive retained observations use actual source-frame gap: `speed = court_distance_ft * 30 / frame_gap`. No speed row was silently excluded: every finite observation is retained; the only potential exclusion would be a nonpositive within-ID frame gap, of which there were zero.

| Distribution or reference | Result |
|---|---:|
| Same-ID steps | 29,973 |
| Median / p90 / p99 / maximum ft/s | 7.762 / 65.571 / 700.118 / 100,457.241 |
| Above 25 ft/s | 5,941 (0.198) |
| Above 30 ft/s | 5,128 (0.171) |
| Above 33 ft/s | 4,765 (0.159) |
| Above 40 ft/s: headline implausible fraction | 4,090 (0.136) |

The 25 ft/s basketball-play reference is conservative: a systematic review reports NBA average top speed of 8.09 m/s, or about 26.5 ft/s, while noting measurement and competition differences ([PLOS One review](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0229212)). The 30 and 33 ft/s rows are deliberately generous elite-sprint comparisons, not basketball acceptance bars. For scale, World Athletics reports Usain Bolt's 12.42 m/s (40.75 ft/s) peak in his 9.58-second world-record 100 m; 40 ft/s is therefore not a universal human impossibility, but it is an error signal for this WNBA in-play, one-frame broadcast projection context ([World Athletics](https://worldathletics.org/heritage/news/bob-hayes-usa-100-yards-world-record-1963)). None of these references is proposed as a production threshold.

## What the implausible steps coincide with -- and what they do not establish

For each current box, G267 retained the ID of the nearest prior-frame box in image-footpoint space. `ID changed` below means that nearest predecessor has a different emitted association ID; it is an association-discontinuity diagnostic, not proof of a real identity swap. `Large pixel jump` was fixed before the draw as more than 100 px between same-ID bottom-centres in a step, the obvious-displacement rung previously used by G257; it is diagnostic only.

| Among 4,090 over-40-ft/s steps | Count | Fraction of implausible steps |
|---|---:|---:|
| Nearest-prior emitted ID changed | 1,965 | 0.480 |
| Same-ID pixel jump >100 px | 2,206 | 0.539 |
| Both diagnostics | 1,804 | 0.441 |
| Either diagnostic | 2,367 | 0.579 |
| Neither diagnostic | 1,723 | 0.421 |

For context, 3,460 and 2,901 implausible steps exceed 20 and 40 px respectively; these are reported as counts only, not bars. The 1,723 neither-diagnostic steps are not locally attributable even at this descriptive level. More importantly, **none** of the categories establishes a cause: an association discontinuity can be a detector change, a real crossing, or an ID switch; a large pixel jump can arise from detector localisation, perspective, or an association error; and neither diagnostic tests the correctness of a track identity or the map. The 2,367 coincident steps cannot be partitioned into one cause without evidence that does not exist.

## Cheap sanity distributions

All 30,071 finite class-0 box feet remain in the denominator. 24,354 are inside the declared 94x50-ft rectangle: **0.810** for this one detector draw. This is necessary but not sufficient evidence of usable tracking; it says neither that boxes are on-court people nor that emitted IDs are correct.

Same-frame distances use every unordered pair of finite detector-box feet, again not authenticated player pairs: 121,926 pairs. Their minimum / p01 / p10 / median / p90 / p99 / maximum in feet is **0.000 / 2.237 / 7.849 / 21.929 / 40.317 / 62.332 / 3269.030**. There are 406 pairs below 1 ft and **two exactly coincident pairs (<=0.01 ft)**. Two distinct humans cannot share one exact court footpoint, so those two are physically impossible coincidences as observations; the data cannot distinguish duplicate detections from a projection or association failure. The enormous upper tail also reflects this deliberately unfiltered detector-box population, including off-court people and projected-outside positions.

## Machine, disk guard, artifact, and verification

The shared pod was used because its read-only full-resolution source and GPU are there. Before dispatch, an executable-and-argument census excluded this checker, its parent, and the G267 launcher ancestry. It found one other scratch lane (`a17`) and no G266 process; no process was interrupted. This was the permitted second lane.

`df` was not used. `du -sm /workspace` was 36,920 MB before the binding 1,048,576-byte `dd conv=fsync` probe and 36,920 MB after its removal. The scratch launcher also passed and removed its 8,388,608-byte fsync probe, reporting `/workspace` at 36,923 MB. After fetch, only G267's scratch measurement JSON (12,052,299 bytes) and its log (361,777 bytes) were removed, freeing 12,414,076 bytes. Known temporary bytes freed total **21,851,260**. No corpus source or either abandoned bridge partial was deleted.

The retained [measurement artifact](g267_court_space_physical_plausibility_artifact/g267_measurement.json) is 12,052,299 bytes, SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`. It retains every frame, direct-map eligibility result, class-0 box footpoint, projection, emitted ID, nearest-prior ID diagnostic, and the complete over-40-ft/s step set. A separate independent reload/recomputation from those raw records reproduced every headline count and distribution in this memo.

```text
python -m pytest scripts/platformkit/tracking/test_g267_court_space_physical_plausibility.py -q -p no:cacheprovider
2 passed in 4.80s
```

Contract self-check: A7 artifact exists; A9 names the exact input path, bytes, and resolution; A11 records all exercised route hashes. B1 retains every finite projected box and names the only structural speed-pair condition; B2--B6 alter no schema, lifecycle, deployment, production module, or module location; B7 uses the complete pre-cut span, not a head slice; B8 uses no self-fit residual as evidence; B9 names box, association-ID, step, and pair denominators; B10 moves no bar. Q does not apply. The new 181-line harness and 24-line test do not grow an allowlisted file, so A12 requires no rail update.

## NOT VERIFIED

- Another clip, seed, arena, camera shot, sport, or a second detector draw. G241 found detector outputs non-deterministic, so every count here is one draw.
- A ground-truth court map, automatic calibration, or a calibration-error decomposition. G257's roughly 20-px eye instrument limit and G252's 5/19-px conditional image offsets remain limitations inherited by this measurement.
- Person precision/recall, whether a box is on court, true identity, or association accuracy. Identity is unvalidated anywhere in this programme.
- Causal attribution of any implausible step to a detector jump, ID swap, projection error, or a real movement. A plausible distribution would also be necessary, never sufficient, evidence of correct tracking.
- A production gate, threshold, tuning change, or readiness claim.
