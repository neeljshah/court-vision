# 2026-10-06 CLV ledger cleanup: six fake KALSHI_A test rows removed (PAPER ONLY)

## Cause
The old `tests/platformkit/test_pm_paper_tick_runner.py` (before commit f243fe37f,
"red tests r2 (cause J)") called `pm_paper_tick_runner.tick(..., pm_dir=tmp_path)`.
Since the 06-20 single-ledger redesign (0d6db3cfc) `tick()` ignores `pm_dir` and appends
to `_DEFAULT_LEDGER` = `data/frontend/clv_ledger.jsonl` (the real local ledger, gitignored).
Only `test_pm_filter_market_id_grouping` produced rows that survive `_coerce_row`
(the other fixtures had no venue and were dropped): two `KALSHI_A` rows per run
(units 0.5 and 0.2; venue inferred from the id). f243fe37f adds an autouse fixture that
redirects the ledger, diagnostic and heartbeat to tmp_path.

## Matching signature
`market_id == "KALSHI_A"` and `bet_id == "pm|kalshi|KALSHI_A"` and `ts` on 2026-10-06.
Full fixture shape: `{"market_id":"KALSHI_A","units":0.5|0.2,"venue":"kalshi","is_pm":true,
"executed":false,"channel":"paper","status":"open","clv_status":"INSUFFICIENT_DATA",
"taken_book":"kalshi","bet_id":"pm|kalshi|KALSHI_A","stake_units":0.5|0.2}`.
No other row in the ledger matched; no other fixture id (PM_B, NBA_GM1_OU, NBA_GM2_ML,
MKT1, MKT_X) was present.

## Removed (line numbers in the pre-cleanup file)
| line | ts (UTC) | units |
|---|---|---|
| 21 | 2026-10-06T05:19:47.804411 | 0.5 |
| 22 | 2026-10-06T05:19:47.804411 | 0.2 |
| 23 | 2026-10-06T11:18:06.290390 | 0.5 |
| 24 | 2026-10-06T11:18:06.290390 | 0.2 |
| 25 | 2026-10-06T11:23:49.229570 | 0.5 |
| 26 | 2026-10-06T11:23:49.229570 | 0.2 |

## Before / after
- Before: 26 rows, 20294 bytes, sha256 `2e98e71e50962639b350ea52af0390eee921a44945dad7e6188b3599e9b749b9`
- After: 20 rows, 18584 bytes, sha256 `f492d8fea427ac0e6ea2dada4b8a6dbfe3e092e81579305419b11f64f432c521`
- The after file is byte-identical to the first 18584 bytes of the backup (cmp verified):
  rows 1-20 untouched, line endings (CRLF) preserved.
- Backup (byte-exact, kept): `data/frontend/clv_ledger.jsonl.bak_fake_rows_2026-10-06`
  (sha256 equals the before hash).

## Method
Done at ~12:47Z, between the 12:26Z tick (status.json tick.ts) and the 12:56Z tick, inside
`scripts.platformkit.clv_ledger_io.ledger_lock` (fail-closed, required=True), with a temp
file plus `os.replace`. Asserted exactly lines 21-26 matched before writing.
Fix commit for the test: f243fe37f. Local-only data; nothing under data/ is committed.
