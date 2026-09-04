# G273: Blind all-detection detector-precision sample

## Verdict

**ACCEPT (measurement only): 43 / 72 = 0.597 sampled retained detections showed a PLAYER on the court of play; 9 / 72 = 0.125 showed a PERSON NOT PLAYER IN PLAY; 15 / 72 = 0.208 showed NOT A PERSON; and 5 / 72 = 0.069 were CANNOT JUDGE.** The useful player yield is category (a), 43 / 72. The detections that would arguably never enter player tracking, the explicitly reported (b)+(c) grouping, are 24 / 72 = 0.333. Category (d) remains separate and is not included in any other grouping.

The all-detection NOT A PERSON rate, 15 / 72 = 0.208, is far below G272b's 24 / 48 = 0.500 rate for its deliberately jump-conditioned detector-box steps (where one or both footpoint crops had no person). On these two samples, non-person locations are concentrated in the jump-step sample relative to the all-detection sample. The units differ (a single detection here versus a two-endpoint step in G272b), and this is not a causal claim: it does not establish that non-person detections cause jumps, nor allocate any cause among detection, localisation, association, or projection.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It makes no production change, filter, threshold, gate, re-detection, or reassociation proposal.

## Frozen inputs and sample

The opened retained input was [G267's measurement artifact](g267_court_space_physical_plausibility_artifact/g267_measurement.json), 12,446,681 bytes, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`. It contains 30,071 finite retained class-0 detector footpoints across source frames 19599--23399 inclusive. The only video opened to render selected locations was `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps. No detector, association, court-map, or source-video write ran.

The 3,801-frame span was split into 72 contiguous equal-width frame bins (57 bins of 53 frames and 15 bins of 52 frames). A seeded uniform draw (`27320260904`) selected one finite retained detection from every bin; every detection in a bin was eligible, and selection used no speed, jump, association outcome, position, ID, or later-derived condition. The selected records cover all 72 bins, 72 distinct source frames, 41 emitted IDs, and source frames 19649--23377. The independent presentation shuffle used blind seed `27320904`.

Each [blind render](g273_detector_precision_blind_sample_artifact/blind_renders/blind_001.jpg) is a 512x640 native-pixel crop centred on the retained bottom-centre footpoint, marked only with a small red centre cross. This shows a person-sized neighbourhood at full source pixel resolution while keeping the 72-crop artifact modest. No detector box is drawn, reconstructed, or inferred: G267 retained no rectangle extents. Thus a NOT A PERSON verdict means that the retained location did not show anything person-like, not that a detector rectangle's extent has been established.

## Blind commitment and categories

The randomized [presentation order](g273_detector_precision_blind_sample_artifact/blind_presentation_order.csv), [blind verdicts](g273_detector_precision_blind_sample_artifact/blind_verdicts.csv), 72 renders, and [map-hash commitment](g273_detector_precision_blind_sample_artifact/blind_order_commitment.json) were committed in `c42b9b1f3bd4802f483189490124e564bd0e7204` before the unblind map was opened. The canonical unblind-map SHA-256 commitment is `2851f20e00b4416459f546fedca62ab714dfd7862d74409d8d254a883f172294`; it matches the later [unblind map](g273_detector_precision_blind_sample_artifact/unblind_map.json).

| Blind category | Count | Sample fraction |
|---|---:|---:|
| (a) PLAYER on the court of play | 43 | 0.597 |
| (b) PERSON NOT PLAYER IN PLAY | 9 | 0.125 |
| (c) NOT A PERSON | 15 | 0.208 |
| (d) CANNOT JUDGE | 5 | 0.069 |
| (b)+(c), reported grouping | 24 | 0.333 |

Category (b) is role judgement rather than identity judgement. The five (d) locations are retained as unjudgeable rather than being reclassified or suppressed.

## Descriptive positions by blind class

The table gives min / median / max for each class's retained footpoint. Court coordinates are the inherited G267 projected coordinates, not a fresh map validation. With these small class counts, this is a location description rather than a density estimate.

| Class | n | Image x px | Image y px | Projected court x ft | Projected court y ft |
|---|---:|---:|---:|---:|---:|
| PLAYER | 43 | 249.188 / 927.750 / 1836.000 | 296.625 / 562.500 / 972.000 | 13.861 / 31.021 / 62.080 | -10.080 / 8.180 / 27.757 |
| PERSON NOT PLAYER IN PLAY | 9 | 80.625 / 993.000 / 1830.000 | 633.000 / 784.500 / 954.000 | 8.416 / 31.903 / 56.185 | 11.376 / 22.832 / 26.881 |
| NOT A PERSON | 15 | 421.875 / 888.750 / 1867.500 | 388.500 / 860.250 / 973.500 | 16.868 / 34.422 / 50.309 | -1.902 / 24.650 / 31.380 |
| CANNOT JUDGE | 5 | 438.375 / 863.812 / 903.000 | 142.875 / 594.000 / 971.250 | 17.265 / 30.362 / 40.064 | -27.311 / 11.851 / 31.249 |

NOT A PERSON locations span much of the observed image and projected-coordinate ranges, with a high median image y (860.250 px) and court y (24.650 ft) in this sample; they are not confined to one reported point or single narrow image strip. The complete class-labelled coordinates are in `measurement_summary.json` and `unblind_map.json`. This descriptive result does not support, test, or propose a spatial filter.

## Machine, disk guard, artifacts, and checks

The shared pod was used only because it holds the named full-resolution source. An executable-and-CWD census, excluding the checker, its parent, and its own ancestry, found one other live lane (`/workspace/wt/a17`); no process was interrupted, making this the permitted second lane. `df` was not used. The binding `/workspace` guard reported 40,062 MB before and after a successful 8,388,608-byte `dd conv=fsync` probe. The peer's separate `/workspace/wt` scratch is included in that scope. After fetch, only the exact G273 pod scratch (3,774,895 bytes) and copied G273 route (9,879 bytes) were removed, freeing 3,784,774 bytes. The later `/workspace` reading was 40,067 MB because the peer lane was concurrently writing; no corpus source or either abandoned bridge partial was deleted.

The committed G273 artifact has 77 files and 3,808,137 bytes, dominated by the 72 crops. The preparation route exercised on the pod has SHA-256 `51086d201c2892e77098b45122720b8150d778ddb43e7c7e6be23940c04628d8`; the final local harness, which verifies the canonical commitment before summary, has SHA-256 `f24693aec72828600fcd391a07f88a9706dcf719ab35354b8c3739ac989dc4fc`.

```text
python -m pytest scripts/platformkit/tracking/test_g273_detector_precision_blind_sample.py -q -p no:cacheprovider
1 passed
```

Contract self-check: A7 names paths present in this commit; A9 names the opened artifact and video with bytes and resolution; A11 records the preparation and final-summary route identities. B1 retains all 30,071 finite records in the named sampling population before the fixed even-time draw; B2--B6 change no schema, lifecycle, deployment, production module, or module location; B7 uses all 72 bins over the complete pre-cut span, not a head slice; B8 uses no fit residual; B9 names the retained-record, frame, ID, and sample denominators; B10 moves no threshold or bar. Q does not apply. The 173-line harness is under the 300-line rail, so A12 does not require an allowlist update.

## NOT VERIFIED

- The category fractions beyond this 72-detection sample, another clip, shot, arena, sport, source draw, or labeller.
- Ground-truth detector precision or recall; this is a one-labeller sample from one non-deterministic detector draw, not an exact population fraction.
- Any person's true identity, a category (b) role beyond what is visible, duplicate status, or association correctness.
- The extent of any detector rectangle. Footpoint crops are neighbourhoods, not boxes.
- A causal relation between non-person locations and jump steps, or any spatial production rule.
- Eye-label reliability. This programme has not cleared 80 percent blind agreement on four measured geometric criteria; this is a coarser categorical judgement.
