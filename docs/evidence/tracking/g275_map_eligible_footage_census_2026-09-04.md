# G275: Painted-court geometry census across one WNBA broadcast clip

## Verdict

**ACCEPT (measurement only): category (a) occurred in 118 / 180 sampled frames = 0.656. This is an upper bound on footage that could ever be calibrated.** Category (a) is necessary, not sufficient: it is the most footage that could ever be calibrated, not footage that will calibrate. This census does not say that any individual (a) frame has a valid map or will calibrate.

The named denominator is **180 sampled frames**, not seconds and not shots. The other purely visual category fractions are 11 / 180 = 0.061 for (b), 50 / 180 = 0.278 for (c), and 1 / 180 = 0.006 for (d). This is one clip, one broadcast, one arena, and one labeller.

## Categories and blind protocol

Every verdict used only these observable single-frame categories:

| Category | Observable verdict | Count / 180 | Fraction |
|---|---|---:|---:|
| (a) | Two or more distinct painted court lines visible and at least one painted-line intersection visible | 118 | 0.656 |
| (b) | Painted court surface visible, but fewer than two distinct lines or no visible intersection | 11 | 0.061 |
| (c) | No painted court surface visible | 50 | 0.278 |
| (d) | Cannot judge | 1 | 0.006 |

No label asks whether a frame is live, replay, or a particular camera. The complete randomized first-pass order and its blind-ID verdicts were committed in `7a49ae186d9faf1e25d99bfee29c3da09cdca85b`, before the source-frame mapping was opened: [mapping and sampling rule](g275_map_eligible_footage_census_artifact/blind_manifest.json), [first-pass blind verdicts](g275_map_eligible_footage_census_artifact/first_pass_labels.csv), [180 full-resolution blind JPEGs](g275_map_eligible_footage_census_artifact/blind_frames/), and [15 blind boards](g275_map_eligible_footage_census_artifact/blind_boards/).

This is a coarse categorical eye judgement, not the sub-pixel geometric measurement that G257 bounded at 20 px.

## Sampling

The read-only POD input was `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`: 2,931,985,407 bytes; SHA-256 `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678`; 1920x1080; 30 fps; duration 5,814.333333 seconds; `ffprobe` metadata frame count 174,430. It was verified before extraction.

The sample has 180 centred uniform positions, with nominal stride `174430 / 180 = 969.055555556` frames. The rule is `floor((2*i+1)*174430/(2*180))` for `i=0..179`; adjacent gaps are only 969 or 970 frames. Each JPEG was extracted by a separate `ffmpeg -ss <frame/30> -i VIDEO -frames:v 1` seek in `/workspace/wt/a6`; the clip was never decoded as one complete pass.

Chronological sampled indices:

```text
484,1453,2422,3391,4360,5329,6298,7267,8236,9206,10175,11144,12113,13082,14051,15020,15989,16958,17927,18896,19865,20834,21803,22772,23741,24710,25679,26649,27618,28587,29556,30525,31494,32463,33432,34401,35370,36339,37308,38277,39246,40215,41184,42153,43122,44092,45061,46030,46999,47968,48937,49906,50875,51844,52813,53782,54751,55720,56689,57658,58627,59596,60565,61535,62504,63473,64442,65411,66380,67349,68318,69287,70256,71225,72194,73163,74132,75101,76070,77039,78008,78978,79947,80916,81885,82854,83823,84792,85761,86730,87699,88668,89637,90606,91575,92544,93513,94482,95451,96421,97390,98359,99328,100297,101266,102235,103204,104173,105142,106111,107080,108049,109018,109987,110956,111925,112894,113864,114833,115802,116771,117740,118709,119678,120647,121616,122585,123554,124523,125492,126461,127430,128399,129368,130337,131307,132276,133245,134214,135183,136152,137121,138090,139059,140028,140997,141966,142935,143904,144873,145842,146811,147780,148750,149719,150688,151657,152626,153595,154564,155533,156502,157471,158440,159409,160378,161347,162316,163285,164254,165223,166193,167162,168131,169100,170069,171038,172007,172976,173945
```

## Fresh blind re-judge

After the first pass commit, 40 of the 180 frames were copied to a fresh blind ordering using seed `2750905`. The new mapping and verdicts are [re-judge manifest](g275_map_eligible_footage_census_artifact/rejudge/manifest.json), [re-judge labels](g275_map_eligible_footage_census_artifact/rejudge/labels.csv), [40 JPEGs](g275_map_eligible_footage_census_artifact/rejudge/frames/), and [four boards](g275_map_eligible_footage_census_artifact/rejudge/boards/). The blind-label agreement is **40 / 40 = 1.000**.

Rows are the committed first-pass category; columns are the fresh re-judge category.

| First pass / re-judge | a | b | c | d |
|---|---:|---:|---:|---:|
| a | 29 | 0 | 0 | 0 |
| b | 0 | 0 | 0 | 0 |
| c | 0 | 0 | 11 | 0 |
| d | 0 | 0 | 0 | 0 |

The selected re-judge subset happened not to include first-pass (b) or (d), so the perfect agreement directly checks 29 (a) and 11 (c) labels only; it does not establish repeatability for the two less frequent categories.

## Studied span and run structure

The previously studied source span 19599-23399 contains four sampled frames: 19865 (a), 20834 (a), 21803 (a), and 22772 (c). Its 3 / 4 category-(a) share is above the clip-wide 118 / 180 share, but it is only four sampled frames. It is not enough evidence to call the studied span unusually court-bearing or to say that the chain used the friendliest footage in the clip.

Category (a) is distributed in mixed runs rather than one long continuous block: 42 runs in chronological sampled order, with 13 singletons, 11 two-sample runs, seven three-sample runs, and a longest 11-sample run from source frame 12113 through 21803. This is a description of the sampled sequence only, not a shot inventory or a claim about unsampled cuts.

## Machine, code identity, and disk guard

The POD was used because it hosts the named full-resolution corpus read-only. Before work, Python processes under `/workspace/wt/a*` reduced to the distinct-worktree set `{ /workspace/wt/a17 }` (one lane, PID 3091578), below the measured two-worktree hold. No process was interrupted.

`df` was not used. The required pre-write `du -sm /workspace` was 40,083 MB. The required `dd if=/dev/zero of=/workspace/wt/a6/.g275_fsync_probe.bin bs=1M count=1 conv=fsync` passed; its 1,048,576-byte probe was removed, freeing 1,048,576 bytes. The `pod_run` scratch preflight then reported `/workspace` 40,086 MB and wrote and removed its 8,388,608-byte quota probe. The temporary remote transport archives were removed after verified retrieval, freeing 32,641,451 bytes. No corpus source, `baseball__npb_05.mp4.part`, or `football__football_m8UWuQoflJo.mp4.part` was deleted.

The POD-exercised sampler route was the initial sealed source `scripts/platformkit/tracking/g275_footage_census.py`, SHA-256 `7afcddd357459c271ee4098a94e0798091702efb748e66c226e105eced7992c6`. It only invokes `ffmpeg` seeks and OpenCV board assembly; no detector, tracker, calibration, or production route ran. The final committed evidence artifact is 51,522,629 bytes across 243 files.

## Contract self-check and NOT VERIFIED

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A2: all four fractions, the span subset, run summary, agreement, and confusion are reproducible by joining the committed mappings and CSV labels. A3/B7: the entire uniform 180-frame sample is retained, not a head slice. A4: 180 source-frame indices are unique. A5/B2-B6: no schema or reader field, lifecycle, deployment, source module, or moved module changed. A7: every evidence path linked above exists. A9 names the full source path, byte size, and resolution; A11 names the POD-exercised route hash. B1 keeps all sampled labels including the separate (d) row; B8 has no fitted geometry; B9 names the sampled-frame denominator; B10 changes no bar. A12 does not apply because no allowlisted file grew. Q does not apply to this tracking measurement.

**NOT VERIFIED:** whether any category-(a) frame has valid calibration geometry; calibration success, correctness, residual, or map repeatability; any detector, tracker, or shot count; other clips, broadcasts, arenas, sports, or amateur footage; a population rate; and re-judge repeatability for (b) and (d). Uniform frame sampling weights long views by runtime and is not a count of shots.
