GAP G326 | sport all | worktree a17 | log cx_g326_crlf_safe_hashes

**TOOLING ROW. `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT only.
Build in `scripts/platformkit/`. NEVER edit a committed evidence hash, a committed evidence
artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL. CPU only. No GPU, no GPU lease, no pod access, no footage.
**NEVER stop, signal or interfere with `track_daemon`.**

**WHY THIS ROW EXISTS.** `python -m scripts.platformkit.tracking.g298_audit` fails a raw-byte
hash assertion on a CRLF checkout before it performs any arithmetic (`g298_audit.py:29`, found
by the G303 verifier). `core.autocrlf` is `true` on this machine, so every text artifact in the
working tree carries CRLF bytes while the same blob is LF in the git object store and on the pod.
A SHA-256 taken over raw file bytes is therefore a function of the CHECKOUT, not of the content:
a landed audit that seals a text artifact by raw bytes cannot be re-executed from a clone whose
line endings differ from the machine that sealed it. Re-executability is the whole point of a
sealed audit, so this defect silently voids it.

**PREMISE (step 0, BINDING before-condition):** run
`python -m scripts.platformkit.tracking.g298_audit` on this checkout and **PRINT the command and
the first 20 lines of the traceback verbatim**, then show the same assertion passing once the
compared bytes are LF-normalized. **If the module does not fail on this checkout, the premise is
FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **SWEEP.** Enumerate every site under `scripts/platformkit/**` that feeds bytes read from a
     FILE ON DISK into a hash. Start from
     `grep -rn "sha256\|hashlib" scripts/platformkit | grep -v "_test"` and narrow to the
     file-reading subset (`read_bytes()`, `open(..., "rb")`, streamed `.read()`). **Report the
     table with `file:line`.** Classify each site into exactly one class:
       - **text-raw-bytes (defect)** -- hashes a text artifact (`.md`/`.csv`/`.json`/`.txt`/`.py`)
         from raw bytes AND compares the digest against a value committed to the repo (a literal
         constant, a committed sidecar, or a field inside a committed evidence artifact).
       - **record-only** -- hashes a text artifact but only WRITES the digest into an output; no
         committed comparison, so no re-execution can fail. Count it, do not convert it.
       - **binary (fine)** -- the hashed path is `.mp4`/`.png`/`.pt`/`.parquet`/`.npy`/`.gz`.
       - **in-memory / same-run (fine)** -- the hashed bytes never come from a checked-out text
         file, or both sides of the comparison are computed in the same run.
       - **already LF-normalized (fine)** -- the site already strips `\r\n`.
  2. **FIX.** For each defect site, hash LF-normalized bytes (`b"\r\n"` -> `b"\n"`) through **ONE
     shared helper**. Add `scripts/platformkit/hash_lf.py` if no shared helper exists; **if
     `sha256_lf` already exists somewhere, reuse it and SAY WHERE.** The change is additive and
     behaviour-preserving on an LF checkout.
  3. **HASH DELTA (the gate on step 2).** For every committed hash a defect site asserts,
     recompute BOTH the raw-byte and the LF-normalized digest on this checkout and state which
     one the committed value equals. **Expected: the committed value is the LF digest, so
     converting the site changes NO committed hash.** If a committed value equals the RAW digest
     instead, that hash was sealed from CRLF bytes on the authoring machine and can never be
     reproduced on an LF checkout: **STOP for that module, convert NOTHING there, and report it
     as a FINDING naming the owning row. NEVER edit a committed evidence hash to make a test
     pass.**
  4. **TEST.** One per-file test per touched module: write the same content to tmp files with
     CRLF and with LF line endings and assert the helper returns EQUAL digests, plus a regression
     assertion that the converted site's committed value is reproduced on THIS checkout.
     **Every touched module's existing test file must still pass; run each individually.**
  5. **CHANGE NOTHING ELSE.** No threshold, no committed hash, no evidence artifact, no register
     edit, no production default, no adoption.

**HONEST LIMITATIONS to state, not discover:** LF normalization makes a digest checkout-invariant;
it does NOT make it correct, and it says nothing about whether the artifact it seals is right.
This row decodes no video, reads no tracking output and measures no recall, precision, accuracy or
registration. A module left unconverted because its committed seal is CRLF-derived stays
un-re-executable on an LF checkout, and the memo must say so in those words rather than implying
the sweep repaired it.

ACCEPTANCE RULE:
  metric        = the classified site table with `file:line` and counts per class; the per-defect
                  hash-delta result (committed == raw digest, or committed == LF digest); the
                  before/after of the premise command
  before        = `g298_audit` raises at `g298_audit.py:29` on a CRLF checkout before any
                  arithmetic; no shared LF-normalizing hash helper is imported anywhere in
                  `scripts/platformkit/`
  bar           = every defect site is either converted through the one shared helper with a
                  passing per-file test, or reported as a FINDING with its hash-delta evidence;
                  and **0 committed hashes change**
  n             = every file-bytes hash site under `scripts/platformkit/**` (CONSTRUCT --
                  exhaustive enumeration, not a sample; Q7 applies, A3 does not)
  eye check     = NONE. No frames, no renders, no labels. Say that rather than implying validation.
  must not move = every committed hash constant and every committed evidence artifact; `src/`,
                  `domains/`, `api/`, `kernel/`, `intel/`; `data/`; `tracking_harness.py`;
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`; the running `track_daemon`
  verdict       = **DONE** if every defect site is converted with a passing test and 0 committed
                  hashes change; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/tracking/g326_crlf_safe_hashes_2026-09-07.md` (<= 60 lines) with VERDICT
on line 1, the site table, the hash-delta result, the converted-module list, a **NOT VERIFIED**
list, wall time and the SHA-256s. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>`
append). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`** -- the orchestrator
owns it.
TEST: `tests/platformkit/test_g326_crlf_safe_hashes.py` -- the CRLF/LF equality construct of step
4 plus the regression assertion. **n = CONSTRUCT.** Run that ONE file, and separately re-run the
existing test file of every touched module. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first. **NEVER PARK.**

VERSION 2026-09-07
