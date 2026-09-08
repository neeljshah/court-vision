# S313 attempt 2 -- route-status table (2026-09-08)

Exhaustive declared S313 route construct (6 funnel stages + 2 connection entries), rescored after
S296 (74bd5ad45), S310 (2a708672e) and S293 (4a41c436e) landed. `NOT_TESTABLE` is a MEASURED refusal
naming the exact prerequisite; it never stands in for a number. The CONNECTION 2 entrypoint string
carries the correction filed by `docs/evidence/harness/S313_VERIFY_2026-09-07.md`.

| scope | declared route | reader / entrypoint | attempt 1 | attempt 2 | receipt now carried |
|---|---|---|---|---|---|
| DATA | S223 source census -> S232 candidate manifest | `scripts/platformkit/intel_foundry_queue.py:load_manifest` | CONSTRUCT ONLY | CONSTRUCT ONLY | no -- S223 census exists but is not an answer-ready source receipt |
| SIGNALS | S232 candidate -> factory outcome | `scripts/platformkit/intel_foundry_queue.py:enqueue_scratch` | NOT_TESTABLE | NOT_TESTABLE | no -- S232 is a dry-run only; no applied factory outcome exists |
| MODELS | S296 full-boxscore OOF receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | NOT_TESTABLE | CONNECTED (route R1) | yes -- S296 receipt sha256 ed618ec3...a495, label NULL survives |
| ENGINES | S310 tail-beta receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | NOT_TESTABLE | CONNECTED (route R2) | yes -- S310 receipt sha256 7713397f...e5fb, label CLOSED AT LIMIT survives |
| PREDICTIONS | S312 teacher receipt -> answer | `resolver_registry.resolve` (`mechanism_effect`) | NOT_TESTABLE | NOT_TESTABLE (route R3) | no -- prerequisite S312 has not landed; S312 is BLOCKED-ON S314 |
| INTELLIGENCE | accepted receipt -> composed response | `contract_client.answer` -> `resolver_registry.resolve` | NOT_TESTABLE | CONNECTED (R1, R2, R4) | yes -- three composed answers quote receipt, hash, basis, n, CI and as-of |
| CONNECTION 1 | S223 source -> S232 candidate -> factory outcome | `scripts/platformkit/ingame/s279_ingame_signal_stacker.py` reads S223; the S232 queue is separate | NOT_TESTABLE | NOT_TESTABLE | no -- no factory application outcome links the construct to a receipt |
| CONNECTION 2 | accepted receipt -> resolver -> answer feedback | `contract_client.answer -> resolver_registry.resolve`; `tools.py:_ask -> resolver_registry.resolve` (envelope only) | NOT_TESTABLE | CONNECTED, OFFLINE VERIFIED / LIVE NOT VERIFIED | yes offline -- the resident consumer reads the main-repo tree, which does not yet carry these rows |

Stage tally: 3 of 6 funnel stages (MODELS, ENGINES, INTELLIGENCE) and 1 of 2 connection entries
now carry a real trace receipt. CONNECTION 2 is a connection entry, never a funnel stage, so it
is counted once, in the connection tally only (fix 2b correction, 2026-09-08; attempt 2 counted
it in both). The spec bar is 6/6 and 2/2, so the bar is NOT met and no bar was moved.

## The five asked routes (prereg section 3), as run

| id | question | status | label in `findings[0].verdict` | label survived composed answer | numbers equal receipt | citation |
|---|---|---|---|---|---|---|
| R1 | what does the evidence say about s296 boxscore distribution plus minus | ok | NULL | yes | yes (0.017225, CI [-0.024603, 0.016096], n 78767) | source_artifact + as_of present |
| R2 | what does the evidence say about s310 ingame tail beta offset | ok | CLOSED AT LIMIT | yes | yes (0.113579822 -> 0.117737205, -0.004157383, CI [-0.010714071, +0.001495545], n 1267) | source_artifact + as_of present |
| R3 | what does the evidence say about s312 tracking teacher student connection | ok | NOT_TESTABLE | yes | n/a -- no number emitted, prerequisite S312 and blocking row S314 named | source_artifact + as_of present |
| R4 | what does the evidence say about s293 tail log loss rail | ok | BEHIND | yes | yes (0.028761870222461097 -> 0.030833806300609553, -0.002071936078148454, n 308756 over 1590 games) | source_artifact + as_of present |
| R5 | what does the evidence say about quantum chromodynamics in liquid helium | not_supported | none | n/a | n/a -- numeric claim withheld | registered-hypothesis list cited |

Number equality was checked mechanically: every decimal and every 3-or-more-digit integer quoted in
each composed answer was searched for in that route's own receipt file(s). Zero mismatches. The one
regex artefact is the seconds-and-microseconds fragment of the `as-of` timestamp, which is a machine
clock value, not a claimed number.

Vocabulary follows contract Q6; automated scan required.

Fix 2b (2026-09-08) also made the route fail closed before `status=ok`: a receipt-bearing row
whose named artifact is absent, no longer hashes to the SHA-256 the row quotes, is newer than the
ledger quoting it, or whose stated number no value within 1e-9 reproduces now returns `no_data`
with status, note and source_artifact only -- never a number. A row that measured nothing (R3)
composes no n at all instead of a literal 0.
