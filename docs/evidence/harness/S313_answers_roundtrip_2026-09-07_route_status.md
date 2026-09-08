# S313 route-status table (2026-09-07)

This is the exhaustive declared S313 route construct. `NOT_TESTABLE` is a
measured refusal: it names the exact prerequisite absent in this worktree and
does not stand in for a numeric answer.

| scope | declared route | current reader / entrypoint | status | exact blocking fact |
|---|---|---|---|---|
| DATA | S223 source census -> S232 candidate manifest | `scripts/platformkit/intel_foundry_queue.py:load_manifest` | CONSTRUCT ONLY | S223 census is present, but it does not establish an answer-ready source receipt. |
| SIGNALS | S232 candidate -> factory outcome | `scripts/platformkit/intel_foundry_queue.py:enqueue_scratch` | NOT_TESTABLE | S232 records a dry-run only; no applied factory outcome or accepted receipt exists. |
| MODELS | S296 full-boxscore OOF receipt -> answer | `scripts/platformkit/answers/resolver_registry.py:RESOLVERS` | NOT_TESTABLE | `docs/evidence/harness/S296_full_boxscore_oof_2026-09-04.md` is absent. |
| ENGINES | S310 tail-beta receipt -> answer | `scripts/platformkit/answers/resolver_registry.py:RESOLVERS` | NOT_TESTABLE | `docs/evidence/harness/S310_tail_beta_offset_2026-09-04.md` is absent. |
| PREDICTIONS | S312 teacher receipt -> answer | `scripts/platformkit/answers/resolver_registry.py:RESOLVERS` | NOT_TESTABLE | `docs/evidence/harness/S312_teach_connection_2026-09-07.md` is absent. |
| INTELLIGENCE | accepted receipt -> composed response | `scripts/platformkit/answers/contract_client.py:answer` through `resolver_registry.resolve` | NOT_TESTABLE | No accepted S296/S310/S312 receipt and no S313-specific registered category exist. |
| CONNECTION 1 | S223 source -> S232 candidate -> factory outcome | `scripts/platformkit/ingame/s279_ingame_signal_stacker.py` reads S223; S232 queue is separate | NOT_TESTABLE | No factory application outcome links the source/candidate construct to a receipt. |
| CONNECTION 2 | accepted receipt -> resolver -> answer feedback | `scripts/platformkit/mcp_server/tools.py:_ask` -> registry -> `contract_client.answer` | NOT_TESTABLE | The three accepted-receipt prerequisites above are absent; no answer feedback can be replayed. |

Supported answer entrypoints were enumerated from the registry, MCP tool bridge,
and contract client. No identifier for S296, S310, S312, or an S313 receipt is a
current resolver source. Existing general receipt handling therefore does not
create a connection for a missing receipt.
