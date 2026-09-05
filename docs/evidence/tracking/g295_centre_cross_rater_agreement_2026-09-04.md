# G295: Centre-cross rater agreement

MEASUREMENT COMPLETE, no pass bar; FULLY BLIND INDEPENDENCE NOT VALIDATED. On all 72 unique crops representing 72 detector-box observations, two model raters -- G287 `gpt-5.6-terra` and G295 `gpt-6-astra` -- agree on 37/72 = 0.513889 categories; Cohen kappa 0.394085 (SE 0.068899). Denominators: 72 crops, 2 raters, 1 clip, 1 span, 1 shot, 1 draw of a non-deterministic route. The population is detector-box observations, not authenticated players; nothing is clip-wide.

**The centre-cross profile does not reproduce.** Kappa is modestly higher than G291's crop-level 0.283 (SE 0.079), but remains low in practical terms: 35/72 categorical disagreements, feet positive agreement 0.190476, and on-a-player judgments 10/72 versus 32/72. This is the similarly-low outcome, not evidence that the well-posed rule solved the programme's rater problem. The problem is not confined to the crop-level rule; every eye-labelled number carries rater uncertainty. This row supplies no universal numerical error bar for other rows. The earlier crop-level figures should remain retired as detector properties; the centre-cross figures cannot replace them as rater-robust quantities on this evidence. No significance test of the two kappas was performed: judgments overlap on these same crops and partly the same raters, and no valid difference test was specified.

## Rule, sequence, and the important blindness breach

I judged the visual content at the centre of the small red cross. A recognizable player elsewhere in the crop did not count: floor under that point received C even with clear players nearby. This applied the centre-cross rule, not the crop-level rule. This is a COARSE categorical judgement at the centre cross, not a geometric judgement or a measurement of distances, box extents, or pixel-accurate ground truth. At shoe and graphic boundaries the marker and broadcast blur limit perception; the sealed notes record the decision made without subsequent adjudication.

All 72 original committed JPEGs were viewed individually at native 512x640 resolution in a fresh randomized order. No re-render, re-crop, re-sample, video decode, detector run, GPU, pod, disk guard or hold rule was used. Python random.Random(seed).shuffle used seed `10592600515899348815` on the sorted 72 original filenames.

**Sealing SHA: `886d98ae64a145d05b95f05ed1fd58a950fb67e3`.** The order and all 72 verdicts, with mandatory free text on every row, were committed in their own commit before the first opening of G287's verdict CSV. The chronological tool transcript records the individual views, progressive verdict writes, seal commit, and then the CSV read. The harness verifies both sealed files against their git blobs (normalizing checkout CRLF to git LF) and verifies every original crop hash. No sealed verdict was edited after that commit.

**However, this was NOT fully blind to crop-specific G287 labels.** Following the spec's READ FIRST instruction, I read the G288 memo before judging. Its table disclosed all 30 G287 C/D crop labels and descriptions, including its note about blind_030. I also read the required G291 memo, which disclosed crop-level notes, and the G287/G273 memos and G291 ledger row. I reported this exposure before viewing the crops and recorded it in the sealed order. The literal CSV-before-seal requirement was met, but the intended absence of reference-label knowledge was not. The exposure cannot be undone by sealing later, randomization, or claiming to ignore it. These are sealed second-model point judgments with partial reference exposure, not a fully independent blind replication. Counts remain the observed measurement; no independence claim or clean rule-clarity conclusion is warranted. No subset was excluded or substituted to conceal the breach.

The category meanings are unchanged: A through G below. G is kept separate. F requires a named object, and every category has free text in the sealed JSONL. Rater names are dispatch-supplied provenance, not an independent audit of model invocation logs.

## Full matrix and rates

Rows are G287 / gpt-5.6-terra; columns are G295 / gpt-6-astra. Every rate denominator is all 72 sampled detector-box observations. Every zero cell, zero row and zero column is printed.

| G287 / G295 | A | B | C | D | E | F | G | G287 total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 2 | 0 | 13 | 0 | 0 | 0 | 0 | 15 |
| B | 3 | 4 | 8 | 1 | 1 | 0 | 0 | 17 |
| C | 1 | 0 | 14 | 0 | 2 | 0 | 0 | 17 |
| D | 0 | 0 | 0 | 9 | 3 | 1 | 0 | 13 |
| E | 0 | 0 | 1 | 0 | 7 | 0 | 0 | 8 |
| F | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 2 |
| G | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| G295 total | 6 | 4 | 37 | 10 | 13 | 2 | 0 | 72 |

| Category | G287 n/72 | G287 rate | G295 n/72 | G295 rate | G295 minus G287 |
| --- | ---: | ---: | ---: | ---: | ---: |
| A: PLAYER'S FEET | 15/72 | 0.208333 | 6/72 | 0.083333 | -0.125000 |
| B: PLAYER'S BODY not feet | 17/72 | 0.236111 | 4/72 | 0.055556 | -0.180556 |
| C: BARE COURT OR FLOOR | 17/72 | 0.236111 | 37/72 | 0.513889 | +0.277778 |
| D: BROADCAST GRAPHIC OR SCORE TICKER | 13/72 | 0.180556 | 10/72 | 0.138889 | -0.041667 |
| E: PERSON not a player in play | 8/72 | 0.111111 | 13/72 | 0.180556 | +0.069444 |
| F: SOMETHING ELSE | 2/72 | 0.027778 | 2/72 | 0.027778 | +0.000000 |
| G: CANNOT JUDGE | 0/72 | 0.000000 | 0/72 | 0.000000 | +0.000000 |

G (CANNOT JUDGE) is used zero times by G287 and zero times by G295: its entire row and column are zero. No other category has a zero marginal for either rater. G has zero shared positives; positive agreement and conditional overlaps are undefined (0/0), not perfect. Its binary agreement of 72/72 is entirely joint absence. F has equal counts of 2/72 for each rater but only one common crop, illustrating why equal marginals are insufficient.

## Agreement, SE, and paired on-a-player test

Raw agreement = 37/72 = 0.513889; empirical marginal chance agreement = 0.197724. Cohen kappa = (po-pe)/(1-pe) = 0.394085, non-null multinomial delta-method SE = 0.068899, nominal 95% Wald interval [0.259043, 0.529127]. With cell proportions p_ij, row marginals r_i and column marginals c_j, g_ij = [I(i=j)(1-pe) - (1-po)(c_i+r_j)]/(1-pe)^2; variance = [sum(p_ij*g_ij^2) - sum(p_ij*g_ij)^2]/72. The implementation uses the equivalent centered-gradient expression. These observation-level inferential calculations assume independent sampled units; within-shot dependence and shared model bias are not accounted for. At n=72 uncertainty is appreciable. The two kappas are compared descriptively only, with both SEs shown above.

Per-category positive agreement = 2*both/(G287 count + G295 count); reference retention = both/G287 count; G295 overlap = both/G295 count; binary agreement includes joint absence. These are agreement measures, never correctness, sensitivity or specificity against truth.

| Category | Both | Positive agreement | G287 retention | G295 overlap | Binary agreement |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 2 | 0.190476 | 0.133333 | 0.333333 | 0.763889 |
| B | 4 | 0.380952 | 0.235294 | 1.000000 | 0.819444 |
| C | 14 | 0.518519 | 0.823529 | 0.378378 | 0.638889 |
| D | 9 | 0.782609 | 0.692308 | 0.900000 | 0.930556 |
| E | 7 | 0.666667 | 0.875000 | 0.538462 | 0.902778 |
| F | 1 | 0.500000 | 0.500000 | 0.500000 | 0.972222 |
| G | 0 | undefined (0/0) | undefined (0/0) | undefined (0/0) | 1.000000 |

On-a-player means A+B only, on the same 72 paired crops. G287: 32/72 = 0.444444; G295: 10/72 = 0.138889; difference -22/72 = -0.305556. Paired table: both on-player 9, G287 on/G295 not 23, G287 not/G295 on 1, neither 39. All 72 remain; G remains separate in the seven-category analysis. Exact two-sided McNemar **nominal p = 0.0000029802322387695312**, computed as 2*P[Binomial(24,0.5)<=1]. This is nominal, with no multiplicity or within-shot dependence correction. No unpaired two-proportion test was used. A nominal paired Wald difference interval is [-0.419503,-0.191608] (SE 0.058136); it does not establish equivalence or generalization.

## Systematic pattern and every disagreement

The dominant pattern is player-to-floor disagreement: 13/15 G287 feet judgments and 8/17 G287 body judgments become floor, 21 of the 35 total disagreements. Many sealed notes put the point below, beside, or between shoes, including points beneath airborne feet. This differs from G291's explicit practice of accepting a player anywhere in the crop, but it still fails to reproduce the point-level profile. We cannot infer G287's attention or exact decision process from these counts, nor prove a perception-versus-rule cause. The explicit point target alone has not produced robust labels in this pass.

Three G287 body crops become feet (058, 048, 021), one becomes a spectator (033), and one a graphic (055). Boundary disagreements also affect overlays: three G287 graphics become courtside people (054, 036, 061), and one becomes chair furniture (035); the notes locate the cross just above the graphic. Two G287 floor crops become people (030, 043), while 022 becomes feet. The G287 basketball label (023) becomes floor below the ball. Referee-foot/floor boundary 063 changes E to C. These patterns describe disagreements, not reference errors to repair. The original judgments, crops, orders, categories and all thresholds remain unchanged.

Every disagreeing crop is listed below in sealed viewing order. Category letters refer to the full unchanged names above; all G295 free text is verbatim from the seal.

| Crop | G287 category | G295 category | G295 sealed free text |
| --- | --- | --- | --- |
| blind_035.jpg | D: BROADCAST GRAPHIC OR SCORE TICKER | F: SOMETHING ELSE | Cross sits on dark chair/backrest furniture below the blue-shirted worker and above the ticker. |
| blind_049.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor just below and right of the jumping players shoes. |
| blind_069.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross centre is in the narrow grey floor gap left of the right shoe, immediately above the ticker. |
| blind_009.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on black painted floor between the players feet. |
| blind_065.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor below the running players forward shoe. |
| blind_063.jpg | E: PERSON not a player in play | C: BARE COURT OR FLOOR | Cross centre is just below the referees black shoe on grey floor. |
| blind_032.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on grey floor below the airborne yellow shoes, inside the arc. |
| blind_051.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross centre sits on floor immediately below and left of the purple shoe heel. |
| blind_019.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor below and left of the white-uniformed players yellow shoe. |
| blind_054.jpg | D: BROADCAST GRAPHIC OR SCORE TICKER | E: PERSON not a player in play | Cross centre meets the red-shirted courtside persons lower torso just above the score panel. |
| blind_064.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross centre is on dark floor just left of the green shoe, beneath the other players blue shoe. |
| blind_062.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor between and below the defenders spread feet. |
| blind_058.jpg | B: PLAYER'S BODY not feet | A: PLAYER'S FEET | Cross meets the dark-uniformed players light-blue sock and shoe region behind the white player. |
| blind_029.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor just right and below the running players green shoe. |
| blind_052.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on grey floor/white arc below the purple shoe and between the white players legs. |
| blind_030.jpg | C: BARE COURT OR FLOOR | E: PERSON not a player in play | Cross is on the light-shirted seated spectators upper back beneath the referee. |
| blind_039.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on dark floor and white line immediately left of the central players shoe heel. |
| blind_033.jpg | B: PLAYER'S BODY not feet | E: PERSON not a player in play | Cross meets the top-left hair boundary of the seated blond spectator beneath the player. |
| blind_055.jpg | B: PLAYER'S BODY not feet | D: BROADCAST GRAPHIC OR SCORE TICKER | Cross lies within the Atlanta score graphic over the players lower body. |
| blind_016.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor below and between the green shoes. |
| blind_014.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor immediately below and left of the purple shoes. |
| blind_043.jpg | C: BARE COURT OR FLOOR | E: PERSON not a player in play | Cross meets the standing blue-shirted bench persons dark shoe at the sideline. |
| blind_072.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on grey floor and arc between the walking players shoes. |
| blind_023.jpg | F: SOMETHING ELSE | C: BARE COURT OR FLOOR | Cross is on grey floor beneath the dribbling player and ball. |
| blind_031.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on grey floor below the running players light shoes. |
| blind_010.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor below the blue-clad players purple shoes. |
| blind_048.jpg | B: PLAYER'S BODY not feet | A: PLAYER'S FEET | Cross meets the white-uniformed players ankle/white shoe over the midcourt logo. |
| blind_020.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on grey floor immediately left of the white players light shoe. |
| blind_022.jpg | C: BARE COURT OR FLOOR | A: PLAYER'S FEET | Cross meets the toe edge of the blue-clad players white shoe. |
| blind_021.jpg | B: PLAYER'S BODY not feet | A: PLAYER'S FEET | Cross meets the dark-uniformed players black shoe at the painted lane boundary. |
| blind_002.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross centre is on black painted floor just right of the crouching defenders shoe. |
| blind_036.jpg | D: BROADCAST GRAPHIC OR SCORE TICKER | E: PERSON not a player in play | Cross is on the blue-shirted courtside workers lower back just above the Indiana graphic. |
| blind_066.jpg | A: PLAYER'S FEET | C: BARE COURT OR FLOOR | Cross is on reflective grey floor left and below the purple shoes. |
| blind_050.jpg | B: PLAYER'S BODY not feet | C: BARE COURT OR FLOOR | Cross is on black painted court near the floor lettering below the ballhandler. |
| blind_061.jpg | D: BROADCAST GRAPHIC OR SCORE TICKER | E: PERSON not a player in play | Cross centre meets the dark-shirted seated spectators lower back immediately above the Indiana panel. |

## Inputs, machine, artifacts and verification

Machine: local Windows CPU at `C:/Users/neelj/nba-track-a4`, branch `track-a4`, because every required crop and reference CSV is committed locally. All creates, edits and git commands stayed in this directory. No video was opened.

`g295_centre_cross_rater_agreement_artifact/input_manifest.json` gives the full absolute path, byte size, resolution (null/not applicable for text), and SHA-256 of every crop and analytical input, plus the required spec, contract, memos and ledger. The 72 original JPEGs are rooted at `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/blind_renders/`, all 512x640 and 3,746,759 bytes total. The reference is `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv`; it is 1,567 bytes in this checkout, with its SHA-256 in the manifest. Text sizes can differ across checkouts because of CRLF. No frame mapping or other original verdict file was opened for scoring; the 72 distinct source-frame statement is inherited from G273, while 72 unique filenames and exact image hashes are directly checked here.

Artifacts under `g295_centre_cross_rater_agreement_artifact/`: `blind_order.json`, `blind_verdicts.jsonl`, `paired_verdicts.json` (all 72 pairs), `measurement_summary.json` (all cells and disagreements), `input_manifest.json`, `task_plan.md`, `findings.md`, `progress.md`.

Local harness: `scripts/platformkit/tracking/g295_centre_cross_rater_agreement.py`. Focused test: `scripts/platformkit/tracking/test_g295_centre_cross_rater_agreement.py`. The harness is additive, with no production callers. Reproduce from the worktree root:

```text
python -m scripts.platformkit.tracking.g295_centre_cross_rater_agreement
python -m pytest scripts/platformkit/tracking/test_g295_centre_cross_rater_agreement.py -q -p no:cacheprovider
.....                                                                    [100%]
5 passed in 0.97s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
.                                                                        [100%]
1 passed in 1.97s
```

Tests pin identical-vector kappa 1.0, chance-vector kappa 0.0 (floating-point tolerance 1e-15), chance SE, all seven matrix rows and columns including a zero-count column and wholly absent G, undefined 0/0 positive agreement, paired A+B McNemar discordance, and invalid inputs. Independent library recomputation with statsmodels cohens_kappa and scipy binomtest agrees: kappa 0.394085116615, SE 0.068899055498, exact paired p 2.98023223876953e-06. Only per-file pytest was run.

## Required limits and NOT VERIFIED

**TWO MODEL RATERS AGREEING IS NOT GROUND TRUTH.** This measures **REPRODUCIBILITY ACROSS RATERS, never CORRECTNESS** -- **both raters can be wrong in the same direction, and high agreement would NOT establish that either is right.** Neither rater is a human and no human has checked these 72 crops.

I am the same model that produced G291's crop-level verdicts on these SAME crops, so I may carry over an impression of them. This makes agreement with G287 a CONSERVATIVE test of rule-clarity rather than a fully independent one. That stipulated carryover limitation is additional to the G288 reference-label exposure: the latter may bias agreement upward, so the overall procedure cannot be certified as conservative or fully blind.

A footpoint is a POINT: this row says what is AT it, never what a bounding box contained. 72 crops, ONE clip, ONE span, ONE shot, ONE draw. Per G278 the span is measurably friendlier than the clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. The population is detector-box observations, not authenticated players. Both raters are G287 gpt-5.6-terra and G295 gpt-6-astra.

NOT VERIFIED:

- Fully blind independence: 30 crop-specific reference labels were exposed by required G288 reading before judging.
- Correctness of either model, human agreement, authenticated identities, detector precision/recall or box geometry.
- A causal separation of rule interpretation, visual perception, boundary ambiguity, carryover and reference exposure.
- Generalization beyond these 72 observations to another clip, span, shot, draw, arena, sport or rater.
- Independent observations for SE/p-values, route repeatability, or shared-bias correction.
- A valid significance test between overlapping kappas, or a numerical uncertainty correction for every programme label.
- Independently audited model invocation provenance or freshly checked raw-video metadata.

No filter, threshold, retrain or production change is proposed. No bar was introduced or moved. No G287, G288, G273 or G291 verdict was revised or reopened for adjudication.

## Verifier-contract self-check

Spec `docs/evidence/tracking/specs/G295_spec.md` and `docs/evidence/tracking/VERIFIER_CONTRACT.md` were read in full. B1: all 72 pairs retained; no exclusions. B2-B6: additive local evidence/harness only, no schema removal, lifecycle, deployment or moved module. B7: all fixed 72 crops, fresh shuffled order, no head slice. B8: no fitted residual; partial reference exposure disclosed and fully blind independence explicitly NOT VALIDATED. B9: 72 unique crop names and hashes checked; detector-box denominator named. B10: no bar, no existing threshold moved. B11: one unreproduced route draw is limited to this fixed sample, not claimed as a system property. A7: all named evidence paths checked present. A9: full input manifest. A11: no pod; local code identity below. A12: no allowlisted file grew, new files are below 300 lines; rail test passed. Q does not apply to tracking G295. Memo and RESULTS_LEDGER row are committed together after the separate seal. TRACKING_GAPS_2026-09-01.md, src/ and domains/ were not touched; the pre-existing spec edit remains untouched.

Local harness identity: 140 lines, 7461 bytes, SHA-256 `1e1f91e00fab095e1e87665ffbd1a300bb2f1c33561298e1e1ca2a09db097965`.
