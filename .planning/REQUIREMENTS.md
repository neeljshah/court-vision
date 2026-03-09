# Requirements: NBA AI Basketball Tracking System

**Defined:** 2026-03-09
**Core Value:** A fully connected end-to-end pipeline where raw video goes in, betting-relevant predictions come out — every layer wired together and working.

## v1 Requirements

### Computer Vision

- [x] **CV-01**: System ingests downloaded NBA game footage (local video files) as pipeline input
- [x] **CV-02**: YOLOv8 detects players and basketball in each frame with bounding boxes and confidence scores
- [x] **CV-03**: YOLOv8 detects court lines and key zone boundaries (paint, three-point line, half-court)
- [x] **CV-04**: DeepSORT assigns and maintains persistent IDs for each detected player and ball across frames
- [x] **CV-05**: Pipeline outputs frame-by-frame coordinates, velocities, and movement directions for all tracked objects
- [x] **CV-06**: Tracking output is stored to PostgreSQL in the tracking_coordinates table

### Data Storage

- [x] **DB-01**: PostgreSQL database schema with tables: games, players, tracking_coordinates, possessions, shot_logs
- [x] **DB-02**: Database maintains historical datasets suitable for ML training (sufficient historical depth)
- [x] **DB-03**: Data pipeline writes tracking_coordinates records automatically after processing a video file (Phase 1). Possession and shot event records are written automatically in Phase 2, after feature engineering detects those events from tracking data.

### Feature Engineering

- [x] **FE-01**: Player spacing metric computed from tracking coordinates (convex hull area, average inter-player distance)
- [x] **FE-02**: Defensive pressure metric computed per player (nearest defender distance, closing speed)
- [x] **FE-03**: Off-ball movement patterns detected (cuts, screens, drift)
- [x] **FE-04**: Pick-and-roll events detected and tagged from tracking data
- [x] **FE-05**: Passing networks built from possession and tracking data (who passes to whom, frequency)
- [x] **FE-06**: Momentum metrics computed (scoring runs, possession streaks, swing points)

### Machine Learning Models

- [x] **ML-01**: Shot probability model trained on defender distance, shot angle, fatigue proxy, and court location; outputs probability [0,1] per shot attempt
- [x] **ML-02**: Win probability model trained on lineup combinations, momentum score, spacing, and efficiency metrics; outputs game win probability updated per possession
- [x] **ML-03**: Momentum detection model identifies scoring streaks and possession change patterns that signal momentum shifts
- [x] **ML-04**: Player impact model computes expected points added (EPA) per player per 100 possessions
- [x] **ML-05**: Lineup optimization model scores lineup combinations by defensive disruption and offensive gravity

### Dashboard & API

- [ ] **UI-01**: Streamlit dashboard with Plotly shot charts (court diagram, makes/misses/zones)
- [ ] **UI-02**: Streamlit dashboard with defensive pressure heatmaps (spatial coverage visualization)
- [ ] **UI-03**: Streamlit dashboard with player tracking overlays (movement paths on court diagram)
- [ ] **UI-04**: Streamlit dashboard with lineup impact graphs (net rating and EPA by lineup)
- [x] **API-01**: FastAPI exposes REST endpoints for model predictions (shot probability, win probability, player impact)
- [x] **API-02**: FastAPI exposes REST endpoints for analytics queries (shot charts, lineup stats, tracking data)

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
| CV-01 | Phase 1 — CV Pipeline + Storage | Complete |
| CV-02 | Phase 1 — CV Pipeline + Storage | Complete |
| CV-03 | Phase 1 — CV Pipeline + Storage | Complete |
| CV-04 | Phase 1 — CV Pipeline + Storage | Complete |
| CV-05 | Phase 1 — CV Pipeline + Storage | Complete |
| CV-06 | Phase 1 — CV Pipeline + Storage | Complete |
| DB-01 | Phase 1 — CV Pipeline + Storage | Complete |
| DB-02 | Phase 1 — CV Pipeline + Storage | Complete |
| DB-03 | Phase 1 (tracking_coordinates) + Phase 2 (possessions, shot_logs) | Complete |
| FE-01 | Phase 2 — Feature Engineering | Complete |
| FE-02 | Phase 2 — Feature Engineering | Complete |
| FE-03 | Phase 2 — Feature Engineering | Complete |
| FE-04 | Phase 2 — Feature Engineering | Complete |
| FE-05 | Phase 2 — Feature Engineering | Complete |
| FE-06 | Phase 2 — Feature Engineering | Complete |
| ML-01 | Phase 3 — ML Models | Complete |
| ML-02 | Phase 3 — ML Models | Complete |
| ML-03 | Phase 3 — ML Models | Complete |
| ML-04 | Phase 3 — ML Models | Complete |
| ML-05 | Phase 3 — ML Models | Complete |
| UI-01 | Phase 4 — Dashboard + API | Pending |
| UI-02 | Phase 4 — Dashboard + API | Pending |
| UI-03 | Phase 4 — Dashboard + API | Pending |
| UI-04 | Phase 4 — Dashboard + API | Pending |
| API-01 | Phase 4 — Dashboard + API | Complete |
| API-02 | Phase 4 — Dashboard + API | Complete |
| AI-01 | Phase 5 — Conversational AI | Pending |
| AI-02 | Phase 5 — Conversational AI | Pending |
| AI-03 | Phase 5 — Conversational AI | Pending |
| AI-04 | Phase 5 — Conversational AI | Pending |
| AUTO-01 | Phase 6 — Automation + Testing | Pending |
| AUTO-02 | Phase 6 — Automation + Testing | Pending |
| AUTO-03 | Phase 6 — Automation + Testing | Pending |
| AUTO-04 | Phase 6 — Automation + Testing | Pending |
| TEST-01 | Phase 6 — Automation + Testing | Pending |
| TEST-02 | Phase 6 — Automation + Testing | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 — DB-03 clarified: Phase 1 covers tracking_coordinates writes; Phase 2 covers possessions and shot_logs writes after event detection feature engineering*
