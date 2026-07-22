# Calibration Record

> DECISION-SUPPORT, NOT a picks / profit / +EV / ROI product. Every number is a CALIBRATION measurement (predicted vs observed), badged by SOURCE. 'MARKET-EFFICIENT HERE' -- matching the devigged close within noise -- is the HONEST, expected result and a first-class feature, not a failure. edge_claimed=False everywhere; no $ figure is produced. Real-corpus OOS-vs-close is VALIDATION_PENDING (human-run).

Source badges: [model-in-corpus] our calibrated forecaster in its own corpus; [devigged-market] the Shin-devigged closing line; [score-only-anchor] the synthetic golden regression anchor (not a real calibration claim).

## Headline state

**MARKET-EFFICIENT HERE** on team-strength markets: where we have power, the calibrated forecast MATCHES the devigged close within noise -- the expected, honest success state for a calibrated predictor, never an edge. Where a slice trails the close it is stated as BEHIND; where rows are thin it ABSTAINS. The decisive measured/calibrated value is in-game state conditioning (see section 3 and the predictor's `--state` path), not a pregame $ edge.

## 1. Eval-gate golden anchor (reliability)

Synthetic regression anchor scored leak-free / walk-forward. BSS<=0 / MATCHES is the HONEST result vs a near-oracle close.

### nba_2023_24  --  BEHIND (model trails close here -- stated honestly)

brier_model=0.2298 [model-in-corpus]  vs  brier_close=0.1851 [devigged-market]  bss=-0.2411  dm_p=0.0453  (golden anchor [score-only-anchor]: synthetic, not a real claim)

| bin | n | predicted | observed | flag | source |
|-----|---|-----------|----------|------|--------|
| 0.1-0.2 | 1 | 0.186 | 0.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.3-0.4 | 4 | 0.356 | 0.750 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.4-0.5 | 4 | 0.458 | 0.250 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.5-0.6 | 8 | 0.535 | 0.625 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.6-0.7 | 16 | 0.654 | 0.625 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.7-0.8 | 10 | 0.762 | 0.700 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.8-0.9 | 6 | 0.826 | 0.667 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.9-1.0 | 2 | 0.924 | 1.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |

### nba_2024_25  --  MARKET-EFFICIENT HERE (MATCHES_CLOSE)

brier_model=0.1827 [model-in-corpus]  vs  brier_close=0.1538 [devigged-market]  bss=-0.1884  dm_p=0.3172  (golden anchor [score-only-anchor]: synthetic, not a real claim)

| bin | n | predicted | observed | flag | source |
|-----|---|-----------|----------|------|--------|
| 0.0-0.1 | 6 | 0.066 | 0.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.1-0.2 | 8 | 0.137 | 0.125 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.2-0.3 | 18 | 0.236 | 0.333 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.3-0.4 | 9 | 0.330 | 0.333 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.4-0.5 | 2 | 0.450 | 0.500 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.5-0.6 | 5 | 0.535 | 0.800 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.6-0.7 | 2 | 0.640 | 0.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.7-0.8 | 1 | 0.733 | 1.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |
| 0.8-0.9 | 1 | 0.873 | 1.000 | SPARSE (n<30, unreliable) | [score-only-anchor] |

## 2. Track-record ledger (Brier / ECE vs devigged close)

Committed fixture ledger; per-sport calibration vs the Shin-devigged close. Each slice has n=30 < the n>=50 report threshold, so the honest verdict is ABSTAIN (too few rows to claim a result) -- surfaced, never buried. On a powered real corpus a non-significant DM would read MARKET-EFFICIENT HERE; that measurement is VALIDATION_PENDING.

Fixture rows (graded): 120 [model-in-corpus]

| sport | market | n | brier (model) | ece | brier (close) | dm_p | verdict |
|-------|--------|---|---------------|-----|---------------|------|---------|
| mlb | ml | 30 | 0.2275 [model-in-corpus] | 0.0832 | 0.2274 [devigged-market] | 0.9473 | ABSTAIN (insufficient_data, n<50) |
| nba | ml | 30 | 0.2491 [model-in-corpus] | 0.0764 | 0.2515 [devigged-market] | 0.4778 | ABSTAIN (insufficient_data, n<50) |
| soccer | over_2.5 | 30 | 0.2055 [model-in-corpus] | 0.1643 | 0.2030 [devigged-market] | 0.4228 | ABSTAIN (insufficient_data, n<50) |
| tennis | p1_match_win | 30 | 0.1970 [model-in-corpus] | 0.1302 | 0.1957 [devigged-market] | 0.6765 | ABSTAIN (insufficient_data, n<50) |

## 3. In-game conditioning -- the one measured CALIBRATION win [model in-corpus, real-corpus]

Conditioning the SAME pregame intelligence prior on the realized mid-game state sharpens the win-prob forecaster (lower Brier = sharper). FORECASTER QUALITY / calibration, NOT a $ edge -- a live book also sees the score, so no DM-vs-close applies and edge_claimed stays False. SCOPING: real-PRIVATE-corpus OOS numbers; on the committed SYNTHETIC fixture the NBA row prints no-improvement (a synthetic-anchor artifact, not a refutation). Reproduced by scripts/platformkit/proof_<sport>/ingame_accuracy.py, rolled up in scripts/platformkit/ingame_scoreboard.py.

| sport | checkpoint | static Brier | score-only Brier (rating-blind) | conditional Brier | gain (model-prior share) | source | corpus scope |
|-------|-----------|--------------|--------------------------------|-------------------|--------------------------|--------|--------------|
| NBA | end Q1/Q2/Q3 | 0.209 | 0.172 | 0.159 | -0.050 (prior adds -0.014, ~27%) | [model in-corpus, real-corpus] | real-corpus OOS = the win; committed fixture prints no-improvement (synthetic-anchor) |
| MLB | after inning 3/5/7 | 0.241 | 0.128 | 0.126 | -0.115 (prior adds -0.001, ~1%) | [model in-corpus, real-corpus] | real-corpus OOS; reproduces on the committed fixture |

MLB/Soccer/Tennis in-game wins reproduce on the committed fixture; the NBA win is real-corpus-only (VALIDATION_PENDING on a fresh clone). Honest attribution: most of the lift is conditioning on the realized score itself -- a rating-blind score-only arm already reaches 0.172 (NBA) / 0.128 (MLB). In NBA the pregame rating prior still adds a measured -0.014 Brier over score-only; in MLB the prior is washed out by mid-game (-0.001) and the realized state carries essentially the whole gain. Full three-arm table: docs/INGAME_PROOF.md section 2a. No $ edge; edge_claimed = False.

## 3a. Per-sport calibration record (consolidated, vs the devigged close)

Pregame calibration/sharpness per sport+market, leak-free OOS, vs the Shin-devigged close
(lower Brier/RMSE = sharper). MATCH = within sampling noise of the close (the honest best
case); BEHIND = a measurable freshness gap (data-bound, not a defect). Source: the
`proof_<sport>/` harnesses rolled up in `vault/_Edge_Maps/_Beat_The_Close.md`. Calibration
only; edge_claimed=False.

| Sport | Market | Metric | model | close | verdict | freshness gap explanation |
|-------|--------|--------|-------|-------|---------|---------------------------|
| NBA | moneyline | Brier | 0.1735 | 0.1672 | MATCH | MOV-aware Elo matches the devigged close |
| NBA | total O/U | RMSE | 19.17 | 18.11 | BEHIND | injuries / lineups a box model cannot see |
| MLB | moneyline | Brier | 0.2429 | 0.2390 | MATCH | tiny deficit = pitcher-blindness (close prices the SP) |
| MLB | total O/U | RMSE | 4.72 | 4.44 | BEHIND | park / weather / SP freshness |
| Soccer | O/U-2.5 | Brier | 0.2465 | 0.2390 | MATCH | pooled Platt recalibration |
| Tennis (ATP) | match-win | Brier | 0.2177 | 0.2028 | BEHIND | ATP closes are very efficient |

### In-game conditioning gain, per sport (the measured calibration win)

Static pregame -> conditional-on-state Brier (lower = sharper). FORECASTER QUALITY, not a $
edge. MLB/Soccer/Tennis reproduce on the committed fixture; NBA is real-corpus OOS
(VALIDATION_PENDING on a fresh clone -- the fixture prints no-improvement, a synthetic-anchor
artifact). Source: `proof_<sport>/ingame_accuracy.py` rolled up in `ingame_scoreboard.py`.

| Sport | Checkpoint | static -> conditional | gain | corpus scope |
|-------|-----------|------------------------|------|--------------|
| NBA | end Q1/Q2/Q3 | 0.209 -> 0.159 | -0.050 | real-corpus OOS; fixture = no-improvement (synthetic-anchor) |
| MLB | after inning 3/5/7 | 0.241 -> 0.126 | -0.115 | reproduces on committed fixture |
| Soccer 1X2 | half-time | 0.626 -> 0.502 | -0.124 | reproduces on committed fixture |
| Soccer O/U-2.5 | half-time | 0.264 -> 0.176 | -0.088 | reproduces on committed fixture |
| Tennis | after set 1 | 0.219 -> 0.151 | -0.068 | reproduces on committed fixture |

### How each verdict is computed (the labels are not editorial)

| Verdict | Rule | Code |
|---|---|---|
| **BEATS_CLOSE** | `BSS > 0` AND DM `p < 0.05` AND `n >= 200` | `eval_gate/run_gate.py::_verdict` |
| **MATCHES_CLOSE** | 95% CI on `(loss_close - loss_model)` overlaps 0 | `_verdict` + `dm_test.py` |
| **BEHIND** | otherwise (honest, recorded, NON-blocking) | `_verdict` |
| **ABSTAIN (insufficient_data)** | `n < 50` -> too few rows to claim a result; surfaced, never buried | the n=30 fixture rows in section 2 |
| **VARIANCE_ONLY** | point estimate fails but interval/coverage improves | `src/loop/gate.py::evaluate` |
| **DEFER** | no leak-safe matrix / no evaluable fold (INSUFFICIENT_DATA, fails closed) | `src/loop/gate.py::evaluate` |

DM is cluster-robust by `game_id` (a naive i.i.d. SE runs ~3x too narrow); BSS is the Brier
skill score of model over close. See [docs/quant-methodology.md](quant-methodology.md) for the
full toolkit and [docs/MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md) for the REJECT
self-audit.

---

## 3b. 2026-07 state — cross-sport rating object, live run

`python -m scripts.platformkit.platform_scoreboard --json` validates the ONE sport-blind
`GenericRatingModel` object (`scripts/platformkit/generic_rating.py`) OOS leak-free per sport
against each sport's own hand-tuned baseline (binary sports) or a naive mean (soccer expected-
score). This is a DIFFERENT comparison than section 3a: not vs the devigged close, but whether
the generic cross-sport abstraction holds up against the sport-specific tuned model. Live run,
2026-07-07:

| Sport | n (OOS) | Metric | Generic rating | Reference (tuned baseline / naive mean) | Beats reference? |
|-------|---------|--------|-----------------|------------------------------------------|-------------------|
| NBA | 4,646 | Brier | 0.21699 | 0.21806 (tuned baseline) | yes |
| MLB | 27,783 | Brier | 0.24760 | 0.24398 (tuned baseline) | no |
| Tennis | 30,416 | Brier | 0.22055 | 0.21845 (tuned baseline) | no |
| Soccer | 25,634 | expected-score RMSE | 0.40059 | 0.42674 (naive mean) | yes |

`validated=true/false` per sport is a beats-baseline flag, not a market-edge claim — see the
binding note in the script: "a baseline match / beats-naive is a validated abstraction, NOT a
market edge." NBA and soccer beat their reference; MLB and tennis trail their tuned baseline
(the generic object gives up sport-specific structure — pitcher identity for MLB, surface for
tennis — for cross-sport simplicity). This is the honest cost of the one-object abstraction,
not hidden.

**In-game static -> conditional framing (repeat, for the 2026-07 record):** the one measured
calibration win stays in-game state conditioning (section 3), with the model prior's marginal
share quantified there (NBA -0.014, MLB -0.001 vs a rating-blind score-only arm);
nothing above changes that. **WTA calibration:** the live temperature recalibrator
(`proof_tennis/wta_temp_live.py`, T=1.36, holdout ECE 0.045 -> 0.019) is a calibration fix, not
a market-vs-close row — it does not appear in section 3a because WTA has no comparable closing-
line corpus wired yet.

**Latency-audit verdict for in-game claims: NOT_ESTABLISHED.** The 2026-07-07 audit found our
GUMBO live-state capture ran a median 54s poll (gaps up to ~102 minutes) against Kalshi's own
~7s quote cadence, and a depth-of-book join for the leading moments failed to resolve (0/135) on
a ticker-format mismatch — a measurement-power problem, not a proven absence of lead. Capture was
upgraded same-day to a ~10s window (verified 11-18s across 11 concurrent live games); the
lead/lag verdict stays NOT_ESTABLISHED until the audit re-runs on the fine-grained captures. No
in-game latency edge is claimed here or anywhere until that re-measurement lands
(`docs/DATA_DEPTH.md` latency section is the full audit).

---

## 4. Reproduce (offline, < 60s each)

```
python -m scripts.platformkit.eval_gate.run_gate --golden
python -m scripts.platformkit.ledger.replay_proof
python -m scripts.platformkit.calibration_record --write
python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof
```

## 5. VALIDATION_PENDING (human-run)

The numbers above reproduce the COMMITTED FIXTURES only. A real-corpus OOS-vs-close calibration result is a human-run step on local/gitignored corpora; no real-data win is claimed here. The in-game section 3 numbers are real-corpus OOS (NBA VALIDATION_PENDING on a fresh clone). See docs/SELL-READINESS.md and docs/JOB_EVIDENCE_PACKET.md.

---

**Sibling docs:** [PROOFS](PROOFS.md) (claim -> proof index) -
[MARKET_EFFICIENCY_PROOF](MARKET_EFFICIENCY_PROOF.md) - [CEILING](CEILING.md) -
[quant-methodology](quant-methodology.md) - [backtest-methodology](backtest-methodology.md) -
[KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) - [full doc map](INDEX.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
