# S688 cloud result -- 2026-09-30 (one-off desk-row-S688, Opus, Ubuntu cloud clone)

Row: S688 (evaluation: game-level Diebold-Mariano with the Harvey-Leybourne-Newbold correction, CORP
isotonic reliability, bias-corrected Brier decomposition beside the naive one). Row text:
docs/evidence/harness/QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; override section 3a.
Branch: `cloud/S688-2026-09-30` from origin/trunk 89218a73. Spec:
docs/evidence/harness/S688_spec_2026-09-30.md (body + AMENDMENT 1). Report-only: no sealed verdict,
PREREG, seal-pinned file or existing file changed. The register and DESK_STATE.md were NOT edited on
this branch. Calibration language only.

Codex is not available in this box. Every independent role below was a separate Opus sub-agent
that did not write the code. They were given read-only instructions and worked on `git archive`
exports.

## Verdicts

| Tier | Agent | Verdict |
|---|---|---|
| Pre-build critique (astra) | independent Opus sub-agent | REVISE, 14 items; all folded as AMENDMENT 1 |
| CONTRACT (A, B1-B10, Q1-Q9 + spec) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS |
| ADVERSARIAL (closed form, clustered null, mutants, boundary probes) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS |

The corrections below were applied without re-verification. They are a spec wording change, this
memo, and additions to the tests only; no module line changed.
- Q6 (both tiers): the spec's premise printed the dm_test G=30 null share as a bare decimal whose
  string matches a retracted figure. It is now written as "11.9 pct" (commit ee272cb3). It was an
  unrelated rejection share and was never a re-print.
- A7 (both tiers): this memo did not exist when the tiers verified. It exists now.
- ADVERSARIAL 6: mutants M11 (bootstrap rows instead of games in the CLI report), M15 (the h > T-1
  check removed) and M17 (the corp non-finite check removed) survived. C9 and C10 gained
  assertions, and each of these three mutants now turns the file red: 1 failed each, re-run by the
  builder.

## Files (all new, <= 300 lines, ASCII)

- `scripts/platformkit/eval_gate/paired_tests.py` (205 lines):
  - `game_means`
  - `dm_hln(series, h)`: textbook DM with a rectangular window and the HLN factor, t(T-1) from scipy.stats.t.
  - `game_level_dm`: h fixed at 1; the estimand is the game-weighted mean of loss_ref - loss_cand.
  - `game_bootstrap_ci`: resamples games, B=2000, seed 688, percentile interval.
  - `compare_to_bootstrap`: sign agreement, and width_gap_pct = |w_boot - w_hln| / w_hln * 100, flagged above 25.
  - A CLI that writes strict JSON.
- `scripts/platformkit/eval_gate/reliability_corp.py` (133 lines):
  - in-house PAV with ties pooled;
  - CORP MCB / DSC / UNC;
  - the Ferro-Fricker 2012 bias-corrected REL / RES / UNC beside `calib_decomp.decompose`, which is imported read-only.
- `scripts/platformkit/eval_gate/test_paired_tests.py` (275 lines, 11 tests, cases C1-C10).
  - On trunk every case fails, because the modules do not exist there.

## Headline numbers

All three tiers reproduced these with their own scripts.

**C1 closed forms, x = [1..6].** These are exact.

| h | Statistic | Value |
|---|---|---|
| 1 | HLN | sqrt(21) |
| 2 | DM | 21/sqrt(35) |
| 2 | HLN | sqrt(7) |

The adversarial tier added its own closed forms:
- x = [0,0,0,4]: h=1 gives HLN = 1; h=2 gives HLN = sqrt(0.6).
- x = [1..6] at h=3: V = 37/36.
- 500 random vectors against scipy ttest_1samp: maximum relative error 3.6e-16.

**Simulated nulls.** Two-sided test at 0.05, 2,000 draws per cell, generator per spec A1.7, seed
20260930 (share of rejections):

| G | DGP | game-level HLN (S688) | eval_gate/dm_test (state-weighted CR1) |
|---|---|---|---|
| 8 | equal sizes | 0.0430 | 0.0630 |
| 15 | equal sizes (bar C3: [0.035, 0.065]) | 0.0515 | 0.0690 |
| 30 | equal sizes | 0.0440 | 0.0520 |
| 8 | size-correlated | 0.0265 | 0.4430 |
| 15 | size-correlated (bar C4: <= 0.065) | 0.0200 | 0.2475 |
| 30 | size-correlated | 0.0350 | 0.1255 |

The adversarial tier ran its own generator with seed 424242 and G=15:

| DGP | game-level | dm_test | naive iid DM |
|---|---|---|---|
| random effect | 0.0485 | 0.0605 | 0.8830 |
| AR(1) rho 0.8 within game + t3 game effects | 0.0445 | 0.0535 | 0.8930 |
| size-correlated | 0.0290 | 0.2975 | 0.9345 |

The G=8 and G=30 cells are printed without bars (A1.9).

**What the null shares mean.** The game-level test is near nominal when game sizes are similar. It
is CONSERVATIVE, at about 0.02-0.03, under the size-correlated null, where a few long games carry
most of the variance. Under that same null the existing state-weighted dm_test rejects 12-44 pct of
the time. The two tests target different estimands: S688 weights every game equally.

**Brier decomposition (C7).** Over 2,000 perfectly calibrated draws (n=300, 10 bins, seed 6881):

| Decomposition | REL mean |
|---|---|
| naive (`calib_decomp.decompose`, asserted identical to 1e-12) | 0.005487 |
| bias-corrected | -0.000101 |

The Ferro-Fricker values on the two-bin fixture match the tier's hand computation:

| Quantity | Value |
|---|---|
| c | 41/2070 |
| REL_bc | 0.0196527 |
| RES_bc | 0.0165917 |
| UNC_bc | 30*0.25/29 |

**Mutation.**
- The five spec MUTATION lines are killed.
- The adversarial tier ran 25 mutants: 19 killed and 6 survived. M8 (PAV with a strict >) is
  equivalent, because blocks with equal means give an identical fit; this was checked against
  sklearn. M11, M15 and M17 are now killed (see Corrections). M24 (the JSON null-ing removed) makes
  the CLI raise loudly rather than print a bogus report. M25 (games sorted instead of kept in
  first-appearance order) does not change any h=1 statistic.

## Tests (one file per process)

| Command | Result |
|---|---|
| `python3 -m pytest scripts/platformkit/eval_gate/test_paired_tests.py -q -s` | 11 passed (builder, after the corrections; both tiers ran 11 passed on 7c915522) |
| `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q` | 1 passed (CONTRACT tier; also on base) |
| `python3 -m pytest scripts/platformkit/eval_gate/test_walkforward.py -q` | 8 passed (CONTRACT tier; also on base) |

## NOT VERIFIED

- **Slate clause 3 is not claimed by this row.** That clause requires that, on the existing
  Model 2.0 probe outputs, the sign agrees with the bootstrap and the widths differ by under 25 pct
  or the gap is printed. Those per-game outputs live only on the laptop; the clone has no data/.
  A laptop session can run
  `python -m scripts.platformkit.eval_gate.paired_tests --csv <game_id,loss_ref,loss_cand>`
  on each probe and record `compare.sign_agree` and `compare.width_gap_pct`.
- The Windows / Py3.10 run of the test file has not been done (cloud-lander re-test).
- Nothing is wired into run_gate or into any read-out, by design.

PORTABLE: yes (the code and its tests); landing is by a laptop session.

## NEW GAP candidates (ids are not allocated here)

- The float-residue guard (A1.2) labels a series with |DM| above about 1e6*sqrt(T) as
  NONPOSITIVE_VARIANCE (for example [1e8+1, 1e8+2, 1e8+3]). No wrong number is emitted, and loss
  differentials never reach that range.
- Since round 5, a truly empty CSV (no header) raises ValueError. A valid header-only CSV
  exits 0 with status INSUFFICIENT and has no scored rows.
- The API treats game ids of mixed types (1, 1.0, True) as one game under Python equality. The CLI
  is unaffected, because it reads every id as a string.
- dm_hln at T=1 reports mean = null, although the mean can be computed. This is cosmetic.
- The C8 flag case uses a synthetic bootstrap dict. A real heavy-tailed resample that exceeds
  25 pct would be a stronger check.
