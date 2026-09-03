# Per-sport broadcast tracking: published SOTA, licences, and the sequence that follows

Planning document, 2026-09-03. **Nothing here is a result.** No code was edited; `src/`, `kernel/`, `api/`,
`scripts/team_system/` and `intel/` were opened read-only. No harness was run. Contract:
[VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including Q6 (calibration language only).

**Sourcing rule.** Every quantitative claim carries a named published benchmark with the page it was read
from, or a file in this repo. External numbers were fetched 2026-09-03. Anything I could not source says NOT
VERIFIED; anything a source contradicts is flagged rather than picked. Builds on
[G_ADJUDICATION_fable_review_2026-09-03.md](G_ADJUDICATION_fable_review_2026-09-03.md) (binding),
[CALIBRATION_STRATEGY_2026-09-02.md](CALIBRATION_STRATEGY_2026-09-02.md) (geometry inventory) and
[G09_calibration_licence_research_2026-09-02.md](G09_calibration_licence_research_2026-09-02.md) (licence
base). Where this file and `CALIBRATION_STRATEGY` disagree on tractability, the adjudication and G196 win.

---

## 0. The seven facts this is built on. Do not re-derive them.

| # | Fact | Evidence |
|---|---|---|
| 1 | Basketball projects through a static `Rectify1.npy` calibrated for a 3698x500 panorama; on broadcast frames the court model collapses to a line. 3 of 3 runs took the fallback branch, 5 fresh-solve attempts each, 0 successes. | G194 |
| 2 | The classical Hough solver `detect_court_homography` returned `None` on **17 of 17** G140 frames, **0 of 51** calls, on frames SELECTED for paint-corner visibility. Error against the 11.39 px label floor is undefined, not zero. | G192b |
| 3 | A homography from four HAND-LABELLED paint corners projects correctly on all 17 frames. The three-point arc, sidelines and centre circle were NOT used in the fit and land on the painted geometry in 3 of 5 evenly spaced eye checks (2 tight-crop indeterminates, 0 clean mismatches). **The ceiling is DETECTION, not geometry.** | G196 |
| 4 | Learned court keypoints were CLOSED AT LIMIT for tennis: PCK@7px 0.0774 / 0.0355 on two held-out matches, median 17.4 px, and **zero frames solved by the model that the classical did not**, both folds. Sub-pixel refinement falsified the quantisation hypothesis. | G31 |
| 5 | A naive local-response corner detector for basketball scored **recall 0/68, precision 0/1,700** at 12 px. That closes THAT detector, not every corner method. | G141 |
| 6 | NCAA uses a **12-ft** lane, WNBA a **16-ft** lane. Confirmed in code: `line_calibration.py:20-32` gives `nba_wnba` lane at y=17/33 and `ncaa_legacy` at y=19/31. One court model silently corrupts one league. | G196, `domains/basketball/tracking/line_calibration.py` |
| 7 | The route is non-deterministic and every RNG hypothesis is eliminated. The spread is SPORT-DEPENDENT: wnba 9 pct on n=3, **ncaa_basketball 8.9x (88 to 787 rows)**, soccer 5.8x, on identical commands. cuDNN-benchmark-off plus `cv2.setRNGSeed` still varies. | G190, G193, G195, G191 |

Two standing constraints every proposal trips over.

- **The frozen bars** (`scripts/platformkit/tracking_harness.py:24-54`): basketball/wnba `min_players 6,
  coverage_min 0.60, oob_max 0.05, jump_p95_max 6.0 ft, ball_valid_min 0.30`, bounds `(0,94,0,50)`; tennis
  `coverage_min 0.90`; soccer and football `min_players 14, coverage_min 0.85`; baseball `min_players 2,
  coverage_min 0.70`. Q3 forbids moving any of them.
- **Ultralytics is AGPL-3.0 and it is what the route runs today** (`yolov8n.pt`). Verified 2026-09-03 via
  `api.github.com/repos/ultralytics/ultralytics/license`: unchanged, AGPL-3.0 plus a paid Enterprise option.
  Ultralytics further states that "All Ultralytics YOLO trained models fall under the AGPL-3.0 License by
  default" (<https://www.ultralytics.com/license>), so **our own fine-tuned weights would inherit it**. That
  is stronger than this repo previously recorded. An Apache-2.0 YOLOX shim already exists, unused, at
  `scripts/platformkit/detection/shim.py:3`.

---

## 0b. The finding that reframes every SOTA question below

Coverage is denominated on frames. On **source-decoded** frames the frozen bars are already unreachable with
a perfect solver, and no imported method changes a denominator:

| Sport | Frozen `coverage_min` | Measured share of decoded frames where the geometry is visible at all | Verdict |
|---|---:|---|---|
| Basketball | **0.60** | **0.462**, Wilson [0.396, 0.529], 97/210 source-decoded frames (G136, caveated at 66.7 pct blind agreement) | Upper CI bound below the bar |
| Tennis | **0.90** | **0.4167** [0.362, 0.473] on one clip (G34) and **0.3767** [0.324, 0.433] on another with agreement 49/50 (G161) | Unreachable by more than 2x |

So the denominator, not the calibrator, decides whether any of this can pass. G197 added
`coverage_attempted_frames_pct` and `ball_valid_attempted_frames_pct` (present at `tracking_harness.py:67,125`)
but its register row still reads OPEN/pending, so the register is stale against the code.

**And the segmenter that would supply the honest denominator is not independent of the tracker.**
`src/pipeline/unified_pipeline.py:992` `_is_gameplay` returns True when a YOLO person count reaches
`MIN_GAMEPLAY_PERSONS = 3` (`:384`), then trusts that verdict for `_GAMEPLAY_CACHE_FRAMES = 90` frames
(`:385`). A frame the detector under-fires on is classified non-gameplay and leaves the denominator. That is
B1 moved one level up, out of the harness and into the producer. Baseball's `Median person count = 1,
threshold 3` preflight (G191) is the same mechanism refusing whole clips.

---

## 1. Cross-sport picture

| Sport | Where the route dies today | Ceiling | Broadcast SOTA to compare against |
|---|---|---|---|
| Basketball | Corner detection; geometry proven recoverable (G196) | **DETECTION** | Almost nothing. One method (KaliCalib, 2022), trained on FIXED-camera data |
| Tennis | Player selection, plus 90.755 pct corner loss dominated by no-court frames (G182/G184) | DETECTION + SELECTION | One unlicensed repo; no peer-reviewed leaderboard |
| Soccer | Landmark visibility: `>=4` in **0 of 100** frames (G91) against `MIN_LANDMARKS = 5` | **FOOTAGE**, not solver | The richest literature of any sport |
| Baseball | Route preflight; 0/0/0 rows on 3 runs (G191) | **STRUCTURAL** from the CF camera | None found. arXiv exact-phrase total = 0 |
| Am. football | Absolute line identity; numerals read at 12.39 pct | DETECTION of identity | None peer-reviewed; commercial systems use PTZ encoders |

---

## 2. Basketball (NBA, NCAA, WNBA)

**(a) Published SOTA.** For registration there is essentially one modern public method: **KaliCalib**
(MMSports 2022, <https://arxiv.org/abs/2209.07795>), a ResNet-18 + U-Net predicting 91 court keypoints plus 2
basket keypoints at 960x540. **Its accuracy is not quotable**: the paper reports test MSE 126.61 cm and
challenge 140.14 cm against a 592.48 cm baseline, while its own README reports 107.78 mm and 73.16 mm. Those
disagree in units and in value, so this document records NOT VERIFIED rather than pick one. The decisive
point is upstream of accuracy anyway: it trains on the DeepSportradar camera-calibration split (728
image+calibration pairs, 480/164/84/84) and those images come from the **Keemotion FIXED camera system**
(65-265 px/m, <https://ispgroup.gitlab.io/code/deepsport/>). It is not broadcast moving-camera data. **No
public broadcast-basketball dataset with ground-truth camera parameters was located, and no basketball
calibration leaderboard has been active since MMSports 2022.**

For tracking, SportsMOT (ICCV 2023, <https://arxiv.org/abs/2304.05170>) is the only benchmark with a
basketball subset drawn from NBA/NCAA YouTube footage: 240 clips, 150,379 frames, 1,629,490 boxes.
**Basketball is the hardest of its three sports.** The only published per-sport table (Table 4, MixSort alpha
ablation) gives best basketball HOTA **66.2** against volleyball 76.9 and football 73.2 for the same tracker.
Pooled over all three sports the leaderboard runs far higher: Deep-EIoU 77.2 HOTA
(<https://ar5iv.labs.arxiv.org/html/2306.13074>), CAMELTrack 80.3, and the server-verified CodaLab top entry
85.63 (<https://codalab.lisn.upsaclay.fr/competitions/12424>). **Plan against 66.2, not against 85.**
Everything else basketball-labelled is fixed or drone camera and so is not our problem (TeamTrack CVPRW 2024,
TrackID3x3 MMSports 2025, Basketball-SORT on a private fixed set).

**(b) Licence.** KaliCalib is CeCILL-2.1 (strong copyleft) and its data is CC-BY-NC-SA: doubly blocked,
unchanged from G09. **New since G09 and material: KpSFR (Chu et al., CVPRW 2022) is MIT**, with public
weights and a public 3,812-image TS-WorldCup set (`api.github.com/repos/ericsujw/KpSFR/license` returns
`MIT`). G09 never listed it. It is soccer-trained, so the weights are the wrong domain, but it is the
permissive keypoint-registration architecture G09 concluded did not exist. PnLCalib is confirmed **GPL-2.0**
today by SPDX; NBJW is **NOASSERTION** (GPLv2 text plus a citation clause), which is worse than plain GPL
because it is not a clean grant. GPL here is a CONSTRAINT, not a blocker: the papers may be read, cited and
reimplemented; the code may not be vendored into a repo intended for a non-copyleft surface. Deep-EIoU has
**no LICENSE file at all** (API 404), so the highest-profile sports tracker is unusable as code even though
its method is reimplementable.

**(c) Data we do not have, and the cheapest honest evaluation.** We have 68 pixel targets across 17 frames
with a measured p90 label repeatability of 11.39 px (G140). The adjudication withdrew "no new labelling is
needed" as the plan's single most concrete over-read, and it was right: 17 frames is an evaluation set, not a
training set. So the cheapest path is not to train anything. It is to ask whether ANY licence-clean
primitive, run zero-shot, proposes four paint corners within 11.39 px on the same 17 frames G196 already
solved. That reuses committed ground truth (`g140_corner_targets/corner_pixel_targets.csv`, 68 rows verified
present today), needs no labelling, no GPU, no pod deploy, and scores on the identical protocol G141 used, so
the two compare directly. A second still-local tier sits behind it: `g130_recensus/source_decodes/` holds
**227 committed frames** (122 ncaa_basketball, 105 wnba).

**(d) Falsifiable test.** A learned or imported basketball calibrator beats what we have if and only if, on
held-out clips, **the count of frames it solves that the classical route does not is at least 30** (the
sampling rail), with the projected three-point arc agreeing with the painted arc on 5 evenly spaced renders.
That is deliberately G31's own metric, because G31 scored **zero** on it for tennis. Any learned-calibration
proposal must cite G31 and name what differs. Three differences are available and each is checkable: (i) G196
established a validated target for basketball that tennis never had, namely that four correct paint corners
suffice; (ii) the paint rectangle is aperiodic and locally compact, whereas G31 regressed 14 points spread to
the image horizon; (iii) KpSFR gives an MIT architecture with a published recipe, whereas G31 was bespoke.
**None of those three is evidence that a retry would work.** Without a passing step 2 below, a learned
basketball calibrator is not credible.

---

## 3. Tennis

**(a) Published SOTA.** Registration: the de-facto standard is one GitHub repo,
`yastrebksv/TennisCourtDetector`, a TrackNet-style heatmap net over 14 court keypoints trained on 8,841
images at 1280x720 (75/25 split, all surfaces). README results at a 7 px threshold: precision **0.936** /
accuracy **0.933** / median 2.83 px base, rising to **0.963 / 0.961 / 1.83 px** with keypoint refinement plus
homography snapping. The classical reference is still Farin et al., SPIE 5307 (2004): colour/texture
line-pixel classification, Hough, then combinatorial court-model matching; no accuracy figure surfaced, NOT
VERIFIED. Two 2024-2025 arXiv entries exist (2404.06977, 2511.04126) and **neither reports a number**. Ball
tracking is the one genuinely solved, benchmarked and permissive piece: **WASB** (BMVC 2023,
<https://papers.bmvc2023.org/0310.pdf>, repo `nttcom/WASB-SBDT` verified **MIT**) reports tennis F1 **95.6** /
accuracy 91.8 / AP 94.2 at 4 px, against TrackNetV2 89.4 / 81.4 / 80.6; it also ships a basketball ball set of
275,328 annotated images (dataset licence NOT VERIFIED). **There is no published tennis player-tracking
benchmark at all**: tennis is absent from SportsMOT, TeamTrack and SoccerNet.

**(b) Licence.** `TennisCourtDetector` has no LICENSE file (API 404), so code, weights and the 8,841-image
set are all-rights-reserved by default. A HuggingFace mirror tags the dataset MIT; that is the uploader's
assertion and does not bind the author, the same "mirror tag is not provenance" trap already in our ledger.
Unchanged from G09: BLOCKED. WASB (MIT) is the one clean asset in tennis and it addresses ball, not court.

**(c) Data and cheapest honest evaluation.** Tennis is the sport where we already spent the
learned-calibration budget and got a null. G31 trained on 2,013 unique frames; the published set is about
6,631 training images, so we were at roughly a quarter of the published label volume and 12x worse on the
identical metric (PCK@7px 0.077 against 0.933, same 7 px threshold, same 1280x720). Whether label volume
explains a 12x gap is NOT VERIFIED, and G31's own renders argue against it: the model landed every keypoint
on the correct intersection on both held-out tournaments, so it failed on precision, not comprehension. The
cheaper row is upstream of calibration entirely, and G18 and G38 both point at selection.

**(d) Falsifiable test.** Selection is the cause if and only if `oob_pct` falls on the 15 frozen G18 ranges
when the selector stops preferring the wrong box, all five current range failures being `oob`. **Premise
flag, to be re-measured before any work (Q8/S2):** the adjudication states
`domains/tennis/tracking/adapter.py:191` keys selection on box AREA. Read today, line 192 keys on **centroid
continuity** (`-min(norm(center - prior))`) and falls back to area only when `self._centroids` is empty, on
the bootstrap frame. Either the file moved since the adjudication was written, or the adjudication described
the fallback. If the second, the failure mode is worse than stated: a wrong bootstrap pick is then LOCKED IN
by continuity for the rest of the clip.

---

## 4. Soccer

**(a) Published SOTA.** The richest literature, and the one place where a published method would be a real
import. PnLCalib (GPL-2.0, <https://arxiv.org/html/2404.08401v4>): SoccerNet-2022 test-centre JaC@5 **80.6**;
WorldCup-2014 JaC@5 **85.2**, IoU_part **97.0 pct**, projection error mean **0.60 m**. TVCalib (MIT code):
SN-Calib centre Acc@5 **57.6 pct** with predicted segmentation, WC14 Acc@5 39.9. NBJW: SoccerNet-Calibration
test JaC@5 73.7, completeness 77.5. The broadcast-temporal leader is **BroadTrack** (WACV 2025,
<https://arxiv.org/html/2412.01721v1>): SoccerNet-GameState JaC@5 **56.88**, MRE **5.02 px**, completeness
100, against NBJW 37.14 / 10.28 / 93.67. The standalone SoccerNet calibration challenge ran in 2022 and 2023
only (2023 winner Sportlight: combined 0.55 = Acc@5 73.22 x completeness 75.59); since 2024 calibration is a
subtask inside Game State Reconstruction, whose winners have **plateaued**, 63.81 GS-HOTA in 2024, 63.90 in
2025.

**Two published results matter more to us than any headline number.** First, on tight central views every
method collapses: PnLCalib JaC@5 **22.4 pct** with MRE 12.8 px, TVCalib JaC@5 **10.2 pct** with MRE 28.8 px
(<https://arxiv.org/html/2504.20052v1>). Broadcast basketball is a tight view. Second, the ProCC protocol
paper (<https://arxiv.org/html/2404.09807v1>) shows WorldCup-2014's own **homography** annotations cap at
JaC@5 **67.4 pct** against 92.5 pct for pinhole-plus-radial-distortion annotations. There is a label-model
ceiling independent of method, and our whole stack is homography-only.

**(b) Licence.** PnLCalib GPL-2.0; NBJW NOASSERTION; `sn-gamestate` GPL-3.0 (and its default pipeline pulls
Ultralytics YOLO11, AGPL); `sn-calibration` no licence; the Sportlight winner has neither licence nor weights;
SoccerNet video is NDA-gated with no published open licence. TVCalib code is MIT with an unlicensed
checkpoint. **KpSFR (MIT) plus its TS-WorldCup download is the only fully permissive registration stack with
public weights.**

**(c) Data and cheapest honest evaluation.** Nothing to evaluate yet, and that is the finding: G91 measured
`>=4` canonical landmarks in **0 of 100** frames and `>=5` in 0 of 100, against `MIN_LANDMARKS = 5` verified
today at `domains/soccer/tracking/geometry.py:14`. Importing a method changes the detector, not the
visibility. Note also the trap already recorded: the centre circle alone yields three **collinear** points
(centre, top, bottom all on the halfway line), and a homography needs four correspondences in general
position with no three collinear, so midfield frames are structurally unsolvable from that landmark set at
any detector quality. The cheapest evaluation is the reopening condition already in the register, run
**conditioned on penalty-box frames** rather than uniformly, because the wide-pitch view share was measured
at 0.65 [0.594, 0.702] while the landmark count was 0. Those two numbers are in tension and one census
settles it.

**(d) Falsifiable test.** A soccer calibrator is worth funding if and only if a penalty-box-conditioned census
of at least 100 frames finds `>=5` canonical landmarks in at least 30. Below that there is no population to
solve on, and the question is corpus acquisition, not method.

---

## 5. Baseball

**(a) Published SOTA.** None. arXiv exact-phrase queries `"baseball" AND "homography"` and `"baseball" AND
"field registration"` both return **total 0**, while the control `"soccer" AND "homography"` returns hits, so
the query mechanics work; the community survey list `cemunds/awesome-sports-camera-calibration` carries zero
baseball entries. Statcast is **not** broadcast: MLB/Hawk-Eye run **12 permanently installed cameras per
park** since 2020, 5 at 100 fps for pitch tracking and 7 at 50 fps for players. What exists from broadcast is
pose and activity only: MLB-YouTube (CVPRW 2018; 4,290 segmented and 2,128 continuous clips, activity labels,
no boxes and no geometry), PitcherNet (CVPRW 2024, single-athlete kinematics), a 2026 injury-screening paper.
The strongest external signal is what the professionals do: MLB's own strike-zone graphics use
**pan/tilt/zoom-encoded cameras**, not landmark registration.

**(b) Licence.** Nothing to license. The one open toolkit, **BaseballCV**, is dual-licensed **AGPL-3.0 plus a
separate commercial licence**, ships detection weights and raw broadcast frame sets, publishes **no
performance metrics**, and has **no registration or calibration tooling at all**. AGPL is a constraint on a
product surface, not a blocker on a measurement lane.

**(c) Data and cheapest honest evaluation.** The route never reaches calibration: it exits 4 at the
person-count preflight in about 8 seconds, 0 rows on 3 of 3 runs (G191). The geometry is structurally
hostile, and two independent readings now agree. Ours (`CALIBRATION_STRATEGY_2026-09-02.md` section 1.4):
rubber, mound circle, plate and batter's boxes lie in a narrow near-collinear band along the pitch axis, so
four non-collinear ground-plane correspondences do not exist to find. The external derivation adds a sharper
failure mode: the reliably visible planar landmarks span roughly 13 ft by 6 ft viewed from 400+ ft and would
have to be extrapolated across a 90 ft diamond, which is a conditioning catastrophe rather than a rank
deficiency; and the mound sits up to **10 inches** off the field plane directly between camera and plate, so
no mound feature is valid for a single ground-plane homography. Cheapest evaluation: a shot-class census of
the **high-home wide** share, currently unmeasured, which the pitch-view gate selects against.

**(d) Falsifiable test.** `court_feet` baseball is reachable if and only if the high-home wide share, over segmented
gameplay frames, is at least the frozen `coverage_min` of **0.70**. Below that a perfect solver still cannot pass the bar, and METRIC_LOCAL is the terminal rung for this sport.

---

## 6. American football

**(a) Published SOTA.** No peer-reviewed broadcast field-registration benchmark exists. arXiv `"american
football" AND "homography"` returns **total 0**; the one hit for `"football field" AND "camera calibration"`
is a soccer paper. Beware the naming trap: "Automated Top View Registration of Broadcast Football Videos"
(arXiv 1703.01437) is soccer. NFL Next Gen Stats is **RFID, not vision**: 20-30 ultra-wideband receivers per
venue, 2-3 tags per player, 10 Hz. The only public labelled broadcast-ish sets are three Kaggle NFL
competitions (Impact Detection 2020-21, Helmet Assignment 2021, Player Contact Detection 2023), whose winners
registered by **matching the NGS position point cloud to detected helmets, explicitly not by detecting field
lines**. Commercial first-down-line graphics have used **PTZ-encoded cameras plus crown correction** since
1998. One promising lead could not be fetched (Pandya and Nandy, CVPRW CVSports 2023, "Homography Based
Player Identification in Live Sports"): sport, landmarks and numbers all NOT VERIFIED.

**(b) Licence.** The Kaggle NFL competition data is **non-commercial only, with an explicit
no-redistribution clause**, so the one public labelled corpus cannot seed a shipped model.

**(c) Data and cheapest honest evaluation.** `domains/football/tracking/geometry.py` already fails closed by
design: `homography_from_yard_lines` returns `independent_scale_unavailable` in all cases, because naming two
hash rows would assume the scale the solve is meant to recover. That refusal is now backed by an explicit
degeneracy argument. A homography has 8 DOF and needs four correspondences in general position with no three
collinear; the dual for lines is four lines with no three **concurrent**, and mutually parallel world lines
are concurrent at their shared ideal point. Yard lines are one parallel pencil, so **no number of yard lines
can ever determine H**. The residual ambiguity is 3-DOF: `x' = x`, `y' = d*x + e*y + f`, that is you recover
how far downfield a player is but not how far from the sideline, not the lateral scale, and the two errors
are coupled. Two lines from a second pencil (both sidelines, or both hash rows) close it. Our own
measurements say exactly where that fails: hash row plus near sideline **0 of 60**, adjacent yard-line pairs
at two depths **1 of 60**, white border 8 of 60, numerals read at **12.39 pct** valid-parse over 444 crops,
frames with >=2 numerals naming different yard lines **13 of 74** against a pre-registered 30 of 74, rigid
solve **0 of 175**. The single kept re-entry is already sized: a real-labelled 5-way numeral classifier whose
per-crop accuracy must roughly double, 0.124 to about 0.22.

**(d) Falsifiable test.** Football re-enters if and only if a labelled 5-way numeral classifier reaches
per-crop accuracy **>= 0.22** on held-out crops, which is the pre-registered gate that sizes the frame-level
gate. Note the second, independent failure this does not address: all yard lines are visually identical, so a
well-conditioned H can still be wrong by a multiple of 5 yards. Any football row needs a discrete labelling
step scored separately from the continuous fit.

---

## 7. Cross-cutting: detection and association

**Detection licences, verified 2026-09-03.** Ultralytics YOLOv8/11/26 AGPL-3.0 including derived weights.
Permissive alternatives with public COCO weights: **YOLOX Apache-2.0**, **RT-DETR / RT-DETRv2 Apache-2.0**,
**RF-DETR Nano through Large Apache-2.0** (XLarge and 2XLarge are PML 1.0, proprietary). Two corrections to
`docs/research/organization-sprint/GITHUB_RESEARCH_sports_cv_2026-09-02.md`: Detectron2 model-zoo weights are
**CC BY-SA 3.0**, not "research-only"; torchvision is BSD-3 with an explicit disclaimer that its weights may
carry dataset-derived terms you must check yourself.

**Association licences.** ByteTrack, BoT-SORT, OC-SORT, Deep OC-SORT and MixSort are all **MIT**; CAMELTrack
is **Apache-2.0** with weights on HuggingFace and is the highest-scoring permissive sports tracker found
(SportsMOT HOTA 80.3). OSNet/torchreid is MIT. **Deep-EIoU has no licence file.**

**A correction we owe our own record.** `TRACKING_ARCHITECTURE_PLAN_2026-09-03.md:46` quotes "Deep-EIoU
reports HOTA 77.2 on SportsMOT and 85.4 on SoccerNet". The 77.2 reproduces. The SoccerNet figure (HOTA
85.443, DetA 99.236) is computed with **oracle detections supplied by the dataset**, which the paper states
plainly. It is not an end-to-end number and must never be compared with anything we measure. Separately,
every high-scoring sports-MOT weight is trained on non-commercial data (SportsMOT CC BY-NC 4.0, SoccerNet
NDA-gated, MOT17/MOT20 and MSMT17 research-only), so permissive *code* does not yield usable *weights*: a
shipped detector or re-ID must be retrained on frames we hold.

**Why association is nonetheless not the next move.** The adjudication already withdrew "a generation behind
on association" for basketball: the route runs per-track Kalman filters, Hungarian assignment, an appearance
model, ByteTrack-style matching and OSNet re-ID. The measured cause at frame 474 was SELECTION (15 raw person
boxes emitted, 2 or 3 kept), not detection and not association.

---

## 8. RECOMMENDED SEQUENCE

Ids below are PROPOSALS in the G210 block; the orchestrator allocates and lanes never invent (S5). **Id hazard
found while writing this:** `TRACKING_GAPS_2026-09-01.md:291` still reads `NEXT_GAP_ID: G198`, but git log
shows G198-G202 already allocated by a peer session (`04f6a1888`, `9b1c52b75`, `67875593a`, `0c4468c5b`,
`1c8ba9ad8`). Reconcile the register before any dispatch. Cheapest decisive first.

**Step 1 -- G210, tennis, minutes, local.** *Does the tennis selector still key on box area?* Premise
re-measurement only. The adjudication says `adapter.py:191` keys on area; today `:192` keys on centroid
continuity with area as the bootstrap fallback. **STOP: if the premise is falsified, report FALSIFIED and
close the row. That is a valid result and it costs one file read.** If confirmed, the follow-on metric is
`oob_pct` over the 15 frozen G18 ranges, before = 5 of 15 range failures all `oob`, bar = fewer, n = 15
(CONSTRUCT).

**Step 2 -- G211, basketball, hours, local, no training, no pod.** *Does any licence-clean zero-shot
primitive propose four paint corners within the 11.39 px label floor?* Candidates, all SHIP-OK or MIT: ELSED
(Apache-2.0), DeepLSD / HAWP / M-LSD (MIT or Apache code, Wireframe-trained weights so AMBER), KpSFR (MIT,
soccer weights, run purely to see whether the architecture proposes anything on a court), and classical
corner refinement seeded by G134's stable line groups. Metric = frames with all four labelled roles matched
within 12 px, denominator 17 (CONSTRUCT, exhaustive); secondary = per-corner recall over 68 and precision
over proposals, the identical protocol to G141 so the two compare. Before: G141 0/68 and 0/1,700; G192b 0 of
17 frames solved. Bar: **>= 1 of 17**. **STOP: 0 of 17 for every candidate closes the ZERO-SHOT corner route
AT LIMIT.** It does not close labelling and must not be read as closing it.

**Step 3 -- G212, all sports, one census, local.** *What is the gameplay share under a segmenter independent
of the tracker?* Premise first: `_is_gameplay` gates on YOLO person count (section 0b), so it cannot supply
the denominator G197 needs. Metric = hand-labelled gameplay share over a seeded evenly spaced census of
>= 300 frames, with blind second-pass agreement measured inside the row. Bar: report, do not gate. **STOP: if
blind agreement is under 0.80 the census is CAVEATED and may not be used to set any bar** (no eye criterion
in this programme has yet cleared 0.80: G76 0.686, G85 0.750, G111 0.489, G136 0.667).

**Step 4 -- G213, basketball, local.** Runs only if step 2 cleared its bar. *At what rate does the best
step-2 candidate propose four corners over the 227 committed `g130_recensus` decodes?* Denominator named as
227 decoded frames (H1). Eye check: 5 evenly spaced renders using the projected three-point arc as the
independent marking, which is G196's non-tautology argument. Bar: proposal rate within a factor of 5 of
G136's human reachability, that is **>= 0.0924**; the current line route sits at about 0.012 (G138, 1 of 84
roles available), a factor of roughly 38. **STOP: below 0.0924 the detection route is closed at current
tooling and the only remaining move is labelling.**

**Step 5 -- G214, basketball, human-gated (touches `src/`).** *Does persisting the per-frame solved
homography, failing closed on unsolved frames, plus a projected-feet polygon filter, move a basketball row
from `coordinate_contract` rejection to a scored verdict?* G42 measured 145.7x inflation from a stale
homography carried across unsolved frames, so emitting nothing on an unsolved frame is the contract, not an
option. Report >= 3 runs per clip, never n=1 (B11; ncaa_basketball spreads 8.9x). **STOP: if
`coverage_attempted_frames_pct` stays under 0.60 at `min_players 6`, the shortfall is detection supply, not
persistence, and the row returns to step 4.**

**Step 6 -- G215, soccer, one census.** *Conditioned on penalty-box frames rather than uniform sampling, are
`>=5` canonical landmarks ever visible?* n >= 100. **STOP: fewer than 30 of 100 closes soccer AT LIMIT on
this corpus, and the next question becomes corpus acquisition rather than method.**

**Step 7 -- G216, football, labelling project.** *Does a real-labelled 5-way numeral classifier reach
per-crop accuracy >= 0.22?* **STOP: below 0.22 football stays NO-BENCHMARK.** Record in the row that yard
lines alone are provably insufficient (section 6c), so hash rows or sidelines are mandatory, and that we
measured hash row plus near sideline at 0 of 60.

**Step 8 -- G217, baseball, one census.** *What share of segmented gameplay frames is the high-home wide
shot?* **STOP: below the frozen `coverage_min` of 0.70, `court_feet` baseball cannot pass with a perfect
solver and METRIC_LOCAL is the terminal rung.**

**Deferred deliberately: the detector swap and the association upgrade.** Both only after one basketball row
passes on the fixed denominator, and the detector swap should then be filed as a LICENCE row (AGPL to
Apache-2.0, using the existing `scripts/platformkit/detection/shim.py`), kept separate from any quality
argument. The measured cause today is selection, not detection.

---

## 9. What we honestly do not know

- **Whether any published number transfers to our footage.** Every figure in sections 2 to 6 was measured on
  the method's own corpus. Not one has ever been reproduced on a frame we hold. This is the single largest
  unknown and it applies to every row above.
- The residual source of route non-determinism, after G190, G193 and G195 eliminated every RNG hypothesis.
- Whether any zero-shot primitive proposes basketball paint corners. G141 bounded one naive detector only.
- The four-corner and court-visible share over properly SEGMENTED gameplay frames, for every sport (only the
  decoded-frame shares are measured), and whether soccer's 0 of 100 is a corpus or a sampling property.
- Whether G31's 12x gap against the published tennis number is explained by label volume. Its own renders
  argue it is a precision failure, not comprehension.
- Whether ImageNet-pretrained backbones are shippable here. The day-1 plan records an unresolved conflict:
  G31 as trained used `ResNet18_Weights.IMAGENET1K_V1` while the standing rail forbids research-only weights.
- KaliCalib's true accuracy. Its paper and README disagree in value and units, so nothing about basketball
  registration performance is quotable from it.
