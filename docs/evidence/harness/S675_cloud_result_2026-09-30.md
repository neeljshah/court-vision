# S675 cloud result (2026-09-30) -- multiplicity haircut + trial-count table

Row S675 (QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; section 3a one-off override). Branch
cloud/S675-2026-09-30 from trunk 89218a73. Cloud box: Ubuntu, Python 3.11.15, numpy 2.2.6,
scipy 1.15.1, statsmodels 0.14.6 (installed in the box for this run only: family_bars.py imports it;
no pin added). Report-only, calibration language only. PORTABLE: yes (code and construct tests);
real-series use needs archived differentials the clone lacks.

## Verdicts

| Tier | Who | Verdict |
|---|---|---|
| Pre-build critique | independent Opus sub-agent (astra role) | REVISE, 11 items, all folded as spec AMENDMENT 1 before any acceptance run |
| CONTRACT (A/B/Q + spec + AMENDMENT 1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (sole correction: this memo) |
| ADVERSARIAL (200-seed null, 12 mutants, probes) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (C1 this memo; C2 mutant m9a green) |

Codex is not available in the cloud box, so every critique/verifier role was a separate Opus
sub-agent (Agent tool), none of which wrote the code. Corrections applied in the follow-up commit:
C1 this memo; C2 a mixed-UTC-offset k_at_launch case added to the test (m9a, string compare, now
turns it red: 1 failed / 12 passed on the mutant copy); fixture source sha now checked in full.
No re-verification round was needed (no REJECT).

## Files (new only)

- scripts/platformkit/eval_gate/multiplicity_haircut.py (194 lines): load_paired_series, holm,
  haircut (Holm + Romano-Wolf via romano_wolf.py + Hansen SPA line via spa_test.py; label BETTER iff
  all three p <= 0.05; NOT_EVALUABLE arms get no p and consume no K; sealed_verdict passed through),
  deflate (sharpe_like only; loss metrics NOT_APPLICABLE), trial_count_table (per-family COUNT via
  family_bars.resolve_family, global max k_cumulative, tz-aware k_at_launch; never writes a ledger).
- scripts/platformkit/eval_gate/multiplicity_nullcheck.py (109 lines): the frozen simulations + CLI.
- scripts/platformkit/eval_gate/test_multiplicity_haircut.py (158 lines, 13 tests).
- scripts/platformkit/eval_gate/reference_runs/s675_paired_losses_fixture.csv: header + every 30th
  data row (index 0..1770, 60 rows) of the tracked docs/evidence/S202_two_way_neff_2026-09-04/
  nba_paired_losses.csv (269,252 bytes; sha256 db28645de44429ee67d303b62b14932e1b0932ab210b042339622742178effa1).
  The loader computes loss_base - loss_recalibrated; S202's own paired_loss_differential column is
  recal - base (opposite sign) and is never read; the test asserts loader == -column to 1e-12.
- docs/evidence/harness/S675_spec_2026-09-30.md (spec + AMENDMENT 1), this memo.
Untouched (byte-identical to 89218a73, checked by both tiers): walkforward.py, romano_wolf.py,
spa_test.py, dm_test.py, deflated_metrics.py, ledger.py, family_bars.py, combo/fwer_budget.py,
spa_catalog_report.txt, retro_correction_report.txt, reference_runs/fwer_backtest_ledger.jsonl,
their tests, every PREREG*.json. No register or DESK_STATE edit on this branch.

## Acceptance (one frozen run, no re-rolls; reproduced identically by both verifier tiers)

| Metric | Bar | Result |
|---|---|---|
| (a) NOISE-60 max survivors over 200 seeds | <= 3 | 1 (total 9; raw unadjusted max 8, mean 2.9) PASS |
| (b) NULL-40 share of seeds with >= 1 BETTER | <= 0.05 | 10/200 = 0.050, CP95 [0.024, 0.090] PASS -- EXACTLY AT THE BAR |
| (c) PLANTED +0.6 sd recovered / unconditional mean | >= 0.95 / 0.6 +- 0.05 | 199/200 = 0.995 / 0.6051 PASS |
| (d)-(g) CONSTRUCT | as spec | PASS (per-file test) |

Honest reading of (b): the label's family-wise control is carried by the Holm leg (Holm alone
10/200). Romano-Wolf alone (15/200) and SPA alone (16/200, binomial tail p 0.044) are liberal at
80 games and 199 bootstrap draws. The triple AND is an intersection of level-alpha tests, so it is
no worse than Holm, but it is not better either at this n. Power line (report-only): +0.35 sd
recovered 106/200 vs analytic Holm first-step 0.507.

Null-check JSON (python3 -m scripts.platformkit.eval_gate.multiplicity_nullcheck, 72 s):

```
{
 "a_noise60": {
  "bar_max": 3,
  "max_survivors": 1,
  "mean_survivors": 0.045,
  "raw_unadjusted_max": 8,
  "raw_unadjusted_mean": 2.9,
  "seeds_with_any": {
   "count": 9,
   "cp95": [
    0.02078,
    0.083703
   ],
   "n": 200,
   "share": 0.045,
   "tail_p_bin_0.05": 0.6729755365865497
  },
  "total_survivors": 9
 },
 "b_null40": {
  "bar_share": 0.05,
  "count": 10,
  "cp95": [
   0.024234,
   0.090028
  ],
  "n": 200,
  "share": 0.05,
  "tail_p_bin_0.05": 0.5452901913191844
 },
 "c_planted": {
  "bar_share": 0.95,
  "bar_tol": 0.05,
  "better": {
   "count": 199,
   "cp95": [
    0.972458,
    0.999873
   ],
   "n": 200,
   "share": 0.995,
   "tail_p_bin_0.05": 2.3653681071150463e-257
  },
  "mean_estimate_all_seeds": 0.6050763764891276,
  "shift": 0.6
 },
 "report_only_components": {
  "noise60": {
   "holm_any": {
    "count": 9,
    "cp95": [
     0.02078,
     0.083703
    ],
    "n": 200,
    "share": 0.045,
    "tail_p_bin_0.05": 0.6729755365865497
   },
   "rw_any": {
    "count": 12,
    "cp95": [
     0.031384,
     0.102462
    ],
    "n": 200,
    "share": 0.06,
    "tail_p_bin_0.05": 0.30024429664578123
   },
   "spa_any": {
    "count": 13,
    "cp95": [
     0.035061,
     0.108587
    ],
    "n": 200,
    "share": 0.065,
    "tail_p_bin_0.05": 0.20351565401154334
   }
  },
  "null40": {
   "holm_any": {
    "count": 10,
    "cp95": [
     0.024234,
     0.090028
    ],
    "n": 200,
    "share": 0.05,
    "tail_p_bin_0.05": 0.5452901913191844
   },
   "rw_any": {
    "count": 15,
    "cp95": [
     0.042583,
     0.120684
    ],
    "n": 200,
    "share": 0.075,
    "tail_p_bin_0.05": 0.07813441567325637
   },
   "spa_any": {
    "count": 16,
    "cp95": [
     0.046418,
     0.126665
    ],
    "n": 200,
    "share": 0.08,
    "tail_p_bin_0.05": 0.04435562916706124
   }
  }
 },
 "report_only_power": {
  "analytic_holm_first_step_power": 0.5066855315405969,
  "better": {
   "count": 106,
   "cp95": [
    0.458331,
    0.600767
   ],
   "n": 200,
   "share": 0.53,
   "tail_p_bin_0.05": 6.585680784566191e-82
  },
  "shift": 0.35
 },
 "settings": {
  "alpha": 0.05,
  "mean_block_length": 5.0,
  "n_bootstrap": 199,
  "n_games": 80,
  "n_seeds": 200
 },
 "verdict": {
  "a_pass": true,
  "acceptance_run": true,
  "b_pass": true,
  "c_pass": true
 }
}
```

## Commands (one test file per process)

- python3 -m pytest scripts/platformkit/eval_gate/test_multiplicity_haircut.py -q -> 13 passed (builder,
  after C2); 13 passed (CONTRACT tier, at 2f150071); 13 passed (ADVERSARIAL baseline on a copy).
- python3 -m scripts.platformkit.eval_gate.multiplicity_nullcheck -> JSON above; builder, CONTRACT and
  ADVERSARIAL runs identical. (Spec line 33's "multiplicity_haircut --null-check" is superseded by A1.10.)
- Mutants (ADVERSARIAL, on a scratch copy): m1-m8, m9b, m10 RED; m9a GREEN at 2f150071, RED after C2.

## NOT VERIFIED

- Any run on real archived per-candidate paired-loss series (the clone has no data/; only the S202
  CSVs are tracked). The 60 catalog classes still have no archived differentials: their SPA line
  stays NOT_EVALUABLE; this row does not change spa_catalog_report.txt.
- The real P1-P6 / R1-R3 families, strata and horizons; the live FWER ledger
  data/cache/eval_gate/backtest_fwer.jsonl (local-only); the fixture is a single-arm K=1 family.
- S686 external cross-check of the SPA / Romano-Wolf p-values against arch.
- Windows / Python 3.10 re-run of the per-file test (laptop lander).
- statsmodels version parity with the laptop (only resolve_family needs it, lazily).

## NEW GAPs (from the verifier tiers; not fixed here)

- RW-only and SPA-only null rejection is liberal at 80 games / B 199 (15/200, 16/200); the label rests on Holm.
- A non-finite diff in one arm raises and aborts the whole family report instead of marking that arm.
- _game_means marks length-mismatched or <2-game arms NOT_EVALUABLE silently rather than raising.
- No minimum-games floor on RW/SPA inputs (n_games 2: RW p 0.01 vs raw t p 0.10; the AND still blocks).
- trial_count_table gives k_at_launch for the whole ledger only (not per family) and skips rows with no at.
