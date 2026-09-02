# S05 attempt 2 -- per-(sport) calibration report (4/4, all FLATTENED)

Gap (register): every calibration piece exists and nothing composes them per
(sport, regime); `docs/evidence/calibration/` held only `foundry_run_*`.

Prereg: `docs/evidence/harness/S05_calibration_prereg_2026-09-03.md`, seal SHA-256
`9051BB6E3BD89F7309A799F9739C8E61EA6DB3530E52AD87666568220591DF8A`, sealed
2026-09-01 23:46:36 -0500 (commit 45e0b4516) -- before any metric here. The seal
re-verifies: SHA-256 over the LF-joined content above the `Seal SHA-256` line,
with no trailing newline, reproduces the embedded digit string exactly. The prereg
file itself was never an ancestor of master (it lived only on the a10 branch); this
row restores it unchanged from 45e0b4516.

Calibration language only. Nothing is charged, promoted or served.
`data/cache/eval_gate/backtest_fwer.jsonl` was not opened; there is no
`_charge_ledger` call anywhere in this row.

## What attempt 1 got wrong, and what changed

The attempt-1 verifier (ledger `e72347e48`) rejected at 3/4 with four named fixes.
All four are addressed:

1. **Run never finished** (codex exit 127; no commit, no memo). This attempt runs
   end to end: memo, pathspec commit, four artifacts.
2. **mlb not scored** (`load_gate_corpus('mlb')` raised `StaleCorpusError`). Fixed by
   the separate row **S41** (commit `9cb019ca4`), which rebuilt the mlb gate corpus
   38,809 -> 39,162 rows with the builder untouched. mlb is now SCORED, so the 4/4
   bar is met without any exemption.
3. **Prereg not named in the artifacts.** Every JSON now carries `prereg_path` and
   `prereg_seal_sha256`.
4. **The artifact did not reproduce itself.** This was the real defect and is
   register gap **S42**: `wp_diagnostics.reliability` binned by `min(9, int(p*10))`
   while `scoring.ece` and `calib_decomp.decompose` bin by numpy edges, so 94 of
   1,814 nba isotonic outputs landing exactly on the 0.1 grid moved 10 rows between
   bins and the published `reliability_bins_after` disagreed with the summary
   (nba ECE 1.10e-4, nba resolution 1.11e-4, soccer ECE 7.74e-5, tennis resolution
   1.95e-5).

**ONE BIN-EDGE RULE.** The published bin table is now produced by
`calibration_report._bin_table`, which uses the SAME rule the summaries use:
equal-width `np.linspace(0, 1, bins + 1)` edges, bin k = `[lo, hi)` for every bin
but the last, which is closed on both sides so `p == 1.0` lands in it. Ten rows are
always emitted; an empty bin is carried as `n = 0` rather than dropped (which is why
the table is a table of 10 and not of the non-empty bins `decompose` keeps).
`wp_diagnostics.reliability` is no longer called by this module.

The module MEASURES the fix instead of asserting it: `build_report` recomputes ECE
and both fitted Murphy terms from its own published bins and publishes the largest
absolute disagreement as `reproduction_max_abs_diff`. **It is 0.0 -- exactly zero,
not "within tolerance" -- on all four sports, before and after.** The reproduction
formulas are published inside each JSON under `reproduction`:

- `ECE = sum_k (n_k/N) * abs(observed_win_freq_k - mean_predicted_prob_k)`
- `Murphy REL = sum_k (n_k/N) * (observed_win_freq_k - mean_predicted_prob_k)^2`
- `Murphy RES = sum_k (n_k/N) * (observed_win_freq_k - base_rate)^2`
- `UNC = base_rate * (1 - base_rate)`

summed over non-empty bins in ascending bin order; `base_rate` is published per report.

A separate lane is landing the S42 fix inside `calib_decomp` / `wp_diagnostics`
(`bin_edges` / `bin_index`, uncommitted in the working tree at the time of this run).
This module deliberately does NOT import it: it is self-contained, so it reproduces
in master whatever happens to that row. Follow-up once S42 lands: `_bin_table` should
import `calib_decomp.bin_edges` instead of rebuilding the array.

## Step 1 -- LIMIT: what each corpus can actually be scored on

Every sport's prediction column is **`p_base`** -- the corpus model probability
(walk-forward Elo for nba/mlb/tennis, the Poisson `p_over25` baseline for soccer).
**No gate corpus carries a devigged close column**, so `devigged_close_column` is
`null` in all four artifacts and nothing here is compared to a market close.

## Step 2 -- results (all four artifacts, `docs/evidence/calibration/<sport>_reliability_2026-09-03.json`)

| sport | scored / input | dropped | ECE before -> after | Murphy REL before -> after | Murphy RES before -> after | UNC | sharpness before -> after | verdict |
|---|---|---|---|---|---|---|---|---|
| nba | 1,814 / 1,814 | 0 | 0.053328 -> 0.024843 | 0.0035146 -> 0.0013466 | 0.0398911 -> 0.0372088 | 0.2481511 | 0.033573 -> 0.040265 | FLATTENED |
| mlb | 39,162 / 39,162 | 0 | 0.005918 -> 0.008077 | 0.0000674 -> 0.0004462 | 0.0040466 -> 0.0039913 | 0.2488327 | 0.003787 -> 0.006063 | FLATTENED |
| soccer | 25,834 / 25,834 | 0 | 0.106927 -> 0.009302 | 0.0161108 -> 0.0007478 | 0.0028144 -> 0.0022363 | 0.2497615 | 0.031968 -> 0.004097 | FLATTENED |
| tennis | 41,886 / 41,886 | 0 | 0.038691 -> 0.008403 | 0.0017829 -> 0.0001393 | 0.0317161 -> 0.0310359 | 0.2498730 | 0.047631 -> 0.034790 | FLATTENED |

`reproduction_max_abs_diff` = **0.0** on all four. Bins emitted 10/10 on all four;
non-empty bins 10 (nba), 6 (mlb), 10 (soccer), 10 (tennis) -- mlb's `p_base` is
concentrated (sharpness 0.003787, base rate 0.534166), so four of its ten bins are
genuinely empty and are published with `n = 0`.

**No sport IMPROVES.** The verdict rule is the sealed one, unmoved: IMPROVES only
when ECE falls AND Murphy reliability falls AND Murphy resolution does not fall.
On nba, soccer and tennis per-regime isotonic buys a large calibration gain and
pays for it in resolution every time (nba -0.0026823, soccer -0.0005781, tennis
-0.0006802), which is exactly the failure the rule exists to catch. **mlb is a
different and honestly worse story**: its `p_base` is already the best-calibrated of
the four (ECE 0.005918, Murphy REL 0.0000674) and recalibration made BOTH ECE and
reliability WORSE. It is labelled FLATTENED because the sealed rule is binary, but
the underlying fact is not flattening -- mlb's sharpness ROSE (0.003787 -> 0.006063).
Recorded, not repaired: the rule is not moved to invent a third label.

The three attempt-1 BEFORE columns reproduce this attempt's BEFORE columns exactly
(nba 0.053328, soccer 0.106927, tennis 0.038691), which is the independent check
that the edge-rule fix changed only the published table, not the measurement.

`max_loser_wp` aggregates are published (quantiles, `above_0_8`, `above_0_9`) but are
DEGENERATE on these inputs and gate nothing -- see NOT VERIFIED and register gap S43.

## Test

`python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q`
-> **6 passed in 2.22s**. Cases: the spec's flattened-toward-0.5 predictor lowers ECE
yet reports FLATTENED with 10 bins and n per bin; the report reproduces its own
summary from its own published bins (< 1e-9, actual 0.0); `_bin_table` agrees with
`scoring.ece` and `calib_decomp.decompose` to < 1e-12 on 500 predictions placed
DELIBERATELY on the 0.1 grid, the exact case where the two old rules disagreed;
below `min_n` -> INSUFFICIENT carrying no metric values; dropped rows counted
(300 in, 2 dropped, 298 scored) never silently removed; every report names its
prereg path and seal.

## ACCEPTANCE

metric = artifact completeness + verdict rule firing; denominator = one artifact per
sport (4). before = 0/4 (attempt 1 landed nothing). after = **4/4**.
n = 1,814 / 39,162 / 25,834 / 41,886 scored rows, every one >= 200, 0 dropped anywhere.
bar = 4/4 with 10 bins + n per bin, max-loser-WP, ECE before/after, three Murphy
terms, sharpness, verdict, prediction column named, dropped-row count -- **met, and
met without the prereg's `INPUT_UNAVAILABLE` exemption**. That exemption (which the
attempt-1 verifier correctly read as a moved bar under Q3) is NOT invoked: the sealed
prereg is left exactly as sealed, the bar stays the spec's 4/4, and the branch is
unreachable because mlb loads. Had mlb still refused, this row would have reported
3/4 INSUFFICIENT with the reason, never a re-defined denominator.
must not move: serving path (`scripts/platformkit/serving_calibration.py` untouched),
all flags, every eval_gate threshold, `data/registry/**`,
`data/cache/eval_gate/backtest_fwer.jsonl` (not opened; no `_charge_ledger`).

## NOT VERIFIED

- **`max_loser_wp` is degenerate here (gap S43).** `event_id` is unique on every row
  of all four gate corpora, so each "game path" is a single tick and the diagnostic
  collapses to the marginal distribution of losing rows' probabilities. nba
  `above_0_8` = 44 and `above_0_9` = 6 are counts of single-row losers, not path
  peaks. It has still never gated a promotion, and this artifact does not gate one.
- **Chronology is positional (gap S44).** The gate corpora carry no date column, so
  `walk_forward_recalibrate`'s expanding window is ordered by row position only.
  Every artifact self-labels this: `order_basis` = `POSITIONAL-ORDER` on all four.
  The rows are stored sorted by the builder's date, but nothing in the corpus proves it.
- `regime_calibration.buckets` assigns confidence terciles from a whole-corpus
  ranking, so the regime KEY is fitted on all rows including the scored one. Only the
  isotonic map is out-of-fold; the key is not.
- `diagnostic_in_sample_isotonic` is in-sample by construction and is labelled a
  diagnostic only. It is not part of any verdict.
- No sport is compared to a market close -- no gate corpus carries one.
- No reliability diagram and no per-regime breakdown table were produced; the
  per-regime fit is exercised but only its pooled effect is published.
- mlb's numbers rest on the S41 rebuild, whose 362 new / 9 dropped event_ids were
  counted but not traced upstream.
