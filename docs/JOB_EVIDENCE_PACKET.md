# Job Evidence Packet — Neel Shah

> The honest 60-second read for a recruiter, hiring manager, or engineer evaluating me. What's real, what I
> retracted, and why. If you only read one doc in this repo, read this one.

**One line:** Self-taught engineer (no CS degree) who solo-built a production-grade computer-vision → ML → systems
platform over 13 months — and, more importantly, built the validation discipline that catches its own mistakes.

**The 3-sentence version:** I built CourtVision end-to-end alone: a CV pipeline that turns broadcast NBA video into
court coordinates and behavioral features, the ML models on top, and the full serving/data/ops stack around them
(~6,000 files, FastAPI, daemons, PostgreSQL, CI). The rarest thing in here isn't a metric — it's that my own
walk-forward validation harness keeps catching my own overclaims, and I document and retract them instead of
shipping them (see "What I retracted" below). I'm looking for ML / computer-vision / data / founding-engineer roles
where building *and* rigorously validating both matter.

---

## 1. Defensible evidence (verifiable — this is the pitch)

### Computer vision in production (not a notebook)
- Broadcast video → court coordinates → per-frame behavioral features via a real pipeline: **YOLOv8 detection →
  SIFT/homography court rectification → Kalman + Hungarian multi-object tracking → OSNet re-ID (512-dim) →
  scoreboard/jersey OCR → event detection**. Code: `src/tracking/`, `src/pipeline/unified_pipeline.py`.
- Runs on a **consumer GPU at ~$0.10–0.13/game** — the cost contrast vs. six-figure licensed tracking
  (Sportradar / Second Spectrum) is the architectural point.
- *Honest scope:* the pipeline is built and runs; full multi-game feature extraction is partial (a handful of games
  fully processed, scale-up in progress). I state this openly rather than imply "80 games done."

### System architecture & breadth (one person, one git history)
- ~6,000 tracked files: CV tracker, prop models, in-play stack, **FastAPI (~49 endpoints across 7 routers)**,
  background daemons, multi-book line scraper, arbitrage detector, parlay builder, P&L ledger, live dashboard,
  Discord/Slack alerting, **PostgreSQL schema + migrations**, CI.
- Verify: `git log` (active, iterative history), the router/endpoint count in `api/`, `tests/` (a real test suite).

### ML & validation methodology (my strongest differentiator)
- **Walk-forward / point-in-time** evaluation (train on past, predict forward), not random splits.
- **Leak detection** baked into the process — I find and fix as-of/look-ahead violations (and have caught several).
- **Shadow-logging + settlement**: every signal is logged live without affecting served predictions, then settled
  against real outcomes — so model quality is measured the way it would actually be used.
- **Per-stat calibration** (isotonic / out-of-fold) with a non-obvious finding: calibration *helps* the stats the
  model loses to the market and *hurts* the one it beats — so it's applied selectively and graded on ROI-vs-market,
  not MAE.
- **Agentic discovery loop** (orchestration of LLM agents to propose → validate → ship/reject signals) behind hard
  ship gates (orthogonality, ≥2 independent corpora, cross-season replication). The gates exist specifically to
  defeat multiple-comparisons false positives and data leakage — and they work.

### Full-stack / data engineering
- Scrapers → PostgreSQL → feature store → daemons → FastAPI serving → live UI; reproducible pipelines; env-gated,
  default-off feature flags so changes ship safely and reversibly.

---

## 2. Honest numbers (what survives scrutiny)

The model is **competitive but not magic**, and the betting market is **efficient on closing lines** — which is
itself a sophisticated, correct finding, not a failure. Specifically:
- The prop models' point accuracy (MAE) is solid and reproducible (`scripts/verify_production_mae.py` checks it
  against committed JSON).
- The model is roughly break-even-to-slightly-negative vs. real closing lines on most stats (the market prices what
  the model knows). One stat (assists) shows a small genuine edge; I don't over-extrapolate from it.
- The CV cost/architecture claim (~$0.10/game on consumer hardware) is the most defensible "moat" claim.

**Grade me on the methodology and the engineering, not a headline ROI** — that's deliberate, and it's the honest read.

## 3. What I retracted (this is a feature, not a bug)

My own validation process caught these in my own work, and I corrected them in the repo rather than bury them:
- **"+18.38% pre-game ROI"** → a **market-follow grading artifact** (the grader was effectively following the
  market's favorite, not the model; at real odds it's ≈ **−2% to −5%**). Retracted.
- **"endQ3 Brier 0.119"** → **leak-inflated** by fourth-quarter-derived features fed into an end-of-Q3 model
  (it peeked at the future). Retracted pending a leak-free re-measure.
- **"+54% in-play ROI"** → measured against an **L5 line proxy**, not real in-play lines. Not a deployment number.

If you're a sharp interviewer: please probe these. The point is that *I* found them, with tooling I built, before
anyone else did. That's the judgment I'd bring to your team.

## 4. Do-not-quote list (so we're aligned)
Do not treat `+18.38%`, `endQ3 Brier 0.119`, or `+54% in-play ROI` as live claims — they're retracted/caveated above.
Older copies of the README/CHANGELOG may still show them; this packet supersedes them.

## 5. 30-second reproducibility
```bash
git clone … && pip install -r requirements.txt
python scripts/verify_production_mae.py   # prop-model MAE vs committed JSON
python -m pytest tests/ -q                # the test suite
```
Reproducibility from committed data is the credibility signal — not a number in a deck.

## 6. Honest gaps (stated up front)
- No CS degree — the git history is the transcript.
- Solo project — no team yet; I'm explicitly looking to work *with* engineers now.
- CV feature scale-up is incomplete; some intelligence-layer artifacts are descriptive (and I found one with an
  attribution bug, now flagged).
- The domain is sports betting; the **transferable product is the CV + ML-validation + systems skill**, not the
  betting returns.

**Contact:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) · Repo: github.com/neeljshah/court-vision
