GAP S181 | sport soccer | worktree a17 | log cx_s181_corpus_denominator
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- self-check A/B and section Q (Q1-Q9) before you report. S-row: eye check = n/a, REPRODUCTION replaces it (A2 applies, A3 does not).
PREMISE (step 0): re-run coverage_report('soccer') (scripts/platformkit/eval_gate/close_join.py:262). MEASURED 2026-09-04 in master: denominator 16322, joined 16322, unjoined 0,
join_rate 1.0, scored 16322; all six by_corpus_unit rates exactly 1.0 (D1 2142, E0 2660, E1 3864, F1 2336, I1 2660, SP1 2660). The corpus it claims to cover,
data/cache/combo/gate_corpus_soccer.parquet, is 25834 rows / 25834 distinct event_id: corpus ids WITH odds 16322, WITHOUT odds 9512 (36.8195 pct), odds ids not in corpus 0.
Cause on disk: _joined (:189-213) merges corpus ONTO odds with how='left' from the odds frame, so the denominator is len(odds); only the tennis path _joined_spine_first (:141-179)
joins odds onto the corpus spine. The S35 degeneracy guard (:299-301) is gated on unjoined != 0, so it can never fire on soccer. NOT part of the gap: docs/evidence/RESULTS_LEDGER_SYSTEM.md
line 17 already names the odds-side denominator verbatim; what is undisclosed is HARNESS_GAPS_2026-09-03.md:43 ("100.0 pct joinable") and the return value itself, which carries no
corpus-side field -- so the bar is SURFACE IT IN THE INSTRUMENT, not "it was hidden everywhere". If any premise number differs, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): none needed -- corpus-side coverage is a full census off two small local parquets. If corpus_unjoined measures 0, the premise is falsified: report FALSIFIED, do not fix.
CHANGE (step 2): ADDITIVE ONLY, inside coverage_report. New TOP-LEVEL keys corpus_denominator / corpus_joined / corpus_unjoined / corpus_join_rate, plus a new top-level
by_corpus_unit_spine (unit -> corpus_denominator / corpus_joined / corpus_join_rate), all measured against the gate-corpus spine for EVERY sport (on the spine-first sport, tennis,
they equal the existing values). Extend the S35 guard: ALSO raise when corpus_unjoined > 0 and any per-unit corpus rate == 1.0. Do not touch _joined or gate_corpus_states, do not
change the value of any existing key, no rename, no removal, no new dependency; close_join.py stays <= 300 LOC of logic and ASCII only.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = coverage_report('soccer') corpus-side coverage; denominator = ALL 25,834 rows of data/cache/combo/gate_corpus_soccer.parquet
  before        = denominator 16322 / joined 16322 / unjoined 0 / join_rate 1.0, six per-unit rates all exactly 1.0, and NO corpus-side key in the return (measured 2026-09-04)
  bar           = corpus_denominator 25834, corpus_joined 16322, corpus_unjoined 9512, corpus_join_rate 0.6318030502; per-unit corpus rate 0.6363636364 for D1/E0/E1/I1/SP1 and
                  0.6058091286 for F1 (all to 1e-9); the extended guard raises on a construct with corpus_unjoined > 0 and a 1.0 per-unit corpus rate
  n             = 25,834 corpus rows (full census) + 6 corpus_units + 1 guard construct
  eye check     = n/a (S-row); reproduction = the verifier re-runs coverage_report('soccer') in MASTER and independently recomputes the corpus-minus-odds set difference from
                  data/cache/combo/gate_corpus_soccer.parquet and data/domains/soccer/odds.parquet
  must not move = every key coverage_report returns today (sport, join_key, denominator, joined, unjoined, join_rate, vintage, bad_price_drop_count, null_close_count,
                  valid_close_count, scored, brier_devig_close, brier_p_base, by_year, by_corpus_unit) identical for soccer AND tennis; the S03 bars ATP 84.4 / WTA 71.2
                  unchanged; gate_corpus_soccer.parquet untouched (25,834 rows, sha256 e0d2f13e7a53...); data/registry never written; data/cache/eval_gate/backtest_fwer.jsonl
                  never opened (18 rows, byte-identical)
NON-TAUTOLOGY: the corpus-side metric covers ALL 25,834 corpus rows INCLUDING the 9,512 that have no odds row -- those are exactly the rows today's denominator excludes, and
excluding them is what makes the 1.0 true. Nothing is filtered out: no date window, no matched-only subset, no per-unit exclusion; the 0 odds ids outside the corpus is stated too.
EVIDENCE: docs/evidence/harness/corpus_denominator_2026-09-04.md -- before/after table of the FULL return for soccer AND tennis, the per-unit corpus table with exact
numerators and denominators, the guard construct, the A5 reader grep (the only close_join.coverage_report reader today is scripts/platformkit/eval_gate/test_close_join_tennis.py),
and a "NOT VERIFIED" list. Also copy both return dicts under docs/evidence/harness/ as JSON so every number is reproducible from the artifact alone.
TEST: exactly ONE new per-file test, scripts/platformkit/eval_gate/test_close_join_corpus_denominator.py; run only that file (per-file pytest ONLY -- a full run freezes the box).
Also re-run scripts/platformkit/eval_gate/test_close_join_tennis.py and test_close_join_soccer.py unchanged to prove the existing keys did not move; do not edit either file.
NO CHARGE: this is corpus instrumentation, not a scored trial -- do not call _charge_ledger, do not open the FWER ledger, do not write data/registry/, do not flip any flag ON.
CALIBRATION LANGUAGE ONLY (Q6): no dollar / ROI / profit / edge word in any artifact, memo or row; none of the retracted figures. A FALSIFIED or CLOSED AT LIMIT report is a success.
POD: not needed -- both parquets are small and local. Do not ssh, do not deploy anything.
COMMIT: explicit pathspec, in the worktree, no push. Report the sha.
NEVER PARK: poll your own jobs in a blocking loop; never end a turn waiting.
