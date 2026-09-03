GAP S151 | sport nba (docs) | worktree a12 | log cx_s151_wallclock_provenance
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of section B AND section Q before you report. Template: docs/evidence/tracking/CODEX_SPEC_TEMPLATE.md. Calibration language only: no dollar, ROI, profit or edge words. Never touch data/registry, src/, kernel/, api/, intel/, scripts/team_system/. Per-file tests only (python -m pytest <one file> -q); NEVER the full suite. data/ in this worktree is a read-only junction -- never write under data/. NEVER PARK: run everything to completion this turn; never end waiting. COMMIT: explicit pathspec (git add <paths> && git commit -m "..." -- <paths>), in this worktree, no push. Last line of your report: SHA: <sha>.
GAP (verbatim from the register): nba_wallclock_join.py's provenance was cut to meet the 300-LOC rail (S145): the cdn.nba.com WAF-block rationale, the Kalshi tricode split-at-3 rule, the 'outcome_home_win comes from the ticker's settled result, NOT games.parquet' anti-landmine note, the no-leak join semantics and the output schema now live nowhere. Bar: restore them verbatim to docs/evidence/harness/nba_wallclock_join_PROVENANCE.md linked from the module's 4-line docstring; or declare the rail CLOSED AT LIMIT for this module.
READ: the CURRENT scripts/platformkit/venue_history/nba_wallclock_join.py (282 lines; 4-line docstring) and the PRE-S145 version of the same file from git history (`git log --oneline -- scripts/platformkit/venue_history/nba_wallclock_join.py` and `git show <sha before S145>:scripts/platformkit/venue_history/nba_wallclock_join.py` -- the 36-line docstring lives there); docs/evidence/harness/S145_S149_wallclock_loc_s116_archive_2026-09-03.md and S141_nba_wallclock_tolerance_2026-09-03.md.
PREMISE (step 0): print the old 36-line docstring verbatim from git history and confirm each of the five items above appears in it and in no other tracked file (grep docs/ scripts/ for 'WAF', 'split-at-3' / tricode, 'outcome_home_win'). If the provenance already lives in a tracked doc, STOP and report FALSIFIED.
LIMIT (step 1): n/a.
CHANGE (step 2): NEW docs/evidence/harness/nba_wallclock_join_PROVENANCE.md carrying the old docstring VERBATIM (quoted, with the git sha it came from) plus a one-paragraph 'why it moved' note (the 300-LOC rail, S145) and the S141 staleness rail added since; edit ONLY the module's docstring (keep it <= 6 lines) to say: 'Provenance and invariants: docs/evidence/harness/nba_wallclock_join_PROVENANCE.md' -- no code line changes; the module must stay <= 300 lines. A per-file test that the PROVENANCE doc exists, contains the five items (grep), and the module docstring links it.
TEST: python -m pytest tests/platformkit/venue_history/test_nba_wallclock_join_loc.py -q (must still pass) and the new test.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = provenance items restored to a tracked doc and linked from the module; denominator = 5 items
  before        = 0/5
  bar           = 5/5 verbatim, module <= 300 lines, code lines unchanged (git diff shows only the docstring)
  n             = 5 (CONSTRUCT)
  eye check     = n/a; reproduction = verifier diffs the doc against git history
  must not move = any code line in the module, the 300 s rail, any published number
NON-TAUTOLOGY: the doc text is diffed against the historical docstring, not retyped from memory.
EVIDENCE: docs/evidence/harness/S151_wallclock_provenance_2026-09-03.md (short).
POD: none. Do not ssh anywhere.
