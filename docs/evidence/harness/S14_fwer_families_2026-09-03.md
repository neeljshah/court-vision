# S14 -- FWER families and the dual bar (2026-09-03)

VERDICT: ACCEPT. The within-family Benjamini-Hochberg bar lands under all three of its
conditions. 200 planted nulls yield **0 discoveries** at q=0.05 (bar: <= 10). 37 families
are frozen, 396 features, 3,564 hypotheses. `k_cumulative` is unchanged and no past
verdict is re-scored.

## THIS IS THE ONLY CHANGE IN THE PROGRAM THAT LOOSENS A BAR -- stated plainly

Until today every hypothesis was priced by `deflated_metrics.deflated_p(raw_p, k_cumulative)`:
Bonferroni across the whole cumulative charge ledger, as if every hypothesis in the program
were one undifferentiated family. S14 adds a SECOND, LOOSER axis: Benjamini-Hochberg at
q=0.05 over the p-values of ONE frozen family.

What q=0.05 within a family means, versus Bonferroni. Bonferroni controls the family-wise
error rate: the probability of even ONE false discovery anywhere in the family is held at
alpha, so each member must clear alpha/K. BH controls the false discovery RATE: among the
hypotheses it calls discoveries, the expected FRACTION that are false is held at q. Those
are not the same promise. In a family of 200 the Bonferroni per-test bar is 0.05/200 =
0.00025, while BH's most permissive step is q = 0.05 -- 200x looser at the top of the step-up
ladder. A hypothesis inside a large family therefore faces a materially easier family bar
than it faced yesterday, and that is exactly why it does not get to ship on the family bar
alone.

## The three conditions, and how each is discharged

(i) FAMILIES FROZEN FIRST, timestamped before the first family-relative trial.
`docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md` was committed in its OWN commit,
`07c5fd6b3`, at `2026-09-02T09:48:52-05:00`, ahead of the commit carrying the module, the
tests and this memo. Proof that no family-relative trial preceded it, measured before the
spec was written: `wc -l data/cache/eval_gate/backtest_fwer.jsonl` = **14 rows**, and
`grep -c '"family"'` over that file = **0** -- not one charged row carries a family field, so
no trial has ever been priced family-relative. The foundry results index
`data/cache/eval_gate/hypotheses.sqlite` does not exist. The spec is pinned by content:
`git hash-object` = `62702554f6e57ec9f3182e8edc1e4d6a109a3b41`, which equals
`git rev-parse HEAD:<spec>`, and that blob id is embedded in every verdict `dual_bar_verdict`
returns (`families_spec_sha`). Editing the spec changes the pin, so a verdict priced against
an edited partition is self-evident.

(ii) EVERY AHEAD PRINTS BOTH BARS AND REQUIRES BOTH. `dual_bar_verdict` returns
`global_pass` (the unchanged `deflated_p(raw_p, k_global) < alpha`) and `family_pass` (BH
rejection inside the frozen family) and sets `AHEAD` only when both are true; `blocked_by`
names whichever failed. `render_bars` prints them on one line. Two measured examples:

    verdict=AHEAD blocked_by=- raw_p=1e-09 | GLOBAL k=100 deflated_p=1e-07 alpha=0.05
      pass=True | FAMILY nba_gate q=0.05 n=20 bh_adj_p=2e-08 pass=True
      | spec=s14-families-v1@62702554f6e5

    raw_p=0.004, k_global=1000, family of 10: FAMILY pass=True (BH threshold 0.005),
    GLOBAL deflated_p=1.0 pass=False -> verdict=NOT AHEAD blocked_by=global.

The second is the load-bearing case: a hypothesis that clears the loosened family bar and
fails the global one is NOT AHEAD. It is `test_bh_pass_but_global_fail_is_not_ahead`.

(iii) NO PAST VERDICT IS RE-SCORED -- true by construction, not by discipline.
`dual_bar_verdict(raw_p, k_global, family_p_values, ...)` takes p-values as ARGUMENTS. It
never opens the FWER charge ledger, the results DB, or any stored verdict, so it cannot
reach a recorded result to restate it. `test_verdict_reads_no_ledger_and_no_stored_result`
wraps `builtins.open` and asserts no path containing `backtest_fwer` or `hypotheses.sqlite`
is touched during a verdict. No verdict recorded before commit `07c5fd6b3` has been
recomputed, quoted or promoted under the looser bar. Re-scoring a recorded verdict against
a bar that arrived after it is a self-serving reinterpretation, and it is written as such in
the module docstring, in the frozen spec and here.

## Dependency: NOT a new one

    $ python -m pip show statsmodels
    Name: statsmodels
    Version: 0.14.4
    License: BSD License
    Location: c:\users\neelj\appdata\local\programs\python\python310\lib\site-packages

statsmodels 0.14.4 was already installed, BSD 3-Clause. `bh_within_family` is a thin wrapper
over `statsmodels.stats.multitest.multipletests(method="fdr_bh")`; the step-up rule is easy
to get subtly wrong at ties and a wrong FDR routine fails OPEN, so it is imported rather than
re-derived. Nothing was installed.

## PREMISE (step 0) -- CONFIRMED, not falsified

`combo/fwer_budget.py` before this change exported exactly
`DEFAULT_EPS, DEFAULT_CORPORA_CAP, eps_eff, min_corpora_eff, fdr_budget, cumulative_k` -- no
BH path anywhere, `deflated_p` Bonferroni-only. Before = 0 family-relative bars; every
hypothesis priced independently.

## The frozen families -- 37, not the draft's 34

The red-team draft (`REDTEAM_SIGNAL_FACTORY_2026-09-03.md` section 4) proposed 34 families /
376 features / 3,384 hypotheses by hand. Measured off `foundry/catalogue.py` `entries()` --
69 catalogue parquets present on disk -- the partition is **37 families / 396 features /
3,564 hypotheses**. The construction rule is mechanical and is written into the spec: a
family is one (sport, column-set) group, so parquets sharing a column set (the four
`opp_allowed_asof_*` seasons, the seven `soccer_states__*` leagues, the ATP/WTA
`asof_setdetail` pair) collapse into one family; a member is a numeric-dtyped column whose
name is not `y`, `season` or `minute` and does not end in `_n_prior` or `_id`;
hypotheses = members x 9 transform instances x 1 horizon x 1 market x empty conditioning.
The draft is superseded because it omitted the in-game MLB and NBA play-by-play state grids
that are on disk and counted per-family features by eye. Five NAMED catalogue paths are
absent from disk and define NO family; they are listed in the spec.

## Measured result on the planted nulls

200 independent null p-values, `numpy.random.default_rng(20260903).uniform(0, 1, 200)`, seeded
and reproducible, following the `null_ship_calibration.py` planted-null pattern at the
p-value layer (that module plants 200 outcome-blind candidates; `family_bars` consumes
p-values, never data, so the plant lands one layer up).

| quantity | measured | bar |
|---|---|---|
| planted nulls (denominator) | 200 | -- |
| BH discoveries at q=0.05, one family of 200 | **0** | <= 10 |
| AHEAD verdicts over the same 200 (k_global=1) | 0 | <= 10 |
| BH discoveries, same 200 split into 20 families of 10, summed | 0 | <= 10 |
| smallest planted p-value | 0.00914156 | -- |

NON-TAUTOLOGY: all 200 are in the denominator. None was dropped, re-seeded or re-labelled
after the count. The 20-family split scores the same 200 draws a second way and is reported
whatever it says.

## k_cumulative did not move

`eps_eff`, `min_corpora_eff`, `fdr_budget`, `cumulative_k` and `deflated_p` are untouched;
the only edits to `fwer_budget.py` are two new functions, one new constant, an extended
`__all__` and docstring text (B2-additive: nothing renamed, nothing removed).
`test_the_global_k_bar_did_not_move` charges a TMP ledger three times (k_cumulative 1, 2, 3),
exercises `bh_within_family` and `across_families` between the reads, charges again and reads
4 -- the switch changes no K. `test_the_real_charge_ledger_is_never_touched` sha256s
`data/cache/eval_gate/backtest_fwer.jsonl` before and after and asserts equality; the
production ledger stands at 14 rows and was never opened for writing. No
`data/registry/` path was written.

## Tests -- per-file only, both green

    $ python -m pytest scripts/platformkit/eval_gate/test_family_bars.py -q
    9 passed in 1.31s
    $ python -m pytest tests/platformkit/combo/test_fwer_families_bh.py -q
    8 passed in 1.41s

Regression on the readers of the touched module (A5): every importer of
`combo.fwer_budget` imports clean (`run_gate`, `null_ship_calibration`, `backtest_runner`,
`replication_gate`, `stacker`, `combo_search`, `retro_correction`, `combo_runner`,
`planted_null_fdr`, `foundry.tiers`), and
`tests/platformkit/combo/test_fwer_budget.py` 6 passed,
`tests/platformkit/combo/test_planted_null_fdr.py` 5 passed,
`scripts/platformkit/eval_gate/test_replication_gate.py` 5 passed.

## Deviations from the S14 spec text, declared

- The frozen spec was written to `docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md`,
  not `docs/research/organization-sprint/`. It sits beside `FACTORY_TIERS_SPEC_2026-09-03.md`,
  which `foundry/tiers.py` already pins the same way, and `docs/research/` is a local-only
  tree absent from a clean clone -- a prereg that vanishes on clone is not a prereg.
- Tests live at `scripts/platformkit/eval_gate/test_family_bars.py` (new module, colocated
  like every other eval_gate test) and `tests/platformkit/combo/test_fwer_families_bh.py`
  (the path the S14 spec names, holding the combo-side cases).
- The S14 spec quotes the ledger at 13 rows; it holds 14 today (S06 charged one). The
  must-not-move item is the file, not the count, and it is byte-identical.

## NOT VERIFIED

- No real hypothesis was scored through the dual bar. Every number above is a planted null
  or a hand-constructed p-value; no corpus was read, no trial charged, K stays 14.
- No caller has been wired to `dual_bar_verdict`. `foundry/tiers.py` `_run_charged` still
  sets its verdict off the global `deflated_p` alone; wiring it is a separate row and would
  itself have to re-pass the two-bar rule.
- The 37-family partition is measured off the parquets present on disk on 2026-09-03. If a
  catalogue parquet is later materialized (five NAMED paths are absent today), the frozen
  spec does NOT update itself -- by design; a new family needs a new spec_version and a new
  commit, made before the trial that uses it.
- The horizon/market label on each family is a frozen convention, not a measurement; no
  family's market assignment was validated against a scored corpus.
- BH's FDR guarantee under arbitrary dependence is not established here: `fdr_bh` controls
  FDR under independence or positive regression dependence, and the members of one family
  are correlated columns from one parquet. The measured 0/200 is evidence for the null
  behaviour of THIS seed and family shape, not a proof of dependence-robust control. The
  conservative `fdr_by` variant was not measured.
- Q6 self-check: no dollar, ROI, profit or edge language appears in the spec, the module, the
  tests or this memo, and none of the retracted figures appears anywhere in them. This is a
  calibration bar, not a claim about money.
