# S195 Paired Brier Delta Correction

Spec: `docs/evidence/tracking/specs/S195_spec.md`

Verifier contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

## Result

The source artifact now publishes close-versus-first-populated-anchor Brier
comparisons from the games shared by both arms. The source manifest was
regenerated because it republishes both verdict sentences. The acceptance
denominator is therefore 8 quote sentences, not the 4 initially enumerated.

| Quote site | Before | After |
|---|---|---|
| `micro_closing_decay.json` WNBA verdict | T-6h 0.2454 -> close 0.2280, n=30 | T-6h 0.2356 -> close 0.2347, delta=+0.0009, n=25 |
| `micro_closing_decay.json` soccer_intl verdict | T-24h 0.1355 -> close 0.1374, n=13 | T-24h 0.1355 -> close 0.1568, delta=-0.0213, n=7 |
| `docs/evidence/true-intelligence.md` WNBA bullet | T-6h 0.2454 -> close 0.2280, n=30 | T-6h 0.2356 -> close 0.2347, delta=+0.0009, n=25 shared games |
| `docs/evidence/true-intelligence.md` soccer_intl bullet | T-24h 0.1355 -> close 0.1374, n=13 | T-24h 0.1355 -> close 0.1568, delta=-0.0213, n=7 shared games |
| `docs/ANALYTICS_CATALOG.md` WNBA row | T-6h 0.2454 -> close 0.2280, n=30 | T-6h 0.2356 -> close 0.2347, delta=+0.0009, n=25 shared games |
| `docs/ANALYTICS_CATALOG.md` soccer_intl clause | T-24h 0.1355 -> close 0.1374, n=13 | T-24h 0.1355 -> close 0.1568, delta=-0.0213, n=7 shared games |
| `site_manifest.json` WNBA one-line | T-6h 0.2454 -> close 0.2280, n=30 | T-6h 0.2356 -> close 0.2347, delta=+0.0009, n=25 |
| `site_manifest.json` soccer_intl one-line | T-24h 0.1355 -> close 0.1374, n=13 | T-24h 0.1355 -> close 0.1568, delta=-0.0213, n=7 |

## Local reproduction

Each local store was measured separately before regeneration: WNBA line history
was 15 JSONL files / 140,366,035 bytes and soccer_intl was 29 JSONL files /
157,713,980 bytes. Both are below the 300 MB read limit. Joining only to their
respective local ESPN outcome parquet yields:

| Sport | First populated anchor | Paired n | First-anchor Brier | Close Brier | Delta |
|---|---:|---:|---:|---:|---:|
| WNBA | T-6h | 25 | 0.235641 | 0.234696 | +0.000945 |
| soccer_intl | T-24h | 7 | 0.135518 | 0.156807 | -0.021289 |

`close_vs_t24h_paired` is unchanged. All pre-existing bucket n, Brier,
log-loss, mean probability, and underpowered values are unchanged. The copied
regenerated artifact is
`docs/evidence/harness/micro_closing_decay_s195_regenerated.json`.

## Exhaustiveness check

The analytics output directory contains 101 JSON artifacts. The numeric
Brier/log-loss-keyed scan found these 14: `bookmaker_accuracy`,
`brier_skill_scores`, `calibration_by_market_type`, `calibration_over_time`,
`calibration_stability`, `info_arrival_curve`, `market_disagreement_profile`,
`mechanism_wiring`, `micro_closing_decay`, `murphy_decomposition`,
`novel_overreaction_harvest_gap`, `soccer_calibration_pack`,
`tennis_showcase`, and `xsport_structure`.

The five required additional delta-artifact checks found that
`cross_sport_scoreboard` uses already paired same-unit rows, while
`mechanism_ledger_export`, `novel_market_foresight_premium`, and
`why_attribution` do not republish this closing-horizon cross-arm Brier
comparison. `site_manifest` republishes both affected sentences and raises the
acceptance denominator by two. The acceptance result is 8 of 8 quoted
sentences with the paired n and paired delta.

## NOT VERIFIED

- The staged `webapp/public/data/showcase/` mirrors were not regenerated. Its
  staging module explicitly reserves that write for the gate phase, and those
  mirrors are outside this source-artifact acceptance denominator.
- No new model, threshold, out-of-sample comparison, confidence interval, or
  trial was introduced. Q1-Q5 and Q9 do not add a new scoring obligation;
  the corrected deterministic paired calculation is reconstructible from the
  stated line-history stores and outcome parquets.

## Verifier self-check

- B1-B10: no filtered metric, schema removal, gate change, deployment, module
  move, head-slice sampling, self-fit claim, recycled denominator, or threshold
  change.
- Q6: calibration language only; no financial-performance language or
  retracted figure.
- Q7: the denominator is a complete construct of 8 published source quote
  sentences, so no sample-size rail applies.
- Q8: the premise was re-measured before implementation and was confirmed.

## ATTEMPT 2 (LOC rail and audit correction)

- The LOC repair extracts stable loader/scorer code into
  `scripts/platformkit/analytics_showcase/closing_decay_io.py` while preserving
  imports from `micro_closing_decay.py`; before: main 378 lines, helper absent;
  after: main 269 lines and helper 130 lines.
- `data/cache/eval_gate/gate_manifest.json` is absent in this worktree, so its
  protected byte identity is NOT VERIFIED.
- `data/cache/eval_gate/backtest_fwer.jsonl` is absent in this worktree, so its
  protected byte identity is NOT VERIFIED.
