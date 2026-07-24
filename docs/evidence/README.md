# Evidence Hub -- claim, receipt, reproduce, one page per claim family

> The most transparent sports forecaster you can audit -- every prediction pre-registered,
> every number gated, including the ones that refuted me. The product is a **calibrated**
> predictor, not a betting-edge product; an honest REJECT or null is a success, and where a
> live market matches or beats us that is stated plainly, in numbers.

Each page below states one claim, traces every figure to a committed artifact, and shows how
to reproduce it. **How to audit:** every number is copied verbatim from a committed JSON under
[`scripts/platformkit/analytics_showcase/out/`](../../scripts/platformkit/analytics_showcase/out/)
or a committed builder/test -- never re-derived from memory; each page carries a *Reproduce on a
fresh clone* block; the single truth-source for any figure is
[docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md); and the one command in the
[proof section](#one-command-proof) re-runs every showcase module and reports pass/fail. Nothing
here is a dollar/ROI/edge claim -- the artifacts carry `edge_claimed: false` in their own metadata.

---

## Self-refutation and honesty

The discipline that catches a good-looking number when it is wrong, and keeps the negative result.

| Page | What it shows | Strongest single receipt |
|---|---|---|
| [retraction-story](retraction-story.md) | The flagship: I built the instruments that refuted my own four headline numbers, and wrote down the negatives instead of deleting them. | Four headline numbers each traced to the artifact that refuted them (e.g. the pregame-ROI grader that bet the market's devigged lean and never read the model, `gate1_full_analysis.json` -> model's own number -2.00%). |
| [leak-instruments](leak-instruments.md) | The harnesses built to *refute*, not confirm: walk-forward leak guard, truncation invariance, multi-corpus gate, ship gate. | `walk_forward_backtester.py` asserts `max_train_date < min_test_date` on *every* fold, so a temporal leak raises instead of silently inflating the score. |
| [execution-honesty](execution-honesty.md) | A full paper-execution stack with no code path to a real order, whose audit publishes its own nulls. | `paper_execution_audit.json`: 83 logged paper bets, all `executed=False`, `edge_claimed=false`, `realized_clv_pct` null for all 37 settled rows (no close feed = no CLV). |
| [knowledge-engine](knowledge-engine.md) | Sports folklore in, pre-registered leak-free verdicts out; nulls kept as first-class results. | 50.4% survival over 256 testable hypotheses (129 confirmed) -- nulls outnumber confirms 2.1x across ledgers (`mechanism_survival.json`, `honesty_exhibit.json`). |
| [industry-metrics](industry-metrics.md) | The public player-metric landscape mapped: three honest approximations built, the RAPM family declared out of reach, a do-not-fake list for the rest. | Aging curves returned as verdict `not_buildable` (no age column in any table) rather than a fabricated curve (`aging_curve_lite.json`). |
| [cross-corpus-replication](cross-corpus-replication.md) | The two-corpora discipline: a hypothesis is not confirmed until the same effect reproduces on an independent second corpus; the single-fold artifacts that failed are kept and labelled, not deleted. | Tennis pregame prior REPLICATED both directions (ATP-train/WTA-test Brier 0.1698->0.1597 n=40516; WTA-train/ATP-test 0.155->0.1432 n=14559), while the MLB divergence-bucket table is buried as `ARTIFACT_CONFIRMED` (`gate_tennis.json`, `mechanism_survival.json`). |

## Calibration and market

Prediction quality measured against the market baseline -- including where the market wins.

| Page | What it shows | Strongest single receipt |
|---|---|---|
| [ingame-conditioning](ingame-conditioning.md) | The one measured calibration win -- in-game conditioning sharpens the win-prob forecaster -- with the market-comparison losses stated plainly. | Static->conditional Brier NBA 0.209 -> 0.159, MLB 0.241 -> 0.126 (real-corpus OOS, `edge_claimed=False`); yet at the one powered checkpoint the market is sharper (end_q1 delta -0.0084 [-0.0161, -0.0008], n=1592). |
| [devig-stack](devig-stack.md) | Four devig methods from scratch (incl. Shin 1992); the Shin-devigged close is the yardstick my own model is graded against. | Recorded MATCH baselines: NBA moneyline Brier 0.1735 vs close 0.1672 (n=372), MLB 0.2429 vs 0.2390 (n=13,992) -- MATCH within noise; totals/ATP TRAIL by the market's freshness edge. |
| [calibration-decomposition](calibration-decomposition.md) | My Brier gap vs the market decomposed into reliability vs resolution, plus the ranked worst-bucket backlog. | MLB model Brier 0.2377 vs market 0.2067 (gap +0.0310), driven mainly by *resolution* (information, not fixable by recalibration), not reliability (`murphy_decomposition.json`). |
| [market-disagreement](market-disagreement.md) | When our model disagrees with the market, who wins -- bucketed by disagreement size, tracked over calendar time. | At the biggest disagreements (`>=.10`) the model is closer only 37.7% of the time in MLB and 21.5% in soccer, market Brier lower in both (`market_disagreement_profile.json`). |

## Engineering depth

Systems built from primitives -- CV, simulation, data, serving, and the AI-engineering surface.

| Page | What it shows | Strongest single receipt |
|---|---|---|
| [cv-pipeline](cv-pipeline.md) | Broadcast video to court coordinates on a consumer RTX 4060, tracker math from primitives, with the not-demonstrated list stated. | 17,254 `cv_features` rows across 241 games / 252 real NBA player IDs; homography unit tests 7/7 pass -- and CV features carry ~0.0 SHAP importance today, stated as an honest non-result. |
| [possession-simulator](possession-simulator.md) | Possession Monte Carlo whose teammate correlation *emerges* from mechanics, graded by game-state cell. | Emergent teammate pts-pts rho ~ -0.10 matches realized (measured -0.104 in `sgp_from_sim.py`), fixing a prior sim's hand-tuned +0.65 (wrong sign and magnitude). |
| [player-props](player-props.md) | A 7-stat projection stack published under two explicitly-labeled measurements, never mixed, with a drift-guarded verify. | Production holdout PTS MAE 4.83 (20,354 rows) vs walk-forward OOF 4.58 (~51K rows/stat); `verify_production_mae.py` exits nonzero on >0.02 drift. |
| [data-layer](data-layer.md) | Keyless, leak-safe, as-of-stamped multi-sport data platform that audits its own completeness. | 103,048 generated claims across 103 families; sidecar re-derived 101,864 of 101,865 sampled with 0 mismatches (98.85% covered) (`claims_corpus_meta.json`). |
| [operations-reliability](operations-reliability.md) | Unattended systems that fail *visibly*: watchdog fleet, hardened alerting, sentinels, and a health readout that honestly reports RED. | `system_proof.py` returns `OVERALL: RED` naming the broken subsystems (1/45 heartbeats RED) after the fix (`2eedc37e`) that stopped a decorative green; restart verified all_ready 44/44. |
| [answer-engine](answer-engine.md) | A fail-closed answer engine: one deterministic resolver per question, refusal by default, coverage published *including* the refusals. | `edge_language` category: n=125, 125/125 refused (0% answered); QA regression bank 87/87 pass, a correct `no_data`/`not_supported` counted as PASS (`qa_coverage_stats.json`). |
| [ai-engineering](ai-engineering.md) | The five 2026 AI-engineering hiring skills mapped to committed, runnable artifacts: evals, fail-closed answers, MCP, guardrails, cost-aware routing. | Each of the five is an openable file plus a runnable command; the load-bearing routing decision is a zero-LLM runtime (XGBoost/LightGBM/NNLS/Monte-Carlo/isotonic), no model call in the prediction path. |
| [mcp-live-demo](mcp-live-demo.md) | Three real MCP envelopes captured live: receipt-backed answers, the caveat ladder, and the engine disclosing when the market is sharper. | Live in-game envelope discloses, unprompted, `model_brier 0.2328` > `market_brier 0.1985` over n=615 games in that state bucket, with `edge_claimed: false`. |
| [agent-fleet-direction](agent-fleet-direction.md) | One human directing an agent fleet under fail-closed gates; the authorship split is recountable from `git`, not asserted. | ~91% agent-authored (packet); a fresh git-log recount reads 95.75% of 3,224 commits on the `GSD Executor` identity and 67.9% carrying a `Co-Authored-By: Claude` trailer (`agent_fleet_history.json`). |

*Run the MCP demo yourself: [../MCP_QUICKSTART.md](../MCP_QUICKSTART.md) connects the 9 fail-closed tools to Claude in ~5 min; [../MCP_TOOLS.md](../MCP_TOOLS.md) is the per-tool reference.*

## Frontier measurements

Uniquely-auditable analytics, each with its honest prior-art verdict attached.

| Page | What it shows | Strongest single receipt |
|---|---|---|
| [novel-analytics](novel-analytics.md) | Five market-microstructure/calibration analytics, each with its honest prior-art verdict (2 INCREMENTAL, 1 ALREADY_DONE, 1 N/A), and the market beating our in-game model stated in numbers. | Information-arrival curve: `market_minus_model_brier` is negative at *every* checkpoint and widens late -- MLB -0.015 (inn1) -> -0.0902 (inn9), soccer -0.1122 (0') -> -0.1891 (85') (`info_arrival_curve.json`). |
| [analytical-depth](analytical-depth.md) | The recorded-analytics inventory as evidence: 23 modules, the claims-corpus generated-vs-validated split, the Statcast base, tick microstructure, fail-closed QA coverage. | 23 self-contained analytics modules, each reads real artifacts and re-runs to the same provenance-stamped number; the 693,037-pitch Statcast base sits under the MLB metrics. |
| [true-intelligence](true-intelligence.md) | The counterfactual/context/microstructure/forward-graded/cross-sport wave -- *what-if*, *why*, *when*, *who-grades-the-graders* -- with the not_buildable verdicts shown as prominently as the wins. | Forward claim scoreboard: 259 families, 121 verified vs 134 null-or-worse, honest nulls-per-confirm ratio 1.107, 5 flipped (`fwd_claim_scoreboard.json`); counterfactual star-removal Jokic +0.582 win-prob pts (roster-confounded CEILING, `cf_star_removal.json`). |

---

## One-command proof

One script re-runs every showcase module's own `--check` self-verification, sequentially, and
reports pass/fail/duration. It is a proof tool, so it does not hide gaps: a module with no
`--check` is listed as `NO_CHECK` rather than silently skipped, and a module whose check fails is
reported `FAIL`, not excused.

```
python scripts/platformkit/analytics_showcase/check_all.py
```

Verbatim result of the recorded run (`as_of` 2026-07-22, written to
[`out/check_all_report.json`](../../scripts/platformkit/analytics_showcase/out/check_all_report.json)
as a list of `{module, status, seconds, as_of}` records):

```
total 27  pass 27  fail 0  no_check 0  runtime 12.60s
```

The trail matters as much as the green: the runner's FIRST real run returned
`pass 23 fail 1 no_check 3` and exited nonzero -- `residual_anatomy.py` failed under package
invocation (a bare sibling import that only worked as a bare script) and three modules shipped
without a `--check` self-verifier. All four gaps were fixed the same session (the import made
package-safe, the three missing checks added), and the runner re-run to the 27/27 above. A proof
harness that returns a truthful nonzero and names its own gaps is the same fail-loudly
discipline the [operations-reliability](operations-reliability.md) page is built on.

---

## Reproduce on a fresh clone

A fresh clone ships with **no `data/`** (the private corpora, ledgers, and model artifacts are
local-only and gitignored). So a live re-run of any data-backed page prints `VALIDATION_PENDING`
or fails closed to `no_data` and falls back to the recorded canonical table -- it never fabricates
a number. The committed `out/*.json` artifacts, the four sport `validation_ledger.jsonl` files,
the `tests/fixtures/proof/` corpus, and the per-page tests are the source of record on a bare
clone: run `check_all.py` for the whole showcase, and follow each page's *Reproduce on a fresh
clone* block for the specific commands (per-file tests only -- never the full suite). What a
reviewer can verify without any private data is exactly the point: the code, the unit tests, the
committed JSON, and that every degraded path reports pending instead of inventing a result.

---

*Honesty rail (applies to every page here): all prediction numbers are calibration / sharpness
(Brier / RMSE / ECE / MAE), never a dollar edge; retracted measurement artifacts appear only
inside [JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md), never as a live result. Truth-source:
[JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
