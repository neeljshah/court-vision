RATER-CONFOUNDED: This row was labelled and analysed by GPT-5 Codex, not gpt-5.6-terra; every comparison with G287 is rater-confounded.

# G292 - Content at both ends of large image jumps

## Verdict

MEASURED, measurement only, no pass bar and no production proposal. The frozen G289 population is exactly 1,897 detector-box same-ID steps that are both implausible and above 150 image pixels, from 4,090 implausible / 29,973 eligible consecutive-observation steps and 30,071 retained detector-box observations. One seeded equal-time-bin draw selected 36 steps and 72 endpoint crops. The point-level blind measurement is coarse categorical judgement at the centre cross, not a geometric measurement.

**Answer: with 29/72 = 0.403 large-jump endpoints on a player versus G287's 32/72 = 0.444 randomly chosen detector-box observations (unpaired z = -0.506, nominal two-sided p = 0.613), this rater-confounded 36-step comparison is too noisy to call; it neither relocates the anomaly onto DETECTION nor supports the identity-contradicting alternative.**

The raw direction is lower player content at jump endpoints, but that is not a statistically resolved result. Therefore this row does not claim that large jumps are between players, does not contradict G281's 0.935 identity purity, and does not establish a detection mechanism either.

## Frozen population and comparable-draw check

I re-derived the population directly from the landed [G289 steps CSV](g289_implausible_step_decomposition_artifact/steps.csv), 6,336,759 bytes, SHA-256 `180e5b2bc8d7adbcebfd19dcb8128a8e9a872aa839c32d96e9f68e6a62bb24a0`, by selecting `implausible == True` and `image_displacement_px > 150`. The result is **1,897**, exactly G289's reported count. Any different result would have stopped this row.

The G273/G287 baseline is comparable at the crop-selection level. I checked the current G267 retained artifact that G289 names, [g267_measurement.json](g267_court_space_physical_plausibility_artifact/g267_measurement.json), 12,052,299 bytes, SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`, through G273's committed `records -> select_evenly -> blind_order -> unblind_map` route. Its recreated map SHA-256 is `2851f20e00b4416459f546fedca62ab714dfd7862d74409d8d254a883f172294`, exactly equal to G273's committed 72-crop map SHA. The executable receipt is [same_draw_check.json](g292_jump_endpoint_content_artifact/same_draw_check.json). Thus G273's fixed 72 crop selection regenerates from the retained-record source used by G289; this is not a cross-draw comparison. The older G273 memo's byte/hash annotation differs, so this statement is deliberately limited to the exact reproducible 72-crop selection rather than asserting a byte-identical historical JSON file.

The 1,897 eligible steps cover before frames 19605--23389 and 83 emitted IDs. The seeded sample (`29220260904`) takes one uniformly random eligible step in each of 36 equal-width before-frame bins, with no selection on track ID, location, speed, or condition beyond the frozen G289 filter. Its 36 selected steps cover before frames 19670--23299, after frames 19671--23300, all 36 bins, and 24 emitted IDs. The complete selected-step receipt is [selection_metadata.json](g292_jump_endpoint_content_artifact/selection_metadata.json).

## Render, gate, and blind seal

The only decoded source was `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps, opened only in pod scratch `/workspace/wt/a6`; the deployed tree was never written. Every endpoint crop is a 512x640 native-pixel crop centred on the recorded footpoint, padded at boundaries, JPEG quality 88, with G273's same red 19-pixel cross (thickness 2, antialiased) and red radius-8 circle (thickness 2). No box, ID, frame, endpoint role, or pairing was drawn. This matches G273's documented geometry and render implementation. The 72 exact local inputs, dimensions, sizes, and hashes are in [input_manifest.csv](g292_jump_endpoint_content_artifact/input_manifest.csv).

The operational CPU/decode gate was, verbatim:

```text
G292_WORKSPACE_DU_MB=UNKNOWN_EMPTY_OR_TIMED_OUT
G292_CPU_LOAD15=97.88
G292_CPU_NPROC=256
G292_CPU_LOAD15_BELOW_NPROC=TRUE
G292_FSYNC_PROBE=PASSED_AND_REMOVED_BYTES=8388608
G292_CROP_BYTES=3571624
```

The `du -sm /workspace` result was unknown after its bounded network walk and was never interpreted as zero or used to stop the row. The only stopping disk condition was a failed `dd conv=fsync` probe; it passed. No GPU gate, lane-count gate, nvidia-smi check, process interruption, corpus-source deletion, or bridge-partial deletion occurred. Pod route receipts are [pod_gate.txt](g292_jump_endpoint_content_artifact/pod_gate.txt) and [pod_route_sha256.txt](g292_jump_endpoint_content_artifact/pod_route_sha256.txt). The exercised pod harness SHA-256 was `745bb1650edd3e18fa7c9b87c9ca6846e48eb13e7cc470071dfeecd81666fcf1`; its shell renderer was `8de5cf4ae0d0d3296519a0a3e9ca12434af3067d89c0d55b76fc3161947e9e81`.

Both endpoints were pooled and shuffled with blind seed `29220904`; the presentation order exposed only `blind_001.jpg` through `blind_072.jpg`. All categories and mandatory free text were committed in `87b8eb99c` before fetching or opening the pairing map. The sealed map commitment is `4cd29ff39bdf41b8815a6989ae094e87dfb87539ccaeadcac4ad4410f795a498` in [blind_order_commitment.json](g292_jump_endpoint_content_artifact/blind_order_commitment.json). The sealed order, 72 verdicts, and 72 crops are [blind_presentation_order.csv](g292_jump_endpoint_content_artifact/blind_presentation_order.csv), [blind_verdicts.csv](g292_jump_endpoint_content_artifact/blind_verdicts.csv), and [blind_renders](g292_jump_endpoint_content_artifact/blind_renders/).

## Endpoint content counts and G287 baseline

All counts below have the named denominator of **72 blind-sampled large-jump endpoints**, each a detector-box observation, not an authenticated player. G287's baseline was read from its landed [blind verdicts](g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv), not recalled from prose; its denominator is separately **72 historical unconditioned detector-box observations**.

| Centre-cross category | G292 large-jump endpoints / 72 | G287 historical baseline / 72 |
| --- | ---: | ---: |
| (a) Player's feet | 8 (0.111) | 15 (0.208) |
| (b) Player's body, not feet | 21 (0.292) | 17 (0.236) |
| (c) Bare court or floor | 11 (0.153) | 17 (0.236) |
| (d) Broadcast graphic or score ticker | 17 (0.236) | 13 (0.181) |
| (e) Person not a player in play | 14 (0.194) | 8 (0.111) |
| (f) Something else | 1 (0.014) | 2 (0.028) |
| (g) Cannot judge | 0 (0.000) | 0 (0.000) |
| (a)+(b) on a player | 29 (0.403) | 32 (0.444) |

For the specified on-a-player comparison, the pooled proportion is 0.423611, SE 0.082355, z -0.505939, and the nominal two-sided p is 0.612899 (no multiplicity correction). These are two independent samples of detector-box observations -- a historical unconditioned G287 sample and a new conditioned jump-endpoint sample -- so the correct requested test is unpaired; McNemar would be incorrect because the 72 G287 observations are not paired to these 72 endpoints.

## Unblinded pairs and direction

The full 36-step ordered joint distribution (before, after) is stored in [measurement_summary.json](g292_jump_endpoint_content_artifact/measurement_summary.json):

```text
1 D->D; 2 D->D; 3 B->A; 4 B->B; 5 D->D; 6 A->D;
7 A->B; 8 D->B; 9 D->D; 10 B->D; 11 D->D; 12 A->C;
13 D->B; 14 E->E; 15 B->C; 16 A->B; 17 B->C; 18 C->B;
19 B->E; 20 E->B; 21 B->C; 22 E->A; 23 E->E; 24 E->D;
25 A->C; 26 B->C; 27 D->A; 28 D->C; 29 E->E; 30 B->E;
31 E->B; 32 B->C; 33 B->C; 34 C->E; 35 F->B; 36 E->B.
```

Of the **36 sampled large-jump steps**, 32/36 = 0.889 have at least one non-player endpoint (C--F), 11/36 = 0.306 have both endpoints non-player, 4/36 = 0.111 have both endpoints on a player (A or B), and 0/36 have a cannot-judge endpoint. The remaining 21/36 are mixed player/non-player steps.

Among those **21 mixed pairs**, the non-player endpoint is before in 9/21 and after in 12/21. The exact nominal two-sided binomial p against 0.5 is 0.663624. There is no resolved direction: this draw does not show IDs drifting onto furniture rather than off it, and that absence of direction is itself the informative direction result.

## Limits and NOT VERIFIED

This row CANNOT separate "implausible" from "large image jump" -- at the measured scales a jump beyond 150 px in one frame IS implausible, so the two are very nearly the same set and there is no matched plausible control available.

The baseline is a HISTORICAL landed sample (G287), not a freshly drawn concurrent control. ONE clip, ONE span, ONE draw of a non-deterministic route, ONE labeller -- and agreement with G287 is rater-matched REPEATABILITY, never independent validation. This row is additionally rater-confounded because GPT-5 Codex, not G287's gpt-5.6-terra labeller, made the G292 classifications. Per G278 the span is measurably friendlier than the clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. A footpoint is a POINT: this row says what is AT it, never what a bounding box contained. The population is detector-box observations, not authenticated players.

NOT VERIFIED: a causal allocation of any large jump to detection or identity; replication across clips, spans, routes, detector draws, arenas, sports, or labellers; ground-truth player identity or detector precision; detector-box extent; a matched plausible control; and any filter, threshold, gate, retrain, or production change. No G273, G287, G289, or G281 verdict, count, artifact, threshold, or production file was altered.

## Reproduction and contract self-check

```text
python -m pytest tests/platformkit/test_g292_jump_endpoint_content.py -q -p no:cacheprovider
3 passed
```

The focused test pins the 1,897 selection from the committed G289 CSV and the 512x640 crop geometry. The current local analysis route SHA-256 is `666b1bd64df960ffdbcbb5cd6290b2794b67452538431d2e6347dc0133e36278`; the final unblind map SHA-256 is `5e67eac8da93643e3ba5f509c8847882bc1eb2813c2fc595c8bab6c8f31ba4cc`.

Self-check against [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), section B: B1 uses every selected endpoint and names the frozen 1,897 population; B2--B6 are additive evidence/harness work only, with no schema, lifecycle, deployment, reader, or production change; B7 uses all 36 equal-time bins rather than a head slice; B8 offers no fitted claim; B9 names detector-box and step denominators; B10 moves no threshold or gate; B11 explicitly limits the one pod render and one non-deterministic source draw. A7 evidence paths named above exist. A9 and A11 source/video and route identities are above. The 263-line harness remains below the LOC rail. Q does not apply to this descriptive tracking G-row.
