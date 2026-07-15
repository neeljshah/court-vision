# CourtVision -- 4-Sport Calibrated Prediction Platform

A single converged engine that produces one calibrated win-probability per sport, anchors a
coherent pregame market surface, and reprices it live as a game unfolds. Built for rigor: every
headline number is leak-free / walk-forward / out-of-sample, reproducible in under 60 seconds,
and the system caught and retracted its own over-claims. No fabricated dollar edge -- ever.

---

## WHAT IT IS

A converged 4-sport (NBA / MLB / Soccer / Tennis) calibrated prediction platform. One
win-probability per sport drives a coherent pregame surface (`predict` -> `to_jd`) plus an
in-game repricer (`predict_live`), all behind a single unified CLI. Adding markets or conditioning
on a realized game state never breaks the shared spine -- the same calibrated prior flows from
pregame through in-game.

- One predictor interface per sport (`domains/<sport>/predictor.py` -> `cohesive_read` for
  pregame, `live_read` for in-game).
- One command-line entry point (`scripts/platformkit/predict_matchup.py`, installed as
  `cv-matchup`).
- 70+ leak-free / OOS proof modules (81 including tests) that grade the platform against the
  market and against itself -- beat-the-close, in-game, calibration, platform, and edge-hunt
  scoreboards among them.

## WHAT IT PREDICTS (markets x sports)

| Sport  | Pregame markets               | In-game checkpoint (conditional reprice) |
|--------|-------------------------------|------------------------------------------|
| NBA    | moneyline, total (O/U)        | end of Q1 / Q2 / Q3                       |
| MLB    | moneyline, total (O/U)        | after inning 3 / 5 / 7                    |
| Soccer | O/U-2.5 (and in-game 1X2)     | half-time                                 |
| Tennis | ATP match-win                 | after set 1                               |

Every prediction is a calibrated probability or a calibrated point forecast (with dispersion) --
never a recommended wager.

## HOW GOOD vs THE MARKET (calibration / sharpness -- NOT an edge)

**Pregame -- vs the devigged closing line, leak-free OOS (held-out 2nd half).**
Lower Brier / RMSE is sharper. "MATCH" = within sampling noise of the sharp close. "BEHIND" =
the market's injury / lineup / weather freshness a public + box-score model cannot see.

| Sport / market    | Our model     | Close   | Verdict                         |
|-------------------|---------------|---------|---------------------------------|
| NBA moneyline     | Brier 0.1735  | 0.1672  | MATCH (within noise)            |
| NBA total O/U     | RMSE  19.17   | 18.11   | BEHIND (injury/lineup freshness)|
| MLB moneyline     | Brier 0.2429  | 0.2390  | MATCH (tiny pitcher-blindness)  |
| MLB total O/U     | RMSE  4.72    | 4.44    | BEHIND (park/weather/SP)        |
| Soccer O/U-2.5    | Brier 0.2465  | 0.2390  | MATCH (pooled Platt)            |
| Tennis ATP ml     | Brier 0.2177  | 0.2028  | BEHIND (ATP closes very tight)  |

Source: `vault/_Edge_Maps/_Beat_The_Close.md`.

**In-game -- conditioning on the realized state vs the static pregame line.**
A live book also sees the state, so this is forecaster QUALITY, not a dollar edge.
NOTE: NBA row is real-corpus-only (VALIDATION_PENDING on a fresh clone -- committed fixture
prints no-improvement for NBA = SYNTHETIC ANCHOR ARTIFACT). MLB/Soccer/Tennis reproduce.

| Sport  | Static -> Conditional Brier  | When                               | Corpus |
|--------|------------------------------|------------------------------------|--------|
| NBA    | 0.209 -> 0.159               | end Q1/Q2/Q3 (rating prior + score)| VALIDATION_PENDING (real-corpus only; fixture = no-improvement) |
| MLB    | 0.241 -> 0.126               | after inning 3/5/7                 | reproduces on committed fixture |
| Soccer | 1X2 0.626 -> 0.502; O/U 0.264 -> 0.176 | half-time               | reproduces on committed fixture |
| Tennis | 0.219 -> 0.151               | after set 1 (leak-free leader)     | reproduces on committed fixture |

Source: `vault/_Edge_Maps/_Ingame_Scoreboard.md`. edge_claimed = False.

**The thesis.** Pregame MATCHES the devigged close on team-strength markets and is BEHIND on
totals / ATP only by freshness data the market sees and we cannot. IN-GAME conditioning -- the
pregame intelligence prior fused with the realized state -- is the decisive, measured, calibrated,
and delivered improvement. MLB/Soccer/Tennis wins reproduce on committed fixtures; NBA in-game
win is real-corpus (VALIDATION_PENDING for buyers without the private corpus). We never claim a
dollar edge.

## WHY TRUST IT (the rigor IS the product)

- **Leak-free by construction.** Walk-forward / expanding-window evaluation with assertion-level
  per-fold leakage guards and truncation-invariance tests (a feature at time T is byte-identical
  with or without future events). Every headline above is OOS on a held-out window.
- **Reproducible proof in 60 seconds.** The two scoreboards re-derive the verdicts from committed
  fixtures on a fresh clone -- no private data, no network.
- **We caught and retracted our own over-claims.** The same harnesses that grade the market were
  pointed inward. They flagged a market-follow ROI artifact, a Q4 look-ahead leak in an in-play
  win-prob model, and an in-sample-tuned filter -- and those numbers were retired in writing.
  Building the instrument that disproves your own hype is the strongest signal here.
- **Honest nulls are successes.** A full-season leak-free backtest proved the pregame model is
  well-calibrated but does not beat the sharp close -- documented as a headline result, not buried.
  Every candidate pregame edge was REJECTED across >=2 corpora -- including catching my own
  full-sample signals that sign-flip out-of-sample -- in the 4-sport real-data edge hunt:
  [`MARKET_EFFICIENCY_PROOF.md`](MARKET_EFFICIENCY_PROOF.md).

Honesty truth-source (the single place numbers are reconciled, including the explicit list of
retracted figures): [`JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md) and
[`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Cite those; this page restates no retracted number.

## RUN IT IN 60 SECONDS

Slim install (predictor only):

```
pip install -r requirements-predictor.txt      # or:  pip install -e .  -> cv-matchup / cv-predict / cv-live
```

1. Pregame + in-game for one matchup:

```
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

Returns one JSON object: a calibrated pregame block (`p_home_win`, `total_mean`, `margin_home`)
and an in-game block that reprices off the realized state -- with `edge_claimed: false` baked in.

2. Reproduce the pregame beat-the-close scoreboard on committed fixtures:

```
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
```

3. Reproduce the in-game scoreboard on committed fixtures:

```
python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof
```

Both scoreboards print the per-sport verdict table directly. The fixtures are small and committed,
so a buyer can verify the methodology end-to-end on a fresh clone in well under a minute; the
canonical full-corpus numbers above live in `vault/_Edge_Maps/`.

---

### Origin / NBA computer-vision lineage (engineering history, not the product)

CourtVision began as an NBA broadcast-video computer-vision pipeline (YOLOv8n ball detector,
SIFT homography, Kalman + Hungarian tracking, OSNet re-ID) feeding a possession-level Monte Carlo
sim and a FastAPI serving layer. That is real, substantial engineering and the lineage of this
platform -- but the CV-derived features carry roughly zero measured predictive value today
(SHAP ~ 0 in production), so the CV layer is not sold as an edge. The product is the converged
calibrated predictor above. See [`JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md) for the full
audited account of the CV pipeline as engineering evidence.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
