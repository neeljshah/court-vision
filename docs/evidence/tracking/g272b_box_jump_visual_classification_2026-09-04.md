# G272b: Footpoint-centred visual classification of retained box jumps

## Verdict

**ACCEPT (measurement only): G271's retained count reproduces exactly: 1,454 / 2,507 = 0.580 of both-endpoints-on-court, strictly-over-40-ft/s same-ID detector-box steps have bottom-centre displacement above 83 px.** A blind sample of 48 of those 1,454 steps, spread over 48 time bins and 45 emitted IDs, classified 14 (0.292) as (a) SAME PERSON, real fast movement; 9 (0.188) as (b) DIFFERENT PERSON; 24 (0.500) as (c) NOT A PERSON in one or both crops; and 1 (0.021) as (d) OCCLUDED / CANNOT JUDGE. These are sample fractions, not population fractions.

The population is retained detector boxes / associated observations, **not authenticated players**. G225's 19 raw boxes for two visibly on-court people remains the warning against treating the denominator as people.

Category (c) is the largest observed sample category. On this visual evidence, the leading defect location is upstream of association: many retained locations do not show a person in at least one crop. Category (b) is present but not dominant; without identity ground truth it cannot prove an identity switch. Category (a) is substantial (14 of 48), so part of G270's 0.105 conditional detector-box error signal can be real fast movement: the prior "physically impossible" framing must be qualified as a detector-box trajectory diagnostic, not a claim that every over-40-ft/s step is false. This does not alter any retained count or establish person identity.

No production change, filter, gate, threshold, re-detection, or reassociation is proposed.

## Frozen inputs, exact reproduction, and sample

The retained measurement input was [G267's artifact](g267_court_space_physical_plausibility_artifact/g267_measurement.json), 12,446,681 bytes, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`. Its source was opened only to render the selected crops: `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps. The source span remained frames 19599--23399. No detection, association, map fitting, map change, or reassociation ran.

The G272b harness recomputed consecutive finite same-ID pairs directly from the G267 artifact, retained only both-endpoints-on-court pairs with strict speed above 40 ft/s and image bottom-centre displacement above 83 px, and asserted the count was 1,454 before it decoded any frame. It printed `G272B_REPRODUCED_BOX_JUMPS=1454`. The harness SHA-256 was `dbd2ad0dff3350abb28b1a6e6a6a6a39c2414a34afc758b76f7e75a57715c740`.

Selection divided the candidate frame extent into 48 equal time bins and chose one seeded candidate from each, preferring an as-yet unused emitted ID inside the bin. The selected steps span source frames 19626--23390, cover all 48 bins, and cover 45 distinct emitted IDs. This is a spread sample, not a head slice or an exhaustive classification.

## Footpoint crop renders, not inferred boxes

Each [blind render](g272b_box_jump_visual_classification_artifact/blind_renders/blind_001.jpg) is a before/after pair of **512x640-pixel** crops at native source resolution. Each crop is centred on the retained bottom-centre footpoint for that emitted ID in that source frame; the red cross marks that retained point. The size shows a person-sized neighbourhood and surrounding scene while keeping the 48 committed pairs modest (the complete final crop artifact is 5,685,297 bytes).

No bounding box is drawn, reconstructed, or inferred: G267 retained no box geometry. A footpoint-centred crop is not the detector's box; it shows the neighbourhood the detection claimed, not the extent it claimed. Therefore a different-person judgement says what is at the two retained locations, which is the question here, but cannot confirm what a detector rectangle actually bounded. Each pair records image displacement and court speed. The render itself states when its two fixed windows overlap heavily; 26 of 48 have that warning, so they are not presented as clearly distinct views.

## Blind classification and unblinding

The sample was randomized with blind seed `272200904`. The commit `55c3c4ccc9cfe6e1102dd30ae146998955afff14` contains the randomized [blind presentation order](g272b_box_jump_visual_classification_artifact/blind_presentation_order.csv), its [unblind-map hash commitment](g272b_box_jump_visual_classification_artifact/blind_order_commitment.json), all 48 blind crop pairs, and [blind verdicts](g272b_box_jump_visual_classification_artifact/blind_verdicts.csv), before the unblind map was opened. The commitment SHA-256 for that map is `79add41fd808b69005bf26aa5e798e9c3b76c8ec07a384732ffa789f242ade20`.

That first commit contained the 48 verdict rows followed by 48 empty generator-template rows. The verdict rows were committed before unblinding and are unchanged; the empty duplicates are removed in this final record so a standard CSV reader cannot overwrite the committed values. The [unblind map](g272b_box_jump_visual_classification_artifact/unblind_map.json) is now committed for audit.

| Blind category | Count | Sample fraction |
|---|---:|---:|
| (a) SAME PERSON, real fast movement | 14 | 0.292 |
| (b) DIFFERENT PERSON | 9 | 0.188 |
| (c) NOT A PERSON in one or both crops | 24 | 0.500 |
| (d) OCCLUDED / CANNOT JUDGE | 1 | 0.021 |

The eye check is appropriate only for this coarse categorical question, "same person at these two retained locations?" It is not a sub-pixel geometric measurement and does not override G257's roughly 20-px bound for court-overlay geometry.

## Disk guard, test, and contract self-check

`df` was not used. A first explicit 8,388,608-byte `dd conv=fsync` probe passed with `du -sm /workspace` at 39,532 MB before and after removal. A second passed immediately before the compact scratch dispatch; its post-removal `/workspace` reading was 39,546 MB. The scratch launcher also removed its own 8,388,608-byte preflight at 39,534 MB; it is reported separately because it did not use `conv=fsync`. After fetch, only the exact G272b scratch artifact (5,682,359 bytes), G272b pod log (64 bytes), and copied G272b harness (10,914 bytes) were deleted from `/workspace/wt/a5`, freeing 5,693,337 bytes. The local unused 10,240-byte fetch tar was also deleted. No corpus source or either abandoned bridge partial was deleted.

```text
python -m pytest scripts/platformkit/tracking/test_g272b_box_jump_visual_classification.py -q -p no:cacheprovider
2 passed
```

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A7: every named evidence path exists in this commit. A9: both the opened artifact and source video path, bytes, and resolution are named. A11: the exercised harness hash is recorded. B1: the full G267 retained set is recomputed before the explicitly named structural restrictions; no selected row is excluded after its outcome. B2--B6: no schema, lifecycle, deployment, production route, or module move occurred. B7: selection is evenly distributed across 48 bins, not a head slice. B8: no fitted residual is evidence. B9: detector-box, emitted-ID, complete candidate, and sample denominators are named. B10: G267/G270/G271's 40-ft/s and 83-px references are unchanged. Q does not apply. The new 189-line harness is below the LOC rail, so A12 needs no update.

## NOT VERIFIED

- The category distribution beyond this 48-step, one-labeller sample; another clip, shot, arena, map, sport, or detector draw.
- Ground-truth identity, person precision/recall, on-court status, duplicate status, or whether category (b) is a true identity switch.
- What a detector rectangle actually bounded; the artifact has no rectangle geometry.
- Any causal proportion for detection motion, association, map error, duplicate boxes, non-person detection, or real movement.
- A production change, filter, gate, threshold, reassociation, tuning decision, or readiness claim.
