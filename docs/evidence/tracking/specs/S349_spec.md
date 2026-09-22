GAP S349 | sport harness | worktree harness-h1 | log cx_s349_preflight_binding
# Make the S333 preflight BINDING: no nonzero exit and no missing prerequisite may seal (astra round 10 rank 9)

SINGLE PROBLEM: ~/bin/lane_commit.py blocks a seal only when contract_preflight exits 3; any other nonzero exit (python error,
module absent) prints a NOTE and the commit proceeds. scripts/platformkit/tracking/contract_preflight.py passes when the spec is
missing: check_spec_threshold returns ok with "no --spec given", and nothing proves the preregistration was sealed BEFORE a score.

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "no --spec given" scripts/platformkit/tracking/contract_preflight.py` hits;
the repo copy of the hook text is absent (lane_commit.py lives outside the repo at C:/Users/neelj/bin, read-only for this lane).

CHANGE:
1. scripts/platformkit/tracking/contract_preflight.py -- ADDITIVE (existing check names, order, output lines and exit code 3 stay
   byte-compatible; contract B2): new flag `--strict`. Under --strict: (a) a missing --spec, or a spec path that does not exist,
   is a FAIL; (b) new check `prereg_order`: for every path whose basename contains "prereg", the file must carry a seal line and
   the SHA-256 of its LF-normalized bytes above the seal line must equal the stated seal; and if any scored artifact (a path under
   docs/evidence/ with a sibling *.json / *.csv result, or a memo containing a numeric Brier / log-loss / CRPS line) is in --paths
   while the prereg is NOT yet in `git log --format=%H -- <prereg>` on the current branch, FAIL with "prereg not committed before
   scores (Q1)"; (c) new check `source_hashes`: every `sha256:` literal the spec or prereg pins to a repo path must match the file
   on disk. Keep the file <= 300 LOC: move the new checks into NEW scripts/platformkit/tracking/contract_preflight_strict.py and
   import them.
2. tests: NEW scripts/platformkit/tracking/test_contract_preflight_strict.py (mirror the location/style of the existing preflight
   tests -- find them with `ls scripts/platformkit/tracking | grep -i preflight`): inject EVERY failure -- missing spec, absent
   spec path, broken seal, CRLF-written prereg (must still verify after normalization), scores staged without a committed prereg,
   source hash mismatch -- and assert exit 3 for each; assert non-strict mode output is unchanged on the existing fixtures.
3. PROPOSED (not applied; the orchestrator applies it): docs/research/organization-sprint/PROPOSED_lane_commit_strict_2026-09-21.patch
   if docs/research exists in the worktree, else docs/evidence/harness/PROPOSED_lane_commit_strict_2026-09-21.patch -- a unified
   diff for lane_commit.py lines 51-60 so that ANY nonzero preflight exit refuses the seal (message names rc + first stderr line),
   with an explicit override env LANE_COMMIT_ALLOW_PREFLIGHT_UNAVAILABLE=1 that prints a loud NOTE. Quote the current lines from
   the spec-writer's paste below as the diff base:
       if pf.returncode == 3:  ... return 0
       if pf.returncode != 0:  print("LANE_COMMIT NOTE preflight unavailable (rc=%s): %s" % (...))

CONTROLS: infrastructure row, construct tests only, no measured number. Harness thresholds and gate values never move.
ACCEPTANCE: the new per-file test passes; every existing preflight test file still passes, run one file at a time; non-strict
output byte-identical on the replay fixtures. Vocabulary follows contract Q6; automated scan required (assemble any banned-token
pattern from single characters at runtime, as the existing module does with _word()). Memo docs/evidence/harness/
S349_preflight_binding_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF: ignore any pod instruction.
