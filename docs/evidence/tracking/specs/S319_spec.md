GAP S319 | sport all | worktree a22 | log cx_s319_receipt_guard_lf

**TOOLING ROW (harness S register). `src/`, `domains/`, `api/`, `kernel/` and `intel/` are READ and IMPORT
only. Build in `scripts/platformkit/answers/` (the answers layer is a safe area). NEVER edit a landed memo, a
committed evidence hash, `docs/evidence/HARNESS_GAPS_2026-09-03.md`, `docs/evidence/RESULTS_LEDGER_SYSTEM.md`
(the lander appends), `data/registry/`, or any threshold.**

**WHERE THIS ROW RUNS:** LOCAL only. No pod, no GPU.

**WHY THIS ROW EXISTS.** S313 landed `scripts/platformkit/answers/receipt_guard.py`, which refuses a
mechanism-effect answer unless the ledger row's quoted receipt still hashes to the artifact and is not
newer than the ledger. At the S313 landing (2026-09-08) the guard failed 3 of 11 label-survival tests on
the main repo tree because (a) `_sha256` hashes RAW bytes while the tree mixes LF files (left by landers'
`git archive -c core.autocrlf=false` extractions) and CRLF files (autocrlf checkouts), so a byte-exact
receipt hash depends on the checkout, not the content (G326 established the same defect for tracking
hashes and shipped `sha256_lf`); and (b) freshness compares file MTIMES, which git does not preserve, so a
checkout stamps receipts newer than the ledger and every route refuses as `stale`. The lander restored
the tree by hand; that is not a fix.

**PREMISE (step 0, BINDING before-condition):** on a scratch copy of the six receipt artifacts the S313
ledger rows name (`domains/basketball_nba/knowledge/validation_ledger.jsonl` rows for S293, S310, S312,
S314 and their named files under `docs/evidence/harness/`), convert one receipt LF->CRLF and touch its
mtime newer than the ledger, run `receipt_guard` against it, and PRINT the refusal. **If the guard does not
refuse a content-identical receipt on line endings or on mtime, the premise is FALSE: STOP, write the
memo, commit, report PREMISE FALSE.**

METHOD:
  1. **HASH LF-NORMALISED BYTES.** Route every receipt hash through the shared `sha256_lf` helper
     (`scripts/platformkit/hash_lf.py`, G326) -- reuse it, do not re-implement. Keep the raw-bytes hash
     available under a new name for binary receipts (`.gz`, `.parquet`); choose by extension and say so.
     The ledger rows' recorded hashes were computed over CRLF bytes on the authoring machine (S313
     landing finding): recompute each named receipt's LF digest, and if a row's recorded hash equals the
     CRLF digest and not the LF digest, do NOT rewrite the row -- add an additive `receipt_sha256_lf`
     field via a NEW ledger row (append-only, B2) or a sidecar map committed under `docs/evidence/harness/
     S319_receipt_hashes_2026-09-08.json`, and make the guard accept either the recorded raw hash or the LF
     hash, reporting which matched in the envelope note. Print the table: receipt, raw digest, LF digest,
     recorded value, which matched.
  2. **FRESHNESS FROM RECORDED DATES, NOT MTIMES.** Replace the mtime comparison with the dates the row
     and the receipt themselves record (the row's `as_of`/`date` field vs the receipt artifact's internal
     `run_utc`/`generated_at`/`as_of` field, whichever the artifact carries -- enumerate per receipt). Where
     an artifact carries no internal date, fall back to the mtime comparison WITH the 1-hour slack and say
     so in the note; never refuse on mtime alone when an internal date exists. `as_of = min(ledger date,
     receipt dates)` stays (S313 fix 3).
  3. **TESTS.** Extend `tests/platformkit/test_s313_answers_label_survival.py` (or add
     `tests/platformkit/test_s319_receipt_guard_lf.py`): (a) a receipt copied with CRLF and LF line endings
     yields the same guard outcome; (b) a receipt whose mtime is newer than the ledger but whose internal
     date is older is ACCEPTED; (c) a receipt whose internal date is newer than the ledger's is REFUSED as
     stale; (d) a flipped hex digit still refuses; (e) the existing 11 tests still pass, on this tree as-is
     (no manual tree repair).
  4. **CHANGE NOTHING ELSE.** No route semantics beyond the two rules; existing envelope fields keep names
     and meanings; `resolver_registry.py` must not grow (1320 lines, allowlist 1323).

**HONEST LIMITATIONS to state, not discover:** LF normalisation makes the receipt hash checkout-invariant,
not correct; an artifact without an internal date keeps the weaker mtime rule; this row does not touch
the S313 verdict or its bars.

ACCEPTANCE RULE:
  metric        = the premise refusal print; the receipt hash table (raw / LF / recorded / matched);
                  the per-receipt date-field table; the tests
  before        = `receipt_guard._sha256` hashes raw bytes; freshness compares mtimes; 3/11 tests fail on
                  a mixed-line-ending tree until the tree is repaired by hand
  bar           = all tests in step 3 pass on the tree AS-IS; 0 ledger rows rewritten; 0 landed memos
                  edited; `resolver_registry.py` <= 1323 lines
  n             = every receipt named by the S313 rows (exhaustive)
  eye check     = NONE. Say that.
  must not move = the S313 bars and verdict; every landed memo and hash; `src/`, `domains/` (read only;
                  the validation ledger may only be APPENDED, never rewritten), `api/`, `kernel/`,
                  `intel/`; `data/`; the pod
  verdict       = **DONE** if the bar holds; **PARTIAL** with the explicit list otherwise.
EVIDENCE: `docs/evidence/harness/S319_receipt_guard_lf_2026-09-08.md` (<= 60 lines) with VERDICT on line
1, the premise print, both tables, a **NOT VERIFIED** list, wall time and the SHA-256s (LF-normalised),
plus the proposed ledger line for the lander: `2026-09-08 | harness-to-answers calibration | S319 | <finding
with n> | <VERDICT>`. **Do NOT write `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.**
TEST: the file(s) of step 3 plus `tests/platformkit/test_loc_rail_scope.py`, each alone. **NEVER a full pytest.**
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
