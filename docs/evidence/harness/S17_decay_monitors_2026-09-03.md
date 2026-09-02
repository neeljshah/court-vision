# S17 -- decay monitors (harness). BUILT NOW, ARMED AFTER S20. 3/3 CONSTRUCT. 2026-09-03

## Premise (Q8) -- HOLDS
`ls scripts/platformkit/eval_gate/decay_monitors.py` = No such file. Module absent, row
stands. Before = 0 monitors, not a weaker monitor.

## Real signatures found vs the plan (3 drifts, adjusted to the code on disk)
1. `LedgerRow` is in `eval_gate/ledger.py:19`, NOT `clv_ledger.py` -- that file has no
   `LedgerRow` class and works in plain dicts. Fields `ts, sport, market, inputs_hash,
   prob, outcome`; no `p_close`, no `game_id`. So `monitor_all` takes MAPPINGS (a LedgerRow
   joined to `p_close` + regime fields), building `LedgerRow`s only for `drift_report`.
2. `intraclass_correlation` / `effective_sample_size` (`gap_effective_n.py:30,:62`) take a
   **pandas DataFrame** (`game_column`/`loss_column`, defaults `"game"`/`"loss_differential"`),
   not a row list, and ESS returns a **dict** (`n_ticks, n_games, rho, design_effect,
   n_eff`), not a float. `_ess_frame` builds it with squared error as the loss; a row
   without `game_id` is a singleton cluster -> rho 0.0, n_eff == n.
3. `regime_calibration.buckets(df)` needs `model_prob`/`pred`/`prediction`; `prob` alone
   raises. Rows are shaped with `model_prob` from `prob` before the call.

## What landed
`decay_monitors.py` (234 lines, ASCII). ESS gate FIRST: rho estimated from the MONITORED
window's own rows every call, never a stored constant; `n_eff < 30` -> INSUFFICIENT for all
three. Then (a) calibration decay composes
`ledger.drift_report(rows, now_iso, 7.0, 30.0, k_sigma=1.0)` UNTOUCHED -- it returns
`threshold = baseline_brier + k_sigma * SE`, so its SE is recovered as
`(threshold - baseline_brier) / k_sigma` and re-inflated by `sqrt(design_effect)`, the
clustering factor its independence assumption omits (composed, never re-implemented);
(b) crowding: trailing-30-day mean `|prob - p_close|` below `0.5 x` the first-30-day mean,
no `p_close` -> INSUFFICIENT (missing is not bad); (c) regime drift: scipy chi-square on
`buckets()` key shares, monitored vs fitting window, `p < 0.05`, expected `>= 5` per cell,
smaller merged into `OTHER`. ALL THREE ALARM AND NONE DISABLES ANYTHING -- `monitor_all`
returns a dict, no side effect; `write_report`'s `out_path` defaults to `None` and
nothing was written to `docs/evidence/calibration/` today.

## Test output
`python -m pytest scripts/platformkit/eval_gate/test_decay_monitors.py -q` = **3 passed in
4.78s**. n = 3 (CONSTRUCT); denominator = the 3 enumerated cases, all asserted:
- thin (9 games x 10 rows, loss constant within game -> rho 1.0): n_eff **9.0**, all three
  INSUFFICIENT.
- drifted: crowding 0.02 vs a 0.05 threshold -> ALARM; regime p **2.35e-61** -> ALARM.
- stable: regime p **1.0**, crowding 0.08, calibration recent Brier 0.1111 under a widened
  threshold 0.1167 -> all three OK.

Two defects found BY the stable case, fixed at the root not in the test. (i) One
`buckets()` call over the concatenated union ranked confidence terciles with ties broken
by list position, pushing whichever window came first into lower terciles, so a stable
pair alarmed (p = 0.0) -- now one call PER WINDOW. (ii) A cell in the monitored window
absent from the fitting one reached `chisquare` with expected 0 (divide-by-zero) --
`_merge_small` now reports INSUFFICIENT when `OTHER` cannot reach 5 expected.

## ARMING
Armed only after S20 has **>= 200 settled rows**. Nothing scheduled today: no caller, no
cron entry, no import of this module anywhere in the tree.

## Must-not-move -- confirmed
`ledger.drift_report` byte-identical to master (`ledger.py` is modified in the working
tree, but by the S13 lane appending FWER helpers BELOW line 113; this commit's pathspec
excludes it). No eval_gate threshold touched, no `data/registry/` write, no
`_charge_ledger` call, no FWER row.

## NOT VERIFIED
- No real settled rows monitored; every number is constructed, never the S20 store.
- Crowding and calibration run only at n_eff == n (one row per cluster); the clustered
  path is exercised solely by the thin case, which short-circuits at the gate, so the SE
  widening has never run at design_effect > 1 on data.
- Confidence terciles are window-relative under the per-window `buckets()` call, so a pure
  confidence-distribution shift is invisible to (c); phase/rest/month drift still register.
  Upgrade needs a bucket API accepting fixed cut points.
- The 0.5 crowding ratio and 30-row ESS floor are the spec's bars, not measured operating
  points; no false-alarm rate is estimated. `write_report` never ran with an `out_path`.
