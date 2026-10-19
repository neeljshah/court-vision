# S530 cloud result -- per-league soccer cohort report (2026-10-02, cloud routine desk-improve)

PAPER ONLY. Report-only, read-only tooling; calibration and data-quality language only. No verdict, contrast or scored claim is produced by this row.

## Row choice (claim check)
- `git ls-remote --heads origin 'cloud/*'`: every PORTABLE row of AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 2 (S691-S703, S705, S707, S709) and of QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2 (S660, S663, S664, S666-S672, S674-S679, S682-S689) already has a cloud/* branch -> TAKEN. Remaining rows in both slates are WINDOWS.
- DESK_STATE section 4 other unowned PORTABLE rows, reasons skipped: S498/S505/S506 (sealed arm E modules, seal chain), S622 (baseline_four_arm seal-pinned), S639 (soccer_crosswalk/aliases seal-pinned), S546/S547 (dependencies unbuilt), S564/S596/S597/S624/S449/S451 (need live/venue data or capture), S632/S635 (owner decision pending), S579 (unreproducible flake, sweep data), S588/S523 (tick/RAM, WINDOWS side), S600 C (polymarket capture measurement).
- TAKEN: S530 (soccer lane, owner NONE after 09-30 22Z; spec + base AMENDMENT 1 at docs/evidence/tracking/specs/S530_spec.md; construct-only; new files only; no cloud/S530 branch existed).

## Branch and identities
- Branch: cloud/S530-2026-10-02. Candidate HEAD (code): e65614e9a269bfe28c6c972c0e83fd4eab2f0741. Verification base trunk: b16997464c7ee255b8d70d6391b8df77d6ce7d48. NOT EQUAL (branch = base + 3 commits, new files only).
- LF-normalised sha256 (recomputed after the last code edit with `python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read().replace(b'\r\n',b'\n')).hexdigest())" <file>`):
  - aeef9a0ca6c4b557352067260da89d61155f8973779682a0775cf0f2a77a02e2 scripts/platformkit/execution/soccer_cohort_report.py (286 LOC)
  - 7f9b504f6f92a577fecab8e65434dab004a1f47bfb7949fb3582b5c6ad0e53d4 scripts/platformkit/execution/soccer_cohort_counts.py (89)
  - 590fbb477a2435e1c23e55a6b8e90c18cd9275351c4d7b5bbefacbdbcf0b252a scripts/platformkit/execution/soccer_cohort_render.py (66)
  - 5c88527209d5b6c7d88d87ddd15fee9bd07a8e0c6bd48a3f10e214e8ce38c35e tests/platformkit/execution/test_soccer_cohort_report.py (296)
  - 98c771bd99fe68700f6fef101edab559d2ece70c3363fe9fa6a4aaae6822710d tests/platformkit/execution/test_soccer_cohort_report_probes.py (94)
- Spec: docs/evidence/harness/S530_spec_2026-10-02.md (cloud deltas D1-D5, AMENDMENT 1 = 13 pre-build critic items, AMENDMENT 2 = round-1 verifier corrections).

## Tests (one file per process; never the suite)
- `python3 -m pytest tests/platformkit/execution/test_soccer_cohort_report.py -q` -> 43 passed
- `python3 -m pytest tests/platformkit/execution/test_soccer_cohort_report_probes.py -q` -> 14 passed
- Construct property: the module did not exist on base (ImportError); the 14 probe tests run against the round-1 code gave 9 failed / 5 passed (the 5 are mutant killers for behaviour already present).
- Real-repo CLI run (09-29..09-30): exit 0; six league lines per night, listed 0, attribution_complete true, reason no_soccer_rows; absent inputs null with named reasons.

## Verdicts (independent Opus sub-agents; none built the code; codex not available)
- Pre-build critic (astra role): REVISE, 13 items -> folded as AMENDMENT 1.
- CONTRACT tier round 1: ACCEPT WITH CORRECTIONS (Decimal could reach json.dumps via 3 unchecked fields; linked sum rule missing; md not_run; memo missing). Round 2 at e65614e9: ACCEPT (43 + 14 passed).
- UNVERIFIED HISTORICAL REPORT (mutation totals; no committed inventory or reproducible runner): ADVERSARIAL tier round 1: ACCEPT WITH CORRECTIONS (23/28 mutants killed; probes F1-F8). Round 2 at e65614e9: ACCEPT; all 5 earlier survivors killed; 10/12 new mutants killed; survivors N6 (mkdir order, harmless now that no Decimal can reach dumps) and N9 (coverage sport type check, never output).
- Remaining minor, recorded not fixed: the embargo-night fixture omits B/C from arm_order (the real scorer keeps requested arms and counts model_not_reconstructible; the unavailable path is covered by the fitted fixture's ger.1); the JSON/md pair is two atomic writes, not one atomic pair; mutant killers live only in the probes file -> BOTH test files belong to the row's test list.

## Mandatory disclosures (base spec)
- Attribution rule: authority = soccer_leagues.league_of_key(game_key) (imported, not re-implemented); corroboration when present = ticker series prefix == LEAGUES[league].series and tick state.league / state.state.league; a prefix alone never attributes; refused keys (unattributed_key, league_conflict, tie_ticker_served, schedule_duplicate, capacity_ticker_unlisted) are counted in no league and set attribution_complete false.
- served_mid_class is a PROXY (tick mid_age_us p50 vs FRESH_MID_AGE_US = 60 s; equality fresh), not an observation of book record_type; it stands in for S531's focus/bulk split (bulk gap p50 1146.6 s, docs/evidence/tracking/specs/S531_spec.md:6).
- Scoreboard counts are RUN-level (all sports in one scorer run), printed once under run_level_counts, never divided by league; the soccer census refused_by_reason is sport-level, never divided by league.
- No pooled soccer line exists in the JSON or the md.
- Nights 10-09..10-12 are expected to carry no fitted soccer arms (B/C unavailable); the report derives this from the scoreboard, never from a date list.
- Mixed or all-false home_oriented arises only in constructed fixtures today (is_home_ticker raises and the tick is refused, ingame_scoreboard.py:208-211).
- astra 15 (league field inside night_coverage_census) is deferred as S530-F1: the census markdown is re-rendered and compared by paper_desk_evidence census_state, and night_coverage_census.py is at 286/300 lines.

## MUST NOT MOVE
`git diff --stat b16997464c7e HEAD` adds 7 files (spec, this memo, 3 modules, 2 tests) and modifies none: ingame_scoreboard*.py, scoreboard_history*.py, night_coverage_census*.py, soccer_leagues.py, every paper_desk_* / paper_night* file, every seal-pinned file in docs/operations/DESK_STATE.md section 2 and everything under docs/evidence/forward/ are byte-unchanged. DESK_STATE.md and the register were not edited (parallel-branch rule).

## Cloud deltas (declared)
D1 fixtures constructed in-test (no committed fixtures/s530, no .gitattributes edit; S635 pin). D2 three modules for the 300-line cap; AMENDMENT 2 adds a second test file for the same reason. D3 this hand-written memo replaces S530_memo.py. D4 --root and per-consumed-date history maps. D5 strict loader + whole-tree walk reused from scoreboard_history.

## NOT VERIFIED
- Historical mutation totals in the ADVERSARIAL paragraph: unverified historical reports; no committed mutation inventory or reproducible runner is named. The original totals and survivor disclosures are retained as history.
- No real soccer night exists yet (first 10-09; first fitted-history night 10-13); every number here is CONSTRUCT.
- FRESH_MID_AGE_US is not profiled against real soccer ticks.
- Soccer link_paths and per_league population by forward_schedule_writer / forward_schedule_soccer.tally on a real D1 run.
- Windows re-run of both test files on the laptop before landing (not run; Linux only).
- Not wired into paper_night or paper_desk (out of scope; orchestrator decision after the first real run).

PORTABLE: yes.
