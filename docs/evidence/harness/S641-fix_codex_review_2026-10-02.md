**S641-fix-2026-09-30: HOLD**

- Unreadable undated parquet can still appear fresh. `scripts/platformkit/mcp_server/served_asof.py:105` reads only the schema; `:107` returns immediately without reading data pages when `date` is absent. A readable footer with corrupt data pages reaches the mtime fallback at `:162`.
- This violates the readable-undated requirement in `docs/evidence/harness/S641_fix_spec_2026-09-30.md:10`.
  - Fix: insert `pq.read_table(path)` immediately before the no-date return at `served_asof.py:107`.
  - Add an undated-input construct where schema reading succeeds and table reading raises; assert `input_unreadable` and unknown as-of.
- Test gap: `tests/platformkit/mcp_server/test_served_asof_s641_fix.py:100` injects only schema failure; `:105` tests a readable undated fixture.

| private/cloud/S641-fix-2026-09-30 | HOLD | none | Unreadable undated input appears fresh | S |

LANDING ORDER: S631, S594, corrected S653-S656 fix, corrected S641 fix after re-verification, corrected S659 after re-verification, then corrected S690. Corrected S658 and S646 remain parked until their respective landing conditions are satisfied.
