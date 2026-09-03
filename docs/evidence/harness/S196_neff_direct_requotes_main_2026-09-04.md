# S196 n_eff direct re-quotes in main repo

Verdict: ACCEPT WITH CORRECTIONS. The S196 premise is confirmed: 23 of 23
target source paths exist in the main repository, and all 23 were converted
from RE-LABELLED to direct RE-QUOTED. The manifest remains 45 rows; its 22
pre-existing RE-QUOTED rows were not changed.

Method: `scripts.platformkit.ingame.gap_effective_n.effective_sample_size` was
run directly on each named raw series, one series at a time and in CSV or
Parquet batches. The informative rule is per-game adjacent `p_candidate` or
`market_prob` change at eps=1e-9, after `game,timestamp` keep-first duplicate
handling. All other rows use all ticks. Per-row source SHA-256, row count,
columns, exact selection rule, direct result, and delta are in
`neff_requote_2026-09-04/direct_requotes.csv`. Small raw tables are copied in
`neff_requote_2026-09-04/direct_sources/`; larger sources are represented by
their SHA-256, row count, and column list. All new source entries are appended
to `neff_requote_2026-09-04/source_inventory.csv`.

| Readout | Published n_eff | Direct n_eff | Direct minus published |
| --- | ---: | ---: | ---: |
| S87b_S80_embargo1_precise | 62.557218376843984 | 62.557218376843984 | 0.0 |
| S87b_S80_embargo0 | 354.3171 | 354.31707081777245 | -0.000029182227535784477 |
| S87b_S80_embargo1_rounded | 62.5572 | 62.557218376843984 | 0.00001837684398253714 |
| S137_S102 | 2295.57 | 2295.4971373056483 | -0.07286269435189752 |
| S137_S82_before | 214.83 | 214.82711185416437 | -0.0028881458356408984 |
| S137_S82_after | 107.06 | 214.82711185416437 | 107.76711185416437 |
| S137_S87_before | 569.67 | 566.1817005774958 | -3.4882994225041557 |
| S137_S87_after | 521.04 | 566.1817005774958 | 45.14170057749584 |
| S137_S112_nba_before | 351.0 | 351.0 | 0.0 |
| S137_S112_nba_after | 171.0 | 171.0 | 0.0 |
| S137_S112_mlb_before | 231.53 | 231.53300700573214 | 0.0030070057321438526 |
| S137_S112_mlb_after | 281.0 | 262.5834267623995 | -18.416573237600517 |
| S137_S114_before | 2369 | 2674.7554542625944 | 305.7554542625944 |
| S137_S114_after | 2674.76 | 2674.7554542625944 | -0.004545737405805994 |
| S137_S116_before | 103.06 | 103.06059446211249 | 0.0005944621124882588 |
| S137_S116_after | 95.09 | 95.08805957009676 | -0.0019404299032430572 |
| S137_S119_before | 120.72 | 214.82711185416437 | 94.10711185416437 |
| S137_S119_after | 107.63 | 214.82711185416437 | 107.19711185416438 |
| S137_S121_before | 107.62 | 214.82711185416437 | 107.20711185416437 |
| S137_S121_after | 107.06 | 214.82711185416437 | 107.76711185416437 |
| S137_S102_recap | 2295.57 | 2295.4971373056483 | -0.07286269435189752 |
| S137_S103 | 2120.08 | 2120.084228331924 | 0.004228331923968653 |
| S137_S115 | 3239.8 | 3239.803849871872 | 0.0038498718718074088 |

No verdict moved. Differences are retained as direct source-to-label deltas;
they do not establish any performance claim.

## NOT VERIFIED

- No target source path is absent.
- The S137 historical labels that differ from the named raw source's current
  row or cluster construction are not reconstructed beyond the direct raw
  re-quote. Their direct deltas above are the finding.
- The S102 source's direct value differs by -0.07286269435189752 from its
  archived label; the raw Parquet source and selected hypothesis are recorded.

Test: `python -m pytest tests/platformkit/ingame/test_s161_neff_requote_manifest.py -q`
passes in the `basketball_ai` environment.
