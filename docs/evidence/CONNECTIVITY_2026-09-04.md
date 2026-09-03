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

## S167 Connectivity Follow-ups - 2026-09-04

This additive re-measurement preserves every landed S160 row above. The L9 scope is
local Markdown targets plus inline-code repository-relative paths containing a slash;
brace groups expand to individual paths; external URLs, anchors, prose, and bare
filenames are excluded. The denominator is the four S167 follow-up links, and all
four rows below are re-quoted (4/4).

| Link | Command | Exit | Number | Verdict | Denominator / notes |
|---|---|---:|---|---|---|
| L4 (S167) | `python scripts/platformkit/proof_mlb/run_proof.py --corpus data/domains/mlb --report <temp>/PROOF_RESULT.md --paper-book-dir <temp>/paper_book` | 1 | V3 expected REJECT=actual REJECT: 6/6; overall PARTIAL/FAIL | FAIL | 2 corpora x 3 signals. The gitignored `src/prediction/bet_grades.py` was copied read-only from `C:/Users/neelj/nba-ai-system` before measurement. Temp overrides prevented all report and paper-book writes under `data/`. |
| L8 (S167) | `from scripts.platformkit.mcp_server.artifact_tools import harness_health; from scripts.platformkit.mcp_server.tools import _system_health; harness_health({}); _system_health({})` | 0 | harness_health status=no_data; system_health status=ok | PASS | 2/2 located in-process handlers. This corrects the prior wrong path; the calls are read-only envelopes, not a live probe. |
| L9 (S167) | `parse docs/PUBLIC_EVIDENCE.md local Markdown and scoped inline-code paths; assert Path.exists()` | 0 | 31/34 unique paths exist | FAIL | 34 unique scoped artifact paths. Missing: `.claude/commands/workday-loop.md`, `data/intelligence`, `data/nba_ai.db`. This replaces the prior 23 occurrence count with a unique-path denominator. |
| L2 (S167) | `python -m scripts.platformkit.calibration_scoreboard --no-write` | 0 | NBA n=4,846 ECE 0.02614 -> 0.01755; TENNIS n=9,006 0.04951 -> 0.01856; MLB n=8,395 0.01732 -> 0.01379; SOCCER n=25,834 0.03294 -> 0.03128 | PASS | 4/4 scoreboard sport rows. `--no-write` printed `Artifact not written (--no-write).`; default CLI behavior remains the writer path. |
| L9 correction (S167, 2026-09-04) | `python os.path.exists over the 34 unique scoped paths from C:/Users/neelj/nba-ai-system` | 0 | main repo 34/34; worktree 31/34 | PASS / FAIL | Main-repo measurement was read-only. Worktree absences are `.claude/commands/workday-loop.md`, `data/intelligence`, and `data/nba_ai.db`; all are gitignored there. |

## S167 Contract self-check

Sections B and Q: PASS. This section is additive. No threshold, landed S160 row,
FWER ledger, feature flag, or `data/` path was written. L4 records the observed
partial/fail result; L9 records the three absent paths rather than treating the
old occurrence count as a pass. All language is calibration and connectivity only.

## S167 NOT VERIFIED

- L8 verifies local handler reachability only; it does not perform a live-system probe.
- The three absent L9 paths are not substituted or inferred to exist.
- L4 is a local corpus re-measurement only; its V1 calibration failure remains reported.
