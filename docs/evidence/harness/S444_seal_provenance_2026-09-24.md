# S444 -- attested seal provenance and the first countable week

Worktree: harness-h100, master-based, HEAD ea21748ed at start, fast-forwarded
to d0c6f114e before any edit. PREPARE only: nothing wired into a runtime
caller; no nonzero paper quote; nothing sealed by this row (decision 13's own
seal not yet committed on master -- HARNESS_GAPS_2026-09-03.md:555).

## Before-condition (S444_spec.md S2)

`microstructure_licence_inputs.py:107-108` (docstring) claimed resolving a
seal to a git object is "the S395 auditor's job" -- false: no landed module
ever ran `git rev-parse`/`git log`/`hash-object`/`blob` near this area before
this row (`git grep` found nothing but an unrelated asset lister in
`stage_webapp_assets.py:132`). `LicenceSeal.commit_utc` (:133-149) is a
caller-supplied string, never checked against git; `microstructure_licence.py`
R4/R5 (:150-161, pre-row) accepted any caller-forged `commit_utc` with no git
check anywhere. `family_week_ledger.py:18/164-173` counts QUALIFICATION weeks
only; LICENSED QUOTING weeks (the seal-gated subset) did not exist as a
distinct number before this row.

## CHANGE built

NEW `scripts/platformkit/execution/seal_provenance.py` (141 LOC at landing):
`attest(repo_root, artifact_path, declared_sha256)` walks every commit that
touched the path oldest-first (`git log --follow`), hashes each commit's blob
(`git rev-parse`/`git cat-file -p`) against the declared digest -- first match
wins, so a later content change never disturbs an earlier true seal; no match
-> `sha_mismatch`, no commit -> `not_tracked`; committer date (`%cI`, never
author date) via the shared `venue_time.parse_venue_time`. `build_receipt(...)`
adds `ledger.streak(family)` (`qualification_weeks`) and the landed
`_first_counted_monday` import (never re-declared) for `licensed_quoting_weeks`
(0 whenever the seal never resolves to a real git object). Nine-field receipt
schema, four-value closed `status` vocabulary (S444_spec.md CHANGE item 2,
literal). `microstructure_licence.py` (277 -> 289 LOC at landing, additive
only): new `"seal_unattested"` REASONS entry after
`"seal_after_first_counted_week"`; `decide_licence(..., attestation: Any =
None)` -- `attestation is None` reproduces the omitted-keyword path
byte-identical (`test_decide_licence_attestation_none_is_byte_identical`);
when supplied, the seal-provenance functions are imported LOCALLY inside the
`else` branch (not top-level, breaking a real circular import against
`seal_provenance.py`'s own top-level import of `_first_counted_monday`).

## Case table (ACCEPTANCE RULE, n=14 CONSTRUCT, bar 14/14)

All 14 covered plus 2 extra in `test_seal_provenance.py` (16 tests): (1)
sealed 8+ weeks before Monday attests true; (2) commit exactly at the Monday
boundary attests false; (3) commit one second after attests false; (4) streak
0 still resolves; (5) streak 7 attests true, gated downstream; (6) streak
exactly 8; (7) never committed -> not_tracked; (8) sha never matches ->
sha_mismatch (digest format alone is never authentication); (9) a later
content change never disturbs the earlier true seal; (10) two corpora, no
cross-contamination; (11) attestation=None byte-identical to before; (12)
commit-after-first-week -> seal_unattested, qty 0; (13) attested-before ->
sizes exactly as before; (14) a forged early commit_utc buys nothing once
attestation is supplied; extras: committer date wins over author date, a
mid-stream pre-seal week is never counted toward licensed_quoting_weeks. Case-
to-test mapping unchanged from landing -- see `test_seal_provenance.py`
docstrings for the exact assertion per case.

Landing pass counts: `test_seal_provenance.py` 16, `test_microstructure_licence.py`
28, `test_microstructure_licence_inputs.py` 44, `test_loc_rail_scope.py` 1 --
all passed; LOC 141 / 289 / 291 (cap 300 each); preflight 9/9 PASS. Nothing in
the original CHANGE was skipped; the spec's own CHANGE item 1-2 text (not a
looser paraphrase) governed the receipt schema and the git-walk mechanism.

## FIX 1b (AMENDMENTS 1-2, 2026-09-24 21:3xZ, round 1)

codex sol REJECT (2 blockers, 1 correction) then Opus tier 2 REJECT (8 items,
2 new gaps). `_toplevel`/`_repo_relative` (`seal_provenance.py`, new) resolved
`artifact_path` against `--show-toplevel`/`--show-prefix` before any pathspec;
every further git call in `attest()` ran `-C <toplevel>`, never `-C
repo_root` (a subdirectory `repo_root` had resolved pathspecs against the
wrong cwd). `_history` (~line 115) read `--name-status` newest-first, kept
each commit's own historical pathname, skipped `D` records, reversed to
oldest-first -- renames, deletions and delete-then-re-add all resolved
without raising. `any_unattested` replaced by `validate_attestation` /
`seal_test_fails` / `attested_seal_commit_utc` (structural completeness --
exact receipt-key set, matched digest multiset including the licence seal;
temporal recompute per call, never a stored status; audit uses receipt
instants, never a forged `commit_utc`). `microstructure_licence.py` R5
else-branch (289->300 LOC, +11): non-tuple attestation raises
`LicenceInputError`, never `TypeError`. NEW `test_seal_provenance_1b.py` (19
tests, real-git-repo constructs plus direct unit tests). Pass counts:
`test_seal_provenance.py` 16, `_1b.py` 19 (new), `test_microstructure_licence.py`
28, `test_microstructure_licence_inputs.py` 44 -- all passed; preflight 9/9
PASS (4 files).

## FIX 1c (AMENDMENT 3, round 2)

codex sol REJECT (2 blockers); AMENDMENTS 1-2 otherwise confirmed. `_history`
(`seal_provenance.py` ~line 115): a `D` record met newest-first AFTER an
already-seen non-deletion record is now an incarnation boundary -- `break`,
excluding it and every older record, so same-content delete-then-re-add
resolves to the RE-ADD, never the stale original (a `D` met before any
non-deletion record stays a bare `continue`, preserving older history).
`validate_attestation` (~line 221): new `_is_sha256_hex` type-checks
`declared_sha256` before the multiset `sorted(...)` comparison, so a
malformed field (e.g. an int) fails structurally instead of `sorted` raising
`TypeError`. `microstructure_licence.py` untouched (300 LOC, byte-identical
to FIX 1b). NEW `test_seal_provenance_1c.py` (153 LOC, 4 tests: same-content
delete/re-add, deletion-as-newest-preserves-history, non-string
`declared_sha256` direct unit, end-to-end `decide_licence` regression). Pass
counts: 16 / 19 / 4 (new) / 28 / 44 -- all passed; preflight 9/9 PASS (6
files).

## FIX 1d (AMENDMENT 4, round 3)

codex sol REJECT (2 blockers); sandbox could not run tmp_path tests (16/19/4/
28/44 setup errors, no writable temp dir) -- both reproduced and fixed on
this host. Finding 1: `validate_attestation` accepted
`status="unattested_sha_mismatch"` and `first_commit_instant=0` as valid.
Fix, `seal_provenance.py:224-263`: new `_valid_receipt(receipt)` locked
`status == STATUS_ATTESTED` exactly and type/form-validated every field
(64/40-hex ids, zoned-string instants via `parse_venue_time`, non-negative
int counts) before the multiset check. Finding 2:
`artifact_path="../outside.txt"` raised `SealProvenanceError` instead of
returning `not_tracked`, and `build_receipt` stored the caller's raw absolute
input rather than the resolved relative path. Fix, `_repo_relative` (~line
102): lexical `posixpath.normpath` on the prefixed relative path returned
`None` for `.`/`..`/`../`-escapes before any `git` call; `attest()`/
`build_receipt()` (~line 160/203) reported the resolved path on every branch.
Correction: the FIX 1b/1c A9 tables had named a nonexistent path for
`gate_a0_ingame_vs_market.py`; the real path is
`scripts/platformkit/ingame/gate_a0_ingame_vs_market.py`, confirmed
LF-identical to master. NEW `test_seal_provenance_1d.py` (199 LOC, 10 tests).
Pass counts: 16 / 19 / 4 / 10 (new) / 28 / 44 -- all passed; preflight 9/9
PASS (7 files); `seal_provenance.py` 298 LOC.

## FIX 1e (AMENDMENT 5, round 4)

codex sol REJECT (2 blockers). Finding 1: `build_receipt` (~line 217,
pre-fix) used `resolved["artifact_path"] or str(artifact_path)` -- Python's
`or` fell through on `None` and silently stored the caller's raw
outside-repo path, contradicting AMENDMENT 4(b). Fix: the fallback removed --
`"artifact_path": resolved["artifact_path"]` on every branch, `None` when
genuinely outside, never the caller's string; the FIX 1d regression that had
asserted the wrong behaviour was corrected. Finding 2: `decide_licence`'s R5
attestation branch (~line 181, pre-fix) set `audit["seal_commit_utc"]` from
`attested_seal_commit_utc(attestation)` BEFORE `validate_attestation(...)`
ran, so a malformed receipt (e.g. `first_commit_instant=0`) still left a
derived instant in the audit even though the receipt set was rejected. Fix:
`matched = validate_attestation(...)` computed first; `seal_commit_utc` is
`"none"` unless `matched`. Pass counts: 16 / 19 / 4 / 10 / 28 / 44 -- all
passed; preflight 9/9 PASS (7 files).

## FIX 1f (AMENDMENT 6, round 5) -- detailed

Candidate HEAD (this worktree, unchanged by this round):
`317bee09b90d076b1913131a227580e5ea68ced2`. codex sol REJECT (one blocker;
AMENDMENT 5 behaviour otherwise confirmed: invalid receipt -> seal_unattested,
quantity 0, seal_commit_utc none; outside fully qualified path -> artifact_path
None). Verifier's own finding: `_verdict_s444_1f.md` (one BLOCKING; NOT
VERIFIED notes the sandbox again produced 16/19/4/10/28/44 setup errors -- no
writable tmp dir -- so no assertion ran there; the finding below is
reproduced and fixed on this host). `git status --short` at fix time
(unchanged from FIX 1e):

```
 M scripts/platformkit/execution/microstructure_licence.py
?? docs/evidence/harness/S444_seal_provenance_2026-09-24.md
?? scripts/platformkit/execution/seal_provenance.py
?? tests/platformkit/execution/test_seal_provenance.py
?? tests/platformkit/execution/test_seal_provenance_1b.py
?? tests/platformkit/execution/test_seal_provenance_1c.py
?? tests/platformkit/execution/test_seal_provenance_1d.py
```

### Finding 1 (BLOCKING): a drive-less Windows-rooted path escaped `_repo_relative`

Reproduction, quoted from `_verdict_s444_1f.md` item 1 (pre-fix): input
`artifact_path='\outside-s444.txt'` raised `SealProvenanceError: git log
--follow --name-status --format=commit:%H -- /outside-s444.txt failed: fatal:
/outside-s444.txt: '/outside-s444.txt' is outside repository at
'<toplevel>'`. Root cause, `seal_provenance.py:104-105` (pre-fix):
`_repo_relative` branched on `candidate.is_absolute()`; a leading backslash
plus a name (no drive letter) is NOT `Path.is_absolute()` on Windows, so it
fell into the *relative* branch, was joined onto an empty `--show-prefix` and
`posixpath.normpath`-ed to `/outside-s444.txt` -- a string that is neither
`.`, `..`, nor `../`-prefixed, so the old guard let it through as a
seemingly-valid repo-relative path. `attest()` then handed that string
straight to `git log -- <path>`, which refused it as outside the repository
and raised, instead of the function returning `not_tracked` (`None`).

Fix, `seal_provenance.py` `_repo_relative` (post-fix, ~line 95): the
absolute/relative branch is removed. Every input is now joined onto
`Path(repo_root).resolve()` and resolved in one step -- `pathlib` join
semantics mean an absolute or rooted segment (drive-qualified, or a
drive-less rooted path with no drive letter) discards the base the same way,
so all three shapes are handled identically -- then checked with
`relative_to(Path(toplevel).resolve())`; a `ValueError` (outside the
repository top level) returns `None`, never raises. The `--show-prefix` git
call and the `posixpath` import are removed as unused.

After the fix (reproduced on this host, same input, via `attest()` on a
fresh temp repo): `OLD attest()` raised the `SealProvenanceError` quoted
above; `NEW attest()` returns `{'resolution': 'not_tracked', 'artifact_path':
None, 'first_commit_sha': None, 'first_commit_instant': None, 'blob_id':
None}`.

Regression, `tests/platformkit/execution/test_seal_provenance_1d.py` (new):
`test_repo_relative_windows_rooted_path_is_not_tracked_never_raises` asserts
`sp.attest(repo, "\\outside-s444.txt", ...)` returns `resolution="not_tracked"`,
`artifact_path=None`, and that `sp.build_receipt` with the same input returns
`status=STATUS_NOT_TRACKED`, `artifact_path=None` -- never a raise. The other
two AMENDMENT 6(a) cases (a drive-qualified outside path, a relative `../`
escape) were already covered by pre-existing FIX 1d/1e regressions
(`test_repo_relative_absolute_outside_receipt_never_stores_absolute_input`,
`test_repo_relative_relative_outside_is_not_tracked_never_raises`) and
re-verified passing unchanged under the new implementation.

Pass counts (per file, this round): `test_seal_provenance.py` 16,
`_1b.py` 19, `_1c.py` 4, `_1d.py` 11 (10 existing + 1 new),
`test_microstructure_licence.py` 28, `test_microstructure_licence_inputs.py`
44 -- all passed. LOC: `seal_provenance.py` 300 (cap 300; `_repo_relative`
shrank 5 net lines, `posixpath` import removed, a 3-line FIX 1f docstring
bullet added); `test_seal_provenance_1d.py` 227 (cap 300). Preflight 9/9 PASS
(7 files: the two candidate `.py` files, the four test files, this memo).

Nothing in AMENDMENT 6(a) was skipped: the one BLOCKING finding has its
corresponding hunk in `_repo_relative`, `microstructure_licence.py` untouched
(AST-EQUAL below), and the verifier's reproduction is now a decision-level
regression.

## AST-EQUAL (current tree, all fix rounds)

`microstructure_licence.py` has been untouched since FIX 1b; FIX 1c/1d/1e/1f/1g
did not edit it. Docstring-stripped `ast.dump` diff of every top-level
`FunctionDef` vs `317bee09b90d076b1913131a227580e5ea68ced2` (full sha, taken
directly from both `git rev-parse HEAD` in this worktree and `git -C
C:/Users/neelj/nba-ai-system rev-parse master` -- the two are EQUAL at fix
time, not merely related): `_calibration`, `_decision`, `_first_counted_monday`,
`_independence`, `quote_licensed`, `skewed_pads`, `weekly_stop` are all EQUAL;
only `decide_licence` is CHANGED (the AMENDMENT 1-2 `attestation` keyword and
R5 branch, never touched by AMENDMENT 3/4/5/6/7).

## Must-not-move

`microstructure_licence_inputs.py`, `family_week_ledger.py`,
`paper_sizing_inputs.py`, `paper_sizing_policy.py`, `paper_sizing_validate.py`,
`forward_replay_qualification.py`, `quote_engine.py`, `venue_time.py`, and
`scripts/platformkit/ingame/gate_a0_ingame_vs_market.py` -- all nine
LF-normalised-sha256-identical to `git show 317bee09b:<path>`, re-verified
this round. `MATCH_N_MIN` (30), `MATCH_HALF_WIDTH_MAX` ("0.01"),
`TARGET_WEEKS` (8) and `decide_licence`'s R1-R7 rule (attestation omitted) remain untouched.

## A9 (regenerated last)

Candidate HEAD, from `git rev-parse HEAD` in this worktree:
`317bee09b90d076b1913131a227580e5ea68ced2`. Verification base, from `git -C
C:/Users/neelj/nba-ai-system rev-parse master`:
`317bee09b90d076b1913131a227580e5ea68ced2`. The two are the SAME commit at
fix time (the worktree is fast-forwarded to the main checkout's current
`master` tip) -- no behind/descendant gap to report this round. Sizes/sha256
below are the working tree, first 8 hex of raw bytes (all six candidate files
are untracked or LF already, so raw == LF-normalised except the one edited
tracked file):

| file | size | sha256 (raw, 8 hex) |
|---|---|---|
| seal_provenance.py (edited) | 14973 | ebbbc655 |
| test_seal_provenance.py | 15907 | a7c505c3 |
| test_seal_provenance_1b.py | 14789 | fee60605 |
| test_seal_provenance_1c.py | 7163 | d22b93d0 |
| test_seal_provenance_1d.py (edited) | 11335 | 00e34ce4 |
| microstructure_licence.py (unchanged this round) | 15685 | 2adb274f (LF: 0ea0b806) |
| master microstructure_licence.py (LF, for diff, at `317bee09b`) | 13979 | aa107af0 |

## FIX 1g (AMENDMENT 7)

codex sol REJECT (one blocker, memo only; AMENDMENT 6(a) reconfirmed by
probe: drive-less rooted, drive-qualified outside and relative-escape paths
all resolve to `None`, an in-repository path to its normalised relative form
-- no code change this round). The FIX 1e/1f identity statements had carried
a non-existent sha (`66c348b2d4468f9f377a83fa2ab353de3ae17966`, a short-sha
substitution the orchestrator ran over the memo after compaction -- `git
show` on it fails `fatal: bad object`) and a garbled, self-referential
"behind the main checkout" claim. Fixed by replacing every candidate-HEAD/
verification-base statement with the full 40-hex output of `git rev-parse
HEAD` (worktree) and `git -C C:/Users/neelj/nba-ai-system rev-parse master`
taken directly at fix time -- both resolve to
`317bee09b90d076b1913131a227580e5ea68ced2`, so the memo now says they are
equal instead of describing a gap that no longer exists. AST-EQUAL,
must-not-move and A9 above were re-derived against this sha, A9 last.

## NOT VERIFIED

No real seal exists on master today (decision 13's own commit is not yet
made -- HARNESS_GAPS_2026-09-03.md:555), so `attest()`/`build_receipt()` have
never resolved a real artifact, only the temp-repo constructs in this row's
own test files. `qualification_weeks` vs `licensed_quoting_weeks` has never
been computed against a real `FamilyWeekLedger` file. The opt-in
`attestation` keyword has zero callers -- nothing in the tree passes a
receipt tuple into `decide_licence` outside this row's own tests.
`validate_attestation`, `seal_test_fails` and `attested_seal_commit_utc` are
likewise exercised only by this row's construct tests, never a real corpus or
a real licence seal. The sandbox verifier could not run the `tmp_path`-based
construct suites in any fix round (16/19/4/11/28/44 (sol round 7 CORRECTION applied by the orchestrator: _1d holds 11 tests) setup errors, no writable
temp directory); every pass count in this memo was produced on this host,
not the sandbox. The first real run is the owner's own seal commit, attested
after the fact, per S444_spec.md's own REAL RUN line.
