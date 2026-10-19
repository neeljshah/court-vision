GAP S611 | all D1 sports (schedule writer memory) | worktree nba-harness-h301 | builder: readiness lead (Opus; codex down)
# Stream forward_schedule_writer._latest so the tick's D1 finishes under its 512 MiB producer cap, with byte-identical output

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md A, B1-B11, Q1-Q9 (S-row). PAPER ONLY. Calibration and execution language only.

BEFORE (MEASURED 2026-09-30 00:5xZ-01:0xZ, readiness lead R3):
- forward_schedule_writer.py:57-88 `_latest` appends every accepted row to `groups[key][at]` for every shard in the folder, then keeps `versions[max(versions)]`.
- A streaming count (it never holds rows) of the real books archive: mlb has 9 shards, 905,728 lines and 199,159 snapshot/snapshot_bulk rows (629 MB of JSON text, 1,801 tickers). nfl has 9 shards, 452,461 lines and 98,897 snapshot rows (238 MB, 951 tickers). They are parsed with parse_float=Decimal.
- `schedule_d1 --sports mlb,nfl` on the real roots passed 512 MB of process RSS within 4 s (killed by the rehearsal guard).
- The S500 tick runs schedule_d1 with rss_mib = paper_desk_config max_rss_mib.schedule = 512 (paper_desk_tick.py:130). paper_desk_process.py stops a child over the ceiling with producer_rss_limit. So the tick's first D1, D1(2026-10-01) at 12:00Z 09-30, is stopped.
- The archive grows every captured day.

CHANGE (owned):
- MODIFIED scripts/platformkit/execution/forward_schedule_writer.py: `_latest` only. Same signature, same return and same counters. Stream every line exactly as today, in sorted-path then line order, with the same parse, the same checks in the same order and the same exception mapping.
  - For each accepted row, increment `sizes[key][at]` (a per-key Counter of instants).
  - Replace `best[key] = (at, row)` only when the key is new or `at > best_at` (strict, so the FIRST row seen at the newest instant is kept, as `rows[0]` is today).
  - After the scan, iterate keys in sorted order. For each key, add `n` to the duplicate counter (`duplicate_state_records` / `duplicate_book_records`) for every instant with n > 1, in the landed order.
  - Emit `row` if `sizes[key][best_at] == 1`, else `{"_refusal": "duplicate_records"}`.
  - No other function changes. The file stays <= 300 lines.
- NEW tests/platformkit/execution/test_s611_latest_stream.py (<= 300 lines):
  - (a) Old-vs-new equivalence. The landed `_latest` body is loaded from the pinned base commit via `git show <BASE sha>:scripts/platformkit/execution/forward_schedule_writer.py` into a module. BASE is pinned as a literal sha, never a moving ref. Cases are construct folders covering: multiple shards; duplicates at the newest instant; duplicates only at an older instant; Decimal-equal instants in different textual forms (offset and fractional nanoseconds); future rows; ignored record types; invalid JSON; non-dict rows; missing keys; an empty folder; state=True and state=False. The returned dict must be equal, key order equal, and `counts` equal including key insertion order.
  - (b) Real-row equivalence on the small real folders, with a hard RSS guard of 600 MB. Those folders are books kalshi/nba, kalshi/soccer and kalshi/wnba, and state/soccer, state/nba and state/nfl. The test skips when the data/cache roots are absent (clean clone).
  - (c) A peak bound. A subprocess runs the new `_latest` on the real kalshi/mlb folder (the largest) and asserts peak process RSS < 300 MB. It skips when the root is absent.
  - (d) Test power: a deliberately wrong variant (for example `>=` instead of `>`, or dropping the older-instant duplicate count) makes (a) fail.

INVARIANTS: output and counters are byte-identical to the landed function for every input. schedule_d1 and paper_desk_* are untouched. No config cap is raised. No capture restart is needed, because schedule_d1 is a fresh subprocess each tick.

LANDING: before 11:30Z 2026-09-30, outside the RAM windows (04:20Z-04:50Z, and from 05:40Z until the 09-29 night JSON exists). Per-file tests: test_s611_latest_stream.py, test_forward_schedule_writer.py, test_forward_schedule_soccer.py, test_forward_schedule_local_date.py, test_forward_schedule_local_date_e2e.py, test_forward_schedule_game_key.py, test_forward_schedule_fix1f.py, test_schedule_d1*.py, test_wnba_registration.py.
REAL-ROW PROBE before verify: schedule_d1 with the tick argv into a scratch out-dir (no --write-pointer), under a 512 MB guard. It must exit 0 or with an honest refusal, with peak < 512 MB.
NOT IN SCOPE: the tick side (S582), and the alias gaps (WSH/WAS, JAX/JAC).

AMENDMENT 1 (PRE-BUILD, 2026-09-30 ~01:3xZ; Opus critic in the astra role, VERDICT REVISE; binding). Folded:
(i) TEST POWER. Replace mutant (d). `>=` in place of `>` is an EQUIVALENT mutant, so it cannot fail. Use three real mutants, and (a) must fail on each:
  - drop the older-instant duplicate count;
  - emit the best row when n > 1;
  - update best on `<`, which keeps the oldest instant.
(ii) REAL-ROW EQUIVALENCE (b) runs only on CLOSED shards (UTC date before today). Copy those bytes into tmp_path first, so a live append cannot race the old and new reads.
  - Folders: books kalshi/nba, kalshi/soccer, kalshi/wnba; state/nba, state/soccer.
  - state/nfl is dropped, because the OLD function would hold all its rows.
  - The RSS guard is 600 MB.
(iii) Equivalence (a) and (b) compare list(result.items()) and list(counts.items()) (order-sensitive) plus json.dumps(sort_keys=True, default=str) bytes of the result.
  - The new code creates the duplicate counter key only when n > 1.
(iv) PEAK (c) runs in a child and reads psutil memory_info().peak_wset (Windows) or ru_maxrss. It is opt-in behind the env var S611_REAL_PEAK=1, so routine per-file runs stay cheap. It runs once before landing, outside the RAM windows.
(v) REAL-ROW PROBE before verify: schedule_d1 with the tick argv (--sports mlb,nfl --local-date-tz America/Chicago, the real roots, a scratch --out-dir, NO --write-pointer).
  - It records peak_wset, wall time, free_ram_before and free_ram_min.
  - Bars: peak < 512 MiB; wall < 300 s (the tick allows 600 s); exit 0 or an honest refusal.
  - The probe also measures _latest on state/mlb.
  - OUT OF S611 SCOPE, stated: the tick's other RAM gates. It defers the step below 1,200 MiB free at start (paper_desk_tick.py:66-69) and stops the child below 1,000 MiB free (paper_desk_process.py:176). S611 cannot guarantee free RAM.
(vi) Emit a FRESH {"_refusal": "duplicate_records"} dict per key, never a shared constant. Rows are mutated downstream (forward_schedule_writer.py:209, tally :218).
(vii) LOC: forward_schedule_writer.py stays <= 300 lines. _latest may grow by at most 9 lines, and no new helper function is added. Keep the loop and the try/except structure exactly as they are: UnicodeDecodeError stays outside the try, as today.
(viii) COORDINATION: S531_spec.md:12 lists forward_schedule_writer.py as MUST NOT MOVE. On landing, the register records that S531's must-not-move base for this file moves to the S611 landing sha.

AMENDMENT 2 (fix round 1, 2026-09-30 ~01:2xZ; binding). Contract tier r1 ACCEPT (3 memo notes). Adversarial tier r1 ACCEPT WITH CORRECTIONS: 2,000-case seeded differential fuzz 0 divergences; 8 of 10 mutants killed; survivor 'drop sorted() on keys' because every construct case inserts keys already sorted. FIX: add one construct case whose keys arrive out of sorted order across shards, and a fourth mutant 'unsorted_keys' (sorted(sizes.items()) -> sizes.items()) that (a) must kill. The 'emit last row at the newest instant' mutant is EQUIVALENT (n > 1 always refuses) and needs no test. Notes recorded at landing: (b) runs on a newest-closed subset under a 25 MiB cap and skips when the real roots are absent (the landing run in the main checkout must show them PASSED); the 600 MB guard is the runner's; state/mlb is covered by the adversarial streaming measurement; per-(key, instant) counters and wall time still grow with archive history (~21 s per GB; no retention window) -- future budget item, not an S611 defect.
