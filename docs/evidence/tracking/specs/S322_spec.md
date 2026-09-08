GAP S322 | sport nba | worktree aX | log cx_s322_sim_diagnostics

**DIAGNOSTIC ROW (S register; astra 2026-09-08 possession-simulator hypotheses A, B, C).** `src/`, `kernel/`,
`api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/ingame/`. NEVER write
`data/registry/`, never flip a flag, never claim an edge (calibration language only), never edit a landed
memo or artifact, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Inputs are CACHED
predictions only: the S287 artifacts (`docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04/
S287_selected_tick_series.csv`, `S287_summary.json`, the per-game series) and the S317 v2 series
(`docs/evidence/harness/S317_series_schema_2026-09-08/`: per tick p_market, p_null, p_simulator, outcome;
2,130 ticks, 355 clusters). NO new simulator rollout in this row. S316 (cross-environment parity) is a
separate prerequisite for any rollout and is not re-scored here.

**WHY THIS ROW EXISTS.** S287 measured the possession Monte Carlo simulator BEHIND at construct scale
(improvement vs the recalibrated null -0.105, 95 pct CI entirely below 0; Brier 0.257 vs market 0.152). Before
any more simulator compute, the three structural reasons a possession-level simulator loses to a recalibrated
null must be separated: (A) wrong state/target semantics (side polarity, remaining vs final score, clock or
overtime), (B) wrong transition law (independent possessions miss ownership, fouling, pace, covariance), (C)
wrong prior/uncertainty (stale team rates displace M0; plug-in pace/lineups omit mixture uncertainty). Each
has a cheap diagnostic on cached outputs; the decision is whether simulator expansion continues.

**PREMISE (step 0, BINDING before-condition):** load the v2 series; PRINT n ticks, n clusters, and recompute
S287's three Brier values to 1e-9 (S317 showed max difference 0). **If they do not reproduce, the premise is
FALSE (the cached inputs moved): STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **A -- SEMANTICS TRACE (`s322_semantics_trace.py`, <= 200 lines).** Seal 30 boundary states (earliest
     and latest ticks, tied games, |margin| >= 15, every overtime tick, both venues) and hand-trace each
     through the adapter fields to the output: home side polarity, remaining vs final score, clock, overtime,
     conservation (probabilities sum to 1). Table with a PASS/FAIL per check per state. Bar: 0 errors.
     Frozen-input replay of the cached logits through the recalibration path: tolerance 1e-9 within this
     environment.
  2. **C -- PRIOR / UNCERTAINTY ABLATION (`s322_prior_ablation.py`, <= 250 lines).** On the cached simulator
     logits, fit train-only inside chronological folds over the 355 clusters (whole-game grouping, embargo):
     (i) temperature + intercept on logit(p_sim); (ii) (i) plus M0 anchoring: logit(p) = a + b logit(p_sim) +
     c logit(p_market_pregame) if a pregame M0 exists in the series, else the tick market probability with
     that substitution labelled; (iii) N alone. Held-out Brier / ECE / log score for each with paired
     game-cluster bootstrap CIs (2,000). Decision rule (prereg): if (ii) fails astra bar C against N (Brier
     improvement >= 0.002, CI lower > 0) the memo recommends STOP SIMULATOR EXPANSION until (B) is fixed.
  3. **B -- TRANSITION LAW (conditional).** If historical NBA play-by-play prefixes exist locally (grep
     `data/cache/` for pbp / possession stores; print what exists), take 200 prior-game prefixes and compare
     the simulator's one-step possession-outcome prediction against an empirical transition null (held-out
     transition log-loss with CIs; 0 illegal transitions). If no prefixes exist locally, report BLOCKED with
     the exact absent path; never fabricate transitions.
  4. **TESTS.** A hand-pinned 12-tick construct: the trace catches a planted polarity flip and a planted
     overtime clock error; the ablation reproduces pinned temperature/intercept values; the comparer
     returns the pinned Brier deltas.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** a one-step pass does not establish end-state calibration; the
2,130-tick construct is the S287 restriction, not a season; (C) uses cached logits produced in the pod
environment (S316's cross-environment difference applies).

ACCEPTANCE RULE:
  metric        = premise recomputation; the 30-state trace table; the ablation table (i)/(ii)/(iii) with CIs
                  and n; the (B) result or BLOCKED path; the decision row
  before        = S287 BEHIND with no separation of A / B / C
  bar           = the trace runs on all 30 states with 0 unexplained errors OR every error is listed with its
                  field; the ablation table is complete with CIs; the decision rule is applied as sealed; all
                  tests pass; 0 landed files edited; 0 new rollouts
  n             = 30 sealed states; 2,130 ticks / 355 clusters; 200 prefixes if (B) runs
  eye check     = NONE. Say that.
  must not move = every S287 / S316 / S317 number; `src/`; `data/`; the registers/ledgers
  verdict       = **DONE** with the decision (CONTINUE / STOP SIMULATOR EXPANSION) if the bar holds;
                  **PARTIAL** with the diagnostic that could not run and why.
EVIDENCE: `docs/evidence/harness/S322_sim_diagnostics_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | in-game calibration | S322 | <finding with n> | <VERDICT>`) + `trace.csv`, `ablation.csv` under
`docs/evidence/harness/S322_sim_diagnostics_2026-09-08/` (each <= 5 MB; integer cells zero-padded to 6 digits).
TEST: `tests/platformkit/test_s322_sim_diagnostics.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the 30-state rule, the ablation forms,
folds, the decision rule), the two modules, the tests and the memo skeleton, and exits `PREPARED FOR
FINISHER` with the exact commands; it must NOT run the cached series itself (Q1).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
