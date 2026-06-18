# Sports CV from Broadcast Video: Detection, Tracking, Re-ID, Pose, Homography, OCR, Foundation Models
_Researched 2026-06-16. Scope: open models + accuracy ceilings + cost for extracting spatial features from broadcast sports video that feed calibrated prediction._

---

## TL;DR (7 bullets -- highest-leverage takeaways)

- **Detection ceiling is NOT the bottleneck.** YOLOv8/YOLOv11/RF-DETR fine-tuned on sports data achieves >90% mAP for player bounding boxes on broadcast video; the hard problems are re-ID across occlusions and correct jersey-number assignment.
- **ByteTrack + BoT-SORT are the practical pair.** ByteTrack wins on speed (real-time on consumer GPU); BoT-SORT (default in Ultralytics) adds camera-motion compensation critical for broadcast panning -- use BoT-SORT for broadcast, ByteTrack for fixed cameras.
- **OSNet / ResNet50 re-ID is solved for team ID, NOT player ID.** Team-color embedding (OSNet trained on ~111 uniform classes) is robust. Individual player re-ID from broadcast crops is fragile due to jersey similarity and occlusion; jersey-number OCR (ResNet) tops out at ~86-93% per crop but degrades badly at low resolution / motion blur.
- **Homography (court/pitch mapping) is the highest-value spatial extraction.** SegFormer + keypoint refinement on 74 pitch landmarks achieves state-of-the-art SoccerNet Game State HOTA of 63.81 (vs 23.36 baseline); this converts pixel positions to real-world court coordinates, enabling distance, speed, spacing, and zone features.
- **SAM2 as tracker is powerful but slow (1-2 FPS on T4).** Viable for offline enrichment; not for real-time. Use YOLO+ByteTrack for real-time, SAM2 for high-quality offline post-processing or when segmentation masks (not just boxes) are needed.
- **Pose estimation (ViTPose / RTMPose) adds body-joint keypoints on top of tracking.** Enables fatigue signals, contested-shot posture, defensive stance -- none of these are in box-level tracking. Pose adds ~10-30ms/frame on GPU.
- **The spatial features MOST useful for prediction are:** spacing (convex hull, lane density), court zone occupancy, transition speed, defensive close-out distance, paint touches, and possession-chain length -- all derivable from homography + tracking WITHOUT jersey-level ID.

---

## Key Capabilities / Techniques

### 1. Detection: YOLO family and RT-DETR / RF-DETR

| Model | Type | Notes |
|---|---|---|
| YOLOv8 / YOLOv11 | One-stage anchor-free | Ultralytics ecosystem; fine-tune on sports in <2h on a single GPU; ~80-150 FPS on RTX 4060 |
| RF-DETR-S | Transformer-based one-stage | Better small-object detection (jersey numbers, ball); slower than YOLOv8 but higher precision |
| RT-DETR | Real-Time DETR | Comparable speed to YOLO, better on crowded scenes; native Ultralytics support |
| YOLOv5m | Lightweight baseline | Used by SoccerNet winning pipeline (2025); acceptable quality/speed trade-off |

Fine-tuning requirement: a labeled sports dataset of 500-2000 frames is sufficient for good player detection. Roboflow Universe hosts multiple pre-labeled basketball/soccer datasets.

### 2. Tracking: ByteTrack and BoT-SORT

**ByteTrack** (Zhang et al., 2022):
- Two-stage association: high-confidence detections first, then low-confidence (recovers occluded players)
- Pure IoU + Kalman filter, no appearance model -> very fast
- Weakness: cluster confusion (players running together), identity switches at crowd junctions
- Best for: fixed cameras, indoor basketball where players spread out

**BoT-SORT** (Aharon et al., 2022):
- Adds global motion compensation (GMC) via sparse optical flow to handle camera pan/zoom
- Optional ReID module (appearance embeddings)
- Default tracker in Ultralytics YOLO as of 2024
- Best for: broadcast video with dynamic camera

**Ultralytics tracker zoo (2025):** BoT-SORT, ByteTrack, OC-SORT, Deep OC-SORT, FastTracker (occlusion-aware), TrackTrack (multi-cue). All configurable via YAML; ReID models available as ONNX (yolov8n/s/m/l/x-reid.onnx).

**SRITrack (2025, ScienceDirect):** addresses re-entry identity instability specific to broadcast sports -- players leave frame and return; adds re-entry identity enhancement module.

Practical accuracy: HOTA ~50-65 on sports tracking benchmarks with fine-tuned detection + BoT-SORT; identity switches remain the dominant error.

### 3. Re-identification: OSNet and appearance embeddings

**OSNet** (Zhou et al., 2019) -- Omni-Scale Network for person re-ID:
- Lightweight multi-scale aggregation network; trained on large ReID datasets (Market-1501, DukeMTMC)
- For sports: fine-tune on team-labeled crops -> robust team assignment (used in SoccerNet 2025 winner)
- For PLAYER-level ID: degrades quickly; jersey colors too similar within a team; broadcast crops at 20-50px height lose discriminating features
- The SoccerNet 2025 winner used OSNet for TeamID (111 uniform classes) + separate ResNet50 for player ReID

**Practical ceiling for player re-ID from broadcast:** ~70-80% correct player-ID assignment over a full game without jersey-number confirmation. With jersey-number OCR as a secondary signal, identity accuracy improves but depends on OCR quality.

### 4. Jersey Number OCR

**State of practice (Roboflow pipeline, 2025):**
- Detect jersey-number region with RF-DETR (separate head or class)
- ResNet-32 classifier: 93% accuracy per crop on test set
- SmolVLM2 (vision-language): 86% accuracy per crop
- Temporal voting (3 consecutive consistent predictions): stabilizes noisy per-frame results

**Hard limits:**
- Resolution: jersey numbers < ~15px height fail all methods
- Motion blur: common in fast cuts; OCR degrades to <50%
- Deformed jerseys / arms raised: standard OCR fails
- Older approaches (image thresholding + off-the-shelf OCR): "very poor results" per Stanford study (2012), still not much improved without DL

OSNet used separately for TeamID (which team) vs jersey OCR for PlayerID -- these are two distinct pipelines.

### 5. Homography and Court / Pitch Mapping

**Why it matters:** converts pixel (u, v) -> real-world (x, y) court coordinates. Enables:
- Player speed (m/s), distance covered
- Spacing metrics (convex hull area, lane density, paint zone occupancy)
- Defensive close-out distance, corner 3 coverage
- Heat maps per game state

**State-of-the-art pipeline (SoccerNet 2025 winner, 63.81 GS-HOTA):**
1. SegFormer CNN-Transformer encoder-decoder predicts 7 camera parameters (position, orientation, FoV)
2. ResNet18 detects 74 pitch line intersection keypoints
3. Brute-force optimization aligns prediction to keypoints
4. Camera-motion compensation (BoT-SORT GMC) maintains alignment across frames

**Jump-aware correction (CVPR Workshop 2025):** standard homography breaks when players jump -- their feet leave the ground plane. Jump-aware systems add vertical displacement estimation to correct projected court position during jump events (important for tracking shot release, contested jump balls).

**Basketball-specific:** 74+ court landmarks (3-point arc, lane lines, center circle, backboard) vs soccer's 74 pitch intersections. NBA court has more curves (arcs) -- requires curve-fitting not just linear homography.

**Cost:** homography estimation adds ~10-20ms/frame; keypoint refinement adds ~5-10ms. Total: ~15-30ms/frame overhead on top of detection.

### 6. Foundation Models: SAM2 and DETR variants

**SAM2 (Meta, 2024):**
- Segment Anything Model 2: video-native with temporal memory bank
- Zero-shot tracking by propagating masks across frames without re-detection
- Achieves state-of-the-art on LaSOT, GOT-10k, VOT2024
- Sports use: frame-to-frame player mask propagation (handles occlusion via memory); team clustering via mask appearance
- Speed: 1-2 FPS on T4 GPU -> NOT real-time. Bottleneck in the Roboflow basketball pipeline. Viable for offline enrichment only.
- SAM2.1 (2025): adds distractor-aware memory management to avoid ID confusion in crowded scenes

**Kalman+SAM2 hybrid (Sensors 2025):** Kalman filtering guides SAM2 memory selection for long-term video segments; reduces drift on clips >30s. Shows improvement on LaSOT.

**DETR / RF-DETR:**
- Detection Transformer: global attention across image, no anchor boxes; better than YOLO on small/occluded players
- RF-DETR: recent variant optimized for real-time; used in 2025 basketball pipelines
- Integrations: DETR + Graph Convolutional Transformer (GCT) for pose-coupled detection (captures spatial+temporal dependencies)

**Vision-Language Models (SigLIP, SmolVLM2):**
- SigLIP: generates visual embeddings for unsupervised team clustering (UMAP -> K-means)
- SmolVLM2: fine-tuned for jersey-number reading (86% crop accuracy)
- GLIP: semantic reasoning about events from video frames

### 7. Pose Estimation

**Models:** ViTPose (transformer), RTMPose (real-time, MMLab), Swin-Transformer-based pose, HRNet
**Integration:** YOLOX + ByteTrack + RTMPose is a common production stack (TrackID3x3 dataset, 2025)
**What you get:** 17-133 body keypoints per player per frame -> elbow angle, lean angle, jump height, hand position
**Sports-specific value:** contested shot posture, defensive stance, fatigue (drooping shoulders, slower recovery), foul probability (arm extension on defender)
**Speed:** RTMPose adds ~10-30ms/frame on RTX-class GPU; ViTPose ~50-100ms
**Dataset:** TrackID3x3 (arXiv 2503.18282) is first joint tracking+pose dataset for basketball (3x3 full court)

### 8. Event Detection (Action Spotting)

**SoccerNet benchmark (500 videos, 764 hours, 17 event classes):**
- Best tight mAP: 73.98 (Tran et al., 2024); best loose mAP: 79.11 (Santra et al., 2025)
- Architectures: T-DEED (Transformer), VideoMAE, SpotFormer, COMEDIAN (self-supervised)
- Frame discriminability is the key bottleneck: adjacent frames look visually identical; events are instantaneous
- Model sizes: 2.3M params (STE, CPU-trainable) to 29.1M params (COMEDIAN)

**Open datasets for basketball event detection:**
- NCAA Basketball: 257 videos, 14 action categories
- TrackID3x3: 3x3 basketball, joint tracking+pose+ID
- No large-scale NBA broadcast dataset is publicly available; all NBA production systems (Second Spectrum, AutoStats) are proprietary

---

## How THIS Project Should Use It

### Priority 1: Homography -> Spatial Features for In-Game Conditioning (HIGH VALUE)
The project already has the PBP-anchored CV recall pipeline and scoreboard OCR as the keystone. The next highest-value addition is **homography to extract spacing and zone features IN REAL TIME during a game:**
- Fit a SegFormer or lightweight ResNet18 keypoint detector to NBA court landmarks (publicly available court diagrams as templates)
- At each possession boundary (detected via PBP event), compute: paint density, 3-point spacing (convex hull of non-ball-handler offensive players), corner occupation, transition speed
- Feed these as in-game conditioning signals into the existing possession-level Monte Carlo engine (already has in-game heads)
- This is extractable WITHOUT reliable player re-ID -- you only need court positions, not identities

### Priority 2: Team-Level Detection + Tracking (MEDIUM VALUE, LOW COMPLEXITY)
- YOLOv8 fine-tuned on NBA broadcast crops (Roboflow has pre-labeled datasets) + BoT-SORT with GMC handles camera pan
- Color-based TeamID via SigLIP/K-means or OSNet fine-tuned on ~2 teams/game (only 2 teams per game, trivially clustered)
- Enables paint touch counting, transition counts per possession -- both correlate with pace and shot quality
- Estimated inference cost: ~$0.10-0.30/game-hour on an RTX 4060 (real-time capable at 30 FPS)

### Priority 3: Scoreboard/Clock OCR Pipeline (ALREADY STARTED -- EXTEND)
The existing scoreboard_ocr.py is already the keystone. Extend with:
- Shot clock OCR (separate text region)
- Period and possession-arrow detection
- These anchor every spatial feature to game time and possession state

### Priority 4: Offline Enrichment with SAM2 + Pose (LOW URGENCY)
- NOT real-time: run overnight on stored clips (1-2 FPS on T4 is fine offline)
- Extract: jump events (jump-aware homography), contested shot posture (ViTPose), defensive recovery speed
- Store extracted features as parquet keyed by (game_id, clock_time) -> join to PBP for model training
- Builds the own-data moat the north star requires: CV-derived features are NOT in any market signal

### Priority 5: Jersey OCR -> Player ID (LOW PRIORITY, HIGH COMPLEXITY)
- ResNet-32 jersey OCR at 93% per-crop, temporal voting: viable for player-level labeling
- But: high engineering cost, fails on fast-break / small crops. Use PBP anchor pattern instead (match CV events to PBP events by time/type) -- this is already the design in pbp_anchored_cv_recall
- Do NOT spend cycles on OSNet player-level re-ID without jersey OCR confirmed working first

### Specific Actionable Recommendations
1. Use **Ultralytics YOLOv8 + BoT-SORT** as the detection+tracking backbone (already in Python ecosystem, RTX 4060 native)
2. Use **SigLIP embeddings -> K-means** for team assignment (2 clusters per game; no fine-tuning needed)
3. Implement **ResNet18 keypoint detector for NBA court landmarks** (74 points analogous to SoccerNet's soccer pitch); open-source SoccerNet homography code is available at github.com/SoccerNet/sn-tracking
4. Store all extracted features as **(game_id, frame_idx, clock_str)** keyed parquet; clock_str joins to PBP
5. **OOS validation**: train spatial-feature models on 2023-24 season, test on 2024-25 (minimum 2 corpora); measure Brier improvement of in-game model with vs without spatial features; honest reject if no improvement

### Expected Prediction Value of Spatial Features (Calibrated Expectation)
- Spacing (convex hull) correlates ~0.15-0.25 with 3P attempt rate (literature); adding it to in-game conditioning likely shifts in-game Brier by 0.005-0.020 -- small but real and leak-free
- Transition speed correlates with pace; pace is already partially captured by PBP stats
- Net: spatial features are a CALIBRATION improvement for in-game heads, not a pregame edge; consistent with the project north star

---

## Gotchas / Limits

- **No public NBA broadcast dataset.** SoccerNet is soccer-only. All NBA-specific ground truth (player positions on court) is proprietary (Second Spectrum, Sportradar). You must self-annotate or use PBP-anchored weak supervision.
- **14% detection ceiling already observed in this project** (see cv_bug_magnitudes, bug39 10-slot ceiling). Detection is not the bottleneck -- ASSOCIATION and OCR are.
- **SAM2 is NOT real-time** (1-2 FPS on T4). Do not use it for live in-game conditioning; it is offline-only.
- **Jersey OCR degrades badly at scale.** 93% per crop sounds high but over a 48-minute game with ~2000 player-crops, that is ~140 errors -- player IDs will be noisy without temporal voting and PBP anchoring.
- **Homography breaks for jumping players.** Use jump-aware correction (CVPR 2025) or simply exclude frames where any tracked player's bounding box center is >N pixels above their Kalman-predicted floor position.
- **Camera panning breaks naive IoU tracking.** BoT-SORT with GMC (sparse optical flow) is required for broadcast; ByteTrack alone will generate many ID switches on fast pans.
- **Class imbalance in event detection.** Background frames dominate (~95%); standard cross-entropy loss degrades; use focal loss or context-aware weighting.
- **Broadcast-only moat is fragile** once SportVU/Hawk-Eye data becomes more available. The moat is the integration of CV-derived features + PBP + intelligence for IN-GAME conditioning; that integration is the actual differentiator.
- **Cost per game (estimated):** detection+tracking at 30 FPS, 2.5 hours -> ~270,000 frames. On RTX 4060 at ~100ms/frame (detection+track+homography): ~7.5 hours wall-clock per game if sequential. Parallelize to ~1 hour using frame subsampling (every 3rd frame sufficient for 10 FPS tracking). Cloud: ~$0.50-2.00/game on A10G instance.

---

## Sources

- [SoccerNet Game State Reconstruction (arXiv 2504.06357, 2025)](https://arxiv.org/html/2504.06357v1) -- SoccerNet 2025 HOTA results, SegFormer homography, OSNet TeamID, YOLOv5m detection pipeline
- [How to Detect, Track, and Identify Basketball Players -- Roboflow Blog (2025)](https://blog.roboflow.com/identify-basketball-players/) -- RF-DETR + SAM2 + SigLIP + ResNet-32 OCR pipeline, 1-2 FPS SAM2 bottleneck
- [TrackID3x3: Multi-Player Tracking + Pose for Basketball (arXiv 2503.18282, 2025)](https://arxiv.org/pdf/2503.18282) -- YOLOX + ByteTrack + ViTPose, first joint basketball tracking+pose dataset
- [Deep Learning for Sports Video Event Detection Survey (arXiv 2505.03991v3, 2025)](https://arxiv.org/html/2505.03991v3) -- SoccerNet mAP benchmarks, T-DEED, COMEDIAN, frame-discriminability bottleneck, dataset catalog
- [Multi-Object Tracking with Ultralytics YOLO -- Official Docs](https://docs.ultralytics.com/modes/track) -- BoT-SORT/ByteTrack/OC-SORT/FastTracker/TrackTrack configs, ReID ONNX models, camera-motion compensation
- [SoccerNet Tracking GitHub -- sn-tracking](https://github.com/SoccerNet/sn-tracking) -- open benchmark, dataset access, baseline code
- [Homography-based Player Identification in Live Sports (ResearchGate, 2023)](https://www.researchgate.net/publication/373127328_Homography_based_Player_Identification_in_Live_Sports) -- court mapping methodology
- [SRITrack: Online MOT for Sports Broadcasting with Re-entry ID Enhancement (ScienceDirect, 2025)](https://www.sciencedirect.com/science/article/abs/pii/S0957417426014120) -- re-entry identity stability problem and solution
