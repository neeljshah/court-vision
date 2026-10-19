GAP S794 | mlb nba (paper night fill_realism: per-ticker replay cost) | worktree cv-s794, branch cxp/S794-2026-10-08 | builder Opus (S794 build lead)
# fill_realism replays each ticker with scans quadratic in its book rows; index them so the night step fits its deadline with byte-identical artifacts
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections A, B, Q (S-row). Citations read on master a54598220. Execution-quality and operations language only; PAPER ONLY.
WHERE THIS ROW RUNS: construct tests on tmp_path and in memory; scratch reruns of the night argv with the output root redirected under C:/Users/neelj/AppData/Local/Temp/s794_scratch/ (inputs hard-linked or prefix-copied there); nothing is written under data/ or docs/evidence/forward/.

PREMISE (re-measured 2026-10-08): night 10-06 fill_realism KILLED at 1200.437 s (nights/2026-10-06.json, step_deadline_exceeded); night 10-07 fill_realism KILLED at 1200.203 s (docs/evidence/forward/nights/2026-10-07.json in the MAIN checkout, untracked at verification time (committed by the morning run); step walls qualification 900.5 s, fill_realism 1200.2 s, e 1800.5 s; the 10-07 argv wall in the memo is measurement only, not an acceptance bar). Night 10-05 RAN in 397.031 s, night 10-03 in 265.094 s.

BEFORE (measured, master a54598220):
- tape_fill_sim.py:55-56 `_queue` filters ALL books per quote (Q x B); :214 loops ALL quotes per print (P x Q).
- fill_realism.py:213 `ahead = next(...)` scans books per quote (Q x B); :214-219 loops every print per quote and, inside, sums over ALL fills (Q x P x F); :198 rebuilds the prepared-row list per fill (F x B).
- fill_realism_io.py:183 opens the input file once per selected row; :199 once per trade row. No progress output (only the final summary line, fill_realism.py:289).
- cProfile top-10 cumulative and the old-code walls: docs/evidence/harness/S794_result_2026-10-08.md.

DESIGN / CHANGE (OWNED: NEW scripts/platformkit/execution/fill_realism_index.py; minimal rewires in fill_realism.py, fill_realism_io.py, tape_fill_sim.py, each <= 300 LOC; NEW tests/platformkit/execution/test_s794_index.py):
1. book_times / latest_books: per-ticker books sorted by time (stable, so list order inside one time is kept) and bisect for the latest time <= submit; `_queue` keeps its size loop, diagnostics and max-over-ties unchanged. Built on the first quote, where the old scan first read b["ticker"].
2. LiveQuotes: quotes grouped by (ticker, side), swept by arrival as the sorted prints advance; yields quotes with arrival < ts < end in the caller's sorted order; the loop body keeps every original condition.
3. first_sizes: dict keyed (ticker, ts, side, price) holding the FIRST size in book and level order (= the old `next(...)`).
4. fill_quantities: Decimal qty keyed (quote_id, trade_id) and the trade ids per quote (= the old inner sum).
5. PrintTape: prints grouped by (ticker, side) in list order with bisect over time; per quote it walks the in-life prints plus every print carrying a fill of that quote, in list order, and counts the rest as outside_quote_life (each skipped print is outside the open life with no fill, the only reason the old loop gave it). Unsorted input falls back to walking every print.
6. The prepared-row list for link_fill is built once per scenario. One open handle per input path in `_load` and `_global_conflicts` (Handles). One progress line per ticker to stderr (`fill_realism progress i/n <ticker> elapsed_s=<s>`); stdout and the summary line are unchanged.
7. (rounds 1-2) Each indexed set carries an exact flag: if any ticker, side or id in it is not plain (exact str or int, or a finite exact Decimal; a str subclass is not plain), every lookup on that set takes the old linear equality scan, so lists, NaN and str subclasses behave as on master.
Alternative NOT taken here: replaying only served tickers (an identity change; own spec).

ACCEPTANCE RULE: A1 scratch reruns of nights 2026-10-03 and 2026-10-05 (night-record argv, output root redirected) are byte-identical (sha256) to the committed fill_realism artifacts, or differ only in named volatile keys proven volatile on the OLD code, with the old-code and new-code scratch artifacts byte-identical to each other; A2 the 10-06 argv finishes under 600 s on a quiet box; A3 a synthetic ticker with 4,000 snapshots and 4,000 prints runs all 8 scenarios under 10 s; A4 the listed fill_realism / tape_fill_sim / qualification isolation test files pass one file per process with their master counts; A5 contract_preflight reports 0 FAIL.
- metric: sha256 of the artifact (A1), wall seconds (A2, A3), per-file pass counts (A4).
- before: committed sha256 d4226ab75501b732591e6c0f2a4cdda6ca97858922518d5b7428c9c490c04f3e (10-03) and 053ddb9b5bcfb1e21045354c0b5c165938e45bb79313acc7aafd2ff1e83c1b6a (10-05); 10-06 killed at 1200 s.
- n = 2 nights for byte identity (CONSTRUCT for the index cases: every case enumerated in test_s794_index.py).
- eye check: replaced by REPRODUCTION (Q7); the memo prints the exact probe commands.
- must not move: every committed receipt; paper_night_budget.json; any seal-pinned file; the fill_realism CLI argv and flags; the summary line format; REFUSALS text and order; fill_realism artifact schema and bytes.

DISCLOSED CHANGE (dispatcher decision 2026-10-08: ACCEPTED IN WRITING as the kill diagnostic): paper_night.py:143 runs each step with stderr merged into stdout, so the night record's stdout_last_line comes from the merged log. On a RAN step it is still the summary line (merged 10-03 rerun). On a KILLED step it is now the last progress line where it was '' (nights 10-06 and 10-07), and paper_desk_evidence.py:85-94 then adds stdout_parse_refusals: 1 to that step's outcome; it is a counter only, and the night status and the step's status, reason and exit code are unchanged. Pinned by test_killed_step_progress_line_is_one_parse_refusal_and_nothing_else (real receipt() on a tmp_path record). paper_night.py and paper_desk_evidence.py are not edited.
NON-TAUTOLOGY: the byte-identity bar compares against artifacts written by master code at night time, not against the new code's own output. The equivalence construct replaces the new indexes with the old full scans inside the same run (NaiveQuotes, NaiveTape) and requires identical reports; the 4,000 x 4,000 timing case is out of reach of the old scans (measured on master code in the memo).

NOT VERIFIED: listed in the result memo.
