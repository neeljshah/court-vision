# S258 incumbent conformal band v2

## Result

This is a full-source, STATIC-arm calibration measurement of the S123 NBA incumbents. The source denominator is 465249 ticks / 1593 games, loaded only with `s86_nba_every_tick.load_ticks(s86.CHECKPOINTS)` on the pod.

The preregistration was committed before scoring in `40726169c`. Its committed LF-byte seal is `143bb939056ad70ead1fc5c83b0fbd6fd3b9cfd616a2f0b4536db24464172d7a`. The first code checkpoint is `f85372af9`; the archival paired-loss addition and pre-score ledger launch entry are `de104319b`.

## Inputs and execution

| Input | Location opened on pod | Bytes | Resolution | SHA-256 |
| --- | --- | ---: | --- | --- |
| Full checkpoint source | `/workspace/nba-ai-system/data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2829826 | Parquet tabular input; no pixel resolution | `5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5` |
| S101 reference | `/workspace/nba-ai-system/data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` | 30939 | JSON | N/A |
| S101 SCREEN input | `/workspace/nba-ai-system/data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` | 49052957 | CSV | N/A |

Machine: pod `root@213.192.2.123:40034`, repository `/workspace/nba-ai-system`. The full-source computation ran there because the local RAM guard terminates this approximately 1 GB lane. The completed scorer PID was `2986984`; log path: `/workspace/s258_conformal_v2.log`. PID monitoring bounded the completed wall clock to 00:09:05 through 00:09:32. The summary was written at 2026-09-04 09:33:52 UTC. The prior no-output launcher PID `2985892` ended after discovering that the committed preregistration had not yet been archived to the pod; no summary JSON was written by that launcher. The sealed file was then archived with matching bytes before PID `2986984` started.

The retrieved raw pod outputs are retained in `S258_incumbent_conformal_band_v2_2026-09-04/`. The canonical summary is `S258_incumbent_conformal_band_v2_2026-09-04.json`; its per-game paired-loss archive is `S258_incumbent_conformal_band_v2_2026-09-04_paired_loss.csv` (1582 paired games / 461947 paired ticks). The canonical CSV preserves those paired Brier rows and appends 50 `grouped_coverage` rows for e4, nominal 0.90, P1, transcribed from the retained pod summary. Those rows make one reported coverage and half-width cell recomputable from the CSV without loading the full source; the raw pod CSV remains unchanged.

## STATIC coverage and interval half-width

Coverage is empirical grouped coverage against the nominal level. Every reported phase cell has at least 400 ticks. No present cell is below `COVERAGE_MIN_GROUP=400`, so there is no `ABSENT_BECAUSE` cell in this run; a cell below that threshold would be retained with its explicit `ABSENT_BECAUSE` reason rather than omitted. The differing scored counts below are named results of the train-only seed and S123 as-of anchor availability; they do not replace the full input denominator.

| Arm | Nominal | Cell | Ticks | Groups | Coverage | Mean half-width |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| e4 | 0.90 | P1 | 37621 | 50 | 0.940000000 | 0.092931704 |
| e4 | 0.90 | P2 | 58364 | 50 | 1.000000000 | 0.113404045 |
| e4 | 0.90 | P3 | 44519 | 50 | 1.000000000 | 0.068198943 |
| e4 | 0.90 | P4 | 234328 | 50 | 1.000000000 | 0.010497366 |
| e4 | 0.90 | OT | 12162 | 30 | 0.966666667 | 0.023539530 |
| e4 | 0.90 | ALL | 386994 | 50 | 0.980000000 | 0.041078518 |
| e4 | 0.80 | P1 | 37621 | 50 | 0.920000000 | 0.070216525 |
| e4 | 0.80 | P2 | 58364 | 50 | 0.980000000 | 0.084306410 |
| e4 | 0.80 | P3 | 44519 | 50 | 0.960000000 | 0.056033628 |
| e4 | 0.80 | P4 | 234328 | 50 | 0.980000000 | 0.006813215 |
| e4 | 0.80 | OT | 12162 | 30 | 0.866666667 | 0.009209693 |
| e4 | 0.80 | ALL | 386994 | 50 | 0.980000000 | 0.030401446 |
| ladder_base | 0.90 | P1 | 37398 | 50 | 1.000000000 | 0.147028274 |
| ladder_base | 0.90 | P2 | 58009 | 50 | 1.000000000 | 0.146450716 |
| ladder_base | 0.90 | P3 | 44277 | 50 | 1.000000000 | 0.095688023 |
| ladder_base | 0.90 | P4 | 233016 | 50 | 0.640000000 | 0.029242594 |
| ladder_base | 0.90 | OT | 12162 | 30 | 0.933333333 | 0.066561486 |
| ladder_base | 0.90 | ALL | 384862 | 50 | 0.780000000 | 0.067178185 |
| ladder_base | 0.80 | P1 | 37398 | 50 | 0.940000000 | 0.115241087 |
| ladder_base | 0.80 | P2 | 58009 | 50 | 1.000000000 | 0.109309079 |
| ladder_base | 0.80 | P3 | 44277 | 50 | 1.000000000 | 0.073596361 |
| ladder_base | 0.80 | P4 | 233016 | 50 | 0.580000000 | 0.020946362 |
| ladder_base | 0.80 | OT | 12162 | 30 | 0.633333333 | 0.042459276 |
| ladder_base | 0.80 | ALL | 384862 | 50 | 0.740000000 | 0.050164711 |

The worst-covered cell is `ladder_base`, nominal 0.80, P4: 0.580000000 coverage. The widest interval is `ladder_base`, nominal 0.90, P1: mean half-width 0.147028274. These are descriptive calibration results, not a deployment or performance claim.

## S101 regression and reproducibility

S101 STATIC market/model grouped coverage was rerun unchanged against its SCREEN CSV. Across 24 arm/nominal/cell values, the maximum absolute coverage difference is `0.0`, satisfying the required tolerance of `<= 1e-9`.

The evaluator kept the fixed S101 constants: 5 folds, game-disjoint purge, symmetric one-day embargo, `COVERAGE_MIN_GROUP=400`, `COVERAGE_MAX_GROUPS=50`, and two minimum groups. Every emitted fold asserts the purge and embargo relationship. The JSON retains fold records and grouped held-out calibration units. The CSV archives paired as-of e4 and ladder-base per-game Brier losses with cluster identifier, timestamps, tick count, and outcome so the differential is reconstructible.

| Route | SHA-256 used by scorer |
| --- | --- |
| s258 evaluator | `efab4f26af0da254ae38e19a7ce5182d924a9be099ed90b7d32f01902b3d0cd3` |
| S86 loader | `5ee345fa337f7a458ab4180ebcf8b7234adcf8a1d1d6cbcddddb2cc63f68c7ad` |
| S101 evaluator | `f80d94c783aeebffd2e56c9e0fa34dbddab93b5d683846ba7c170c1b4b665dbb` |
| S123 incumbent | `ba91cf85e1e5b3f1822b1b5fb551c52a1c2b5095cc12fa9298c053a6c2049f50` |
| ACI support | `b37877d34ef13dd9b62bbc8b6b68dffd038a58de56f9ca4031ad91effe56c2cf` |

## Pod transfer MD5 parity

The full source, S101 SCREEN input, S101 reference, preregistration, and retrieved raw outputs matched on both sides. The canonical summary and paired-loss CSV are local, explicitly described archive enrichments, so their MD5 values differ from the unchanged raw pod outputs.

| Item | MD5 |
| --- | --- |
| s258 evaluator | `7ad5fd0ea045ec7dad2a2141b9e655a8` |
| S86 loader | `8f4189c45c87de3c883a557042b1f3cf` |
| S101 evaluator | `a03f45e96b9c5ea9b454386bea47dbdd` |
| S94 import | `6a3a8b6fabda8949466ca6546ae33e07` |
| S123 incumbent | `7981daa0261fbae4dd9243cbcee55d92` |
| ACI support | `e2207e37a5cb70a02456949e61e55291` |
| Full checkpoint source | `8e0e8c51833d538a17f13c17e1f9a459` |
| S101 SCREEN CSV | `9d01e63f21dc0c304200ca942c86c7d0` |
| S101 reference JSON | `fb987311d277b586905900be9750a405` |
| Sealed preregistration | `621feb81956b38d1a87004a8eead845d` |
| Raw pod summary JSON | `d06cc7bc963aefecbf8bee7f5f8c2947` |
| Paired-loss CSV | `d7c39c9559b8a5735db4666e52b3cdb0` |
| Pod log | `ac79a822d0ee5fff58338dc82f802c34` |

| Artifact | Local MD5 | Pod MD5 | Status |
| --- | --- | --- | --- |
| Raw paired-loss output | `d7c39c9559b8a5735db4666e52b3cdb0` | `d7c39c9559b8a5735db4666e52b3cdb0` | byte-identical retrieval |
| Pod summary JSON | `d06cc7bc963aefecbf8bee7f5f8c2947` | `d06cc7bc963aefecbf8bee7f5f8c2947` | byte-identical retrieval |
| Canonical summary JSON | `1d8924282ad1fe347edad451f4c0e7f6` | `d06cc7bc963aefecbf8bee7f5f8c2947` | local SHA-256 reference update for the enriched CSV |
| Canonical paired-loss CSV | `e7167870368bd009f4cbf36664571932` | `d7c39c9559b8a5735db4666e52b3cdb0` | local archive enrichment described above |

The recorded pod log tail is retained at `S258_incumbent_conformal_band_v2_2026-09-04/pod_log.txt`; it ends with the 24 table rows and `S101 STATIC max_abs_coverage_diff 0`.

## Contract self-check and NOT VERIFIED

- Q1: the committed preregistration seal predates scoring.
- Q2: the pre-score launch row is committed in `de104319b` and names K=0 and the absent, unwritten FWER path. No FWER, hypothesis, registry, or protected pod cache file was written.
- Q3: all fixed thresholds and fold constants are retained.
- Q4: the code uses its purged, symmetric-embargo walk-forward design and the S101 STATIC regression reproduces to the required tolerance.
- Q5: this is a calibration report, not an AHEAD result.
- Q6: calibration language only.
- Q7: this S-row is reproducible from the named full source and artifacts.
- Q8: the premise was remeasured before scoring: 465249 ticks / 1593 games.
- Q9: the per-game paired-loss CSV and grouped calibration differential are archived beside the summary.

NOT VERIFIED:

- An independent verifier has not rerun the landed archive.
- No second independent corpus is supplied; this memo makes no cross-corpus result.
- The opt-in evaluator has no deployment or feature-flag action.
- The pre-score launch entry records K=0 from the absent FWER path; its K read was not independently witnessed by a verifier.
