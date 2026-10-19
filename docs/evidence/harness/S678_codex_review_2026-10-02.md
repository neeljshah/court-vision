1. **S678: HOLD**

   - **False ordering acceptance:** `scripts/platformkit/eval_gate/corpus_manifest_git.py:49` extracts only the night's digest; line 66 reads the caller-supplied manifest path. A night can cite an absent path while another previously committed path containing identical bytes makes `order` return `BEFORE`.
     **Fix:** read the path and digest from the same night citation; reject a supplied path that differs. Add a mismatched-path construct.
   - **Registry write route:** `scripts/platformkit/eval_gate/corpus_manifest.py:174` accepts any output directory, including `data/registry`; line 184 writes there.
     **Fix:** refuse lexical and resolved registry destinations before creating the directory or temporary file.
   - **Windows replacement risk:** `scripts/platformkit/eval_gate/corpus_manifest.py:188` uses bare `os.replace`.
     **Fix:** use `replace_with_retry(..., durable=True)` from the existing helper.
   - The mutation and digest tests exercise real logic. However, the register's three consecutive real days remain explicitly unverified at `docs/evidence/harness/S678_cloud_result_2026-09-30.md:62`. Landing tooling must not close that operational acceptance.
