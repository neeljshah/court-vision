# S248 - NBA fatigue conditioned forms v2: CLOSED AT LIMIT

Row: `docs/evidence/tracking/specs/S248_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

## Preregistration

The sealed preregistration is
`docs/evidence/harness/S248_nba_fatigue_conditioned_v2_2026-09-04_prereg.md`.
Its embedded SHA-256 seal is
`ad49226dfc829e90c37cf37ccb7940835a8055ac8216cfc3031c10a0254948bb`.
It was committed before any archive metric was calculated in commit
`33093da1f8f7b93ab3969feb6bf678d54cfd7db3`.  After that commit, this exact
LF-byte verification succeeded:

```text
git show HEAD:docs/evidence/harness/S248_nba_fatigue_conditioned_v2_2026-09-04_prereg.md | head -n 61 | sha256sum
ad49226dfc829e90c37cf37ccb7940835a8055ac8216cfc3031c10a0254948bb *-
```

The preregistration fixed three forms and forbade a substitute for the third
form.  It also fixed the response to an unavailable third input: stop all
candidate scoring and name the unavailable column.

## Binding before-condition: reproduced

Inputs were opened one at a time:

| input | bytes | SHA-256 | use |
|---|---:|---|---|
| `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` | 38,630,145 | `f498a7a040201571270183a79a025cd87d91ed5060f244b69964a150eab7d0f6` | ALL reproduction and schema check |
| `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_rated.csv` | 16,420,946 | `848ba53d041887d4700c375ddbc1bce36123f4a3be48d4ac85399a946ab753fe` | companion row-count and schema check |

The ALL archive remeasurement printed 79,554 ticks, 661 clusters, 194 date
folds with 191 scored, and dates 2024-10-25 through 2026-04-06.  Its Brier
order was market 0.142876712852, recalibration null 0.144293050901, and
incumbent 0.146849530547.  The companion RATED archive printed 33,713 rows,
284 clusters, 80 scored dates, and dates 2024-10-25 through 2025-04-13.

The exact reproduction output was:

```text
REPRO fatigue_min ACTUAL -0.000211900205426249 EXPECTED -0.000211900205426191 ABS_DIFF 5.82758667710958633e-17 P 0.489924499554432291 CI -0.000814202715139908 0.000390402304287409
REPRO fatigue_share ACTUAL -0.000098022604728771 EXPECTED -0.000098022604728742 ABS_DIFF 2.87042525165537299e-17 P 0.792022951736571112 CI -0.000827666142738347 0.000631620933280804
REPRO unit_onoff ACTUAL -0.000397492225916192 EXPECTED -0.000397492225916174 ABS_DIFF 1.81603863891321993e-17 P 0.237998206880955410 CI -0.001058332141765905 0.000263347689933521
MAX_ABS_DIFF 5.82758667710958633e-17
```

This clears the required maximum absolute difference of 1e-9.  The S92
before-condition therefore holds; this memo does not label it falsified.

## Fixed change blocked by the archived schema

Both CSV headers contain `period`, `elapsed`, and `fatigue_min`, so the first
two fixed x values are constructible.  Neither header contains
`absolute_margin` or `margin_s`, the only preregistered allowed sources for
the third fixed x value.  The schema check printed:

```text
HAS_ABSOLUTE_MARGIN False
HAS_MARGIN_S False
REQUIRED_MARGIN_COLUMNS_ABSENT True
```

The required forms are reported without selectively scoring a subset:

| fixed form | calibration improvement | DM p | clustered 95 percent CI | n_eff | status |
|---|---:|---:|---|---:|---|
| fatigue_min x period | not scored | not scored | not scored | not scored | not run: fixed three-form screen halted |
| fatigue_min x remaining time | not scored | not scored | not scored | not scored | not run: fixed three-form screen halted |
| fatigue_min x absolute margin | not scored | not scored | not scored | not scored | unavailable: `absolute_margin` and `margin_s` absent |

No new module, candidate probability, candidate loss, or per-tick differential
series was produced.  Constructing a proxy from a different source or dropping
the third form after the schema check would violate the sealed preregistration
and the spec's all-three requirement.  The S92 archive files were not written;
their post-check SHA-256 values are recorded above.  No ledger, register,
feature flag, or data path was written.

## Test and verifier self-check

TEST: `scripts/platformkit/eval_gate/test_s248_fatigue_forms_v2.py` was not
created or run because the sealed schema gate stopped the required three-form
module before implementation.  No Python source changed, so there is no new
reader, import, or LOC-rail surface.

* B1: no candidate row subset was scored; the unchanged S92 dead-clock
  exclusion remains named by the archived corpus.
* B2/B3/B4/B5/B6: no runtime schema, gate, claim path, deployment, move, or
  import changed.
* B7/B8/B9: no sampled render, self-fit result, or new denominator is claimed.
* B10/Q3: the +0.004 calibration-improvement bar is unchanged.
* Q1: the pre-score seal and post-commit LF verification are above.
* Q2: this screen did not charge a trial; no ledger or K field was read.
* Q4/Q9: no OOS candidate score or candidate differential exists, so none is
  claimed.
* Q5: no AHEAD result is claimed.
* Q6: this memo uses calibration language only.
* Q7: no new sampled or scored metric is reported.
* Q8: the archive before-condition was rerun and quoted before the fixed
  change was assessed.

## NOT VERIFIED

* The three conditioned forms are not calibration-screened because the required
  archived absolute-margin input is unavailable.
* No candidate paired-loss series exists; Q9 is therefore not asserted.
* No result beyond the archived S92 reproduction is claimed.

VERDICT: CLOSED AT LIMIT
