# Architecture Decisions

This document records key architectural decisions, the alternatives considered, and the reasoning behind each choice. The goal is to make it clear why the system works the way it does — so future contributors (and future me) don't re-debate solved problems.

---

## Tracking Architecture

### DEC-001: YOLOv8n for person detection (not Detectron2)

**Decision:** Use YOLOv8n (ultralytics) for player detection.

**Alternatives considered:**
- Detectron2 (Mask R-CNN) — original implementation
- YOLOv8x — higher accuracy but slower

**Why YOLOv8n:**
- Detectron2 is not installable on Python 3.10 + PyTorch 2.1. No workaround available.
- YOLOv8n runs at 5.7 fps on RTX 4060 — sufficient for real-time processing
- 87% detection accuracy is good enough for tracking; Phase 2.5 upgrades to YOLOv8x (94%)
- `ultralytics` API is clean: `model(frame, classes=[0], conf=0.35)`

**Tradeoffs:**
- YOLOv8x would give 94% accuracy but drops to ~3.5 fps
- YOLOv8n misses ~13% of detections (mostly partial occlusions) — handled by Kalman prediction

---

### DEC-002: Kalman + Hungarian for tracking (not SORT/DeepSORT/ByteTrack)

**Decision:** Custom Kalman filter (6D state) + Hungarian assignment.

**Alternatives considered:**
- SORT — simple but high ID switch rate
- DeepSORT — adds appearance embedding but slow
- ByteTrack — state-of-the-art, ~3% ID switches (Phase 2.5 upgrade path)

**Why custom Kalman+Hungarian:**
- Full control over cost matrix weights — can tune IoU vs appearance contribution
- Basketball-specific tuning: appearance weight increases when team uniforms are similar
- Sufficient accuracy for current data volume (17 short clips)
- ByteTrack upgrade planned for Phase 2.5 — it's a direct drop-in for this phase

**State vector:** `[cx, cy, vx, vy, w, h]` — center position + velocity + bounding box size.

---

### DEC-003: HSV histogram for appearance re-ID (not deep embeddings only)

**Decision:** Primary re-ID uses 96-dim HSV histogram (L1-normalized). Deep CBAM re-ID model exists but is secondary.

**Why HSV first:**
- Fast to compute — no GPU needed for re-ID decision
- 96 bins (32 per channel) captures team color well
- EMA update (α=0.7) smooths appearance over time
- NBA uniforms are highly team-specific (color is the primary distinguisher)

**Problem:** Similar team colors (e.g., both teams wearing light-colored uniforms).

**Solution (DEC-003a):** `TeamColorTracker` in `color_reid.py` — KMeans k=2 per detection, builds per-team EMA color signature. When hue centroids within 20°: appearance weight raised +0.10, jersey OCR tiebreaker widened.

**Deep re-ID (CBAM):** Available in `src/re_id/` but not deployed in main pipeline yet. Will activate in Phase 2.5 when processing full games where appearance matters over longer re-appearances.

---

### DEC-004: SIFT panorama stitching for court homography

**Decision:** Pre-compute a court panorama template with SIFT matching per frame.

**Why SIFT:**
- Robust to lighting changes (scale-invariant)
- Works with partial court views (broadcast crops vary by camera position)
- Well-established — SIFT has been reliable for court mapping since 2012

**3-tier acceptance (DEC-004a):**
- `<8 inliers` → reject, use previous homography (EMA)
- `8-39 inliers` → EMA blend with previous (α=0.3 for new)
- `≥40 inliers` → hard-reset with new homography

**Why 3 tiers:** Hard-resetting on 8 inliers causes jitter. EMA prevents jitter but can drift. Hard-reset only when confident (40+) gives stability + correction.

**Drift check:** Every 30 frames, project court boundary lines and count white pixels aligned. If <35% aligned → force hard-reset. This catches slow drift that EMA accumulates.

---

### DEC-005: EasyOCR dual-pass for jersey numbers (not single-pass)

**Decision:** Run EasyOCR twice per crop: normal image + inverted binary.

**Why dual-pass:**
- Light-on-dark jerseys (e.g., dark home uniform) fail normal-pass OCR
- Dark-on-light jerseys (e.g., white away uniform) fail inverted-pass OCR
- Dual-pass covers both cases; take highest-confidence result

**JerseyVotingBuffer:** `deque(maxlen=3)` — only accept a jersey number when same value appears in 2+ of last 3 frames. Eliminates OCR noise from single-frame misreads.

---

## Data Architecture

### DEC-006: File-based CSV output (not direct PostgreSQL writes) for tracking

**Decision:** CV pipeline writes to CSV files. PostgreSQL ingestion is a separate step.

**Why CSV first:**
- Pipeline can run without database connection (important for development)
- Easy to inspect/debug tracking output directly
- Phase 6 adds PostgreSQL writes once data volume justifies it

**Problem:** Every run overwrites `tracking_data.csv` (ISSUE-010).

**Solution (Phase 6):** Write to `data/games/{game_id}/tracking_data.csv` (per-game isolation) + INSERT into `tracking_frames` table in PostgreSQL.

---

### DEC-007: Smart TTL caching for all external API calls

**Decision:** All NBA API and external source data is cached to disk with TTL.

**TTL strategy:**
- Completed seasons (2022-23, 2023-24): `ttl=None` (infinite) — data never changes
- Active season (2024-25) stats: 24h TTL
- Injury reports: 6h (NBA official) / 30min (Rotowire)
- Prop lines: 15min (DraftKings/FanDuel)
- Historical odds: 7d
- BBRef data: 48h

**Why:** NBA API rate limits (0.8s minimum between calls). Without caching, even checking a model's features would trigger 20+ API calls, taking 16+ seconds. With caching, inference is instant.

---

### DEC-008: XGBoost for all ML models (not deep learning)

**Decision:** Use XGBoost for all 18 currently trained models.

**Why XGBoost:**
- Tabular data with 27-52 features: XGBoost outperforms neural nets at this scale
- Fast training: full model trains in <60 seconds on CPU
- Interpretable: `feature_importances_` + SHAP values available
- Robust to missing values (handles NaN natively)
- Sufficient data (3,685 games, 622 players, 221K shots)

**Why not neural networks yet:**
- Not enough CV game data (17 short clips) to justify deep learning on spatial features
- Phase 7+ (20+ full games): gradient boosting still likely wins on tabular features
- Phase 16 (200+ games): LSTM for possession sequence modeling — that's where deep learning earns its place

---

### DEC-009: Walk-forward validation for prop models (not random split)

**Decision:** Use walk-forward cross-validation for all prop models.

**Why walk-forward:**
- NBA stats have temporal structure — using future data to predict past inflates accuracy
- Walk-forward: train on games 1-200, predict game 201; train 1-201, predict 202; etc.
- This is the validation method that matches actual deployment (predict today's game, trained on yesterday's history)

**Why not k-fold:**
- k-fold allows training on future games to predict past games — leakage
- Reported MAE with k-fold would be ~15-20% optimistic

---

## Model Design

### DEC-010: 7-layer feature hierarchy for prediction

**Decision:** Structure the master prediction formula as 7 layers, stacked from most-stable to most-volatile.

```
Layer 1: Season context (win%, home/away, rest)          — stable
Layer 2: Player history (gamelogs, rolling form)          — stable
Layer 3: Behavioral profile (CV: drives, spacing)         — medium
Layer 4: Matchup context (defender zone, synergy)         — medium
Layer 5: Game environment (refs, injuries, travel)        — volatile
Layer 6: Market signals (line movement, CLV)              — very volatile
Layer 7: Live state (current score, fatigue, momentum)    — real-time
```

**Why this matters:** When layers are added incrementally (Phase 4.6 → 6 → 7), each layer's contribution is measurable. You can attribute accuracy gains to specific data sources.

---

### DEC-011: 10K Monte Carlo simulations per game

**Decision:** Run 10,000 simulations of each game to produce stat distributions.

**Why 10K:**
- 1,000 sims: too much variance in distribution tails (P90/P10 unreliable)
- 10,000 sims: P10/P25/P75/P90 stable within ~0.5% run-to-run
- 100,000 sims: diminishing returns, takes ~20s (vs ~2s for 10K)

**Why Monte Carlo (not closed-form):**
- Possession dependencies (fatigue builds across possessions, foul trouble changes lineup)
- These dependencies are not analytically tractable
- Monte Carlo naturally handles them — each sim is a full possession-by-possession game

---

## Product Decisions

### DEC-012: Claude API for AI chat (not GPT-4 or custom LLM)

**Decision:** Use Claude API (claude-opus-4-6) for the AI chat interface.

**Why Claude:**
- Best-in-class tool use API — clean JSON tool calls without prompt engineering
- `render_chart` tool: Claude is reliable about calling it when data is available
- Long context window: can hold entire game analysis in context
- Anthropic's safety properties: won't hallucinate specific prop lines when uncertain

**Why not GPT-4:**
- Tool calling is reliable on both, but Claude's reasoning on multi-step sports analysis queries is stronger in testing

---

### DEC-013: Role player props as primary betting edge (not star props)

**Decision:** Focus edge detection on role player props (6-15 pts, 2-5 reb/ast range).

**Why role players:**
- Sportsbooks price star props with heavy sharp money action — lines move to true probability quickly
- Role player props have wider bid/ask spread and slower line movement
- Injury-to-star scenarios create massive role player props mispricing (blowout risk, usage shifts)
- Our spatial CV data (off-ball movement, spacing contribution) is most differentiated for role players — public has no edge here

---

## Rejected Approaches

| Approach | Why Rejected |
|----------|-------------|
| Detectron2 for detection | Not installable on Python 3.9 + PyTorch 2.0 |
| REST API polling during live games | WebSocket is more efficient for real-time win prob |
| SQLite instead of PostgreSQL | SQLite has no concurrent write support; multi-process pipeline needs PostgreSQL |
| Storing video frames in DB | 30fps × 48min = 86,400 frames per game — disk prohibitive, CVs read from file |
| Neural net for props at current data scale | XGBoost consistently wins on tabular data at <100K rows |
| Using only box-score features | No edge vs. public tools; spatial CV data is the entire moat |
