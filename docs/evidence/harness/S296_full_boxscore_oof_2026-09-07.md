# S296 strict-prior full-boxscore OOF (2026-09-07)

## Result

SINGLE-WINDOW calibration comparison. Improvement is baseline loss minus candidate loss; positive means
candidate better. CRPS, pinball and energy carry their own units, so the frozen +0.004 bar is not their
threshold and nothing here is compared against it. All comparative NULL results are valid.

| Field | CRPS base | CRPS cand | CRPS improvement | CRPS 95 pct CI | q50 pinball improvement | Coverage base | Coverage cand | below q10 | above q90 | q10==q90 atom |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| min | 9.829701 | 8.780448 | 1.049253 | [0.965079, 1.076456] | 0.897697 | 0.6251 | 0.5420 | 0.1175 | 0.3405 | 0.2148 |
| pts | 6.213131 | 5.276364 | 0.936766 | [0.902024, 0.968623] | 0.708209 | 0.6866 | 0.6330 | 0.0667 | 0.3003 | 0.2180 |
| reb | 2.352726 | 2.057103 | 0.295623 | [0.284676, 0.306682] | 0.205276 | 0.6963 | 0.6646 | 0.0564 | 0.2790 | 0.2178 |
| oreb | 0.751458 | 0.679343 | 0.072114 | [0.069669, 0.076378] | 0.060793 | 0.8249 | 0.8182 | 0.0072 | 0.1746 | 0.2426 |
| dreb | 1.812435 | 1.608457 | 0.203978 | [0.194675, 0.211616] | 0.144483 | 0.7237 | 0.6903 | 0.0444 | 0.2654 | 0.2205 |
| ast | 1.622360 | 1.363154 | 0.259206 | [0.252797, 0.268772] | 0.179390 | 0.7626 | 0.7212 | 0.0307 | 0.2481 | 0.2252 |
| stl | 0.540781 | 0.523970 | 0.016811 | [0.014217, 0.018422] | 0.032222 | 0.8450 | 0.8349 | 0.0019 | 0.1632 | 0.2502 |
| blk | 0.385383 | 0.355341 | 0.030041 | [0.028254, 0.032119] | 0.011134 | 0.8805 | 0.8795 | 0.0015 | 0.1190 | 0.3416 |
| tov | 0.841947 | 0.762621 | 0.079327 | [0.075199, 0.083610] | 0.053182 | 0.8058 | 0.7858 | 0.0123 | 0.2019 | 0.2320 |
| fgm | 2.284250 | 1.967762 | 0.316489 | [0.303862, 0.326241] | 0.241675 | 0.7152 | 0.6708 | 0.0511 | 0.2780 | 0.2192 |
| fga | 4.480915 | 3.716797 | 0.764118 | [0.737681, 0.788941] | 0.582014 | 0.6561 | 0.6039 | 0.0810 | 0.3151 | 0.2152 |
| fg3m | 0.877560 | 0.765637 | 0.111923 | [0.108539, 0.116948] | 0.092621 | 0.8152 | 0.7963 | 0.0132 | 0.1905 | 0.3139 |
| fg3a | 2.071703 | 1.682316 | 0.389387 | [0.381908, 0.403300] | 0.305775 | 0.7430 | 0.6916 | 0.0427 | 0.2656 | 0.2728 |
| ftm | 1.243260 | 1.080613 | 0.162647 | [0.157407, 0.171582] | 0.130315 | 0.8164 | 0.7964 | 0.0109 | 0.1928 | 0.2649 |
| fta | 1.542326 | 1.338763 | 0.203564 | [0.198099, 0.214479] | 0.164917 | 0.8084 | 0.7866 | 0.0132 | 0.2002 | 0.2551 |
| pf | 1.038413 | 1.002694 | 0.035719 | [0.029979, 0.037636] | 0.037630 | 0.7692 | 0.7397 | 0.0287 | 0.2316 | 0.2205 |
| plus_minus | 7.239793 | 7.222568 | 0.017225 | [-0.024603, 0.016096] | -0.007192 | 0.6215 | 0.5998 | 0.2020 | 0.1982 | 0.2151 |

Denominators: every field row scores n = 78767 held-out player-games in 3645 game clusters; nominal q10-q90 coverage is 0.80.

| Joint metric | Baseline | Candidate | Improvement | Paired 95 pct CI |
|---|---:|---:|---:|---|
| energy | 17.650227 | 16.127457 | 1.522770 | [1.438063, 1.564659] |
| energy_train_scaled | 3.363129 | 3.044121 | 0.319008 | [0.308110, 0.328133] |
| coherence_violation | 0.000000 | 0.000000 | 0.000000 | [0.000000, 0.000000] |

## Folds

| Split | Dates | Rows | Held-out games | Status |
|---|---|---:|---:|---|
| 0 | 2023-10-24 .. 2024-02-09 | 16705 | 775 | SCORED |
| 1 | 2024-02-10 .. 2024-12-08 | 17522 | 812 | SCORED |
| 2 | 2024-12-09 .. 2025-03-30 | 16088 | 755 | SCORED |
| 3 | 2025-03-31 .. 2026-01-21 | 16624 | 768 | SCORED |
| 4 | 2026-01-22 .. 2026-06-05 | 11828 | 535 | SCORED |

## Reproduction

- Shared vector CPCV used one stable player-game state per scored tick, the inherited purge, and a
  symmetric one-day embargo; every source tick is a test state exactly once.
- Samples are archived as source-state keys and reconstruct from the re-emitted observed-field table.
- No future-label reads: the predictor selects only evaluator-supplied states strictly earlier than each
  test timestamp, and the test view has its outcome vector removed under strict redaction.
- Every per-field q10/q50/q90, pinball, coverage, exceedance and atom figure is in the JSON summary;
  the per-state paired losses are in the paired-losses parquet.

## Premise and absorbed S292 preflight

Both were re-measured inside the scoring process, before any fit, and again locally on this box.

| Premise fact | Spec value | Measured |
|---|---|---|
| player_boxscores.parquet unique game_id+player_id | 77,744 | 77,744 (1,118,538 bytes) |
| nba_player_box_extension.parquet rows | 1,023 | 1,023 (34,147 bytes) |
| union unique player-games | 78,767 | 78,767 |
| game clusters | 3,645 | 3,645 |
| key overlap between the two sources | 0 | 0 (also 0 shared game ids) |
| source algebra violations | 0 | 0 over 7 checks (oreb+dreb==reb, fgm<=fga, fg3m<=fg3a, fg3m<=fgm, ftm<=fta, 2*(fgm-fg3m)+3*fg3m+ftm==pts, non-negativity) |
| missing keyed field cells | 0 | 0 across all 17 fields x 78,767 rows |
| S271 sample carries player_id | no | no: S271_boxscore_quantile_producer_sample_2026-09-04_attempt2b.parquet has 18 columns, none of them player_id |

Zero-minute preservation: 547 observed DNP rows (min == 0) are kept in every denominator, alongside
42,317 bench rows. Missing roster records are NOT OBSERVABLE from these two sources: neither carries an
as-of roster, so an absent player leaves no key at all. The only quantification available is the
per-game-team row count, measured at min 7 / median 10 / max 18 over 3,645 games.

Absorbed S292 preflight, n = 4 (CONSTRUCT, exhaustive). All four counts reproduced and all four are
labelled NOT_TESTABLE_TODAY:

| Input | Measured | Blocking fact |
|---|---|---|
| data/cache/prop_calibration_history.parquet | 4,942 rows, 7 stats, no game_id column | player-stat AGGREGATE grain; no per-game rows exist to join |
| data/cache/props_eval_nba_calibration.json | overall n = 356,678 | aggregate summary only; no per-bet or per-game record archived |
| data/cache/prop_sigma_scale.json | 7 rolling scale factors, window 15 | the per-game residuals they derive from are not archived |
| data/frontend/prop_history_corpus.jsonl | 3,000 rows, market_prob NULL on all 3,000, 15 unique prop_player ids, 619 unique player-game pairs, model_prob <= 0.05: 21 rows, >= 0.90: 20 rows | no market comparison is possible at all, and both tail bins are below n = 30 |

The aggregate-versus-per-bet granularity distinction and the total absence of market comparisons are
reported here as blocking facts, not omitted. The preflight ran on the local box because three of the
four inputs do not exist on the pod and the fourth path there is a 0-byte file; its measured table
(docs/evidence/harness/S296_s292_preflight_2026-09-07.json, carrying per-input bytes and SHA-256) was
shipped into the pod job and embedded in the summary JSON.

## Cold-start diagnostic subset

The sealed empty-prior convention (prereg attempt 2) scores every row, including rows whose strict-prior
league prefix is empty; those use the fixed all-zero vector point mass in BOTH arms. Measured here:
16,705 of 78,767 scored rows (21.2 pct) are cold-start rows, all of them in CPCV split 0, whose training
blocks are entirely later in time. Only 77 of those 16,705 rows have an all-zero observed vector, so the
degenerate arm is wrong on nearly all of them, it is identical in both arms (paired delta exactly 0), and
it pulls the all-rows coverage and CRPS numbers in the headline table down. A further 3,510 rows had no
player prior but a non-empty league prefix (20,215 league-fallback rows in total).

Those rows are never excluded. The table below is an additive diagnostic recomputed from the archived
artifacts alone: restrict the samples parquet to cold_start_zero == 0 (62,062 rows) and recompute, taking
the CRPS terms from the paired-losses parquet.

| Field | Coverage all rows (n=78,767) | Coverage warm rows (n=62,062) | CRPS base warm | CRPS cand warm | CRPS improvement warm |
|---|---:|---:|---:|---:|---:|
| min | 0.5420 | 0.6859 | 6.444846 | 5.113170 | 1.331676 |
| pts | 0.6330 | 0.7708 | 4.997159 | 3.808246 | 1.188912 |
| reb | 0.6646 | 0.8108 | 1.899217 | 1.524022 | 0.375195 |
| oreb | 0.8182 | 0.9062 | 0.687813 | 0.596288 | 0.091525 |
| dreb | 0.6903 | 0.8322 | 1.479408 | 1.220527 | 0.258881 |
| ast | 0.7212 | 0.8467 | 1.393001 | 1.064026 | 0.328975 |
| stl | 0.8349 | 0.9123 | 0.501929 | 0.480593 | 0.021336 |
| blk | 0.8795 | 0.9336 | 0.360114 | 0.321987 | 0.038127 |
| tov | 0.7858 | 0.8919 | 0.745427 | 0.644748 | 0.100679 |
| fgm | 0.6708 | 0.8126 | 1.838412 | 1.436735 | 0.401677 |
| fga | 0.6039 | 0.7512 | 3.459399 | 2.489607 | 0.969792 |
| fg3m | 0.7963 | 0.8908 | 0.792543 | 0.650493 | 0.142049 |
| fg3a | 0.6916 | 0.8184 | 1.755403 | 1.261207 | 0.494197 |
| ftm | 0.7964 | 0.8811 | 1.132156 | 0.925730 | 0.206426 |
| fta | 0.7866 | 0.8770 | 1.389263 | 1.130907 | 0.258356 |
| pf | 0.7397 | 0.8790 | 0.832452 | 0.787119 | 0.045333 |
| plus_minus | 0.5998 | 0.7491 | 6.784389 | 6.762528 | 0.021861 |
| energy (joint) | n/a | n/a | 14.066473 | 12.133825 | 1.932648 |
| energy_train_scaled (joint) | n/a | n/a | 2.832647 | 2.427773 | 0.404875 |

Read against nominal 0.80, the warm rows OVER-cover on the low-count fields (blk 0.9336, stl 0.9123,
oreb 0.9062) and UNDER-cover on the wide ones (min 0.6859, plus_minus 0.7491, fga 0.7512). That is the
opposite direction from the headline all-rows table. The over-covering half is the comparable of S271,
whose fitted intervals over-covered at 0.894 / 0.907 / 0.900 for PTS / REB / AST against the same
nominal 0.80 on 23,458 rows and 1,266 games; the S296 warm rows sit at 0.7708 / 0.8108 / 0.8467 for the
same three fields on 62,062 rows and a full 3,645-game corpus.

## Endpoint exceedances and discrete atoms

Exceedances are strongly one-sided for every count field: below q10 runs 0.0015 (blk) to 0.2020
(plus_minus) while above q90 runs 11.90 pct (blk) to 34.05 pct (min). These are exceedance shares of the
held-out player-games, in their own units; no retracted figure is quoted anywhere here. The cause of the
one-sidedness is the zero atom, not a tuning
choice: a count field's empirical q10 is usually exactly 0, so "below q10" is nearly unreachable and the
whole miss mass sits in the upper tail. plus_minus, the one signed field with no floor at zero, is also
the one field with a near-symmetric split (0.2020 below, 0.1982 above). Degenerate atoms (q10 == q90)
are 0.2148 to 0.3416 of all rows but only 0.0035 to 0.1643 of warm rows: most of the all-rows atom mass
is the cold-start point mass itself.

## Estimator note on plus_minus

Exactly one of the 88 paired metrics has its point estimate outside its own CI: plus_minus_crps,
improvement 0.017225 with paired CI [-0.024603, 0.016096]. The two are computed on different weightings,
each fixed separately by the preregistration: the point estimate is the unweighted mean over the 78,767
scored rows, while the CI bootstraps game-cluster means, which weights each of the 3,645 games equally.
Neither is changed here. The honest reading is the CI: plus_minus is a NULL and no improvement is
established on it. Three other metrics also have CIs covering zero and are likewise NULL:
blk_coverage_loss, pf_pinball_q10, and coherence_violation (identically 0.0 in both arms). All
comparative NULLs are valid results.

## Machine, route and provenance

- Pod job 20260907174807_147781_10273; log /workspace/wt/a17/jobs/20260907174807_147781_10273/pod_run.log.
- Pod log tail: RSS_MB before 189.25 | S292_PREFLIGHT all_reproduced=True falsified={} | S296_PREMISE {...}
  | RSS_MB after 4106.30 | S296_COMPLETE rows=78767 games=3645 rss_mb=4106.30 wall_seconds=3327.80 |
  POD_RUN_DONE job=20260907174807_147781_10273 rc=0. Host VmHWM high-water at read time: 2,878,512 kB.
- The scorer ran exactly once, on the pod, in the per-worktree scratch job root; the deployed tree was
  never written and nothing under data/ was written on either machine.
- Two-sided source hash parity, local worktree against pod:
  player_boxscores.parquet 9590d276e075309a181b0c4cb46e9d157dc2ab9f340cfeb63c07a0cba7252152 and
  nba_player_box_extension.parquet d18f69c03d6fd8b00bd3d4cf047a112ffc651b614cadb4e27c07badbf8393e94
  match on both sides.
- Route SHA-256 for every file the run exercised is in the summary JSON under route_sha256
  (full_boxscore_oof.py, s296_report.py, s292_preflight.py, cpcv_vector_distribution.py, cpcv_engine.py).
- Three preregistration seals, verified by the run itself and recorded in the JSON: 06d8bba3 (base),
  71fd96e1 (empty-prior correction), 53862fc7 (2026-09-07 finish-audit supplement).
- Tests: python -m pytest tests/platformkit/test_s296_full_boxscore_oof.py -q -> 5 passed (seals for all
  three preregs; truncation, unseen player, empty prior and DNP; sample identities and signed plus_minus;
  endpoint/atom accounting and train-scaled energy invariance; key uniqueness, independent folds and
  score replay to 1e-12). python -m pytest tests/platformkit/test_loc_rail_scope.py -q -> 1 passed.
- The paired-losses archive is NOT in git (see the section below); the samples parquet (28,007,843
  bytes) is landed uncompressed.
- A superseded 2026-09-04 attempt of this row exists untracked in the worktree. It predates the
  finish-audit clauses, carries no preflight, premise, atom or train-scaled-energy output, and its route
  hashes name code that has since changed. It is deliberately NOT landed; this 2026-09-07 set is the
  result.

## Paired-losses archive (not in git)

The per-state paired-losses table is retained out of git: at 144,391,569 bytes gzipped it exceeds the
100 MB GitHub blob limit and the repository's 50 MB evidence rail, so the landing deliberately excludes
it. Every number in this memo is reproducible from it plus the landed samples parquet.

| Property | Value |
|---|---|
| File | S296_full_boxscore_oof_2026-09-07_paired_losses.parquet.gz |
| SHA-256 (gzip) | 63c6881ec65e274b9baa47c3c1476ef77ef5f641403cf48d09a214e4b0174b2c |
| Size, gzipped | 144391569 bytes |
| Size, raw parquet | 205147186 bytes |
| Rows | 78,767 unique player-game keys (verifier EVIDENCE check decoded the committed gzip to 78,767 unique rows) |

Retained locations, both outside git:

- Worktree: C:/Users/neelj/nba-track-a17/docs/evidence/harness/S296_full_boxscore_oof_2026-09-07_paired_losses.parquet.gz
- Pod job root: /workspace/wt/a17/jobs/20260907174807_147781_10273

## Corrections applied at landing

- Verifier codex-sol (memo docs/evidence/harness/S296_VERIFY_2026-09-07.md, CORRECTION line) required the
  summary JSON artifact record to name the file that actually exists. Applied: in
  S296_full_boxscore_oof_2026-09-07.json the artifacts key suffix .parquet was renamed to .parquet.gz with
  size 144391569, and 205147186 is retained under a separate top-level raw_bytes key. No score, count or
  interval changed. The verifier's three NEW GAP items (reporter records pre-compression path metadata;
  row-weighted point estimates paired with equal-game-weighted intervals; the spec's +0.004 bar does not
  name its remaining target) are recorded here and remain open.

## NOT VERIFIED

- Sample box-score algebra holds by construction: both arms resample observed source vectors, so the
  coherence-violation count is a property of the resampling, not evidence that a model learned coherence.
- A second independent corpus, any AHEAD promotion, or anything beyond SINGLE-WINDOW calibration.
- Missing roster records: neither source carries an as-of roster, so players with no row are unobservable.
- Live, deployment or forward-operating behaviour.
- The cold-start subset table and the S271 comparison are additive diagnostics recomputed from the
  archived artifacts; they are not a second corpus and do not change the preregistered headline numbers.
- The four S292 inputs are all NOT_TESTABLE_TODAY, so no prop-market or per-bet comparison of any kind
  was measured here.
- Whether 25 empirical samples is the right resolution for these distributions, and whether a richer
  family (minutes mixtures, rare-count families) would do better, is untested; those are S297 and S298.
- The 2026-09-04 attempt's artifacts were not re-scored, re-verified or landed.
