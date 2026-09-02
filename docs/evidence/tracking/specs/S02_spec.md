GAP S02 | sport soccer (harness) | worktree a11 | log cx_s02_close_join_soccer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q (Q1-Q8) before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md.
GAP (verbatim from the register): soccer gate corpus carries a target but no market close: `p_base` is a Poisson MODEL baseline, so the sport cannot enter walk-forward against a close. Gate corpus EXISTS (25,834 rows) -- this is a close JOIN, not a corpus build.
READ (exact symbols, verified on disk): scripts/platformkit/combo/corpus_cache.py `load_gate_corpus(sport)` :268 and `StaleCorpusError` :48; kernel/validation/proof_metrics.py `devig2(price_a, price_b)` :157 (decimal; FAILS OPEN to (0.5, 0.5) on any price <= 1.0 -- drop bad rows FIRST); scripts/platformkit/eval_gate/shin.py `shin_devig_decimal` :66; scripts/platformkit/eval_gate/walkforward.py `walk_forward(states, predict_fn, select_inside=True)` and `LeakError`; scripts/platformkit/eval_gate/backtest_runner.py `load_states` and `_devig` :54 (American-only -- NEVER call it). Data: data/domains/soccer/matches.parquet, data/domains/soccer/odds.parquet, data/cache/combo/gate_corpus_soccer.parquet. kernel/** is READ-ONLY (human-gated); combo/corpus_cache.py is read-only for this job.
PREMISE (step 0): `load_gate_corpus("soccer")` has NO `devig_close_prob` column; odds.parquet spans 2019-08-02..2026-05-24 with 16,322 rows and 0 null close prices (print the exact close column names you find, e.g. `ou_close_over` / `ou_close_under` or the 1x2 closes). Print all counts. If a close column already exists on the gate corpus, or the odds file is absent, STOP, write the memo, commit, report FALSIFIED / NO DATA.
LIMIT (step 1): the raw join rate of odds rows onto the gate spine by the spine key, measured BEFORE any change and printed. If it is below the bar, STOP and report CLOSED AT LIMIT with the number.
CHANGE (step 2): NEW scripts/platformkit/eval_gate/close_join.py (<=300 LOC). Do NOT edit backtest_runner.load_states, corpus_cache, or the gate-corpus builder.
  @dataclass(frozen=True) JoinSpec(sport, spine, date_col, side_a, side_b, fallback_a, fallback_b, name_a, name_b)
  close_column(odds: pd.DataFrame, spec: JoinSpec) -> pd.Series   # devig2 -> P(y=1); null / zero / <=1.0 prices are DROPPED and COUNTED (the count is exposed)
  gate_corpus_states(sport: str, start: str, end: str) -> list[dict]   # walk_forward-shaped states carrying devig_close_prob
  coverage_report(sport: str) -> dict   # join rate overall / by year / by corpus_unit; bad-price drop count; null-close count; Brier(devigged close) and Brier(p_base) on the joined rows
TEST: NEW scripts/platformkit/eval_gate/test_close_join_soccer.py (beside the module, like the other eval_gate tests): 2.00/2.00 -> 0.5000 exactly; a lopsided pair lands on the correct side; planted bad prices are dropped and the drop count matches; walk_forward smoke on 40 synthetic states raises no LeakError. Run ONLY that file with `python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q`.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = join rate; denominator = 16,322 odds rows 2019-08-02..2026-05-24
  before        = 0 (no close column on the gate corpus)
  bar           = 100.0 pct joined with 0 bad-price drops and 0 null closes; AND Brier(devigged close) < Brier(p_base) on the joined rows (if the close does not beat p_base the JOIN is wrong -- report REJECT yourself)
  n             = 16,322 (scored)
  eye check     = n/a (S-row); reproduction = verifier reruns coverage_report("soccer") in master and reprints the rates and both Briers
  must not move = backtest_runner._devig, corpus_cache (the gate-corpus builder), every threshold under scripts/platformkit/eval_gate/, kernel/**, data/registry/**, data/cache/eval_gate/backtest_fwer.jsonl (13 rows)
NON-TAUTOLOGY: the denominator is ALL 16,322 odds rows; dropped or unjoined rows stay in the denominator and are counted, never removed. No `_charge_ledger` call anywhere (nothing here is a charged trial).
EVIDENCE: docs/evidence/harness/S02_close_join_soccer_2026-09-03.md -- premise counts, the limit rate, the coverage_report output (overall / per-year / per-unit), both Briers, exact commands, test output, a NOT VERIFIED list. Calibration language only (Q6): no dollar, ROI, profit or edge word.
POD: none. Local parquet only.
COMMIT: explicit pathspec (module, test, memo), in this worktree, no push. Last line of your report: `SHA: <sha>`.
NEVER PARK: run everything to completion this turn; never end waiting.
