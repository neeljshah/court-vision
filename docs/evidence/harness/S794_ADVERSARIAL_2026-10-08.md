# S794 adversarial verifier (tier 2) on f21cab588 -- 2026-10-08

VERDICT: ACCEPT WITH CORRECTIONS (on f21cab588; PAPER ONLY; execution-quality language only)

Probes ran on f21cab588 (mutations in a git-archive copy, s794_adv/tree). Old code = s794_scratch/oldcode
(= a54598220 modulo CRLF).

## Findings

1. CORRECTION (contract tier finding, confirmed). fill_realism_index.py:17 (`grouped[book["ticker"]]`),
   :43 (LiveQuotes groups) and tape_fill_sim.py:57: a list ticker raises `TypeError: unhashable type` where
   the old `==` scan returned a fill (probe tk_probe.py, case `list`). A shared NaN ticker object matches
   by identity in the dict. On simulate_fills the NaN case gave the same output bytes in my probe (the loop
   body re-checks `q["ticker"] != ticker`, and queue_ahead only reaches fills), but the queue value differs.
   Neither production caller can reach it: fill_realism `_visible` refuses non-str tickers
   (identity_invalid), and exec_policy_replay.phase2 passes one `ticker: str`. Not BLOCKING for night artifacts. Fix: index only `type(ticker) is str`, scan otherwise
   (head 4bceed511 claims exactly this).
2. CORRECTION. fill_realism_io.py:274 progress lines go to stderr, but paper_night.py:143 runs the step with
   `stderr=subprocess.STDOUT`, so the night record's `stdout_last_line` is the merged log. On RAN it is still
   the summary (merged 10-03 rerun: last line = the night's summary). On KILLED, nights 10-06 and 10-07
   recorded `''`; the new code records a progress line, and paper_desk_evidence.py:85-94 then adds
   `stdout_parse_refusals: 1` to that step's outcome. The spec's "stdout unchanged" is true for the
   process, not for the night receipt. Fix: state this in the spec MUST-NOT-MOVE notes and pin it with a
   test, or accept it as the intended kill diagnostic in writing.
3. CORRECTION (test gap). Mutant M7 (`ahead` = dict miss -> 0 for every no-side quote) passes
   test_s794_index.py and test_fill_realism.py, yet changes 230 of my 300 dense cases. The end-to-end
   equivalence test swaps LiveQuotes and PrintTape only, not first_sizes or book_times. Fix: in
   test_index_equivalence_end_to_end, also monkeypatch `fill_realism.first_sizes` with a naive scan-backed
   mapping and tape_fill_sim `latest_books` with the old filter.
4. NOTE. Handles (fill_realism_index.py:111) keeps one buffered handle per path. Correct for append-only shards;
   stale bytes if a shard were rewritten in place.
5. NOTE. The 10-05 growth replay is not tautological: probe.py appends real D+1 rows (tail05.jsonl) and
   never reads the committed artifact; the 164-line cut is one fitted parameter (row_count and
   future_records). The old and new code agree on the uncut inputs (f42e174c both).

## Reproduced

- Equivalence, old vs new, same entry points, byte-identical outputs: 3,000 random simulate_fills cases
  (ties at one ts, both sides, duplicate books, out-of-order books, empty books, prints before the first
  book, arrival and end boundaries, latencies, replacements, sizes NaN/inf/-1/many-digit Decimal/str/float),
  987 with fills; 400 fill_realism.run cases (shuffled rows, duplicate books, NaN/inf counts); 300 dense
  valid cases (4,235 fills; queue_not_depleted, quote_already_filled, price_above_quote,
  outside_quote_life all nonzero); 40 run_files shard cases. 0 divergences, 0 exceptions.
- A1 10-03 independent rerun (copied inputs, night argv): sha256 d4226ab7... = committed; 34.8 s; peak
  361 MB; stdout = the night's summary line; stderr = 136 progress lines only.
- LOC 127/300/294/295/165; no non-ASCII; no banned vocabulary in the diff, spec or memo.
- test_s551_replay 14, test_s551_cancel_policy 20, test_s693_paper_exec_model 17 pass; isolation
  closure case passes.

## Mutation table (test_s794_index.py + one file)

| id | mutation | result |
|---|---|---|
| M1 | latest_books bisect_right -> bisect_left | caught |
| M2 | latest_books keeps one tied book | caught |
| M3 | book_times sort by position only | caught |
| M4 | LiveQuotes returns arrival order | caught |
| M5 | PrintTape walk drops last in-life print | caught |
| M6 | PrintTape skipped count 0 | caught |
| M7 | ahead dict miss -> 0 (no side) | SURVIVED (finding 3) |
| M8 | Handles reuses one stale handle | caught |
| M9 | Handles drops seek | caught |
| M10 | fill_quantities overwrites not sums | caught |
| M11 | LiveQuotes sweep arrival+1 | caught |
| M12 | first_sizes keeps last size | caught |

## NOT VERIFIED

- A1 10-05 growth replay, A2 (10-06 120.7 s), A3 timing: not rerun.
- isolation test_pinned_baseline case: needs a git repo (my copy is an archive).
- Head 4bceed511: not reviewed. Re-check there: finding 1 fix on both index sites plus `_queue`;
  rerun eq_probe.py, dense_probe.py, tk_probe.py old vs new; M7 with the strengthened test; A1 10-03
  sha; LOC <= 300 on tape_fill_sim.py (295 before the fix).
