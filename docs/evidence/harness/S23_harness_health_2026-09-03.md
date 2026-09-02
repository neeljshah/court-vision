# S23 -- harness_health MCP artifact generator (implementer memo)

2026-09-03 | S23 implementer | claim: handler no_data -> ok | n = 5 (CONSTRUCT),
the five composed sections enumerated below | contract B1-B10 + Q1-Q8, Q6 language.

## Premise (step 0, Q8) -- CONFIRMED, not falsified
Handler `harness_health()` at `scripts/platformkit/mcp_server/artifact_tools.py:147`
tries `_HEALTH` (:20-24) in order: (1) `data/frontend/analytics/harness_health.json`
<- FIRST, the write target; (2) `data/cache/analytics_verify/harness_health.json`;
(3) `scripts/platformkit/analytics_showcase/out/harness_health.json`. All three
ABSENT at lane start (`test -f`). Fields it reads (:153-157): `golden_verdicts`
(key `golden_verdicts` or `golden`), `null_ship_calibration` (`null_ship_calibration`
or `null_ship`), `retro_correction_survivors`, `multiplicity_ledger_K` (or `K`),
plus `as_of` via `_as_of()` (prefers `as_of`/`generated_at`/`updated_at`/`created_at`,
else mtime) and `source_artifact` = the rel path read.

BEFORE, via `tools.handler_for("harness_health")({})`:

    {"status": "no_data", "category": "harness_health",
     "source_artifact": "data/frontend/analytics/harness_health.json",
     "as_of": null, "note": "harness-health artifact absent or unreadable"}

## Change
NEW `scripts/platformkit/eval_gate/harness_health_report.py` (207 LOC, ASCII):
`build(out_path=None, root=ROOT) -> dict` + `__main__`. Composes, read-only:

| section | source | today |
|---|---|---|
| golden | `tests/fixtures/golden/game_states.json` scored by the UNMODIFIED `run_gate_in_process(offline_predict_fn)` (7.7 s, offline) | exit_code 0; nba_2023_24 n=51 BEHIND bss -0.2411; nba_2024_25 n=52 MATCHES_CLOSE bss -0.1884; mlb_2024 CORPUS_ABSENT |
| null_ship | `scripts/platformkit/eval_gate/post_hardening_revalidation_report.txt` | candidates 200, ships 0, observed_null_ship_rate 0.0, ceiling 0.1, PASS, 2 exploits BLOCKED |
| retro_correction | `scripts/platformkit/eval_gate/retro_correction_report.txt` footer | survivors 0, catalog_signals_on_disk 60, n_trials_this_sweep 85 |
| fwer_ledger | `data/cache/eval_gate/backtest_fwer.jsonl` (READ-ONLY) | rows 13, k_cumulative_max 13, last_at 2026-09-01T23:39:17.271881+00:00 |
| gate_manifest | `data/cache/eval_gate/gate_manifest.json` | rows_ok 19, rows_unreadable 0 |

`as_of` = MAX of the composed artifacts' OWN timestamps (declared field, else file
mtime) = `2026-09-01T23:39:17.271881+00:00`, labelled `as_of_source=fwer_ledger`.
`generated_at` (wall clock) is separate and never feeds `as_of`. An absent or
unreadable input gives that section `{"status":"no_data","path":<tried>}` -- no
exception, no invented number. Two handler-facing aliases are written so the tool
does not serve nulls: `retro_correction_survivors` 0, `multiplicity_ledger_K` 13.
The null-ship report's own `status=FINAL` is kept as `report_status` so it cannot
clobber the section status. The artifact path is GITIGNORED (`.gitignore:503
data/*`), so it stays LOCAL and is NOT in the commit.

AFTER, same call, handler unchanged:

    {"status": "ok", "category": "harness_health",
     "source_artifact": "data/frontend/analytics/harness_health.json",
     "as_of": "2026-09-01T23:39:17.271881+00:00",
     "golden_verdicts": {...3 corpora...}, "null_ship_calibration": {...},
     "retro_correction_survivors": 0, "multiplicity_ledger_K": 13}

The artifact's own `source_artifact` field lists all five composed paths.
## Test
`python -m pytest scripts/platformkit/eval_gate/test_harness_health_report.py -q`
-> `4 passed in 1.64s`. tmp-root: two planted inputs (fwer ledger, gate manifest)
+ three absent (golden, null_ship, retro) -> ok/no_data correct, each no_data
names the path tried; `as_of` = the MAX planted stamp (2026-09-01T23:25:28.871310
+00:00 over 2026-08-01T00:00:00+00:00), not the wall clock; the written JSON
round-trips to the returned payload; malformed JSON yields no_data / zero rows
instead of raising. Reader regression, single file:
`tests/platformkit/mcp_server/test_artifact_tools.py` -> `5 passed in 2.64s`.

## FWER ledger untouched (READ-ONLY)
    before  52785ad273e24782dc7e94eeffbd47ed23c1a198d8a9d717e767d9947bb24cb7
    after   52785ad273e24782dc7e94eeffbd47ed23c1a198d8a9d717e767d9947bb24cb7
Byte-identical; no `_charge_ledger` call in the new module.
`git status --porcelain scripts/platformkit/mcp_server/` EMPTY -- no MCP file edited.
A5: `git grep -l harness_health` hits only `artifact_tools.py` + its two tests.

## NOT VERIFIED
- The golden section is recomputed each build on the SYNTHETIC fixture: a
  regression/leak anchor, NOT a calibration claim about any real corpus.
- Determinism of the Romano-Wolf / SPA bootstraps across runs was not measured;
  one build was compared against one direct gate run.
- `staleness_days` in the gate manifest is not surfaced or gated on (that is S09).
- The two fallback artifact paths are never written and remain untested.
- No scheduler or hook refreshes the artifact; it is stale until `build()` re-runs.
- Q1 seal: composition infrastructure, not a scored comparison entering a prereg
  or charged trial, so no prereg seal was created or claimed.
