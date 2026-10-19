# S743 cloud result 2026-10-05 -- daily coverage receipt (listed vs selected vs served vs qualified vs scored)

Run: desk-improve cloud routine, ONE-OFF OVERRIDE (row S743 named by the owner, not picked from DESK_STATE).
Branch: cloud/S743-2026-10-05 (base trunk b9d4ecf81). PAPER ONLY. Coverage counts only; nothing scored.
Pre-check: `git ls-remote --heads origin 'cloud/S743*'` was empty before the build.
HARNESS_GAPS_2026-09-03.md and DESK_STATE.md: NOT edited (override rule b).

## Reviewers (codex not available here)
Independent Opus sub-agents, none of which built the code:
- pre-build critic: REVISE (13 items, all folded in as spec AMENDMENT 1);
- CONTRACT tier;
- ADVERSARIAL tier: probes plus 38 single-line mutants.

## Verdicts
| tier | build 98b78721 | fix round 1 2450829f (one re-verify) |
|---|---|---|
| CONTRACT | ACCEPT WITH CORRECTIONS (result memo missing -> this file) | ACCEPT |
| ADVERSARIAL | REJECT (10 surviving mutants, 12 malformed-input crashes, silent zeros) | ACCEPT WITH CORRECTIONS (1: one test for a qualification game without `served`; 2: test file at the 300-line rail) |

How the ADVERSARIAL corrections were handled (final commit):
- Correction 1: the case already existed in the MALFORMED list but was masked by a test-helper bug. `edit()` wrote a popped bool back as the whole file. The helper now keeps in-place edits. Re-checked locally: the `_qual_ok` served-bool mutant now fails the tests (1 failed, 46 passed), and with the source restored all 47 pass.
- Correction 2: no line added. The test file stays at 300 lines; the next edit must split it (NEW GAP).

## Built
- scripts/platformkit/evidence/coverage_receipt.py: CLI, assembly, .md render, atomic write.
- scripts/platformkit/evidence/coverage_receipt_inputs.py: the seven inputs, shape checks, refusals.
- scripts/platformkit/evidence/coverage_receipt_rows.py: per-sport cells.
- tests/platformkit/evidence/test_coverage_receipt.py: 47 CONSTRUCT cases.

Usage: `python -m scripts.platformkit.evidence.coverage_receipt --date D [--root R] [--out-dir DIR]`. Exit 0 means no refusal; exit 3 means refusals were counted (outputs are still written); exit 2 means a bad --date.
Not wired into the tick or the night. Reads only the seven tracked-shape inputs. Writes only coverage/<D>.json and .md, via mkstemp in the target directory and then ops/atomic_replace.replace_with_retry.

## Fixtures (committed copies, newest committed dates)
- schedules: 2026-09-30 (with run.json); 2026-09-24 (no run.json); 2026-09-22 (legacy census and capacity-note names).
- qualification: 2026-09-22.json; 2026-09-24.json (committed 0 bytes, so unreadable).
- scoreboard: 2026-09-24.json.

No committed date has all seven inputs. The exit-0 fixture is real 2026-09-24 schedules plus the real scoreboard, with a run record and a qualification artifact derived from those schedule files. The sport_not_enabled case is SYNTHETIC: no committed input shows a captured sport outside --sports.

## Real receipt: docs/evidence/forward/coverage/2026-09-30.json + .md (exit 3)
| sport | enabled | listed | selected | served | unserved by cause | qualified | scored ticks |
|---|---|---|---|---|---|---|---|
| mlb | yes | 4 | 3 of 4 | 3 of 3 | link_or_alias 1, cap 0 (outside_utc_date 2 of 6 kept apart) | null (qualification_missing) | null (scoreboard_missing) |
| nfl | yes | 0 | 0 of 0 | 0 of 0 | cap 0 | null (qualification_missing) | null (scoreboard_missing) |

Refusals: qualification_missing 1, scoreboard_missing 1. Those two files for 09-30 are not in the clone; nights after 09-24 were not committed here.

Reproduced by both tiers from the committed files:
- 09-24: mlb 9/4/4, not_pregame 3, link_or_alias 2; scored ticks A 1991, B_lag 1966, B/C/D 0 of 1991 emitted (all-sport attempted 2357).
- 09-22: mlb selected 6, served 3, cap 3; qualified FAIL 6 of 6.

Definition: "listed" = the census's schedule-feed games starting on D (games_seen minus outside_utc_date). The inputs carry no count of Kalshi-listed game events, so none is invented.

## Test commands (one file per process)
- `python3 tools/desk_bin/run_files.py . tests/platformkit/evidence/test_coverage_receipt.py` -> 47 passed
- `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q` -> 1 passed

The construct test fails on trunk b9d4ecf81: the module is absent there, so the test errors at import.

## NOT VERIFIED
- Windows re-run of the test file (laptop landing, A1 in master).
- Any date after 2026-09-30: qualification and scoreboard after 09-24 and schedules after 09-30 are not committed in this clone.
- nba / wnba / soccer / tennis coverage: those sports are outside --sports, so the seven inputs cannot see them (the receipt prints this note).
- No data/, capture archive or venue host was read.

## NEW GAP lines (for the orchestrator; no id allocated here)
- The census does not record a per-sport count of Kalshi-listed game events (len of the event index), so "every match Kalshi lists" cannot be checked from tracked inputs. A capture-root or venue-side per-sport list is needed.
- A sport outside the writer's --sports leaves no trace in census, capacity note or run record.
- record_counts and qualification diagnostics carry no totals, so those counters have no exact denominator.
- Legacy and canonical schedule names both present but disagreeing is not noted (canonical wins).
- A sport_not_enabled row prints selected 0; null would match the other cells.
- tests/platformkit/evidence/test_coverage_receipt.py is at exactly 300 lines; the next edit must split it.

PORTABLE: yes.
