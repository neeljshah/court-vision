# G280b: Amateur detector precision from a sealed blind sample

## Verdict

**ACCEPT (measurement only): 25 / 72 = 0.347 sampled retained detector-box observations showed a PLAYER on the court of play; 10 / 72 = 0.139 showed a PERSON NOT PLAYER IN PLAY; 37 / 72 = 0.514 showed NOT A PERSON; and 0 / 72 = 0.000 were CANNOT JUDGE.** The detector's useful-player yield in this sample is category (a), 25 / 72. The explicitly reported G273 grouping (b)+(c), boxes that arguably should never enter player tracking, is 47 / 72 = 0.653. Category (d) remains separate and is not merged into another category.

Against G273's broadcast all-detection blind sample, the amateur sample's PLAYER rate is lower (0.347 versus 0.597): pooled p = 0.472222, SE = 0.083205, z = -3.004640, nominal two-sided p = 0.002659. Its NOT A PERSON rate is higher (0.514 versus 0.208): pooled p = 0.361111, SE = 0.080054, z = 3.816879, nominal two-sided p = 0.000135. These are nominal two-sided p values with no multiplicity correction for the many comparisons in this programme. They compare two 72-observation samples of retained detector-box observations; they are not a population-wide claim about amateur footage.

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It makes no production change, filter, threshold, gate, calibration, court-space, speed, or track-length claim.

## Seal, blind procedure, and inputs

Before any crop was reviewed, the local packet at `docs/evidence/tracking/g280_amateur_footage_trackability_artifact/blind_packet/` was checked against sealed commit `41e53801f6c3879831b6582b0dd65cb7d3d2fab7`: it held 72 JPEG crops, 72 presentation-order rows, and 72 blank verdict rows. `blind_order_commitment.json` (433 bytes) declares sample size 72 and the canonical unblind-map SHA-256 `4bb76cd6da4c094fcd7a903671cb0006b6c60c20cebabc00a96270a7330e8a32`. Regenerating the deterministic map in memory from `docs/evidence/tracking/g280_amateur_footage_trackability_artifact/run_1/tracking_data.csv` (3,363,300 bytes) produced 72 entries and that exact hash before crop review. The regenerated `unblind_map.json` was written only after the blinded verdict commit and again matched the commitment.

The 72 rendered inputs were the exact paths and byte sizes in [blind_input_manifest.csv](g280_amateur_footage_trackability_artifact/blind_packet/blind_input_manifest.csv): `docs/evidence/tracking/g280_amateur_footage_trackability_artifact/blind_packet/blind_renders/blind_001.jpg` through `blind_072.jpg`, all 512x640 pixels, 3,359,298 bytes in total (25,346--67,816 bytes each). No source video was opened for this row; these pre-rendered native-pixel footpoint neighbourhoods were the only image inputs. The committed [presentation order](g280_amateur_footage_trackability_artifact/blind_packet/blind_presentation_order.csv) is 2,315 bytes. The broadcast baseline is the 8,257-byte [G273 memo](g273_detector_precision_blind_sample_2026-09-04.md): 43 / 72 PLAYER and 15 / 72 NOT A PERSON. The 12,532-byte verifier contract named above was read before work.

The four G273 categories were used unchanged and in committed order:

1. PLAYER on the court of play.
2. PERSON NOT PLAYER IN PLAY.
3. NOT A PERSON.
4. CANNOT JUDGE.

The completed [blind verdict sheet](g280_amateur_footage_trackability_artifact/blind_packet/blind_verdicts.csv) was committed by itself as `a651e098d` before the map was generated or opened. Its post-fill size is 1,144 bytes. The later [unblind map](g280_amateur_footage_trackability_artifact/blind_packet/unblind_map.json) is 18,856 bytes and the machine [measurement summary](g280_amateur_footage_trackability_artifact/blind_packet/blind_measurement_summary.json) is 818 bytes.

The sealed draw has one retained class-`player` detector-box observation from each of 72 equal-width source-frame bins, conditioned on nothing downstream. After unblinding it spans 72 distinct source frames (21--3,579) and 33 emitted track IDs. Its population is the 24,078 retained detector-box observations in the deterministic G280 run, not authenticated players. The detector's `cls=player` label is not a verified identity.

## Counts and comparison

| Blind category | Amateur count / 72 sampled detector-box observations | Amateur sample fraction | G273 broadcast count / 72 | Test versus G273 |
|---|---:|---:|---:|---|
| (a) PLAYER on the court of play | 25 / 72 | 0.347 | 43 / 72 | pooled p 0.472222; SE 0.083205; z -3.004640; nominal p 0.002659 |
| (b) PERSON NOT PLAYER IN PLAY | 10 / 72 | 0.139 | 9 / 72 | no requested two-proportion test |
| (c) NOT A PERSON | 37 / 72 | 0.514 | 15 / 72 | pooled p 0.361111; SE 0.080054; z 3.816879; nominal p 0.000135 |
| (d) CANNOT JUDGE | 0 / 72 | 0.000 | 5 / 72 | kept separate; no requested two-proportion test |
| (b)+(c), reported grouping | 47 / 72 | 0.653 | 24 / 72 | descriptive grouping only |

The sample shows substantially fewer on-court-player locations and more locations with nothing person-like at the claimed footpoint than G273's broadcast sample. It does not establish the exact fraction for the 24,078-box population or for amateur video generally.

## Descriptive image positions

These are source image-pixel coordinates from the unblinded deterministic mapping, shown as min / median / max. They are a descriptive location breakdown only, not a density estimate and not a spatial filter proposal.

| Class | n | Image x px | Image y px | Source frame |
|---|---:|---:|---:|---:|
| PLAYER | 25 | 111.920 / 605.851 / 1109.401 | 297.201 / 399.297 / 651.382 | 291 / 1,854 / 3,456 |
| PERSON NOT PLAYER IN PLAY | 10 | 103.830 / 421.219 / 1218.870 | 231.812 / 573.290 / 676.891 | 156 / 2,103 / 3,405 |
| NOT A PERSON | 37 | 20.285 / 647.270 / 1241.161 | 93.504 / 400.658 / 713.310 | 21 / 1,662 / 3,579 |
| CANNOT JUDGE | 0 | not applicable | not applicable | not applicable |

NOT A PERSON observations span broadly across the image-coordinate range in this sample. That description neither tests nor supports a filtering rule.

## Box-density context and limits

G280's three byte-identical production-tracker runs each recorded 24,078 retained detections across about 1,243 processed frames, about 19.4 detector boxes per processed frame, on footage with at most a dozen people on court. That is a detector-box count, not a false-positive rate and not evidence of cause. The blind categories make its precision meaning more concrete: in this 72-observation sample, 25 locations show an on-court player, 10 show a person not playing, and 37 show nothing person-like at the claimed footpoint. The sample does not allocate why those locations occurred.

This is one 120-second amateur clip, one camera, one labeller, and one deterministic draw. It cannot support a claim about amateur footage as a class. The 72 of 24,078 retained detector-box observations are a sample, so all reported fractions are sample fractions, not exact population fractions. A footpoint-centred crop is not a detector box: NOT A PERSON means nothing person-like is visible at that claimed location, not that a rectangle extent was established. Category (b) is a role judgement rather than an identity judgement. The blind classification is a coarse categorical eye judgement, not the sub-pixel geometric measurement G257 bounded at 20 px. Eye-label reliability in this programme has not cleared 80 percent blind agreement on four measured criteria.

## Contract self-check and NOT VERIFIED

Contract self-check: A7 paths named here exist in this worktree; A9 names the locally opened crop inputs, dimensions, and byte manifest; A11 is not applicable because G280b ran no pod route. B1 retains the full fixed 72-bin sample with no verdict-conditioned exclusions. B2--B6 change no schema, lifecycle, deployment, production module, or module location. B7 uses the already sealed all-span one-bin-per-time-bin draw, not a head slice. B8 fits no model. B9 names the 72-sample and 24,078-population denominators. B10 moves no bar or threshold. Q does not apply.

NOT VERIFIED:

- Exact precision of the 24,078 retained detector-box population, any other draw, clip, camera, arena, sport, or labeller.
- Detector recall, identity correctness, association correctness, detector-box extents, or a causal mechanism for NOT A PERSON locations.
- Court-space accuracy, calibration, speed, track length, or any claim based on `step_count = 0`; the production tracker emits every third frame and those are outside this row.
- Any spatial production rule, filter, threshold, gate, tuning, or retraining.
