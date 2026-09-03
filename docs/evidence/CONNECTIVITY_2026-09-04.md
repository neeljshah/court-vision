# S160 Connectivity Measurement - 2026-09-04

## Scope

This is a read-only construct measurement of the eleven specified product-funnel
links. It records the command, exit code, printed count or status, and verdict
for every link. The premise was remeasured as 11/11 enumerated links. `data/`
was not written. Commands that require an unavailable local corpus, pod, or
ledger are recorded as NOT TESTABLE HERE rather than substituted.

## Measurements

| Link | Command | Exit | Number | Verdict | Notes |
|---|---|---:|---|---|---|
| L1 | `Set-Location scripts/platformkit/eval_gate; & C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe run_all.py` | 0 | 47/47 | PASS | Golden set, walk-forward, Shin, blend, freshness, and ledger scoreboard all printed OK. |
| L2 | `& C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m scripts.platformkit.calibration_scoreboard` | N/A | N/A | NOT TESTABLE HERE | The mandated CLI unconditionally writes `data/frontend/ops/calibration_scoreboard_latest.json`; S160 forbids every write under `data/`, so it was not run. |
| L3 | `& C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m scripts.platformkit.platform_scoreboard` | 0 | 4 sports | PASS | NBA 0.21699 vs 0.21806; MLB 0.24760 vs 0.24398; tennis 0.22055 vs 0.21845; soccer RMSE 0.40059 vs 0.42674. |
| L4 | `& C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe scripts/platformkit/proof_mlb/run_proof.py --corpus data/domains/mlb` | 1 | 0 verdict rows | FAIL | Import chain stopped at missing `src.prediction.bet_grades`; no proof corpus was loaded or signal verdict emitted. |
| L5 | `FOUNDRY_PORTABLE_CORPUS=1; seed_queue --db <temp>/foundry.sqlite --limit 50 --sport mlb; foundry_runner --db <temp>/foundry.sqlite --ledger <temp>/backtest_fwer.jsonl --trials-dir <temp>/trials --max-passes 1 --predictor real --sport mlb --batch 50 --idle-exit` | 0 | screens=50; tracebacks=0 | PASS | Seeded 50. One bounded real-predictor pass completed; 20 promotions were held because charging was off. All generated files were redirected to a unique temp directory. |
| L6 | `ResultsDB(<temp>).record -> family_p_values(family, 'T0') -> dual_bar_verdict(...)` | 0 | p_values=1 | PASS | Temp-only construct call chain returned a dual-bar verdict for `ingame_arms_mlb`; this verifies wiring only and is not a scored finding. |
| L7 | `from predict_service.produce import produce_sport; produce_sport('mlb')` | 0 | predictions=31 | PASS | Dry producer call returned `status=ok` with 31 predictions. |
| L8 | `from scripts.mcp_server.tools import harness_health, system_health; harness_health(); system_health()` | 1 | 0 calls | FAIL | `scripts/mcp_server/tools.py` is absent in this worktree, so the answer-layer tools cannot be imported or called. |
| L9 | `parse local Markdown targets in docs/PUBLIC_EVIDENCE.md; assert (memo.parent / target).exists()` | 0 | 23/23 | PASS | Every local Markdown artifact target cited by the public-evidence memo exists; external URLs were excluded. |
| L10 | `flag_ticks(1 landed MLB joined-store game) -> effective_sample_size -> cluster_bootstrap CI` | 0 | n=557; informative=128; n_eff=128.00 | PASS | One 261,004-byte store file yielded construct CI [-0.025886, -0.025886]. With one game it is necessarily degenerate and is not inferential evidence. |
| L11 | `write_readout(<temp>/clv_ledger.jsonl, <temp>/execution_status.json, <temp>/PAPER_LIVE.md, now_iso=...)` | 0 | n_settled=INSUFFICIENT | PASS | The S20 readout returned `status=no_data`, `n_settled=INSUFFICIENT`, and `verdict=INSUFFICIENT` from an empty temp ledger, without touching the real ledger. |

## Contract self-check

Sections B and Q: PASS. This is additive docs/test evidence only; no field,
threshold, ledger, feature flag, or production artifact changed. No deployment,
scored comparison, or claimed result was made. The only temporary writes were
outside the repository. The L5 runner had charging disabled. The 11-link
denominator is exhaustive by specification, and L10/L11 are explicitly labelled
construct or insufficient where their local denominators cannot support an
inference.

## NOT VERIFIED

- L2's real calibration CLI was not run because it unconditionally writes a
  `data/frontend/ops` artifact, prohibited in this run.
- L4 cannot reach its signal proof because `src.prediction.bet_grades` is absent.
- L8 cannot import either requested answer-layer health tool because
  `scripts/mcp_server/tools.py` is absent.
- L10's one-game CI is a degenerate construct, not multi-game evidence.
- L11 has no settled local paper-ledger rows, so its readout is insufficient.

## Corrections at landing (Opus verifier, 2026-09-04)

- L4 (signal audit) FAIL is a WORKTREE ARTIFACT, not a product defect: src/prediction/bet_grades.py is gitignored
  (.gitignore:408) and exists in the main repo. Re-measure in the main repo -> S167.
- L8 (answer layer) FAIL is a WRONG-PATH finding: the tools live in scripts/platformkit/mcp_server/artifact_tools.py,
  not scripts/mcp_server; harness_health({}) called in process returns exit 0 with envelope status=no_data, so the
  answer layer IS reachable; system_health has no home in that module (locate it) -> S167.
- L9: 23 markdown-link occurrences resolve, but the honest denominator is 14 UNIQUE artifact paths (14/14);
  backticked citations were not in scope -> S167 gives the check a stated scope.
- L2 (calibration report) NOT TESTABLE HERE is true for the reason that __main__ hard-codes write=True (a data/ write),
  not a pod- or ledger-only reason; the same computation is reachable read-only via build_calibration_scoreboard(write=False).
- Verifier reproductions (3/3 in the worktree): L1 47/47 ALL GREEN; L7 status=ok predictions=31 (attribute access on the
  SnapshotEnvelope, not .get()); L9 14/14 unique paths.
