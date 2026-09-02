# S59 -- the charged tiers decide on BOTH bars (2026-09-03)

VERDICT: PASS on the ACCEPTANCE RULE. `foundry/tiers.py::_run_charged` now prices every charged
T2/T3 against the global Bonferroni bar AND its frozen family's within-family bar, and AHEAD
requires both. n = 4 (CONSTRUCT): the enumeration below is every reachable outcome of the family
lookup, and each one is measured. Calibration language only. NOTHING IS CLAIMED HERE -- every
number below comes from a 60-row synthetic corpus with a PINNED p-value; no real hypothesis was
scored, and the one AHEAD is a fixture that exists to prove the AND, not a finding.

PREMISE (step 0, re-measured this session): before this lane, `_run_charged` computed
`deflated_p(dm.p_value, k_global)` and branched on `dp >= rule.alpha` alone -- one bar. S14's
`eval_gate/family_bars.dual_bar_verdict` existed with 9 passing tests and ZERO importers outside
its own test file (`grep -rn dual_bar_verdict --include=*.py` = 1 module + 1 test). Premise HOLDS;
the row is not falsified.

## 1. The four reachable cases (denominator = 4; every one measured, none excluded)

| # | case | family bar | global bar | `verdict` | `dual_verdict` | tmp ledger rows |
|---|---|---|---|---|---|---|
| 1 | clears BH, fails global (`raw_p = 0.004`, `k_global = 1000`) | pass | FAIL | MATCH | NOT AHEAD | 1 seed -> 2 |
| 2 | clears both (`raw_p = 1e-9`, `k_global = 1`) | pass | pass | AHEAD | AHEAD | 0 -> 1 |
| 3 | family not in the frozen partition (`s12_construct`) | n/a | n/a | NOT_IN_FROZEN_FAMILIES | (unset) | 0 -> 0 |
| 4 | global pass, family blocked by 40 recorded nulls | FAIL | pass | MATCH | NOT AHEAD | 0 -> 1 |

Measured bars lines, verbatim from the artifact JSON each trial wrote:

    1: verdict=NOT AHEAD blocked_by=global raw_p=0.004 | GLOBAL k=1000 deflated_p=1 alpha=0.05
       pass=False | FAMILY nba_gate q=0.05 n=1 bh_adj_p=0.004 pass=True | rule=fdr_bh
       fdr_bh_adj_p=0.004 pass=True fdr_by_adj_p=0.004 pass=True | spec=s14-families-v1@62702554f6e5
    2: verdict=AHEAD blocked_by=- raw_p=1e-09 | GLOBAL k=1 deflated_p=1e-09 alpha=0.05 pass=True
       | FAMILY nba_gate q=0.05 n=1 bh_adj_p=1e-09 pass=True | rule=fdr_bh fdr_bh_adj_p=1e-09
       pass=True fdr_by_adj_p=1e-09 pass=True | spec=s14-families-v1@62702554f6e5
    4: verdict=NOT AHEAD blocked_by=family raw_p=0.03 | GLOBAL k=1 deflated_p=0.03 alpha=0.05
       pass=True | FAMILY nba_gate q=0.05 n=41 bh_adj_p=0.9 pass=False | rule=fdr_bh
       fdr_bh_adj_p=0.9 pass=False fdr_by_adj_p=1 pass=False | spec=s14-families-v1@62702554f6e5

Common to cases 1/2/4: `n = 30` (verdict side of the SF-1 partition), `n_eff = 6.0743`
(team-clustered, SF-10), `brier_model = 0.225557`, `brier_close = 0.250200`, `screened_n = 40`.
Case 3 scores nothing: `n_eff = 0.0`, every metric field `None`, `dual_verdict` empty.

CASE 3 IS THE POINT. The frozen-family lookup runs BEFORE `charge_tier`, so a family invented
after the fact returns NOT_IN_FROZEN_FAMILIES and the tmp ledger is still 0 rows -- it is reported,
never charged silently, and no AHEAD is reachable for it. Q2 still holds for the other three: the
ledger row is appended before any metric, and `k_global` is the K read AT LAUNCH.

## 2. Which bar decides, and when that was decided

The q-rule is a PREREG choice read off the frozen partition, never picked after the p-values are
in. `Family.q_rule` is an OPTIONAL per-family field defaulting to `fdr_bh`; the frozen
`FWER_FAMILIES_SPEC_2026-09-03.md` declares none, so all 37 families are `fdr_bh` today and the
file is UNTOUCHED -- `git hash-object` is still `62702554f6e57ec9f3182e8edc1e4d6a109a3b41`, the pin
S14 landed under, and that pin is embedded in every verdict as `families_spec_sha256` beside
`prereg_sha256`.

BOTH rules are computed and printed on every verdict either way. BH assumes PRDS; a family here is
the correlated columns of one parquet, which is exactly where PRDS is not obvious. Benjamini-
Yekutieli is valid under arbitrary dependence and strictly more conservative, so printing
`fdr_by_adj_p` next to `fdr_bh_adj_p` shows the reader how much of a verdict rests on the PRDS
assumption. Case 4 measures the gap on real numbers: `fdr_bh_adj_p = 0.9` against
`fdr_by_adj_p = 1` over the same 41 p-values. Selecting `fdr_by` for a family is a spec edit,
which changes the blob id, which is visible in every verdict priced afterwards.

## 3. Where the family's p-values come from

`ResultsDB.family_p_values(family)` joins `result` to `hypothesis` on `hash` and returns the
recorded `raw_p` of every scored trial for that frozen family; `_run_charged` appends THIS trial's
own `raw_p` and hands the list to the bar. Read-only -- it opens no ledger and re-scores no stored
verdict, so S14's condition (iii) is unchanged. `results_db` is an optional keyword; without it a
charged trial is honestly a family of one (`n_family = 1` in cases 1 and 2), which is looser than
it will be once S16 passes its DB through, and is labelled as such in the printed line.

## 4. Bars not moved (Q3)

`alpha` still comes off `PromotionRule` (0.05, frozen in FACTORY_TIERS_SPEC), `q` off
`FamiliesSpec.q_within_family` (0.05, frozen), `deflated_p`, `eps_eff`, `min_corpora_eff` and the
cumulative K are untouched, and the real `data/cache/eval_gate/backtest_fwer.jsonl` is still 14
rows -- no trial was charged against it by this lane. The only branch added to the verdict ladder
is a NARROWING one: `elif not bars["family_pass"]: verdict = "MATCH"`, which can only turn an
AHEAD into a MATCH, never the reverse.

## 5. Files, tests, LOC

- `scripts/platformkit/eval_gate/family_bars.py` (171 -> 252): `Family.q_rule`, `_by_within_family`,
  both q-rules in `dual_bar_verdict` and `render_bars`, plus `frozen_family`, `families_spec_sha`
  and `charged_bars` (which writes the artifact JSON).
- `scripts/platformkit/foundry/tiers.py` (300 -> 278): the wiring, plus 5 additive TierResult
  fields (`family_q`, `bh_passed`, `global_passed`, `dual_verdict`, `families_spec_sha256`) and an
  optional `results_db=` keyword on `run_tier`. Every pre-existing field and the `run_tier`
  signature are byte-compatible; S16's `foundry_runner.py` is untouched and its 22 tests pass.
- `scripts/platformkit/foundry/promotion.py` (NEW, 66): `PromotionRule` and `promote` moved out
  UNCHANGED so `tiers.py` stays inside the 300-LOC cap; `tiers` re-exports both names, so
  `tiers.PromotionRule` / `tiers.promote` keep resolving for every importer.
- `scripts/platformkit/foundry/results_db.py` (241 -> 252): `family_p_values`.
- `scripts/platformkit/combo/fwer_budget.py` NOT touched -- it is token-locked
  (`docs/evidence/SHARED_MODULE_TOKEN.md`, holder none), which is why the BY variant lives in
  `family_bars.py` rather than beside `bh_within_family`.

Per-file tests, run in master: `tests/platformkit/foundry/test_tiers.py` 11 passed (6 existing + 5
new; one existing test now names a frozen family for its charged tiers, because an unfrozen one no
longer charges), `test_results_db.py` 7 passed, `scripts/platformkit/eval_gate/test_family_bars.py`
9 passed, `test_foundry_runner_s16.py` + `test_grammar.py` + `test_catalogue.py` 22 passed.

## NOT VERIFIED

- No REAL hypothesis has been scored through the dual bar. Every number here is a construct on a
  synthetic corpus with a pinned p-value; the AHEAD in case 2 is a fixture, not a finding.
- `n_family` is 1 for any trial run without a `results_db`, which is the loosest the family bar
  can be. S16's runner does not yet pass its DB through, so the first real promotion batch will
  run at n_family = 1 unless that keyword is wired first.
- `fdr_by` is computed and printed but has never DECIDED a verdict: no frozen family selects it,
  so the BY branch of `dual_bar_verdict` is covered only by the printed values, not by a verdict.
- The PRDS assumption behind BH on a family of correlated parquet columns is still unmeasured;
  printing BY quantifies the exposure but does not discharge it.
- `_n_eff = 6.0743` on 30 synthetic rows is a construct artifact of the 6-team fixture, not a
  statement about any real corpus.
