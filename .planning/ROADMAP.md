# Roadmap: NBA AI Basketball Tracking System

## Overview

Six phases deliver the end-to-end pipeline. Phase 1 builds the foundation: video ingestion, computer vision tracking, and database storage — raw footage becomes structured coordinates. Phase 2 computes basketball-specific features from those coordinates. Phase 3 trains the ML models that generate betting-relevant predictions. Phase 4 exposes everything through a dashboard and API. Phase 5 adds the conversational AI interface. Phase 6 automates the full pipeline and validates every module with tests.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: CV Pipeline + Storage** - Ingest NBA footage, detect and track objects frame-by-frame, store coordinates to PostgreSQL
- [ ] **Phase 2: Feature Engineering** - Compute basketball-specific spatial and temporal features from tracking data
- [ ] **Phase 3: ML Models** - Train shot probability, win probability, momentum, and player impact models
- [ ] **Phase 4: Dashboard + API** - Expose predictions and analytics through Streamlit dashboard and FastAPI endpoints
- [ ] **Phase 5: Conversational AI** - Natural-language interface that answers game and player queries using live model data
- [ ] **Phase 6: Automation + Testing** - End-to-end pipeline scripts and unit/validation tests for every module

## Phase Details

### Phase 1: CV Pipeline + Storage
**Goal**: Raw NBA game footage can be processed through the computer vision pipeline and all tracking data is stored to the database
**Depends on**: Nothing (first phase)
**Requirements**: CV-01, CV-02, CV-03, CV-04, CV-05, CV-06, DB-01, DB-02, DB-03
**Success Criteria** (what must be TRUE):
  1. A local video file can be passed to the pipeline and YOLOv8 produces bounding boxes for players and the basketball in each frame with confidence scores
  2. Court lines and key zone boundaries (paint, three-point line, half-court) are detected and usable as spatial reference
  3. DeepSORT assigns persistent IDs to each player and ball that remain consistent across frames throughout a sequence
  4. Frame-by-frame coordinates, velocities, and movement directions for all tracked objects are written to the PostgreSQL tracking_coordinates table
  5. The database schema exists with all required tables (games, players, tracking_coordinates, possessions, shot_logs) and contains enough historical data depth to support ML training
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — PostgreSQL schema, Python environment, project package structure
- [ ] 01-02-PLAN.md — Video ingestion + YOLOv8 player/ball detection + court zone detection
- [ ] 01-03-PLAN.md — Historical game and player data seeding for ML training depth
- [ ] 01-04-PLAN.md — DeepSORT tracking + coordinate computation + pipeline CLI + DB write

### Phase 2: Feature Engineering
**Goal**: Structured basketball features are computed from tracking coordinates and available for model training
**Depends on**: Phase 1
**Requirements**: FE-01, FE-02, FE-03, FE-04, FE-05, FE-06
**Success Criteria** (what must be TRUE):
  1. Player spacing metrics (convex hull area, average inter-player distance) are computed per possession from tracking data
  2. Defensive pressure values (nearest defender distance, closing speed) are computed per player per frame
  3. Off-ball movement events (cuts, screens, drift) are detected and tagged from tracking sequences
  4. Pick-and-roll events are identified and recorded with the players involved
  5. Passing networks are built from possession data showing who passes to whom and at what frequency, and momentum metrics (scoring runs, possession streaks, swing points) are available per game segment
**Plans**: TBD

### Phase 3: ML Models
**Goal**: Five trained models produce betting-relevant predictions from the computed features
**Depends on**: Phase 2
**Requirements**: ML-01, ML-02, ML-03, ML-04, ML-05
**Success Criteria** (what must be TRUE):
  1. The shot probability model outputs a [0,1] probability for any shot attempt given defender distance, shot angle, fatigue proxy, and court location
  2. The win probability model outputs a per-possession game win probability updated from lineup combinations, momentum score, spacing, and efficiency metrics
  3. The momentum detection model identifies scoring streaks and possession-change patterns that signal momentum shifts in a game
  4. The player impact model outputs expected points added (EPA) per player per 100 possessions
  5. The lineup optimization model scores any lineup combination by defensive disruption and offensive gravity
**Plans**: TBD

### Phase 4: Dashboard + API
**Goal**: Model predictions and analytics are accessible through a visual dashboard and REST API
**Depends on**: Phase 3
**Requirements**: UI-01, UI-02, UI-03, UI-04, API-01, API-02
**Success Criteria** (what must be TRUE):
  1. The Streamlit dashboard shows an interactive shot chart with a court diagram and makes/misses/zones rendered in Plotly
  2. The dashboard shows defensive pressure heatmaps and player tracking overlays (movement paths on court) and lineup impact graphs with net rating and EPA
  3. FastAPI endpoints return model predictions (shot probability, win probability, player impact) for valid query parameters
  4. FastAPI endpoints return analytics data (shot charts, lineup stats, tracking data) for valid query parameters
**Plans**: TBD

### Phase 5: Conversational AI
**Goal**: A natural-language interface answers game prediction, player stat, and game explanation queries using live model data
**Depends on**: Phase 4
**Requirements**: AI-01, AI-02, AI-03, AI-04
**Success Criteria** (what must be TRUE):
  1. Typing "Predict tonight's games" returns win probability estimates for current matchups
  2. Typing "Show Curry's shot chart" returns a visualization of shot locations and outcomes
  3. Typing "Explain why Boston won" returns a narrative analysis backed by model data from that game
  4. Each conversational response is generated by querying PostgreSQL and/or running models dynamically — not from static cached text
**Plans**: TBD

### Phase 6: Automation + Testing
**Goal**: The full pipeline runs end-to-end via automation scripts and every module is validated by unit tests and self-checking scripts
**Depends on**: Phase 5
**Requirements**: AUTO-01, AUTO-02, AUTO-03, AUTO-04, TEST-01, TEST-02
**Success Criteria** (what must be TRUE):
  1. Running the ingestion script on a raw video file triggers the full CV pipeline and writes tracking data to the database without manual steps
  2. Running the training script pulls historical data, trains all models, and saves artifacts ready for inference
  3. Running the prediction script loads trained models, scores current game data, and outputs predictions to a readable format
  4. Running the dashboard refresh script pulls the latest data and updates Streamlit visualizations without manual intervention
  5. Unit tests pass for each module (CV, feature engineering, ML, API, dashboard) and self-checking scripts confirm output correctness and data integrity for each
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. CV Pipeline + Storage | 1/4 | In Progress|  |
| 2. Feature Engineering | 0/TBD | Not started | - |
| 3. ML Models | 0/TBD | Not started | - |
| 4. Dashboard + API | 0/TBD | Not started | - |
| 5. Conversational AI | 0/TBD | Not started | - |
| 6. Automation + Testing | 0/TBD | Not started | - |
