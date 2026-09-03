GAP S232 | sport all | worktree aXX | log cx_s232_intel_foundry_queue_wiring
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: intelligence-derived candidates cannot reach the pod screening runner today, so every family above stays a
one-off script. Three extension points need no shared-module edit: (i) a parquet matching foundry/catalogue.GLOBS
(*states*.parquet, opp_allowed_asof_*.parquet) is enumerated with zero code change, since seed_queue.hypotheses()
reads its columns and grammar.enumerate_family fans them over the frozen alphabet; (ii) a new FWER family is one '###
fam: <name>' block appended to the git-blob-pinned FWER_FAMILIES_SPEC_2026-09-03.md, as S89/S102/S144 did; (iii) a new
predictor may live in a new file (backtest_runner._load_callable takes 'module:callable'). The queue is a SQLite table
(results_db_sql.py:29-31), default data/cache/eval_gate/hypotheses.sqlite, 0 bytes today.
PREMISE (step 0): confirm all three extension points on disk -- that catalogue.GLOBS matches the stated patterns, that
seed_queue enumerates a present parquet without a code edit, and that the families spec parses after an appended
block. If any is false, that is the finding.
LIMIT (step 1): count how many stores proposed by S223-S231 match a GLOB, how many need one NAMED line, and how many
cannot be enumerated at all (undated or below the row floor). That count bounds this wiring.
CHANGE (step 2): additive only -- a queue manifest under docs/ plus one new seeding helper under scripts/platformkit/
that enqueues a declared candidate list into a SEPARATE sqlite path (never the canonical hypotheses.sqlite), dry-run
by default. catalogue.py, seed_queue.py, foundry_runner.py, tiers.py and every eval_gate module stay byte-identical;
any change to them is a PROPOSED snippet under docs/research/.
RAILS: one store at a time, never over 300 MB; never write under data/; never touch the register or the FWER ledger;
no edits under src/ kernel/ api/ intel/ scripts/team_system/ or the token-gated eval_gate modules (PROPOSED snippets
in docs/research/ instead); new helpers <= 300 lines (LOC rail).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = candidate stores enumerated into a queue without a shared-module edit, of those declared
  before        = hypotheses.sqlite is 0 bytes; no intelligence store is in catalogue.NAMED or matches a GLOB
  bar           = every store declared by S223-S231 classified GLOB-REACHABLE / NEEDS-ONE-NAMED-LINE / NOT-ENUMERABLE
      with its reason; a dry-run seed into a scratch sqlite gives a hypothesis count matching grammar.enumerate_family
      exactly; catalogue.py, seed_queue.py, foundry_runner.py and tiers.py byte-identical; hypotheses.sqlite untouched
  n             = every store declared by S223-S231 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the dry-run seed into a fresh scratch sqlite and
      diffs the counts and the four md5s
  must not move = catalogue.py, seed_queue.py, foundry_runner.py, tiers.py, every eval_gate module; hypotheses.sqlite;
      the FWER ledger
NON-TAUTOLOGY: the classification covers every declared store including those that cannot be enumerated, each with the
reason; none is dropped to make the reachable share look better.
EVIDENCE: docs/evidence/harness/S232_intel_foundry_queue_wiring_2026-09-04.md plus the queue manifest and the dry-run
count table. ASCII only, calibration language only; an honest NULL, REJECT or CLOSED AT LIMIT is a success.
TEST: one new per-file test (a dry run seeds nothing; the scratch path is never the canonical one), run only that
file.
REPORT: the three-way classification counts, the dry-run hypothesis count, the four md5s, the test line, SHA. Commit
by pathspec, no push. NEVER PARK.
