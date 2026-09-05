# G291: Independent second-rater agreement

MEASUREMENT COMPLETE; no pass bar. On all 72 detector-box observations (72 unique crops and 72 source frames), two model raters -- G273 `gpt-5.6-terra` and G291 `gpt-6-astra` -- agree on 47/72 = 0.652778 categories, with Cohen's kappa 0.283439 (SE 0.078538); this is 1 clip, 1 span, 1 shot, 1 draw of a non-deterministic route, not authenticated players and not clip-wide.

**No: the independent rater does not reproduce 0.597, judging 60/72 = 0.833333 PLAYER versus G273's 43/72 = 0.597222, a +0.236111 (23.61 percentage-point) margin with a nominal paired 95% Wald interval for that difference of +0.129989 to +0.342233.**

Agreement beyond chance is low in practical terms, especially outside PLAYER; no acceptance threshold or conventional kappa band was introduced. The programme's eye-labelled numbers carry rater uncertainty that was never quantified, and every downstream comparison inherits it. This is a successful reproducibility measurement, not a correction to G273 or evidence that the higher rate is more accurate. It supplies no numerical error bar for another row, corpus or rater. Of G273's 43 PLAYER verdicts, 42 survive this rater (42/43 = 0.976744), but 18 other crops become PLAYER and one PLAYER becomes CANNOT JUDGE: retention of positive labels does not reproduce the original rate.

## Blind procedure and seal

The order and 72 free-text verdicts were committed in their own commit **`b35967751945038273c8c65709e493322c386475`**, before opening G273's verdict CSV, unblind map, presentation CSV, G273/G287 memos, or their ledger rows. The memos and ledger rows were deliberately deferred because they could expose per-crop reference judgments, prioritizing the user's blind-sealing instruction over the spec's READ FIRST ordering. The aggregate rates and G287 aggregate decomposition were already supplied in the dispatch; blindness was to crop-specific reference labels and mappings, not to those aggregate headlines. The chronological tool transcript contains the original-image views, progressive verdict writes, seal commit, and only then the first reference read.

All 72 original committed JPEGs were viewed individually at their native 512x640 resolution, in the fresh randomized order in `g291_independent_second_rater_agreement_artifact/blind_order.json`. Python `random.Random(seed).shuffle` used a freshly generated 64-bit seed (recorded below). No re-render, re-crop, re-sample, video decode, detector run, GPU or pod was used. `blind_verdicts.jsonl` contains one free-text line for each crop in that exact viewing order. Neither sealed file was changed after unblinding. The comparison harness checks them against the seal's git blobs, accounting only for Windows CRLF versus git LF line endings.

Applied rule: **WHAT THE CROP SHOWS**, G273's coarse categorical judgment at full crop resolution, **not a geometric judgment and not G287's centre-cross rule**. The pre-existing red marker was visible but was not used to choose a target. A visible recognizable player could support PLAYER even if partial, peripheral, or sharing the crop with an official or graphic. Close-ups without enough in-play context could be CANNOT JUDGE. The four category meanings are unchanged: (a) PLAYER on the court of play; (b) PERSON not a player in play; (c) NOT A PERSON; (d) CANNOT JUDGE. The harness maps the sealed long names to the reference CSV's short spellings only; it does not relabel observations. CANNOT JUDGE remains its own row, column and rate, including when its count is small.

These are independent model-family judgments, not a fresh human assessment. The dispatch identifies G273/G280b/G285b/G287 as `gpt-5.6-terra` and this pass as `gpt-6-astra`; this row uses that supplied rater provenance, without independently auditing dispatch logs.

## Confusion matrix and rates

Rows: G273 / `gpt-5.6-terra`. Columns: G291 / `gpt-6-astra`. Every marginal and rate denominator is all 72 sampled detector-box observations. P = PLAYER; O = PERSON not a player in play; N = NOT A PERSON; U = CANNOT JUDGE.

| G273 / G291 | P | O | N | U | G273 total |
| --- | ---: | ---: | ---: | ---: | ---: |
| P | 42 | 0 | 0 | 1 | 43 |
| O | 6 | 3 | 0 | 0 | 9 |
| N | 10 | 4 | 0 | 1 | 15 |
| U | 2 | 1 | 0 | 2 | 5 |
| G291 total | 60 | 8 | 0 | 4 | 72 |

| Category | G273 n/72 | G273 rate | G291 n/72 | G291 rate | G291 minus G273 |
| --- | ---: | ---: | ---: | ---: | ---: |
| PLAYER | 43/72 | 0.597222 | 60/72 | 0.833333 | +0.236111 |
| PERSON NOT PLAYER IN PLAY | 9/72 | 0.125000 | 8/72 | 0.111111 | -0.013889 |
| NOT A PERSON | 15/72 | 0.208333 | 0/72 | 0.000000 | -0.208333 |
| CANNOT JUDGE | 5/72 | 0.069444 | 4/72 | 0.055556 | -0.013889 |

G273's exact counts reproduce the supplied rounded rates 0.597 / 0.125 / 0.208 / 0.069. No reference verdict was corrected, reopened for adjudication, or changed. The map was read after sealing only to join and verify filenames/source frames; it did not inform any label.

## Agreement, uncertainty and paired test

Raw agreement is 47/72 = 0.652778; empirical marginal chance agreement is 0.515432. Cohen's kappa = (raw - chance)/(1 - chance) = 0.283439, with non-null multinomial delta-method SE 0.078538 and nominal 95% Wald interval [0.129505, 0.437374]. **At n = 72, kappa is imprecise.** These are observation-level approximations, not cluster-robust intervals or evidence of independence among adjacent frames from one shot. The exact finite-sample descriptive counts do not require an independent-crop assumption; inferential SEs, intervals and p-values do. Shared clip/span/shot dependence and systematic shared model biases are not captured by the SE.

For reproducibility, with cell proportions p_ij, row marginals r_i, column marginals c_j, observed agreement po and chance agreement pe, the gradient is g_ij = [I(i=j)(1-pe) - (1-po)(c_i+r_j)]/(1-pe)^2. Estimated variance is [sum(p_ij*g_ij^2) - sum(p_ij*g_ij)^2]/72. The local route implements this expression without a fitted model.

Per-category positive agreement is 2*both/(G273 count + G291 count), so joint absence cannot conceal zero positive overlap. Reference retention is both/G273 count; G291 overlap is both/G291 count. These are agreement measures, not sensitivity, specificity or correctness against truth.

| Category | Both | Positive agreement | Reference retention | G291 overlap | Binary agreement (including joint absence) |
| --- | ---: | ---: | ---: | ---: | ---: |
| PLAYER | 42 | 0.815534 | 0.976744 | 0.700000 | 0.736111 |
| PERSON NOT PLAYER IN PLAY | 3 | 0.352941 | 0.333333 | 0.375000 | 0.847222 |
| NOT A PERSON | 0 | 0.000000 | 0.000000 | undefined (G291 n=0) | 0.791667 |
| CANNOT JUDGE | 2 | 0.444444 | 0.400000 | 0.500000 | 0.930556 |

NOT A PERSON has **zero positive agreement (0/15 reference positives reproduced)** despite binary agreement 57/72 from joint absence. Overall kappa alone would obscure this failure of category reproducibility.

The required paired PLAYER indicator comparison has 42 both PLAYER, 18 G273 non-PLAYER / G291 PLAYER, 1 G273 PLAYER / G291 non-PLAYER, and 11 neither PLAYER (all 72 retained). The indicator tests whether a label equals PLAYER; it does not merge CANNOT JUDGE into another four-category bucket. There are 19 discordant pairs. Exact two-sided McNemar nominal p = 2*P[Binomial(19, 0.5) <= 1] = **0.0000762939453125**. This is **nominal**, with no multiplicity adjustment and no within-shot dependence correction; no unpaired two-proportion test was used. The observed paired difference is +17/72 = +0.236111, SE 0.054144, nominal paired Wald 95% interval [+0.129989, +0.342233]. There is no preregistered equivalence margin; this interval is descriptive uncertainty under the stated assumptions, not an equivalence acceptance test or a clip-wide interval.

## What the disagreements mean

All 25 disagreements are listed below with sealed G291 free text. The dominant pattern is spatial scope within mixed-content crops: 10 G273 NOT A PERSON and 6 G273 PERSON-not-player crops become PLAYER because this rater sees recognizable players elsewhere in the crop, including peripheral shorts/legs, players behind officials, and players above graphics. Another 4 G273 NOT A PERSON crops become PERSON-not-player because spectators or staff are visible. The remaining G273 NOT A PERSON crop (`blind_038`) becomes CANNOT JUDGE because a close uniformed torso lacks in-play context. Thus the 15 NOT A PERSON labels split 10 PLAYER / 4 PERSON / 1 CANNOT JUDGE, never NOT A PERSON.

This is a systematic difference in applying the shared crop-content categories to mixed scenes, not simply uncertain distant blurred shapes. It does not establish which pixels G273 attended to or justify claiming G273 used the centre-cross rule. G291's own notes expose judgment boundaries too: partial limbs can suffice when court context is visible, while some tight uniform close-ups cannot establish in-play status. Two G273 CANNOT JUDGE crops become PLAYER (`blind_042`, `blind_069`), one becomes PERSON (`blind_071`), and one G273 PLAYER becomes CANNOT JUDGE (`blind_059`). The source judgments stand unchanged; no reconciliation pass was performed.

| Crop | G291 / gpt-6-astra | G273 / gpt-5.6-terra | G291 sealed free text |
| --- | --- | --- | --- |
| blind_001.jpg | PLAYER | NOT A PERSON | Partial dark-uniformed player with blue headband is visible on the court side of the blue sideline; bench staff behind. |
| blind_002.jpg | PLAYER | NOT A PERSON | Several uniformed players defend and move around the painted lane. |
| blind_004.jpg | PLAYER | NOT A PERSON | Two cropped but recognizable uniformed players run across the upper court; spectators and scoreboard fill most of the image. |
| blind_006.jpg | PLAYER | NOT A PERSON | A cropped blue-uniformed player and leg are visible at the right edge on court; bench staff stand across the sideline. |
| blind_012.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | A dark-uniformed player runs behind referee 11; spectators and graphics occupy the lower crop. |
| blind_018.jpg | PLAYER | NOT A PERSON | Dark-uniformed player 25 and other partial players are visible on court beside referee 11. |
| blind_024.jpg | PLAYER | NOT A PERSON | Dark-uniformed player 20 raises an arm while a white-uniformed player moves beside her above the scoreboard. |
| blind_025.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | White-uniformed player and dark-uniformed defender face each other on court; spectators below and black padding at left. |
| blind_027.jpg | PERSON NOT PLAYER IN PLAY | NOT A PERSON | Standing and seated spectators dominate the crop beneath a scoreboard; only shoes at the far top edge, no identifiable player in play. |
| blind_030.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | Referee 11 dominates center; cropped players lower legs and basketball shoes are visible in the painted lane at the top. |
| blind_034.jpg | PLAYER | NOT A PERSON | White and dark uniformed players contest a play in the painted lane, several arms raised. |
| blind_036.jpg | PERSON NOT PLAYER IN PLAY | NOT A PERSON | Referee runs past headset-wearing courtside workers; only clipped shoes at the top edge, no identifiable player body. |
| blind_037.jpg | PLAYER | NOT A PERSON | Overhead view of white and dark uniformed players standing beside the painted court line above graphics. |
| blind_038.jpg | CANNOT JUDGE | NOT A PERSON | Tight white-uniformed player torso and face above scoreboard; insufficient surroundings to establish in-play versus off-court status. |
| blind_042.jpg | PLAYER | CANNOT JUDGE | Close view of a dark-uniformed player beside a referee; the player torso and braided hair fill the right side, court itself out of view. |
| blind_043.jpg | PERSON NOT PLAYER IN PLAY | NOT A PERSON | Standing blue-clad bench staff and seated spectators are visible beyond an otherwise empty foreground court. |
| blind_044.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | A dark and blue uniformed player runs at the top, with a referee and spectators beneath. |
| blind_045.jpg | PERSON NOT PLAYER IN PLAY | NOT A PERSON | Seated spectators and a headset-wearing courtside worker; empty court above and large black padding, no player visible. |
| blind_053.jpg | PLAYER | NOT A PERSON | Blue and white uniformed players are clearly visible on court, alongside an official near the sideline. |
| blind_054.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | Cropped uniformed players with shorts and legs are visible on court at the top; foreground spectators and scoreboard dominate below. |
| blind_059.jpg | CANNOT JUDGE | PLAYER | Close portrait of a blue-headband player in dark jersey; background too restricted to establish court of play versus bench. |
| blind_061.jpg | PLAYER | NOT A PERSON | A white-uniformed player with red shoes runs across the top of the crop; foreground is spectators, media staff and graphics. |
| blind_067.jpg | PLAYER | PERSON NOT PLAYER IN PLAY | Referee 11 dominates center, but cropped dark shorts, legs and blue basketball shoes of a player are visible on court at upper right. |
| blind_069.jpg | PLAYER | CANNOT JUDGE | Close cropped blue and black player uniforms, arms, shorts and basketball shoes are visible above broadcast graphics. |
| blind_071.jpg | PERSON NOT PLAYER IN PLAY | CANNOT JUDGE | Courtside personnel behind monitors and a cropped foreground head; no identifiable player in play. |

## Exact inputs, machine and artifacts

Machine: local Windows CPU, `C:/Users/neelj/nba-track-a4`, branch `track-a4`, because all original JPEGs and committed reference inputs are already here. All writes and git operations stayed in this worktree.

`g291_independent_second_rater_agreement_artifact/input_manifest.json` enumerates **every analytical input's absolute full path, byte size, resolution (null/not applicable for text), and SHA-256**. Its first 72 entries are the original JPEGs, each 512x640, totaling 3,746,759 bytes. They are rooted at `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g273_detector_precision_blind_sample_artifact/blind_renders/`. This is a manifest of original inputs, not newly rendered images. Subsequent entries name the post-seal G273 verdict CSV, map, presentation CSV, and both G291 sealed inputs. Source-file byte sizes are the actual local Windows bytes, which can differ from another checkout's text byte sizes through line endings. No source video was opened; inherited video metadata is not a fresh video verification.

Analytical evidence, all under `docs/evidence/tracking/g291_independent_second_rater_agreement_artifact/`:

- `blind_order.json` and `blind_verdicts.jsonl`: original independently sealed order, image hashes and 72 notes.
- `input_manifest.json`: exact local source identities.
- `paired_verdicts.json`: all 72 paired categorical observations, source frames and viewing positions; no exclusions.
- `measurement_summary.json`: complete matrix, marginals, SE, paired test and 25 disagreements.
- `task_plan.md`, `progress.md`, `findings.md`: workflow record.

Local harness: `scripts/platformkit/tracking/g291_independent_second_rater_agreement.py`. Focused test: `scripts/platformkit/tracking/test_g291_independent_second_rater_agreement.py`. Reproduce from this worktree root with:

```text
python -m scripts.platformkit.tracking.g291_independent_second_rater_agreement
python -m pytest scripts/platformkit/tracking/test_g291_independent_second_rater_agreement.py -q -p no:cacheprovider
.....                                                                    [100%]
5 passed in 9.85s
```

The test pins kappa = 1.0 on identical nondegenerate verdict vectors, kappa = 0.0 on a balanced 4x4 chance table, the chance-table SE, exact McNemar p = 0.625 for 3-versus-1 discordance, retention of zero-count and CANNOT JUDGE categories, and rejection of invalid or undefined-kappa inputs. Only per-file pytest commands are used.

## Required limitations and NOT VERIFIED

**TWO MODEL RATERS AGREEING IS NOT GROUND TRUTH.** This row measures **REPRODUCIBILITY ACROSS RATERS, never CORRECTNESS** -- **both raters can be wrong in the same direction, and high agreement would NOT establish that either is right.** Neither rater is a human and no human has checked these 72 crops. A 512x640 crop is not the detector's box, and a crop-level judgement cannot say where IN the crop the detection fell -- that is why G287's centre-cross re-judge found G273's 43 PLAYER verdicts split 13 feet / 15 body / 12 floor / 2 graphic / 1 basketball. This row inherits that limit and does not touch it. 72 crops, ONE clip, ONE span, ONE shot, ONE draw of a non-deterministic route. Per G278 the span is measurably friendlier than the clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. The population is detector-box observations, not authenticated players -- both raters are G273 `gpt-5.6-terra` and G291 `gpt-6-astra`.

NOT VERIFIED:

- Correctness of either rater, human agreement, authenticated player identities, or geometric detector precision/recall.
- Box extents or where within these crops each detection falls; association and court-map accuracy.
- Generalization to any other clip, span, shot, draw, arena, sport, resolution, conditioning rule, or model/human rater.
- A numeric rater-variance correction for G280b, G286, G287, or any downstream comparison; only this paired sample was measured.
- Independence of crop observations for inference, stable route repeatability, or model biases shared by both raters.
- Dispatch-log model provenance independently of the user's supplied verification; raw footage metadata by fresh inspection.

No filter, threshold, retrain, production change or changed bar is proposed.

## Verifier-contract self-check

Spec: `docs/evidence/tracking/specs/G291_spec.md`; contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`. B1: all 72 observations retained, including four CANNOT JUDGE judgments and a zero-count category. B2-B6: additive measurement files only, no schema/lifecycle/deployment/module move. B7: exhaustive review of the fixed 72-crop decision set in a new random order, not a head slice. B8: independently sealed second-model labels, no fitted residual and no claim of independent ground truth. B9: 72 unique filenames and source frames; observation population explicitly named. B10: no bar exists and no existing threshold or verdict moved. B11: one non-deterministic route draw is explicitly limited to this sample, not asserted as a system property. A7: every evidence path is present. A9: source identities in the complete manifest. A11: no pod route; local harness identity is recorded below. A12: the new harness is below 300 lines, with no allowlisted file grown, so no shared allowlist edit is required. Q does not apply: this is tracking G291, not an S-register row. The memo and append-only RESULTS_LEDGER.md row are committed together after the separate blind seal. The user's pre-existing spec modification is left untouched.

Fresh shuffle seed: `16117033965268563314`.
Local harness: 139 lines; 7219 bytes; SHA-256 `adcc503623c6a94f04b8b5db5a9bbb4ec36371d0844c2df05df3072997901bdd`.

Additional validation (local, per-file only):

```text
statsmodels kappa: 0.28343949044586 SE: 0.07853785608957922
Independent library recomputation agrees to 1e-12.
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
.                                                                        [100%]
1 passed in 2.28s
```

Final artifact census: 77 analytical input manifest entries exist and match their hashes;
72 unique JPEG hashes, 72 unique crop IDs, 72 unique source frames; all 25 disagreement
rows appear exactly once in the memo. G273/G287 source artifacts are unchanged.
