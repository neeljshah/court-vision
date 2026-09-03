# S88 -- per-phase recalibration on the S06 partition, spec chosen inside the folds (2026-09-04)

Row S88 (docs/evidence/HARNESS_GAPS_2026-09-03.md): "no charge" -- descriptive only, no
FWER ledger write, no prereg. Calibration language only; edge_claimed always False.

## 1. Premise (step 0, re-verified today)

Both artifacts the row cites are confirmed on disk and confirmed UNCITED anywhere in
`docs/evidence` except the gapfinder memo itself
(`grep -rln "mlb_bucket_recalibration\|probe_R12_B32" docs/evidence` -> only
`docs/evidence/harness/INGAME_GAP_PREMISES_2026-09-03.md`):

- `data/frontend/ops/mlb_bucket_recalibration.json` (2026-07-12): pooled Brier
  0.242978 -> 0.230308 recal; `late|leading_big` 0.3745 -> 0.2759 IMPROVED; pooled
  verdict_vs_raw NO_CHANGE. Winner spec confirmed chosen IN-SAMPLE at
  `scripts/platformkit/ingame/bucket_recalibration.py:213`
  (`winner_name = min(SPECS, key=lambda n: spec_pooled[n]["recal"]["brier"])` --
  `spec_pooled[n]` is computed on the SAME `eval_ticks` the CI at `score_group` then
  rules on); persisted params additionally refit on ALL history at `:226`.
- `data/cache/probe_R12_B32_recal_winprob_endQ{1,2,3}.json`: orphan, NBA, endQ3
  retracted lineage, no CI, no market baseline -- zero `docs/` references. Out of
  scope below (no S06-equivalent leak-free partition or incumbent exists for it).

Premise CONFIRMED TRUE. Proceeding.

## 2. Method (reuse only; nothing in the fit/apply/scoring machinery reimplemented)

- Corpus: `hedge_trial_arms.load_corpus` (MLB, `ingame_grade_joined`) +
  `eval_gate.stacker.e4_gd_series` for the S06 leak-free e4-blend incumbent. Denominator
  asserted equal to the S06-blessed **47,104 ticks / 158 games** before any scoring
  (`scripts/platformkit/ingame/s88_phase_recal.py:build_records`, hard assert).
- Bucket = `phase|margin` (`state_bucket_benchmark.phase_bucket` / `margin_bucket`),
  same definition `bucket_recalibration.py` uses -- the exact granularity the row's
  `late|leading_big` claim is stated at.
- **Fix applied (the only new logic in this module):** OUTER expanding
  GAME-FIRST-DATE walk-forward (mirrors `stacker.outer_walk_forward`). At each outer
  step the two `bucket_recalibration.SPECS` (`phase_platt`, `phase_platt_margin`) are
  fit on an INNER holdout carved from the OUTER-TRAIN dates only (last 20% of
  outer-train dates), scored there, and the winner is refit on the FULL outer-train
  before it ever sees the held-out date -- the winner is never selected on the fold
  it is scored on. `spec_choice_counts` = `{phase_platt: 4, phase_platt_margin: 6}`
  (both specs actually win folds -- not a degenerate always-same-spec selector).
- Scoring: `bucket_recalibration._per_game_delta` + `state_bucket_benchmark.
  _cluster_bootstrap_ci` (2,000-resample game-clustered bootstrap, unchanged from the
  house implementation) vs incumbent AND vs market, restricted to S87
  `tick_informative.flag_ticks` **informative** ticks (`market_col=market_prob,
  model_col=model_prob`). `n_eff` via `ingame.gap_effective_n.effective_sample_size`.
- No charge: `edge_claimed=False`, no ledger row, no prereg SHA, no BH family bar.

## 3. Per-phase table (informative ticks only; n = all eval ticks in the bucket after burn-in)

n_burn_in_dates=3, n_eval_ticks=33,920 of 47,104, n_informative_ticks=11,087 (32.7 pct).

| bucket | n | n_informative | n_games_inf | n_eff | Brier incumbent | Brier recal | Brier market | delta vs incumbent (CI95) | verdict vs incumbent | verdict vs market |
|---|---|---|---|---|---|---|---|---|---|---|
| early\|leading | 2281 | 964 | 83 | 83.7 | 0.223260 | 0.226049 | 0.222258 | +0.000898 [-0.0164, 0.0178] | NO_CHANGE | NO_CHANGE |
| early\|leading_big | 643 | 207 | 26 | 27.8 | 0.092675 | 0.106277 | 0.084609 | +0.001870 [-0.0202, 0.0267] | NO_CHANGE | NO_CHANGE |
| early\|tied | 6970 | 2027 | 126 | 126.1 | 0.245914 | 0.247616 | 0.240514 | -0.001826 [-0.0148, 0.0116] | NO_CHANGE | NO_CHANGE |
| early\|trailing | 2228 | 873 | 84 | 85.0 | 0.204022 | 0.201695 | 0.196666 | -0.009335 [-0.0223, 0.0036] | NO_CHANGE | NO_CHANGE |
| early\|trailing_big | 1243 | 363 | 33 | 35.7 | 0.148601 | 0.147503 | 0.142096 | -0.005454 [-0.0227, 0.0098] | NO_CHANGE | NO_CHANGE |
| late\|leading | 1729 | 660 | 54 | 59.6 | 0.181619 | 0.174400 | 0.172578 | +0.005426 [-0.0116, 0.0232] | NO_CHANGE | NO_CHANGE |
| **late\|leading_big** | 2084 | 349 | 50 | 51.1 | 0.037098 | 0.028937 | 0.030465 | **+0.031643 [0.0088, 0.0572]** | **IMPROVED** | NO_CHANGE |
| late\|tied | 1028 | 448 | 41 | 41.2 | 0.237475 | 0.263650 | 0.212079 | -0.012826 [-0.0375, 0.0133] | NO_CHANGE | NO_CHANGE |
| late\|trailing | 1640 | 721 | 54 | 62.3 | 0.100201 | 0.101502 | 0.104608 | -0.007924 [-0.0175, 0.0000] | NO_CHANGE | NO_CHANGE |
| late\|trailing_big | 2382 | 492 | 48 | 64.5 | 0.058338 | 0.064173 | 0.052865 | -0.007126 [-0.0202, 0.0045] | NO_CHANGE | NO_CHANGE |
| mid\|leading | 2930 | 1157 | 77 | 78.9 | 0.213530 | 0.214004 | 0.203061 | +0.004965 [-0.0091, 0.0207] | NO_CHANGE | MODEL_BEHIND |
| mid\|leading_big | 2111 | 538 | 42 | 46.9 | 0.050122 | 0.051921 | 0.048949 | +0.005157 [-0.0047, 0.0165] | NO_CHANGE | NO_CHANGE |
| mid\|tied | 1894 | 664 | 69 | 69.2 | 0.239524 | 0.244737 | 0.233888 | -0.007685 [-0.0241, 0.0087] | NO_CHANGE | NO_CHANGE |
| **mid\|trailing** | 2383 | 963 | 66 | 68.8 | 0.161531 | 0.157551 | 0.175560 | **-0.011964 [-0.0232, -0.0010]** | **WORSE** | NO_CHANGE |
| mid\|trailing_big | 2374 | 661 | 41 | 45.3 | 0.063736 | 0.064914 | 0.068178 | -0.007031 [-0.0156, 0.0005] | NO_CHANGE | NO_CHANGE |
| **POOLED (all buckets)** | 33920 | 11087 | 127 | 179.8 | 0.174603 | 0.176080 | 0.170853 | -0.002890 [-0.0114, 0.0052] | NO_CHANGE | NO_CHANGE |

## 4. Honest verdict per phase (calibration only)

- **late\|leading_big: IMPROVED**, CI excludes 0 (+0.0088 to +0.0572), clears the FIRST clause of the L6
  memo's bar (>= +0.004 on late|leading_big) but NOT its second clause
  (INGAME_GAP_PREMISES_2026-09-03.md:717: no phase degraded by more than 0.001) --
  mid|trailing at -0.0120 fails it, so the L6 bar is NOT cleared as a whole. This is the ONE bucket the row's cited artifact also
  flagged -- it reproduces here OOF, with the spec chosen inside the folds and on a
  different (S06, informative-only) partition. Confirms the row's central claim.
- **mid\|trailing: WORSE**, CI excludes 0 in the negative direction (-0.0232 to
  -0.0010) -- a real per-game-clustered degradation. Note the discrepancy: the
  UNWEIGHTED pooled Brier for this bucket looks slightly BETTER for recal (0.157551 <
  0.161531), but the GAME-CLUSTERED per-game mean delta is negative -- a few
  high-tick-count games pull the pooled number one way while most games got worse.
  This is exactly the failure mode game-clustering exists to catch; it did not appear
  in the original in-sample artifact (which reported no WORSE bucket at all).
- Every other bucket (11 of 15) and the POOLED row: **NO_CHANGE** both vs incumbent
  and vs market -- a delta whose CI includes 0 is a null result, not evidence either
  way. `mid|leading` reads NO_CHANGE vs incumbent but MODEL_BEHIND vs market (the
  market is ahead of both raw and recal there).
- No global claim: this is 15 buckets scored NO_CHANGE / IMPROVED (1) / WORSE (1) with
  no multiple-comparison correction applied (see NOT VERIFIED) -- read bucket-by-bucket,
  not as a single verdict.

## 5. NOT VERIFIED

- NBA (`probe_R12_B32*`) is untouched: no S06-equivalent leak-free partition or
  incumbent exists for it, so it stays an unreviewed cache artifact, exactly as the
  gapfinder memo already said. Not addressed by this module.
- The isotonic in-game path (`ingame_blend_recal.py`, per-time-bucket) is a different
  lineage from the Platt path scored here (`bucket_recalibration.py`) and is untouched.
- No multiple-comparison (BH/family) correction applied across the 15 buckets scored
  here -- consistent with the row's "no charge", but the per-bucket verdicts above are
  therefore each a single uncorrected test, not a family-adjusted claim.
- Single window/partition (S06, 2026-06-28..07-12) and single corpus (MLB); no second
  corpus or out-of-window replication attempted (Q5 not applicable -- no charge).
- Nothing is wired or persisted: no params file written, no serve-side change, no flag
  flipped. `mid|trailing`'s WORSE finding is a new, uncharged signal for any future
  lane that would wire per-phase recal live -- it should not ship without excluding or
  re-validating that bucket.
- `data/cache/probe_R12_B32_recal_winprob_endQ{1,2,3}.json` retracted-lineage caveat
  from `.claude/rules/no-edge-claims.md` still applies; nothing from it is quoted here.

## 6. Reproduction

```
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.ingame.s88_phase_recal
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_s88_phase_recal.py -q
```

Artifacts: `docs/evidence/harness/s88_phase_recal_2026-09-04.json` (summary + per-phase
table + fold_choices), `docs/evidence/harness/s88_phase_recal_2026-09-04.csv` (33,920
per-tick rows: game_id, ts, phase_bucket, is_informative, outcome, model_prob,
recal_prob, market_prob -- the archived paired-loss series, Q9).
