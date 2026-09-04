# G271: On-court concentration and image displacement of G267 implausible steps

## Verdict

**ACCEPT (measurement only): the retained detector-box result is distributed rather than concentrated in a few emitted IDs, and its on-court impossible steps contain both large image moves and small image moves.** In the both-endpoints-on-court partition, the worst five of 98 emitted IDs account for 521 / 2,507 = **0.208** of strict-over-40-ft/s steps and the worst ten account for 889 / 2,507 = **0.355**. Nineteen IDs have zero on-court impossible steps, leaving 79 with at least one. This is not a result in which a few IDs supply most of the retained on-court defect. It is a descriptive distribution across emitted detector-box IDs, not evidence that any individual track is correct or that a concentrated ID would be spurious.

The paired image/court measurement splits the 2,507 on-court impossible steps into 1,454 / 2,507 = **0.580** with image bottom-centre displacement above 83 px (descriptive box-jump bin), 218 / 2,507 = **0.087** below 17 px (descriptive projection-amplified bin), and 835 / 2,507 = **0.333** from 17 through 83 px inclusive (indeterminate). The large-move group is the largest observed descriptive bin, but the small-move group is nonzero. This does not allocate a single cause: detection motion, association, wrong-person/duplicate boxes, map error, and real movement remain unresolved.

Denominator: one non-deterministic detector draw, one WNBA clip, one arena, one pre-cut camera shot, G233d's retained published map, source frames 19599--23399 inclusive (3,801 frames), 30,071 retained finite class-0 detector-box feet, 98 emitted association IDs, 29,973 all-position same-ID consecutive steps, and the **23,783 both-endpoints-on-court same-ID steps** used for every G271 headline. These are detector boxes and associated observations, **not authenticated players**: officials, bench personnel, spectators, and duplicates can be in this population.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It proposes no production change, filter, gate, threshold, tune, reassociation, source-tree change, or corpus operation.

## Reproduced baselines and frozen input

The sole opened measurement input was the current retained [G267 measurement artifact](g267_court_space_physical_plausibility_artifact/g267_measurement.json), SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`. No detector call, video decode, relabelling, association change, court-model fit, source-video reopen, or reassociation occurred. It declares the inherited source as `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps, span 19599--23399.

Before scoring any G271 row, G267's complete retained analysis was rerun and exactly reproduced 4,090 / 29,973 = **0.136** strict-over-40-ft/s steps. The unchanged both-inside condition then exactly reproduced G270's 2,507 / 23,783 = **0.105**. All 23,783 G271 records also match the current G270 artifact's same-ID frame keys and speeds byte-for-number at the comparison precision; no partition row was excluded.

The retained [G271 measurement artifact](g271_implausibility_concentration_and_image_displacement_artifact/g271_measurement.json) is 7,882,569 bytes, SHA-256 `a8fcb7d7866dbeafdb00bb79e82481e7158e4c5cb9beb4c70497eb94923edc92`. It retains every on-court same-ID step with its emitted ID, frames, actual frame gap, court-space speed, image bottom-centre displacement, and descriptive movement bin, plus all 98 per-ID rows.

## Per-emitted-ID concentration

This table is restricted to the 23,783 both-endpoints-on-court steps. `n/a` means an emitted ID has no on-court same-ID step, not that it was excluded. IDs are emitted association labels, not validated identities.

| Emitted ID | On-court same-ID steps | Over-40 steps | Fraction |
|---:|---:|---:|---:|
| 1 | 750 | 73 | 0.097 |
| 2 | 964 | 73 | 0.076 |
| 3 | 59 | 0 | 0.000 |
| 4 | 335 | 22 | 0.066 |
| 5 | 111 | 25 | 0.225 |
| 6 | 148 | 19 | 0.128 |
| 7 | 949 | 102 | 0.107 |
| 8 | 395 | 36 | 0.091 |
| 9 | 7 | 1 | 0.143 |
| 10 | 94 | 10 | 0.106 |
| 11 | 102 | 10 | 0.098 |
| 12 | 0 | 0 | n/a |
| 13 | 76 | 9 | 0.118 |
| 14 | 218 | 38 | 0.174 |
| 15 | 1386 | 106 | 0.076 |
| 16 | 242 | 34 | 0.140 |
| 17 | 187 | 14 | 0.075 |
| 18 | 581 | 46 | 0.079 |
| 19 | 1 | 0 | 0.000 |
| 20 | 572 | 74 | 0.129 |
| 21 | 0 | 0 | n/a |
| 22 | 478 | 26 | 0.054 |
| 23 | 68 | 14 | 0.206 |
| 24 | 627 | 64 | 0.102 |
| 25 | 1100 | 51 | 0.046 |
| 26 | 74 | 11 | 0.149 |
| 27 | 6 | 0 | 0.000 |
| 28 | 9 | 0 | 0.000 |
| 29 | 224 | 31 | 0.138 |
| 30 | 25 | 5 | 0.200 |
| 31 | 559 | 49 | 0.088 |
| 32 | 1023 | 74 | 0.072 |
| 33 | 826 | 74 | 0.090 |
| 34 | 542 | 58 | 0.107 |
| 35 | 462 | 35 | 0.076 |
| 36 | 176 | 14 | 0.080 |
| 37 | 382 | 42 | 0.110 |
| 38 | 103 | 1 | 0.010 |
| 39 | 83 | 6 | 0.072 |
| 40 | 273 | 18 | 0.066 |
| 41 | 270 | 21 | 0.078 |
| 42 | 1320 | 111 | 0.084 |
| 43 | 1 | 1 | 1.000 |
| 44 | 503 | 56 | 0.111 |
| 45 | 892 | 57 | 0.064 |
| 46 | 327 | 25 | 0.076 |
| 47 | 603 | 48 | 0.080 |
| 48 | 324 | 25 | 0.077 |
| 49 | 492 | 50 | 0.102 |
| 50 | 0 | 0 | n/a |
| 51 | 5 | 0 | 0.000 |
| 52 | 22 | 1 | 0.045 |
| 53 | 43 | 3 | 0.070 |
| 54 | 47 | 8 | 0.170 |
| 55 | 546 | 72 | 0.132 |
| 56 | 191 | 25 | 0.131 |
| 57 | 296 | 51 | 0.172 |
| 58 | 2 | 1 | 0.500 |
| 59 | 12 | 1 | 0.083 |
| 60 | 30 | 9 | 0.300 |
| 61 | 293 | 38 | 0.130 |
| 62 | 151 | 3 | 0.020 |
| 63 | 249 | 39 | 0.157 |
| 64 | 351 | 102 | 0.291 |
| 65 | 22 | 1 | 0.045 |
| 66 | 114 | 8 | 0.070 |
| 67 | 98 | 8 | 0.082 |
| 68 | 338 | 68 | 0.201 |
| 69 | 347 | 59 | 0.170 |
| 70 | 120 | 16 | 0.133 |
| 71 | 80 | 20 | 0.250 |
| 72 | 49 | 2 | 0.041 |
| 73 | 3 | 0 | 0.000 |
| 74 | 48 | 15 | 0.313 |
| 75 | 1 | 1 | 1.000 |
| 76 | 0 | 0 | n/a |
| 77 | 21 | 2 | 0.095 |
| 78 | 42 | 18 | 0.429 |
| 79 | 0 | 0 | n/a |
| 80 | 214 | 41 | 0.192 |
| 81 | 130 | 70 | 0.538 |
| 82 | 14 | 2 | 0.143 |
| 83 | 376 | 100 | 0.266 |
| 84 | 58 | 11 | 0.190 |
| 85 | 49 | 20 | 0.408 |
| 86 | 51 | 18 | 0.353 |
| 87 | 15 | 9 | 0.600 |
| 88 | 4 | 0 | 0.000 |
| 89 | 91 | 2 | 0.022 |
| 90 | 0 | 0 | n/a |
| 91 | 0 | 0 | n/a |
| 92 | 13 | 2 | 0.154 |
| 93 | 87 | 0 | 0.000 |
| 94 | 99 | 0 | 0.000 |
| 95 | 84 | 2 | 0.024 |
| 96 | 1 | 0 | 0.000 |
| 97 | 26 | 0 | 0.000 |
| 98 | 1 | 0 | 0.000 |

The five largest impossible-step contributors are IDs 42, 15, 7, 64, and 83 (111, 106, 102, 102, and 100). The ten largest add IDs 20, 32, 33, 1, and 2 (74, 74, 74, 73, and 73). They do not dominate the 2,507-step denominator.

### Track length against impossible fraction

Across the 91 IDs with at least one on-court same-ID step, Spearman correlation of on-court step count with that ID's impossible-step fraction is **0.014**. The equal-ID-count length groups are below. The shortest group has the highest aggregate rate, but the groups are not monotone and the rank association is near zero; short tracks are therefore not uniformly worse in this retained partition.

| Length-rank quartile | IDs | On-court steps | Over-40 steps | Fraction | Per-ID step-count range |
|---:|---:|---:|---:|---:|---:|
| 1 | 23 | 283 | 54 | 0.191 | 1--42 |
| 2 | 23 | 1768 | 203 | 0.115 | 43--114 |
| 3 | 22 | 5404 | 773 | 0.143 | 120--351 |
| 4 | 23 | 16328 | 1477 | 0.090 | 376--1386 |

## Joint image-displacement and court-speed result

Every row in the retained G271 artifact contains its paired image bottom-centre displacement and court-space speed; the following are paired-set summaries, not an independence claim. Image displacement and court speed are related by the map under test. The Spearman values quantify that relationship rather than supplying an additional causal signal.

| Both-endpoints-on-court step class | Paired steps | Image px median / p90 / max | Court ft/s median / p90 / max | Paired image-px vs speed Spearman |
|---|---:|---:|---:|---:|
| Plausible (at most 40 ft/s) | 21276 | 5.408 / 21.905 / 890.612 | 5.976 / 20.927 / 39.990 | 0.884 |
| Impossible (strictly over 40 ft/s) | 2507 | 119.097 / 472.039 / 1619.858 | 92.868 / 407.229 / 1368.623 | 0.640 |

The same paired population cross-tabulated by speed class and the indicative sampled-Jacobian image ranges is:

| Court-speed class | Below 17 px | 17--83 px inclusive | Above 83 px | Total |
|---|---:|---:|---:|---:|
| Plausible (at most 40 ft/s) | 17991 | 2997 | 288 | 21276 |
| Impossible (strictly over 40 ft/s) | 218 | 835 | 1454 | 2507 |

There are **218** on-court impossible steps below 17 px. G267's four sampled Jacobian locations imply that a 40-ft/s one-frame step needs roughly 17--83 image px; therefore the three descriptive bins are named as follows: below 17 px is projection-amplified, above 83 px is box-jump, and the intervening range is indeterminate. The 17--83 px span is indicative, not a production threshold: G257 certifies the map only to about 20 image px and the Jacobian was sampled at four court points.

## Machine, disk guard, artifact, and verification

The pod was used only through `/workspace/wt/a5`, after the required executable-and-CWD census excluded the census process and its parent ancestry. It found one other lane, `a15`, so this was the permitted second lane; no process was interrupted. The deployed `/workspace/nba-ai-system` tree and corpus were never written.

`df` was not used. The binding explicit 8,388,608-byte `dd conv=fsync` preflight passed and removed its probe at `du -sm /workspace` readings of 38,999 MB before and after. The three G271 measurement attempts each ran and removed an 8,388,608-byte `dd conv=fsync` probe before any artifact write; the two setup-only attempts reached 39,001 MB and did not score, and the completed measurement recorded 39,015 MB. The successful wrapper's own removed 8,388,608-byte preflight recorded 39,014 MB. After fetch, only the exact pod scratch G271 measurement JSON and its three G271 logs were removed: 7,883,085 bytes. Known temporary bytes freed are at least **49,826,741** (the explicit first probe, three G271 fsync probes, the successful wrapper preflight, and those exact scratch outputs); local runner diagnostics added and removed 616 bytes. No corpus source or either abandoned bridge partial was deleted.

Route SHA-256: G271 `5ffedffcfc250e15ca7ca80c19c3c7dd95e11de387110a46b9fc137c959e8436`; G267 analysis `85f0fddfc0eb1d1845605052103711890b98f930392833971e4a6a308cffe1ac`; G270 position conditioning `fa5a75fe2fad224c36e53dd9329e7ac72887e09324a8bc15c55c2b2aa9c04606`.

```
python -m pytest scripts/platformkit/tracking/test_g271_implausibility_concentration_and_image_displacement.py -q -p no:cacheprovider
2 passed in 1.78s
```

Contract self-check: A7 names existing artifacts; A9 names the exact inherited source path, bytes, and resolution; A11 records every exercised route hash. B1 retains every finite G267 box through baseline reproduction and every both-inside structural same-ID step through the G271 table/artifact; B2--B6 change no schema, lifecycle, deployment, production module, or module location; B7 uses G267's complete retained pre-cut span; B8 uses no fit residual; B9 names box, ID, and step denominators; B10 keeps G267's strict-over-40 reference. Q does not apply. The new 188-line harness and 21-line focused test do not grow an allowlisted file, so A12 requires no rail update.

## NOT VERIFIED

- Another clip, shot, arena, map, sport, or detector draw. This is one draw of a non-deterministic detector.
- Person precision/recall, on-court status, duplicate status, or identity correctness. The detector-box population is not authenticated people.
- That a concentrated or non-concentrated emitted ID is correct, spurious, a duplicate, a crowd/bench box, or an association failure.
- A causal allocation among detector motion, association, projection conditioning, map error, wrong-person boxes, duplicates, or real movement. The descriptive image bins do not establish a cause.
- Map accuracy outside G257's roughly 20-px certification or Jacobian behavior beyond G267's four sampled court points.
- A production filter, threshold, gate, reassociation, tuning choice, or readiness claim.
