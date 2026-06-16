# Project Index -- Navigation Hub

The product is a converged **4-sport (NBA / MLB / Soccer / Tennis) calibrated
prediction platform**: one win-probability per sport anchors a coherent pregame
surface plus an in-game repricer, behind one unified CLI. The selling point is
RIGOR (leak-free / walk-forward / OOS discipline, with self-caught retractions),
the measured IN-GAME conditioning edge, and honest CALIBRATION -- never a
fabricated dollar edge.

**Single honesty truth-source for every number:** [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).
Cite it; this repo does not restate retracted figures outside of it and
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## Start here -- the honest product

| Document | What it is |
|----------|------------|
| **[JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)** | **TRUTH-SOURCE.** Every claim's proof artifact, adversarially audited, plus the explicit do-not-claim / retraction list. Read this first. |
| **[PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md)** | The product, in full: the thesis, the two scorecards (beat-the-close + in-game), the kernel/adapter architecture, why the rigor is the sell. |
| **[PREDICTOR_QUICKSTART.md](PREDICTOR_QUICKSTART.md)** | Run a calibrated prediction in minutes: slim install, one matchup (pregame + in-game), reproduce the scoreboards on committed fixtures. |
| **[PRODUCT_ONE_PAGER.md](PRODUCT_ONE_PAGER.md)** | The one-page pitch: what it predicts, how good vs the market, why trust it, run-it-in-60-seconds. |
| **[PROOFS.md](PROOFS.md)** | The provability index: every prediction claim mapped to its runnable, leak-free / OOS proof module + the exact reproduce command. |
| **[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)** | Explicit validation gaps, unvalidated claims, and the retraction context. |

### Run commands a buyer uses

```
# slim install (predictor only; no CV / web / daemon stack)
pip install -r requirements-predictor.txt        # or: pip install -e .  -> cv-matchup / cv-predict / cv-live

# one matchup, pregame + in-game, unified CLI
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0

# reproduce the leak-free scoreboards on committed fixtures (proof in under 60s, fresh clone)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard         --corpus tests/fixtures/proof
```

All numbers these emit are calibration / sharpness (Brier / RMSE / ECE), never a
dollar edge. The canonical full-corpus numbers live in `vault/_Edge_Maps/_Beat_The_Close.md`
and `vault/_Edge_Maps/_Ingame_Scoreboard.md` (local, gitignored); the fixture
commands run the SAME code on a small committed slice.

---

## Architecture

One sport-blind kernel + per-sport adapters. Adding a sport is an adapter, not a
kernel rewrite.

| Document | Description |
|----------|-------------|
| [PLATFORM.md](PLATFORM.md) | The kernel/adapter split: `kernel/` (validated machinery) + `domains/<sport>/` adapters. |
| [PLATFORM_TOOLING.md](PLATFORM_TOOLING.md) | The platformkit CLI surface and proof-module tooling. |
| [architecture/system-overview.md](architecture/system-overview.md) | The core systems and how they interconnect. |
| [architecture/possession-simulator.md](architecture/possession-simulator.md) | Possession Monte Carlo engine design -- why distributions beat point estimates. |

| Path | Contents |
|------|----------|
| `domains/<sport>/predictor.py` | Per-sport adapter: one calibrated win-prob anchors `predict()` / `to_jd()` (pregame) and `predict_live()` (in-game). Adapters for `basketball_nba`, `mlb`, `soccer`, `tennis`. |
| `scripts/platformkit/cohesive_read.py` (`cv-predict`) | The coherent pregame surface off the anchor: moneyline, totals, margin. |
| `scripts/platformkit/live_read.py` (`cv-live`) | The in-game repricer: conditions the same prior on the realized state. |
| `scripts/platformkit/predict_matchup.py` (`cv-matchup`) | The unified CLI: pregame surface + in-game reprice in one JSON read, `edge_claimed: false` baked in. |
| `scripts/platformkit/proof_*` | ~25 leak-free / OOS proof modules (`proof_nba`, `proof_mlb`, `proof_soccer`, `proof_tennis`, shared `proof_common`) that regenerate every scorecard number. |
| `kernel/` | The sport-blind validated machinery shared by all adapters. |

---

## Methodology and validation (the rigor that is the sell)

| Document | Description |
|----------|-------------|
| [research/validation-methodology.md](research/validation-methodology.md) | CLV-over-ROI doctrine, null-hypothesis discipline, no K-fold on time series. |
| [quant-methodology.md](quant-methodology.md) | Walk-forward CV, leak guards, multi-corpus calibration acceptance gate. |
| [backtest-methodology.md](backtest-methodology.md) | Leak-free backtest construction and the market-efficiency findings. |
| [models/calibration.md](models/calibration.md) | Probability calibration -- Platt / isotonic / temperature, ECE, Shin devig. |
| [risk-framework.md](risk-framework.md) | Decision-layer guardrails (kill-switch, drawdown) as an engineering demonstration. |

---

## Demo and contribution

| Document | Description |
|----------|-------------|
| [DEMO.md](DEMO.md) | Deterministic walkthrough: environment, prediction CLIs, FastAPI app, CV pipeline. |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Setup, branch/PR workflow, the ML/prediction ship-gate, repo hygiene. |
| [../README.md](../README.md) | GitHub entry point -- funnel narrative with honest numbers. |
| [../CLAUDE.md](../CLAUDE.md) | AI-agent runbook (truth-source routing). |

---

## Origin / NBA computer-vision lineage (engineering history, not the product)

The platform grew out of **CourtVision**, an NBA broadcast-video computer-vision
pipeline. This is real, substantial engineering and the origin of the validation
machinery -- but it is **lineage, not the headline**. The CV-derived features
carry ~0 measured predictive value in production today (SHAP ~0); there is NO CV
moat / edge claim. The product is the converged 4-sport predictor above. These
docs document the CV pipeline as engineering evidence:

| Document | Description |
|----------|-------------|
| [CV_TRACKING.md](CV_TRACKING.md) | The CV pipeline: YOLOv8n -> SIFT homography -> Kalman + Hungarian -> OSNet re-ID. |
| [architecture/cv-pipeline.md](architecture/cv-pipeline.md) | Full CV layer design. |
| [ML_MODELS.md](ML_MODELS.md) | The NBA prop / win-prob model stack. |
| [INTELLIGENCE.md](INTELLIGENCE.md) | The 80-artifact NBA intelligence-layer manifest. |
| [PLAYER_INTELLIGENCE.md](PLAYER_INTELLIGENCE.md) | Per-player statistical dossiers (showcase + honest scope). |
| [DATA.md](DATA.md) | Data sources and ingest pipeline. |
| [API.md](API.md) | FastAPI reference. |
| [BETTING.md](BETTING.md) | Decision-layer engineering (de-vig, Kelly, CLV) -- an engineering demonstration, not a claimed edge. |

---

## Source code map

| Path | Contents |
|------|----------|
| `domains/` | Per-sport predictor adapters (the product). |
| `scripts/platformkit/` | Unified CLI + proof modules. |
| `kernel/` | Sport-blind validated machinery. |
| `src/tracking/` | CV: YOLOv8 detection, re-ID (OSNet, color), homography, Kalman/Hungarian. |
| `src/features/` | Feature engineering -- CV spatial + API-derived features. |
| `src/prediction/` | NBA prop / win-prob models, calibration, devig, backtester (large research surface; small load-bearing graph). |
| `src/sim/` | Possession Monte Carlo simulator. |
| `src/loop/` | LLM-free signal-discovery loop + the honest ship gate. |
| `api/` | FastAPI serving layer (NBA lineage demonstration). |
| `tests/` | Per-file test suite; `tests/fixtures/proof/` holds the committed proof fixtures. |

---

*Numbers are calibration / sharpness only, never a dollar edge. The single honesty
truth-source is [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).*
