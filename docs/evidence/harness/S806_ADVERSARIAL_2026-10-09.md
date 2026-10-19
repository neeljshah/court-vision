# S806 adversarial tier (2026-10-09, PAPER ONLY)

Tier: one Opus subagent, read-only on the branch; mutants applied in its own scratch copy
(C:/Users/neelj/AppData/Local/Temp/claude/s806_adv/), every pytest through gate.py, one process at a time.

## Round 1 (candidate ad3af4da2, base 0666dbc99) -- verbatim report

ACCEPT

Baseline: the 6 candidate files pass (6 + 8 + 34 + 17 + 71 + 109). Copied into the scratch tree: signals/ (conftest needs it)
and docs/evidence/harness/S344_tape_fills_2026-09-21.md. After all 16 mutants the tree md5 matched its pre-mutation value.

| id | mutant | result | killing test |
|---|---|---|---|
| M1 | intern keyed by the Decimal value, not as_tuple (merges 1.0 / 1.00) | killed | s806::test_intern_shares_only_identical_decimals |
| M2 | strip also pops event_ticker | killed | s806::test_strip_drops_only...; io::test_schedule_linked_native_states_survive... |
| M3 | strip also pops close_time | killed | s806 x4; s794::test_one_open_handle...; io x12 |
| M4 | strip ignores release (always pops) | killed | s806::test_strip_drops_only_the_prepare_only_keys |
| M5 | release also clears the caller's states list | SURVIVED | NOTE: no output change |
| M6 | _scenario memo keyed by value s, not id(s) | SURVIVED | NOTE: report unchanged, internal fill records change |
| M7 | memo shared across scenarios (ignores the multiplier) | killed | s806 golden; s794 end_to_end; fill_realism x7 |
| M8 | streaming precision: high starts at -1e9, not 0 | SURVIVED | NOTE: no output change |
| M9 | streaming precision: low starts at +1e9, not 0 | SURVIVED | NOTE: no output change |
| M10 | n counts only valid sizes | SURVIVED | NOTE: no output change |
| M11 | run_files stops passing release=True | killed | s806::test_run_files_strips_every_book_row... |
| M12 | row_count computed after the release | killed | s806::test_release_keeps_the_golden_bytes... |
| M13 | strip never called (memory bound removed) | killed | s806::test_run_files_strips...; s806::test_released_input_is_not_resident... |
| M14 | rows[1].clear() removed (visible trade copies kept) | SURVIVED | NOTE: memory only |
| M15 | intern with a fresh dict per side (no sharing across rows) | SURVIVED | NOTE: memory only |
| M16 | intern keyed by (as_tuple, str) | SURVIVED | equivalent mutant: str is fixed by as_tuple |

Result: 8 killed, 8 survived. No survivor changes a fill_realism report byte.

Findings (condensed from the report):
1. No real bug: 32 construct cases (mixed size spellings 1/1.0/1.00, 0.5/0.50, 40/40.00, 3.000, 0; run() and run_files()
   over a two-ticker shard) give the same report sha on master 0666dbc99 and the candidate; run(release=True) = run(release=False)
   in all 16 run cases; internal simulate_fills fill records match master exactly (248 records, qty and queue_ahead_at_submit).
2. M6 is a test gap below the report level: a value-keyed memo merges 0.5*m with 0.50*m and changes queue_ahead_at_submit
   spelling in 102 of 248 internal fill records; that field is not serialised into the report (84 construct cases, sha unchanged).
3. M8 / M9 / M10 cannot change output through fill_realism (unknown_queue 1_000_000 is always in the value stream, so high >= 6
   and low <= 0; _prepare rejects invalid sizes). For direct simulate_fills callers precision can move by at most 1 digit above 28.
4. M14 / M15 are memory-only; no test pins the gain from the trade-list clear or from cross-row interning (measurement table only).
5. M5 changes no output (rows[2] is the visible copy). 6. By reading: nothing after _prepare reads 'book' / 'raw_market'; the
   id-keyed memo is safe (every keyed object stays alive in `prepared`); a raising size is not cached.
Scripts and logs: s806_adv/work/ (mutate.py, runall.py, cmut.py, construct*.py, cmp.py, muts.log, out_*.txt).

## Builder response (fix round 1, commit c87d35247)
- M6: test_scaled_ladders_keep_each_size_spelling (sizes 1.0 / 1.00 at x2 and x8 must keep both spellings); the builder re-applied
  M6 (memo keyed by s) in the worktree: 1 failed, 7 passed; restored: 8 passed.
- M8 (and the contract tier's NON-TAUTOLOGY finding): test_precision_seed_is_decimal_zero_when_every_size_is_fractional calls
  simulate_fills directly with only fractional sizes and unknown_queue_contracts 0.25: precision 33; seed (-1e9, 1e9): 1 failed.
- M9 / M10 / M5 / M14 / M15 / M16: left as NOTES (output-equivalent; M14 / M15 memory-only, covered by the measurement table).

## Round 2 (head d50abf355; no code change since ad3af4da2) -- verbatim verdict, table condensed

ACCEPT

All 16 mutants re-run; 10 killed, 6 survive, no survivor changes a report byte. Baseline test_s806_bound 8 passed; scratch tree code
md5 restored after all mutants (e2d7f3ba...). Tests: s806_bound, s794_index, fill_realism, fill_realism_io, tape_fill_sim,
tape_fill_time_fees, each through gate.py.
| id | result | killing test / note |
|---|---|---|
| M1 | killed | s806 intern + spelling |
| M2 | killed | s806 strip; io schedule_linked |
| M3 | killed | s806 x5; s794 one_open_handle; io x12 |
| M4 | killed | s806 strip |
| M5 | survived | no output change (rows[2] is the visible copy) |
| M6 | KILLED (new) | s806 test_scaled_ladders_keep_each_size_spelling |
| M7 | killed | s806 golden + spelling; s794 end_to_end; fill_realism x7 |
| M8 | KILLED (new) | s806 test_precision_seed_is_decimal_zero_when_every_size_is_fractional |
| M9 | survived | through fill_realism qty 1 and unknown queue 1_000_000 keep low <= 0 |
| M10 | survived | _prepare rejects invalid sizes; direct callers: at most 1 digit of precision |
| M11 | killed | s806 run_files strips |
| M12 | killed | s806 golden bytes |
| M13 | killed | s806 run_files strips; s806 tracemalloc |
| M14 | survived | memory only |
| M15 | survived | memory only |
| M16 | survived | equivalent (str fixed by as_tuple) |
Optional, non-blocking: an invalid-size / integer-free direct case would kill M9 / M10; no test pins the M14 / M15 memory share.
Logs: s806_adv/work/muts_r2.log.
