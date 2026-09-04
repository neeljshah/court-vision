# S238 S123 conformal-band premise audit

## Verdict

FALSIFIED. This is a contract Q8 closure. The required pre-score premise that
no in-game win-probability route prints interval width beside coverage is false.
Consequently, no data store was opened, no scored comparison was run, no
preregistration was required, and no implementation or test was added.

## Machine and scope

Measured locally in `C:\Users\neelj\nba-track-a13` on 2026-09-04. The audit is
a static source measurement, so it does not use the pod or wait for a daemon.
It opens code files only and has no input video, image, or tabular-store
resolution to report.

The user scope prohibits writes to the register and ledger; neither was read
for a launch count nor written. No score was launched, so no trial required a
charge.

## Exact sources opened

| Source | Bytes | Resolution | SHA-256 |
| --- | ---: | --- | --- |
| `C:\Users\neelj\nba-track-a13\scripts\platformkit\eval_gate\s101_aci_coverage.py` | 15395 | N/A (Python source) | `4DBADC319B76A0E9C6E4EA53E3C683F242176774290917BEBEE894344C2CF93F` |
| `C:\Users\neelj\nba-track-a13\scripts\platformkit\eval_gate\s97_nba_sensor_fusion.py` | 18112 | N/A (Python source) | `D5DDCD2E003158A8266559C6817EF8410637939C132224F0DEE98D25886D7435` |
| `C:\Users\neelj\nba-track-a13\scripts\platformkit\foundry\ingame_incumbent_nba.py` | 5819 | N/A (Python source) | `476ED9FDFB714B93C5B722F8E99FB1266CDB5987A729495F12E84D2B62EA08ED` |
| `C:\Users\neelj\nba-track-a13\scripts\platformkit\eval_gate\walkforward.py` | 8207 | N/A (Python source) | `1058F981A328121802A996E8D46FF9502212A026918C723B7EBE28F49DCE0C69` |

## Premise measurement

The non-falsified portion of the premise holds: S101 defines
`ARMS = ("market", "model")` at line 54, while the S123 route exposes its
incumbent series through `apply_incumbent(rows, kind, embargo_days)`.

The width-absence portion is false in two independently inspected routes:

| Route | Measured source evidence | Result |
| --- | --- | --- |
| S101 | `grouped_coverage` emits `mean_interval_width` at line 124. `main` emits the per-band coverage row at lines 261-265 and `ALL width` at lines 266-268. | Width is printed with coverage for its STATIC in-game arm. |
| S97 | `score_cell` emits `mean_interval_width` at line 211. `main` emits `cover90 ... cover ... width ...` at lines 292-294. | Width is printed on the same per-phase coverage line. |

General width routes exist, but the S123 before-condition remains true. The
statement about every in-game route was too broad; it does not change the
incumbent-specific absence named by the S238 acceptance rule.

## Required handling

Verifier contract Q8 states that a false premise is a valid result and closes
the row without a fix. Therefore this audit makes no S238 scored claim and does
not invoke `walk_forward` or `cpcv_evaluate`; their purge and symmetric-embargo
requirements are not reached. There is no coverage table, width table, or S101
regression diff because those would be a new scored comparison after a premise
closure.

The evidence artifact is this memo only (under 50 MB). No human-gated path
change is proposed.

## Contract self-check

| Clause | Result |
| --- | --- |
| Q1 | No scored comparison; preregistration is not applicable. |
| Q2 | No trial launched; no charge is applicable. |
| Q3-Q5, Q9 | No metric or comparison was produced. |
| Q6 | Calibration-only terminology used. |
| Q7 | Reproduction replaces an eye check for an S-row; no scored construct exists after the Q8 closure. |
| Q8 | Satisfied: premise re-measured before work and reported FALSIFIED. |
| B1-B11 | No schema, data, deploy, module, or metric mutation occurred. |

## Test

Not run: the false premise closes the row before the specified additive script
and per-file test become applicable.

## ATTEMPT 2

Attempt 2 supersedes the closure conclusion above while retaining the attempt-1
source audit. It implements the requested additive report. The `e4` label maps
to S123's unchanged `market` callable kind because `apply_incumbent` accepts
`market`, `recal_null`, and `ladder_base`; `ladder_base` is passed unchanged.

### Sealed preregistration and launch

The preregistration is
`docs/evidence/harness/S238_attempt2_preregistration_2026-09-04.md`. Its seal
is `1496560415d30ba193c41bc1a701dc7804314d1c5daf33ca346fc269dfdd96b6`, the
SHA-256 of every byte above its `SEAL_SHA256` line. It was committed before the
archive score in commit `5e1c01525357af08cc41bfbcd5f26481f4b0fa42`.

The launch row was appended to `docs/evidence/RESULTS_LEDGER_SYSTEM.md` before
scoring. K read at launch was 0: the normal FWER ledger path
`data/cache/eval_gate/backtest_fwer.jsonl` is absent in this worktree, and no
data file was written.

### Before and after

| Item | Attempt 1 | Attempt 2 |
| --- | --- | --- |
| Binding S123 condition | Unreported incumbent coverage and half-width | Still true before the run; reported below for e4 and ladder_base |
| General width condition | Declared false premise | Corrected: general routes exist, but S123 remains unreported before this attempt |
| Additive evaluator | None | `scripts/platformkit/eval_gate/s238_incumbent_conformal_band.py` |
| S123 coverage/half-width cells | 0 | 24 reported cells, all at or above the fixed grouping floor |
| S101 STATIC regression | Not run | maximum absolute coverage difference 0.0, required at most 1e-9 |
| Per-file test | Absent | 2 passed in 1.44s; LOC rail 1 passed in 0.61s |

### Archive and evaluator record

The opened source was
`C:\Users\neelj\nba-track-a13\data\cache\eval_gate\s86_nba_every_tick_2026-09-03.csv`,
49,052,957 bytes, CSV resolution, SHA-256
`f0d0565af7fd051d6fc7baac63cff0098b7d495c1100d25609737e01b5fe1487`.
The specification quotes 465249 ticks / 1593 games. The archive measured
232951 ticks / 797 games, which is the count used by this attempt. The five
held-out blocks use a game-disjoint purge and a symmetric nonzero one-day
embargo. S101 constants remain 400 ticks per group, at most 50 groups, and two
minimum groups.

The complete machine-readable result is
`docs/evidence/harness/S238_conformal_band_s123_2026-09-04.json` (25,033
bytes; SHA-256 `9E1F7092F92A25435051552C39B5DF0E495E30BC34CCAAA21EAB715FA821D4B9`).
It records every fold, coverage cell, interval half-width, code identity, and
the unchanged S101 regression comparison.

### S123 STATIC coverage and half-widths

Half-width columns are mean and median interval half-width. All cells are
reported; no cell is absent because of the grouping rule.

| Arm | Nominal | Cell | Ticks | Groups | Coverage | Mean half-width | Median half-width |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| e4 | 0.90 | P1 | 18876 | 47 | 0.936170213 | 0.116806373 | 0.116843750 |
| e4 | 0.90 | P2 | 29349 | 50 | 0.940000000 | 0.120888914 | 0.130036585 |
| e4 | 0.90 | P3 | 22259 | 50 | 0.960000000 | 0.088840456 | 0.089576659 |
| e4 | 0.90 | P4 | 115035 | 50 | 0.980000000 | 0.011397909 | 0.000550817 |
| e4 | 0.90 | OT | 7116 | 17 | 0.941176471 | 0.028082383 | 0.018233781 |
| e4 | 0.90 | ALL | 192635 | 50 | 0.960000000 | 0.047973101 | 0.002703358 |
| e4 | 0.80 | P1 | 18876 | 47 | 0.851063830 | 0.091219343 | 0.091075650 |
| e4 | 0.80 | P2 | 29349 | 50 | 0.940000000 | 0.106907251 | 0.112173913 |
| e4 | 0.80 | P3 | 22259 | 50 | 0.840000000 | 0.067995113 | 0.069530892 |
| e4 | 0.80 | P4 | 115035 | 50 | 0.960000000 | 0.008430662 | 0.000500000 |
| e4 | 0.80 | OT | 7116 | 17 | 0.823529412 | 0.012066221 | 0.008135294 |
| e4 | 0.80 | ALL | 192635 | 50 | 0.960000000 | 0.038563422 | 0.001515547 |
| ladder_base | 0.90 | P1 | 15708 | 39 | 0.923076923 | 0.142886949 | 0.111810341 |
| ladder_base | 0.90 | P2 | 24382 | 50 | 0.860000000 | 0.105895735 | 0.096559458 |
| ladder_base | 0.90 | P3 | 18487 | 46 | 0.978260870 | 0.084570857 | 0.086674073 |
| ladder_base | 0.90 | P4 | 95316 | 50 | 0.640000000 | 0.030142976 | 0.000008810 |
| ladder_base | 0.90 | OT | 6310 | 15 | 0.800000000 | 0.060506756 | 0.051760542 |
| ladder_base | 0.90 | ALL | 160203 | 50 | 0.800000000 | 0.060203523 | 0.053100860 |
| ladder_base | 0.80 | P1 | 15708 | 39 | 0.923076923 | 0.116903981 | 0.089420148 |
| ladder_base | 0.80 | P2 | 24382 | 50 | 0.780000000 | 0.091966924 | 0.076872521 |
| ladder_base | 0.80 | P3 | 18487 | 46 | 0.934782609 | 0.074474102 | 0.073697412 |
| ladder_base | 0.80 | P4 | 95316 | 50 | 0.600000000 | 0.018079523 | 0.000002022 |
| ladder_base | 0.80 | OT | 6310 | 15 | 0.800000000 | 0.043555783 | 0.030779779 |
| ladder_base | 0.80 | ALL | 160203 | 50 | 0.780000000 | 0.046525801 | 0.030759637 |

The scored e4 rows are 192635 ticks / 673 games. The scored ladder_base rows
are 160203 ticks / 555 games because S123's train-only anchor has no prediction
for its seed block. That omission is named in the JSON and is not a substitute
for any cell.

### Script output and tests

`python -m scripts.platformkit.eval_gate.s238_incumbent_conformal_band` printed
the archive count, every table row above, and `S101 max abs coverage diff 0`.

`python -m pytest tests/platformkit/ingame/test_s238_incumbent_conformal_band.py -q -p no:cacheprovider`
returned `2 passed in 1.44s`.

`python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider`
returned `1 passed in 0.61s`.

### NOT VERIFIED

- An independent verifier has not rerun the script from an archive landing.
- The full 465249-tick / 1593-game source quoted by the specification is not
  the archive present in this worktree; this attempt uses and labels the
  232951-tick / 797-game archive instead.
- This opt-in report has no `predict_live` caller and no deployment action.
- A second independent corpus was not supplied for this calibration report.
- The absent FWER ledger prevents a nonzero K read; the launch record names the
  observed zero rather than synthesizing one.
