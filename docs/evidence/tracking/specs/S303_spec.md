GAP S303 | sport all | worktree a21 | log cx_s303_prereg_committed_object_seals
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: codex test audit (the orchestrator-held codex test audit (local-only; NOT a lane input) section D):
  persisted-artifact seal tests
  read the
  COMMITTED object; they hash a working FILE (raw or normalized) or `git hash-object` of the current file, so a
  dirty working copy passes. The landing recipe (S261 attempt 2d, worktree a13 commit ccb10fe9f) is: `git show
  HEAD:<prereg>` primary; normalized FILE bytes only after `git cat-file -e HEAD:<prereg>` proves absence.
PREMISE: enumerate all 15 audit rows, then name the exact 8 tracked-file hashing tests and 6 unique tracked
  prereg/spec paths; do not call either set 10.
CHANGE (step 1): additive tests/platformkit/test_prereg_committed_object_seals.py: for each of the 6 named prereg
  paths read `git show HEAD:<path>`, normalize nothing, hash the bytes above the seal line, compare to the embedded
  seal; a temporary git repo fixture commits a prereg, dirties the working FILE, and requires the committed bytes
  to be the ones checked; the fallback path is exercised on an uncommitted prereg. Existing tests untouched.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
WHERE: local construct only. POD: n/a; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command>.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = committed-object seal match for 6 unique paths and all 8 tracked-file hashing tests; temp-repo
                  dirty-file and fallback cases.
  before        = 0/8 tracked-file hashing tests use committed-object primary (audit table).
  bar           = 6/6 unique paths match and 8/8 tests use committed bytes; dirty-file and fallback cases pass.
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
  n             = 6 (CONSTRUCT: every unique tracked prereg/spec path named explicitly).
  eye check     = n/a (S-row); reproduction = verifier reruns the test file and one git show by hand
  must not move = every prereg artifact and existing seal test byte-identical; nothing charged
NON-TAUTOLOGY: a mismatching committed seal is a FINDING (list it); the test never rewrites a seal.
EVIDENCE: docs/evidence/harness/S303_prereg_committed_object_seals_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/test_prereg_committed_object_seals.py; run only that file.
REPORT: the 8-test/6-path table, dirty/fallback lines, test line, SHA. No push. NEVER PARK.

## VERSION 2026-09-07b (attempt 2)
ATTEMPT 1 (worktree a21, candidate 3e5b7b7a5) was REJECTED: it counted route NAMES, not behaviour. Committed-primary
stayed 0/8 before and after (docs/evidence/harness/S303_VERIFY_2026-09-07.md lines 3, 6, 7, 33); the current-file reads
are still at S261 test:38, S272 route:40, S277 route:28, S265 test:18, S268 test:98, S270 test:21, S273 test:19,
S274 test:32. EVERY acceptance clause above is RETAINED UNCHANGED (6/6 unique anchors match; dirty-file and fallback
cases; no seal ever rewritten; no write to data/ or docs/research/; every existing module byte-identical unless the
CHANGE names it, SHA-256 printed). The clauses below are ADDED and are what attempt 2 is scored on.
CHANGE (2026-09-07b): an ADDITIVE committed-object CHECKER MODULE under scripts/platformkit (new file, <= 300 LOC, no
  existing module edited). For EACH of the eight (reader, sealed path) mappings named below it reads the sealed bytes
  from the COMMITTED OBJECT as PRIMARY -- `git cat-file -p HEAD:<path>`, or `git cat-file -p <recorded landing
  sha>:<path>` where the row records a landing sha -- and falls back to the WORKING FILE only when the object is
  ABSENT, absence being proven by `git cat-file -e HEAD:<path>` returning the not-found status and nothing else.
  A repository or object ERROR (not a git repository, bad revision, unreadable or corrupt object, git not on PATH, any
  other non-zero status) is NEVER treated as absence: the checker exits NON-ZERO naming the reason and the failing path.
THE EIGHT MAPPINGS (preregistered here; all eight anchors verified present at HEAD; the lane names each in its report):
  1. scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py:38
     -> docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md
  2. scripts/platformkit/ingame/s272_ingame_tail_recal.py:40 (route _verify_prereg)
     -> docs/evidence/harness/S272_ingame_tail_recal_prereg_2026-09-04.md
  3. scripts/platformkit/ingame/s277_ingame_market_staleness.py:28 (route _verify_prereg)
     -> docs/evidence/harness/S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md
  4. tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py:18
     -> docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md
  5. tests/platformkit/test_s268_distributional_evaluator_route.py:98
     -> docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md
  6. tests/platformkit/test_s270_ingame_power_feasibility.py:21
     -> docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md
  7. tests/platformkit/test_s273_mlb_ingame_latency_screen.py:19
     -> docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md
  8. tests/platformkit/test_s274_mlb_distribution_evaluator_route.py:32
     -> docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md
OLD TESTS STAY BYTE-IDENTICAL: none of the eight readers above is edited (SHA-256 of each printed before and after).
  Their current-file reads are the FALLBACK path, not the bar; the bar is what the NEW checker SELECTS. This resolves
  the conflict between lines 14/29 (old tests byte-identical) and line 24 (reader behaviour must change) raised as a
  NEW GAP at docs/evidence/harness/S303_VERIFY_2026-09-07.md:35, exactly as the astra finish audit
  (docs/research/astra_harness_finish_2026-09-07.md, package 2) directs: an ADDITIVE committed-object checker covering
  the eight test/path mappings.
ACCEPTANCE RULE (2026-09-07b -- supersedes only the clauses it names; every other clause above still binds):
  metric        = the count of the eight mappings PROVEN BEHAVIOURALLY: per mapping, a case that writes DIFFERENT bytes
                  into the working file at that sealed path and asserts the checker returned the COMMITTED bytes,
                  asserted on CONTENT (the committed bytes or their SHA-256) -- never on a route name, a path string,
                  a list length or a count of names.
  before        = 0/8 committed-primary, remeasured by the verifier on master AND on candidate 3e5b7b7a5
                  (S303_VERIFY_2026-09-07.md:6).
  bar           = 8/8 behavioural cases pass, PLUS the retained committed-seal match on the unique anchors, PLUS four
                  checker-behaviour cases: (a) DIRTY -- working file differs, committed bytes still selected;
                  (b) FALLBACK -- a path not in HEAD inside a fixture repo THAT HAS A COMMITTED HEAD falls back to the
                  working file and reports "fallback"; (c) ABSENT -- a path missing from HEAD is reported as ABSENT,
                  not as an error; (d) ERROR -- a non-repository directory, a bad revision and an unreadable object
                  each exit NON-ZERO with a reason and are NOT counted as absence. Both NEW GAPs in
                  S303_VERIFY_2026-09-07.md (:35 and :36) must be resolved, including the fixture's committed HEAD.
  sign          = n/a for this row. THE FROZEN +0.004 BAR DOES NOT APPLY HERE: S303 is a TEST-AUDIT CONSTRUCT with no
                  loss, no score and nothing charged, so the line 25-26 sign clause is SUPERSEDED FOR THIS ROW ONLY
                  (astra finish audit 2026-09-07, package 2). The row's metric is the 8/8 behavioural count. The
                  +0.004 bar itself is UNCHANGED and still binds every scored row.
  n             = 8 mappings (exhaustive: every audited reader named above) over 8 committed anchors; the retained
                  6-anchor construct is a subset of these, not a replacement for them.
  eye check     = n/a (S-row); reproduction = the verifier reruns the test file, runs the checker by hand, and dirties
                  one anchor's working copy in a scratch fixture to see the committed bytes still selected.
  must not move = the eight readers above and every prereg artifact byte-identical (SHA-256 printed); the +0.004 bar;
                  nothing charged; no register and no ledger write.
NON-TAUTOLOGY (2026-09-07b): every behavioural dirty-file case runs inside a TEMPORARY git repository fixture seeded
  with that anchor's committed bytes -- this repository's tracked working files are NEVER dirtied; the live anchor
  check is read-only against HEAD. A mismatching committed seal is a FINDING (listed, never repaired); the checker
  never writes a seal and never rewrites an artifact.
EVIDENCE (2026-09-07b): docs/evidence/harness/S303_prereg_committed_object_seals_2026-09-07b.md + JSON (NEW dated
  filenames; the 2026-09-04 attempt-1 memo and JSON stay byte-identical).
TEST (2026-09-07b): exactly tests/platformkit/test_prereg_committed_object_seals.py, extended with the eight
  behavioural cases and the four checker-behaviour cases; run that file only (plus the LOC rail file).
REPORT (2026-09-07b): the eight-mapping table with the selection source and the asserted content hash per mapping, the
  four checker-behaviour lines, the anchor seal table, the byte-identity SHA-256 of all eight old readers, the test
  line, and the sandbox SHA line. No push. NEVER PARK.
