# CourtVision -- a converged 4-sport calibrated prediction platform

**One calibrated win-probability per sport (NBA / MLB / Soccer / Tennis) that anchors a
coherent pregame market surface and reprices it live as the game unfolds.**

The pregame model MATCHES the devigged closing line within sampling noise on team-strength
markets and trails on totals / ATP ONLY by freshness data the market sees and a public model
cannot. IN-GAME conditioning -- the pregame intelligence prior fused with the realized state --
is the decisive, measured, calibrated advantage, 4 sports out of 4. Every headline number is
leak-free / walk-forward / out-of-sample, reproducible from a fresh clone in under 60 seconds.
**No fabricated dollar edge -- ever.** The selling point is the rigor.

Built by **[Neel Shah](https://neelshahportfolio.netlify.app)** -- solo human architect and
director of an agentic build pipeline. Engineering judgment, ship/reject decisions, and
validation methodology are mine. Open to **ML / data / quant / founding-engineer** roles ->
[neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

## What it predicts

| Sport  | Pregame markets            | In-game checkpoint (conditional reprice) | Anchor                        |
|--------|----------------------------|------------------------------------------|-------------------------------|
| NBA    | moneyline, total (O/U)     | end of Q1 / Q2 / Q3                       | MOV-aware Elo win-prob        |
| MLB    | moneyline, total (O/U)     | after inning 3 / 5 / 7                    | walk-forward MOV-Elo          |
| Soccer | O/U-2.5 (in-game 1X2 too)  | half-time                                 | EW-Poisson + finishing + Platt|
| Tennis | ATP match-win              | after set 1                              | surface-Elo + Platt           |

One calibrated win-probability per sport is the anchor; the pregame surface and the in-game
repricer are coherent reads off that same anchor, not independent models. Every output is a
calibrated probability or point forecast (with dispersion) -- never a recommended wager.

---

## The thesis (calibration / sharpness -- NEVER a dollar edge)

### Pregame -- vs the devigged closing line, leak-free OOS (held-out 2nd half)

Lower Brier / RMSE is sharper. MATCH = within sampling noise of the sharp close. BEHIND = the
market's injury / lineup / weather / park / starting-pitcher freshness a public + box-score
model cannot see. Source: `vault/_Edge_Maps/_Beat_The_Close.md`.

| Sport / market    | Our model     | Close   | Verdict                          |
|-------------------|---------------|---------|----------------------------------|
| NBA moneyline     | Brier 0.1735  | 0.1672  | MATCH (within noise)             |
| NBA total O/U     | RMSE  19.17   | 18.11   | BEHIND (injury/lineup freshness) |
| MLB moneyline     | Brier 0.2429  | 0.2390  | MATCH (tiny pitcher-blindness)   |
| MLB total O/U     | RMSE  4.72    | 4.44    | BEHIND (park/weather/SP)         |
| Soccer O/U-2.5    | Brier 0.2465  | 0.2390  | MATCH (pooled Platt)             |
| Tennis ATP ml     | Brier 0.2177  | 0.2028  | BEHIND (ATP closes very tight)   |

### In-game -- conditioning on the realized state beats the static pregame line. All 4 WIN.

A live book also sees the state, so this is forecaster QUALITY, not a dollar edge.
Source: `vault/_Edge_Maps/_Ingame_Scoreboard.md`.

| Sport  | Static -> Conditional Brier             | When                                |
|--------|-----------------------------------------|-------------------------------------|
| NBA    | 0.209 -> 0.159                          | end Q1/Q2/Q3 (rating prior + score) |
| MLB    | 0.241 -> 0.126                          | after inning 3/5/7                  |
| Soccer | 1X2 0.626 -> 0.502; O/U 0.264 -> 0.176  | half-time                           |
| Tennis | 0.219 -> 0.151                          | after set 1 (leak-free leader)      |

**Reading it.** Pregame MATCHES the devigged close on team-strength win markets and is BEHIND
on totals / ATP only by freshness data the market sees and we cannot -- a data-bound gap, not a
model defect (a cleverer pregame model does not close it). The sharpest forecaster FUSES the
pregame intelligence prior with the realized state, not either alone. That in-game conditioning
is the decisive, measured, calibrated, delivered improvement, 4/4 sports. We never claim a
dollar edge, an ROI, or beating the close.

---

## Run it in minutes

Slim install -- the predictor needs only a small scientific-Python surface (numpy, pandas,
pyarrow, scipy, scikit-learn). The heavy CV / web / daemon dependencies are NOT required.

```bash
pip install -r requirements-predictor.txt      # or:  pip install -e .  -> cv-matchup / cv-predict / cv-live
```

### 1. One matchup -- pregame + in-game in a single JSON read

```bash
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

Real output:

```json
{
  "sport": "nba", "home": "BOS", "away": "LAL",
  "edge_claimed": false,
  "framing": "Pregame MATCHES the devigged close (calibration/sharpness, not an edge); in-game ADDS the realized state. No $ edge.",
  "pregame": { "p_home_win": 0.605, "total_mean": 211.3, "margin_home": 3.0 },
  "ingame":  { "p_home_win": 0.5732, "pregame_p_home": 0.605, "proj_total": 211.3, "proj_margin_home": 4.4 }
}
```

The `pregame` block is the cohesive read (one win-prob anchors a consistent moneyline / total /
margin surface). The `ingame` block reprices off the realized state. Swap `--sport` for `mlb`,
`soccer`, or `tennis` and pass the corresponding teams to run the other domains.

### 2. Reproduce the scoreboards on committed fixtures (proof in under 60s, fresh clone)

```bash
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard        --corpus tests/fixtures/proof
```

Both scoreboards print the per-sport verdict table directly. The `--corpus tests/fixtures/proof`
fixtures are a small committed demo slice (so the printed numbers are NOT the canonical headline
numbers -- those come from the full local corpora; see "Where the real numbers live"), and the
point is that the leak-free / walk-forward machinery runs end-to-end on a fresh clone with no
private data and no network. The scoreboards print "fixture/demo mode -- canonical report NOT
written" on the fixture path so the demo slice can never overwrite the canonical reports.

> No box-freezing full-suite pytest needed to verify the product. The predictor is validated by
> the per-module proof harnesses above (and per-file tests under `tests/`), not by a
> repo-wide `pytest tests/` run.

---

## Why trust it -- the rigor IS the product

- **Leak-free by construction.** Walk-forward / expanding-window evaluation with assertion-level
  per-fold leakage guards and truncation-invariance leak tests (a feature at time T is
  byte-identical with or without future events). Every headline number is OOS on a held-out
  window. The close is a comparison forecaster, never a model input.
- **Honest nulls are successes.** "BEHIND by freshness" and "MATCH within noise" are stated
  plainly. A full-season leak-free backtest proving the pregame market is efficient is reported
  as a headline result, not buried. Matching the sharp close within noise is the realistic best
  case for an efficient market -- beating it would imply information the close lacks.
- **We caught and retracted our own over-claims.** The same harnesses that grade the market were
  pointed inward and flagged a market-follow ROI artifact, a Q4 look-ahead leak in an in-play
  win-prob model, and an L5-proxy ceiling mislabeled as edge. Those numbers were retired in
  writing. Building the instrument that disproves your own hype is the strongest signal here.

**Honesty truth-source.** Every prediction number's provenance, and every retracted over-claim,
live in **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)** (cite this for any number;
it never restates a retracted figure as current). Open gaps:
**[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)**.

We never claim a dollar edge / ROI / profitable betting edge, beating the close, or a
computer-vision predictive moat (CV SHAP is ~0 in production today).

---

## Architecture -- one sport-blind kernel + per-sport adapters

Adding a sport is an adapter, not a kernel rewrite.

```
                          domains/<sport>/predictor.py
                          (one calibrated win-prob anchor per sport)
                                       |
              +------------------------+------------------------+
              |                                                 |
     PREGAME read (cohesive)                          IN-GAME read (live)
     predict() / to_jd()                              predict_live()
     scripts/platformkit/cohesive_read.py             scripts/platformkit/live_read.py
     -> moneyline / totals / margin                   -> repriced win-prob + proj
        (matches the devigged close)                     (conditions on realized state)
              |                                                 |
              +------------------------+------------------------+
                                       |
                       scripts/platformkit/predict_matchup.py
                       Unified CLI:  cv-matchup  (pregame + in-game in one read)
                                     cv-predict (cohesive_read)
                                     cv-live    (live_read)
```

- **`domains/<sport>/predictor.py`** -- the per-sport adapter: a single calibrated
  win-probability anchors `predict()` / `to_jd()` (pregame, the cohesive read) and
  `predict_live()` (in-game, the live read). Adapters exist for all four sports
  (`basketball_nba`, `mlb`, `soccer`, `tennis`).
- **`scripts/platformkit/cohesive_read.py`** (`cv-predict`) -- the coherent pregame surface off
  the anchor: moneyline, totals, margin.
- **`scripts/platformkit/live_read.py`** (`cv-live`) -- the in-game repricer that conditions the
  same prior on the realized state.
- **`scripts/platformkit/predict_matchup.py`** (`cv-matchup`) -- the unified CLI a buyer runs,
  with an explicit `"edge_claimed": false` and honest framing baked into every response.
- **~25 leak-free / OOS proof modules** under `scripts/platformkit/proof_*` reproduce every
  scorecard number; the two roll-up scoreboards regenerate the tables above.

---

## Buyer docs

| Document | What it covers |
|----------|----------------|
| [docs/PRODUCT_ONE_PAGER.md](docs/PRODUCT_ONE_PAGER.md) | The 60-second product pitch + scorecards |
| [docs/PREDICTOR_PLATFORM.md](docs/PREDICTOR_PLATFORM.md) | Full platform: thesis, scorecards, architecture, why it sells |
| [docs/PREDICTOR_QUICKSTART.md](docs/PREDICTOR_QUICKSTART.md) | Step-by-step run-in-minutes, real output |
| [docs/PROOFS.md](docs/PROOFS.md) | The provability index -- every claim -> the runnable leak-free proof that backs it |
| [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) | The single honesty truth-source -- every number + the do-not-claim list |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Open gaps and what is not yet demonstrated |
| [docs/PLATFORM.md](docs/PLATFORM.md) | Kernel + adapter multi-sport architecture direction |

---

## Origin / NBA computer-vision lineage (engineering history, not the product)

This platform grew out of **CourtVision**, an NBA broadcast-video computer-vision pipeline. That
is real, substantial engineering and it is where the validation machinery -- walk-forward CV,
leak guards, the multi-corpus calibration gate -- came from. It is **lineage, not the headline**:
the CV-derived features carry roughly zero measured predictive value in production today
(SHAP ~ 0), so the CV layer is NOT sold as an edge.

The CV pipeline converts a raw NBA broadcast feed into structured court-coordinate data at
**~$0.10-0.13 per full game** on a single consumer GPU:

```
Broadcast video
  -> YOLOv8n detection            players, ball, rim, referee, shoot/made events
  -> SIFT homography              image pixels -> 94 x 50 ft court coordinates
  -> Kalman + Hungarian tracking  6D constant-velocity motion + globally-optimal ID assignment
  -> OSNet re-ID (512-dim)        recover identities through occlusion / scene cuts
  -> EasyOCR                      jerseys, scoreboard clock + period + score
  -> EventDetector                shots, passes, dribbles, screens, drives, closeouts, rebounds
```

The tracking math is implemented from primitives (a 6D constant-velocity Kalman filter plus
Hungarian assignment over a blended IoU+appearance cost in
[`src/tracking/advanced_tracker.py`](src/tracking/advanced_tracker.py); OSNet re-ID
reimplemented in PyTorch; a broadcast-hardened SIFT homography with inlier gating, EMA
smoothing, drift re-anchoring, and replay/scene-cut suspension). It feeds a possession-level
Monte Carlo simulator whose teammate correlation emerges correct from the mechanics (a shared
scoring pie, measured rho ~ -0.10 vs realized) rather than a hand-tuned matrix, plus a FastAPI
serving layer. Full audited account of the CV pipeline as engineering evidence is in
[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section 2; CV internals in
[docs/CV_TRACKING.md](docs/CV_TRACKING.md).

---

## Tech stack

**ML / data:** Python 3.9, NumPy, pandas, pyarrow, scipy, scikit-learn (Isotonic + Platt + NNLS),
XGBoost, LightGBM. **Quant / validation:** walk-forward CV (season / era purged), Shin (1992)
devig, per-stat isotonic / temperature recalibration, multi-corpus calibration acceptance gate,
truncation-invariance leak tests. **CV lineage:** YOLOv8n (Ultralytics), OpenCV, SIFT homography,
OSNet re-ID, EasyOCR. **Serving:** FastAPI, uvicorn, SSE, parquet feature store.
**AI agents:** Claude Code -- Opus orchestrator + parallel Sonnet executors under hard ship gates.

---

## Contact

Solo-built (human-directed agentic pipeline). Available for senior ML / data / quant /
founding-engineer roles.

- **Start here:** [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) -- the honest, audited account
- **Portfolio:** [neelshahportfolio.netlify.app](https://neelshahportfolio.netlify.app)
- **Email:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

*All prediction numbers in this README are calibration / sharpness (Brier / RMSE / ECE), never a
dollar edge. The single honesty truth-source is
[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md); retracted / inflated numbers appear
only there and in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md), in explicit retraction
context, and never here.*
