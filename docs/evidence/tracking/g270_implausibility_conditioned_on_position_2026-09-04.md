# G270: Implausibility conditioned on projected position

## Verdict

**ACCEPT (measurement only): G267's retained detector-box records reproduce 4,090 / 29,973 = 0.136 strict-over-40-ft/s same-ID steps. Both-endpoints-inside-court is 2,507 / 23,783 = 0.105; one-inside/one-outside is 766 / 1,001 = 0.765; both-outside is 817 / 5,189 = 0.157.**

The raw 0.136 is not solely an off-court projection tail: 2,507 / 4,090 = 0.613 of strict-over-40 steps have both endpoints inside the declared rectangle. It is nevertheless strongly concentrated when a step crosses that boundary and at smaller image distances from the static published-map horizon.

**0.136** answers the full G267 detector-box / emitted-association-ID / projection question. **0.105** answers that same question conditional on both projected box feet inside the 50 x 94 ft rectangle. It is not a tracking-quality score for authenticated people: the denominator remains detector boxes, including officials, bench personnel, spectators, and duplicates. G225's 19 raw boxes for two visibly on-court people remains the warning against calling these boxes players; identity is unvalidated everywhere in this programme.

This is a conditioning choice, not a repair or improvement. No box was filtered from the retained population; every finite box remains produced and projected. A low in-court result would be necessary but never sufficient evidence of usable tracking, and 0.105 does not collapse relative to 0.136. No production filter, gate, threshold, tune, or source-tree change is proposed.

Denominator: one non-deterministic detector draw, one WNBA clip, one arena, one pre-cut shot, G233d's retained published map, source frames 19599--23399 inclusive (3,801 frames), 30,071 finite class-0 detector-box feet, 98 emitted association IDs, and 29,973 same-ID consecutive observation steps. These are not authenticated players.

## Frozen input and method

The only measurement input opened was G267's retained [measurement artifact](g267_court_space_physical_plausibility_artifact/g267_measurement.json), SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`. No detector call, video decode, relabelling, association change, court-model fit, or source-video reopen occurred. The inherited source identity is `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps. G270 checked its exact contiguous 19599--23399 span.

G267's unchanged analysis was first rerun on every retained finite record and returned 30,071 detector-box feet, 29,973 same-ID steps, and 4,090 strict-over-40 steps (0.136). A mismatch aborts the harness. An independent reload of G270's retained step records again yielded 29,973 total and 4,090 strict-over-40 steps; each partition family sums exactly to those totals.

Each original same-ID pair keeps G267's speed: court distance times 30 divided by actual source-frame gap. The exhaustive endpoint partition is the unchanged inclusive rectangle `0 <= x <= 50`, `0 <= y <= 94`: both inside, exactly one inside, or both outside. No step is excluded.

The horizon is `h31*x + h32*y + h33 = 0` from G267's unchanged published seed image-to-court homography. Both image-foot distances are retained. A step is banded by the smaller endpoint distance because either footpoint near the horizon can make that displacement poorly conditioned. Local ft/px is the image-to-court Jacobian singular-value pair at that nearer endpoint.

This is explicitly a **static published-map horizon** analysis. G267 retained the published seed H, not its per-frame propagated maps; G270 uses the retained H exactly and does not recreate absent maps by reopening the video. The horizon result assumes the map is right where it is least constrained and least tested. G257's map certification is only about 20 image px; this is conditioning, not map validation.

## Court-position partition

| Endpoint partition | Same-ID steps | Strict-over-40 ft/s steps (fraction) | p99 ft/s | Max ft/s |
|---|---:|---:|---:|---:|
| Both inside 50 x 94 ft court | 23,783 | 2,507 (0.105) | 417.774 | 1,368.623 |
| One inside, one outside | 1,001 | 766 (0.765) | 1,392.150 | 3,739.046 |
| Both outside | 5,189 | 817 (0.157) | 1,437.219 | 100,457.241 |
| All retained same-ID steps | 29,973 | 4,090 (0.136) | 700.118 | 100,457.241 |

The one-inside/one-outside group is the sharpest partition. The both-outside group contains the 100,457.241 ft/s maximum, consistent with unbounded projection. But the both-inside group still has 2,507 strict-over-40 steps, p99 417.774 ft/s, and a 1,368.623 ft/s maximum. Projection conditioning is a substantial contributor, not a complete causal explanation or authentication of in-court boxes.

## Horizon-distance partition

Bands use the smaller retained endpoint distance to the static horizon. `Median local ft/px` is the median singular-value range at that endpoint; `p99 max` is the p99 larger singular value. All figures are reported to three decimals.

| Minimum endpoint horizon distance | Steps | Strict-over-40 ft/s steps (fraction) | Median local ft/px min--max | p99 max ft/px |
|---|---:|---:|---:|---:|
| 0 to <1,200 px | 795 | 270 (0.340) | 0.036--0.115 | 0.142 |
| 1,200 to <1,400 px | 5,341 | 1,150 (0.215) | 0.031--0.081 | 0.108 |
| 1,400 to <1,600 px | 8,718 | 1,139 (0.131) | 0.027--0.066 | 0.079 |
| 1,600 to <1,800 px | 8,311 | 1,068 (0.129) | 0.024--0.049 | 0.064 |
| 1,800 px or more | 6,808 | 463 (0.068) | 0.020--0.045 | 0.050 |

The rate rises from 0.068 in the farthest band to 0.340 in the nearest, while median maximum local ft/px rises from 0.045 to 0.115. This is the expected shape for projection conditioning. It cannot attribute an individual step among detection error, wrong association, wrong person box, duplication, map error, or real motion.

## Machine, disk guard, artifact, and verification

The shared pod was used only through `/workspace/wt/a5` after an executable-and-CWD census, excluding this checker, its parent, and the census process, found `a17` and `a15` active then `a15` clear. No process was interrupted. The deployed `/workspace/nba-ai-system` tree and corpus were never written.

`df` was not used. Two foreground wrappers completed and removed their 8,388,608-byte `dd conv=fsync` probes at `/workspace` readings of 38,467 MB and 38,469 MB, but their local waits hit the 30-second terminal ceiling before shipping. The completed hidden wrapper removed its third 8,388,608-byte fsync probe and reported `du -sm /workspace` at 38,504 MB before scratch writes. After fetch, the exact scratch measurement JSON (17,378,995 bytes) and 43-byte pod log were removed, freeing 17,379,038 bytes. Known temporary bytes freed total **42,544,862**: three probes plus those outputs. No corpus source or either abandoned bridge partial was deleted.

The retained [G270 measurement artifact](g270_implausibility_conditioned_on_position_artifact/g270_measurement.json) is 17,378,995 bytes, SHA-256 `99407091fc43e59dcdcc3a1449e83d7e0e4702e2dd34a7b41c51b69a59f3fd80`. It records all steps, endpoint court flags, both horizon distances, selected Jacobian scales, and summaries. Route SHA-256: G270 `fa5a75fe2fad224c36e53dd9329e7ac72887e09324a8bc15c55c2b2aa9c04606`; G267 analysis `85f0fddfc0eb1d1845605052103711890b98f930392833971e4a6a308cffe1ac`.

```
python -m pytest scripts/platformkit/tracking/test_g270_implausibility_conditioned_on_position.py -q -p no:cacheprovider
2 passed in 1.99s
```

Contract self-check: A7 paths exist; A9 names the opened artifact and inherited source path, bytes, and resolution; A11 records route hashes. B1 retains every finite detector-box step and names the structural pairing; B2--B6 alter no schema, lifecycle, deployment, production module, or module location; B7 uses the complete span; B8 uses no fit residual; B9 names box, ID, and step denominators; B10 keeps G267's strict-over-40 reference. Q does not apply. The 176-line new harness is below the 300-line rail and grows no allowlisted file, so A12 needs no update.

## NOT VERIFIED

- Another clip, shot, arena, detector draw, map, or sport; this is one draw only.
- Person precision/recall, on-court status, duplicate status, or identity correctness. An in-court projection can still be the wrong person.
- A causal allocation of any step among detection, association, conditioning, map error, or real motion.
- Per-frame propagated-map horizons, map correctness near the horizon, or a calibration accuracy decomposition.
- A production change, filter, gate, threshold, tune, readiness claim, or a claim that either conditional fraction establishes good tracking.
