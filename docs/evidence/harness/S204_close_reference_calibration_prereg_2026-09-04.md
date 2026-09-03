# S204 Close Reference Calibration Preregistration

Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q1-Q9.
Spec: docs/evidence/tracking/specs/S204_spec.md.

## Premise

The S05 report claims that no gate corpus carries a market close. This must be
re-measured before scoring. The fixed S05 after-ECE values are NBA 0.024843
(1,814), MLB 0.008077 (39,162), soccer 0.009302 (25,834), and tennis
0.008403 (41,886), all with zero dropped rows and FLATTENED labels.

## Fixed inputs and pairing

- NBA: data/cache/combo/gate_corpus_nba_close.parquet. Keep only finite y,
  finite p_base, finite p_close, and close_source equal to
  pregame_last_tick_before_commence. Count first_inplay_tick separately and
  exclude it from the paired pregame denominator.
- MLB: data/cache/combo/gate_corpus_mlb_close.parquet. Keep only finite y,
  finite p_base, finite p_close, and close_source equal to
  pre_first_pitch_two_sided.
- Soccer: data/cache/combo/gate_corpus_soccer.parquet paired one-to-one by
  event_id with data/domains/soccer/odds.parquet using the existing S02
  devigged close rule. Keep only finite y, finite p_base, and finite close.
- Tennis: do not score a close series because S03 labels its close vintage
  SYNTHETIC. Count that separately as not verified for a pregame comparison.

No other row may be excluded. Every exclusion must be named in the summary.
The source files are opened sequentially and each is below 300 MB.

## Fixed forecaster and metrics

For each sport, compute the model probability with the existing S05
per-regime expanding out-of-fold recalibration: p_base, y, and
scripts.platformkit.regime_calibration.buckets, using the unchanged
calibration_report._oof_per_regime route. Pair after those model predictions
exist; never refit after pairing.

For each scorable sport, report on the identical paired rows for model and
close: ECE, Brier, log loss, and ten reliability bins. Bins use S05's sole
rule: np.linspace(0, 1, 11); bins are [lo, hi) except the last is [lo, hi].
Report paired Brier delta as Brier(close) minus Brier(model), its corpus_unit
clustered 95 percent t interval, and n_eff equal to the number of distinct
corpus_unit values. Labels are MATCH when the interval contains zero and
BEHIND when it does not; fewer than 30 corpus units is NOT SCORABLE.

Store event_id, corpus_unit, event_date, y, model probability, close
probability, and both squared losses in the paired per-row artifact so every
metric and interval can be reproduced without a data-store read. This is a
calibration comparison only. No flag changes, ledger action, or register
action are authorized.

## Acceptance

The bar is the S204 spec verbatim: all four metrics for both sides on
identical paired rows under the one S05 bin rule, zero rows dropped after
pairing, and a per-sport MATCH, BEHIND, or NOT SCORABLE label determined by
its own interval. A BEHIND label is a valid calibration result. No existing
artifact, calibrator default, fold, bin rule, threshold, register, or ledger
may change.

Seal SHA-256: 150DFC16B37055B741F65F4D332C3625FA41B6EE4CDA140B4E5D39A7D31C5178
