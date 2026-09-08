# S313 attempt 2 -- ANSWERS round trip preregistration (sealed before any scoring)

Row S313 (harness <-> intelligence/answers, finish audit package 11, allocated as ANSWERS).
Spec: `docs/evidence/tracking/specs/S313_spec.md`. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`
sections A/B/Q. Consumer contract: `docs/AI_CONSUMER_CONTRACT.md`.
Attempt 1 (`ace9f953d`, verify memo `docs/evidence/harness/S313_VERIFY_2026-09-07.md`) closed
NOT_TESTABLE because the S296/S310/S312 receipts were absent. They are re-checked below.
Vocabulary follows contract Q6; automated scan required.

## 1. Receipts each route consumes (paths + SHA-256 on master at seal time)

| id | row | receipt path | SHA-256 | landed |
|---|---|---|---|---|
| R1 | S296 | docs/evidence/harness/S296_full_boxscore_oof_2026-09-07.md | ed618ec301b8edbf351714233c6cc69c15885f7fc013cd8fcd3c7ffefba2a495 | 74bd5ad45 |
| R2 | S310 | docs/evidence/harness/S310_tail_beta_offset_2026-09-07.md | 7713397fc16d2361343e90f9bcf2e4ae2994fd66098391b9bb1883f5078ae5fb | 2a708672e |
| R3 | S312 | ABSENT -- no S312 result exists; prerequisite named, never a number | n/a | not landed |
| R3b | S312 spec (blocked-state evidence) | docs/evidence/tracking/specs/S312_spec.md | 816350ba70fde99f25beadb9ab65d1e73e2660545eaaad3ca3d0b606032ecb52 | n/a |
| R3c | S314 (the blocking row) | docs/evidence/harness/S314_teach_packet_qualification_2026-09-07.md | 9117329d4361514bebf0966295b3bdb7375a8dcd938bcba7b8d314b6b724f5b7 | ef4504489 |
| R4 | S293 | docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md | 288635e41b242dad685156a5f814351bd025228e63801947cdf1a955c72b606d | 4a41c436e |
| R4b | S293 summary | docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_summary.json | f8c40d3d46d9ff1d502c3c430d5c8e4f88d9ebdd060cfd88de40d3eb39abd6c1 | 4a41c436e |

Answer-layer state at seal time: `domains/basketball_nba/knowledge/validation_ledger.jsonl`
SHA-256 `1d32d42fc81edf713baa9dedde2c1117ac504b488047e367d515d65cc69c9478`, 85 rows, 74 unique
hypotheses, none of them S296/S310/S312/S293. All four questions below therefore return
`not_supported` at seal time; that baseline is recorded in the artifact directory.

## 2. The connection built (safe tree only)

Four receipt rows are APPENDED to `domains/basketball_nba/knowledge/validation_ledger.jsonl`
(a `domains/` adapter tree; the file is the declared `source_artifact` of the registered
`mechanism_effect` category in `scripts/platformkit/answers/resolver_registry.py:173`, and its
loader re-reads it on every call). Additive only: no field is renamed or removed, no existing row
is edited, no schema key is dropped. Nothing under `api/`, `intel/`, `src/`, `kernel/`,
`data/registry/`, `data/` or `docs/research/` is written. No flag is flipped.

## 3. Questions (at least one per route) and the labels that must survive

| id | question (verbatim, asked as-is) | ledger hypothesis | label that must survive |
|---|---|---|---|
| R1 | what does the evidence say about s296 boxscore distribution plus minus | s296_boxscore_distribution_plus_minus | NULL |
| R2 | what does the evidence say about s310 ingame tail beta offset | s310_ingame_tail_beta_offset | CLOSED AT LIMIT |
| R3 | what does the evidence say about s312 tracking teacher student connection | s312_tracking_teacher_student_connection | NOT_TESTABLE |
| R4 | what does the evidence say about s293 tail log loss rail | s293_tail_log_loss_rail | BEHIND |
| R5 | what does the evidence say about quantum chromodynamics in liquid helium | none (out of domain) | the numeric claim is withheld |

R3 carries NO number by construction (spec LIMIT, line 16): its note names the exact missing
prerequisite S312 and the row blocking it, S314.

## 4. Envelope fields that must carry each label verbatim

The `mechanism_effect` envelope is the unit of proof. Required, byte-exact:

- `findings[0].verdict` -- carries the label string exactly (`NULL`, `CLOSED AT LIMIT`,
  `NOT_TESTABLE`, `BEHIND`). Any case change, truncation or synonym is a route FAIL.
- `findings[0].effect_local`, `findings[0].n`, `findings[0].p`, `findings[0].corpus` -- verbatim.
- `findings[0].note` -- carries basis, CI, `measured_as_of`, receipt path and receipt SHA-256; it
  must appear in the composed answer unchanged.
- `source_artifact` and `as_of` -- both present and non-empty (consumer contract rule 3).
- `framing` -- present and repeated by the composer.

The composed answer is `scripts/platformkit/answers/contract_client.answer(...)`, the executable
form of `docs/AI_CONSUMER_CONTRACT.md`. Both the direct resolver envelope and the composed string
are recorded.

## 5. Completion-manifest schema

`docs/evidence/harness/S313_attempt2_artifact/completion_manifest.json`:

```
{ "row": "S313", "attempt": 2, "as_of": "<iso8601>",
  "consumable_today":  [ {"row","label","receipt","receipt_sha256","question","category","landed"} ],
  "not_testable":      [ {"row","prerequisite","blocking_row","reason"} ],
  "labels_survived":   { "<label>": {"route","survived": true|false} },
  "refusal":           {"question","status","numeric_claim_withheld": true|false},
  "liveness":          "<OFFLINE VERIFIED / LIVE NOT VERIFIED | LIVE VERIFIED>",
  "absorbed_s290_capability_manifest": {"source","sha256","nba","mlb","soccer","tennis"},
  "scan": {"words_hits","digits_hits"} }
```

## 6. Pass rule (applied exactly, nothing else)

PASS requires ALL of:
1. R1, R2, R3, R4 each return `status == "ok"` from the real resolver.
2. Every label in section 3 appears verbatim in that route's `findings[0].verdict` AND survives
   into the composed answer string unchanged (NON-TAUTOLOGY, spec line 32).
3. Every number quoted in a route's answer equals the receipt to the printed digits.
4. Every route answer carries a non-empty `source_artifact` and `as_of`.
5. R3 quotes NO number and names the exact prerequisite (S312) and blocking row (S314).
6. R5 withholds the numeric claim (a `not_supported`, `no_data` or `refused` status; a correct
   refusal is a pass, spec ACCEPTANCE `sign`).
7. The round trip repeats identically from a FRESH consumer process (spec LIVENESS).
8. Both automated scans over every new file report zero non-exempt hits (contract Q6 and its
   2026-09-04 opaque-identifier NOTE).

Any route failing 1-5 -> PARTIAL naming that route. A prerequisite found absent -> NOT_TESTABLE
naming it. No bar is moved; the +0.004 frozen bar is not an input here and is untouched. A
label dropped from the manifest to raise coverage is an automatic REJECT.

## 7. Seal

This file is sealed by its own SHA-256, recorded in the memo, and committed ALONE before the
first metric is computed.
