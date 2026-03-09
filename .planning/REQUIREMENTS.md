# Requirements: NBA AI Basketball Tracking System

**Defined:** 2026-03-09
**Core Value:** A fully connected end-to-end pipeline where raw video goes in, betting-relevant predictions come out — every layer wired together and working.

## v1 Requirements

### Computer Vision

- [ ] **CV-01**: System ingests downloaded NBA game footage (local video files) as pipeline input
- [ ] **CV-02**: YOLOv8 detects players and basketball in each frame with bounding boxes and confidence scores
- [ ] **CV-03**: YOLOv8 detects court lines and key zone boundaries (paint, three-point line, half-court)
- [ ] **CV-04**: DeepSORT assigns and maintains persistent IDs for each detected player and ball across frames
- [ ] **CV-05**: Pipeline outputs frame-by-frame coordinates, velocities, and movement directions for all tracked objects
- [ ] **CV-06**: Tracking output is stored to PostgreSQL in the tracking_coordinates table

### Data Storage

- [ ] **DB-01**: PostgreSQL database schema with tables: games, players, tracking_coordinates, possessions, shot_logs
- [ ] **DB-02**: Database maintains historical datasets suitable for ML training (sufficient historical depth)
- [ ] **DB-03**: Data pipeline writes tracking, possession, and shot event records automatically after processing

### Feature Engineering

- [ ] **FE-01**: Player spacing metric computed from tracking coordinates (convex hull area, average inter-player distance)
- [ ] **FE-02**: Defensive pressure metric computed per player (nearest defender distance, closing speed)
- [ ] **FE-03**: Off-ball movement patterns detected (cuts, screens, drift)
- [ ] **FE-04**: Pick-and-roll events detected and tagged from tracking data
- [ ] **FE-05**: Passing networks built from possession and tracking data (who passes to whom, frequency)
- [ ] **FE-06**: Momentum metrics computed (scoring runs, possession streaks, swing points)

### Machine Learning Models

- [ ] **ML-01**: Shot probability model trained on defender distance, shot angle, fatigue proxy, and court location; outputs probability [0,1] per shot attempt
- [ ] **ML-02**: Win probability model trained on lineup combinations, momentum score, spacing, and efficiency metrics; outputs game win probability updated per possession
- [ ] **ML-03**: Momentum detection model identifies scoring streaks and possession change patterns that signal momentum shifts
- [ ] **ML-04**: Player impact model computes expected points added (EPA) per player per 100 possessions
- [ ] **ML-05**: Lineup optimization model scores lineup combinations by defensive disruption and offensive gravity

### Dashboard & API

- [ ] **UI-01**: Streamlit dashboard with Plotly shot charts (court diagram, makes/misses/zones)
- [ ] **UI-02**: Streamlit dashboard with defensive pressure heatmaps (spatial coverage visualization)
- [ ] **UI-03**: Streamlit dashboard with player tracking overlays (movement paths on court diagram)
- [ ] **UI-04**: Streamlit dashboard with lineup impact graphs (net rating and EPA by lineup)
- [ ] **API-01**: FastAPI exposes REST endpoints for model predictions (shot probability, win probability, player impact)
- [ ] **API-02**: FastAPI exposes REST endpoints for analytics queries (shot charts, lineup stats, tracking data)

### Conversational AI Interface

- [ ] **AI-01**: Conversational interface accepts natural-language game prediction queries ("Predict tonight's games") and returns win probabilities
- [ ] **AI-02**: Conversational interface accepts player stat queries ("Show Curry's shot chart") and returns visualizations
- [ ] **AI-03**: Conversational interface accepts game explanation queries ("Explain why Boston won") and returns narrative analysis backed by model data
- [ ] **AI-04**: AI interface queries PostgreSQL and runs models dynamically to answer each prompt

### Automation & Testing

- [ ] **AUTO-01**: Automated script for video ingestion (ingest raw footage → run CV pipeline → store to DB)
- [ ] **AUTO-02**: Automated script for ML training (pull historical data → train models → save artifacts)
- [ ] **AUTO-03**: Automated script for prediction generation (load models → score current games → output predictions)
- [ ] **AUTO-04**: Automated script for dashboard refresh (pull latest data → update Streamlit visualizations)
- [ ] **TEST-01**: Unit tests for each module (CV pipeline, feature engineering, ML models, API, dashboard)
- [ ] **TEST-02**: Self-checking scripts for each module that validate output correctness and data integrity

## v2 Requirements

### Enhanced Analytics

- **V2-01**: Real-time in-game tracking (live feed processing, not just post-game)
- **V2-02**: Advanced play classification (fast break, half-court sets, transition defense)
- **V2-03**: Referee tendency modeling
- **V2-04**: Injury/fatigue modeling from movement patterns across multi-game stretches

### Expanded Interface

- **V2-01**: Mobile-friendly dashboard
- **V2-02**: Automated daily prediction reports delivered via email/Slack
- **V2-03**: Backtesting engine to evaluate model profitability on historical lines

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time broadcast capture | Legal/technical complexity; working from downloaded files only |
| Official NBA API streaming | Licensing constraints; pipeline must work on locally-owned footage |
| Mobile app | Web-first via Streamlit |
| Manual data entry UI | All data flows through automated pipelines |
| Social / sharing features | Solo analysis tool |
| Managed cloud hosting | User manages own infrastructure |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CV-01 – CV-06 | Phase 1 | Pending |
| DB-01 – DB-03 | Phase 1 | Pending |
| FE-01 – FE-06 | Phase 2 | Pending |
| ML-01 – ML-05 | Phase 3 | Pending |
| API-01 – API-02 | Phase 4 | Pending |
| UI-01 – UI-04 | Phase 4 | Pending |
| AI-01 – AI-04 | Phase 5 | Pending |
| AUTO-01 – AUTO-04 | Phase 6 | Pending |
| TEST-01 – TEST-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after initial definition*
