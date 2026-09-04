# S272 NBA in-game pooled-tail recalibration

## Verdict: BEHIND

Preregistration: `docs/evidence/harness/S272_ingame_tail_recal_prereg_2026-09-04.md`

Preregistration SHA-256: `bd33af6d49a43150916e7d4d6a0dd6e15a520165aab9a2834159042b39ed006d`

S224 premise reproduced before scoring: low 136809/775, high 171947/963, middle 156493, total 465249, dropped 0.

| denominator | arm | Brier (95 pct game-clustered CI) | tail ECE (95 pct game-clustered CI) | n ticks / games |
|---|---|---|---|---|
| all | candidate | 0.073354 [0.069461, 0.077502] | - | 465249 / 1593 |
| all | incumbent | 0.073317 [0.069432, 0.077459] | - | 465249 / 1593 |
| tail | candidate | 0.006840 [0.005205, 0.008700] | 0.001245 [0.000289, 0.003119] | 308756 / 1590 |
| tail | incumbent | 0.006785 [0.005173, 0.008618] | 0.001493 [0.000579, 0.003293] | 308756 / 1590 |

All-ticks improvement versus recal_null: -0.000037 [-0.000070, -0.000008]; frozen bar: +0.004.
Although pooled tail ECE declines from 0.001493 to 0.001245, the all-ticks result is BEHIND; this is a trade-off, not a win.

## Method and reproduction

The shared `cpcv_evaluate` route used two season groups, the shared purge, and a symmetric one-day embargo. Fits admit only strict-prior game-first-dates. The candidate changes only the fixed low/high tail; outside it candidate equals recal_null.

Artifacts: `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json` and `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv`. The paired CSV has per-game all-tick loss sums plus tail-tick predictions/losses, sufficient to recompute the reported all-ticks Brier and tail ECE.
Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2829826 bytes; tabular, resolution not applicable). RSS at artifact write: 458616832 bytes. Route SHA-256: `4bb4d92c3095bf0d109bc6e02361683624c0e9b39d4e4c3cf6dd02f622464d76`.
Focused test: `python -m pytest scripts/platformkit/ingame/test_s272_ingame_tail_recal.py -q -p no:cacheprovider`.

## NOT VERIFIED

- Exact all-ticks bootstrap-CI replay from paired CSV alone; scorer game order is not archived.
