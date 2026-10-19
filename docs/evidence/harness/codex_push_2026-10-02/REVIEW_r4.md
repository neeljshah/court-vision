Only S679 is ready to land unchanged. S686 needs small fixes; the other six have correctness or rail blockers.

This was a static, read-only review. No tests or network calls ran. All eight branches have unlanded commits. Every reverse diff against master over the branch's touched paths was empty. The diffs are additive, with no seal-pinned edits, feature activation, field removal, `.gitattributes` changes, secret-like literals found, or code/test files exceeding 300 lines.

Citations below refer to the named branch unless marked `master`.

1. **S678: HOLD**

   - **False ordering acceptance:** `scripts/platformkit/eval_gate/corpus_manifest_git.py:49` extracts only the night's digest; line 66 reads the caller-supplied manifest path. A night can cite an absent path while another previously committed path containing identical bytes makes `order` return `BEFORE`.
     **Fix:** read the path and digest from the same night citation; reject a supplied path that differs. Add a mismatched-path construct.
   - **Registry write route:** `scripts/platformkit/eval_gate/corpus_manifest.py:174` accepts any output directory, including `data/registry`; line 184 writes there.
     **Fix:** refuse lexical and resolved registry destinations before creating the directory or temporary file.
   - **Windows replacement risk:** `scripts/platformkit/eval_gate/corpus_manifest.py:188` uses bare `os.replace`.
     **Fix:** use `replace_with_retry(..., durable=True)` from the existing helper.
   - The mutation and digest tests exercise real logic. However, the register's three consecutive real days remain explicitly unverified at `docs/evidence/harness/S678_cloud_result_2026-09-30.md:62`. Landing tooling must not close that operational acceptance.

2. **S679: LAND**

   The date boundary, backdating guard, token placement, reader compatibility and exact hook exemption are tested meaningfully. The frozen gzip fixture avoids checkout newline changes.

   The documented first-backdated-line escape follows the amended scope: `scripts/platformkit/ledger_audit/ledger_review_lint.py:146` starts enforcement at the first post-cut date. I found no additional blocking defect.

3. **S682: HOLD**

   - **Stale premise silently omits a sealed estimand:** `scripts/platformkit/ops/power_ledger.py:51` permanently declares S644 unsealed; line 156 returns `NOT_SEALED` without consulting disk. Master now has S644's sealed prereg: `docs/evidence/forward/late_game/PREREG_R2.json:102`, with its seal at line 109.
     **Fix:** resolve S644's existing prereg and report its sealed population/floor; preserve the separately declared sport populations.
   - **Test entrenches the stale premise:** `tests/platformkit/ops/test_power_ledger_s682.py:137` requires S644 to remain `NOT_SEALED`, even when its prereg exists.
     **Fix:** construct both absent and present S644 prereg cases instead of asserting permanent absence.
   - **Malformed input becomes successful empty evidence:** `scripts/platformkit/ops/power_ledger.py:224` converts a list or null accrual document into no estimands; the CLI can then write a successful ledger.
     **Fix:** reject non-object top-level accrual before extracting `estimands`; test exit 2 and no artifact.
   - **Finite input can produce non-finite output:** `scripts/platformkit/ops/power_ledger.py:100` can overflow while summing finite differences. Serialization at line 262 sits outside the refusal handler.
     **Fix:** refuse non-finite intermediate/final MDE values and include serialization in the CLI refusal boundary. Add a finite-overflow case.

   The rounding and projection tests otherwise discriminate meaningful arithmetic errors.

4. **S683: HOLD**

   - **Fails on current master:** `scripts/platformkit/ops/interp_determinism_prereg.py:20` has no rule for `PREREG_R2.json`; line 120 therefore marks it `UNRULED`. That prereg is already on master. The archived 61-entry result cannot establish current-master determinism.
     **Fix:** add R2's actual canonical seal and regeneration rules, then regenerate the comparison against the complete current prereg set.
   - **Vacuous success:** `scripts/platformkit/ops/interp_determinism.py:140` accepts two absent schemas as equal; lines 141 and 146 default missing entries/checks to empty maps. Consequently, `compare({}, {})` reports identity. Dropping a check also goes undetected when remaining checks are true.
     **Fix:** require the expected schema, nonempty validated maps, identical check-key sets and valid digest values before comparing. Add empty-manifest and dropped-check cases.
   - **Windows test defect:** `tests/platformkit/ops/test_interp_determinism.py:163` inserts `str(ROOT)` into JSON without escaping backslashes. The scanner at `scripts/platformkit/ops/interp_determinism.py:67` normalizes doubled JSON backslashes, so this test misses its planted Windows path.
     **Fix:** generate that fixture using `json.dumps({"p": str(ROOT)})`.
   - **Registry write route:** `scripts/platformkit/ops/interp_determinism.py:166` writes an unrestricted output path.
     **Fix:** reject lexical and resolved registry destinations before writing.

5. **S684: HOLD**

   - **Inconsistent game denominator:** `scripts/platformkit/evidence/subset_census.py:105` counts distinct universe keys, while line 121 retains duplicates and line 122 uses their list length for the selection bound. Repeating a schedule game changes the reported interval without adding a game.
     **Fix:** validate nonmissing, unique game keys when loading the schedule; refuse duplicates explicitly. Add a duplicate-universe case.
   - **Registry write route:** the output guard at `scripts/platformkit/evidence/subset_census.py:205` protects only `docs/evidence/forward`; line 215 can write into `data/registry`.
     **Fix:** add lexical and resolved registry checks before writing.
   - **Windows replacement risk:** `scripts/platformkit/evidence/subset_census.py:216` uses bare `os.replace`.
     **Fix:** use the existing durable retry helper.

   The Decimal reconstruction, unequal-tick game weighting, bucket boundaries and WITHHELD cases are substantive tests. They do not cover duplicate universe keys.

6. **S685: HOLD**

   - **Registry write route despite contrary help text:** `scripts/platformkit/oracles/dixon_coles_oracle.py:146` says output is never under `data/`, but line 150 opens any supplied destination.
     **Fix:** reject lexical and resolved registry destinations before opening the file; add a CLI refusal case.

   The external kernel comparison and planted tau/lambda mutations exercise real logic. Their execution is conditional: `tests/platformkit/test_dixon_coles_oracle.py:99` skips oracle tests when the dependency is absent. A Windows run with those skips would not establish oracle acceptance.

   S685 and S686 overlap on `scripts/platformkit/oracles/__init__.py`; retain S686's harmless package docstring at line 1 when combining them.

7. **S686: LAND AFTER FIX**

   - **Confirmed CRLF landing failure:** `scripts/platformkit/oracles/spa_arch_fixtures.py:109` hashes raw checkout bytes. `tests/platformkit/oracles/test_spa_arch_crosscheck.py:77` compares that hash to the archived LF identity. The local `spa_test.py` has 150 CRLF endings and hashes to `c0c6f5a0...44def`; the artifact pins `b9c86896...1456c6` at `tests/platformkit/oracles/fixtures/S686_crosscheck_2026-09-30.json:339`.
     **Fix:** normalize CRLF to LF in `sha256_file`; retain the existing LF pins. No `.gitattributes` append is needed.
   - **Failure returns success:** `scripts/platformkit/oracles/spa_arch_crosscheck.py:213` returns zero even when the document says `FAIL`. Line 209 also accepts a matching failed artifact, including one just written with `--write --check`.
     **Fix:** retain the result document and require `row_verdict == "PASS"` for both success paths. Add mocked FAIL cases for normal execution and write/check.
   - **Static verdict test:** `tests/platformkit/oracles/test_spa_arch_crosscheck.py:136` reads the committed artifact and checks its own labels; it does not exercise live classification.
     **Fix:** use `fresh_doc` in this test. Keep archived-artifact reproduction as a separate check.

8. **S687: HOLD**

   - **Future or excluded labels choose the audit method:** `scripts/platformkit/eval_gate/conformal_coverage_audit.py:95` detects kind before cleaning or splitting. `scripts/platformkit/eval_gate/conformal_coverage_core.py:114` examines the entire outcome column. Adding an invalid-date row with `y=2` switches otherwise binary evidence to regression, although cleaning subsequently discards that row.
     **Fix:** determine kind from declared task metadata or cleaned calibration-side rows; freeze it for the test side. Add excluded-row and future-label method-invariance cases.
   - **Reference disagreement does not refuse a verdict:** `scripts/platformkit/eval_gate/conformal_coverage_audit.py:108` stores `reference_agrees`, but line 113 assigns a coverage verdict regardless. The required agreement is merely diagnostic.
     **Fix:** refuse unexpected reference disagreement before producing a verdict, preserving the explicitly allowed regression off-by-one case. Test a forced disagreement.
   - **Fixture generator bypasses the registry guard:** `scripts/platformkit/eval_gate/conformal_coverage_fixture.py:67` writes arbitrary destinations; only the audit CLI checks registry paths.
     **Fix:** apply the registry refusal to the fixture CLI before directory creation.

   `tests/platformkit/eval_gate/test_conformal_coverage_audit.py:90` tests future-label invariance only for a regression fixture, so it misses the method-switch defect.

Windows symlink tests also need explicit capability handling: S678 at `tests/platformkit/eval_gate/test_corpus_manifest.py:265`, S682 at `tests/platformkit/ops/test_power_ledger_s682.py:268`, and S684 at `tests/platformkit/evidence/test_subset_census.py:288` create links unconditionally. Without Windows symlink privileges, they fail before exercising their assertions. Preserve deterministic mocked link/reparse coverage if integration cases are capability-gated.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| private/cloud/S678-2026-09-30 | HOLD | None | Ordering check ignores cited path | M |
| private/cloud/S679-2026-09-30 | LAND | None | None found | - |
| private/cloud/S682-2026-09-30 | HOLD | S644, already on master | Sealed S644 reported unsealed | M |
| private/cloud/S683-2026-09-30 | HOLD | S644, already on master | Current prereg unsupported; vacuous comparison | M |
| private/cloud/S684-2026-09-30 | HOLD | None | Duplicate games alter bound denominator | S |
| private/cloud/S685-2026-09-30 | HOLD | None | Unrestricted registry output | S |
| private/cloud/S686-2026-09-30 | LAND AFTER FIX | None | CRLF hash failure and successful FAIL exit | S |
| private/cloud/S687-2026-09-30 | HOLD | None | Outcome-dependent method and fail-open agreement | M |

**LANDING ORDER:** Land S679 now. After corrections and fresh per-file Windows verification, use S678, S682, S683, S684, S685, S686, S687. There is no mandatory runtime dependency between these eight branches; coordinate the shared oracle initializer. Keep S678's real three-day acceptance open after its tooling lands.