# G17C v3 soccer role classifier LIMIT measurement

## Verdict: CLOSED AT LIMIT

This is the final G17 role-filter attempt. The three-class model clears the
pooled accuracy, paired-delta, and labelled-render-disagreement numerical
bars, but it finds zero of seven referees in held-out crops. With only seven
referee crops across five folds, this is a label-scarcity limit, not evidence
that the class can be recovered reliably. Soccer count features therefore
close at limit; S1 is not re-adjudicated.

## Immutable premise and scope

The existing `soccer_roles_labels/labels.csv` and `crops/` join exactly:
300 unique CSV crop names and 300 JPEGs. The label distribution is player 268,
other 25, referee 7. The sealed n=100 premise reproduced before model work:
manual median 13.0, manual pct >=14 0.490, and mean paired
manual-minus-detector delta -1.23.

The coverage bound remains camera framing, not the crop classifier. A typical
broadcast wide shot holds roughly 10 to 16 of 22 players, while the sealed set
also contains close-ups with as few as one visible player. A perfect role
classifier can remove detected non-players; it cannot recover players outside
the frame. The manual median of 13.0 and 49/100 frames at or above 14 show why
count-based verdicts remain bounded by framing.

Sampling was fixed before training: seeded round-robin over all 100 sealed S1
frames plus 30 G08 endpoint frames, visiting frames and boxes in seeded-random
order rather than confidence or frame-index order. Every one of the 130 source
frames contributed at least one crop. No frame was excluded because a prior
classifier handled it well. Five folds hold an entire `source_frame` out, so
the model used for a packet frame did not train on any crop from that frame.

## From-scratch five-fold crop CV

Architecture: torchvision ResNet18 with `weights=None`, random initialization,
and a three-output head. Training was CPU-only and local: 160x96 RGB crops,
60 epochs, AdamW, batch size 32, seed 20260904. All 300 predictions are OOF in
`soccer_role_classifier_v3_2026-09-04/cv_predictions.csv`.

| fold | n | accuracy | player recall | other recall | referee recall |
|---|---:|---:|---:|---:|---:|
| 0 | 64 | 0.9063 | 1.0000 | 0.4000 | 0.0000 |
| 1 | 60 | 0.8167 | 0.9608 | 0.0000 | 0.0000 |
| 2 | 55 | 0.9273 | 1.0000 | 0.2500 | 0.0000 |
| 3 | 57 | 0.9649 | 0.9811 | 0.7500 | n/a (no held-out referee) |
| 4 | 64 | 0.9375 | 0.9828 | 0.5000 | n/a (no held-out referee) |
| pooled OOF | 300 | **0.9100** | **0.9851** | **0.3600** | **0.0000** |

The majority-class baseline is 268/300 = **0.8933**. The model exceeds it by
0.0167 and has non-zero `other` recall, so that small gain is not solely a
majority-class tautology. It is nevertheless not useful for referee removal:
all seven held-out referees were assigned another class. The expected referee
outcome is therefore closed at label scarcity.

## Packet paired delta and render tally

For every sealed frame, its source-frame-held-out model labelled fresh local
detector boxes. The original sealed count columns contain no box coordinates,
so the before side remains the immutable sealed statistic while the after side
uses the deterministic local box rerun. The rerun differs from the sealed raw
count in 27/100 frames; this confound is retained, not hidden.

| statistic | n | mean manual count | mean count | mean manual-minus-count |
|---|---:|---:|---:|---:|
| sealed baseline detector | 100 | 12.15 | 13.38 | **-1.23** |
| source-frame-held-out classifier boxes | 100 | 12.15 | 12.69 | **-0.54** |

The full, unique 100-frame paired table is
`soccer_role_classifier_v3_2026-09-04/packet_paired_delta.csv`; its denominator
is 100 frames. The after absolute delta, 0.54, is below 1.0.

All 100 packet renders were generated and reviewed in ten consecutive contact
sheets (`contact_sheets/S1_0001_0010.jpg` through
`contact_sheets/S1_0091_0100.jpg`), not a head slice. The only per-box visual
ground truth is the seeded label set, which covers 227 labelled boxes across
all 100 packet frames. Comparing its source-frame-held-out prediction to its
label gives 19 disagreements / 227 = **8.37%**. The remaining fresh detector
boxes have no independent role label and are not silently counted as correct.

| clip | frames | labelled boxes | disagreements | rate |
|---|---:|---:|---:|---:|
| soccer_AgspyOj5BPk | 34 | 71 | 8 | 11.27% |
| soccer_DdnvC6-PGYY | 33 | 78 | 8 | 10.26% |
| soccer_kSgNjoaqCpI_1080p | 33 | 78 | 3 | 3.85% |
| pooled | 100 | 227 | 19 | **8.37%** |

## Acceptance bars

| bar | result | status |
|---|---:|---|
| OOF crop accuracy >= 0.90, n=300 | 0.9100 | pass |
| abs paired delta < 1.0, n=100 | 0.54 | pass, with 27 fresh/sealed raw-count mismatches disclosed |
| render disagreement < 10% | 8.37%, 19/227 labelled rendered boxes across all 100 frames | pass |
| per-class recall reported | player 0.9851, other 0.3600, referee 0.0000 | reported; referee result closes at limit |

## Licence and NOT VERIFIED

Licence/data line: classifier weights are random ResNet18 `weights=None`;
no ImageNet checkpoint, DINO weight, SoccerNet data, or SoccerNet-derived
material was used. The crop dataset is the local 300-row human-labelled
`soccer_roles_labels` set. The existing deterministic packet box producer uses
`yolov8n.pt` only to generate fresh boxes for the packet comparison; it is not
a classifier training weight. No model or data was copied to a pod.

NOT VERIFIED:

- A second labeler, label agreement, and referee-label adjudication are absent.
- The 27 fresh versus sealed detector-count mismatches prevent an isolated
  bit-identical before/after count claim.
- The 73 fresh packet boxes without a labelled counterpart are not role-scored.
- Generalization beyond these three broadcast clips, kits, and camera regimes
  is unmeasured.
- Zero referee recall is not proof that a larger, independently labelled
  referee corpus could not work; this 7-example set cannot establish that.

## VERIFIER_CONTRACT section B self-check

| rule | self-check |
|---|---|
| B1 circular metric | No row was excluded: 300 OOF crop predictions, all 100 packet frames, and all 227 labelled packet crops are named denominators. |
| B2 non-additive schema | New standalone CSVs only; no existing field, status, or reader changed. |
| B3 fall-through loss | This is measurement-only; no production gate quarantines an item. |
| B4 re-claim loop | No claim or retry path was added; the stated outcome is CLOSED AT LIMIT. |
| B5 pre-verification deploy | No pod command, file copy, deployment, or pod Git operation occurred. |
| B6 orphans | No module was moved or retired; the new module has its one focused test. |
| B7 head-slice evidence | Every S1_0001 through S1_0100 frame is rendered in consecutive ten-frame contact sheets. |
| B8 self-fit as independent | Crop predictions are OOF and the packet model holds the complete source frame out of training. Fresh unlabelled boxes are not claimed as independently role-labelled. |
| B9 degenerate denominator | Crop, labelled-box, and frame denominators are explicit and unique: 300, 227, and 100. |
| B10 moved bar | No detector, harness, threshold, or acceptance bar was modified. |
