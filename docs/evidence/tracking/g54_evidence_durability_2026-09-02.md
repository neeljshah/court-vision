# G54 evidence durability (2026-09-02)

## Premise reproduced

`RESULTS_LEDGER.md` records two lanes blocked in the same session. G25b could
not reproduce G25 containment because `/tmp/t3b_reemit` was gone after pod
reallocation and the eight replacement tables omitted `frame_width` and
`frame_height`. G26/G38 could not test its oob linkage on the original failure
clips because the tables carrying oob were overwritten by re-tracks. State
record section 7 independently says `/tmp` is lost on pod stop and that
artifacts needed later must be copied to `docs/evidence` first.

## Exact text added

`CODEX_SPEC_TEMPLATE.md`:

> REQUIRED EVIDENCE DURABILITY: before reporting, copy under docs/evidence/ every artifact a verifier must use to reproduce a number: at minimum a summary JSON and the sampled rows. A directory of renders may stay local, but the numbers behind the renders must not.

> RE-EMITTED TABLES: preserve the FULL column set, not only the subset this lane uses; a table written for one purpose can omit columns a later lane needs (for example frame_width and frame_height).

`VERIFIER_CONTRACT.md`:

> A7 Confirm that every evidence path named by the memo exists at verification time; a missing path is NOT VALIDATED, never a silent pass.

## Historical-case prevention walk-through

| Historical case | New clause that catches it | Prevention |
|---|---|---|
| G25b: `/tmp/t3b_reemit` was destroyed and its replacements lacked frame dimensions. | "copy under docs/evidence/ every artifact a verifier must use to reproduce a number" preserves the containment summary JSON and sampled rows before reporting. "preserve the FULL column set" specifically preserves `frame_width` and `frame_height` in any re-emission. | The original containment inputs survive reallocation, and a replacement cannot silently strip the dimensions required to recompute containment. If either durable path is absent, A7 requires a NOT VALIDATED verdict rather than a pass. |
| G26/G38: oob-bearing tennis tables were overwritten before the linkage test. | "copy under docs/evidence/ every artifact a verifier must use to reproduce a number" preserves the oob-bearing sampled rows before a report; those rows are the evidence needed for the linkage number. | A later re-track may replace its working table, but cannot overwrite the committed evidence copy. If the memo names no surviving copy, A7 catches the missing path as NOT VALIDATED. |

The first rule prevents both destroyed-artifact failures; the second, separate
rule prevents the G25b column-stripping failure. A7 makes either omission
observable at verification rather than silently accepting an unreproducible
number.

## `/tmp` path scan

Method: unique Markdown paths shown by `git log --since=2026-09-01` under
`docs/evidence/tracking/`, excluding specs, README files, the contract/template,
ledger, program-state, queue/runbook, handoff, and consolidated spec documents.
The 65 remaining landed memos were scanned for an evidence path matching
`/tmp/<name>`. 17/65 name at
least one such path. The count is a path-level census, not a sampled metric.

## Verifier-contract section B self-check

| Clause | Result |
|---|---|
| B1 | PASS: the 17/65 scan names its full denominator and exclusion rule; no failures were excluded from its result. |
| B2 | PASS: documentation additions only; no schema or reader changed. |
| B3 | PASS: no gate or missing-evidence flow changed. |
| B4 | PASS: no claim or failure path changed. |
| B5 | PASS: no pod copy, deployment, or restart occurred. |
| B6 | PASS: no module, import, or test moved. |
| B7 | PASS: no renders or row sample support this documentation change. |
| B8 | PASS: no fit or residual is asserted. |
| B9 | PASS: the scan denominator is 65 unique memo paths, each counted once. |
| B10 | PASS: no harness threshold or gate value changed. |

## NOT VERIFIED

- No destroyed `/tmp` artifact was recoverable; this documents prevention, not
  historical-artifact recovery.
- No future lane has yet exercised the new durability rule.
- No code was added, so no per-file test applies.
- A future automatic copier is intentionally out of scope; it needs a separate
  orchestrator-assigned gap id.
