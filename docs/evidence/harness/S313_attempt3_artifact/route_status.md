# S313 attempt 3 -- route-status table (2026-09-08)

Exhaustive declared S313 route construct: 6 funnel stages + 2 connection entries, every one
listed, none sampled and none dropped. Rescored after the attempt-3 prereg was sealed and
committed alone (`5b45a5133`, seal `9eb403d5d6ea7c712856a2156592a19754dae9429381aaf7a274dd7eea602c28`).
`NOT_TESTABLE` is a MEASURED refusal naming the exact prerequisite; it never stands in for a
number. The CONNECTION 2 entrypoint string carries the correction filed by
`docs/evidence/harness/S313_VERIFY_2026-09-07.md`.

| scope | declared route | reader / entrypoint | attempt 2 | attempt 3 | receipt now carried |
|---|---|---|---|---|---|
| DATA | S223 source census -> S232 candidate manifest | `scripts/platformkit/intel_foundry_queue.py:load_manifest` | CONSTRUCT ONLY | CONSTRUCT ONLY | no -- the S223 census exists but is not an answer-ready source receipt |
| SIGNALS | S232 candidate -> factory outcome | `scripts/platformkit/intel_foundry_queue.py:enqueue_scratch` | NOT_TESTABLE | NOT_TESTABLE | no -- S232 is a dry run only; no applied factory outcome exists |
| MODELS | S296 full-boxscore OOF receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | CONNECTED (R1) | CONNECTED (R1) | yes -- S296 receipt sha256 ed618ec3...a495, label NULL survives |
| ENGINES | S310 tail-beta receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | CONNECTED (R2) | CONNECTED (R2) | yes -- S310 receipt sha256 7713397f...e5fb, label CLOSED AT LIMIT survives |
| PREDICTIONS | S312 teacher receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | NOT_TESTABLE (R3) | NOT_TESTABLE (R3) | no -- prerequisite S312 has not landed; S312 is BLOCKED-ON S314 and S315 |
| INTELLIGENCE | accepted receipt -> composed response | `contract_client.answer` -> `resolver_registry.resolve` | CONNECTED (R1, R2, R4) | CONNECTED (R1, R2, R4) | yes -- three composed answers quote receipt, hash, basis, n, CI and as-of |
| CONNECTION 1 | S223 source -> S232 candidate -> factory outcome | `scripts/platformkit/ingame/s279_ingame_signal_stacker.py` reads S223; the S232 queue is separate | NOT_TESTABLE | NOT_TESTABLE | no -- no factory application outcome links the construct to a receipt |
| CONNECTION 2 | accepted receipt -> resolver -> answer feedback | `contract_client.answer -> resolver_registry.resolve`; `tools.py:_ask -> resolver_registry.resolve` (envelope only) | CONNECTED, OFFLINE VERIFIED / LIVE NOT VERIFIED | CONNECTED, OFFLINE VERIFIED / LIVE NOT VERIFIED | yes offline -- the resident consumer reads the main-repo tree, which does not carry these rows |

Stage tally: **3 of 6** funnel stages (MODELS, ENGINES, INTELLIGENCE) and **1 of 2** connection
entries carry a real trace receipt. CONNECTION 2 is a connection entry, never a funnel stage, so
it is counted once, in the connection tally only. The spec bar is 6/6 and 2/2, so the bar is NOT
met, no bar was moved, and no route was merged or dropped to raise the tally. The three missing
stage receipts and CONNECTION 1 were declared UNREACHABLE in the sealed prereg BEFORE this run.

## The five asked routes (prereg section 2), as run

| id | question | status | `findings[0].verdict` | label survived composed answer | numbers equal receipt | as-of emitted |
|---|---|---|---|---|---|---|
| R1 | what does the evidence say about s296 boxscore distribution plus minus | ok | NULL | yes | yes (0.017225, CI [-0.024603, 0.016096], n 78767) | 2026-09-08T05:44:15.193717+00:00 |
| R2 | what does the evidence say about s310 ingame tail beta offset | ok | CLOSED AT LIMIT | yes | yes (0.113579822 -> 0.117737205, -0.004157383, CI [-0.010714071, +0.001495545], n 1267) | 2026-09-08T05:44:16.454257+00:00 |
| R3 | what does the evidence say about s312 tracking teacher student connection | ok | NOT_TESTABLE | yes | n/a -- no number emitted; `effect_local` and `n` are present with null values, no numeric value asserted | 2026-09-08T05:44:16.565142+00:00 |
| R4 | what does the evidence say about s293 tail log loss rail | ok | BEHIND | yes | yes (0.028761870222461097 -> 0.030833806300609553, -0.002071936078148454, n 308756 over 1590 games) | 2026-09-08T05:44:15.144950+00:00 |
| R5 | what does the evidence say about quantum chromodynamics in liquid helium | not_supported | none | n/a | n/a -- numeric claim withheld | none (a non-ok envelope carries no as-of) |

Labels survive 5 of 5 routes: the four verdict strings appear byte-exact in `findings[0].verdict`
and unchanged in the composed answer, and R5's refusal survives as a refusal. Number equality was
re-checked mechanically: every decimal and every 3-or-more-digit integer in each composed answer,
with the as-of timestamp excluded as a machine clock value, was searched for in that route's own
receipt file(s) -- 6, 12 and 8 tokens for R1, R2 and R4, zero mismatches. Pass 2, run in a FRESH
consumer process, equals pass 1 route-for-route.

## The as-of floor (spec bar: derived freshness may never exceed its oldest required input)

`scripts/platformkit/answers/receipt_guard.py:as_of` now dates every `mechanism_effect` answer at

    min(ledger mtime, the mtime of EVERY artifact the answered rows name)

The ledger `domains/basketball_nba/knowledge/validation_ledger.jsonl` has mtime 2026-09-08T05:51
UTC and is the NEWER file, so all four answers are dated by their own oldest named input, as the
table above shows -- attempt 2 emitted the ledger mtime for all four, which the verifier rejected.

TWO HONEST DEVIATIONS FROM THE SEALED PREREG, both stated rather than papered over:

1. The prereg's section 4 rule is per-answer ("every receipt named by the answered rows"), but its
   worked example predicted one shared value, the R4 receipt mtime, for R1, R2 and R4. The rule as
   written is what shipped, so each route is dated by ITS OWN oldest input; the predicted value is
   correct for R4 only. The rule, not the worked example, is the thing that was preregistered.
2. The prereg's pass rule item 7 required R3 to name prerequisite S312 and the blocking rows S314
   and S315. The landed ledger row names S312 and S314 but NOT S315, and attempt 3 appends, edits
   or removes no ledger row, so this sub-clause is met 2 of 3. S315 is named as a blocking row by
   `docs/evidence/tracking/specs/S312_spec.md`, not by the answer.

## Refusal behaviour re-verified this run

A receipt-bearing row reaches `status="ok"` only when every artifact it names is present, still
hashes to the SHA-256 the row quotes, is no newer than the ledger quoting it, and still has its
stated number reproduced within 1e-9. Otherwise the route returns `no_data` with status, note and
`source_artifact` only, and never a number. Attempt 3 generalised which references are checked:
any `<path> sha256 <hex>` pair in a row note now counts, not only a `receipt=`/`summary=` labelled
one, so R3's S312 spec and S314 receipt are hash-verified and set its as-of floor too. A row that
measured nothing carries `n` as a null value rather than a literal 0, so composition prints
`effect=None n=None` and no numeric value is asserted. The stale, missing, corrupt and
flipped-basis surfaces are each asserted in
`tests/platformkit/test_s313_answers_label_survival.py` (11 passed).

Vocabulary follows contract Q6; automated scan required.
