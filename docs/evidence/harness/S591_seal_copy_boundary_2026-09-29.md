# S591 -- seal_provenance: a git COPY record is an incarnation boundary (2026-09-29)

Row S591 (spec docs/evidence/tracking/specs/S591_spec.md incl. AMENDMENTS 1-2). At fix round 1: master `0f4d51da3f02fa3db61db35b7357da1efd62fb4e`;
worktree HEAD `0f4d51da3f02fa3db61db35b7357da1efd62fb4e` (candidate is uncommitted working-tree changes on top). Provenance language only.
Master moved to the base sha above after the worktree was cut; no file in scripts/platformkit/execution/seal_provenance.py,
the S551 prereg path, or the seal_provenance / s551 test files differs between the two.

## CHANGE
`scripts/platformkit/execution/seal_provenance.py` `_history`: right after a non-delete record is appended,
`if parts[0].startswith("C"): break`. The C record (destination path, its own commit) is kept; every older
record -- the copy SOURCE's history -- is dropped. R records are followed exactly as before; D handling and the
delete-then-re-add boundary are unchanged. Docstring names the copy boundary. File length 300 lines (cap 300;
the module docstring FIX 1d/1f paragraphs and the `_history` docstring were rewrapped to absorb the 2 added lines).
No other behaviour change, no new public name, no attest signature change.

## REAL-REPO BEFORE / AFTER (read-only; declared sha256 = sha256 of `git show 4cff999eec274a484a65e3814737c8f3915c29e7:docs/evidence/forward/exec_policy/PREREG_S551.json`)
declared_sha256 = `ca522ad9e80a0e96b2179c9de47c3eaef65000c1355f6e9c64f0df3c3d800371`

`git log --follow --name-status --format=commit:%H -- docs/evidence/forward/exec_policy/PREREG_S551.json` (git version 2.55.0.windows.5):
```
commit:4cff999eec274a484a65e3814737c8f3915c29e7
C100	tests/platformkit/execution/fixtures/s551_prereg_fixture.json	docs/evidence/forward/exec_policy/PREREG_S551.json
commit:fc0bee00747f64047be1ab0653f5cf601e87d05a
A	tests/platformkit/execution/fixtures/s551_prereg_fixture.json
```
BEFORE (master's seal_provenance.py, loaded from `git show master:`):
```
{"artifact_path": "docs/evidence/forward/exec_policy/PREREG_S551.json", "blob_id": "e50876d1b9d0c83e453ee37604d4f19d8e8d143c", "first_commit_instant": "2026-09-29T21:43:21+00:00", "first_commit_sha": "fc0bee00747f64047be1ab0653f5cf601e87d05a", "resolution": "resolved"}
```
AFTER (this candidate):
```
{"artifact_path": "docs/evidence/forward/exec_policy/PREREG_S551.json", "blob_id": "e50876d1b9d0c83e453ee37604d4f19d8e8d143c", "first_commit_instant": "2026-09-29T21:44:13+00:00", "first_commit_sha": "4cff999eec274a484a65e3814737c8f3915c29e7", "resolution": "resolved"}
```
first_commit_sha moves from `fc0bee00747f64047be1ab0653f5cf601e87d05a` (the fixture's add) to `4cff999eec274a484a65e3814737c8f3915c29e7` (the
copy commit that created PREREG_S551.json); blob_id unchanged (`e50876d1b9d0c83e453ee37604d4f19d8e8d143c`); both instants fall on UTC day
2026-09-29.

## CASES (tests/platformkit/execution/test_seal_provenance_1e.py, 12 tests)
Each copy/rename case first asserts the exact `git log --follow --name-status` line it relies on.
- a: X added 2026-06-01, Y = byte copy 2026-07-01 -> Y's copy commit, instant 2026-07-01T00:00:00+00:00.
- b: `git mv X Y` -> X's add (R followed; asserts `R100`).
- c: copy (t1) then edit (t2): S -> t1, S2 -> t2, never-present bytes -> sha_mismatch.
- d (two tests): delete then re-add same path -> re-add (asserts A/D/A); q deleted then re-added as a copy of an
  older byte-identical z -> asserts `C100 z.json q.json` and NO D line, resolves to the re-add (before: z's add).
- e: X B1 -> X B2 -> Y copy: sha(B1) -> sha_mismatch (before: resolved to X's B1 add); sha(B2) -> Y's copy commit.
- f: real repo, skipif the pinned commit is absent: resolves to the full 40-char `4cff999eec274a484a65e3814737c8f3915c29e7`.
- g: build_receipt (small FamilyWeekLedger built in-test) -> json.dumps(allow_nan=False) -> file -> fresh
  `python -c` subprocess -> tuple(json.loads) -> attested_seal_commit_utc == copy instant 2026-07-06T00:00:00+00:00;
  seal_test_fails at Monday == copy instant -> True (landed contract `instant is None or instant >= boundary`
  -> fails, seal_provenance.py seal_test_fails), one day later -> False, one day earlier -> True.
  validate_attestation is not re-exercised here (needs corpora + a licence seal; covered by 1b/1c).
- h: untracked -> not_tracked; outside the repo -> not_tracked with artifact_path None; non-git repo_root raises
  SealProvenanceError as before; `_history` of a never-existing path -> []; attest key set and resolution values unchanged.
- i (two tests): y copied from x (t1), `git mv y r` (t2), r copied back to y (t3): attest(y) -> t3, attest(r) -> t1
  (asserts `R100 y r` then `C100 x y`; before: x's add). Same-commit `git mv m2 m3` + k = copy of m2: git labels
  k `R100 m2.json k.json` (asserted); attest(k) -> m2's first commit (rename followed, pinned unchanged behaviour).
- j (AMENDMENT 2(a), fix round 1): x = B2 (Jan), x edited to B (Feb), y = B2 (Mar): asserts git's `C0dd x.json y.json`
  (score < 100) and attest(y, sha(B2)) -> y's Mar add (before: x's Jan add). Power: with the mutation
  `startswith("C")` -> `== "C100"` applied and restored, `-k test_j` = 1 failed (the adversarial tier's surviving mutant).

## TEST POWER (fix reverted to `if False:` in the worktree, then restored)
```
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_a_copy_of_older_file_dates_to_copy_commit
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_c_copy_then_edit
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_d_delete_then_readd_as_copy_resolves_to_readd
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_e_older_source_blobs_no_longer_walked
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_f_real_repo_prereg_s551_resolves_to_its_own_copy_commit
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_g_receipt_round_trip_through_landed_consumers
FAILED tests/platformkit/execution/test_seal_provenance_1e.py::test_i_copy_rename_copy_chain
7 failed, 4 passed in 47.96s
```
The 4 that still pass pre-fix are b, d-same-path, h and i-same-commit-rename: exactly the unchanged-behaviour pins.

## PER-FILE RESULTS (final candidate, each file run alone)
```
tests/platformkit/execution/test_seal_provenance_1e.py: 12 passed in 42.48s (fix round 1)
tests/platformkit/execution/test_seal_provenance.py: 16 passed in 18.20s
tests/platformkit/execution/test_seal_provenance_1b.py: 19 passed in 11.96s
tests/platformkit/execution/test_seal_provenance_1c.py: 4 passed in 3.45s
tests/platformkit/execution/test_seal_provenance_1d.py: 11 passed in 4.55s
tests/platformkit/execution/test_s551_prereg_report.py: 10 passed in 13.32s
```

## MANDATORY DISCLOSURES
1. The S551 seal date did not change in practice: before 2026-09-29T21:43:21+00:00, after 2026-09-29T21:44:13+00:00,
   same UTC day 2026-09-29, so no eligibility date moves today.
2. The only behavioural change is the copy (C) case; renames, deletions, delete-then-re-add, not_tracked,
   outside-repo and non-git refusals are unchanged (cases b, d, h, i-rename green before and after).
3. The live docs/evidence/forward/exec_policy/PREREG_S551.json is byte-untouched: `git diff --stat master -- <it>`
   = (empty: byte-untouched vs master); its LF-normalised working sha256 = `ca522ad9e80a0e96b2179c9de47c3eaef65000c1355f6e9c64f0df3c3d800371`.
4. NOT VERIFIED: any repo whose history was rewritten (rebase / filter) after a seal; git versions other than the
   local git version 2.55.0.windows.5 for C detection.
5. Renames are still followed (S444 design): `git mv` of an older fixture onto a seal path, or a copy whose source
   is deleted in the same commit (git labels it R -- measured in case i), still dates the seal to the source's
   first commit. S591 closes only the C path.
6. Merged histories (AMENDMENT 2(c)): if main adds y (Mar) and a side branch adds y as a copy of x (Apr) that is
   merged, --follow lists only the side's C (Apr), so the seal dates to Apr, LATER than y's first existence
   (conservative direction; pre-fix it dated to x's add, false-early). Paths git quotes (tab, non-ASCII) raise
   SealProvenanceError before and after S591. The test repos inherit the global git config.

## NOT VERIFIED
- Behaviour under history rewrites, shallow clones, or other git versions (C/R labelling is git's heuristic).
- Case f is skipped (not failed) in a clone lacking commit 4cff999eec274a484a65e3814737c8f3915c29e7.
- No runtime caller exercised end to end beyond the case-g subprocess; exec_policy_prereg and microstructure_licence are unedited.

## VERIFY ROUNDS
- r1 (2026-09-29): contract tier ACCEPT WITH CORRECTIONS (memo header shas); adversarial tier ACCEPT WITH CORRECTIONS (mutant `== "C100"` survived -> case j; merged-history disclosure). Fixed in round 1 per AMENDMENT 2.
