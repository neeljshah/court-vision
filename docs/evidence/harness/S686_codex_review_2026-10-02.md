7. **S686: LAND AFTER FIX**

   - **Confirmed CRLF landing failure:** `scripts/platformkit/oracles/spa_arch_fixtures.py:109` hashes raw checkout bytes. `tests/platformkit/oracles/test_spa_arch_crosscheck.py:77` compares that hash to the archived LF identity. The local `spa_test.py` has 150 CRLF endings and hashes to `c0c6f5a0...44def`; the artifact pins `b9c86896...1456c6` at `tests/platformkit/oracles/fixtures/S686_crosscheck_2026-09-30.json:339`.
     **Fix:** normalize CRLF to LF in `sha256_file`; retain the existing LF pins. No `.gitattributes` append is needed.
   - **Failure returns success:** `scripts/platformkit/oracles/spa_arch_crosscheck.py:213` returns zero even when the document says `FAIL`. Line 209 also accepts a matching failed artifact, including one just written with `--write --check`.
     **Fix:** retain the result document and require `row_verdict == "PASS"` for both success paths. Add mocked FAIL cases for normal execution and write/check.
   - **Static verdict test:** `tests/platformkit/oracles/test_spa_arch_crosscheck.py:136` reads the committed artifact and checks its own labels; it does not exercise live classification.
     **Fix:** use `fresh_doc` in this test. Keep archived-artifact reproduction as a separate check.

Only S679 is ready to land unchanged. S686 needs small fixes; the other six have correctness or rail blockers.
   S685 and S686 overlap on `scripts/platformkit/oracles/__init__.py`; retain S686's harmless package docstring at line 1 when combining them.
| private/cloud/S686-2026-09-30 | LAND AFTER FIX | None | CRLF hash failure and successful FAIL exit | S |
**LANDING ORDER:** Land S679 now. After corrections and fresh per-file Windows verification, use S678, S682, S683, S684, S685, S686, S687. There is no mandatory runtime dependency between these eight branches; coordinate the shared oracle initializer. Keep S678's real three-day acceptance open after its tooling lands.
