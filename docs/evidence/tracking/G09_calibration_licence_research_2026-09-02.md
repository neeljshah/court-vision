# G09 -- broadcast camera-calibration assets: licence research (2026-09-02)

Lane: G09-CALIBRATION-LICENCE-RESEARCH. Research only; no training, no model
downloaded, no dataset downloaded. Method: GitHub licence API
(`api.github.com/repos/<r>/license`) plus the raw LICENSE / terms page fetched
live on 2026-09-02. Where the API said `NOASSERTION` the LICENSE text was read.
Repos that 404 on the licence endpoint were re-queried for existence so that
"no licence file" is distinguished from "wrong path".

Standing rule (from `sports_cv_licensed_assets_2026_09_01`): MIT / Apache-2.0 /
BSD are usable; NO STATED LICENCE = NOT usable; GPL / CeCILL are copyleft and
unusable in a closed product. A licence on CODE never carries the WEIGHTS, and a
permissive licence on code trained on research-only data is AMBER, not green.

## Classification key

- SHIP-OK -- permissive (MIT / Apache-2.0 / BSD / CC-BY), may enter the product.
- AMBER -- permissive artifact, but its TRAINING DATA is research-only or
  unlicensed; usable only if we retrain the architecture on our own frames.
- DATA-RESEARCH-ONLY -- may inform design and may be quoted as a published
  reference number; may NEVER train a shipped model.
- BLOCKED -- non-commercial, copyleft, or no stated licence at all.

## Table A -- calibration / registration code + weights

| asset | url | licence clause (quoted, <=15 words) | class | provenance flag |
|---|---|---|---|---|
| SCCvSD (Chen and Little, synthetic camera search) | github.com/lood339/SCCvSD | "BSD 2-Clause License / Copyright (c) 2019, Jimmy Chen" | SHIP-OK | AMBER on the shipped feature files: the synthetic camera distribution is fitted to WorldCup2014 annotations. Regenerate the distribution from our own frames and it is clean. |
| TVCalib | github.com/mm4spa/tvcalib | licence API: `MIT` (code) | code SHIP-OK, weights BLOCKED | `train_59.pt` has no stated weight licence (ledger 2026-09-01, unchanged). Segmentation stage is SoccerNet-trained. |
| PnLCalib | github.com/mguti97/PnLCalib | licence API: `GPL-2.0` | BLOCKED | copyleft |
| No Bells Just Whistles (NBJW) | github.com/mguti97/No-Bells-Just-Whistles | "All the scripts ... are Free Software under the GNU General Public License, version 2" | BLOCKED | copyleft; API reported NOASSERTION, LICENSE text read directly |
| KaliCalib | github.com/CEA-LIST/KaliCalib | licence API: `CECILL-2.1` | BLOCKED | copyleft AND trained on DeepSportRadar (CC-BY-NC-SA). Doubly blocked. |
| sportsfield_release (Jiang et al. / Sportlogiq) | github.com/vcg-uvic/sportsfield_release | "ACADEMIC OR NON-PROFIT ORGANIZATION NONCOMMERCIAL RESEARCH USE ONLY" | BLOCKED | NEW verdict this lane. This repo is also the usual redistribution channel for the WorldCup2014 annotations -- see Table B. |
| Sportlight (SoccerNet-2023 calibration winner) | -- | no licence file (API 404, verified 2026-09-01) | BLOCKED | unchanged |
| SoccerNet sn-calibration (baseline + eval code) | github.com/SoccerNet/sn-calibration | repo exists, `license: None` -- no LICENSE file | BLOCKED | NEW verdict. Only `ChallengeRules.md`. The separate `SoccerNet` PyPI downloader package IS MIT, but that licenses the downloader, not the data. |
| SoccerNet sn-gamestate (game-state reconstruction, incl. calibration) | github.com/SoccerNet/sn-gamestate | licence API: `GPL-3.0` | BLOCKED | NEW verdict; copyleft |
| TennisCourtDetector | github.com/yastrebksv/TennisCourtDetector | repo exists, `license: None` -- no LICENSE file | BLOCKED | NEW verdict. Code, weights and the 8,841-image dataset are all unlicensed. Its published numbers are still quotable as a target (Table D). |
| TennisProject (same author, tracking) | github.com/yastrebksv/TennisProject | repo exists, `license: None` | BLOCKED | NEW verdict |

## Table B -- datasets

| dataset | url | terms clause (quoted, <=15 words) | class | notes |
|---|---|---|---|---|
| SoccerNet (all tasks incl. calibration-2023) | soccer-net.org/faq | "meant for research purposes, it is not intended for commercial purposes" | DATA-RESEARCH-ONLY | NDA-gated; the FAQ states the videos carry European-league copyright and the NDA exists to prevent redistribution. Scale, per the PnLCalib paper: 22,816 images; SN22-test-center 1,454. |
| WorldCup2014 (Homayounfar, CVPR 2017) | cs.toronto.edu/~namdar (paper) | no licence or terms page located | BLOCKED | 395 images total (209 train/val from 10 games, 186 test from 10 others). In practice redistributed inside sportsfield_release, whose licence is NONCOMMERCIAL -- so the copy everyone actually uses is non-commercial. |
| TS-WorldCup | (via PnLCalib / NBJW repos) | not fetched | BLOCKED pending | derived from WorldCup2014 footage; inherits the same defect. |
| DeepSportRadar basketball-instants | kaggle.com/datasets/deepsportradar/basketball-instants-dataset | "made available for non-commercial research only under the licence cc-by-nc-sa" | BLOCKED | the only serious basketball court-keypoint corpus; it is what KaliCalib trained on. |
| Roboflow Universe basketball court-keypoint sets | universe.roboflow.com (several) | uploader-applied `CC BY 4.0` | AMBER, not SHIP-OK | Two problems: (a) tiny -- 80 to 351 images each; (b) an uploader's CC-BY tag on NBA broadcast frames does not launder the broadcaster's copyright in those frames. Same class as the "HuggingFace mirror tag is not provenance" caveat already in the ledger. |
| Wireframe dataset (Huang et al.) | github.com/huangkuns/wireframe | repo exists, `license: None` | BLOCKED | matters only as the provenance of the line-detector weights in Table C. |
| baseball field-keypoint corpus | -- | none found | does not exist | no public broadcast baseball calibration set was located. |

## Table C -- generic line / keypoint detectors (sport-blind)

| asset | url | licence | class | provenance flag |
|---|---|---|---|---|
| ELSED | github.com/iago-suarez/ELSED | `Apache-2.0` | SHIP-OK | NO learned weights at all -- purely algorithmic. Zero provenance risk. The cleanest primitive available to us. |
| M-LSD | github.com/navervision/mlsd | `Apache-2.0` | code SHIP-OK | AMBER weights: trained on Wireframe (unlicensed). |
| LETR | github.com/mlpc-ucsd/LETR | `Apache-2.0` | code SHIP-OK | AMBER weights: Wireframe / YorkUrban. |
| DeepLSD | github.com/cvg/DeepLSD | `MIT` | code SHIP-OK | AMBER weights: README states the two checkpoints are "trained respectively on the Wireframe and MegaDepth datasets". |
| HAWP | github.com/cherubicXN/hawp | `MIT` | code SHIP-OK | AMBER weights: Wireframe. |
| OpenCV `LineSegmentDetector` | opencv.org | NOT VERIFIED THIS LANE | unknown | Recorded landmine only: LSD was pulled from OpenCV over the original implementation's AGPL and later reimplemented. Verify the version in our env before shipping it. |

Reading of Table C: every learned line detector we may legally ship carries the
same unlicensed Wireframe training set behind its weights. So the only
zero-doubt line primitive is ELSED (or our existing classical detector), and any
learned detector must be retrained on our own frames before it ships.

## Table D -- published accuracy, so the register can carry an achievable LIMIT

| sport | benchmark | best published number | source |
|---|---|---|---|
| soccer | SoccerNet-2023 calibration challenge | winner Sportlight: combined 0.55, JaC@5 73.22, completeness 75.59. Provided baseline: 0.08 / 13.54 / 61.54. | sn-calibration README leaderboard |
| soccer | WorldCup2014 (186 test images) | PnLCalib SV+PnL: IoU_part 97.0 pct, IoU_whole 93.4 pct, projection error 0.60 m | arxiv 2404.08401v3 tables |
| soccer | WorldCup2014, older synthetic-only method | SCCvSD README: mean IoU 0.948, median IoU 0.964 (refined homography) | SCCvSD README |
| tennis | 8,841-image court set, 14 keypoints, 7 px threshold | precision 0.936, accuracy 0.933, median distance 2.83 px | TennisCourtDetector README |
| basketball | DeepSportRadar (KaliCalib) | NOT FETCHED -- asset is blocked either way, so the number was not chased | -- |
| baseball | -- | no benchmark exists | -- |

The tennis row is the one directly comparable to our own instrument: the judge
in `synthcal_w7_verdict_2026-09-01.md` measures PCK@7px on 1280x720, and that
paper's set is 1280x720 at the same 7 px threshold.

## Per-sport compliant route

**Tennis.** Everything published is blocked (TennisCourtDetector has no licence
at all), so the route is self-labelled keypoints on OUR broadcast frames feeding
a retrained heatmap net, with the classical detector as both the bootstrap
labeller and the fallback. The published set is 8,841 images / 14 points /
75-25 split for 0.933 accuracy at 7 px across all three surfaces; we need fewer
surfaces, so the first checkpoint target is roughly 2,000 to 2,500 self-labelled
frames sampled sequentially (never linspace -- G18) across at least 3 matches,
bootstrapped by `domains/tennis/tracking/court_lines.py` + `camera_lock.py`
proposals and hand-adjudicated through the render-and-look loop already used in
the W7 verdict. LIMIT to carry in the register: accuracy@7px 0.93 and median
2.83 px are the published ceiling at 8.8k labels; anything we claim below ~2k
labels should be held to a materially weaker bar, and the operative gate stays
the depth-band ft error against the standing classical 5.28 ft median, not PCK
(the judge's PCK has a 0.40 floor from solve landmarks).

**Soccer.** SoccerNet is DATA-RESEARCH-ONLY by its own FAQ and every strong
public model on it is GPL, CeCILL or unlicensed, so no learned soccer
calibrator can be imported. The compliant route is SCCvSD's shape: BSD-2-Clause
code, a camera distribution regenerated from OUR OWN broadcast frames rather
than from WorldCup2014 annotations, synthetic edge images rendered from the
known FIFA pitch template, and retrieval-plus-refinement against ELSED lines.
This is a licence-clean synthetic route in a way our failed synthcal was not
constrained to be -- and note W7 failed on convergence, not on licensing, so
SCCvSD's retrieval formulation is a genuinely different bet from W7's direct
heatmap regression. Label count: WorldCup2014 reached IoU 0.95 with 209
training images because the pitch template is strong, so the realistic target is
400 to 800 self-labelled soccer frames for the real-image half, with the
synthetic half unbounded. LIMIT: IoU_part in the 0.95 to 0.97 band is the
published ceiling on WC14-style wide views; the SoccerNet leaderboard's much
harsher JaC@5 of 73.22 is the honest number for arbitrary broadcast frames, and
G08 (homography never locks on isolated frames) must be closed with a
stream-based packet before any of it is measurable.

**Basketball.** The only real corpus (DeepSportRadar) is CC-BY-NC-SA and the
only strong model (KaliCalib) is CeCILL, so both are out; the Roboflow CC-BY
sets are 80 to 351 images and their CC-BY tag does not resolve the broadcast
frames' underlying copyright, so they are AMBER and too small to matter anyway.
Route: self-labelled keypoints on our own frames through the existing
`domains/basketball/tracking/keypoints.py` and
`scripts/platformkit/basketball_keypoint_measure.py`, gated behind G03's
producer fix -- there is no point labelling a court lock while the producer
still writes minimap canvas px under x/y. Label count: KaliCalib's 91-keypoint
formulation is far heavier than we need; a half-court possession lock on the
visible key and three-point arc is a ~10 to 14 point problem, so budget 2,000 to
4,000 self-labelled frames, on the tennis set's scaling. LIMIT: no
broadcast-basketball public benchmark is quotable, so the register should carry
the tennis-derived 7 px accuracy bar as a proxy and mark it EXTRAPOLATED, not
measured.

**Baseball.** No dataset, no model, no benchmark exists publicly, which
retrospectively validates the geometry-first route already shipped (mound-chord
vs rubber scale anchor, G10, 9/36 segments validated). There is nothing to
license and nothing to import. Route: keep the classical anchor, keep failing
closed, and treat the shipped MIT TransNetV2 cut detector as the only external
asset in this sport. Label count: not applicable until a pitch-view classifier
that beats the rejected `hue_geometry` candidate exists (G11); if one is
attempted, the honest budget is a few hundred hand-adjudicated frames per
lighting regime (day / night), since the measured day-vs-night split is the
actual failure axis. LIMIT: none quotable; the register should record
"no public baseball calibration benchmark" rather than an invented bar.

## New verdicts to append to the licence ledger

BLOCKED, newly verified this lane: `vcg-uvic/sportsfield_release` (Sportlogiq
noncommercial), `mguti97/No-Bells-Just-Whistles` (GPL-2.0),
`mguti97/PnLCalib` (GPL-2.0), `SoccerNet/sn-calibration` (no licence file),
`SoccerNet/sn-gamestate` (GPL-3.0), `yastrebksv/TennisCourtDetector` and
`yastrebksv/TennisProject` (no licence file), `huangkuns/wireframe` (no licence
file), WorldCup2014 (no terms), DeepSportRadar basketball-instants
(CC-BY-NC-SA), SoccerNet data (research-only per its own FAQ).

SHIP-OK, newly verified: `lood339/SCCvSD` (BSD-2-Clause),
`iago-suarez/ELSED` (Apache-2.0), `navervision/mlsd` (Apache-2.0),
`mlpc-ucsd/LETR` (Apache-2.0), `cvg/DeepLSD` (MIT), `cherubicXN/hawp` (MIT) --
the last four code-only, weights AMBER on Wireframe.

## Not verified

- The SoccerNet NDA document itself was not opened (it is behind a form); the
  research-only clause quoted above is from the public FAQ page, not the NDA.
  `soccer-net.org/download` returned HTTP 404.
- TS-WorldCup terms were not located; it is marked BLOCKED pending, on the
  inheritance argument from WorldCup2014, not on a fetched clause.
- KaliCalib's reported accuracy on DeepSportRadar was not fetched.
- The OpenCV LSD licence history is recorded from memory as a landmine and was
  NOT checked against the version installed in this environment.
- No weight file for any asset was downloaded, so no weight-level licence was
  inspected beyond what the repos state in text.
