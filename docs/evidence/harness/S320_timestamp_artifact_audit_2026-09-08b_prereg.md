# S320 timestamp artifact audit preregistration (VERSION b)

Row: S320. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q. Amendment: S320_spec.md
VERSION 2026-09-08b (orchestrator amendment after attempt 1 stopped PARTIAL, 828ddf4c7 in a16: the sealed
"100 states, >=5 per non-empty stratum" rule was infeasible against 63 non-empty strata).

Scope: this prereg seals the VERSION b selection rule and prints the full strata census computed from the
parquet columns only. No audit, replay, comparison, metric, or model fit has run in this lane.

Input: data/cache/inplay_odds/nba_checkpoints_full.parquet. The finisher records its byte size and SHA-256
before use.

## Unchanged from the attempt-1 prereg (docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08_prereg.md)

- Seed: 32020260908.
- Population: all input ticks.
- Strata: exact period x absolute-margin bucket (0-3, 4-9, 10+) x clock bucket (>300s, 60-300s, <60s, ==0s).
- A state is identified by (game_id, state_ts), where state_ts is the integer ts rendered as UTC ISO-8601.
- Checks for every sealed pair: availability of each null feature (market_prob and game_date) at or before
  prediction time; status using the S309 terminal mask (period >= 4 and game_clock_s == 0); target polarity
  using side and venue evidence with paired sides merged; duplicate (game_id, state_ts) keys; settlement only
  after the final tick. Missing evidence is NOT VERIFIED, not accepted. If received_at is absent, availability
  is recorded as NOT_VERIFIED (tick-order-only), never ACCEPTED.
- Replay arms: full history a, prefix history b (all records after the state deleted), delayed history c
  (only records at least 60 seconds old). Bar: max absolute(b-a) == 0; every nonzero c-a must name a record
  in the 60-second delay window, else it is a violation.
- Sign convention: improvement equals baseline loss minus candidate loss; positive means candidate better.
  This preparation and this row make no comparison/gain claim.

## Amended (VERSION b) selection rule

Sort each non-empty stratum by SHA-256(seed + "|" + game_id + "|" + state_ts) (state_ts, the ISO-8601
rendering used as the state identity -- not the raw integer ts -- so the rank key matches the state identity
exactly), take the first 5 unique (game_id, state_ts) pairs; if a stratum has fewer than 5 eligible ticks,
take all of them and say so. No global 100-pair cap, no round-robin backfill, no >20-stratum stop. Total
sealed n = sum over non-empty strata of min(5, n_eligible).

## Full strata table (stratum, n eligible, n drawn) -- computed from the parquet columns only, no audit yet

63 non-empty strata; n_eligible ranges 3 (`p5_m10_plus_c60_300`) to 133026 (`p4_m10_plus_ceq_0`); every
stratum but `p5_m10_plus_c60_300` (3 eligible, draws 3) has >=5 eligible and draws exactly 5. Sealed total
n = 313.

| stratum | n_eligible | n_drawn |
|---|---:|---:|
| p1_m0_3_c60_300 | 5644 | 5 |
| p1_m0_3_ceq_0 | 907 | 5 |
| p1_m0_3_cgt_300 | 12255 | 5 |
| p1_m0_3_clt_60 | 1092 | 5 |
| p1_m10_plus_c60_300 | 2895 | 5 |
| p1_m10_plus_ceq_0 | 788 | 5 |
| p1_m10_plus_cgt_300 | 1517 | 5 |
| p1_m10_plus_clt_60 | 861 | 5 |
| p1_m4_9_c60_300 | 6798 | 5 |
| p1_m4_9_ceq_0 | 1127 | 5 |
| p1_m4_9_cgt_300 | 9141 | 5 |
| p1_m4_9_clt_60 | 1403 | 5 |
| p2_m0_3_c60_300 | 3844 | 5 |
| p2_m0_3_ceq_0 | 4693 | 5 |
| p2_m0_3_cgt_300 | 8103 | 5 |
| p2_m0_3_clt_60 | 886 | 5 |
| p2_m10_plus_c60_300 | 6025 | 5 |
| p2_m10_plus_ceq_0 | 8812 | 5 |
| p2_m10_plus_cgt_300 | 9090 | 5 |
| p2_m10_plus_clt_60 | 1438 | 5 |
| p2_m4_9_c60_300 | 5667 | 5 |
| p2_m4_9_ceq_0 | 7688 | 5 |
| p2_m4_9_cgt_300 | 11217 | 5 |
| p2_m4_9_clt_60 | 1362 | 5 |
| p3_m0_3_c60_300 | 3123 | 5 |
| p3_m0_3_ceq_0 | 562 | 5 |
| p3_m0_3_cgt_300 | 6354 | 5 |
| p3_m0_3_clt_60 | 693 | 5 |
| p3_m10_plus_c60_300 | 7891 | 5 |
| p3_m10_plus_ceq_0 | 1544 | 5 |
| p3_m10_plus_cgt_300 | 13491 | 5 |
| p3_m10_plus_clt_60 | 1841 | 5 |
| p3_m4_9_c60_300 | 5019 | 5 |
| p3_m4_9_ceq_0 | 850 | 5 |
| p3_m4_9_cgt_300 | 10098 | 5 |
| p3_m4_9_clt_60 | 1179 | 5 |
| p4_m0_3_c60_300 | 3317 | 5 |
| p4_m0_3_ceq_0 | 31090 | 5 |
| p4_m0_3_cgt_300 | 5420 | 5 |
| p4_m0_3_clt_60 | 2812 | 5 |
| p4_m10_plus_c60_300 | 8533 | 5 |
| p4_m10_plus_ceq_0 | 133026 | 5 |
| p4_m10_plus_cgt_300 | 16009 | 5 |
| p4_m10_plus_clt_60 | 1770 | 5 |
| p4_m4_9_c60_300 | 4672 | 5 |
| p4_m4_9_ceq_0 | 66831 | 5 |
| p4_m4_9_cgt_300 | 8713 | 5 |
| p4_m4_9_clt_60 | 2393 | 5 |
| p5_m0_3_c60_300 | 556 | 5 |
| p5_m0_3_ceq_0 | 5294 | 5 |
| p5_m0_3_clt_60 | 418 | 5 |
| p5_m10_plus_c60_300 | 3 | 3 |
| p5_m10_plus_ceq_0 | 288 | 5 |
| p5_m10_plus_clt_60 | 5 | 5 |
| p5_m4_9_c60_300 | 238 | 5 |
| p5_m4_9_ceq_0 | 6179 | 5 |
| p5_m4_9_clt_60 | 171 | 5 |
| p6_m0_3_c60_300 | 71 | 5 |
| p6_m0_3_ceq_0 | 285 | 5 |
| p6_m0_3_clt_60 | 21 | 5 |
| p6_m4_9_c60_300 | 16 | 5 |
| p6_m4_9_ceq_0 | 1190 | 5 |
| p6_m4_9_clt_60 | 30 | 5 |

## Recalibrated null N and M0 (VERSION b, sealed here; attempt 1 never reached this step)

N: one FROZEN train-only logistic recalibration of logit(market_prob) -> outcome_home_win, one feature,
fit exactly once on tick rows from games with game_date <= (median game_date - 1 day symmetric embargo);
the frozen intercept/slope are then applied unchanged to whichever market_prob value is visible under each
replay arm (full / prefix / delayed) -- the model itself never varies, only the visible input does. This is
the train-only null the WHY section calls for; it is not re-fit per state or per arm ("cached predictions
only: no new model is fit" per state). M0: the latest available raw market_prob at or before the arm's
cutoff, no recalibration. Both are evaluated only through the sealed replay procedure above; no scored
comparison, walk-forward CI, or gain claim is made by this row (paired game CIs remain descriptive only).

## replay.csv schema (sealed; standardises the header names attempt 1's writer used, which the verify pass
flagged as mismatched with this schema)

state_id, game_id, state_ts, stratum, model, p_full, p_truncated, p_delayed, delta_b, delta_c,
records_in_window (plus verdict, additive).

## Bar, verdict vocabulary (unchanged)

Bar: 0 accepted future, terminal, or wrong-target states among the sealed n; 0 prefix (delta_b) prediction
changes; every delayed (delta_c) change traced to a record in the 60-second window; all tests pass; 0 landed
files edited. Verdict vocabulary: CLEAN if the bar holds; VIOLATION with the list (blocks S321+ scoring
until the named fix lands); PARTIAL with the check that could not run and why. REJECT / NULL / BEHIND are
successes, not failures.

Input: tabular parquet; resolution not applicable.

SEAL sha256 a735f99d397d17d62b53f9ae29d5193147443e300e8f63c1db43796611ed88b8
