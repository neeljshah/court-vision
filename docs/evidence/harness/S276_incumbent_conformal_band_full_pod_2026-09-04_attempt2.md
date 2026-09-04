# S276 attempt 2 full-source CPCV conformal band, pod scratch

## Result

The sealed CPCV design reaches 465249 ticks / 1593 game clusters. Its census is
465249 loaded, 465249 scorable, and 465249 scored ticks; 1593 loaded, 1593
scorable, and 1593 scored game clusters; `excluded_by_reason={}`. Every S86
game-first-date block was the held-out block exactly once. The symmetric
embargo and purge removed only training states, never a scored evaluator state.

This is a calibration measurement, not a comparative promotion. Attempt 1
remains REJECT: its paired archive was 461947 ticks / 1582 clusters and its
walk-forward score was 384862 / 1337. The corrected attempt-1 memo and JSON
remain at their original dated paths.

The sealed preregistration is
`docs/evidence/harness/S276_preregistration_incumbent_conformal_band_full_pod_2026-09-04_attempt2.md`.
Its LF-normalized SHA-256 seal is
`8217203a503ebcf52c90889d4b97629c964cdae00e932d6a3f9f367ff22de2a2`.

## STATIC grouped coverage and mean half-width

| Nominal | Cell | Scored ticks | Groups | Coverage | Mean half-width |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0.90 | P1 | 44428 | 50 | 0.920000000 | 0.083881183 |
| 0.90 | P2 | 68825 | 50 | 0.940000000 | 0.062643881 |
| 0.90 | P3 | 52645 | 50 | 0.940000000 | 0.055754549 |
| 0.90 | P4 | 284586 | 50 | 0.900000000 | 0.010091224 |
| 0.90 | OT | 14765 | 36 | 0.916666667 | 0.055659232 |
| 0.90 | ALL | 465249 | 50 | 1.000000000 | 0.031524964 |
| 0.80 | P1 | 44428 | 50 | 0.800000000 | 0.062678054 |
| 0.80 | P2 | 68825 | 50 | 0.820000000 | 0.048306048 |
| 0.80 | P3 | 52645 | 50 | 0.860000000 | 0.037046453 |
| 0.80 | P4 | 284586 | 50 | 0.820000000 | 0.004889075 |
| 0.80 | OT | 14765 | 36 | 0.777777778 | 0.030226131 |
| 0.80 | ALL | 465249 | 50 | 1.000000000 | 0.021273111 |

No cell is ABSENT_BECAUSE. The lowest grouped coverage is OT at nominal 0.80,
0.777777778; the widest mean half-width is P1 at nominal 0.90, 0.083881183.
The S101 24-cell regression line is `max_abs_coverage_diff=0.0`.

## Reproduction artifacts and pod boundary

- Full source: `data/cache/inplay_odds/nba_checkpoints_full.parquet`,
  2829826 bytes, Parquet tabular input; pixel resolution is not applicable.
- S101 summary: `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json`,
  30939 bytes, JSON tabular input; pixel resolution is not applicable.
- S101 retained screen: `reference/s101_aci_coverage_2026-09-03_ticks.csv.gz`,
  scratch MD5 parity `2dd8f53f9ec629cb5764e6201dad539a`; compressed CSV tabular
  input; pixel resolution is not applicable.
- Paired evaluator archive:
  `docs/evidence/harness/S276_incumbent_conformal_band_full_pod_paired_loss_2026-09-04_attempt2.csv.gz`,
  10904326 bytes, SHA-256
  `4c49985745fe05409b31b80c5e03447746dd59ea1d1b44ae2d15e4a7c7fc2b62`.
  Its decompressed SHA-256 is
  `f4f1399a09b71604250682ecd35c17461e9969775a6f3465d85749ff68eaee77`,
  the exact fetched CSV hash.

The computation used only `/c/Users/neelj/bin/pod_run a17` in
`/workspace/wt/a17`. The dd write probe passed, the data link was read-only,
and no deployed-tree write, process stop, process restart, backtest_fwer.jsonl,
hypotheses SQLite path, or data/registry path was used. An accidental duplicate
scratch launch was allowed to finish without intervention; both emitted the
same census and S101 line. The accepted final JSON is the later run, with pod
peak RSS 1948352512 bytes.

Both-sided MD5 parity for every shipped route input was verified:

| Input | MD5 |
| --- | --- |
| s276 attempt-2 route | cb9bef57e8c2d0d2a2f83af2f26ac727 |
| CPCV engine | 62f1d751a928c59215a8f7de6245d928 |
| S265 route | 83e9a01e4919aaea00179f0a7adce48b |
| S86 route | aed2f5bf0f0983abf39d63a016ac0c64 |
| S101 route | 1900301a909da76a6372eaa6dd5a2209 |
| S123 incumbent route | 9752f2818550233c8fe92dae0c0257f9 |
| ACI route | 9937ea988d5a3a8a4e5df27ffc4c80ca |
| attempt-2 preregistration | 35e3b9550f8efcb5912bbfa66e196176 |

The focused archive-census test asserts JSON `n_scored_*` equals the paired
CSV census on a fixture and streams the fetched gzip artifact structurally.
Not independently rerun: the pod execution and peak RSS. The local checks
replayed its complete archive census, grouped cells, seal, identities, and
S101 summary.
