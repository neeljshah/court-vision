# S304 preregistration: S108 as-of feature guards

## Scope

This is an exhaustive local construct of `scripts/platformkit/eval_gate/s108_features.py`. It opens no store, uses no evaluator, no pod, no ledger, and no scored comparison. The only executable evidence will be `tests/platformkit/eval_gate/test_s108_features.py`.

## Binding premise

Before this preregistration, the exact direct-import census was:

```text
BINDING_BEFORE_CONDITION
NO_DIRECT_IMPORTER_TESTS
```

The module public behaviors under test are `asof_sources` (line 28), `_add` (line 35), and `build` (line 40). The baseline module SHA-256 is `b59eea4051a5232bc44612c73540cdd127e2bbd84bce980ad771265a30388c0e`.

## Fixed fixture and checks

Every test uses two SCREEN states with event ids `event-a` and `event-b`, date timestamps `2024-01-01` and `2024-01-02`, incumbent probabilities `[0.25, 0.75]`, outcomes `[0, 1]`, and a one-row-per-event unit map. The partition is fixed to both event ids. All external loaders are monkeypatched in-process; no parquet file is opened.

The exact exhaustive construct has n = 4 behaviors:

1. A source has the planted outcome-equal column `home_final` with values `[0.0, 1.0]` and the legitimate as-of column `asof_rating` with `[10.0, 20.0]`. `home_final` must appear in refusals, must not enter `X`, and a `pd.to_numeric` guard must prove that its values were not read. `asof_rating` must enter `X` as `[10.0, 20.0]`.
2. A source has duplicate `event_id` values and two numeric as-of columns. The source must be refused as a whole before column processing: its short filename appears in refusals, it is absent from sources, and both candidate columns are absent from `X`.
3. Two accepted sources share `asof_rating`. The first supplies `[1.0, NaN]`; the second supplies `[9.0, 2.0]`. The exact assembled value is `[1.0, 2.0]`: the first wins and the second fills only the gap.
4. One accepted source supplies `asof_rating` as `[1.0, NaN]`. The exact assembled feature is `[1.0, NaN]`; `asof_rating__isna` is `[0.0, 1.0]`; and `n_missing_cols` is `1`.

## Bar and evidence

The acceptance bar is 4/4 asserted behaviors with the exact values above, the planted outcome-equal column refused before value access, and the legitimate as-of column accepted. `s108_features.py` must remain byte-identical. The result memo and JSON are `docs/evidence/harness/S304_s108_features_asof_guards_2026-09-04.md` and `docs/evidence/harness/S304_s108_features_asof_guards_2026-09-04.json`.

No delta or predictive claim is calculated in this construct. If a later comparison is added, improvement means baseline loss minus candidate loss; positive means the candidate is better.

Seal-SHA256: 38e294679e91920b894ce28b345b1d6eff65277743e111cbfd4cc125d9eb9a70
