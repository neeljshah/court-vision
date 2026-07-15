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

**Decision:** Use XGBoost as the primary framework across the trained model set (now grown well beyond the original 18 -- 31 prop model files plus 21+ LightGBM quantile models and hundreds of total artifacts in `data/models/`; `prop_model_stack.py` supports XGBoost, LightGBM, and CatBoost).

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

**Decision:** Use Claude API (currently `claude-sonnet-4-6`, see `src/analytics/chat.py`) for the AI chat interface.

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

## Execution Decision Logic

### DEC-014: Bet on divergence, not on the prediction

**Decision:** A bet candidate is a *divergence* between the calibrated model
probability and the Shin-devigged market probability -- never the raw prediction.

**Why:** A confident model number that agrees with the market is not bettable;
there is no edge to harvest. The unit of decision is therefore
`edge = model_prob - market_prob`, and the thing that gets sized is the
divergence, not the projection. This is enforced structurally in
`frontend/exec_decision.py::decide_row` and `src/prediction/bet_selector.py`.

**Reference math (`exec_decision.py`):**

```
market_prob = shin_devig(best two-way price)      # odds_shop.devig_twoway
edge        = model_prob - market_prob
EV          = model_prob * decimal_odds - 1        # odds_shop.ev_vs_price
```

EV is recomputed against the **best bettable price across books**, not a flat
fiction. (Reading the market's own devigged lean instead of the model, and
pricing at a flat -110, is precisely the artifact behind the retracted pregame
figure -- see `docs/JOB_EVIDENCE_PACKET.md`.)

---

### DEC-015: Tier floors on EV, with a no-bet default

**Decision:** EV is bucketed into tiers by hard floors; anything below the lowest
floor is **not a bet**.

| Tier | EV floor (true close) | EV floor (proxy close) |
|---|---|---|
| A | >= 0.08 | >= 0.09 |
| B | >= 0.04 | >= 0.05 |
| C | >= 0.02 | >= 0.03 |
| (none) | < 0.02 -> `decision="no_bet"`, `stake_units=0` | < 0.03 -> no bet |

`assign_tier()` returns the **strongest** tier whose floor the EV clears, or
`None`. When the settle line is only a proxy (not a true settled close) every
floor is raised by `PROXY_FLOOR_BUMP = 0.01`, so a proxy line must clear a
stricter bar and its CLV is flagged `clv_is_proxy`.

**Why a no-bet default:** the market is efficient; most candidates do not clear a
floor, and the correct action is to pass. Emitting a "best available" bet every
slate is how a system manufactures a fake edge. No-bet is the modal, intended
outcome.

**Layered policy floors.** On top of the EV tier, `bet_selector.py` applies
per-policy guards (`src/prediction/bet_policy.py`): a per-stat raw-unit edge
floor, a closing-line cap, a stat-direction filter (e.g. BLK OVER is dropped as
zero-edge), and a **playoff-AST regime guard** (AST bets on playoff game ids are
skipped unless explicitly allowed, because gated playoff AST does not hold up).
These only ever *remove* bets or shrink stakes -- they never invent one.

---

### DEC-016: Dual edge + CLV gate before sizing

**Decision:** A candidate must clear **both** an edge bar and a predicted-CLV bar
before it is sized.

```
keep iff  |edge| > edge_min (~0.04)   AND   predicted_CLV > clv_min (~1.5%)
```

**Why:** edge alone is the in-sample optimist's filter; predicted CLV is the
out-of-sample reality check. Requiring both drops bets the model expects to lose
closing-line value even when the nominal edge looks fine. The CLV predictor
**degrades gracefully** -- if `clv_predictor.pkl` has not been trained yet (no
settled history), the gate is skipped and the pipeline falls back to edge-only
filtering rather than crashing the slate.

---

### DEC-017: Units-only sizing, paper-only, human-gated live

**Decision:** Stakes are emitted as **unit counts**, never dollars; live capital
is off by default and human-gated.

- Two units per accepted bet: a flat `1.0u` (for unbiased CLV tracking) plus a
  capped quarter-Kelly `kelly_units = min(0.25 * f*, 4.0)`.
- `exec_decision.py` has **no `$` field by construction**; the in-game
  `decision_engine.py` Kelly is a bankroll *fraction* (capped at 0.25), again not
  a dollar amount.
- `LIVE_BETTING=0` is enforced in `bet_selector.py` (non-zero exit otherwise);
  real money is unlocked only by a human after the recorded-CLV evidence gate in
  [risk-framework](risk-framework.md) passes in full.

**Why:** units make CLV the scoreboard and keep the public artifact free of any
dollar edge/ROI claim. CLV (holding a better number than the close) is the only
money-adjacent yardstick the system reports.

---

## Rejected Approaches

| Approach | Why Rejected |
|----------|-------------|
| Detectron2 for detection | Not installable on Python 3.9 + PyTorch 2.0 |
| REST API polling during live games | WebSocket is more efficient for real-time win prob |
| SQLite instead of PostgreSQL | SQLite has no concurrent write support; multi-process pipeline needs PostgreSQL |
| Storing video frames in DB | 30fps x 48min = 86,400 frames per game -- disk prohibitive, CVs read from file |
| Neural net for props at current data scale | XGBoost consistently wins on tabular data at <100K rows |
| Using only box-score features | No edge vs. public tools; spatial CV data is the entire moat |

---

See also: [BETTING](BETTING.md) (edge/EV/CLV math, line-shopping, paper loop)  - 
[EXECUTION_GUIDE](EXECUTION_GUIDE.md) (sized-bet pipeline)  - 
[risk-framework](risk-framework.md) (sizing caps, circuit breakers, live gate)  - 
[architecture/execution-engine](architecture/execution-engine.md) (venue routing)  - 
[label_strategy](label_strategy.md) (prop tiering).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
