# Calibration Record

> DECISION-SUPPORT, NOT a picks / profit / +EV / ROI product. Every number is a CALIBRATION measurement (predicted vs observed), badged by SOURCE. 'MARKET-EFFICIENT HERE' -- matching the devigged close within noise -- is the HONEST, expected result and a first-class feature, not a failure. edge_claimed=False everywhere; no $ figure is produced. Real-corpus OOS-vs-close is VALIDATION_PENDING (human-run).

Source badges: [model-in-corpus] our calibrated forecaster in its own corpus; [devigged-market] the Shin-devigged closing line; [score-only-anchor] the synthetic golden regression anchor (not a real calibration claim).

## Headline state

**MARKET-EFFICIENT HERE** on team-strength markets: where we have power, the calibrated forecast MATCHES the devigged close within noise -- the expected, honest success state for a calibrated predictor, never an edge. Where a slice trails the close it is stated as BEHIND; where rows are thin it ABSTAINS. The decisive measured/calibrated value is in-game state conditioning (see the predictor's `--state` path), not a pregame $ edge.

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

## 3. Reproduce (offline, < 60s each)

```
python -m scripts.platformkit.eval_gate.run_gate --golden
python -m scripts.platformkit.ledger.replay_proof
python -m scripts.platformkit.calibration_record --write
```

## 4. VALIDATION_PENDING (human-run)

The numbers above reproduce the COMMITTED FIXTURES only. A real-corpus OOS-vs-close calibration result is a human-run step on local/gitignored corpora; no real-data win is claimed here. See docs/SELL-READINESS.md and docs/JOB_EVIDENCE_PACKET.md.
