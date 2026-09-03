# S177 S88 cluster-unit re-quote

This calibration re-quote reads the archived S88 probabilities from
`s88_phase_recal_2026-09-04.csv` and joins S106 real-game sequence labels from
the read-only MLB joined store. It does not refit any probability. The archived
CSV has 33,920 evaluation ticks, including 11,087 informative ticks on both
bases. The two bases therefore cover the same tick rows.

| Basis | Bucket | Clusters | Mean paired Brier difference | 95% interval | Verdict |
| --- | --- | ---: | ---: | --- | --- |
| ticker | pooled | 127 | -0.002889992 | [-0.011405037, +0.005215357] | NO_CHANGE |
| ticker | late\|leading_big | 50 | +0.031643090 | [+0.008761613, +0.057204168] | IMPROVED |
| ticker | mid\|trailing | 66 | -0.011963636 | [-0.023186186, -0.001032645] | WORSE |
| real_game | pooled | 234 | +0.000364981 | [-0.007487816, +0.008318432] | NO_CHANGE |
| real_game | late\|leading_big | 52 | +0.027234030 | [+0.004565782, +0.052815341] | IMPROVED |
| real_game | mid\|trailing | 76 | -0.006392399 | [-0.017149273, +0.004151254] | NO_CHANGE |

The self-contained
`s88_cluster_unit_2026-09-04.json` artifact stores these six rows beside the
234 real-game per-unit Brier series and all 11,087 informative paired losses
(cluster id, timestamp, incumbent loss, and recalibrated loss). It is sufficient
to recompute the clustered intervals from archived probabilities alone.

The S106 split input had 77,327 unique `(game_id, ts)` rows: 227 tickers, 360
real games, 112 multi-game tickers, and 21,284 ticks in sequence two or later.

## NOT VERIFIED

- No probability was refit or newly trained.
- No new external corpus was assessed.
- No live deployment behavior was assessed.
