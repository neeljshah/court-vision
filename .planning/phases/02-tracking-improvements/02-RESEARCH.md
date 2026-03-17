# Phase 2: Tracking Improvements - Research

**Researched:** 2026-03-15
**Domain:** Computer vision OCR, player re-identification, analytics filtering, footage acquisition
**Confidence:** MEDIUM-HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REQ-04 | Jersey number OCR reads number from player crop each frame (PaddleOCR or CRNN) | EasyOCR recommended over PaddleOCR for this env; allowlist + preprocessing pattern documented |
| REQ-05 | Jersey number → player name lookup using NBA API roster for the game | `CommonTeamRoster` endpoint returns `NUM` field; roster fetch + dict pattern documented |
| REQ-06 | Named player ID mapping persisted in PostgreSQL across clips | `tracking_frames` table already has `player_id` and `tracker_player_id` columns; mapping table design documented |
| REQ-07 | HSV re-ID uses k-means k=3 color clustering + jersey number tiebreaker on ambiguous cases | k-means on HSV jersey crop pattern documented; integrate into `_compute_appearance` / `_reid` |
| REQ-08 | Referees (team_id=2) excluded from all spacing, pressure, and analytics calculations | `defense_pressure.py`, `momentum.py`, `shot_quality.py` already skip `referee` at aggregation; gaps identified in feature_engineering spatial metrics |
| REQ-08b | At least 5 real NBA broadcast game clips acquired and enriched with --game-id | `video_fetcher.py` + `CURATED_CLIPS` exists; `fetch_game_ids` pattern documented; cookie auth required |
</phase_requirements>

---

## Summary

Phase 2 adds named player identity to the tracking pipeline. Right now every player is an anonymous slot (0–9). The core work is: (1) read jersey numbers from bounding-box crops using OCR, (2) match those numbers to an NBA API roster to get real player names, (3) persist the mapping in PostgreSQL, (4) harden re-ID for similar-colored uniforms with k-means clustering, (5) filter referees from all analytics, and (6) acquire real broadcast clips so the shot enrichment pipeline has real game IDs to work with.

The biggest technical risk is OCR quality. Jersey number crops from broadcast video are typically 30–80 px tall, often motion-blurred, sometimes partially occluded. No off-the-shelf OCR library solves this reliably without preprocessing. The recommended strategy is EasyOCR with a digit-only allowlist and a multi-frame voting buffer (confirm same number 3 times before committing), falling back to unknown when confidence is low. PaddleOCR is heavier to install on this Windows/conda stack and has no meaningful accuracy advantage for single-digit recognition in this domain.

The referee filtering work is mostly already done at the analytics layer — `defense_pressure.py` and `momentum.py` both already skip `team == "referee"`. The gap is in `feature_engineering.py` spatial metric calculations and the shot quality heatmap grouping, which need an explicit `team_id != 2` guard before computing convex hull areas and coverage statistics.

**Primary recommendation:** Implement OCR as a parallel annotation pass (not inside the real-time tracking loop). Read crops every N frames, accumulate votes, flush confirmed jersey→slot mappings to a per-clip dict, write to PostgreSQL at end of clip.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| easyocr | 1.7.x (latest) | Jersey number OCR from player crops | Installable via pip in existing env; GPU-accelerated via existing PyTorch 2.0.1; `allowlist` parameter restricts output to digits; well-documented preprocessing hooks |
| nba_api | existing | `CommonTeamRoster` endpoint → jersey NUM → player name dict | Already installed; `NUM` field documented in endpoint |
| scikit-learn | existing (in basketball_ai env) | `KMeans(n_clusters=3)` on HSV crop for color-based re-ID | Clean API; already a dependency of other modules; no new install |
| opencv-python | existing | Crop preprocessing: resize, CLAHE, threshold before OCR | Already used throughout the codebase |
| psycopg2 | existing (Phase 1 dependency) | Persist player_id mapping to PostgreSQL | Already in stack from Phase 1 schema work |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| yt-dlp | existing | Broadcast clip download | REQ-08b footage acquisition; `video_fetcher.py` already wraps it |
| numpy | existing | Array ops for HSV histogram + k-means input | Already used in tracker |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| EasyOCR | PaddleOCR | PaddleOCR requires installing PaddlePaddle (separate framework from PyTorch); heavier dependency; no accuracy advantage for single digits; EasyOCR reuses existing PyTorch install |
| EasyOCR | SmolVLM2 fine-tuned | 93% accuracy for jersey numbers after fine-tuning, but requires ~3,600 labeled crops and custom training; overkill for Phase 2 |
| EasyOCR | Tesseract | Tesseract performs poorly on sub-100px crops; no GPU; generally outperformed by EasyOCR on degraded sports images |
| scikit-learn KMeans | OpenCV k-means | Both work; scikit-learn is already used for ML features and has cleaner API for n_clusters=3 |

**Installation (new dependencies only):**
```bash
conda activate basketball_ai
pip install easyocr
```
EasyOCR auto-detects the existing PyTorch + CUDA install. No additional packages needed.

---

## Architecture Patterns

### Recommended Project Structure additions
```
src/
├── re_id/                    # existing — deep re-ID model (not used in Phase 2)
├── tracking/
│   ├── advanced_tracker.py   # existing — add k-means to _compute_appearance / _reid
│   ├── jersey_ocr.py         # NEW — OCR reader, preprocessing, voting buffer
│   └── player_identity.py    # NEW — jersey→name mapping, PostgreSQL persistence
└── data/
    └── nba_stats.py          # existing — add fetch_roster() wrapping CommonTeamRoster
```

### Pattern 1: OCR as a Parallel Annotation Pass (not in tracking loop)

**What:** Run OCR separately from the main tracking loop. The tracker runs at frame rate; OCR runs every N=5 frames on each player crop. A voting buffer accumulates jersey number predictions per tracker slot. When the same number appears 3 times consecutively, the slot is confirmed.

**When to use:** Always. Running OCR inside `get_players_pos` on every frame at 30 fps will stall the loop — EasyOCR Reader initialization is ~2s and inference per crop is ~40ms even with GPU.

**Implementation sketch:**
```python
# src/tracking/jersey_ocr.py
# Source: EasyOCR docs (https://www.jaided.ai/easyocr/documentation/) + research findings

import easyocr
import cv2
import numpy as np
from typing import Optional

_reader: Optional[easyocr.Reader] = None

def get_reader() -> easyocr.Reader:
    """Lazy-initialize EasyOCR reader (GPU if available)."""
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(['en'], gpu=True, verbose=False)
    return _reader

def preprocess_crop(crop_bgr: np.ndarray) -> np.ndarray:
    """
    Prepare a player bounding-box crop for digit OCR.

    Steps: upscale to at least 64px tall, CLAHE contrast enhancement,
    convert to grayscale, binary threshold to isolate jersey digits.

    Args:
        crop_bgr: Raw BGR crop from frame (any size).

    Returns:
        Preprocessed grayscale image suitable for EasyOCR.
    """
    h, w = crop_bgr.shape[:2]
    # Focus on jersey area: rows 20%-70% of crop height
    y1 = int(h * 0.20)
    y2 = int(h * 0.70)
    roi = crop_bgr[y1:y2]
    if roi.size == 0:
        return np.zeros((64, 32), dtype=np.uint8)
    # Upscale if too small
    scale = max(1, 64 // max(roi.shape[0], 1))
    if scale > 1:
        roi = cv2.resize(roi, (roi.shape[1] * scale, roi.shape[0] * scale),
                         interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    return enhanced

def read_jersey_number(crop_bgr: np.ndarray) -> Optional[int]:
    """
    Read jersey number from a player crop. Returns int or None.

    Args:
        crop_bgr: BGR player bounding-box crop.

    Returns:
        Integer jersey number (0-99) or None if no confident read.
    """
    img = preprocess_crop(crop_bgr)
    reader = get_reader()
    results = reader.readtext(
        img,
        allowlist='0123456789',
        detail=1,
        paragraph=False,
    )
    for (_, text, conf) in results:
        text = text.strip()
        if text.isdigit() and conf >= 0.65:
            n = int(text)
            if 0 <= n <= 99:
                return n
    return None
```

### Pattern 2: Multi-Frame Voting Buffer (Confirmation Gate)

**What:** A dict mapping tracker slot → deque of recent OCR reads. A slot is "confirmed" only when the same jersey number appears 3+ consecutive times.

**When to use:** Always. Single-frame OCR is noisy. Three consecutive identical reads eliminates most misreads without needing custom training data.

**Example:**
```python
# In src/tracking/player_identity.py
from collections import defaultdict, deque
from typing import Dict, Optional

CONFIRM_THRESHOLD = 3   # consecutive identical reads to confirm
SAMPLE_EVERY_N = 5      # run OCR every N frames

class JerseyVotingBuffer:
    """
    Accumulates per-slot jersey number OCR votes across frames.

    Usage:
        buf = JerseyVotingBuffer()
        # Each frame where OCR runs:
        buf.record(slot=3, number=23)
        confirmed = buf.get_confirmed(slot=3)  # returns 23 or None
    """
    def __init__(self, confirm_threshold: int = CONFIRM_THRESHOLD):
        self._votes: Dict[int, deque] = defaultdict(lambda: deque(maxlen=confirm_threshold))
        self._confirmed: Dict[int, int] = {}
        self._threshold = confirm_threshold

    def record(self, slot: int, number: Optional[int]) -> None:
        """Record an OCR read for a slot. None reads are included to break streaks."""
        self._votes[slot].append(number)
        buf = self._votes[slot]
        if len(buf) == self._threshold and len(set(buf)) == 1 and buf[0] is not None:
            self._confirmed[slot] = buf[0]

    def get_confirmed(self, slot: int) -> Optional[int]:
        """Return confirmed jersey number for slot, or None."""
        return self._confirmed.get(slot)

    def reset_slot(self, slot: int) -> None:
        """Call when a slot is evicted/re-IDed."""
        self._votes.pop(slot, None)
        self._confirmed.pop(slot, None)
```

### Pattern 3: Roster Lookup (NBA API → jersey number dict)

**What:** Fetch team roster for the game's two teams, build a `{jersey_number: player_name}` dict for each team. Called once per clip before processing starts.

**Example:**
```python
# Add to src/data/nba_stats.py

def fetch_roster(team_id: int, season: str = "2024-25") -> dict:
    """
    Fetch jersey number → player name mapping for a team.

    Returns:
        {jersey_number_int: {"player_id": int, "player_name": str}}
    """
    from nba_api.stats.endpoints import CommonTeamRoster
    import time
    cache_key = f"roster_{team_id}_{season}"
    cache_path = os.path.join(_NBA_CACHE, f"{_safe(cache_key)}.json")
    if os.path.exists(cache_path):
        return _load(cache_path)
    time.sleep(0.6)
    roster = CommonTeamRoster(team_id=str(team_id), season=season)
    df = roster.get_data_frames()[0]
    result = {}
    for _, row in df.iterrows():
        num_str = str(row.get("NUM", "")).strip()
        if num_str.isdigit():
            result[int(num_str)] = {
                "player_id": int(row.get("PLAYER_ID", 0)),
                "player_name": str(row.get("PLAYER", "")),
            }
    _save(cache_path, result)
    return result
```

### Pattern 4: k-means Color Clustering for HSV Re-ID (REQ-07)

**What:** Replace the single dominant-color HSV approach in `_compute_appearance` with k-means k=3 clustering on the jersey ROI pixels. The dominant cluster (largest centroid) becomes the primary color for appearance matching. When two players have ambiguous HSV appearance distance, the confirmed jersey number is used as a tiebreaker in `_reid`.

**Where it goes:** `advanced_tracker.py` — modify `_compute_appearance` to optionally include a dominant-HSV-cluster vector alongside the histogram embedding.

**Example (k-means dominant color extraction):**
```python
# Source: OpenCV k-means docs + scikit-learn KMeans API
import cv2
import numpy as np
from sklearn.cluster import KMeans

def dominant_hsv_cluster(crop_bgr: np.ndarray, k: int = 3) -> np.ndarray:
    """
    Extract dominant jersey color using k-means on HSV pixels.

    Returns the dominant cluster center as a 3-dim HSV vector.
    """
    h, w = crop_bgr.shape[:2]
    roi = crop_bgr[: int(h * 0.70)]      # upper 70% = jersey area
    if roi.size == 0:
        return np.zeros(3, dtype=np.float32)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    if len(hsv) < k:
        return hsv.mean(axis=0)
    km = KMeans(n_clusters=k, n_init=3, max_iter=30, random_state=0)
    labels = km.fit_predict(hsv)
    counts = np.bincount(labels, minlength=k)
    dominant = km.cluster_centers_[counts.argmax()]
    return dominant.astype(np.float32)
```

**Jersey number tiebreaker in `_reid`:** When HSV appearance distance between two gallery candidates is within a `REID_TIE_BAND = 0.05` window, prefer the candidate whose confirmed jersey number matches the OCR read for the new detection.

### Pattern 5: PostgreSQL Named Player Persistence (REQ-06)

**What:** The `tracking_frames` table already has `player_id INTEGER REFERENCES players(player_id)` and `tracker_player_id INTEGER`. The mapping work is: after a clip is processed and jersey numbers are confirmed, UPDATE `tracking_frames` rows to fill `player_id` where `tracker_player_id` matches a confirmed slot.

A new `player_identity_map` table is needed (per-game, per-slot → player_id) so the mapping survives across clips of the same game.

**Schema addition to `database/schema.sql`:**
```sql
-- Per-game tracker slot → named player mapping
CREATE TABLE IF NOT EXISTS player_identity_map (
    id              BIGSERIAL PRIMARY KEY,
    game_id         VARCHAR(20) NOT NULL REFERENCES games(game_id),
    clip_id         UUID NOT NULL,
    tracker_slot    SMALLINT NOT NULL,   -- anonymous slot 0-9 from tracker
    jersey_number   SMALLINT,
    player_id       INTEGER REFERENCES players(player_id),
    confirmed_frame INTEGER,             -- frame at which identity was confirmed
    confidence      REAL,               -- OCR vote fraction (0-1)
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (game_id, clip_id, tracker_slot)
);
CREATE INDEX IF NOT EXISTS idx_identity_game ON player_identity_map(game_id);
```

**UPDATE pattern for `tracking_frames`:**
```sql
UPDATE tracking_frames tf
SET    player_id = pim.player_id
FROM   player_identity_map pim
WHERE  tf.game_id = pim.game_id
  AND  tf.clip_id = pim.clip_id
  AND  tf.tracker_player_id = pim.tracker_slot
  AND  pim.player_id IS NOT NULL;
```

### Pattern 6: Referee Filtering in Analytics (REQ-08)

**What:** Guard all spatial metric calculations against `team_id == 2` / `team == "referee"` rows before computing convex hulls, nearest-opponent distances, and coverage counts.

**Current state:**
- `defense_pressure.py` line 64: `non_ref = fgrp[fgrp["team"] != "referee"]` — DONE
- `momentum.py` line 63: `df[df.get("team", pd.Series()) != "referee"]` — DONE
- `shot_quality.py` `_write_heatmap()` line 152: `if team != "referee"` — DONE for heatmap groupby, but NOT for the shot frame filtering itself (line 102 does not filter referees from `shots` DataFrame before scoring)
- `feature_engineering.py` spatial metrics — NOT filtered; convex hull, nearest_opponent, paint_count calculations include referee positions → inflates defender-distance scores

**Fix required in `feature_engineering.py`:** Before computing any spatial metric that groups by frame across all players, add:
```python
# Filter referees from all spatial metric calculations
non_ref = df[df["team"] != "referee"].copy()
# Use non_ref instead of df for spacing, hull, nearest_opponent calculations
```

**Fix required in `shot_quality.py`:** Line 102 — filter referees before extracting the shots DataFrame:
```python
shots = df[(df.get("event", pd.Series()) == "shot") &
           (df.get("team", pd.Series()) != "referee")].copy()
```

### Anti-Patterns to Avoid

- **Running OCR inside `get_players_pos` on every frame:** Adds 40ms+ per frame per player crop → stalls the tracking loop at <1 fps. Keep OCR in a separate annotation pass.
- **Initializing EasyOCR Reader per crop:** `easyocr.Reader(['en'])` takes 2+ seconds to initialize. Initialize once, reuse globally (see `get_reader()` pattern above).
- **Trusting single-frame OCR reads:** On broadcast crops, single-frame accuracy is ~50-60% without fine-tuning. Always require 3 consecutive identical reads.
- **k-means on every frame in the tracking loop:** k-means on 70×40px ROI takes ~5ms per call with scikit-learn. Call it during `_reid` (gallery lookup, infrequent) not during `_match_team` (every frame for every player).
- **Hard-coded team IDs in analytics filters:** Use the string label `"referee"` (matches the tracker's team classification) not a numeric `team_id=2` for CSV-based analytics; use `team_id IS NOT NULL AND team_id != 2` for PostgreSQL queries.
- **Calling CommonTeamRoster inside the frame loop:** It makes an HTTP request. Cache the result in `data/nba/` (existing caching pattern) and load once before the clip starts.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Digit recognition from image | Custom CNN or regex on raw pixels | EasyOCR with `allowlist='0123456789'` | EasyOCR handles detection + recognition in one call; digit-only allowlist eliminates non-digit outputs; GPU-accelerated |
| Color clustering | Manual histogram thresholding to find dominant color | `sklearn.cluster.KMeans(n_clusters=3)` | Handles multimodal distributions (e.g., jersey + skin + background); well-tested; already in env |
| Roster data | Scraping NBA.com HTML | `nba_api.stats.endpoints.CommonTeamRoster` | Official endpoint; returns structured data with PLAYER_ID, NUM, PLAYER fields; already cached by project pattern |
| Image contrast enhancement | Manual gamma correction | `cv2.createCLAHE()` | CLAHE adapts locally; outperforms global histogram equalization on uneven lighting conditions in arena broadcasts |

**Key insight:** OCR on sports video is a solved problem at the pipeline level — the challenge is preprocessing quality and voting robustness, not OCR architecture. Use commodity tools with good preprocessing rather than custom models.

---

## Common Pitfalls

### Pitfall 1: EasyOCR Misreads on Dark Jerseys
**What goes wrong:** On dark (black/navy/dark green) jerseys, the digit area has low contrast. EasyOCR returns empty results or misreads numbers as letters even with `allowlist`.
**Why it happens:** CLAHE applied to a nearly-uniform dark region produces low-frequency noise, not clear digit outlines.
**How to avoid:** After CLAHE, apply adaptive thresholding (`cv2.adaptiveThreshold`) with ADAPTIVE_THRESH_GAUSSIAN_C before feeding to EasyOCR. Also try inverting the image (white digits on dark → dark digits on white) and run OCR on both versions, taking the higher-confidence result.
**Warning signs:** Confirmed jersey numbers are all in range 1–9 (single digit bias), or very few slots are ever confirmed.

### Pitfall 2: K-Means Not Converging on Small Crops
**What goes wrong:** With crops smaller than ~20×10px, k-means with k=3 may fail to find 3 distinct clusters and assigns all pixels to 1–2 clusters.
**Why it happens:** Not enough pixels for meaningful clustering at k=3.
**How to avoid:** Add a size guard: if `roi.size < 600` (approximately 20×30px), fall back to a simple mean-color HSV vector rather than k-means. The CLAHE + upscale in `preprocess_crop` also mitigates this.
**Warning signs:** `KMeans.inertia_` is near 0 or cluster centers are nearly identical.

### Pitfall 3: Player ID Mapping Breaks on Track Eviction
**What goes wrong:** When a player track is evicted (lost for `MAX_LOST=90` frames) and a new detection fills the same slot, the confirmed jersey number from the old occupant is carried over to the new player.
**Why it happens:** `JerseyVotingBuffer` dict is keyed by slot number, not by a stable identity token.
**How to avoid:** Call `buf.reset_slot(slot)` inside `AdvancedFeetDetector._activate_slot` whenever `p.previous_bb is None` before activation (i.e., when the slot was previously empty). This is the same place `self._gallery.pop(slot, None)` already fires.
**Warning signs:** Player #23 is correctly identified, then #4 shows up in the same slot and is still labeled as #23.

### Pitfall 4: CommonTeamRoster NUM Field is a String, Not Int
**What goes wrong:** Some rosters return `NUM=""` for players on two-way contracts or exhibit entries. Treating all NUM values as integers raises exceptions.
**Why it happens:** The NBA API returns NUM as a string; some entries are empty or contain non-numeric characters.
**How to avoid:** Use `num_str.isdigit()` guard before `int(num_str)` (shown in `fetch_roster` pattern above). Log how many roster entries had missing NUM values.
**Warning signs:** `ValueError: invalid literal for int()` during roster parse.

### Pitfall 5: Broadcast Clip Download Fails Due to YouTube Bot Detection
**What goes wrong:** `yt-dlp` returns HTTP 403 or "Sign in to confirm you're not a bot" even with browser cookies.
**Why it happens:** YouTube increasingly challenges automated downloads. The existing `video_fetcher.py` handles this with a cookie file fallback, but the cookie file may expire.
**How to avoid:** The existing `video_fetcher.py` already documents the fix (export cookies via "Get cookies.txt LOCALLY" extension). For REQ-08b, acquire clips in batches and store them locally — the manifest.json prevents re-downloading. NBA.com official highlights are more reliable than YouTube search queries.
**Warning signs:** `RuntimeError: YouTube download failed (bot detection)` in the fetcher output.

### Pitfall 6: Referee Rows in Convex Hull Calculations
**What goes wrong:** `feature_engineering.py` computes `team_spacing` (convex hull area) and `paint_count_opp` across all rows in a frame group. Referee positions near the paint inflate `paint_count_opp` for the wrong team and shrink the convex hull area for the team they are near.
**Why it happens:** The current `feature_engineering.py` does not filter `team == "referee"` before spatial metric calculations (only analytics modules do).
**How to avoid:** Add the referee filter at the top of each spatial metric function in `feature_engineering.py`.
**Warning signs:** `defense_pressure` output shows unexpectedly high pressure values even when players are spread out.

---

## Code Examples

### EasyOCR digit-only read with preprocessing
```python
# Source: EasyOCR documentation (https://www.jaided.ai/easyocr/documentation/)
# and GitHub issue #341 (thresholding improves single-digit accuracy)
reader = easyocr.Reader(['en'], gpu=True, verbose=False)
results = reader.readtext(
    preprocessed_gray_image,
    allowlist='0123456789',
    detail=1,
    paragraph=False,
    width_ths=0.7,    # merge nearby detections
    min_size=5,       # accept small digit boxes
)
# results: [([[x1,y1],[x2,y1],[x2,y2],[x1,y2]], '23', 0.87), ...]
```

### CommonTeamRoster jersey number lookup
```python
# Source: nba_api GitHub docs
# https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/commonteamroster.md
from nba_api.stats.endpoints import CommonTeamRoster
roster = CommonTeamRoster(team_id='1610612737', season='2024-25')
df = roster.get_data_frames()[0]
# df columns: PLAYER, PLAYER_SLUG, NUM, POSITION, HEIGHT, WEIGHT, PLAYER_ID, ...
jersey_map = {
    int(row['NUM']): {'player_id': int(row['PLAYER_ID']), 'player_name': row['PLAYER']}
    for _, row in df.iterrows()
    if str(row['NUM']).strip().isdigit()
}
```

### OpenCV CLAHE + adaptive threshold pipeline
```python
# Standard OpenCV preprocessing for low-contrast digit crops
gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
enhanced = clahe.apply(gray)
# Adaptive threshold helps on dark jerseys
binary = cv2.adaptiveThreshold(
    enhanced, 255,
    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
    cv2.THRESH_BINARY, 11, 2
)
```

### Referee filter guard (analytics modules)
```python
# Pattern to apply at top of any per-frame spatial calculation
non_ref = df[df["team"] != "referee"].copy()
# For PostgreSQL queries:
# WHERE team_id IS NOT NULL AND team_id != 2
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tesseract for jersey OCR | EasyOCR / VLM approaches | 2023-2025 | EasyOCR is faster, more accurate on degraded images; VLMs (SmolVLM2, ResNet-32) achieve 86-93% with custom training |
| Single-frame OCR commit | Multi-frame vote buffering | Industry practice since ~2023 | Eliminates most false identity assignments without custom training data |
| Global HSV threshold for team color | k-means clustering | 2022-2024 | Handles multi-modal color distributions; more robust to lighting changes |
| Anonymous slot IDs throughout pipeline | Named player IDs via OCR | This phase | Enables lineup analytics, per-player props, and named player heatmaps |

**Deprecated/outdated:**
- Tesseract for sports video OCR: performs poorly on small, low-contrast crops; replaced by EasyOCR in the Python sports-CV ecosystem.
- Single dominant color for re-ID: known to fail when two teams wear similar primary colors (e.g., BOS green vs. MIL green); k-means with k=3 captures multi-tone uniform patterns.

---

## Open Questions

1. **OCR accuracy on the specific calibration clip**
   - What we know: The clip used for development is `Short4Mosaicing.mp4` — a non-broadcast calibration clip; jersey numbers may be low resolution or partially visible.
   - What's unclear: Whether EasyOCR will achieve >=3 consecutive confirmed reads per slot on the existing footage, or whether real broadcast clips (REQ-08b) are required first.
   - Recommendation: Implement OCR + voting buffer, run on existing 16 processed games, measure confirmation rate per slot. If <50% of slots confirm within a clip, prioritize REQ-08b footage acquisition before tuning OCR.

2. **Team ID availability at OCR time**
   - What we know: The tracker assigns team classification ("green"/"white"/"referee") but the `fetch_roster` function needs an integer NBA `team_id`. The `run_clip.py` entry point accepts `--game-id` but not `--home-team-id` / `--away-team-id`.
   - What's unclear: How to resolve the two-team roster lookup without knowing which HSV color corresponds to which NBA team.
   - Recommendation: In `player_identity.py`, accept both rosters (`home_roster` and `away_roster`). When confirming a jersey number, try both rosters; use the one that returns a valid match. Persist the color→team_id resolution in the `player_identity_map` table.

3. **PostgreSQL connection availability**
   - What we know: Phase 1 created `database/schema.sql` but the connection string / credentials are not wired into any module yet.
   - What's unclear: Whether psycopg2 is installed in the `basketball_ai` env and what the connection string is.
   - Recommendation: Plan 02-02 (PostgreSQL persistence) should start with a connection helper module (`src/data/db.py`) that reads `DATABASE_URL` from environment or a `.env` file, and test the connection before building the persistence layer.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (standard) — no config file detected, tests run as plain Python scripts today |
| Config file | None detected — Wave 0 should add `pytest.ini` |
| Quick run command | `conda run -n basketball_ai pytest tests/ -x -q` |
| Full suite command | `conda run -n basketball_ai pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-04 | `read_jersey_number()` returns int in range 0-99 or None | unit | `pytest tests/test_jersey_ocr.py -x` | ❌ Wave 0 |
| REQ-04 | Voting buffer confirms same number after 3 reads | unit | `pytest tests/test_jersey_ocr.py::test_voting_buffer -x` | ❌ Wave 0 |
| REQ-05 | `fetch_roster()` returns dict with known player jersey numbers | unit (cached) | `pytest tests/test_player_identity.py::test_fetch_roster -x` | ❌ Wave 0 |
| REQ-06 | `player_identity_map` rows inserted and `tracking_frames.player_id` updated | integration | `pytest tests/test_player_identity.py::test_db_persistence -x` | ❌ Wave 0 |
| REQ-07 | `dominant_hsv_cluster()` returns 3-dim vector; different teams produce distinct clusters | unit | `pytest tests/test_jersey_ocr.py::test_kmeans_cluster -x` | ❌ Wave 0 |
| REQ-08 | `defense_pressure.run()` output contains no referee rows | unit | `pytest tests/test_analytics_filter.py -x` | ❌ Wave 0 |
| REQ-08b | At least 5 video files in `data/videos/` | smoke | `pytest tests/test_footage.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `conda run -n basketball_ai pytest tests/ -x -q`
- **Per wave merge:** `conda run -n basketball_ai pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pytest.ini` — configure testpaths, markers
- [ ] `tests/test_jersey_ocr.py` — unit tests for `preprocess_crop`, `read_jersey_number`, `JerseyVotingBuffer`, `dominant_hsv_cluster` — covers REQ-04, REQ-07
- [ ] `tests/test_player_identity.py` — unit tests for `fetch_roster`, `player_identity_map` DB writes — covers REQ-05, REQ-06
- [ ] `tests/test_analytics_filter.py` — verify referee rows absent from all analytics outputs — covers REQ-08
- [ ] `tests/test_footage.py` — smoke test that >=5 clips exist in data/videos/ — covers REQ-08b
- [ ] `tests/conftest.py` — shared fixtures: synthetic crop images, mock NBA API responses, temp database

---

## Sources

### Primary (HIGH confidence)
- `nba_api` GitHub `commonteamroster.md` — endpoint fields confirmed (NUM, PLAYER_ID, PLAYER)
- `advanced_tracker.py` source read — existing HSV embedding and re-ID code patterns
- `defense_pressure.py`, `momentum.py`, `shot_quality.py` source read — referee filter status confirmed
- `database/schema.sql` source read — confirmed `player_id`, `tracker_player_id` columns exist in `tracking_frames`
- EasyOCR PyPI + official docs (https://www.jaided.ai/easyocr/documentation/) — `allowlist` parameter, GPU support
- EasyOCR GitHub issue #341 — binary inverse thresholding improves single-digit recognition

### Secondary (MEDIUM confidence)
- Roboflow blog (https://blog.roboflow.com/identify-basketball-players/) — multi-frame voting (confirm after 3 consecutive reads), ResNet-32 vs SmolVLM2 accuracy comparison on 2025 NBA Playoffs crops
- WebSearch: `CommonTeamRoster` usage pattern and field names — verified against official nba_api GitHub docs
- WebSearch: PaddleOCR installation complexity on Windows/conda — confirmed requires separate PaddlePaddle framework install
- scikit-learn KMeans API — standard and well-documented; usage pattern confirmed

### Tertiary (LOW confidence)
- Accuracy figures (EasyOCR ~56% baseline, ResNet-32 93% after fine-tuning) are from Roboflow's specific 2025 NBA Playoffs dataset and may not generalize to other footage
- k=3 as the correct cluster count for jerseys — reasonable given jersey + skin + background, but not empirically validated on this specific codebase's footage

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — EasyOCR installation path confirmed; nba_api roster endpoint verified against official docs; existing codebase libraries confirmed via source read
- Architecture: MEDIUM — OCR annotation pass pattern is well-established; specific accuracy on this project's footage is untested
- Pitfalls: MEDIUM-HIGH — single-digit EasyOCR issues confirmed via GitHub issues; track eviction mapping bug is a logical analysis of the existing code structure

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable libraries; nba_api endpoint stability is HIGH)
