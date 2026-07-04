# Tail-Bias Evidence: Final Memo

Scope: H1 longshot-underpriced [0.10,0.20) and H2 mid-fav-overpriced [0.65,0.80),
the sprint's lead edge candidate (prereg 2026-07-03). Every number below is copied
verbatim from the cited artifact; nothing here is recomputed.

## 1. Full corpus table

| Corpus | Sport | Band | n_games | venue_gap | CI95 | Verdict |
|---|---|---|---|---|---|---|
| kalshi_discovery_2026 | mlb | H1 [.10,.20) | 42 | +0.1260 | [-0.0732, 0.3259] | CALIBRATED |
| kalshi_discovery_2026 | mlb | H2 [.65,.80) | 63 | -0.1784 | [-0.3339, -0.0173] | VENUE_OVERPRICES |
| kalshi_historical (excl. discovery window) | mlb | H1 [.10,.20) | 750 | -0.0080 | [-0.0390, 0.0247] | CALIBRATED |
| kalshi_historical (excl. discovery window) | mlb | H2 [.65,.80) | 942 | +0.0061 | [-0.0964, 0.1046] | CALIBRATED |
| kalshi_historical | nba (all 106 mkts, no discovery overlap) | H1 [.10,.20) | 62 | +0.1322 | [-0.1545, 0.4988] | CALIBRATED |
| kalshi_historical | nba | H2 [.65,.80) | 74 | -0.0017 | [-0.1831, 0.1626] | CALIBRATED |
| polymarket_2023 | mlb | H1 [.10,.20) | 14 | +0.3678 | [0.0170, 0.7036] | VENUE_UNDERPRICES |
| polymarket_2023 | mlb | H2 [.65,.80) | 138 | -0.0399 | [-0.1816, 0.0693] | CALIBRATED |
| polymarket_2023 | nba | H1 [.10,.20) | 122 | +0.0857 | [-0.0618, 0.2575] | CALIBRATED |
| polymarket_2023 | nba | H2 [.65,.80) | 280 | -0.0542 | [-0.1447, 0.0347] | CALIBRATED |
| polymarket_2024plus_mlb | mlb | H1 [.10,.20) | 1630 | -0.0103 | [-0.0367, 0.0180] | CALIBRATED |
| polymarket_2024plus_mlb | mlb | H2 [.65,.80) | 1900 | -0.0175 | [-0.0898, 0.0535] | CALIBRATED |
| polymarket_2024plus_nba | nba | H1 [.10,.20) | 1056 | +0.0397 | [-0.0109, 0.0929] | CALIBRATED |
| polymarket_2024plus_nba | nba | H2 [.65,.80) | 1058 | -0.0348 | [-0.0879, 0.0163] | CALIBRATED |
| forward_gates (pre-registered) | mlb | H1 [.10,.20) | 3 games / n_ticks=89 | +0.6107 | null (INSUFFICIENT_DATA) | INSUFFICIENT_FORWARD |
| forward_gates (pre-registered) | mlb | H2 [.65,.80) | 3 games / n_ticks=488 | +0.3000 | null (INSUFFICIENT_DATA) | INSUFFICIENT_FORWARD |
| forward_gates | soccer_intl | H1+H2 | 31 games (n_ticks not surfaced) | n/a | n/a | INSUFFICIENT_FORWARD (DECIDABLE_NOW per scoreboard) |
| forward_gates | wnba, kbo, npb, soccer, tennis | H1+H2 | 0 games each | n/a | n/a | INSUFFICIENT_FORWARD (NEVER_AT_THIS_RATE) |

Sources: `data/venue_history/kalshi/{mlb,nba}_tail_validation.json` (MLB row uses
`excluded_discovery_window.bands`, the honest independent subset; NBA's
`pooled_all.bands` == `excluded_discovery_window.bands` per the file's own note,
since no discovery-window overlap ran for NBA), `data/venue_history/polymarket/
{mlb,nba}_tail_validation.json`, `data/venue_history/polymarket/
{mlb,nba}_2024plus_tail_validation.json`, `data/frontend/ops/
tail_hypothesis_ledger.json` (kalshi_discovery_2026 rows), `data/domains/mlb/
ingame_tail_verdict.json` (forward gate), `data/frontend/ops/
forward_evidence_scoreboard.json` (cross-sport forward accrual).

## 2. Honest conclusion

**H2 (mid-fav overpriced [.65,.80)) is CALIBRATED in every independent historical
corpus**: Kalshi MLB excl. discovery (n=942, gap +0.0061), Kalshi NBA (n=74, gap
-0.0017), Polymarket-2023 MLB (n=138, gap -0.0399), Polymarket-2023 NBA (n=280, gap
-0.0542), Polymarket-2024+ MLB (n=1900, gap -0.0175), Polymarket-2024+ NBA (n=1058,
gap -0.0348). The one non-calibrated H2 read is the Kalshi 2026 *discovery* sample
itself (n=63, gap -0.1784, VENUE_OVERPRICES) -- the sample the hypothesis was mined
from, not independent confirmation. H2 is dead: no persistent mispricing.

**H1 (longshot underpriced [.10,.20)) is CALIBRATED everywhere except one thin
pocket**: Polymarket-2023 MLB, n=14 games (n_ticks=373), gap +0.3678, CI95
[0.0170, 0.7036] -- VENUE_UNDERPRICES, the smallest sample in the table. Every
other H1 read is CALIBRATED: Kalshi MLB excl. discovery (n=750, gap -0.0080),
Kalshi NBA (n=62, gap +0.1322, CI spans zero), Polymarket-2023 NBA (n=122, gap
+0.0857), Polymarket-2024+ MLB (n=1630, gap -0.0103), Polymarket-2024+ NBA
(n=1056, gap +0.0397). Per the ledger's synthesis: "only the PM-MLB-2023 pocket
(n=14) is significant; every larger corpus reads CALIBRATED." Most likely a
small-sample artifact in the thinnest cell, not a persistent edge.

## 3. What would change the verdict

The forward gate (`ingame_tail_gate.py`, pre-registered 2026-07-03) is the sole
arbiter and has not yet decided. Per `data/domains/mlb/ingame_tail_verdict.json`:
MLB forward_n=5 games since registration, both H1 and H2 read INSUFFICIENT_FORWARD
(H1: gap +0.6107 on n_ticks=89/3 games; H2: gap +0.3000 on n_ticks=488/3 games --
directionally provocative, statistically undeclared, CI null). The scoreboard
shows MLB at `distance_to_decidable: 5_DAYS` against its pre-declared floor (~20
games needed vs 5 accrued). The 6-sport multi registration (wnba/kbo/npb/soccer/
tennis/soccer_intl, mostly registered 2026-07-04T12:00Z) shows 0 forward games for
5 of 6 sports (`NEVER_AT_THIS_RATE`) and soccer_intl at forward_n=31
(`DECIDABLE_NOW` per scoreboard, gate file itself still INSUFFICIENT_FORWARD).
Only these pre-registered gates accruing to their floors could resurrect H1 --
historical corpora are exhausted and already lean CALIBRATED.

## 4. No edge claimed

Every source artifact carries `"edge_claimed": false`. All statements above are
calibration/coverage statements about venue price accuracy vs. realized outcome,
not $ ROI or PnL. Acting on a future CONFIRMED verdict remains a human decision
per the gate's own `honest_note`.
