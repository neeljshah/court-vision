# S443: week fill accounting chain

Worktree: `C:/Users/neelj/nba-harness-h98` (bash `/c/Users/neelj/nba-harness-h98`).
Candidate HEAD and verification base (AMENDMENT 3(g)/4(e)/5(e)/9(d)/10(c)/
11(b)/12(b)/13(d): both roles read fresh at this round's close via `git
rev-parse HEAD` in this worktree and `git -C C:/Users/neelj/nba-ai-system
rev-parse master`): `fb4bd620b041bf44036cdb164baccf7db2bba397`, EQUAL. HEAD
never moved by this row's own edits.

## Design history + STEP 0/1 (superseded by FIX 1a -- collapsed per S446
A2(e)/S439 A2(f) precedent)

AMENDMENT 1 re-scoped this row (fill_realism.py's landed output kept only
aggregate counts, no per-fill stream) into STEP 0 (`fill_receipts.py`, NEW):
an additive per-fill receipt export -- `fill_realism.py` edited nowhere (0
bytes changed, AST/LF-byte-equal to `git show HEAD:...`); `_capture()`
monkeypatches `_scenario`/`simulate_fills` for one extra `run_files()` call
without touching `run`/`_prepare`/`_visible`/`_decimal`; per credited fill:
identity, timestamps, qty (Decimal string), mark_30/120/300 (never a
fabricated zero when absent), preceded by a header row; rows sorted by
(fill_receipt, canonical JSON); ASCII, atomic write. And STEP 1
(`week_fill_accounting.py` + `week_fill_accounting_rules.py`, both NEW): the
week accounting chain over those receipts -- CLI `python -m
scripts.platformkit.execution.week_fill_accounting --nights-dir <dir>
--fills-dir <STEP 0 receipts> --iso-year Y --iso-week W --out <path>`. Per
UTC date: missing night -> `NO_NIGHT`, missing fills artifact ->
`MISSING_FILLS_ARTIFACT`, both never crash. Each fill row classifies
(AMENDMENT 5(b)/6(b): hard refusals `unknown_excluded_reason`/
`malformed_mark` first) into those, `duplicate` (`(ticker, trade_id, side)`
already seen -- `quote_id` restarts per capture run), `row_refused_
record_type`, `missing_mark` (mark_30 alone), `excluded_<reason>`
(unreachable from a real receipt today -- STEP 0 exports only credited
fills; CONSTRUCT-only), else `qualified`; exact denominators enforced
(`denominator_mismatch` otherwise); sha256+bytes per artifact (A9); ASCII
JSON, `sort_keys`; deterministic. Full detail in git history at this
memo's fix-1a/1g revisions.

## Fix history (one dated line per fix)

- 2026-09-24 fix-1a (AMENDMENTS 1-2): re-scoped into STEP 0/STEP 1 (see
  "Design history" above); `fill_receipts.py` wrapper CLI keeps S411 green.
- 2026-09-24 fix-1b (AMENDMENTS 3-4): identity + dedup key finalised
  `(ticker, trade_id, side)`; `unknown_excluded_reason` /`malformed_mark` /
  `row_refused_record_type` buckets; `GAME_KEY_ABSENT`; real `per_family`.
- 2026-09-24 fix-1c (AMENDMENT 5): shared-`now` wrapper; `classify()` moved
  before the duplicate test; per_family hand check parses families JSON
  directly; memo cleanup.
- 2026-09-24 fix-1d (AMENDMENT 6, round 3 REJECT): see "FIX 1d through 1j detail" below.
- 2026-09-24 fix-1e (AMENDMENT 7, round 4 REJECT): see "FIX 1d through 1j detail" below.
- 2026-09-24 fix-1f (AMENDMENT 8, round 5 REJECT): header reconciliation
  enforced (`header_mismatch` else); non-finite JSON constants refused
  (`non_finite_field`); conflicting duplicates canonicalised, both
  `duplicate_conflict`, order-independent; see "FIX 1d through 1j detail" below.
- 2026-09-24 fix-1g (AMENDMENT 9, round 6 REJECT): header shape hardened to
  require a dict of non-negative strict ints (array/scalar/negative headers
  refuse, never crash); same-label duplicate retention now picks the
  canonical-JSON-first member, order-independent; every mark cell validated
  as a mapping before `.get` (string/int/list shapes -> `malformed_mark`,
  never a crash); rules split into `week_fill_accounting_rules.py`; see
  "FIX 1d through 1j detail" below.
- 2026-09-25 fix-1h (AMENDMENT 10, round 7 REJECT): a non-finite header
  value now refuses as `HeaderMismatch` instead of escaping `_read_fills()`
  as a raw `ValueError`; `fill_receipts.py` validates qty FIRST so a numeric
  NaN/+-Infinity qty is `invalid_qty`, never `non_finite_field`; see "FIX
  1d through 1j detail" below (compacted).
- 2026-09-25 fix-1i (AMENDMENT 11, round 8 REJECT): `_valid_qty` now refuses
  `bool` and `float` outright (a binary float's rounding approximation, e.g.
  `0.1 + 0.2`, was being stringified into an authoritative Decimal),
  accepting only `str`/`int`/`Decimal`; existing quantity fixtures audited,
  none needed a change; see "FIX 1d through 1j detail" below.
- 2026-09-25 fix-1j (AMENDMENT 12, round 9 REJECT): the whole-fill finite
  probe in `_rows_from_captured` now runs on a copy whose `qty` is
  `str(qty)` (the canonical validated string), never the raw accepted
  `Decimal` object, which `json.dumps` cannot serialize; see "FIX 1d through 1j detail" below
  (compacted).
- 2026-09-25 fix-1k (AMENDMENT 13, round 10 REJECT): an explicit-null mark
  cell now classifies `malformed_mark` (was silently treated as absent, via
  a membership test before any `.get`); an empty fills artifact now refuses
  `HeaderMismatch` (was an escaping `ValueError`); both `_rows_from_captured`
  finite probes now also catch `TypeError` (a non-finite Decimal identity
  value, e.g. `quote_id=Decimal("NaN")`, is `non_finite_field`, never a
  crash); see "FIX 1k" below.

## Test counts (per-file, all singly)

| file | result |
|---|---|
| tests/platformkit/execution/test_fill_realism_fills_out.py | 15 passed (unchanged this round) |
| tests/platformkit/execution/test_fill_realism_fills_out_1h.py | 4 passed (unchanged this round) |
| tests/platformkit/execution/test_fill_realism_fills_out_1i.py | 4 passed (unchanged this round) |
| tests/platformkit/execution/test_fill_realism_fills_out_1k.py | 2 passed (NEW this round: A13(c) x2) |
| tests/platformkit/execution/test_week_fill_accounting.py | 21 passed (unchanged this round) |
| tests/platformkit/execution/test_week_fill_accounting_1c.py | 6 passed (unchanged this round) |
| tests/platformkit/execution/test_week_fill_accounting_1f.py | 5 passed (unchanged this round) |
| tests/platformkit/execution/test_week_fill_accounting_1g.py | 9 passed (unchanged this round) |
| tests/platformkit/execution/test_week_fill_accounting_1h.py | 2 passed (unchanged this round) |
| tests/platformkit/execution/test_week_fill_accounting_1k.py | 3 passed (NEW this round: A13(a) x2, A13(b) x1) |
| 8 other pre-existing fill_realism/paper_night files (test_fill_realism.py 34, test_fill_realism_1b.py 12 frozen-byte, test_fill_realism_1d.py 6, test_fill_realism_classify.py 49, test_fill_realism_io.py 17, test_fill_realism_markout.py 22, test_paper_maker_fill_realism.py 12, test_paper_night.py 39) | all passing at fix-1c, unchanged; not re-run this round (none touched by fix-1k) |

## LOC

`fill_receipts.py` 297 (edited FIX 1k) | `week_fill_accounting.py` 212
(edited FIX 1k) | `week_fill_accounting_rules.py` 152 (edited FIX 1k) |
`test_fill_realism_fills_out.py` 300 (unchanged) |
`test_fill_realism_fills_out_1h.py` under 60 (unchanged) |
`test_fill_realism_fills_out_1i.py` 62 (unchanged) |
`test_fill_realism_fills_out_1k.py` 36 (NEW) |
`test_week_fill_accounting.py` 284 (unchanged) |
`test_week_fill_accounting_1c.py` 130 (unchanged) |
`test_week_fill_accounting_1f.py` 113 (unchanged) |
`test_week_fill_accounting_1g.py` 153 (unchanged) |
`test_week_fill_accounting_1h.py` 53 (unchanged) |
`test_week_fill_accounting_1k.py` 59 (NEW) | `fill_realism.py` 300
(unchanged from master, byte-identical). `S443_PROPOSAL_week_fill_wiring_
2026-09-24.md` 71 | this memo <= 300 (see wc at fix-1k close).

## A9 identities (path | bytes | sha256) -- every candidate and must-not-move file, recomputed from this tree LAST at fix-1k close, candidate HEAD fb4bd620b041bf44036cdb164baccf7db2bba397 / verification base fb4bd620b041bf44036cdb164baccf7db2bba397 (EQUAL), LF-normalized bytes (read_bytes().replace(b"\r\n", b"\n"))

| path | bytes | sha256 |
|---|---|---|
| scripts/platformkit/execution/fill_realism.py | 18642 | bf3c56b76d2289517a5001e956e4dda534ec32094db7775525f57e28da2d5b42 |
| scripts/platformkit/execution/fill_realism_markout.py | 4547 | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e |
| scripts/platformkit/execution/fill_realism_io.py | 16327 | f952dcd2ae5f3ef8cac95d2fbd7d13228a0a2bee6507cb004572c929d10fdf0f |
| scripts/platformkit/execution/forward_replay_qualification.py | 14575 | 0db7fcd48d692e9e90b4c0cfb97d28cbec59299d1f8921d1ec9988e90f9778c8 |
| scripts/platformkit/execution/paper_night.py | 15058 | d4a2138ea446b0b39c16398c22320fa9ef37686a5bcdf2add81e913507c24cc5 |
| scripts/platformkit/ops/forward_week_report.py | 14274 | 45642475e36881566c1a61099baec0e360724cbf65aff50dd6248cb2f56eaa86 |
| scripts/platformkit/execution/family_week_ledger.py | 11149 | 7b224575cbf6c663f775f3148afd24218fa94f54e5ebf48dbea1f22761e81a9c |
| scripts/platformkit/execution/weekly_record.py | 10903 | 823d8b30d3dbb229f12672e1bbb7f842ea117f77bc3b1442a22c6b11fa1bd85e |
| docs/GO_LIVE_GATES.md | 3624 | c55556a121599bc45909fac7592b627bf02b5b81064dbf007d9be795e9d2abd0 |
| docs/evidence/tracking/specs/S443_spec.md (grew to AMENDMENT 13 between rounds) | 26946 | 8a3315f88ef557e33936a6f5f2d0dc57aeccfb07a5e3c0b9d35f89fc41b04c2e |
| docs/evidence/forward/families_maker_forward.json | 4225 | c9dc31ea2bc65ff5f622b8c02dfc35e38e5841c2874649f13c9d30f707ed03ee |
| scripts/platformkit/execution/fill_receipts.py (edited FIX 1k) | 14987 | 70d5f2b7ae6dc2b34091b16c171f0da8792aa27ca6d80ed33fa7378c22f5ebe2 |
| scripts/platformkit/execution/week_fill_accounting.py (edited FIX 1k) | 10655 | 1a8d71db62f0138b195b77f6477b968bee642a08144431e4836ce6c4f259608c |
| scripts/platformkit/execution/week_fill_accounting_rules.py (edited FIX 1k) | 6913 | 9c188ea741b78e9df6d741acc7d41f1fc8c108e87d8c6844e40d59d38ac6d536 |
| tests/platformkit/execution/test_fill_realism_fills_out.py (unchanged this round) | 15152 | cb6482357448d62b83411991c7b8cc93eeca4c35635cfa8135eeb6de73d1799b |
| tests/platformkit/execution/test_fill_realism_fills_out_1h.py (unchanged this round) | 2518 | 356024e2451caff795702e42bd39bcb07df057803bff17fb6e501e76518103de |
| tests/platformkit/execution/test_fill_realism_fills_out_1i.py (unchanged this round) | 2898 | 8617eaddcbd79a0e9dd9b79a216085661da595ed6c131234fbda17353ebbac64 |
| tests/platformkit/execution/test_fill_realism_fills_out_1k.py (NEW this round) | 1700 | 522487b228834a7072c17c5d3b40ea1209dc8a95f003bf5c132a9935fc36f8be |
| tests/platformkit/execution/test_week_fill_accounting.py (unchanged this round) | 13560 | e656e91dc852e92d2cf822d083041b5376f7a55299b09bbfbb0a676e20588a4e |
| tests/platformkit/execution/test_week_fill_accounting_1c.py (unchanged this round) | 6901 | 219b7e0b9278d07e28514be361e616fedaea09fcbb9623494ab4d50407132c6d |
| tests/platformkit/execution/test_week_fill_accounting_1f.py (unchanged this round) | 5597 | b73f7910334a4e487c728f7ac7eb826297e27ae2e038158c211b304da5ab9ad2 |
| tests/platformkit/execution/test_week_fill_accounting_1g.py (unchanged this round) | 7484 | 9cd4da1227abc98f9f38b1a9b16595afe559b5fc9640638e2e70b3f42085c2c7 |
| tests/platformkit/execution/test_week_fill_accounting_1h.py (unchanged this round) | 2681 | 8fa2d27b37cfe855ef39e876266c480aa7dd928429e3eca0f02cde0cd5326338 |
| tests/platformkit/execution/test_week_fill_accounting_1k.py (NEW this round) | 2770 | cde1ce61456c0b07e859e3bcf2498033bf30e28ed27ce7f1382c094fb867e6a6 |
| docs/evidence/harness/S443_PROPOSAL_week_fill_wiring_2026-09-24.md (unchanged this round) | 3767 | 21c8467236bf62e6bbda260af3db0461ffc40a6435a955cd7f510d2ae6b6b55f |

All nine must-not-move files (fill_realism.py, fill_realism_markout.py,
forward_replay_qualification.py, paper_night.py, forward_week_report.py,
family_week_ledger.py, weekly_record.py, GO_LIVE_GATES.md, plus
fill_realism_io.py as a read-only candidate this row imports but never
edits) are confirmed untouched by `git diff --stat master -- <path>` (empty
for every one) at verification base `fb4bd620b` (equal to candidate HEAD),
cross-checked against `git show master:<path>` bytes (LF-normalized,
identical for all nine), and by `git status --short` (only tracked
NEW/edited files plus this memo appear).

## PROPOSED integration

`docs/evidence/harness/S443_PROPOSAL_week_fill_wiring_2026-09-24.md` (FIX 1d,
AMENDMENT 6(a): the TRACKED candidate file; the gitignored
`docs/research/organization-sprint/PROPOSED_S443_week_fill_wiring.md` copy
stays byte-identical) sketches the one-parameter
`forward_week_report.py._row()` change and names the unresolved
`game_key`/`game_id` identity gap a later row must close first. Not applied.

## Preflight

```
cd /c/Users/neelj/nba-harness-h98 && python -m scripts.platformkit.tracking.contract_preflight \
  --base master --spec docs/evidence/tracking/specs/S443_spec.md \
  --paths scripts/platformkit/execution/fill_receipts.py \
          scripts/platformkit/execution/week_fill_accounting.py \
          scripts/platformkit/execution/week_fill_accounting_rules.py \
          tests/platformkit/execution/test_fill_realism_fills_out.py \
          tests/platformkit/execution/test_fill_realism_fills_out_1h.py \
          tests/platformkit/execution/test_fill_realism_fills_out_1i.py \
          tests/platformkit/execution/test_fill_realism_fills_out_1k.py \
          tests/platformkit/execution/test_week_fill_accounting.py \
          tests/platformkit/execution/test_week_fill_accounting_1c.py \
          tests/platformkit/execution/test_week_fill_accounting_1f.py \
          tests/platformkit/execution/test_week_fill_accounting_1g.py \
          tests/platformkit/execution/test_week_fill_accounting_1h.py \
          tests/platformkit/execution/test_week_fill_accounting_1k.py \
          docs/evidence/harness/S443_week_fill_accounting_2026-09-24.md \
          docs/evidence/harness/S443_PROPOSAL_week_fill_wiring_2026-09-24.md
```
Result (fix-1k, this round, 15 files): 9 PASS, 0 FAIL (vocab, crlf, loc,
schema, head_slice, spec_threshold, proposed, removed_artifact,
row_duplication).

`git status --short` in the worktree shows only the new/untracked tracked
files plus this memo. Nothing was committed or pushed; no network; no write
under `data/`; no running capture touched; candidate HEAD never moved
(`fb4bd620b` throughout, equal to the verification base -- see intro).

## FIX 1d through 1j detail (superseded by FIX 1k -- collapsed per S446
A2(e)/S439 A2(f) precedent)

Round-3 (AMENDMENT 6, `_verdict_s443_1d.md`, three BLOCKING: tracked
proposal copy, exclusion-before-mark-validation ordering, non-finite
identity values), round-4 (AMENDMENT 7, `_verdict_s443_1e.md`, two BLOCKING
+ one CORRECTION), round-5 (AMENDMENT 8, `_verdict_s443_1f.md`, four
BLOCKING: header reconciliation absent, non-finite JSON constants silently
accepted, input-order-dependent conflicting duplicates), round-6 (AMENDMENT
9, `_verdict_s443_1g.md`, three BLOCKING: header shape could crash/accept a
negative counter, same-label duplicate retention was input-order dependent,
a malformed mark container crashed), round-7 (AMENDMENT 10,
`_verdict_s443_1h.md`, two BLOCKING: a non-finite header escaped as a raw
`ValueError`; quantity validated AFTER the whole-fill finite probe), round-8
(AMENDMENT 11, `_verdict_s443_1i.md`, one BLOCKING: `_valid_qty` accepted a
binary float and stringified its rounding error, e.g. `0.1 + 0.2`, as an
authoritative Decimal -- now refuses `bool`/`float` outright, accepting
only `str`/`int`/`Decimal`), and round-9 (AMENDMENT 12, `_verdict_s443_1j.md`,
one BLOCKING: an accepted `Decimal` qty crashed the whole-fill finite probe
with `TypeError: Object of type Decimal is not JSON serializable`, since the
probe ran on the raw `fill` dict rather than a copy with `qty=str(qty)`) are
each summarized one-line-per-item in "Fix history" above; full
reproductions, hunks, AFTER-states and per-round pass counts (21/6/5/15 at
1f; 21/6/5/9/15 at 1g; 21/6/5/9/2/15/4 at 1h; +4 at 1i; +0/extended at 1j,
all 0 failed, preflight 9/9 each) are preserved in git history at this
memo's fix-1e/1f/1g/1h/1i/1j revisions.

## FIX 1k (AMENDMENT 13, round 10 REJECT -- three BLOCKING from
`_verdict_s443_1k.md`)

1. **An explicit-null mark cell was misclassified `missing_mark`**
   (`week_fill_accounting_rules.py:78`, `_mark_malformed`). Repro (fix-1j
   code): `{"mark_30": None, "mark_120": {"present": False}, "mark_300":
   {"present": False}}` -> `classify() == "missing_mark"`; AMENDMENT 13(a)
   requires `"malformed_mark"` for an explicit null, distinct from a
   genuinely absent key. Hunk: `if field not in row: continue` (skip only a
   truly absent key) precedes `cell = row[field]` and the `isinstance(cell,
   dict)` check, so `None` now falls through like any other non-mapping.
   AFTER: same input -> `"malformed_mark"`. Regressions (NEW,
   `test_week_fill_accounting_1k.py`):
   `test_a13a_explicit_null_mark_is_malformed_not_missing`,
   `test_a13a_genuinely_absent_mark_key_still_missing_mark` (negative control).

2. **An empty fills artifact escaped as a raw `ValueError`**
   (`week_fill_accounting.py:83`, `_read_fills`). Repro (fix-1j code): a
   0-byte fills file -> `ValueError("empty_fills_artifact")`, uncaught by
   `accumulate()`'s `except HeaderMismatch`, crashing `build()`. Hunk: that
   branch now raises `HeaderMismatch("header_mismatch")` -- no header to
   parse is the same shape failure as a malformed one. AFTER: `status ==
   "header_mismatch"`, `fills == 0`. Regression (NEW):
   `test_a13b_empty_fills_artifact_is_header_mismatch_not_a_crash`.

3. **A non-finite Decimal identity value still crashed both finite probes**
   (`fill_receipts.py:189`, `_rows_from_captured`). Repro (fix-1j code):
   `quote_id=Decimal("NaN")`, `qty="1"` -> `TypeError: Object of type
   Decimal is not JSON serializable` (the fix-1j copy only replaced `qty`;
   json has no Decimal encoder at all, `ValueError` or not). Hunk: both
   `except ValueError:` clauses now catch `(ValueError, TypeError)`. AFTER:
   `Decimal("NaN")`/`Decimal("Infinity")` quote_id with `qty="1"` -> zero
   rows, `non_finite_field=1`. Regressions (NEW,
   `test_fill_realism_fills_out_1k.py`):
   `test_a13c_decimal_nan_identity_value_is_non_finite_field_not_a_crash`,
   `test_a13c_decimal_infinity_identity_value_is_non_finite_field_not_a_crash`.

4. **A9 regenerated.** Regenerated as the LAST edit this round at candidate
   HEAD `fb4bd620b` / verification base `fb4bd620b` (EQUAL, no drift this
   round), LF-normalised bytes, cross-checked against `git show master:<path>`.

Verified in THIS environment (not a sandbox): all ten touched-or-touching
test files ran to a real count -- 21/6/5/9/2/3 (week_fill_accounting
family) and 15/4/4/2 (fill_realism_fills_out family), 0 failed; preflight
9 PASS, 0 FAIL over 15 files; every must-not-move file byte-identical to the
verification base (LF-normalised sha256, matching an empty `git diff --stat
master -- <path>`).

## NOT VERIFIED

Every round-3 through round-10 verifier
(`_verdict_s443_1d/1e/1f/1g/1h/1i/1j/1k.md`) ran in a sandbox with no
writable temporary directory: all row tests (66, now 71) stopped during
`tmp_path` fixture setup before any test body ran, so no verifier's sandbox
has independently reproduced a single row test's pass/fail count -- each
instead verified the diffs/hunks, the must-not-move byte-identity, A9
hashes, and preflight by other means. This fix-1k pass, as with 1f-1j
before it, ran on the HOST (this environment): all ten touched-or-touching
row test files executed for real, 0 failed (named above), but that host
run remains unreproduced by any sandboxed verifier. Existing unchanged
suites beyond the files this row touches, real-week execution, a real
corpus, and the real FWER ledger were still not run this round (out of
this row's scope).

No real ISO week exists yet: `docs/evidence/forward/nights/` has no 7-date
completed week at the time of this build, and STEP 0's `--fills-out` flag
has not been wired into `paper_night.py` (by design), so no real
fill_realism run has ever produced a STEP 0 receipts file. All construct
cases above are CONSTRUCT-only, over hand-built or synthetic fixtures, per
the spec's own `n = 13 (CONSTRUCT)` acceptance rule. `excluded_<reason>`
classification is exercised only via constructed fixture rows and has
never been observed from a real fill_realism receipt. The PROPOSED
`forward_week_report.py` wiring is a sketch only, not applied, not
re-verified against S427's contract, and depends on an unresolved
game_key/game_id identity question. The first real receipts, and the first
real week, arrive only after a future row wires `--fills-out` into
`paper_night.py`'s fill_realism step and a completed week accumulates
under `docs/evidence/forward/nights/`.
