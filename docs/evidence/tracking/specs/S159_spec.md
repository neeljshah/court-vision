GAP S159 | sport all | worktree a14 | log cx_s159_public_repo_sweep
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: origin master = the PUBLIC recruiter/buyer-facing repo (github.com/neeljshah/court-vision); a private
backup mirror receives the same commits. The user wants every detail of the public repo perfect: every link
resolves, every doc the entry points name exists, every number traces to an artifact, nothing private tracked.
PREMISE (step 0), all measured READ-ONLY on HEAD and written into the memo with exact denominators:
  (a) markdown links: every relative link in README.md, docs/INDEX.md, docs/PUBLIC_EVIDENCE.md,
      docs/JOB_EVIDENCE_PACKET.md, docs/INTELLIGENCE.md, docs/PLATFORM.md, CLAUDE.md, AGENTS.md -> exists? (n links,
      n broken, list); (b) register/ledger citations: every memo or artifact path cited in
      docs/evidence/HARNESS_GAPS_2026-09-03.md and docs/evidence/RESULTS_LEDGER_SYSTEM.md -> exists? (n, n missing);
  (c) tracked-path hygiene: `git ls-files` contains NOTHING under data/, vault/, .planning/, docs/research/,
      docs/strategy/, and no file matching secrets patterns (sk-, AKIA, ghp_, gho_, api_key=, token=, .env with
      values) -- report counts; (d) retracted figures (+18.38%, 0.119, +54%, 78.11, 8.94, 54.57) appear ONLY inside
      an explicit retraction context (grep every hit, classify each); (e) docs/INDEX.md lists every docs/*.md top-level
      file (n listed / n present); (f) the funnel narrative numbers in README.md match docs/JOB_EVIDENCE_PACKET.md.
LIMIT (step 1): n/a (CONSTRUCT over the enumerated files and links).
CHANGE (step 2): fix ONLY what (a)-(f) found: repair or remove broken links, add missing INDEX entries, wrap any
unframed retracted figure in retraction framing citing JOB_EVIDENCE_PACKET, and NOTHING else. Docs only; no code,
no numbers invented; a missing artifact is REPORTED (not fabricated) with the row/line that cites it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = broken links + missing citations + hygiene hits + unframed retracted figures + INDEX gaps
  before        = the measured counts from (a)-(f)
  bar           = 0 broken links, 0 hygiene hits, 0 unframed retracted figures, 0 INDEX gaps; missing
                  artifacts LISTED in the memo (they are not fixable by docs)
  n             = the enumerated link/citation/file counts (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = the verifier re-runs the same greps/link walk on the worktree HEAD
  must not move = every number in docs/JOB_EVIDENCE_PACKET.md; no file under data/ or vault/; no code file
NON-TAUTOLOGY: every file the entry points reach is in the enumeration; nothing is excluded.
EVIDENCE: docs/evidence/harness/S159_public_repo_sweep_2026-09-04.md -- the (a)-(f) tables before/after, the
missing-artifact list, a NOT VERIFIED list. ASCII only. Calibration language only.
TEST: one new per-file test scripts/platformkit/ops/test_public_repo_links.py that walks the entry-point links
and asserts 0 broken (skip-free; runs in under 10 s); run only that file.
COMMIT: explicit pathspec in the worktree, no push. Report the sha. NEVER PARK; finish with the report + SHA.
