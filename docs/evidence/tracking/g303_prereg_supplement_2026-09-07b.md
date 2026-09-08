# G303 preregistration SUPPLEMENT (fix pass 1b) -- sealed before any number is recomputed

Supplement to `g303_prereg_2026-09-07.md` (seal
`86e2ccad77a8fc452d329d6026f21f5ac4c422240e7458fca439e64c0a23d1ce`, committed ALONE at
`8c223275e`). It exists because the first candidate `e82b702fc` was REJECTED
(`G303_VERIFY_2026-09-07.md`) on four protocol counts and because G296 has since LANDED on
master at `ef3269572`, which supplies the adjudicated basis the G303 spec asks for. Every
clause of the sealed prereg that is not restated below still binds unchanged. The spec
amendment this implements is `G303_spec.md` VERSION 2026-09-07b, committed ALONE at
`2abfd06aa`. NO BAR IS MOVED; there is no pass bar in this row and none is introduced.

## 1. What is fixed, and why

- REJECT (2): the arms ran at the route's `conf = 0.22`, not the spec's registered `conf = 0.3`.
- REJECT (1): the secondary "denominators" divided the PRIMARY numerator by 131 and 130.
  That is not a measurement of anything and is withdrawn in full.
- REJECT (4): four tolerances were reported where three are registered.
- REJECT (3): the six mandated eye-check overlays were never rendered.
- The 113-point adjudicated set was not on master at first seal; it is now.

## 2. Bases, each with its own points, its own matching and its own denominator

Every basis is scored by the SAME rule (section 4) against the SAME detection CSVs. No
numerator is ever carried from one basis to another. Each recall figure prints its own
denominator and the name of its basis.

- PRIMARY -- ADJUDICATED 113. `docs/evidence/tracking/g296_ground_truth_2026-09-07.csv`,
  every row whose `source` is not `dropped`: 1 `agreed`, 28 `adjudicated_A`, 84
  `adjudicated_B` = 113 on-court points over 16 of the 24 frames. This is the G303 spec's
  intended set and the HEADLINE denominator.
- SECONDARY -- CONSENSUS 86. `g296_merge_locators.consensus()` at its committed, unmodified
  `MATCH_RADIUS_PX = 60.0`, midpoint of each greedy mutual-nearest pair: 86 points over 15
  frames. Carried forward so this pass is comparable with the rejected candidate.
- SECONDARY -- PASS A 131. `g296a_located_players_artifact/located_players.csv`, rows with
  `role = player_on_court`, `feet_visible = true` and both coordinates present. This is pass
  A's OWN eligible set, not a set difference; "pass-A-only" in the spec names the labels one
  pass located, and the count 131 reproduces the G296 merge memo.
- SECONDARY -- PASS B 130. Same filter on `g296b_located_players_artifact/located_players.csv`.

## 3. Arms -- five, and what separates them

All five construct the UNEDITED human-gated `AdvancedFeetDetector` and run it through its
own `get_players_pos`. `src/` is imported and run, NEVER edited; conf and imgsz are set on
the INSTANCE only.

| arm | imgsz | conf | role |
| --- | --- | --- | --- |
| P | route value measured in step 0 | 0.3 REGISTERED | the headline baseline |
| P_repeat | same as P | 0.3 | determinism check, byte-compared to P |
| R | 1920 | 0.3 | the single-difference comparison arm |
| M | 1280 | 0.3 | sensitivity only, never the headline |
| P22 | route value | the route's OWN `_fill_conf_threshold`, untouched | the route exactly as it runs |

The ONLY difference between P and R is `_infer_imgsz`. P22 exists solely to record the
spec-vs-route conflict the first pass found; it is REPORTED and is NEVER substituted for P,
and no P-vs-P22 comparison is treated as a resolution result.

## 4. Matching rule, tolerances, footpoint -- unchanged except for the tolerance set

Footpoint, one-to-one Hungarian primary rule and the many-to-one NEAREST secondary rule are
exactly as sealed in `g303_prereg_2026-09-07.md` section 4. TOLERANCES ARE THE THREE
REGISTERED VALUES: 25, 50 and 100 px in 1920x1080 pixels. 50 px is the headline. The 40 px
column the rejected candidate added is DROPPED, not relabelled.

## 5. Estimators fixed before recomputation

- recall(arm, basis, tol) = one-to-one matched points of that basis / that basis's own count.
- delta(tol) = recall(R) - recall(P) on the PRIMARY basis. Positive means R finds more.
- 95% CI: percentile bootstrap resampling the basis's own scored FRAMES with replacement,
  10000 draws, `numpy.random.default_rng(20260907)`; a delta uses the SAME resampled frame
  list for both arms, so the interval is paired.
- Paired test: McNemar two-sided EXACT conditional binomial on the per-point detected /
  not-detected indicator, P versus R, on the PRIMARY basis. Unpaired would be WRONG: both
  arms observe the same points on the same frames. All p are NOMINAL; NO multiplicity
  correction across the three tolerances, the four bases or the two matching rules; points
  within a frame are not independent and no clustering adjustment is made.
- precision LOWER BOUND = one-to-one matched / all detections the arm emitted on that basis's
  scored frames. A correct detection of a real person outside the basis counts against it.
- descriptive per arm: total detections, detections per frame, median nearest-detection
  distance, ms per frame and peak VRAM, ONE draw each, no practicality conclusion drawn.

## 6. Eye check, fixed now

Six frames at sample positions 0, 5, 9, 14, 18 and 23 of the 24 sorted frame indices --
`round(i * 23 / 5)` for i = 0..5, evenly spaced, no head slice, chosen before any overlay is
rendered. Each render carries the adjudicated points, the consensus points, and ARM P's and
ARM R's detection footpoints, from the SAME run whose CSVs are committed (B11). JPEG, at most
300 KB each, headless `cv2.imwrite`, committed with the memo under
`docs/evidence/tracking/g303_artifact/eyecheck/`.

## 7. Outcomes, declared now

No pass bar. A LARGE positive delta on the adjudicated basis STRENGTHENS G298's attribution
of the detector defect to input resolution; a SMALL or ABSENT delta WEAKENS it and means
G298's headline was specific to its 15-frame span. The second is the more important outcome
to report honestly and will be reported as plainly as the first. A conf-0.3 result that
differs materially from the conf-0.22 route is itself a reportable finding and changes no
production default.

## 8. Limitations, restated

Section 9 of the sealed prereg binds unchanged, and the adjudicated basis adds one more: the
adjudicator that produced the 113 points is a THIRD MODEL, so an accepted point is model
located and model adjudicated and is not human ground truth. Two model locators agreeing
measures REPRODUCIBILITY, never CORRECTNESS, and both can be wrong in the same way.

SEAL SHA-256 (LF-normalized bytes above this line):
aaf4751a1fb3d4cbc61e22ef5c23a1f8328ce0008de3e2a4296d161d3706c6aa
