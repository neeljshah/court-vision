# NBA AI Basketball Tracking System

## What This Is

A full-scale AI basketball analytics platform that ingests raw NBA game footage, runs computer vision pipelines for player/ball tracking, builds ML models for shot probability, win probability, and momentum detection, and surfaces insights through a conversational AI interface and interactive dashboard. Built to generate a genuine sports betting edge across game lines, live in-game wagering, and player props.

## Core Value

A fully connected end-to-end pipeline where raw video goes in, betting-relevant predictions come out — every layer (tracking → features → models → conversational AI) wired together and working.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Video ingestion pipeline processes downloaded NBA game footage
- [ ] YOLOv8 detects players, ball, and court lines frame-by-frame
- [ ] DeepSORT tracks detected objects across frames with IDs
- [ ] Frame-by-frame coordinates, velocities, and directions stored to PostgreSQL
- [ ] Database schema covers games, players, tracking_coordinates, possessions, shot_logs
- [ ] Spatial features computed: spacing, defensive pressure, off-ball movement, pick-and-roll detection, passing networks, momentum metrics
- [ ] Shot probability model uses defender distance, shot angle, fatigue, and court location
- [ ] Win probability model uses lineups, momentum, spacing, and efficiency
- [ ] Momentum detection model identifies scoring streaks and possession change patterns
- [ ] Player impact and lineup optimization outputs expected points added, defensive disruption, gravity
- [ ] Streamlit + Plotly dashboard with shot charts, defensive pressure maps, tracking overlays, lineup graphs
- [ ] FastAPI exposes model predictions and analytics as API endpoints
- [ ] Conversational AI interface answers natural-language prompts with visualizations
- [ ] Automation scripts for video ingestion, tracking, ML training, prediction, and dashboard generation
- [ ] Unit tests and self-checking scripts for each module

### Out of Scope

- Real-time video capture from broadcast feeds — working with downloaded footage only
- Mobile app — web-first via Streamlit
- Manual data entry UI — all data flows through automated pipelines
- Social/sharing features — this is a solo analysis tool

## Context

- **Video source:** Downloaded NBA game footage (local files), processed locally for inference
- **Betting target:** Full suite — pre-game win probabilities, live in-game probability shifts, and player prop projections
- **Hardware:** Mix of local (GPU available for dev/inference) and cloud (for heavy ML training)
- **Tech stack (locked):** Python, YOLOv8, DeepSORT, PostgreSQL, Streamlit, Plotly, FastAPI, Claude API for conversational interface
- **MCP connectors:** Used for database and runtime access within the GSD workflow
- **Repository layout:** tracking/, pipelines/, features/, models/, analytics/, api/, frontend/, dashboards/

## Constraints

- **Data:** NBA footage licensing is a grey area — pipeline must work on locally-owned/downloaded files; no dependency on official NBA API streaming
- **Compute:** Heavy training offloaded to cloud; local GPU used for inference and dev iteration
- **Token efficiency:** Pipelines modularized to minimize LLM token usage per operation
- **Architecture:** Each module must be independently testable with unit tests and self-checking scripts

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| YOLOv8 for detection | State-of-art object detection, good community support, Python-native | — Pending |
| DeepSORT for tracking | Proven multi-object tracker, integrates with YOLO detections | — Pending |
| PostgreSQL for storage | Relational structure fits game/player/event schema, supports analytics queries | — Pending |
| Streamlit + Plotly for dashboard | Fast iteration, Python-native, no frontend framework required | — Pending |
| FastAPI for endpoints | High-performance async Python API, natural pairing with ML stack | — Pending |
| Claude API for conversational interface | Native tool use for DB queries + model calls, structured output | — Pending |

---
*Last updated: 2026-03-09 after initialization*
