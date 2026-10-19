# S813 -- the S803 detail read is confined, sha-checked, and a malformed detail keeps the externalized key (PAPER ONLY)

## Premise (measured 2026-10-09 21:3xZ on master 9b40bb209, read-only, scratch tree under s813_scratch, real detail bytes)
- paper_desk_issue_refusals.py:41-44 reads `ctx.read(CACHE + row["detail_path"])` for a row whose refusals is exactly
  {journal_row_externalized: 1}; ctx.path only refuses paths outside the repo. detail_sha256 is never read.
- Probe (scripts in C:\Users\neelj\AppData\Local\Temp\claude\s813_scratch\probe.py), subjects opened / diagnostics:
  genuine real row -> night:2026-10-04/child_exited_during_observation; `journal_details/../decoy.json` holding {} -> [] {};
  real path with sha-mismatched {} detail -> [] {}; detail refusals list / null -> [] {refusals_malformed: 1} (row skipped).
  So a traversal or a tampered detail hides the externalized key, and a malformed detail drops it.
- paper_desk_limits.bound_row writes json.dumps(row, sort_keys=True) + newline and sets detail_sha256 = sha256(that dump);
  all 5 real details re-hash to their file names.

## Change (owned files only; scanner read-only; attention table untouched)
- paper_desk_issue_refusals.py `_detail_refusals(ctx, row)` (101 LOC): resolved path (ctx.path, realpath) must lie strictly
  inside data/cache/paper_desk/journal_details/, else `detail_path_refused` +1. ctx.read as before (unreadable -> keep key).
  If the row carries detail_sha256: sha256(file bytes minus one trailing newline) must equal it, else `detail_sha_mismatch` +1.
  A detail whose refusals is not a dict (list, null, missing) -> `malformed_detail` +1. Each of these returns None and the row
  keeps {journal_row_externalized: 1}, which opens `step_refusal_key <step>/journal_row_externalized` (fail closed).
- test_paper_desk_issue_refusals_s803.py: its `externalized` helper now writes bound_row's bytes and real sha (was "0"*64).

## Clauses
- V1 The real 10-05 night:2026-10-04 row + its real detail (fixtures/s813, byte copies) open child_exited_during_observation, no counter.
- V2 Traversal (`journal_details/../decoy.json`, `../decoy.json`, the directory itself, a path into journal/, an absolute path),
  with the decoy carrying the REAL detail bytes: detail_path_refused 1, journal_row_externalized kept.
- V3 Row sha changed, or detail content changed under the real sha: detail_sha_mismatch 1, key kept.
- V4 refusals list / null / missing, with and without a (matching) sha: malformed_detail 1, key kept. Unreadable detail as before.
- V5 A row without detail_sha256 still reads its detail.
- V6 New tests fail on master's module; every test_paper_desk_issue*.py file passes one per process.
- V7 Read-only re-scan of the real tree at 09-30T23Z, 10-03T23Z, 10-05T16Z, 10-06T07Z: same night subjects as S803, diagnostics {}.
- V8 paper_desk_attention.py and paper_desk_issue_checks.py untouched; no --write / --link run; <= 300 LOC; no $/edge language.

## Fix round 1 (adversarial REJECT on d99c75dea: M6 non-str sha skipped, M11 sibling-dir prefix, M16 race fail-open)
- The sha path hashes and parses ONE read (path.read_bytes -> strict_json) and uses that parse; a failed read or a non-str
  carried sha is detail_sha_mismatch (never compared against a None sentinel). 104 LOC.
- V9 detail_sha256 None / 0 -> detail_sha_mismatch; `journal_details_evil/...` (direct and via `..`) -> detail_path_refused;
  a read failing after ctx.read (sha present or None) -> detail_sha_mismatch; when the two reads differ, the sha-verified bytes are used.

ACCEPTANCE RULE: V1-V9 all hold on the branch diff + per-file test output.
