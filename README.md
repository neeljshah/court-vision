# CourtVision — NBA Broadcast Tracking → ML → Serving

**A computer-vision system that turns ordinary NBA broadcast video into structured, court-coordinate data on every player, the ball, and every possession** — then a prediction + serving stack built on top. Runs end-to-end on a single consumer GPU (~$0.10–0.13 per full game).

**Built by [Neel Shah](https://neelshahportfolio.netlify.app)** — self-taught, solo (intensive ~3-month build, Mar–May 2026), architected and directed via an agentic build pipeline I designed. Open to **ML / computer-vision / data / founding-engineer** roles. → [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

> 📄 **Start here: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** — an independently-audited account of what's real, what I retracted, and why. Every metric in this README is verifiable from committed code, data, or the packet. Where a famous number didn't survive scrutiny, it's listed as retracted — not quietly dropped.

---

## 1. The tracker — broadcast video → structured court data *(the primary artifact)*

You give it a broadcast clip; it returns per-frame, court-coordinate data. **Verified output** (counts measured directly from the data on disk):

| Product | Granularity | Verified |
|---|---|---|
| **`tracking_data.csv`** | per frame × player | **68 columns** — court coords (px + normalized + feet), velocity/accel/heading, bbox, ball position + velocity, possession flag, distance-to-ball, nearest opponent/teammate, team spacing + convex-hull + centroid, paint counts, court zone, drive/fast-break flags, dribble hand/count, contest-arm angle, jump flag, shot-clock estimate, possession ID + duration, play type, homography-valid, confidence |
| **`possessions.csv`** | per possession | **16 columns** — team, start/end, duration, spacing, drive count, shot attempt, play type, lineup |
| **`ball_tracking.csv`** | per frame | ball court x/y, detected/live/inferred flags |
| `shot_log.csv`, `events_log.csv`, `scoreboard_log.csv` | per shot / event / OCR read | produced when the shot-detection weights + OCR are enabled (present on a subset of games) |

**Scale (verified from `data/nba_ai.db`):** **241 games** processed into the feature store → **17,254 `cv_features` rows** across **252 resolved NBA player identities**. Tracking output also persists to SQLite (or PostgreSQL via `DATABASE_URL`); NBA-Stats enrichment joins official play-by-play to label real player IDs and makes/misses.

### How it works
```
Broadcast video
 → YOLOv8n detection (players, ball, rim)
 → SIFT homography           (image pixels → 94 × 50 ft court coordinates)
 → Kalman + Hungarian tracking (motion model + globally-optimal frame-to-frame ID assignment)
 → OSNet re-ID               (appearance embedding; HSV-histogram backstop)
 → EasyOCR                   (jerseys + scoreboard) + event detection (drives, passes, screens…)
 → per-frame writer (CSV / SQLite / Postgres) → NBA-API enrichment (real IDs, PBP labels)
```

| Layer | Module |
|---|---|
| Detection (YOLOv8n) | [`src/tracking/player_detection.py`](src/tracking/player_detection.py) |
| Court homography (SIFT) | [`src/pipeline/unified_pipeline.py`](src/pipeline/unified_pipeline.py) |
| Tracker (Kalman + Hungarian, from primitives) | [`src/tracking/advanced_tracker.py`](src/tracking/advanced_tracker.py) |
| Re-ID (OSNet, reimplemented) | [`src/tracking/osnet_reid.py`](src/tracking/osnet_reid.py) |
| Player resolver (jersey OCR + PBP priority + roster validation) | [`src/tracking/player_resolver.py`](src/tracking/player_resolver.py) |
| Events / scoreboard | [`src/tracking/event_detector.py`](src/tracking/event_detector.py), [`scoreboard_ocr.py`](src/tracking/scoreboard_ocr.py) |

### Honest tracking-quality note *(no flags — this is the real state)*
The pipeline runs end-to-end on a consumer RTX 4060 and produces the columns above. What is **not** yet validated, stated plainly: multi-object-tracking accuracy and homography error are **not benchmarked against labeled ground truth** (no MOTA/IDF1 yet), tracking quality varies on broadcast footage (it loses or duplicates players on hard sequences), and the **higher-order derived metrics** (possession segmentation, spacing units, defender distance) need ground-truth validation before they're trustworthy. Consistent with that, the CV-derived features currently carry **~0 SHAP importance** in the prediction models — they're complete plumbing and a credible thesis, **not yet a demonstrated predictive edge.** Validating these against MOT17/SportsMOT-style ground truth is the clearly-scoped next phase. (OSNet ships ImageNet-pretrained; the production appearance signal is HSV histograms — see the packet.)

---

## 2. Prediction layer + the honest edge

**Per-stat point accuracy — leak-free walk-forward OOF** (n = 50,954 held-out player-games/stat; computed from `data/cache/pregame_oof.parquet`):

| Stat | MAE | | Stat | MAE |
|---|--:|---|---|--:|
| PTS | **4.58** | | STL | **0.71** |
| REB | **1.90** | | BLK | **0.52** |
| AST | **1.34** | | TOV | **0.88** |
| FG3M | **0.88** | | *(bias: model under-predicts ~0.45 PTS)* | |

**The edge — stated precisely, with bounds (verified this session at real posted odds):**
- Against real DK/FanDuel/MGM **closing** lines, the prop book is **roughly break-even-minus-vig** overall — the closing market is efficient. Calibrating a stat moves it *toward* the line, so "calibrate everything" converges to break-even, not a universal edge.
- The **one durable, verified edge is assists (AST): +7.2% ROI** on 863 graded bets at real odds; it **replicates on an independently-sourced book** (+17.0% on the gated subset, same window), and **persists cross-season** at a smaller, honest **~+5%** (61% win rate vs the 52.4% break-even). It is genuine *selection skill* (positive in both over/under directions, beats a blind baseline) and **honestly bounded: it breaks in the playoffs.**
- **In-game, the model has real accuracy a pregame model can't reach:** graded against real in-play lines, its rest-of-game projection is **closer to the final box than the live market line ~66% of the time on assists, ~64% on FG3M** (cadence-independent), with a ~26% MAE reduction over a naive in-game carry-forward baseline. I treat this as **model accuracy, not proven betting ROI** (the live-line corpus is still small).

> **Retracted (caught by my own harness, documented openly):** a "+18.38% pre-game ROI" (a market-follow grading artifact — the grader bet the market's favorite at a fictional flat −110; real ≈ −2% to −5%), an "endQ3 Brier 0.119 / Pinnacle-class" (a fourth-quarter data leak; leak-free ≈ 0.141), and a "+54% in-play ROI" (an L5 line-proxy ceiling, not real closes). Details + the exact code that produced each illusion: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).

---

## 3. Validation methodology *(the real differentiator)*
- **Walk-forward CV** with an assertion-level per-fold leak guard (`max(train_date) < min(test_date)` every fold) + a CI gate that fails the build on overfitting.
- **Truncation-invariance** property tests for streaming features (a feature at time T is byte-identical with or without future events).
- A **multi-corpus calibration gate** (ships a change only if it beats baseline on ≥2 independent out-of-sample corpora).
- **Shadow-logging** of every evaluated bet (passed *and* blocked) + a settlement engine — a counterfactual dataset, not guesswork.
- These harnesses caught my own **+18% ROI** (artifact), a **Q4 leak**, and a **0.79-CV-vs-0.06-holdout** overfit — each documented as a negative result. **Telling a real result from an artifact is the deliverable.**

---

## 4. System & engineering breadth
- **FastAPI serving layer of ~99 endpoints across 12 routers** (REST + WebSocket + SSE), counted at runtime — props, live win-prob, devig/EV, CLV, risk/kill-switch, multi-book line scan.
- **9 long-running daemons** + a watchdog supervisor; a transactional P&L ledger (file locking, atomic writes); Slack/Discord alerting (rate limiting + circuit breakers).
- **Dual-backend persistence** — PostgreSQL-first with a transparent SQLite fallback that auto-translates SQL + idempotent migrations.
- **Shin (1992)** de-vig from scratch (stable bisection) + 3 other methods; fractional-Kelly sizing (correlation penalty, drawdown breaker).
- A **291,625-row** player-vs-player matchup database from 2,214 raw tracking files across 3 seasons; an idempotent single-writer fold into a 690-node knowledge graph.
- **CI/CD** on GitHub Actions; **5** Docker images; a large pytest suite (~7,400 tests, ~97–98% passing; betting-math + in-play cores pass clean — see KNOWN_LIMITATIONS).
- **Build method (disclosed):** the majority of commits are agent-authored — I designed and directed the multi-agent pipeline (planner orchestrating executors under hard ship gates); the architecture, ship/reject decisions, and validation methodology are mine.

---

## Reproduce / explore
```bash
git clone … && pip install -r requirements.txt
python scripts/run_gate1_full_analysis.py     # model vs real closing lines, per stat, real odds
python -m pytest tests/ -q                     # the test suite (betting-math + in-play cores pass clean)
```
*Honest note: some verify scripts have a fresh-clone gap (a feature-count mismatch; training data is gitignored) — treat the repo as a self-auditing harness; closing the fresh-clone reproducibility gap is known work.*

| Want… | Read |
|---|---|
| The audited evidence (what's real / retracted / why) | **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** |
| Known limitations + validation gaps | [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) |
| The intelligence layer (manifest) | [docs/INTELLIGENCE.md](docs/INTELLIGENCE.md) |
| Contact | [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) |
