# The Player-Projection Stack -- one accuracy claim, published under two labeled measurements

> I built a 7-stat player-projection stack (points, rebounds, assists, threes,
> steals, blocks, turnovers) and published its accuracy under TWO explicitly-labeled
> measurements -- a public, re-runnable production holdout and an internal
> walk-forward OOF frame -- with a hard rule that their numbers are NEVER mixed, and
> a drift-guarded verify script that exits nonzero if the production numbers move.
> The label discipline is the product. The single truth-source for every figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); `edge_claimed = False`
> throughout and no dollar, ROI, or edge figure appears anywhere on this page.

---

## The claim

A projection MAE is meaningless unless you say exactly which measurement produced it.
The same stack scored two legitimate ways gives two legitimately different numbers
(on the walk-forward OOF frame BLK reads 0.515; on the production holdout it reads
0.44), and quoting one number with the other's row-count is the single most common
way projection accuracy gets accidentally inflated. So the accuracy here ships as a
labeled pair, each number bound to its own measurement basis, row count, and artifact.

---

## The two measurements (labeled -- never mix their numbers)

| Stat | Production holdout MAE | Walk-forward OOF MAE |
|------|-----------------------:|---------------------:|
| PTS  | 4.83 | 4.58 |
| REB  | 1.92 | 1.90 |
| AST  | 1.39 | 1.34 |
| FG3M | 0.89 | 0.88 |
| STL  | 0.71 | 0.71 |
| BLK  | 0.44 | 0.515 |
| TOV  | 0.89 | 0.88 |

- **Production holdout** (the public, re-runnable lead number): last-20%-by-date
  chronological holdout, **20,354 player-game rows**, scored through the exact
  production inference path by `scripts/verify_production_mae.py`. Re-measured
  2026-07-20 on the grown corpus. Every public doc leads with this column.
- **Walk-forward OOF** (internal artifact, `data/cache/pregame_oof.parquet`,
  gitignored): **~51K held-out player-games per stat** (50,954 rows/stat), with a
  small consistent PTS under-bias (~-0.45). Its predictions are byte-identical to
  the calibration frame's (max abs diff 0.0 over 319,081 rows, monotonic
  non-overlapping windows).

**The centerpiece rule:** a `4.83` / `0.44` number belongs ONLY with the
"production holdout, 20,354 rows" label; a `0.515` / `~51K` number belongs ONLY
with the "walk-forward OOF" label. They are different measurements of the same
stack, not interchangeable. Both are leak-free and competitive with published
prop-model benchmarks -- but they are quoted separately, always under their own label.

---

## The overfit catch that forced this discipline

The two-measurement habit is not cosmetic; it exists because a single-measurement
number already lied once here. `src/prediction/prop_cv_split.py` documents a
leakage-driven grid-search that reported **train CV R^2 ~= 0.79** on steals/blocks
while the honest leak-free holdout came in at **~= 0.06**. That is a ~13x
gap -- the CV number was an artifact of future information bleeding across the split.
The fix is not a comment: the module applies corrective regularization that **takes
precedence over the stale tuned params**, so the leaky hyperparameters cannot
silently reappear on a future retrain. An honest 0.06 that survives is worth more
than a 0.79 that does not.

---

## The drift guards

Three guards keep the published numbers honest between retrains:

1. **Tolerance-gated verify exit.** `verify_production_mae.py` re-scores each stat
   on the production path and compares to the claimed MAE with a **0.02 tolerance**;
   it exits `0` only if every stat holds, exits `1` (with a per-stat drift table)
   otherwise -- so a future bot loop catches drift instead of shipping it.
2. **Train-time feature columns, not today's.** The persisted model was trained on
   the (possibly shorter) feature list recorded in `_meta.json`; today's feature
   builder may be longer. The script scores each stat on `meta["stats"][stat]
   ["feature_columns"]` rather than the live list -- the fix for the
   85-vs-129-shape crash that otherwise blocks reproduction.
3. **Artifact-drift assertion.** The invariant `pkl n_features_in_ == _meta.json
   feature count` is enforced across the audit/backtest scripts
   (`scripts/audit_oof_prod_fidelity.py`, `scripts/backtest_holdout_wf.py`,
   `scripts/iter56_tov_exploration.py`): a retrained pickle whose input width no
   longer matches its metadata is rejected before it can serve a wrong number.

---

## Receipts -- verified committed paths

| Claim | Artifact (committed) |
|---|---|
| 7-stat projection stack + production inference path | `src/prediction/prop_pergame.py` |
| Production-holdout verify script (0.02 drift-gated exit) | `scripts/verify_production_mae.py` |
| Train-time-columns fix for the 85-vs-129 crash | commit `eb95e13b8` (2026-07-20) |
| Self-caught overfit + corrective regularization | `src/prediction/prop_cv_split.py` (lines ~185-186) |
| Artifact-drift assertion (`n_features_in_` == meta count) | `scripts/audit_oof_prod_fidelity.py`, `scripts/backtest_holdout_wf.py` |
| Both labeled measurements, with the never-mix rule | `docs/JOB_EVIDENCE_PACKET.md` section 3 |

---

## Reproduce

```
# re-score the production holdout and drift-check it against the claimed MAEs
python scripts/verify_production_mae.py
```

Where the trained models and dataset are present (local / pod), the script prints a
per-stat `claim / live / delta / verdict` table and exits `0` when all seven stats
sit within 0.02 of the published production numbers. On a fresh clone the models are
absent (`data/models/` is local-only and gitignored), so the script prints a
documented "nothing to verify" note and exits `0` -- it never fabricates a number to
fill the gap. The verify script was fixed to run cleanly in commit `eb95e13b8`
(2026-07-20), which also re-measured the quickstart MAE table on the grown corpus.

---

## Why it matters

Anyone can report a projection MAE. The hire signal is that I report it twice, under
two named measurements, refuse to mix their numbers, and back the discipline with a
script that fails loudly when the production number drifts. That habit came from
catching my own 0.79-vs-0.06 overfit -- so the label rule is not bureaucracy, it is
the scar tissue from a real mistake, encoded so it cannot recur. A number you can
trust is a number that tells you exactly how it was measured.

---

*edge_claimed = False everywhere. Every figure is an MAE against a real
out-of-sample corpus, never a dollar figure, and nothing here implies a projection
beats the market. Retracted measurement artifacts appear only in
[JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never on this page.*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
