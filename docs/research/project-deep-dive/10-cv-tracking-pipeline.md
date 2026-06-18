# 10 - Computer-Vision Tracking Pipeline (the original NBA data moat)

Scope: how broadcast video becomes tracking data, what the pipeline can and cannot
extract, the known walls/bugs, and an honest ceiling for the CV moat. READ-ONLY
research note. No edge claim is made anywhere; CV here is a *feature-source / data
moat*, not a betting edge. Where CV-derived features touch prediction the honest
verdict (per memory) is they are sparse, partly contaminated, and mostly REJECT.

---

## 1. INVENTORY -- components that EXIST and are USED

### Tracking stack (`src/tracking/`)
- `advanced_tracker.py` (94 KB) -- `AdvancedFeetDetector`, the core MOT class:
  YOLOv8n -> Kalman + Hungarian + HSV/OSNet appearance + gallery re-ID + pose +
  optical flow + per-team color calibration. Entry point `get_players_pos()`.
- `ball_detect_track.py` (54 KB) -- `BallDetectTrack`, dedicated ball detector/tracker
  (separate from the person detector; CSRT + YOLO ball class).
- `event_detector.py` (65 KB) -- `EventDetector`: stateful per-frame classifier for
  shot/pass/dribble + rich events (screen, cut, drive, closeout, rebound, steal,
  block, post-up, help-defense).
- `possession_classifier.py` -- `PossessionClassifier`: geometry-only 7-type
  possession labels + shot-clock/paint-touch/off-ball-distance accumulators.
- `scoreboard_ocr.py` (19 KB) -- `ScoreboardOCR` / `read_scoreboard()`: PaddleOCR(CPU)
  -> EasyOCR fallback; parses clock/shot-clock/score/period from the top strip.
- `jersey_ocr.py` (15 KB) -- `read_jersey_number_with_conf()`, `JerseyVotingBuffer`:
  per-crop digit OCR with confidence-weighted majority vote.
- `player_resolver.py` (35 KB) -- `PlayerResolver`: turns anonymous slots into real
  NBA player IDs via jersey votes + team-color + team-restricted Hungarian assignment.
- `osnet_reid.py` (24 KB) -- `DeepAppearanceExtractor`: OSNet-x0.25 deep re-ID
  (torchreid weights, or a hand-rolled `OSNetX025`, or TensorRT engine), 256-dim L2.
- `color_reid.py` -- `TeamColorTracker`, `dominant_team_color()`, `similar_team_colors()`
  (HSV team signatures; ISSUE-005 similar-uniform handling).
- `court_detector.py` / `rectify_court.py` -- `detect_court_homography()`, panorama
  rectify utilities (SIFT court-line homography to 940x500 canonical court).
- `play_type_classifier.py`, `defensive_scheme_classifier.py` -- derived labels.
- `player_detection.py` (`FeetDetector` base), `player.py` (`Player` slot),
  `player_identity.py` (persist identity map), `video_handler.py` (`VideoHandler`,
  TOPCUT), `cv_quality.py` (per-clip QC), `evaluate.py` (track/eval/gap-fill/self-test),
  `tracker_config.py` (`load_config`).

### Orchestration / consumption (`src/pipeline/`)
- `unified_pipeline.py` (253 KB) -- the orchestrator. Owns frame decode, per-clip
  homography (`_build_2d_map`, `_get_homography`, `_kornia_homography`,
  `_recover_homography`, drift check), the replay/cut suspension logic, possession
  buffering/merge, and the EventDetector/PossessionClassifier wiring. Emits
  `tracking_data.csv`, possession rows, shot log, events log.
- `tracking_feature_extractor.py` (46 KB) -- `extract(game_id) -> {player_id: {feat:val}}`;
  aggregates shot_log / tracking rows into per-player CV features
  (avg_defender_distance, contested_shot_rate, contest_arm_angle, touches, etc.).
- `cv_feature_registry.py` -- writes/reads `cv_features` rows to the DB;
  `has_cv_features()` / `get_cv_features()` gate whether prop models include the CV group.
- `tracking_pipeline.py`, `run_pipeline.py` -- thin runners.

### Downstream consumers
- `src/prediction/prop_pergame.py`, `player_props.py`, `signal_attribution.py`
  read `cv_features` (via the registry) as an optional prop-model feature group.
- `scripts/batch_season.py` shells `unified_pipeline` per clip (subprocess, 4 h timeout).
- DB fact: `data/nba_ai.db` `cv_features` = **17,254 rows / 241 games / 252 distinct
  NBA player IDs** (measured this session; matches JOB_EVIDENCE_PACKET).

---

## 2. HOW IT WORKS -- data flow + key algorithms

End-to-end (matches `docs/architecture/cv-pipeline.md`):

```
broadcast H.264 -> decord/PyAV decode -> YOLOv8n (person cls0 + ball cls32)
  -> SIFT/LoFTR court homography (frame -> 940x500 court)
  -> Kalman predict + Hungarian assign (+ HSV/OSNet appearance, gallery re-ID)
  -> pose (ankles) + optical-flow gap-fill -> court (x,y), speed, possession
  -> EventDetector (shot/pass/dribble/...) + PossessionClassifier (7 types)
  -> jersey OCR votes + team color -> PlayerResolver (slot -> NBA player_id)
  -> scoreboard OCR (clock/score/period)
  -> tracking_data.csv + shot_log + possession/events
  -> tracking_feature_extractor.extract() -> cv_feature_registry -> cv_features (DB)
```

Key algorithm signatures / refs:

- Detection->track cost. `AdvancedFeetDetector.get_players_pos(M, M1, frame, timestamp,
  map_2d, ...)` (`advanced_tracker.py:1135`). Cost matrix is
  `(1 - IoU(kalman_pred, det)) * 0.75 + appearance_dist * 0.25`; gate rejects pairs
  > 0.80; solved by `_assign()` (`:210`, scipy `linear_sum_assignment`, greedy fallback).
  When `similar_team_colors()` fires (hue centroids within 20), appearance weight rises
  to 0.35 / IoU drops to 0.65 (ISSUE-005, `:847`).
- Kalman 6D state `[cx,cy,vx,vy,w,h]`: `_make_kf` (`:104`), `_kf_predict_bbox` (`:132`),
  `_kf_correct` (`:140`). Lost slots survive `MAX_LOST=90` frames then evict to gallery.
- Appearance: `_compute_appearance()` (`:150`) = 96-bin HSV hist + 3 mean-HSV (99-dim,
  L1-norm) over top 70% of crop; EMA update alpha=0.70. `_appear_dist()` (`:184`)
  histogram-intersection. OSNet (256-dim L2) substitutes when weights load
  (`DeepAppearanceExtractor.batch_extract`, `osnet_reid.py:490`).
- Gallery re-ID: `_reid()` (`:1066`); TTL 300 frames; `REID_THRESH=0.45`;
  jersey-number tiebreak inside `REID_TIE_BAND=0.05`.
- Team color: `_calibrate_team_colors()` (`:675`, KMeans k=2 over first ~30 non-ref
  detections, re-cal every 150 frames); `TeamColorTracker.batch_update` (`color_reid.py:230`).
- Homography (orchestrator): `_get_homography()` (`unified_pipeline.py:1231`) does
  SIFT every ~15 frames at 0.5x with three-tier accept (reject <8 inliers / EMA-blend
  alpha=0.25 on 8-39 / hard-reset >=40); `_kornia_homography` (`:1184`) is the GPU LoFTR
  path; drift check (`:1358`) reprojects court boundary lines and forces reset under 0.35
  alignment; `_recover_homography` (`:1120`) re-detects after cuts; replay/cut detector
  suspends SIFT for `_REPLAY_SUSPEND_FRAMES=20`.
- Events: `EventDetector.update(...)` (`event_detector.py:191`) -> `_classify` (`:408`)
  -> `_evaluate_shot` (`:514`). Shot gates: ball vel between `_SHOT_MIN_VEL` and noise
  cap 120 px/frame, debounce (~5-8 s of frames), handler must be moving toward basket,
  ball in-bounds, backcourt band 0.40-0.60 rejected. Rich events have their own
  detectors (`_detect_screens/cuts/drives/closeout/rebound/steal/block/post_up`).
- Possession: `PossessionClassifier.update(players, ball_pos, frame_num)`
  (`possession_classifier.py:~90`) -> 7 geometry types; resets on possessing-team change;
  tracks shot-clock estimate (ISSUE-023).
- Identity: `PlayerResolver.get_jersey_number()` (`player_resolver.py:169`) keeps a read
  only when the weighted majority >= `_MIN_DOMINANT_FRACTION=0.35`;
  `_assign_team_restricted()` (`:289`) does a team-restricted distinct (Hungarian)
  slot->player assignment requiring `_MIN_ASSIGN_VOTES=2`; unassigned slots stay honest
  `unknown`. `finalize()` (`:393`) re-runs on full-game votes (ISSUE-057 fix at
  `unified_pipeline.py:2977`).
- Features: `tracking_feature_extractor.extract(game_id)` (`:464`) ->
  `{player_id: {avg_defender_distance, contested_shot_rate, avg_contest_arm_angle,
  touches_per_game, ...}}`. `_PIXEL_SCALE_THRESHOLD=100` (`:53`) auto-detects rows still
  in pixel units (homography failure guard).

Graceful degradation is real and deliberate: torchreid/kornia/PaddleOCR/decord/Postgres
all have CPU/lib fallbacks (SIFT for LoFTR, EasyOCR for PaddleOCR, HSV for OSNet, PyAV
for decord, CSV for Postgres). Runs on a laptop or a 3090 with no code change.

---

## 3. HOW IT IS USED

- `scripts/batch_season.py` invokes `unified_pipeline` per clip as a subprocess.
- Output `tracking_data.csv` + shot_log/possession/events feed
  `tracking_feature_extractor.extract()`.
- `cv_feature_registry.register_game()` writes per-player rows to `cv_features`.
- Prop models (`prop_pergame.py`, `player_props.py`, `signal_attribution.py`) call
  `has_cv_features()` / `get_cv_features()` and *optionally* fold the CV group in.
- Throughput (per the architecture doc): ~4 fps CPU, ~20 fps single 3090/1 worker,
  ~80-100 fps with 4 workers + OMP cap. Tracker self-reports ~15 fps on a 4060.
- Cost framing in OUTREACH_KIT: ~$0.10-0.13 per game on a consumer GPU.

---

## 4. STRENGTHS (genuinely solid)

- **A real, end-to-end broadcast MOT stack** that produces court-coordinate tracks from
  ordinary TV footage -- not the overhead angle most research assumes. The full
  YOLO -> homography -> Kalman/Hungarian -> re-ID -> OCR -> events chain exists and runs.
- **Engineering robustness.** Three-tier homography with drift reprojection + velocity
  clamp (250 px/frame), replay/cut suspension, EMA smoothing, optical-flow gap-fill,
  per-team color recalibration, OSNet/HSV dual appearance path, full dependency
  fallbacks. This is mature defensive systems work, not a demo.
- **Honest, instrumented self-knowledge.** Nearly every wall is *measured*, not guessed:
  jersey read rate 2.3% (150/6662 crops), shot recall 14% median, 10-slot ceiling
  confirmed on 20 games, defender-distance contamination 30-50% of rows. The bug
  magnitude table is quantified against 32,761 rows.
- **Contest geometry is the real signal.** The court-coordinate geometry (defender
  distance, paint dwell, contest) is the part that is mechanically trustworthy; BLK
  shows 3 correctly-signed CV features >= +0.15 corr.
- **Scale exists.** 17,254 cv_features rows across 241 games / 252 real player IDs.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS (brutally honest)

The CV layer is impressive plumbing whose **player-level attribution is not yet usable**,
and several feature columns are contaminated. Concretely:

- **Jersey OCR is a proven NOISE WALL (~2.3% true read rate).** 150 reads / 6662 crops.
  Sampling-unstable: same code gave 3 different answers on one game. The 30-frame OCR
  skip-cache re-emits the last read at conf=1.0, inflating an apparent ~35% read rate
  that is really 2.3%. Lowering `_SAMPLE_EVERY` does not help -- it is a resolution wall,
  not a density wall. So "0 Wemby shots" baseline is NOT honestly beaten end-to-end.
- **10-slot ceiling (Bug 39).** The tracker structurally emits exactly 10 position slots;
  all 20 sampled games have max(player_id)=10, distinct=10. Subs collapse: one slot held
  Draymond -> Jaylin Williams -> Curry, resolving to ONE nba_id. Result:
  **~75% of player-game observations missing** (avg 2.6 distinct resolved players/game vs
  18-22 in the boxscore). Per-quarter resolution (`backfill_cv_features.py` Phase B1) is a
  partial fix but over-attributes whole-game features to the quarter-resolved player
  (Phase B2 per-quarter feature partitioning still deferred).
- **Scoreboard period NaN / broken OCR (Bug 41).** 100% of games lack a real per-frame
  quarter; period column reads NULL; clock can stick (e.g. "0:56" for ~1400 frames on
  G5). Atlases fall back to a frame-percentile heuristic, which *defeats* per-quarter
  signals. Bug 41's fix populated `cv_features.period` but did NOT propagate
  `scoreboard_period` into `tracking_data.csv` for Q1-Q3 (only Q4 in one game across
  1.33 M frames), blocking frame-grain per-quarter joins.
- **Shot detection ceiling (Bug 30 / Bug 33).** Tracker emits ~9 shots/game vs ~180 real
  FGA -> median PBP recall 9.6%, 63/402 games at ZERO recall. No YOLO-NAS shot weights on
  the pod, so only the ball-trajectory heuristic runs (~4% recall on one game). The made/
  missed JOIN itself is healthy (74.8% on detected shots) -- recall is a *detection* wall,
  not a join bug; widening match windows does nothing.
- **Defender-distance contamination (Bug 1).** 30-50% of shot rows measured distance to a
  TEAMMATE (the "any non-shooter" fallback). This previously flipped a CV-feature
  coefficient sign. Roster collisions (Bug 6) put a wrong player on 23.5% of rows
  (7,712/32,761).
- **Capped / degenerate features.** preshot_velocity_peak clipped at 40.0 on 93% of
  nonzero rows (manufactured fake bench/starter signals); touches capped at 150;
  shot_clock_est MAE 17.16 s (step-shaped); ~14% all-zero EAV noise rows; pixel-unit
  leakage produced 50-101 ft defender distances before cleanup.
- **Ghost slots / re-ID artifacts.** OSNet creates stationary ghost slots near stars
  that pass frame-count but fail motion gates; mode-jersey voting then mislabels them.
- **No accuracy ground truth.** No Second Spectrum reference; ID-switch ~8-12% and
  position +/-12-18 in are *estimates* (README marks them as unvalidated Phase 2.5).
- **Stranded / partial.** Postgres writes "not yet wired" (ISSUE-010, runs overwrite a
  single CSV); referee-gesture foul detection is "partial"; ~8% of games keep
  `ball_track_suspended` True for the whole video (root cause untriaged).
- **Net downstream value is thin.** Because ~50%+ of CV training rows are noise or
  missing-not-at-random, CV features are an optional, mostly-REJECT prop group. The
  defensible value today is the geometry asset and the engineering, NOT a prediction lift.

---

## 6. PLAN TO GET BETTER (prioritized)

Quick wins (highest leverage first, all measured-cheap):

1. **Fix scoreboard_ocr.py (period + decrementing clock + score), per frame.** This is
   THE keystone. It simultaneously (a) unlocks PBP-anchoring -- map each real PBP shot to
   a frame via clock, then read CV geometry at that frame, which BYPASSES both jersey OCR
   and the shot detector; and (b) enables per-quarter slot resolution that defeats the
   10-slot collapse. Approach: tighter ROI crop per broadcast template, digit-segment
   model rather than generic OCR, temporal consistency (monotone-decrementing clock,
   period only increments), and a learned/templated region per network. Propagate
   `scoreboard_period` into `tracking_data.csv` for Q1-Q3 (close Bug 41 propagation gap).
2. **Land the Bug-1 defender-distance fix end-to-end** (exclude same-team players from the
   nearest-defender search) and re-derive cv_features; removes a 30-50% contamination and
   the inverted-sign risk.
3. **Re-derive after Bug 6 / Bug 31 / Bug 34 caps removed** -- delete the clip caps (40.0,
   150) that manufacture fake t-test signals; emit None not 0.0 for missing columns.
4. **Per-quarter feature partitioning (Bug 39 Phase B2)** so quarter-resolved players get
   only their own quarter's touches (today Phase B1 over-attributes). Est. ~4x row unlock
   (17.5K -> 70-80K) if attribution is honest.

Bigger bets:

5. **PBP-anchored CV recall** (depends on #1): use the PBP shot list to drive shooter +
   frame, so shot-detection recall (the ~9 vs ~180 wall) stops being the bottleneck for
   the made/contest geometry features.
6. **Replace the 10-slot tracker with an identity-persistent tracker** (e.g. ByteTrack/
   BoT-SORT style with a real gallery sized for 20+ identities + per-quarter reset), so
   substitutions don't collapse onto one nba_id.
7. **Load proper shot-detection weights** (YOLO-NAS or a trained ball-arc + pose head) to
   lift native shot recall above the heuristic 4-14%.
8. **Establish ground truth** on a handful of games (manual or a public tracking sample)
   to actually measure ID-switch and position error instead of estimating them.

Honesty rail: only ship a CV feature into a prop model after >= 2 corpora + walk-forward
+ null control; BLK is the single best-evidenced retrain candidate, and even that is
gated on coverage densifying past ~20%.

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

- **As an engineering/cost story: already strong.** A laptop/consumer-GPU broadcast MOT
  pipeline that produces court coordinates at ~$0.10-0.13/game, with graceful fallbacks,
  is a genuine, defensible artifact regardless of the prediction question.
- **As a geometry feature source: medium, capped by attribution.** The contest/spacing
  geometry is mechanically real. If #1 (scoreboard OCR -> PBP anchoring) lands, the
  realistic ceiling is *reliable per-shot contest/defender geometry for the shots PBP
  knows happened* -- i.e. clean defender_distance / contest_pct attributed to the correct
  shooter, across most games. That alone could legitimately move a stat like BLK's xhead.
- **As a player-identity moat: low without a tracker rebuild.** Jersey OCR at 2.3% is a
  resolution wall, not an effort problem; broadcast crops simply do not carry the pixels.
  Identity can only be recovered indirectly (PBP anchor + team color + per-quarter
  resolution), never from jersey OCR alone. The 10-slot ceiling caps native coverage at
  ~25% of player-games until the tracker is replaced.
- **As a prediction edge: none, and none is claimed.** Markets are efficient; the honest
  win for the whole system is calibration. The CV layer's honest contribution is a *data
  asset and a systems-engineering proof*, plus possibly one or two calibrated, leak-free,
  null-controlled feature heads (BLK the best candidate) -- not a dollar edge.

**Single highest-leverage fix: make `scoreboard_ocr.py` read period + a decrementing
clock + score per frame.** It is the one change that unblocks PBP-anchoring (kills the
jersey-OCR and shot-detection walls at once) and per-quarter resolution (kills the
10-slot collapse), so it dominates every item on the jersey-OCR path.
