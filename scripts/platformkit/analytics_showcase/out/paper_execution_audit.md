# Paper Execution Audit

edge_claimed: False  |  units: probability points (not dollars, not ROI)

Source: `data/pod_backup_2026_07_20/frontend/clv_ledger.jsonl`

## Counts

- records: 83
- placed: 83
- executed (real fills): 0
- suppressed (gate-failed): 0
- status split: {'open': 46, 'settled': 37}
- sport split: {'mlb': 79, 'wnba': 4}
- settled outcome split: {None: 46, 'loss': 17, 'win': 20}

## Placement-time divergence (probability points)

- n=82, median=0.0920, mean=0.0816, min=0.0101, max=0.1441
- divergence = |model_prob - implied_prob(taken_decimal)| at the moment the paper bet was logged. It measures how far the model's number sat from the price taken -- a pre-trade sizing input, not realized CLV.

## Realized CLV

- clv_pct is null for all 37 settled rows in this corpus -- no independent closing-price feed was captured for this channel, so realized CLV could not be measured (degraded honestly, not fabricated).

## Settle status snapshot

```json
{
  "updated_at": "2026-07-20T15:51:39Z",
  "component": "m_ingame_paper_settle",
  "settled": 0,
  "still_open": 9,
  "errors": 0,
  "by_sport": {
    "mlb": {
      "settled": 0,
      "open": 5
    },
    "wnba": {
      "settled": 0,
      "open": 4
    }
  },
  "executed": false,
  "edge_claimed": false,
  "units": "probability",
  "note": "settles OPEN paper_ingame bets against the realized final score (MLB via ticker->boxscore); units/probability only, no $; a game not yet final stays open. This is the missing in-game settle arm.",
  "consecutive_zero_ticks": 8,
  "status": "OK"
}
```

## Honest story

This is a PAPER-only execution ledger (83 logged bets, all executed=False -- none of these were real fills). Every row passed its exec_gate (0 suppressed-by-gate rows survive in this rescued corpus). 37/83 rows settled by final score; realized CLV is unmeasurable for all of them because no independent close feed was wired for the paper_ingame channel -- the corpus honestly records clv_status='no_close' rather than backfilling a number. The only quantity this ledger can speak to is placement-time divergence (model vs taken price), reported in probability points, which is a measurement of execution behavior, not a proven edge.
