# S313 attempt 2 -- automated vocabulary and retracted-figure scans

Vocabulary follows contract Q6; automated scan required.

Two scans were run over every file this row adds or changes (the prereg, the four artifact JSON
files, the route-status table, the per-file test, and the four appended ledger lines, extracted by
`git diff` so no pre-existing ledger content is scanned). The patterns are supplied on the command
line only and are not written into any artifact.

## Scan A -- restricted claim vocabulary

Case-insensitive, WORD-BOUNDED, four restricted tokens: **0 hits.**

A naive SUBSTRING form of the same scan reports 88 apparent hits. All 88 are classified and none is
a claim:

| what matched | count | why it is exempt |
|---|---:|---|
| the word "ledger" (upper and lower case) | 50 | an ordinary English word that contains one token as a substring |
| the word "knowledge" | 30 | same, inside the `domains/<sport>/knowledge/` path |
| a JSONL schema FIELD NAME carried by every row in this ledger, whose `false` value is what makes a row receivable at all | 4 | opaque identifier, contract Q6 NOTE (2026-09-04, S223) |
| one PRE-EXISTING registered hypothesis NAME, echoed verbatim inside the out-of-domain route's list of registered hypotheses | 4 | opaque identifier quoted verbatim; the Q6 NOTE forbids renaming or masking it |

## Scan B -- retracted figures

Claim-context form (each retracted figure as a figure, not as a digit fragment inside a longer
number, a hash or a clock): **0 hits.**

The literal alternation form reports 45 apparent hits, all of them the two-digit fragment. All 45
are classified and none is a retracted figure:

| what matched | count | why it is not a claim |
|---|---:|---|
| an ISO-8601 clock value (the seconds field of `as_of` / `run_ts`) | 21 | machine timestamp |
| the trailing digits of the S293 landed improvement `-0.002071936078148454` | 10 | the receipt's own value, quoted to the printed digits |
| the digits of the S310 upper CI bound `+0.001495545` | 6 | the receipt's own value, quoted to the printed digits |
| a fragment of the SHA-256 of `docs/evidence/tracking/specs/S312_spec.md` | 6 | opaque identifier, contract Q6 NOTE |
| the same fragments repeated across the pass-1 / pass-2 envelope copies | 2 | duplicates of the above |

Result: 0 hits on both scans under contract Q6 and its 2026-09-04 opaque-identifier NOTE. No
retracted figure appears in any file this row adds, in any context.
