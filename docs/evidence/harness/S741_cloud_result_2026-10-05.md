# S741 cloud result 2026-10-05 -- books bootstrap keeps same-day games after a restart

Row: S741 (one-off override of the desk-improve routine; row text = `grep '^| S741 ' docs/evidence/HARNESS_GAPS_2026-09-03.md`).
Branch: cloud/S741-2026-10-05 from trunk b9d4ecf8. NOT landed, NOT merged. PAPER ONLY. No venue host contacted.
Spec: docs/evidence/harness/S741_spec_2026-10-05.md with AMENDMENTS 1-3.

## Verdicts
| Round | Tier | Verdict |
|---|---|---|
| pre-build | critique (independent Opus sub-agent, astra role) | REVISE, 12 items -> AMENDMENT 1 |
| 1 (8ac433d8) | CONTRACT (independent Opus sub-agent) | ACCEPT WITH CORRECTIONS |
| 1 (8ac433d8) | ADVERSARIAL (independent Opus sub-agent; 24 mutants, 12 killed; 1 crash probe) | ACCEPT WITH CORRECTIONS |
| 2 (bd2777892) | CONTRACT (fresh independent Opus sub-agent) | ACCEPT |
| 2 (bd2777892) | ADVERSARIAL (fresh independent Opus sub-agent; 34 mutants; all non-equivalent round-1 survivors killed) | ACCEPT WITH CORRECTIONS (3 test-only items -> AMENDMENT 3, folded; each new test confirmed to kill its mutant: N11, M2, N9) |
Codex is not available in the cloud box; every critique and verifier tier was a separate Opus sub-agent that did not build the change.

## Pin check (step -1)
grep of docs/evidence/forward/**/PREREG*.json for schedule_pointer.py, local_capture_runner.py, capture_scheduler.py: 0 hits. The S515 memo seal (docs/evidence/harness/S515_live_shadow_quoter_2026-09-29.md, nine modules) names none of them. schedule_pointer.py is NOT pinned, so it was edited in place (one import plus two changed lines); the logic lives in the NEW module.

## Change
- NEW scripts/platformkit/ingame/schedule_siblings.py (145 lines): open_siblings returns the prior that read_schedule_pointer unions with the target. The prior is the in-memory rows plus every `<date>_maker_forward.json` (the family suffix comes from the target name) beside the target that meets all of these:
  - its day is not closed (D+86400+3600 > now; closed days are never read);
  - its `<date>_run.json` receipt verifies it (D1, exactly one basename entry, strict int bytes, sha256);
  - it parses under the same strict _rows checks;
  - it unions without conflict.
  Siblings are tried in date order, and each passes through the existing union_open_rows, so capacity admission is unchanged. A sibling that conflicts, cannot be verified or is malformed is dropped, and the drop is counted in errors and in schedule_pointer_health. It never blocks the target or raises.
- scripts/platformkit/ingame/schedule_pointer.py 297 -> 298 lines: the :243 prior comes from open_siblings, and the success-path health merge adds the per-read sibling fields.
- Heartbeat fields (in schedule_pointer_health, which both runners spread into the heartbeat). They appear only once a dated in-window candidate has been seen: schedule_sibling_files_loaded, schedule_sibling_rows_loaded, schedule_sibling_files_refused, schedule_sibling_refusals_total (cumulative), schedule_sibling_last_reason, schedule_sibling_files {basename: sha256}.
- Declared deviation: a conflict between a SIBLING and the target or the in-memory rows drops only that sibling. A conflict between the TARGET and the in-memory rows still refuses the whole read, exactly as before (test T8 next to T3).

## Tests (one file per process, Python 3.11.15, `python3 -m pytest <file> -q -p no:cacheprovider`)
| File | Result |
|---|---|
| tests/platformkit/ingame/test_schedule_siblings.py | 25 passed |
| tests/platformkit/ingame/test_schedule_siblings_probes.py | 17 passed |
| tests/platformkit/test_loc_rail_scope.py | 1 passed |
| tests/platformkit/ingame/test_capture_schedule_pointer.py | 35 passed |
| tests/platformkit/ingame/test_capture_schedule_pointer_1c.py | 11 passed |
| tests/platformkit/ingame/test_capture_schedule_pointer_1d.py | 7 passed |
| tests/platformkit/ingame/test_schedule_pointer_bootstrap_seed.py | 8 passed |
| tests/platformkit/ingame/test_schedule_pointer_startup_union.py | 22 passed, 1 failed (baseline) |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1c.py | 4 passed, 1 failed (baseline) |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1d.py | 3 passed, 3 failed (baseline) |
| tests/platformkit/ingame/test_schedule_pointer_startup_union_1e.py | 3 passed |
| tests/platformkit/execution/test_schedule_revise_e2e.py | 22 passed |
| tests/platformkit/execution/test_schedule_pointer_writer_retry.py | 9 passed, 1 failed (baseline) |
| tests/platformkit/execution/test_forward_schedule_local_date_e2e.py | 16 passed |
| tests/platformkit/ops/test_schedule_recovery.py | 9 passed |

All 6 failures are pre-existing on trunk b9d4ecf8 with the same test ids, checked before any edit and again by both contract tiers:
- 4 fakes lack `utc_clock`;
- polymarket heartbeat_ts drifts against the base-commit bytes;
- 1 directory listing order on Linux.

The git-show tests need an unshallowed clone; this run used `git fetch --unshallow`.

Acceptance construct: with schedule_pointer.py reverted to b9d4ecf8, test_schedule_siblings.py gives 19 failed and 6 passed, and T1 (a restart between two published days keeps both days' open rows) is red. The candidate keeps 3 of 3 open rows.

## NOT VERIFIED
- Adoption takes effect only at the NEXT books capture restart on the Windows recorder, and that restart is NOT VERIFIED here. The register's check (heartbeat scheduled_games_total before and after the restart, plus the new schedule_sibling_* fields) is owed by the owner session.
- Windows-only behaviour: path case folding, real receipt keys at runtime, and the relative path from the pointer root data/cache/schedule_pointers to docs/evidence/forward/schedules. These were tested only on Linux tmp_path layouts that mirror it.
- No live capture, no data/ and no real archive were used. Everything is construct-only.
- The polymarket runner was exercised only through refresh_polymarket_pointer, not through a full capture loop.

## NEW GAP lines (from the verifiers; not fixed here)
- A deeply nested pointer TARGET (not a sibling) still raises RecursionError out of read_schedule_pointer (schedule_pointer.py:250 catch list). This predates S741.
- schedule_pointer.py is at 298 of 300 lines. It is a split candidate the next time it is touched.
- A stray far-future `<date>_maker_forward.json` with no receipt adds one refusal per read (about 1440 per day) until it is removed. This is by design: it stays visible in the heartbeat.

PORTABLE: yes (code and tests). Adoption: WINDOWS (one books restart).
