# 🏀 Project CourtVision: The Autonomous NBA Intelligence Engine
> **A fully automated AI-driven ecosystem transforming raw tracking data and game footage into proprietary, predictive basketball metrics.**

![Python](https://img.shields.io/badge/Language-Python_3.10-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Computer Vision](https://img.shields.io/badge/AI-Computer_Vision-red?style=for-the-badge&logo=opencv)
![LLM](https://img.shields.io/badge/NLP-GenAI_/_RAG-00A67E?style=for-the-badge&logo=openai)
![Status](https://img.shields.io/badge/Status-Work_In_Progress-orange?style=for-the-badge)

---

## 🏗️ Project Vision
Most NBA analytics are **descriptive** (what happened). CourtVision is built to be **predictive** (what will happen). This system is a self-correcting intelligence engine that pulls raw data, watches game footage via Computer Vision, and engineers proprietary metrics like **Fatigue-Adjusted Performance** and **Real Shot Quality**.

The end goal: A fully autonomous system that rivals million-dollar NBA front-office tools, updating overnight to provide a complete analytical picture every morning.

---

## 🛠️ The System Architecture (The "Triple-Threat" AI)

### 1. The Pattern Finder (Predictive ML) 🧠
*   **Goal:** Train models on high-volume historical and tracking data to predict game outcomes and point-spread movements.
*   **Status:** `[||||------] 40% Complete`
*   **Tech:** XGBoost, LSTMs for time-series momentum, and Bayesian Optimization.

### 2. The Digital Eye (Computer Vision) 👁️
*   **Goal:** Extract player positioning, velocity, and spacing metrics directly from broadcast footage where raw tracking data is unavailable.
*   **Status:** `[|||-------] 30% Complete`
*   **Tech:** OpenCV, MediaPipe for pose estimation, and YOLOv8 for object detection.

### 3. The Analyst Voice (Generative AI Layer) 💬
*   **Goal:** A natural language interface (RAG) that allows users to query the database in plain English (e.g., *"Show me Curry's efficiency drop-off in the 4th quarter when guarded by a 6'5" wing"*).
*   **Status:** `[|||||-----] 50% Complete`
*   **Tech:** LangChain, OpenAI GPT-4o, Vector Databases (ChromaDB).

---

## 📊 Proprietary Metrics Under Construction
We aren't just using Box Scores. We are engineering the "Secret Sauce":
*   **Real Shot Quality (RSQ):** Modeling expected value based on defender proximity, shooter fatigue, and spatial history.
*   **True Defensive Impact (TDI):** Measuring the "Gravity" a defender exerts on offensive flow, even without recording a stat.
*   **Fatigue-Adjusted Performance (FAP):** Quantifying the decay of shooting mechanics based on distance traveled and speed-burst frequency.
*   **Momentum Response:** A volatility index measuring a team's statistical resilience during opposing scoring runs


```
Video Input
    │
    ▼
┌─────────────────────────────────┐
│  Computer Vision Pipeline       │
│  YOLOv8 detection (batched)     │
│  DeepSORT multi-object tracking │
│  Court homography calibration   │
│  Ball Kalman filter             │
└────────────┬────────────────────┘
             │ tracking_coordinates (PostgreSQL)
             ▼
┌─────────────────────────────────┐
│  Feature Pipeline (14 steps)    │
│  Spacing · Defensive Pressure   │
│  Pick-and-Roll · Passing Net    │
│  Momentum · Drive Analysis      │
│  Play Recognition · Game Flow   │
│  + 6 more modules               │
└────────────┬────────────────────┘
             │ feature_vectors, detected_events, etc.
             ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│  FastAPI     │  │  Streamlit   │  │  Flask           │
│  REST API    │  │  Dashboard   │  │  Game Browser    │
│  /docs       │  │  port 8501   │  │  port 5001       │
└──────────────┘  └──────────────┘  └──────────────────┘
```

---

## Project Structure

```
nba-ai-system/
├── tracking/               # Core tracking system
│   ├── tracker.py          # ObjectTracker (DeepSORT wrapper, team assignment)
│   ├── homography.py       # Pixel → court-feet coordinate mapping
│   ├── ball_kalman.py      # Kalman filter for ball occlusion handling
│   ├── coordinate_writer.py# Buffered bulk-insert to PostgreSQL
│   ├── database.py         # DB connection factory
│   └── schema.sql          # Database schema
│
├── pipelines/              # CV ingestion pipeline
│   ├── run_pipeline.py     # Main orchestrator (batched GPU inference)
│   ├── detector.py         # YOLOv8 object detection wrapper
│   ├── video_ingestor.py   # Frame reader with resume support
│   └── court_detector.py  # Court line/corner detection
│
├── features/               # Analytics feature modules (pure computation)
│   ├── spacing.py          # Convex hull area, inter-player distance
│   ├── defensive_pressure.py # Nearest defender distance, closing speed
│   ├── pick_and_roll.py    # PnR detection via speed + proximity thresholds
│   ├── off_ball_events.py  # Cut / screen / drift classification
│   ├── passing_network.py  # Directed pass graph per possession
│   ├── momentum.py         # Scoring runs, possession streaks, swing points
│   ├── drive_analysis.py   # Drive mechanics and penetration depth
│   ├── shot_creation.py    # Shot type classification
│   ├── space_control.py    # Radial influence model, lane openness
│   ├── play_recognition.py # 12+ play-type classifier
│   ├── defensive_scheme.py # Man / zone / hybrid scheme detection
│   ├── game_flow.py        # Momentum index, comeback probability
│   ├── micro_timing.py     # Decision latency, catch-to-action times
│   ├── lineup_synergy.py   # Spacing quality, cohesion, gravity scores
│   └── feature_pipeline.py # 14-step orchestrator with DB I/O
│
├── models/                 # ML models
│   ├── win_probability.py  # Game-state win probability model
│   ├── player_impact.py    # Expected Points Added (EPA) per 100 possessions
│   ├── lineup_optimizer.py # Lineup synergy optimization
│   ├── momentum_detector.py# Momentum shift detection
│   └── shot_probability.py # Shot quality estimator
│
├── pipeline/               # Post-processing
│   ├── export_data.py      # Export tracking data for visualizations
│   ├── generate_graphs.py  # Render analytics charts (PNG)
│   └── run_all.py          # End-to-end post-processing runner
│
├── api/                    # FastAPI REST layer
│   ├── main.py             # App entrypoint, CORS, startup
│   ├── analytics_router.py # /analytics/* endpoints
│   └── models_router.py    # /models/* endpoints
│
├── analytics/              # Conversational AI
│   └── chat.py             # Claude-powered game analysis chat
│
├── dashboards/             # Streamlit dashboard
│   ├── app.py              # Main dashboard app
│   └── charts.py           # Chart rendering utilities
│
├── frontend/               # Flask game browser UI
│   ├── app.py              # Routes (game list, dashboard, graph serving)
│   └── templates/          # Jinja2 HTML templates
│
├── tests/                  # Full test suite (301 tests)
│   ├── test_accuracy_validation.py    # NBA ground-truth accuracy tests
│   ├── test_tracker.py                # ObjectTracker unit tests
│   ├── test_coordinate_writer_and_pipeline.py
│   ├── test_court_detector.py
│   ├── test_spacing.py
│   ├── test_defensive_pressure.py
│   ├── test_off_ball_events.py
│   ├── test_pick_and_roll.py
│   ├── test_passing_network.py
│   ├── test_momentum.py
│   └── ...                            # 18 test files total
│
├── .env.example            # Environment variable template
├── requirements.txt        # Python dependencies
└── start.sh                # One-command startup script
```

---

## Quickstart

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- CUDA-capable GPU (recommended for real-time inference)

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/nba-ai-system.git
cd nba-ai-system
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL and ANTHROPIC_API_KEY
```

### 3. Initialize the database

```bash
psql $DATABASE_URL -f tracking/schema.sql
```

### 4. Launch

```bash
./start.sh
```

| Service | URL |
|---------|-----|
| Streamlit Dashboard | http://localhost:8501 |
| REST API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Flask Game Browser | http://localhost:5001 |

---

## Running the Tracking Pipeline

Process a video file end-to-end:

```bash
python -m pipelines.run_pipeline \
    --video path/to/game.mp4 \
    --game-id YOUR_GAME_UUID \
    --weights yolov8x.pt \
    --skip 1
```

The pipeline is **resumable** — if interrupted, it picks up from the last processed frame.

After tracking completes, run the feature pipeline:

```bash
python -m features.feature_pipeline --game-id YOUR_GAME_UUID
```

---

## Running Tests

```bash
pytest tests/ -v
```

The test suite includes **NBA ground-truth accuracy validation** that verifies:
- All computed stats fall within published NBA tracking benchmarks
- Physical constraints (speeds ≤ 32.3 ft/s, positions within court bounds)
- Detection thresholds are calibrated in court-feet units (not pixel units)
- Cross-module consistency between spacing, momentum, and event detection

```
301 passed in ~10s
```

---

## Key Technical Details

### Coordinate System

All tracking data is stored in **court feet** (0–94 ft × 0–50 ft), converted from broadcast pixels via homography calibration. Speeds are in **ft/s**. This enables cross-game and cross-camera comparison.

### Tracking Pipeline

| Stage | Technology | Notes |
|-------|-----------|-------|
| Object detection | YOLOv8x | Batched (8 frames/pass), GPU |
| Multi-object tracking | DeepSORT | Re-ID embeddings per track |
| Court mapping | Homography | Calibrated from court line detection |
| Ball smoothing | Kalman filter | Handles occlusion up to 15 frames |
| Team assignment | K-means (HSV) | Re-clusters every 45 frames |
| Scene cut detection | Frame diff | Recalibrates homography on camera switch |

### Feature Detection Thresholds (NBA-calibrated)

All thresholds are calibrated to real NBA player movement in **court-feet units**:

| Event | Threshold | NBA Reference |
|-------|-----------|--------------|
| Hard cut | speed > 14 ft/s | ~9.5 mph, SecondSpectrum |
| Screen (stationary) | speed < 3 ft/s | Screener nearly stationary |
| Screen contact | distance < 6 ft | Body-contact range |
| Ball handler (PnR) | speed > 8 ft/s | Handler accelerating off screen |
| Drift (off-ball) | 4–10 ft/s | Light jog, lateral movement |

---

## API Reference

The FastAPI layer exposes:

- `GET /analytics/{game_id}/spacing` — Per-frame spacing metrics
- `GET /analytics/{game_id}/momentum` — Momentum snapshots
- `GET /analytics/{game_id}/passing-network` — Passing graph
- `GET /models/{game_id}/win-probability` — Win probability curve
- `GET /models/{game_id}/player-impact` — EPA per 100 possessions
- `POST /models/{game_id}/lineup` — Lineup optimization

Full interactive docs: `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `ANTHROPIC_API_KEY` | Claude API key for conversational analytics |
| `VIDEO_INPUT_DIR` | Directory for input video files |
| `MODEL_WEIGHTS_DIR` | Directory for YOLO weight files |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Object detection | YOLOv8 (Ultralytics) |
| Multi-object tracking | DeepSORT |
| Computer vision | OpenCV |
| Deep learning | PyTorch |
| Database | PostgreSQL |
| REST API | FastAPI + Uvicorn |
| Dashboard | Streamlit |
| Game browser | Flask |
| Conversational AI | Anthropic Claude |
| Graph analytics | NetworkX |
| ML / Stats | scikit-learn, scipy, pandas |
| Testing | pytest (301 tests) |

---

## License

MIT
