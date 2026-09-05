# G297: Clean centre-cross inter-rater agreement

## Verdict

**NOT RATER-ROBUST, although the well-posed rule materially improves categorical agreement.** On the same 72 detector-box observations, G287 `gpt-5.6-terra` and the fresh G297 `gpt-5.6-sol` rater agree on 42/72 = 0.583333 exact seven-way categories. Cohen's kappa is 0.479142 (SE 0.071141), descriptively 0.195702 higher than G291's crop-level kappa 0.283439 (SE 0.078538). No significance test of that kappa difference was run or is implied.

That higher kappa says the centre-cross rule removes real crop-scope ambiguity. It does not rescue the programme's main point-content rate: G297 marks the footpoint on a player at all, A+B, in 17/72 = 0.236111 observations versus G287's 32/72 = 0.444444. There are 17 G287-on-player/G297-not pairs and 2 pairs in the other direction; exact two-sided McNemar nominal p = 0.000728607. The systematic loss is 15 G287 A/B observations called floor and 2 called graphic by G297.

Bluntly: the under-specified crop rule was part of G291's problem, but it was not the whole problem. The well-posed centre-cross rule produces materially higher kappa, yet the programme's approximately 0.44 on-player figure does not reproduce across these two model raters. Crop-level figures should still be retired because their target is ambiguous; centre-cross figures should be quoted only with this measured rater uncertainty, and every eye-labelled point-content number carries it.

Denominators: 72 crops, 72 detector-box observations, 2 named model raters, 1 clip, 1 span, 1 shot, and 1 detector draw. The population is detector-box observations, not authenticated players. This is a coarse categorical judgement at a point, not a geometric distance measurement.

## Blind procedure and seal

The fresh randomized [order](g297_centre_cross_rater_agreement_clean_artifact/blind_order.csv) and all 72 mandatory-free-text [ratings](g297_centre_cross_rater_agreement_clean_artifact/blind_ratings.csv) were committed by themselves before unblinding. The sealing SHA is **`2607641d6d6f5308e23baca18acb3a32bb25a402`**. The harness verifies both files byte-for-byte against their blobs in that commit, allowing only the checkout's CRLF representation of Git's LF bytes.

I applied the centre-cross rule, not the crop-level rule: I judged only what lay under the small red cross. A recognizable player elsewhere in a crop had no bearing on the label; when the cross itself sat on court, I used C even if a player was plainly visible nearby. A footpoint is a point: this row says what is at it, never what a bounding box contained.

The dispatch's broad reading restriction overrode G297's instruction to read predecessor memos first. Before sealing, I did not open the G287 memo, G288 memo, G273 memo, G291 memo, or any prior `blind_verdicts.csv`, because those files could name `blind_NNN` items and disclose content. I read G287's committed verdict CSV, the G287/G273/G291 memos, and aggregate ledger context only after the seal. I never opened the G288 memo because it was unnecessary. No re-render, re-crop, re-sample, decode, detector run, GPU, or pod was used.

You have not judged these crops before, so unlike G295 this pass's crop-specific independence is intact. The aggregate G291 and G295 results supplied in the dispatch were known, so the pass was blind to crop-specific labels, not to programme-level context.

## Categories and confusion matrix

The unchanged G287 categories are A player's feet; B player's body, not feet; C bare court or floor; D broadcast graphic or score ticker; E person not a player in play; F something else with free text; and G cannot judge, kept separate.

Rows are G287 `gpt-5.6-terra`; columns are G297 `gpt-5.6-sol`. Both marginals and all zero cells are explicit.

| G287 / G297 | A | B | C | D | E | F | G | G287 total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 5 | 0 | 9 | 1 | 0 | 0 | 0 | 15 |
| B | 6 | 4 | 6 | 1 | 0 | 0 | 0 | 17 |
| C | 2 | 0 | 13 | 0 | 2 | 0 | 0 | 17 |
| D | 0 | 0 | 0 | 12 | 1 | 0 | 0 | 13 |
| E | 0 | 0 | 1 | 0 | 7 | 0 | 0 | 8 |
| F | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 2 |
| G | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| G297 total | 13 | 4 | 30 | 14 | 10 | 1 | 0 | 72 |

Observed agreement is 42/72 = 0.583333 and marginal chance agreement is 0.200039. Cohen's kappa is 0.479142 with multinomial delta-method SE 0.071141 and nominal Wald 95% interval [0.339706, 0.618577]. `statsmodels.stats.inter_rater.cohens_kappa` independently reproduces kappa 0.4791 and ASE 0.0711.

Per-category positive agreement is `2 * diagonal / (G287 marginal + G297 marginal)`. Binary agreement includes joint absences and is supplied so the zero-count G category is not silently lost.

| Category | Both | Positive agreement | G287 retention | G297 overlap | Binary agreement |
| --- | ---: | ---: | ---: | ---: | ---: |
| A feet | 5 | 0.357143 | 0.333333 | 0.384615 | 0.750000 |
| B body | 4 | 0.380952 | 0.235294 | 1.000000 | 0.819444 |
| C floor | 13 | 0.553191 | 0.764706 | 0.433333 | 0.708333 |
| D graphic | 12 | 0.888889 | 0.923077 | 0.857143 | 0.958333 |
| E other person | 7 | 0.777778 | 0.875000 | 0.700000 | 0.944444 |
| F something else | 1 | 0.666667 | 0.500000 | 1.000000 | 0.986111 |
| G cannot judge | 0 | undefined (0+0 denominator) | undefined (G287 n=0) | undefined (G297 n=0) | 1.000000 |

G is a zero-count row and zero-count column for both raters. It is retained in the 7x7 matrix, rates, and focused regression test rather than dropped.

## Seven rate comparison and paired on-player test

Every rate uses all 72 detector-box observations.

| Category | G287 n/72 | G287 rate | G297 n/72 | G297 rate | G297 minus G287 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A player's feet | 15/72 | 0.208333 | 13/72 | 0.180556 | -0.027778 |
| B player's body, not feet | 17/72 | 0.236111 | 4/72 | 0.055556 | -0.180556 |
| C bare court or floor | 17/72 | 0.236111 | 30/72 | 0.416667 | +0.180556 |
| D graphic or ticker | 13/72 | 0.180556 | 14/72 | 0.194444 | +0.013889 |
| E person not a player in play | 8/72 | 0.111111 | 10/72 | 0.138889 | +0.027778 |
| F something else | 2/72 | 0.027778 | 1/72 | 0.013889 | -0.013889 |
| G cannot judge | 0/72 | 0.000000 | 0/72 | 0.000000 | 0.000000 |

For paired on-player status, A+B, 15 observations are on-player for both raters, 17 are G287-on-player/G297-not, 2 are G287-not/G297-on-player, and 38 are neither. The exact two-sided McNemar test uses only the 19 discordant pairs and gives nominal p = **0.000728607177734375**. This p-value is nominal: there is no multiplicity or within-shot dependence correction. An unpaired two-proportion test was not used because these are the same 72 crops.

## Comparison with the prior kappas

G291's under-specified crop-level comparison was kappa 0.283439 (SE 0.078538). This clean centre-cross comparison is kappa 0.479142 (SE 0.071141), descriptively higher by 0.195702. G295's crop-specifically leaked centre-cross comparison was kappa 0.394 (SE 0.069); the clean value is also higher, but the leaked result is not treated as an independent benchmark. No difference-between-kappas significance test was performed because the judgements overlap and no valid test was specified.

The comparison supports a narrow conclusion: specifying the spatial target improved seven-way agreement. The feet/body/floor boundary remained unstable enough to reverse the paired on-player marginal. Therefore the rule is clearer, not reliably reproduced on the programme's primary A+B quantity.

## Every disagreement

All 30 disagreements follow. Categories are G287 then G297; free text is the unchanged sealed G297 note.

| Crop | G287 | G297 | G297 sealed free text |
| --- | --- | --- | --- |
| blind_030.jpg | C floor | E other person | Cross is on the head/hair of a seated courtside spectator or staff person. |
| blind_029.jpg | A feet | C floor | Cross is on open gray court between moving players. |
| blind_020.jpg | A feet | C floor | Cross is on gray court just beside the white lane boundary. |
| blind_023.jpg | F something else | C floor | Cross is on open gray court below and away from the nearby player. |
| blind_052.jpg | B body | A feet | Cross is on the lime-green shoe/foot of the player in white. |
| blind_021.jpg | B body | C floor | Cross is on the painted court/line immediately below the players' feet. |
| blind_014.jpg | A feet | C floor | Cross is on gray court just left and below the player's purple shoes. |
| blind_049.jpg | A feet | C floor | Cross centre is on gray court immediately below the two players' shoes. |
| blind_019.jpg | A feet | C floor | Cross is on gray court below the nearby players' feet. |
| blind_009.jpg | A feet | C floor | Cross is on the black painted court beside the moving shoe. |
| blind_031.jpg | B body | C floor | Cross is on open gray court below the running player's foot. |
| blind_058.jpg | B body | A feet | Cross overlaps the light-blue shoe of the player moving behind number 5. |
| blind_064.jpg | B body | A feet | Cross is on the turquoise shoes of the player in black. |
| blind_032.jpg | B body | C floor | Cross is on the painted arc immediately below the yellow shoe. |
| blind_016.jpg | A feet | C floor | Cross is on gray court below the cluster of players' shoes. |
| blind_033.jpg | B body | C floor | Cross is on gray court just above the seated spectators and below the players. |
| blind_063.jpg | E other person | C floor | Cross is on the white court logo just below the official's black shoe. |
| blind_055.jpg | B body | D graphic | Cross is on the Atlanta panel of the score graphic. |
| blind_050.jpg | B body | C floor | Cross is on the black painted court over the WNBA logo. |
| blind_072.jpg | B body | C floor | Cross is on gray court below the nearby player's shoe. |
| blind_035.jpg | D graphic | E other person | Cross is on the head/hair of a seated courtside person above the promo graphic. |
| blind_010.jpg | A feet | C floor | Cross is on gray court below the player's purple shoes. |
| blind_026.jpg | C floor | A feet | Cross overlaps the purple shoe of the player standing in the paint. |
| blind_051.jpg | B body | A feet | Cross overlaps the purple shoe of the player in blue leggings. |
| blind_039.jpg | B body | A feet | Cross overlaps the cluster of players' shoes on the black painted court. |
| blind_069.jpg | A feet | D graphic | Cross is on the top edge of the black sports ticker. |
| blind_048.jpg | B body | A feet | Cross overlaps the white shoe of the player crossing the centre-court logo. |
| blind_062.jpg | A feet | C floor | Cross is on open gray court between the defender's feet. |
| blind_053.jpg | C floor | E other person | Cross is on the lower leg of the sideline official. |
| blind_057.jpg | C floor | A feet | Cross is on the dark shoe of the player running across the top of the paint. |

The dominant pattern is not attention to people elsewhere in the crop. It is the boundary at and immediately around the cross: G297 called floor whenever the cross centre appeared just below, beside, or between visible shoes. Fifteen G287 A/B labels become G297 C, while six G287 B labels become G297 A. G297 used B only four times, all four shared with G287, so the body category's zero off-diagonal inflow and much smaller marginal, 4 versus 17, are especially informative. Graphics and non-player people reproduce much better: D positive agreement is 0.889 and E is 0.778. Both raters use G zero times.

## Exact inputs, machine, artifacts, and reproduction

Machine: local Windows CPU in `C:/Users/neelj/nba-track-a4`, branch `track-a4`. This was entirely local because every required committed input was present. No pod process, deployed tree, source video, production route, or GPU was touched.

The [input manifest](g297_centre_cross_rater_agreement_clean_artifact/input_manifest.csv) states the absolute full path, byte size, width, and height of every input opened by the rating and comparison. It lists all 72 original JPEGs individually; each is 512x640 and together they total 3,746,759 bytes. It also lists the sealed order (1,242 bytes), sealed ratings (7,412 bytes), and post-seal G287 reference verdicts (1,567 bytes), with blank resolution fields for text. The memo's analytical inputs are therefore exhaustively named in the manifest, not represented by a game ID or directory alone.

The committed [summary](g297_centre_cross_rater_agreement_clean_artifact/measurement_summary.json) records the full matrix, marginals, kappa, SE, and paired test. The local read-only-input recomputation route is `scripts/platformkit/tracking/g297_centre_cross_rater_agreement.py`. It includes every row, validates the seal and crop-set identity, retains all seven categories, and prints the complete calculation plus exact SHA-256 identities. Reproduce with:

```text
python -m scripts.platformkit.tracking.g297_centre_cross_rater_agreement
python -m pytest scripts/platformkit/tracking/test_g297_centre_cross_rater_agreement.py -q -p no:cacheprovider
...                                                                      [100%]
3 passed in 1.64s
```

The focused test pins kappa 1.0 on identical nondegenerate vectors, kappa 0.0 at chance, and retention of a zero-count category as a seventh matrix row and column. No full test suite was run.

## Required limitations and NOT VERIFIED

**TWO MODEL RATERS AGREEING IS NOT GROUND TRUTH.** This measures **REPRODUCIBILITY ACROSS RATERS, never CORRECTNESS** -- **both raters can be wrong in the same direction, and high agreement would NOT establish that either is right.** Neither rater is a human and no human has checked these 72 crops. You have not judged these crops before, so unlike G295 your independence is intact -- but you are still a MODEL rater and the reference is a MODEL rater, and neither is a human.

A footpoint is a POINT: this row says what is AT it, never what a bounding box contained. There are 72 crops from ONE clip, ONE span, ONE shot, and ONE draw. Per G278 the span is measurably friendlier than the clip (0.836 vs 0.656, p=0.0078), so nothing here may be quoted clip-wide. The population is detector-box observations, not authenticated players; the raters are G287 `gpt-5.6-terra` and G297 `gpt-5.6-sol`.

NOT VERIFIED:

- Correctness of either model rater, human agreement, or ground-truth content at any footpoint.
- Generalization to another clip, span, shot, draw, arena, sport, crop design, or human/model rater.
- Detector precision or recall, authenticated player identity, association correctness, homography correctness, or detector-box extent.
- Independence of nearby observations for the reported inferential SE, interval, or nominal p-value.
- A numerical rater-error correction for G287 or any other eye-labelled row.

No filter, threshold, retrain, production change, gate, or changed bar is proposed. No G287, G288, G273, or G291 verdict was changed, reopened for adjudication, corrected, or converged.

## Verifier-contract self-check

Spec: `docs/evidence/tracking/specs/G297_spec.md`; contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`. B1: all 72 paired observations and all seven fixed categories are retained, including the zero-count G row/column. B2-B6: additive evidence and a local harness only; no existing schema, lifecycle, deployment, module, or production path changed. B7: all 72 crops were reviewed in a fresh randomized order, not a head slice. B8: independently sealed crop-specific ratings, no fit or self-fit residual. B9: 72 unique crop IDs and the detector-box-observation denominator are explicit. B10: no threshold or bar exists or moved. B11: one draw is limited to this fixed sample and is not claimed as a system or clip-wide property. A7: every evidence path named above exists. A9: the exhaustive manifest identifies every opened input. A11: no pod route was exercised. A12: the new harness is below 300 lines and no allowlisted file grew, so no shared allowlist edit is required. Q does not apply because G297 is a tracking row, not an S-register row.
