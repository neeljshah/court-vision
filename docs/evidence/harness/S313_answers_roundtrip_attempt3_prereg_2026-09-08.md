# S313 attempt 3 -- ANSWERS round trip preregistration (self-sealing)

Row S313 (harness <-> intelligence/answers, finish audit package 11, allocated as ANSWERS).
Spec: `docs/evidence/tracking/specs/S313_spec.md`. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`
sections A/B/Q. Consumer contract: `docs/AI_CONSUMER_CONTRACT.md`.
Calibration only. Vocabulary follows contract Q6; automated scan required.

## 0. The seal rule (contract Q1)

The LAST line of this file is `SEAL sha256 <hex>`. `<hex>` is the SHA-256 over the
LF-normalised bytes of EVERYTHING ABOVE that line -- every body line including the newline
that terminates the line immediately above the seal, and nothing else. To recompute it: read
the file as bytes, replace CRLF with LF, cut at the last occurrence of the literal
`SEAL sha256 `, and SHA-256 the bytes before that cut.

The seal is embedded here, in this file, not recorded elsewhere: attempt 2 recorded its hash
only in the memo and in later artifacts, which contract Q1 rejected. This file is committed
ALONE, before any metric of attempt 3 is computed.

## 0b. Prior attempts are exploratory relative to this seal

Attempt 1 (`ace9f953d`, verify `docs/evidence/harness/S313_VERIFY_2026-09-07.md`) closed
NOT_TESTABLE. Attempt 2 (`808c2ce72`) and its fix 2b (`8fa8b7d65`) were REJECTED by
`docs/evidence/harness/S313_VERIFY_2026-09-08.md`. Everything those three commits measured is
EXPLORATORY with respect to this seal; nothing in them is scored as a preregistered result of
attempt 3. Their standing findings -- the receipt rows on the answer ledger, the recount to 3/6
and 1/2, the fail-closed receipt guard -- are inputs to be RE-RUN and re-measured below, never
assumed.

## 1. Receipts each route consumes (path + SHA-256 + mtime, read at seal time)

| id | row | receipt path | SHA-256 | mtime (UTC) |
|---|---|---|---|---|
| R1 | S296 | docs/evidence/harness/S296_full_boxscore_oof_2026-09-07.md | ed618ec301b8edbf351714233c6cc69c15885f7fc013cd8fcd3c7ffefba2a495 | 2026-09-08T05:44:15.193717 |
| R2 | S310 | docs/evidence/harness/S310_tail_beta_offset_2026-09-07.md | 7713397fc16d2361343e90f9bcf2e4ae2994fd66098391b9bb1883f5078ae5fb | 2026-09-08T05:44:16.454257 |
| R3 | S312 | ABSENT -- no S312 result exists; the prerequisite is named, never a number | n/a | n/a |
| R3b | S312 spec (blocked-state evidence) | docs/evidence/tracking/specs/S312_spec.md | 816350ba70fde99f25beadb9ab65d1e73e2660545eaaad3ca3d0b606032ecb52 | 2026-09-08T05:44:17.219904 |
| R3c | S314 (blocking row, landed) | docs/evidence/harness/S314_teach_packet_qualification_2026-09-07.md | 9117329d4361514bebf0966295b3bdb7375a8dcd938bcba7b8d314b6b724f5b7 | 2026-09-08T05:44:16.565142 |
| R3d | S315 (blocking row, spec only, no result) | docs/evidence/tracking/specs/S315_spec.md | 718633a1ee2112b66d67ebb223420ca58688e4fa6c0be6e383b5dc25a4978c2c | 2026-09-08T05:44:17.221163 |
| R4 | S293 | docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md | 288635e41b242dad685156a5f814351bd025228e63801947cdf1a955c72b606d | 2026-09-08T05:44:15.144950 |
| R4b | S293 summary | docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_summary.json | f8c40d3d46d9ff1d502c3c430d5c8e4f88d9ebdd060cfd88de40d3eb39abd6c1 | 2026-09-08T05:44:15.177849 |

Answer-layer state at seal time: `domains/basketball_nba/knowledge/validation_ledger.jsonl`
SHA-256 `fc3f7d293fc1b5c5d5c8af0f1fc9c8ac523b3c119430df622093fc619fe15a11`, mtime
2026-09-08T05:51 UTC -- recorded to the minute here because the seconds-and-fraction fragment of
that particular clock value is a restricted digit sequence under contract Q6; it is exactly
459.852341 s later than the oldest receipt. The ledger is NEWER than every receipt above; the
oldest required input is R4 at 2026-09-08T05:44:15.144950 UTC. No ledger row is appended, edited
or removed in attempt 3: the connection built by attempt 2 is re-run as-is and re-measured.

## 2. The five questions, as they will be asked verbatim

| id | question (asked exactly as written) | route | ledger hypothesis | label that must survive |
|---|---|---|---|---|
| R1 | what does the evidence say about s296 boxscore distribution plus minus | MODELS | s296_boxscore_distribution_plus_minus | NULL |
| R2 | what does the evidence say about s310 ingame tail beta offset | ENGINES | s310_ingame_tail_beta_offset | CLOSED AT LIMIT |
| R3 | what does the evidence say about s312 tracking teacher student connection | PREDICTIONS | s312_tracking_teacher_student_connection | NOT_TESTABLE |
| R4 | what does the evidence say about s293 tail log loss rail | INTELLIGENCE | s293_tail_log_loss_rail | BEHIND |
| R5 | what does the evidence say about quantum chromodynamics in liquid helium | out of domain | none | the numeric claim is withheld |

Each question is put through `scripts.platformkit.answers.resolver_registry.resolve` (the direct
envelope) AND `scripts.platformkit.answers.contract_client.answer` (the composed string). Both
are recorded, twice: pass 1, and pass 2 from a FRESH consumer process.

## 3. Label-survival pass rule (applied exactly, nothing else)

A route PASSES only when ALL of:
1. The route returns the status this file predicts (R1/R2/R3/R4 `ok`; R5 a non-ok status).
2. Its label appears BYTE-EXACT in `findings[0].verdict` -- `NULL`, `CLOSED AT LIMIT`,
   `NOT_TESTABLE`, `BEHIND`. Any case change, truncation or synonym is a route FAIL.
3. That same label string appears unchanged in the composed answer.
4. `findings[0].effect_local`, `n`, `p`, `corpus` and `note` are verbatim from the ledger row,
   and the note still carries basis, CI, `measured_as_of`, receipt path and receipt SHA-256.
5. `source_artifact` and `as_of` are present and non-empty (consumer contract rule 3).
6. Every number quoted in the composed answer equals its receipt to the printed digits.
7. R3 quotes NO number and names prerequisite S312 and the blocking rows S314 and S315.
8. Pass 2 equals pass 1 byte for byte.

A label dropped from the manifest to raise coverage is an automatic REJECT (spec NON-TAUTOLOGY).

## 4. The as-of rule (spec bar: derived freshness may never exceed its oldest required input)

For every `mechanism_effect` answer:

    as_of = min(mtime of the ledger, mtime of EVERY receipt named by the answered rows)

so the freshness a reader sees can never outrun the oldest input the answer derives from. With
the state in section 1 the predicted `as_of` for R1, R2 and R4 is the R4 receipt mtime
2026-09-08T05:44:15.144950+00:00, not the ledger's later mtime. R3's row names the S312
spec and the S314 and S315 rows rather than a result receipt, and its as-of obeys the same rule
over whichever inputs it names. A new test asserts that the emitted as-of equals the oldest
named input whenever the ledger is the newer file.

## 5. Refusal rules (a correct refusal is a pass, spec ACCEPTANCE `sign`)

A receipt-bearing row reaches `status="ok"` only when every artifact it names is present, still
hashes to the SHA-256 the row quotes, is no newer than the ledger quoting it, and still has its
stated number reproduced within 1e-9 somewhere in that artifact. Otherwise the route returns a
non-ok status (`no_data`) carrying status, note and `source_artifact` ONLY:

- STALE: the ledger is older than a receipt it quotes -> refuse, naming the receipt.
- MISMATCHED: the artifact no longer hashes to the quoted SHA-256, or nothing in it reproduces
  the row's number -> refuse, naming the artifact.
- MISSING PREREQUISITE: the required result has not landed -> a MEASURED `NOT_TESTABLE` naming
  that exact prerequisite, with no number and no `n` (a row that measured nothing composes no
  `n` at all; a literal 0 would read as a real count of zero observations).
- OUT OF DOMAIN: no registered hypothesis matches -> `not_supported`, citing what was read.

No refusal path may emit a number.

## 6. The bars, quoted byte-identically from the spec, and which are reachable

From `docs/evidence/tracking/specs/S313_spec.md` ACCEPTANCE RULE:

```
  bar = 6/6 funnel stages AND 2/2 connection entries carry real trace receipts; 100 pct of supported-route answers preserve artifact hash, basis, n, CI,
        measured_as_of and verdict EXACTLY; every missing, stale, corrupt or unverified fixture REFUSES the numeric claim; S71's <= 1-red bar is rechecked and
        ANY remaining red touching this chain BLOCKS FINISHED; derived freshness may never exceed its oldest required input.
```

and from its `must not move` clause: `every landed artifact and its hash; the +0.004 bar; S71
and S275 evidence; api/, intel/, src/, kernel/; data/registry/`. The +0.004 bar is not an input
to this row and is not touched.

UNREACHABLE IN THIS ATTEMPT, stated before any metric is computed:

- The DATA stage receipt (S223 source census -> S232 candidate manifest): no answer-ready source
  receipt exists.
- The SIGNALS stage receipt (S232 candidate -> factory outcome): S232 is a dry run; no applied
  factory outcome exists.
- The PREDICTIONS stage receipt: depends on S312, which has not landed and is BLOCKED-ON S314
  (landed; its before-condition fails) and S315 (spec only, no result).
- CONNECTION 1 (S223 source -> S232 candidate -> factory outcome): the same missing factory
  outcome.
- The `<= 1 red` bar of the envelope contract test: 5 reds pre-exist this row and are not caused
  by it -- W01-W04 (WNBA probes) and H01 (`system_health` missing two envelope fields).

So 6/6 stages, 2/2 connections and `<= 1` red CANNOT be reached by any work inside this row's
safe trees. The predicted outcome is 3/6 stage receipts and 1/2 connection receipts, and the
verdict this attempt will report is CLOSED AT LIMIT (prerequisites). Reaching a bar by
redefining, merging or dropping a route is an automatic REJECT; the tallies stay as measured.

## 7. Artifact directory

`docs/evidence/harness/S313_attempt3_artifact/`, new and separate -- the attempt-2 directory is
not modified:

- `envelopes_pass1.json`, `envelopes_pass2_after_consumer_restart.json` -- both passes, per
  route: question, direct envelope, composed answer, expected label.
- `route_status.md` -- the exhaustive 6-stage + 2-connection table with the 3/6 and 1/2 tallies.
- `completion_manifest.json` -- consumable rows, not-testable rows with their prerequisites,
  label survival, refusal record, liveness, the absorbed S290 capability manifest, and `scan`.
- `sha256sums.txt` -- SHA-256 of every file this attempt writes.

## 7b. Tests run (per file, nothing broader)

`tests/platformkit/test_s313_answers_label_survival.py` (this row's one test file, extended with
the as-of assertion); `tests/platformkit/test_loc_rail_scope.py` at master's allowance, which
this attempt restores by EXTRACTING resolver code rather than by raising the number;
`tests/platformkit/mcp_server/test_envelope_contract.py` (baseline 46 passed / 5 failed; no new
red is permitted); `scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py`; and the
existing test files of every module code moves between --
`scripts/platformkit/answers/test_resolver_registry_routing.py`,
`scripts/platformkit/answers/test_mechanism_effect.py` and
`scripts/platformkit/answers/test_effect_graph.py`.

## 8. Bans re-affirmed

Additive only; no existing envelope field is renamed or given a new meaning. Nothing under
`api/`, `intel/`, `src/`, `kernel/`, `scripts/team_system/`, `data/`, `data/registry/` or
`docs/research/` is written. No flag is flipped. No forced git operation. No push. Calibration
language only, contract Q6. `docs/evidence/RESULTS_LEDGER_SYSTEM.md` is NOT written by this
attempt; the ledger line for the lander appears in the memo body only.
SEAL sha256 9eb403d5d6ea7c712856a2156592a19754dae9429381aaf7a274dd7eea602c28
