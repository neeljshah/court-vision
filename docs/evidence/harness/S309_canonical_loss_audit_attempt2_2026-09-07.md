# S309 canonical loss audit -- attempt 2

## Verdict: SCREEN ONLY -- the candidate is BEHIND on both designs, far below the frozen bar

Attempt 1 (candidate `e6384a12f`) was REJECTED. This memo reports attempt 2, scored once on the
pod on 2026-09-07 from the sealed attempt-2 preregistration. No promotion, no feature flag, no
register write, no shared-ledger write, no source-store write. Nothing is charged.

## What attempt 1 was rejected for, and what changed

| finding | attempt 1 | attempt 2 |
|---|---|---|
| B9 / Q4 CPCV arm | `loss_cpcv_*` assigned from `loss_forward_*`; design delta trivially 0 | both arms are real out-of-fold series from the shared evaluators; they differ on 215,072 of 465,249 ticks |
| Q4 shared evaluators | hashed but never called | `walk_forward` and `cpcv_evaluate` are called; 1,593 forward records and 11,151 CPCV records |
| Q4 symmetric embargo | recorded as `embargo_days: 1`, not enforced | `cpcv_evaluate(..., embargo_days=1)`: the engine's symmetric calendar-day window on BOTH sides of every test block |
| B2 alias | `polymarket_probability_replay_max_abs_error` renamed without an alias | the old key is restored with its original Polymarket-only meaning, beside the new key |
| ACCEPTANCE S293 order | S293 was not an ancestor | S293 `4a41c436e3650cfad1517d1987a27d09d5a00122` is an ancestor of this branch |
| ACCEPTANCE tests | variable-cluster and future-label tests absent | both added; counts below |
| ACCEPTANCE secondary scores | absent | the full CPCV table set is published as NAMED SECONDARY |
| memo hash defect | the route emitted a memo the lane then rewrote, so its recorded hash was stale | the route emits NO memo; this memo is lane-authored and no artifact claims a hash of it |

## Preregistration and order (Q1)

Preregistration `docs/evidence/harness/S309_canonical_loss_audit_2026-09-07b_preregistration.md`,
seal `cd9e157abc95c2e699228069bfa40292621fc26f6e48fa0352b3d992e5f69cad`.
Recomputed over the committed bytes above the seal line after normalizing CRLF to LF: MATCH.
It was committed ALONE in `bf7a14de8` ("S309 attempt 2: preregistration sealed (Q1)"), before the
route/test commit `a9cf9cdfb` and before every metric below. The attempt-1 preregistration and
all attempt-1 artifacts are untouched; attempt 2 wrote only new `2026-09-07b` filenames.

## Sign convention

Every improvement number is `baseline loss - candidate loss`: POSITIVE means the candidate is
better, NEGATIVE means the candidate is worse. The candidate is the S272 low/high-tail isotonic
recalibration; the baseline is the S272 logistic recalibration. The design delta is
`forward-only loss - CPCV loss`: POSITIVE means the CPCV loss is lower. The frozen comparison bar
is +0.004 and was not changed.

## Replay of the historical artifacts

| replay | value | bar | result |
|---|---:|---|---|
| S272 historical baseline Brier | 0.073316945557 | -- | reproduced |
| S272 historical candidate Brier | 0.073353613895 | -- | reproduced |
| S272 baseline replay error | 0.0 | <= 1e-12 | PASS |
| S272 candidate replay error | 0.0 | <= 1e-12 | PASS |
| S280 tick-weighted minus equal-game delta | -0.000130557034 | -- | matches the spec premise 0.000130557 |

Historical replay denominator 465,249 ticks / 1,593 games; S280 replay denominator 8,828 ticks /
40 games. The S272 replay error is exactly 0.0, so the absorbed S299 precondition is satisfied and
the design comparison was allowed to run.

## Regenerated forward-only scoring (headline, deployment design)

Denominator: all 465,249 checkpoint ticks in 1,593 game clusters. No tick was dropped and no
outcome-based exclusion was applied. `positive_clock` (194,095) and `zero_clock` (271,154)
partition the 465,249 exactly. `unknown_status` is the terminal-like table, `period >= 4 and
game_clock_s == 0`: 244,183 ticks, matching the spec premise; its status is UNKNOWN because
receipt and final timestamps do not exist in these stores.

| table | ticks | games | baseline Brier | candidate Brier | improvement | 95 pct CI | candidate MDE |
|---|---:|---:|---:|---:|---:|---|---:|
| all | 465249 | 1593 | 0.073906391099 | 0.073984841253 | -0.000078450154 | [-0.000136780928, -0.000028628302] | 0.000053709961 |
| positive_clock | 194095 | 1593 | 0.152767880040 | 0.152914344242 | -0.000146464203 | [-0.000260383669, -0.000051682426] | 0.000105565618 |
| zero_clock | 271154 | 1593 | 0.017456474462 | 0.017486239416 | -0.000029764954 | [-0.000055830571, -0.000007305431] | 0.000024428895 |
| unknown_status | 244183 | 1592 | 0.000850316745 | 0.000846393758 | 0.000003922986 | [-0.000000906755, 0.000010221193] | 0.000005685285 |

Reading: on all ticks the tail-isotonic candidate is WORSE than the logistic baseline by
0.000078450154 Brier, and the interval excludes zero, so the direction is resolved. The magnitude
is roughly two orders below the frozen +0.004 bar; the bar is not met in either direction. The
same negative direction holds on both clock partitions. On the terminal-like table the interval
spans zero, so that table is a null. Ratio bootstrap on game sums and counts, seed 901, 10,000
replicates.

These numbers differ in the last digits from attempt 1 (which reported -0.000078443437 on the all
table) because the forward fits are now produced by the shared evaluator: states are ordered by
game start rather than by calendar date, the shared 48-hour same-team purge and 3-day same-matchup
embargo now apply, and a train game must be SETTLED strictly before the test state timestamp. The
direction, the magnitude and the verdict are unchanged.

## CPCV secondary scoring (labelled robustness companion)

| table | ticks | games | baseline Brier | candidate Brier | improvement | 95 pct CI | candidate MDE |
|---|---:|---:|---:|---:|---:|---|---:|
| all | 465249 | 1593 | 0.073423403292 | 0.073454986628 | -0.000031583337 | [-0.000059550789, -0.000005652876] | 0.000027119933 |
| positive_clock | 194095 | 1593 | 0.151788443540 | 0.151843624043 | -0.000055180502 | [-0.000109920177, -0.000006032116] | 0.000052250331 |
| zero_clock | 271154 | 1593 | 0.017328850059 | 0.017343542287 | -0.000014692227 | [-0.000028092050, -0.000002990586] | 0.000012510381 |
| unknown_status | 244183 | 1592 | 0.000861527540 | 0.000863918691 | -0.000002391150 | [-0.000008463056, 0.000001527381] | 0.000005144534 |

The candidate is BEHIND on the CPCV design too, on every table except the terminal-like one,
whose interval spans zero. Nothing here is a promotion and nothing is a monetary quantity.

## Named secondary diagnostics (they set no label)

| table | forward improvement | forward candidate log loss | forward candidate 10-bin ECE |
|---|---:|---:|---:|
| all | -0.000078450154 | 0.222624002 | 0.006105968 |
| positive_clock | -0.000146464203 | 0.459446166 | 0.013511882 |
| zero_clock | -0.000029764954 | 0.053104105 | 0.002721509 |
| unknown_status | 0.000003922986 | 0.003450113 | 0.001481479 |

| table | CPCV improvement | CPCV candidate log loss | CPCV candidate 10-bin ECE |
|---|---:|---:|---:|
| all | -0.000031583337 | 0.220456401 | 0.004191956 |
| positive_clock | -0.000055180502 | 0.454831515 | 0.009736413 |
| zero_clock | -0.000014692227 | 0.052688129 | 0.001777022 |
| unknown_status | -0.000002391150 | 0.003591182 | 0.001403858 |

## Design comparison (the absorbed S299 arm)

Primary design delta, forward-only minus CPCV, on candidate loss: **0.000529854625**, 95 pct CI
[-0.000034107543, 0.001139144397]. The interval INCLUDES ZERO, so **DESIGN-SENSITIVE is False**. The point
estimate says the CPCV loss is lower, which is the expected direction for a design whose train set
straddles the test block on both sides, but at this sample the preregistered primary interval
cannot separate the two designs. That is an honest null on the design question.

The two arms are NOT the same series. They differ on 215,072 of 465,249 ticks, with a maximum
absolute candidate-probability difference of 0.720733267701 and a mean absolute difference of
0.014350587816 over the differing ticks. The remaining 250,177 ticks agree EXACTLY because both
arms' tail isotonic saturates to 0.0 or 1.0 there (236,416 of those 250,177 are clock-zero ticks,
where the market is already at an extreme). That saturation is a property of the data, not of the
code path, and it is stated here so it is not mistaken for the attempt-1 aliasing.

## Embargo and purge provenance

| property | forward-only arm | CPCV arm |
|---|---|---|
| evaluator | `scripts.platformkit.eval_gate.walkforward.walk_forward` | `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` |
| records returned | 1593 (one per game cluster) | 11151 (7 paths per cluster) |
| distinct fits | 1269 | 28 (one per path) |
| same-team purge | 48 hours (shared) | 48 hours (shared, symmetric) |
| same-matchup embargo | 3 days (shared) | 3 days (shared, symmetric) |
| calendar embargo | forward-only, none added | 1 day, SYMMETRIC on both sides of every test block |
| extra train rule | settled strictly before the test state timestamp | none: straddling is the design under test |
| strict redaction | True | True |
| S301 duplicate-state-key guard | True | True |
| train-set size range | 0 to 1592 states | 1130 to 1210 states |

CPCV design: 8 groups, 2 test groups, 28 paths, so every game is a test row on
exactly 7 paths and its CPCV probability is the mean over those paths. Per-path test-cluster
counts range from 370 to 442 games. Fold membership, fitted logistic coefficient and
intercept, tail point counts, train-set sizes and the maximum train settle timestamp are archived
per fit in the folds JSON: 1297 rows, 1269 forward and 28 CPCV. Two forward fits fall back to the
raw market probability because no settled prior data existed. Every forward fold satisfies
`max_train_settle < first_test_state_ts`, checked over all 1269 rows.

GRAIN, declared in the preregistration before scoring: the shared evaluators build each test row
train set with a per-state loop that is quadratic in the number of states, so they are driven at
game-cluster grain -- one evaluator state per game (1,593), each emitting one out-of-fold
probability for every tick of its test game. The scored series is therefore one prediction per
tick per design, `state_key` is unique over all 465,249 rows, and the tick series agrees with each
evaluator's own returned records to 2.22e-16 (bar 1e-9).

## Canonical source accounting (the absorbed S300 arm, unchanged from attempt 1)

Denominator: 8092183 moneyline rows out of 8,399,632 rows in `nba_price_series.parquet`. Every
source row is retained in the accounting artifact with all original columns plus aliases, and
carries exactly one reason.

| accounting reason | rows |
|---|---:|
| CANONICAL | 4917502 |
| EXACT_DUPLICATE_TICK | 1417673 |
| UNPARSEABLE_EVENT | 1642063 |
| COMPLEMENT_UNUSED_HOME_PRESENT | 114945 |
| total | 8092183 |

Canonical branch split: DIRECT_HOME 4896419 and COMPLEMENT_AWAY 21083.

| added bar | value | result |
|---|---:|---|
| duplicate canonical keys | 0 | PASS |
| unaccounted source rows | 0 | PASS |
| Polymarket games joined | 1593 / 1593 | PASS |
| probability replay max abs error | 0.0 (bar <= 1e-12) | PASS |
| `polymarket_probability_replay_max_abs_error` (restored alias) | 0.0 (bar <= 1e-12) | PASS |
| cross-venue overlapping games | 40 | REPORTED, not closed at limit (bar was "closed below 30") |

## Inputs

| path | rows | bytes | sha256 |
|---|---:|---:|---|
| data/cache/inplay_odds/nba_checkpoints_full.parquet | 465249 | 2829826 | 5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5 |
| data/cache/inplay_odds/nba_price_series.parquet | 8399632 | 25140428 | 3db7d0444d800cfe487ab48c4780a9283b3a621511e0b259975a4339b970bd5b |
| data/domains/basketball_nba/espn_nba_game_bridge.parquet | 1299 | 46002 | e0e0ab68d6882bf77987dca2890a1896376ffe18d8e46d11656338a7ec037f4f |

## Code identity (A11)

Route `scripts/platformkit/s309_canonical_loss_audit.py` SHA-256 `67128d59bc9cd52a947c1ed40b1a347f30936886892f146a061f88a59ac74984`; shared
`scripts/platformkit/eval_gate/walkforward.py` `c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e` and
`scripts/platformkit/eval_gate/cpcv_engine.py` `5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5`. These are the raw bytes shipped to the
pod; the preregistration records the same files under both raw and LF-normalized hashes, because
this Windows worktree holds a mix of LF and CRLF checkouts after the rebase. Neither shared file
was modified by this row.

## Test result

Per-file only, run in the worktree `C:\Users\neelj\nba-track-a15` after the rebase onto master:

| file | command | result |
|---|---|---|
| tests/platformkit/test_s309_canonical_loss_audit.py | `python -m pytest <file> -q -p no:cacheprovider` | 3 passed |
| tests/platformkit/test_s309_design_evaluators.py | `python -m pytest <file> -q -p no:cacheprovider` | 2 passed |
| tests/platformkit/test_loc_rail_scope.py | `python -m pytest <file> -q -p no:cacheprovider` | 1 passed |

Total 6 passed, 0 failed, 0 skipped. The two ADDED tests are the ones the verifier named:

1. `test_variable_cluster_sizes_keep_one_oof_record_per_tick_per_design` -- a 40-game fixture with
   unequal tick clusters (3 to 11 ticks) and unequal games per calendar day. It asserts one forward
   record per cluster, exactly 7 CPCV records per cluster, unique `state_key`, no NaN loss, record
   agreement <= 1e-9, the symmetric embargo recorded on every CPCV fold, and -- the B9 guard --
   that the two arms are NOT `np.allclose` to each other.
2. `test_a_planted_future_label_moves_no_prior_forward_loss` -- flips the outcome label of the
   chronologically last game and asserts that NO prior tick forward baseline or candidate loss
   changes by a single bit (`np.array_equal`). It also asserts the CPCV arm DOES move on the same
   plant, so the test has power: a test that saw the plant nowhere would also pass on an aliased
   route.

No LOC allowlist entry was raised: `s309_canonical_loss_audit.py` is 245 lines and the new
`s309_design_evaluators.py` is 248, both under the 300-line rail, so A12 does not apply.

## Pod run and RSS

Compute-only scratch job under `/workspace/wt/a15` via `C:/Users/neelj/bin/pod_run a15`, run
EXACTLY ONCE. The deployed tree `/workspace/nba-ai-system` was never written; `data/registry`,
`backtest_fwer.jsonl` and `hypotheses*.sqlite` never reached the pod; no pod process was stopped
or restarted.

- Job `20260907192558_275815_26020`, log
  `/workspace/wt/a15/jobs/20260907192558_275815_26020/pod_run.log`
- Log tail:
  `S309 verdict=SCREEN_ONLY all_improvement=-0.000078450154 design_delta=0.000529854625 fits=1269/28 rss_bytes=6866489344`
  followed by `POD_RUN_DONE job=20260907192558_275815_26020 rc=0`
- Process RSS reported by the route: 6866489344 bytes (6.87 GB), which is why the preregistration
  routed this to the pod rather than the laptop. Wall time about 50 minutes.
- Pod environment: Python 3.12.3, scikit-learn 1.9.0, pandas 2.3.3, numpy 2.1.2.
- One earlier pod job on this attempt was an import-only smoke test (`python -m ... --help`, job
  `20260907181322_179128_7773`, rc=0) that produced no artifact.

## Artifact hashes

| artifact | sha256 |
|---|---|
| S309_canonical_loss_audit_2026-09-07b.json | ce4a1f2bd5b92298c23a3dc684523d5b8eb6733eb68b0e4bf86f1b1dda129e96 |
| S309_canonical_loss_audit_2026-09-07b_accounting.parquet | 297586e2fa98e733d50f7abce36b95cdc488b0f3e59792cb766e55edb7b47d68 |
| S309_canonical_loss_audit_2026-09-07b_folds.json | 278181763f36b6ce1317f44dc5c70b3159c51065a6b34c799b4a6ce06d0a6b7c |
| S309_canonical_loss_audit_2026-09-07b_keys.parquet | 581c332b893b426dc13bb3a8f1f27a8a37aaf1010cb31f90ed2fc9de5b08f41d |
| S309_canonical_loss_audit_2026-09-07b_paired_losses.parquet | 6fdf85c48a72101125ca29be1fea66a4b3845953d412dacc9d4d3bfa67db78a5 |
| S309_canonical_loss_audit_2026-09-07b_preregistration.md | bbd30338c706faeec7106875bf2275b97d44817c78e0a63e0dc3f48256f8defd |

The hashes JSON does not contain its own hash, and contains no entry for this memo: the route
emits no memo, so nothing here can carry a stale hash of a rewritten file.

## NOT VERIFIED

- **The design question is a NULL, not a resolution.** The primary design interval
  [-0.000034107543, 0.001139144397] includes zero, so DESIGN-SENSITIVE is False. The point estimate favours
  the CPCV design but this run cannot separate the two designs at n = 1,593 clusters.
- **The evaluators are driven at game-cluster grain, not tick grain.** One evaluator state per
  game, not per tick, because the shared routes are quadratic per state and 465,249 states is not
  runnable through them. Each call emits one out-of-fold probability per tick of its test game and
  the tick series reproduces the evaluators' own records to 2.2e-16, but a reader who expects
  465,249 evaluator states will not find them. This was declared in the preregistration before
  scoring.
- **The forward arm extra settle rule is this row's, not the shared route's.** `walk_forward`
  orders states by game start; dropping train games not settled before the test timestamp is an
  additional restriction applied inside this row's predictor. It is strictly tighter, not looser.
- **The cross-venue arm is REPORTED, not closed.** 40 overlapping games is at or above the bar of
  30, so the preregistered "CLOSED AT LIMIT below 30 games" clause does not apply and no
  cross-venue conclusion is drawn here.
- **Terminal status is UNKNOWN.** Receipt and final timestamps do not exist in these stores, so the
  244,183 period >= 4 / clock-zero ticks are labelled UNKNOWN rather than terminal. No
  outcome-based exclusion was used to make them look clean.
- **The Kalshi ticker team order is an assumption.** The parser reads `KXNBAGAME-<date><AAAHHH>` as
  away-then-home, mirroring the Polymarket slug convention. No independent source confirms that
  order for Kalshi tickers, and 40 games is the entire Kalshi overlap, so a swap would change only
  that arm.
- **The spec EVIDENCE line still names 2026-09-04 filenames** while attempt 1 wrote `2026-09-07`
  and attempt 2 writes `2026-09-07b`. The attempt-1 verifier filed this as a NEW GAP; this lane did
  not edit the spec.
- **`/workspace/wt` on the pod is at 13.2 GB**, above the 3 GB warning threshold pod_run prints.
  This lane deleted nothing. The tracking session should be pinged, per pod_run's own message.
- **No promotion, no second corpus.** This is a screen on one corpus. Nothing here is a deployment
  decision, the +0.004 bar was neither met nor moved, and no monetary or advantage claim is made
  anywhere in this memo.
