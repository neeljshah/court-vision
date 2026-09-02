# S101 -- adaptive conformal coverage on NBA in-play ticks

Row: S101 (signals-ingame). Gap map L17. Reference row: S97, whose fitted Gaussian posterior
reached **0.08 grouped coverage at nominal 0.90**.

**Headline.** A grouped split-conformal band, calibrated on TRAIN folds only, lifts nominal-0.90
grouped coverage on the S86 NBA per-tick SCREEN series from S97's **0.08 to 0.936-0.980 per
phase** -- the sign of the deficit flips from massive under-coverage to modest OVER-coverage --
at roughly **10x the interval width** (P1 0.0221 -> 0.2336). **The 90 +/- 2 bar is NOT REACHED
in any phase for either point predictor**; every phase over-covers by 2 to 8 points except the
as-of prior in OT, which under-covers by 25 points. The online ACI arm, run within each
held-out game, **saturates at coverage 1.000 at 5x the static width** and is reported as a
LABEL-CONSUMING diagnostic, not a leak-free result -- see section 5. Calibration only; no
ledger charge, no prereg seal, no K read; SINGLE-WINDOW.

Artifacts: `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` (30.9 KB) and
`..._ticks.csv.gz` (18.4 MB, 770,540 rows = 192,635 scored ticks x 2 predictors x 2 nominals,
15 columns: game, date, ts, phase, cell, arm, nominal, p, y, lo_static, hi_static, lo_aci,
hi_aci, alpha_t, fold). Every number below recomputes from that archive alone (Q9).
Module: `scripts/platformkit/eval_gate/s101_aci_coverage.py` (276 LOC).
Test: `tests/platformkit/ingame/test_s101_aci_coverage.py` -- **8 passed**.

---

## 0. Premise (Q8) -- CONFIRMED, not falsified

`scripts/platformkit/ingame/aci_online.py` public API, measured this session:

| symbol | line | signature |
|---|---|---|
| `aci_update` | 25 | `(a_t, err_t, alpha_target=0.10, gamma=0.01) -> float` |
| `apply_aci_to_band` | 40 | `(base_lo, base_hi, q_static, alpha_t, alpha_target) -> (lo, hi)` |
| `run_aci_stream` | 64 | `(base_lo, base_hi, y, alpha_target=0.10, gamma=0.01) -> dict \| "INSUFFICIENT_DATA"` |
| `run_planted_null` | 135 | same signature; adds `null_collapses` |
| `gate_aci_on_stream` | 159 | same signature; adds `ship_recommendation` |

- **alpha update rule:** `a_{t+1} = clip(a_t + gamma * (alpha_target - err_t), 0, 1)`, with
  `err_t in {0, 1}` enforced by a `ValueError` (line 34). Gibbs+Candes 2021.
- **score function it expects:** none. It does not take a nonconformity score. It takes a
  **base interval** `[base_lo, base_hi]` per tick plus the realised `y`, forms
  `err_t = 1[y_t not in [lo_t, hi_t]]`, and rescales the half-width by
  `min(alpha_target / max(alpha_t, 1e-6), 100)` (line 51). The 100x cap and the `[0, 1]` clip on
  alpha are the only guards. `_MIN_STREAM_LEN = 50` -> shorter streams return `INSUFFICIENT_DATA`.
- **Callers:** exactly one production path, nba-hardcoded --
  `scripts/platformkit/ingame/aci_stream_shim.py:15-16,109` imported from
  `scripts/platformkit/ingame/ingame_pred_tick_runner.py:145-146` (`apply_to_document(doc, "nba")`)
  and `:200-201` (`update_stream("nba")`). Plus its own `_main()` synthetic demo at :217 and
  `scripts/platformkit/ingame/test_aci_online.py`.
- **Never scored on ticks:** `data/cache/ingame_aci` **does not exist**; no `s101_*` or `aci_*`
  artifact under `data/cache/eval_gate/`; no `docs/evidence/harness/` file mentions ACI coverage.
  **PREMISE HOLDS -- not falsified.** (The shim blocker recorded in L17 is unchanged and was not
  touched: `ingame_grade` rows still carry no `lo`/`hi`, so the shim remains a structural no-op.
  S101 calls `run_aci_stream` directly, as L17 directs.)

## 1. Corpus, folds, leak contract

Input `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv` -- 232,951 ticks / 797 games,
SCREEN side only; the verdict side is never read. Loaded through S94's `load_screen`/`prepare`,
so the phase cell (`period_bucket|margin_bucket|rem_bucket`) and the game-first date are the
same objects S94/S97 used. Expanding walk-forward by game-first date, 5 held-out blocks after a
train-only seed block; **192,635 ticks / 673 games scored**, the 40,316-tick seed never scored.
Fold windows are byte-identical to S94's and S97's, which is the point -- S101 and S97 are
scored on the same rows.

| fold | test window | train ticks / games | test ticks / games | embargo cut | train date max |
|---|---|---|---|---|---|
| 1 | 2024-12-09..2025-01-25 | 38,698 / 118 | 38,179 / 138 | 2024-12-08 | 2024-12-07 |
| 2 | 2025-01-27..2025-11-04 | 78,495 / 262 | 38,838 / 123 | 2025-01-26 | 2025-01-25 |
| 3 | 2025-11-05..2025-12-26 | 116,246 / 381 | 38,628 / 137 | 2025-11-04 | 2025-11-03 |
| 4 | 2026-01-02..2026-02-25 | 155,961 / 522 | 38,280 / 135 | 2026-01-01 | 2025-12-26 |
| 5 | 2026-02-26..2026-06-10 | 193,353 / 654 | 38,710 / 140 | 2026-02-25 | 2026-02-24 |

Purge asserted game-disjoint and the 1-day embargo asserted
(`train_date_max < embargo_cut <= test_start`) per fold, in code, on every run.

## 2. The construction

A per-tick nonconformity score `|y - p|` is **degenerate**: `y in {0,1}` is never inside a band
of half-width 0.02 around a probability, so a literal conformal interval on it covers 0.0 and
measures nothing -- the same degeneracy S97 recorded for its own interval. The measurable form
is grouped, and S101 uses it on BOTH sides of the pipe:

- **Calibrate (TRAIN folds only).** Within each phase cell, TRAIN ticks are cut into equal-count
  groups (`>= 400` ticks each, capped at 50) ordered by the point prediction `p`; a group's
  score is `|mean(p) - realised group frequency|`. The cell half-width is the `(1 - alpha)`
  empirical quantile (`method="higher"`) of those group scores. A cell too small for 2 groups
  inherits the pooled quantile over all train groups. 12 cells calibrate on fold 1 rising to 20
  on fold 5; pooled half-width 0.0766-0.1334 depending on arm and nominal.
- **Band.** `[clip(p - hw, 0, 1), clip(p + hw, 0, 1)]`, held fixed across the test fold. This is
  the **STATIC** arm and it is the leak-free deliverable.
- **Adapt (ACI).** `run_aci_stream(lo, hi, y, alpha, gamma=0.01)` is called **per held-out game**
  in ts order, alpha reset at every game boundary, alpha at tick t built from misses at 0..t-1
  only. This is the **ACI** arm. Zero games hit `INSUFFICIENT_DATA` (min game length 156 ticks
  vs `_MIN_STREAM_LEN = 50`).
- **Score.** S97's grouped coverage, unchanged: within a phase, equal-count groups (`>= 400`,
  cap 50) by `p`; a group is COVERED when its realised frequency lies inside that group's mean
  `[lo, hi]`. `gamma` is aci_online's own default 0.01, reported not tuned.

Point predictors: `market` (the raw in-play line) and `model` (the S86 as-of state prior).

## 3. Coverage at nominal 0.90 -- the deliverable

STATIC arm (leak-free). Bar `0.90 +/- 0.02`:

| phase | n | groups | group size | market cov | dev | market width | model cov | dev | model width |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 18,876 | 47 | 401 | 0.9362 | +0.0362 | 0.2336 | 0.9574 | +0.0574 | 0.2622 |
| P2 | 29,349 | 50 | 586 | 0.9400 | +0.0400 | 0.2418 | **0.8800** | **-0.0200** | 0.2752 |
| P3 | 22,259 | 50 | 445 | 0.9600 | +0.0600 | 0.1777 | 0.9400 | +0.0400 | 0.1969 |
| P4 | 115,035 | 50 | 2,300 | 0.9800 | +0.0800 | 0.0228 | 0.9400 | +0.0400 | 0.0264 |
| OT | 7,116 | 17 | 418 | 0.9412 | +0.0412 | 0.0562 | **0.6471** | **-0.2529** | 0.3760 |
| ALL | 192,635 | 50 | 3,852 | 0.9600 | +0.0600 | 0.0959 | 0.9800 | +0.0800 | 0.1201 |

**Not one cell is inside the bar.** The single closest is the as-of prior in P2 at 0.8800,
whose deviation is `-0.02` to the printed precision but `-0.020000000000000018` in float, so the
strict `abs(dev) <= 0.02` comparison records it as a MISS. It is reported as a miss; the
tolerance was not widened (Q3).

**Against S97 on the same rows.** S97's Gaussian: P1 0.191, P2 0.120, P3 0.220, P4 0.080, OT
0.000, ALL 0.080 -- every phase 68 to 90 points BELOW nominal. S101's conformal band: every
phase 2 to 8 points ABOVE nominal (market) at 4-11x the width. The comparison that matters is
against S97's own in-sample inflation diagnostic, which asked how wide a Gaussian would have to
be: it found P1 needs `k = 15` (width 0.3152, coverage 0.936) and **P3, P4, OT and ALL reach
0.90 at no scalar inflation up to k = 200**. S101 hits 0.936 at P1 with width **0.2336** --
narrower than S97's in-sample answer, and out of sample -- and reaches 0.94-0.98 at P3/P4/OT
where no Gaussian inflation could. That is the mechanism S97 named: late in games the deficit
is a LOCATION error, not a scale error, and a conformal half-width fitted per cell to the actual
`|p - frequency|` deviation absorbs a location bias that a symmetric variance inflation cannot.

**The as-of prior in OT is the one hard failure.** 0.6471 at width 0.3760 -- the prior is both
badly located and badly dispersed in overtime, and no amount of the calibrated width rescues it.
The market band in OT covers 0.9412 at width 0.0562, one seventh as wide. This reproduces, on a
coverage measure, the OT repricer artifact S98 recorded on Brier.

## 4. Coverage at nominal 0.80

| phase | market static | dev | width | model static | dev | width |
|---|---|---|---|---|---|---|
| P1 | 0.8511 | +0.0511 | 0.1824 | 0.8936 | +0.0936 | 0.2258 |
| P2 | 0.9400 | +0.1400 | 0.2138 | 0.8600 | +0.0600 | 0.2374 |
| P3 | 0.8400 | +0.0400 | 0.1360 | 0.8600 | +0.0600 | 0.1722 |
| P4 | 0.9600 | +0.1600 | 0.0169 | 0.9400 | +0.1400 | 0.0210 |
| OT | 0.8235 | +0.0235 | 0.0241 | 0.4706 | -0.3294 | 0.3050 |
| ALL | 0.9600 | +0.1600 | 0.0771 | 0.9800 | +0.1800 | 0.1020 |

Bar `0.80 +/- 0.02`: **not reached in any cell**, and the over-coverage is WORSE at 0.80 than at
0.90 (market ALL +0.16 vs +0.06). The band is not tracking the nominal level -- lowering the
target shrinks the half-width (market ALL 0.0959 -> 0.0771) far less than the nominal drop
requires, because the calibration quantile is taken over a small number of cell groups
(2 to 50) whose upper tail is thin. This is a real limitation of the grouped calibration, not a
tuning artifact, and it is why the 0.80 row is honestly worse than the 0.90 row.

## 5. The ACI arm, its alpha trajectory, and why it is a diagnostic only

| nominal / arm | P1 | P2 | P3 | P4 | OT | ALL | ALL width |
|---|---|---|---|---|---|---|---|
| 0.90 market ACI | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.5160 |
| 0.90 model ACI | 1.000 | 1.000 | 1.000 | 0.960 | 1.000 | 0.980 | 0.5103 |
| 0.80 market ACI | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.3518 |
| 0.80 model ACI | 1.000 | 1.000 | 1.000 | 0.960 | 1.000 | 0.980 | 0.3785 |

**The online arm saturates.** It buys coverage 1.000 at 5x the static width (0.5160 vs 0.0959
overall; 1.22 wide in P2, i.e. the whole probability line). It is not an improvement -- a band
that always covers at any width is the trivial solution -- and it is not the leak-free number.

**Why, mechanically.** `run_aci_stream`'s error indicator is `1[y_t not in [lo_t, hi_t]]` with
`y` binary. Early in a game `p` sits near 0.5 and the band is ~0.09 wide, so **every tick is a
miss**, alpha falls at `0.9 * gamma` per tick, and the half-width scales by
`alpha_target / alpha_t` -- it widens without any evidence that it should. Late in a game `p`
converges to `y`, misses stop, and alpha climbs back. Measured trajectory (market, 0.90):
mean alpha USED 0.0592 against a target of 0.10; mean alpha over each game's last quarter
**0.0916**; ticks pinned at the zero clip 0.73 pct; per-game terminal alpha 0.0905-0.0954 across
folds with tail std 0.0044-0.0066. **So alpha settles, but it settles per game after a
down-and-back excursion, not to a stable global level** -- and for the as-of prior it settles
ABOVE target (0.90: terminal 0.167-0.201, tail std 0.016-0.021; 0.80: terminal 0.357-0.413, tail
std 0.037-0.042), i.e. the update tries to NARROW the prior's band even as its coverage is the
one that fails. 16 to 46 pct of games touch the zero clip at some point in the game.

**Why it is label-consuming.** Measured on this corpus: `y` has `nunique == 1` for all 797
games. There is only one label per game, attached to every tick. Any within-game online update
therefore reads the game's own final outcome, however the strictly-before guard is written. The
guard is real and tested (section 7) -- no tick's interval depends on a LATER tick -- but the
quantity it reads at earlier ticks is still the game's result. **The ACI arm is reported as a
label-consuming ceiling, never as a leak-free result. STATIC is the leak-free arm.** A leak-free
online form would have to update alpha between COMPLETED games, not within one; that is a
different row and is not built here.

**Planted null.** `gate_aci_on_stream`'s `run_planted_null` returns `null_collapses = False` and
`ship_recommendation = "REJECT:planted_null"` for all four (arm, nominal) pairs, on the
`iid_resample_empirical_residuals` construction. This is **NOT INFORMATIVE** on this surface and
is recorded as such rather than as a verdict: the null's internal criteria are the per-tick
binary coverage and the pinball loss, both of which are the degenerate form S101 exists to
replace. Only `null_collapses` was read, and it fails for the same mechanical reason the ACI arm
saturates.

## 6. Verdict against the bar

**BAR NOT REACHED.** `90 +/- 2` per phase: 0 of 5 phases for `market`, 0 of 5 for `model`
(P2 model at 0.8800 sits exactly on the boundary and is recorded as a miss). At nominal 0.80,
0 of 5 for either. The bar is reported MISSED, never lowered (Q3). This is a SCREEN and a
NON-FINDING: no charge, no seal, no K read, no prereg draft.

**What the row nonetheless establishes.** The interval problem S97 left open is not
unfixable -- an out-of-sample conformal band moves grouped coverage from 0.08 to 0.94-0.98 on
identical rows, including in the three phases where S97 proved no Gaussian inflation ever
reaches 0.90. What it does NOT do is land ON nominal: the band systematically over-covers, worse
at 0.80 than at 0.90, and the honest reading is that the calibration quantile over 2-50 cell
groups is too coarse to hit a 2-point target. Two named next steps, neither taken here: a
finer conformal grid (smaller `COVERAGE_MIN_GROUP` on the calibration side only, with the
scoring resolution left at S97's 400 so the bar is unmoved), and an asymmetric band -- every
under-covering cell here is a location miss, and the symmetric `p +/- hw` cannot express it.

## 7. Rails self-check (VERIFIER_CONTRACT B and Q)

- **B1 no circular metric** -- no tick is excluded after scoring. Every screen tick in a test
  fold is banded and scored; the only rows absent are the train-only seed block (named, 40,316
  ticks) and phases with fewer than 2 groups of 400 (none occur; OT has 17 groups).
- **B2 additive** -- new module + new test; no existing symbol renamed, removed or re-signed.
  `aci_online.py` was READ and CALLED, never edited.
- **B7 no head-slice** -- all 192,635 scored ticks / 673 games enter every table; folds 1-5 are
  all reported.
- **B8 no self-fit as independent** -- the conformal quantile is fitted on TRAIN folds only and
  evaluated on purged, embargoed held-out folds. The one in-sample number quoted (S97's `k`
  inflation) is labelled in-sample and belongs to S97.
- **B9 no degenerate denominator** -- the coverage denominator is the group count, reported in
  every row (17-50), and its resolution limit is stated in section 8.
- **B10 / Q3 no bar moved** -- `COVERAGE_TOL = 0.02`, `COVERAGE_MIN_GROUP = 400`,
  `COVERAGE_MAX_GROUPS = 50` are asserted byte-identical to S97's by the per-file test. The
  0.8800 boundary case is reported as a miss rather than rounded into tolerance.
- **Q1 / Q2 no seal, no charge** -- SCREEN, so no prereg artifact is required and none is
  claimed. `_charge_ledger` never imported; `backtest_fwer.jsonl` never opened and still
  **18 rows**; K never read; `data/registry/` untouched; no flag flipped.
- **Q4 leak contract** -- expanding walk-forward, purge asserted game-disjoint, symmetric 1-day
  embargo asserted per fold, in code. Calibration reads TRAIN rows only. No meta-learner.
- **Q5 two corpora** -- one corpus (the S86 NBA screen side) -> labelled **SINGLE-WINDOW** in the
  artifact and in the register row.
- **Q6 calibration language only** -- coverage and interval width only; no dollar, ROI, profit or
  edge language; none of the retracted figures appears. Asserted by the per-file test, which
  scans the module source.
- **Q7 sampling rail** -- SCORED metric, n = 192,635 ticks / 673 games, well over the rail.
- **Q9 archive the differential** -- the per-tick archive stores, for every scored tick and every
  (predictor, nominal) pair, both bands, the alpha actually used, `p`, `y`, the phase, the cell,
  the game and the fold. Every table above recomputes from that file alone.
- **Human-gated paths** -- nothing under `src/`, `kernel/`, `api/`, `intel/` or
  `scripts/team_system/` was read or written. `scripts/platformkit/ingame/aci_online.py` was
  imported, not modified.

## 8. Limits (named, not hidden)

1. **The ACI arm is label-consuming** (section 5) and is a ceiling, not a result.
2. **The coverage measure cannot resolve the bar in OT.** With 17 groups the resolution is
   `1/17 = 0.0588`, coarser than the `+/- 0.02` tolerance -- OT cannot land inside the bar at
   this group size even in principle. P1 (47 groups) resolves to 0.0213 and the rest to 0.0200,
   i.e. the bar is exactly one group wide everywhere. This is inherited from S97's definition
   and was not changed, because changing it would move the bar.
3. **`gamma = 0.01` is aci_online's default, not a fitted value.** No sensitivity sweep was run;
   a different gamma moves the ACI arm's width but cannot fix its saturation, which is a
   property of the binary error indicator rather than of the step size.
4. **The conformal quantile has no finite-sample correction.** `method="higher"` on 2-50 group
   scores approximates `ceil((n+1)(1-alpha))/n` and is conservative in the same direction as the
   observed over-coverage; part of the +2 to +8 point excess is this, and the two are not
   separated here.
5. **SINGLE-WINDOW** -- one corpus, one sport, one venue's traded mid rather than a devigged
   close. Nothing here transfers to MLB, soccer or tennis without being re-run.
6. **NOT VERIFIED** -- lane's own report; no independent verifier re-run.
