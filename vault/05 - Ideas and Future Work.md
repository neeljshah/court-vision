# Ideas and Future Work
*Last updated: 2026-03-24*

← [[04 - Pipeline Flow]] | [[00 - Home]]

---

## Immediate Next Steps (Phase F/G)

### Phase F — Full Game Processing (NEXT)
- Build `scripts/full_game_pipeline.py` — downloads full NBA game from YouTube (yt-dlp ytsearch), processes with `--game-id`, populates `data/full_game_results.json`
- Wire `DATABASE_URL` → PostgreSQL writes live
- Target: 10 full games processed

### Phase G — Cloud GPU Blast
- RunPod A100 (or equivalent)
- Budget: $50–100
- Target: 50–100 games
- Unlocks: xFG v2, shot selection quality, all Tier 3 models

---

## CV Tracker Upgrades (Phase 2.5)

### Highest ROI Improvements

**1. Pose Estimation (3 days, closes 60% of gap vs Second Spectrum)**
- Replace bbox-bottom foot heuristic with YOLOv8-pose ankle keypoints
- Position accuracy: ±24" → ±6–8"
- Already: `yolov8n-pose.pt` and `yolov8n-pose.onnx` in repo root

**2. ByteTrack (replaces Kalman+Hungarian)**
- ID switch rate: ~15% → ~3%
- Tested ByteTrack implementation in `deep-sort-realtime`
- Implementation effort: ~2 days

**3. Per-Clip Homography (ISSUE-017 partial fix)**
- Current: M1 calibrated for pano_enhanced angle
- Fix: `detect_court_homography()` auto-detects per-broadcast-angle
- 3 of 4 clips detect cleanly; 1 still falls back

**4. OSNet Deep Re-ID (already partially built)**
- `src/re_id/` — full OSNet training pipeline exists
- Replace 99-dim HSV with 256-dim OSNet embeddings
- Training data: `src/re_id/data/download_data.py`

### What's Not Worth Chasing

- Ball height: requires stereo vision or depth sensor. Worth ~1% accuracy.
- Hand contest angle: requires high-fps camera or pose on arms. Worth ~1%.
- These two combined (~2%) are not worth the engineering cost for prop markets.

---

## Model Ideas

### Short-Term (Phase 5–7)

- **Shot arc predictor** — parabola fit on ball trajectory → shot quality vs optimal arc. Requires ball height proxy.
- **Double-team detector** — detect when 2 defenders converge on ball handler (CV spatial)
- **Screen effectiveness model** — does the screen actually free the cutter? Synergy data + CV
- **Foul drawing rate model** — foul_draw_rate_model.py built, needs shot_type + contact features
- **Contested shot predictor** — contested_rate_model.py built, needs CV defender dist

### Medium-Term (Phase 9–12)

- **Lineup chemistry matrix** — mutual information between any two players' on-court + metrics
- **Fatigue curve** — player speed vs personal baseline as game progresses (needs 50+ games)
- **Late-game efficiency split** — separate model for clutch possessions (Q4 <5 min, <5 pt margin)
- **Closeout quality** — how fast does the defender close out on perimeter shots?

### Long-Term (Phase 15–16)

- **Live win probability LSTM** — possession-by-possession sequence model (needs 200+ games)
- **Real-time prop updater** — adjusts in-game prop lines as game evolves
- **Player fatigue alert** — flag "this player is tired, expect performance drop" mid-game
- **Coming off injury adjustment** — separate regime model for first 10 games after return

---

## Betting Edge Ideas

### Book-Level Arbitrage
- **Soft book lag detector** — built in `soft_book_lag.py`. Some books price props 15–30 min behind sharp markets. Time the window.
- **Alt line EV** — `alt_line_ev_model.py` built. Alt lines often mispriced relative to main line.
- **Same-game parlay optimizer** — `parlay_optimizer.py` built. Correlations between same-game stats are exploitable.

### Market Timing
- **Injury news lag** — injury_news_lag.py built. Best edge is in the 15–60 min window between beat reporter tweet and official report.
- **Line movement prediction** — `line_movement_predictor.py` built. Predict where the line moves → bet before move.

### Untapped Markets
- **First basket scorer** — correlated with lineup, offense type, tip-off winner
- **Player points in first quarter** — starters playing full Q1 → predictable shot volume
- **Assist totals** — highly correlated with pace, usage distribution, and opponent defensive scheme

---

## Infrastructure Ideas

### Performance
- **TensorRT FP16 for YOLOv8** — already YOLO TRT FP16 used for ball. Apply same to player detection.
- **Async NBA API fetcher** — `aiohttp` batch requests vs sequential `nba_api` calls
- **Redis caching layer** — cache all prediction results with 5-min TTL to avoid re-compute
- **Model serving with ONNX** — convert XGBoost → ONNX for 3–5× inference speedup in API

### Observability
- **Prediction tracking DB table** — store every prediction with model version, features used, confidence
- **Model drift dashboard** — Streamlit view of accuracy over time per model
- **CLV dashboard** — visual CLV trend vs closing line by sport, book, market type

### Cloud Architecture (Phase 17)
- **Containerize** — Docker + docker-compose (already started in Dockerfile)
- **CI/CD** — GitHub Actions (already started in `.github/workflows/ci-cd.yml`)
- **Cloud DB** — AWS RDS PostgreSQL or Supabase
- **Video processing** — RunPod / Lambda GPU instances (spot instances for cost)
- **Model registry** — MLflow or DVC for model versioning at scale

---

## AI Chat (Phase 15) Ideas

Tool ideas for the Claude AI chat:
- `get_player_props(player_name, date)` → props + model projection + edge
- `get_game_prediction(home, away, date)` → win prob + spread + total
- `render_shot_chart(player_name, season, split)` → D3 hexbin shot chart
- `get_lineup_matrix(team, opponent)` → lineup combinations + net rating
- `get_win_prob_timeline(game_id)` → waterfall chart of win prob over possessions
- `compare_players(player1, player2, stat)` → bar chart comparison
- `get_injury_news(team)` → latest injury report + impact on props
- `get_betting_edges(date, min_ev)` → list of flagged +EV props
- `simulate_game(home, away, n_sims)` → Monte Carlo results
- `get_lineup_optimizer(slate_type, budget)` → DFS lineup suggestions

---

## Research Ideas

- **Tournament-style simulation** — simulate playoff bracket, conference finals, NBA Finals odds
- **Trade impact model** — estimate stat change from player trade using lineup chemistry + usage
- **Draft model** — project rookie performance from college stats + combine + CV (college video)
- **G-League pipeline** — same CV pipeline on G-League footage to find call-ups before they happen

---

## Related Notes

- [[01 - System Architecture]] — current architecture
- [[02 - Model Catalog]] — model roadmap
- [[04 - Pipeline Flow]] — how to implement new models
