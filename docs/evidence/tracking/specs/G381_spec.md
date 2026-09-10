GAP G381 | sport all | worktree a7 | log cx_g381_memo_digest_census

**MEMO DIGEST CENSUS ROW (NEW GAP named by G377 CLOSED AT LIMIT b53a12574: three of G367's memo digests do not identify committed
bytes; G35 open since 2026-09-02: NOT VERIFIED sections nobody swept). A landed memo's SHA-256 line is the only thing that binds a
verdict to the bytes a verifier read; a digest that identifies nothing is an unverifiable claim. This row measures, over EVERY landed
tracking memo on master, whether each printed digest identifies a committed artifact.** Codex PREPARES (prereg, modules, tests, memo
skeleton; NO numbers) and, after the prereg is sealed alone, codex MEASURES on the PC (git history only; no pod; CPU only; PC RAM gate:
free >= 2.8 GB, one python process < 800 MB RSS). `src/`, `kernel/`, `api/`, `intel/` READ only. Build additively in
`scripts/platformkit/tracking/g381_*.py`. NEVER write `data/registry/`, never flip a flag, never edit any landed memo or evidence
file, never touch the register.

**WHERE THIS ROW RUNS:** on the PC in the lane worktree from `git` history only (`git log --diff-filter=A`, `git ls-tree`,
`git cat-file`, `git hash-object --no-filters`); reads nothing under `data/`; writes only its own evidence dir.

**PREMISE (step 0, BINDING before-condition):** enumerate every memo `docs/evidence/tracking/g*_*.md` and `docs/evidence/tracking/G*_*.md`
on master whose text carries at least one 64-hex token, or an 8-to-63-hex token on a line containing `sha` (case-insensitive), and
PRINT: memos / digest tokens / distinct tokens; **if fewer than 30 memos carry a digest, the premise is FALSE: STOP, memo, commit,
report.**

METHOD (sealed before any number):
  1. **CENSUS:** for each digest token record memo path, line number, the artifact the line names (the backticked path nearest the
     token on that line, else NONE), the token and its length.
  2. **RESOLUTION, fixed order, first hit wins:** (a) `git hash-object --no-filters` of the named artifact at the memo's landing
     commit (the first master commit that added the memo) equals the token; (b) the same at HEAD; (c) sha256 of the named artifact's
     content with CRLF normalised to LF at the landing commit; (d) the token equals ANY blob reachable from the landing commit's tree
     of the memo's evidence dir (the same-stem directory); (e) UNRESOLVED. A prefix token resolves only when it matches exactly one
     candidate; two candidates = UNRESOLVED (prefix ambiguous).
  3. **CLASSES:** IDENTIFIES_AT_LANDING (a), IDENTIFIES_AT_HEAD_ONLY (b; the artifact changed after landing -- named), CRLF_ONLY (c),
     ARTIFACT_UNNAMED (d), UNRESOLVED (e) with sub-reason: artifact never committed / pod-only or absolute path / prefix ambiguous /
     token is not a digest (commit sha, seal of a file that is itself the memo, etc.).
  4. **PER ROW:** the G-id from the memo name; resolved / total tokens; the register verdict text for that row (read only, quoted).
  5. **CONVENTION (proposal, evidence dir only):** `PROPOSED_digest_convention.md` -- full 64-hex of `git hash-object --no-filters`
     bytes at the sealing commit, the artifact path on the same line, prefixes never; plus `scripts/platformkit/tracking/g381_lint.py`
     that flags any memo line violating it (wired nowhere; a proposal).
  6. CHANGE NOTHING ELSE; no memo edits; no flag; no src hook.

ACCEPTANCE RULE:
  metric        = digest tokens IDENTIFIES_AT_LANDING / all tokens; per-row share; every UNRESOLVED token named with sub-reason
  before        = no census exists; G377 found 3 of 5 G367 memo digests non-identifying
  bar           = 100 pct of tokens classified (0 UNCLASSIFIED); every UNRESOLVED token NAMED with memo:line and sub-reason; the
                  census reproduces from git history alone (a second run diffs byte-identical); 0 memo edits; the linter flags every
                  UNRESOLVED fixture line and passes a clean fixture
  n             = every landed tracking memo on master (CONSTRUCT; exhaustive enumeration, no sampling)
  eye check     = REQUIRED: 10 evenly spaced UNRESOLVED tokens shown with the memo line and the candidates tried (`eye.txt`)
  must not move = every landed memo, evidence file, seal, bar, flag; the register
  verdict       = **DONE** (every clause) / **PARTIAL** (name the clause) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g381_memo_digest_census_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall time;
SHA-256s -- full 64-hex with the artifact path on the same line) + `.../g381_memo_digest_census_2026-09-10/{prereg,census.csv,
per_row.csv,unresolved.csv,PROPOSED_digest_convention.md,summary.json,eye.txt}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g381_memo_digest_census.py` alone (resolution order fixed; a prefix with two candidates is UNRESOLVED;
CRLF_ONLY is distinct from IDENTIFIES; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6;
automated scan required. Prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
