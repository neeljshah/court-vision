# The Predictor Platform - a converged 4-sport calibrated forecaster

> **What this is:** one converged, leak-free CALIBRATED prediction platform across
> **NBA, MLB, Soccer, and Tennis**. For each sport a single win-probability anchors a
> coherent pregame surface (moneyline, totals, derived markets) and an in-game repricer
> that conditions on the realized game state. The selling point is **rigor** (leak-free /
> walk-forward / OOS discipline, with self-caught retractions) plus the measured **in-game
> conditioning edge** and honest **calibration** - never a fabricated dollar edge.
>
> **Honesty truth-source:** every number's provenance and every retracted over-claim live in
> [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md). This doc cites it; it does not restate
> retracted numbers. Open gaps: [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## 1. The thesis (read this first)

Three honest claims, all calibration/sharpness, never a dollar edge:

1. **Pregame MATCHES the devigged closing line** on team-strength win markets (NBA & MLB
   moneyline) - within sampling noise. The market is efficient; matching the best available
   predictor (the devigged close) with our OWN data is the achievable, honest win.
2. **Pregame is BEHIND ONLY on totals / derived markets** (NBA totals, MLB totals, ATP
   match-win) and only by the **freshness data we cannot see** - injuries, lineups, weather,
   park, starting pitcher - that the market prices and a public/box model cannot. The gap is
   data-bound, not model-bound: a cleverer pregame model does not close it.
3. **In-game conditioning is the decisive, measured, calibrated, delivered edge - 4/4 sports.**
   Conditioning the same pregame intelligence prior on the realized mid-game state is sharper
   than the static pregame line in every sport. (A live book also sees the state, so this is
   forecaster QUALITY, not a tradeable dollar edge - we never claim one.)

**We never claim:** a dollar edge / ROI / profitable betting edge; beating the close; a
computer-vision predictive moat (CV SHAP is ~0 in production today). Honest framings we DO
use: "matches the devigged close within noise", "calibrated", "the in-game conditioning edge",
"leak-free / walk-forward / OOS", and "we caught and retracted our own over-claims" - the rigor
is the sell.

---

## 2. What each sport predicts

| Sport | Pregame markets | In-game checkpoint(s) | Anchor |
|---|---|---|---|
| **NBA** | moneyline (win prob), total (O/U), home margin | end of Q1 / Q2 / Q3 | MOV-aware Elo win-prob |
| **MLB** | moneyline (win prob), total (O/U) | after inning 3 / 5 / 7 | walk-forward MOV-Elo |
| **Soccer** | O/U-2.5 goals (+ 1X2 in-game) | half-time | EW-Poisson + finishing + pooled Platt |
| **Tennis (ATP)** | match-win | after set 1 | surface-Elo + Platt |

One calibrated win-probability per sport is the anchor; the pregame surface and the in-game
repricer are coherent reads off that same anchor, not independent models.

---

## 3. Scorecard - BEAT-THE-CLOSE (pregame quality vs the market)

Our model vs the **devigged closing line** on the SAME real outcomes, leak-free OOS on a
held-out second half. Lower Brier / RMSE = sharper. MATCH = within sampling noise; BEHIND =
the market's freshness (injury/lineup/weather/park/SP) edge a public model cannot see.
Calibration/accuracy only - NOT a dollar edge.
Source: `vault/_Edge_Maps/_Beat_The_Close.md`.

| Sport | Market | Metric | Our model | Close | Verdict | Why |
|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 0.1735 | 0.1672 | **MATCH** | MOV-aware Elo; within sampling noise of the close |
| NBA | total (O/U) | RMSE | 19.17 | 18.11 | BEHIND | possessions/efficiency model; gap = injuries/lineups (freshness) |
| MLB | moneyline | Brier | 0.2429 | 0.2390 | **MATCH** | walk-forward MOV-Elo; tiny deficit = pitcher-blindness (close prices SP) |
| MLB | total (O/U) | RMSE | 4.72 | 4.44 | BEHIND | run-rate expected total; gap = park/weather/SP/lineup (freshness) |
| Soccer | O/U-2.5 | Brier | 0.2465 | 0.2390 | **MATCH** | EW-Poisson + finishing + pooled Platt vs devigged Pinnacle close |
| Tennis (ATP) | match-win | Brier | 0.2177 | 0.2028 | BEHIND | surface-Elo + Platt; ATP closes very efficient |

**Reading it:** on team-strength win markets (NBA & MLB moneyline) we MATCH the devigged close
within noise. On totals / derived markets we trail ONLY by the freshness edge the market sees
and we cannot. Soccer O/U sits in the MATCH band (pooled Platt). Closing the remaining gaps
needs the data the market has (a freshness feed, forward) or in-game conditioning - not a
cleverer pregame model.

---

## 4. Scorecard - IN-GAME (conditional on realized state vs the static pregame line)

Conditioning on the **realized mid-game state** vs the **static pregame** predictor, on the
SAME real outcomes. Lower Brier = sharper. WIN = the conditional forecaster is sharper - the
sharpest forecaster fuses the pregame intelligence (ratings) AS THE PRIOR with the realized
state, not either alone. Forecaster quality, NOT a dollar edge (a live book sees the state too).
Source: `vault/_Edge_Maps/_Ingame_Scoreboard.md`. **All 4 sports WIN.**

| Sport | Checkpoint | Metric | Conditional | Static | Verdict | Why |
|---|---|---|---|---|---|---|
| NBA | end Q1/Q2/Q3 | Brier | **0.159** | 0.209 | WIN | combined (Elo prior + realized score) beats prior-only and score-only |
| MLB | after inning 3/5/7 | Brier | **0.126** | 0.241 | WIN | combined (MOV-Elo prior + realized runs) beats both alone |
| Soccer | half-time | Brier (1X2) | **0.502** | 0.626 | WIN | HT-conditional; O/U-2.5 also sharpens 0.264 -> 0.176 |
| Tennis | after set 1 | Brier | **0.151** | 0.219 | WIN | combined (Elo prior + realized set lead), leak-free leader framing |

**Reading it:** where a leak-free per-period corpus exists (NBA per-quarter linescores, MLB
per-inning runs, soccer half-time, tennis set-1), the conditional-on-state forecaster is
decisively sharper than the static pregame line. The strongest forecaster fuses the pregame
prior with the realized state. This is the decisive, measured, calibrated, delivered edge -
forecaster quality, not a dollar edge.

---

## 5. Architecture

One sport-blind kernel + per-sport adapters. Adding a sport is an adapter, not a kernel rewrite.

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

- **`domains/<sport>/predictor.py`** - the per-sport adapter: a single calibrated
  win-probability anchors `predict()` / `to_jd()` (pregame, the cohesive read) and
  `predict_live()` (in-game, the live read). Adapters exist for all four sports
  (`basketball_nba`, `mlb`, `soccer`, `tennis`).
- **`scripts/platformkit/cohesive_read.py`** (`cv-predict`) - the coherent pregame surface
  off the anchor: moneyline, totals, margin.
- **`scripts/platformkit/live_read.py`** + `live_read_cli.py` (`cv-live`) - the in-game
  repricer that conditions the same prior on the realized state.
- **`scripts/platformkit/predict_matchup.py`** (`cv-matchup`) - the unified CLI a buyer runs:
  one matchup -> pregame surface + in-game reprice in a single JSON read, with an explicit
  `"edge_claimed": false` and honest framing baked into every response.
- **~25 leak-free / OOS proof modules** under `scripts/platformkit/proof_*` (`proof_nba`,
  `proof_mlb`, `proof_soccer`, `proof_tennis`, plus shared `proof_common`) reproduce every
  scorecard number: beat-the-close, in-game accuracy, as-of/leak-free gate tests, fusion, and
  calibration. The two roll-up scoreboards (`beat_the_close_scoreboard.py`,
  `ingame_scoreboard.py`) regenerate the tables in sections 3-4 from committed fixtures.

The CLI returns an explicit no-edge contract. Real output (NBA, BOS vs LAL, pregame):

```json
{
  "sport": "nba", "home": "BOS", "away": "LAL",
  "edge_claimed": false,
  "framing": "Pregame MATCHES the devigged close (calibration/sharpness, not an edge); in-game ADDS the realized state. No $ edge.",
  "pregame": { "p_home_win": 0.605, "total_mean": 211.3, "margin_home": 3.0 },
  "ingame":  { "p_home_win": 0.5732, "pregame_p_home": 0.605, "proj_total": 211.3 }
}
```

---

## 6. Why this is sellable - the rigor IS the product

- **Leak-free by construction.** Walk-forward / OOS held-out evaluation, as-of feature
  builders, truncation-invariance leak tests, and per-fold leak-guard gates. The proof modules
  do not confirm headlines - they are built to refute them.
- **Honest nulls are successes.** "BEHIND by freshness" and "MATCH within noise" are stated
  plainly. The full-season backtest that proves the pregame market is efficient is reported as
  a result, not buried.
- **Self-caught retractions = proof of discipline.** The same person who built the system built
  the instruments that caught and retracted his own over-claims (a market-follow ROI artifact, a
  Q4 lookahead leak, an L5-proxy ceiling mislabeled as edge). Those retractions live, in full
  context, in [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) and
  [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). This doc cites the honest numbers only.
- **The in-game edge is the one measured, calibrated, delivered advantage**, proven 4/4 sports
  and shipped through `predict_live` / `cv-live`.

---

## 7. Reproduce it

A buyer reproduces every number from a fresh clone in under a minute:

- **Slim install:** `pip install -r requirements-predictor.txt` (or `pip install -e .` to get
  the `cv-matchup` / `cv-predict` / `cv-live` console entrypoints).
- **One matchup (pregame + in-game):**
  `python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --elapsed 0 --home-score 0 --away-score 0`
- **Reproduce the scoreboards on committed fixtures (proof in <60s):**
  `python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof` and
  `python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof`

Full step-by-step is in [docs/PREDICTOR_QUICKSTART.md](PREDICTOR_QUICKSTART.md); the proof-module
map and what each one validates is in [docs/PROOFS.md](PROOFS.md). The canonical scorecard
numbers above are the full-corpus measurements in `vault/_Edge_Maps/_Beat_The_Close.md` and
`vault/_Edge_Maps/_Ingame_Scoreboard.md`; the fixture commands run the SAME code on a small
committed sample (flagged "fixture/demo mode") so the pipeline is verifiable end-to-end without
the private corpora.

---

## 8. Origin / NBA computer-vision lineage (engineering history, not the product)

This platform grew out of **CourtVision**, an NBA broadcast-video computer-vision pipeline:
YOLOv8n ball detection, SIFT homography, Kalman + Hungarian tracking, OSNet re-ID, and a
possession-level Monte Carlo simulator, feeding a FastAPI serving layer. That is real,
substantial engineering (see [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) section 2),
and the validation machinery built there - walk-forward CV, leak guards, the multi-corpus
calibration gate - is exactly what makes the predictor platform trustworthy today.

But it is **lineage, not the headline.** The CV-derived features carry ~0 measured predictive
value in production today (SHAP ~0); we do NOT claim a CV moat. The product is the converged
4-sport calibrated predictor above. The CV pipeline is the origin story that explains where the
rigor came from.

---

*All prediction numbers in this doc are calibration / sharpness, never a dollar edge. The single
honesty truth-source is [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md); retracted numbers
appear only there and in [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), in explicit retraction
context, and never here.*
