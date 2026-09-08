# S319 preregistration -- checkout-invariant receipt hashing and recorded-date freshness (2026-09-08)

Row: GAP S319, worktree a22, LOCAL only (no pod, no GPU). Written and committed ALONE before any
code change, per verifier contract Q1.

## Seal rule (stated before the seal is taken)

The last line of this file is `SEAL sha256 <hex>`. The hex is the SHA-256 of every byte of this
file ABOVE that line, after replacing every CRLF with LF (the normalisation of the shared helper
`scripts/platformkit/hash_lf.py`). The trailing newline of the line preceding `SEAL` is INCLUDED in
the sealed prefix; the `SEAL` line itself is not. Anyone may recompute it by reading the file as
bytes, truncating at the last occurrence of the marker text `SEAL sha256 `, replacing CRLF with LF
in what remains, and taking the SHA-256 of that.

## Premise (step 0, BINDING before-condition)

On a scratch copy of the six receipt artifacts named by the four receipt-bearing rows of
`domains/basketball_nba/knowledge/validation_ledger.jsonl` (rows `s296_boxscore_distribution_plus_minus`,
`s310_ingame_tail_beta_offset`, `s312_tracking_teacher_student_connection`, `s293_tail_log_loss_rail`),
with the ledger itself copied beside them, I will run the LANDED `receipt_guard.check_rows` twice:

  P1  one receipt rewritten with the other line-ending convention and NOTHING else changed
      (this worktree is a CRLF checkout, so the rewrite is CRLF -> LF, which is the byte form a
      pod checkout and `git archive -c core.autocrlf=false` produce);
  P2  the scratch tree left byte-identical, one receipt's mtime advanced past the ledger's by more
      than the guard's 3600-second slack.

Both refusals will be PRINTED verbatim in the memo. If the landed guard does NOT refuse a
content-identical receipt on line endings, or does NOT refuse on mtime, the premise is FALSE:
I stop, write the memo, commit, and report PREMISE FALSE. No code change is made in that case.

## Rule 1 -- hash the normalised bytes, accept either recorded form

`_sha256` (raw bytes) is renamed `_sha256_raw` and kept for BINARY receipts, chosen by extension
(`.gz`, `.zip`, `.parquet`, `.png`, `.jpg`, `.mp4`, `.npy`, `.pkl`, `.pt`, `.bin`); git stores those
verbatim, so normalising them would be wrong. Every other extension is treated as text and hashed
through the shared `sha256_lf` helper (`scripts/platformkit/hash_lf.py`, G326) -- reused, not
re-implemented.

The four ledger rows' recorded hashes were sealed over CRLF bytes on the authoring machine, so a
straight switch to the normalised digest would refuse all six receipts. Ledger rows are NOT
rewritten (B2, and `domains/` is append-only). Instead a sidecar map is committed at
`docs/evidence/harness/S319_receipt_hashes_2026-09-08.json`, keyed BY THE RECORDED DIGEST and
valued by the normalised digest of the same content. A text receipt verifies when ANY of:

  (a) its normalised digest equals the digest the row records            -> match reason `lf`
  (b) the sidecar maps the recorded digest to its normalised digest      -> match reason `sidecar_lf`
  (c) its raw digest equals the digest the row records                   -> match reason `raw`

checked in that order, and the reason that fired is reported in the envelope note. The sidecar is
keyed by the RECORDED digest, never by path, so altering the digit string a row quotes still
refuses: no sidecar entry exists for the altered value and neither computed digest equals it.
Rules (a) and (b) are checkout-invariant; (c) is the legacy raw form and is kept only so a row
sealed on a CRLF machine still verifies on a CRLF checkout. A binary receipt is checked by (c)
alone.

## Rule 2 -- freshness from recorded dates, not mtimes

The comparison `ledger_mtime < receipt_mtime - slack` is replaced by a comparison of the dates the
row and the receipt themselves record, at day granularity:

  ledger side   the row's own date field, first of `as_of`, `date`, `run_ts` that the row carries;
  receipt side  the artifact's own `run_utc` / `generated_at` / `as_of` field when it carries one,
                otherwise the LATEST ISO-8601 `YYYY-MM-DD` the artifact's text records.

A receipt is stale when its recorded date is STRICTLY LATER than the row's. The latest recorded
date is used rather than the first because an artifact cannot have been produced before the newest
date it names, which makes the fallback fail-closed in the direction of refusing. When EITHER side
records no date, the old mtime comparison with its 3600-second slack applies to that receipt and
the note says so; when an internal date exists, mtime alone never refuses.

`as_of` (the answer's freshness floor, S313 fix 3) is NOT changed: it stays `min(ledger, receipts)`
over mtimes, because the spec says it stays and an existing test pins it to that form. This is
recorded as a limitation, not a fix.

## Date-field enumeration plan

For each of the six receipts I will report, in a table: the structured date field it carries (or
NONE), the latest ISO-8601 date its text records, the row date it is compared against, which of the
two branches decided it, and the outcome. The enumeration is exhaustive over the six; there is no
sample.

## Tests

`tests/platformkit/test_s319_receipt_guard_lf.py` (new file, at most 300 lines), each case built on
a scratch copy so no tracked file is touched:

  T1  the same receipt written with CRLF and with LF yields the SAME guard outcome;
  T2  a receipt whose mtime is newer than the ledger's but whose recorded date is older is ACCEPTED;
  T3  a receipt whose recorded date is later than the row's is REFUSED as stale;
  T4  a flipped hex digit in the digit string a row records still refuses;
  T5  the sidecar file's every entry maps a recorded digest to the normalised digest of the very
      artifact the ledger names (no orphan and no unused entry).

`tests/platformkit/test_s313_answers_label_survival.py` must still pass on this tree AS IS, with no
hand repair of line endings or mtimes. One of its eleven cases,
`test_a_stale_ledger_refuses_instead_of_answering`, builds its staleness by back-dating the ledger
FILE's mtime -- the exact construct rule 2 removes. If, as expected, that case can only pass by
re-expressing its setup (back-date the row's recorded date instead of the file's mtime, keeping the
test's name and every assertion), then step 3(e) of the spec is not literally met and this row is
PARTIAL, saying so with that single named case. I will not weaken any assertion to avoid that.

Also run, each alone: `tests/platformkit/test_loc_rail_scope.py`,
`scripts/platformkit/answers/test_resolver_registry_routing.py`,
`scripts/platformkit/answers/test_mechanism_effect.py`. Never a full pytest run.

## Verdict rule (fixed here, before any measurement)

DONE only if ALL of: every test above passes on the tree as-is; zero ledger rows rewritten; zero
landed memos edited; `scripts/platformkit/answers/resolver_registry.py` still at most 1323 lines and
not grown; both premise refusals printed. PARTIAL otherwise, with the explicit list of what did not
hold. PREMISE FALSE stops the row before any code change. No bar in this or any other row moves,
and no number is claimed beyond the counts named here.

## Must not move

The S313 verdict and bars; every landed memo and every committed digest; `src/`, `api/`, `kernel/`,
`intel/`, `scripts/team_system/`; `domains/` (read-only except APPENDING a ledger row, which this
row does not do); `data/` and `data/registry/`; every feature flag; the pod.
SEAL sha256 6583456965bd3ea92b245e70d6dc42c27e7a77dfbb153d9e9c4a560edaa11a8b
