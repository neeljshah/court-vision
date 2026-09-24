# Evidence index

Every claim this project makes, in one table: the number, the verdict, the file that proves it,
the command that re-checks it, and the live page that shows it.

**Live analytics site:** https://neeljshah.github.io/court-vision/analytics/

Ground rules for this page:

- **Calibration only.** Nothing here is a dollar, ROI, or betting-edge claim. The documented
  central result is that the market is efficient.
- **Losses are listed.** `MARKET_SHARPER`, `BEHIND`, `UNDERPOWERED`, `REJECT`, and `RETRACTED`
  rows are part of the record, not footnotes.
- **Power is stated before results.** The minimum detectable effect of every market-relative
  row -- which rows could have answered their question at all -- is on
  [docs/evidence/POWER_PAGE_2026-09-22.md](docs/evidence/POWER_PAGE_2026-09-22.md).
- **The corpora are documented before the results.** Data cards and the defect register are on [docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md](docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md).
- **Multiplicity is accounted for in writing.** The 0-of-60 result, its family, K and null are on [docs/evidence/MULTIPLICITY_MEMO_2026-09-22.md](docs/evidence/MULTIPLICITY_MEMO_2026-09-22.md).
- **No row without an artifact.** Numbers are transcribed from the cited file; the audited
  narrative and the do-not-claim list live in
  [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md), and every generated receipt in
  [RECEIPTS.md](RECEIPTS.md).
- **Reproduce** = a command that runs on a fresh clone with no private data
  ([REPRODUCE.md](REPRODUCE.md)). Rows marked *recorded* are read from a committed artifact;
  the corpus behind them is private.

Verdict vocabulary: `MATCHES_CLOSE` / `TRAILS_CLOSE` / `MARKET_SHARPER` / `MODEL_SHARPER_PROVISIONAL` /
`BEHIND` / `UNDERPOWERED` / `REJECT` / `HOLD` / `RETRACTED` / `DESCRIPTIVE`.

---

## A. Pregame calibration against the closing line

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| Pregame team-strength forecasts are within noise of the devigged close on NBA moneyline (underpowered) and trail it by small, interval-resolved margins on MLB moneyline and soccer O/U; nothing beats the close | per-corpus Brier / BSS table | `MATCHES_CLOSE` (NBA) / `TRAILS_CLOSE` (MLB, soccer) | [docs/MARKET_EFFICIENCY_PROOF.md](docs/MARKET_EFFICIENCY_PROOF.md), [docs/evidence/cross-corpus-replication.md](docs/evidence/cross-corpus-replication.md) | recorded |
| NBA pregame win probability, held-out half vs the Shin-devigged close | Brier 0.1735 model vs 0.1666 close, gap +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20, n=372 scored (743 in the overlap; the first half is the fit) | `MATCHES_CLOSE` (CI includes 0; underpowered: MDE 0.0152) | [docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md](docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md), [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section 3 | `python -m scripts.platformkit.eval_gate.dm_recompute_pregame` (private corpora) |
| MLB moneyline and soccer O/U 2.5, held-out half vs the devigged close, game-clustered intervals attached to the proof-page rows | MLB gap +0.0039 [+0.0028, +0.0051], DM p 3.6e-12, n=13,992; soccer gap +0.0076 [+0.0059, +0.0092], DM p 1.1e-19, n=7,558 | `TRAILS_CLOSE` (small, measurable; the proof page's MATCH was a fixed-threshold label) | [docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md](docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md) | same command; test `python -m pytest scripts/platformkit/eval_gate/test_dm_recompute_pregame.py -q` |
| NBA win probability, 3-fold walk-forward | Brier 0.1930 (std 0.0084), n=1,473 | no market baseline in artifact | [results/winprob_walk_forward_results.json](results/winprob_walk_forward_results.json) | [RECEIPTS.md](RECEIPTS.md) row |
| MLB total runs, pregame CRPS vs market | 2.9331 vs 2.8808, delta -0.0523 [-0.1657, 0.0482], n=300 | `UNDERPOWERED` | [last_run_mlb.json](scripts/platformkit/benchmarks/crps_market/last_run_mlb.json) | [RECEIPTS.md](RECEIPTS.md) row |
| Per-sport reliability curves (NBA, MLB, soccer, tennis) | all bins with intervals | `DESCRIPTIVE` | [docs/evidence/calibration/](docs/evidence/calibration/) | [live: calibration](https://neeljshah.github.io/court-vision/analytics/calibration/) |
| Calibration decomposition (reliability / resolution / uncertainty) | per-sport table | `DESCRIPTIVE` | [docs/evidence/calibration-decomposition.md](docs/evidence/calibration-decomposition.md) | recorded |
| NBA player-prop accuracy, production-model chronological holdout | MAE: PTS 4.83, REB 1.92, AST 1.39, FG3M 0.89 (20,354 player-games) | accuracy, no market comparison | [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section 3 | recorded |

## B. In-game conditioning

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| NBA in-game win probability vs market, end of Q1 | Brier 0.2006 vs 0.1922, delta -0.0084 [-0.0161, -0.0008], n=1,592 | `MARKET_SHARPER_PROVISIONAL` | [last_run_ingame_nba_winprob_ALLGAMES_v3.json](scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json) | [RECEIPTS.md](RECEIPTS.md) row |
| NBA halftime / end of Q3 / Q4 under 5:00 | deltas -0.0040 / +0.0011 / +0.0019, all CIs include 0, n=1,593 | `UNDERPOWERED` | same artifact | [RECEIPTS.md](RECEIPTS.md) rows |
| MLB total runs, end of innings 6 / 7 / 8, CRPS vs market | deltas 0.6392 / 0.7327 / 1.4201, CIs exclude 0, n=49-55 | `MODEL_SHARPER_PROVISIONAL` | [last_run_ingame_mlb.json](scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json) | [RECEIPTS.md](RECEIPTS.md) rows |
| Soccer home-win probability, minute 60 / 75 | Brier deltas -0.0931 / -0.1075 (market closer), n=22 / 17 | `UNDERPOWERED` | [last_run_ingame_soccer.json](scripts/platformkit/benchmarks/crps_market/last_run_ingame_soccer.json) | [RECEIPTS.md](RECEIPTS.md) rows |
| Conditioning on realized game state sharpens the forecaster against a STATIC pregame prior | NBA Brier 0.209 to 0.159; MLB 0.241 to 0.126 | sharpness vs static, not vs the market | [docs/INGAME_PROOF.md](docs/INGAME_PROOF.md), [docs/evidence/ingame-conditioning.md](docs/evidence/ingame-conditioning.md) | recorded |

## C. Rejects, retractions, and the instruments that caught them

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| Gate A-0: in-game models against the contemporaneous Kalshi in-play price, paired ticks, game-clustered bootstrap | MLB Brier 0.2377 vs 0.2067, delta +0.0310 [0.0170, 0.0454], 227 games; soccer 0.2279 vs 0.1427, 51 games | `BEHIND` (measured 2026-09-14 on a corpus that later failed the project's own join-integrity check; the per-game segmented revision -- 178 games / 27,351 ticks -- is published on the site with a regeneration receipt, and the verdict is unchanged: the market reference is closer) | [docs/evidence/ingame/GATE_A0_2026-09-14.md](docs/evidence/ingame/GATE_A0_2026-09-14.md), [mlb-ingame-regeneration.json](webapp/public/data/audits/mlb-ingame-regeneration.json) | [live: join-integrity finding](https://neeljshah.github.io/court-vision/analytics/findings/ingame-join-integrity/) |
| Gate B: prior-season player-tracking aggregates added to the per-game prop model | pts / reb / ast all `CEILING_ZERO` across three seasons | `REJECT` | [q06_gate_b_tracking_ablation_summary.json](docs/evidence/props/q06_gate_b_tracking_ablation_summary.json) | recorded |
| Per-game prop model + defender-matchup features | not seed-stable; CRPS underpowered | `HOLD` | [q15c_prop_game_model_matchup_summary.json](docs/evidence/props/q15c_prop_game_model_matchup_summary.json) | recorded |
| Win-probability feature challenger | see memo | recorded verdict | [Q16_WINPROB_FEATURE_CHALLENGER_2026-09-14.md](docs/evidence/pregame/Q16_WINPROB_FEATURE_CHALLENGER_2026-09-14.md) | recorded |
| Signal discovery: 60 candidate signal classes through the leak-free gate | 0 shipped; 513 recorded REJECT / DEFER verdicts | `REJECT` (the expected shape of honest discovery) | [spa_catalog_report.txt](scripts/platformkit/eval_gate/spa_catalog_report.txt), [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section G | recorded |
| The retracted headline figures, what was wrong with each, and how each was caught | six figures | `RETRACTED` | [docs/evidence/retraction-story.md](docs/evidence/retraction-story.md), [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | [live: retraction finding](https://neeljshah.github.io/court-vision/analytics/findings/retraction/) |
| Leak instruments: per-fold date assertion, truncation invariance, staged-path leak guard | tests pass | engineering control | [docs/evidence/leak-instruments.md](docs/evidence/leak-instruments.md), [tests/platform/test_no_leak_paths_staged.py](tests/platform/test_no_leak_paths_staged.py) | `python -m pytest tests/platform/test_no_leak_paths_staged.py -q` |

## D. Intelligence layer

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| Derived intelligence layer between raw data and models | 151 files, manifest per sport | `DESCRIPTIVE` | [docs/INTELLIGENCE.md](docs/INTELLIGENCE.md), [docs/evidence/intelligence/](docs/evidence/intelligence/) | recorded |
| Fact-claims corpus, generated vs re-verified split | 103,048 generated; 101,864 recompute from their declared source and formula (provenance, not predictive accuracy) | `DESCRIPTIVE` | [claims_corpus_meta.json](scripts/platformkit/analytics_showcase/out/claims_corpus_meta.json) | `python -m scripts.platformkit.analytics_showcase.claims_corpus_meta --check` |
| Entity atlas | 1,549 entity cards | `DESCRIPTIVE` | [webapp/public/data/showcase/](webapp/public/data/showcase/) | [live site](https://neeljshah.github.io/court-vision/analytics/) |

## E. The analytics site

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| Every committed showcase artifact re-verifies on a bare clone | 0 FAIL is the bar | CI-enforced | [check_all_report.json](scripts/platformkit/analytics_showcase/out/check_all_report.json) | `python scripts/platformkit/analytics_showcase/check_all.py` |
| Research papers, each with evidence paths checked against the published artifacts | see site | CI-enforced | [webapp/public/data/papers/](webapp/public/data/papers/) | [live: papers](https://neeljshah.github.io/court-vision/analytics/papers/) |
| Published JSON is scrubbed and receipt-checked before deploy | every file | CI-enforced | [webapp/scripts/verify-public-json.mjs](webapp/scripts/verify-public-json.mjs) | runs in [deploy-demo.yml](.github/workflows/deploy-demo.yml) |

## F. Engineering discipline

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| The honesty gate: a build fails on edge language or a retracted figure outside retraction framing | every push | CI-enforced | [webapp-qa.yml](.github/workflows/webapp-qa.yml), [docs/HONESTY_SYSTEM.md](docs/HONESTY_SYSTEM.md) | push |
| Walk-forward harness, leak guard, calibration and deflated-metric code | readable source | engineering sample | [scripts/platformkit/eval_gate/](scripts/platformkit/eval_gate/), [kernel/](kernel/) | `python -m pytest scripts/platformkit/eval_gate/test_leak_contract.py -q` |
| Order-lifecycle code has no reachable live path; tested against a mock exchange | double-gated | engineering control | [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) section G | recorded |


## G. Execution discipline (paper only -- no live order path exists)

Read this section with its caveat: these rows show *discipline*, not a working trading system.
The execution modules below are published as readable source; their wider import closure lives in the
private tree, so they are not runnable from this repository.
The forward paper series is currently dormant, and the in-game models trail the live market
reference (section C). Both facts are part of the record.

| Claim | Number | Verdict | Artifact | Reproduce |
|---|---|---|---|---|
| A complete order lifecycle (submit, ack, partial, fill, cancel/replace, settle) with the live path deliberately unreachable: an explicit `live=True`, an undocumented env flag, and a terminal hard refusal | three independent gates | engineering control | [executor/lifecycle.py](scripts/platformkit/execution/executor/lifecycle.py) | read the module header |
| Pre-registered thresholds, each with its registration date, source measurement and sample size; a threshold moved after seeing its own result is treated as curve-fitting | every constant dated | engineering control | [execution/thresholds.py](scripts/platformkit/execution/thresholds.py) | read the module |
| A venue fee model that fails closed (raises on a unit error rather than returning a zero fee) and names what it could not verify | tested against golden numbers | engineering control | [execution/venue_fees.py](scripts/platformkit/execution/venue_fees.py) | recorded |
| Guards against fabricated closing-line value: off-market prices are filtered at read time without mutating the ledger | two-condition rule | engineering control | [clv_ledger.py](scripts/platformkit/clv_ledger.py) | recorded |
| The circuit breaker gates on the median, not the flattering fat-tailed mean | pre-registered 2026-07-15 | engineering control | [execution/circuit_breaker.py](scripts/platformkit/execution/circuit_breaker.py) | recorded |
| The paper-execution audit publishes its own nulls: every logged paper bet is `executed=False`, and realized closing-line value is null where no independent close feed exists | see artifact | `DESCRIPTIVE` | [docs/evidence/execution-honesty.md](docs/evidence/execution-honesty.md), [paper_execution_audit.json](scripts/platformkit/analytics_showcase/out/paper_execution_audit.json) | recorded |
| A check-then-append race in the ledger writer, closed and proven by a test that races two real OS processes | test passes | engineering control | [clv_ledger_io.py](scripts/platformkit/clv_ledger_io.py), [test_clv_ledger_io.py](scripts/platformkit/test_clv_ledger_io.py) | readable here; runs in the full private tree |
| The bar for any real order is fixed in advance: six gates, including 8 weeks of fee-netted shadow markout with an interval excluding 0 on two market families; no gate may be weakened after its own result | pre-registered 2026-09-17; G6 not started | pre-registration | [docs/GO_LIVE_GATES.md](docs/GO_LIVE_GATES.md) | read the page |
| An integrity checker that fails the project's own headline in-game corpus, shipped with the finding it produced | exit 1 on the original corpus | engineering control | [check_ingame_join_integrity.py](scripts/platformkit/check_ingame_join_integrity.py) | [live: join-integrity finding](https://neeljshah.github.io/court-vision/analytics/findings/ingame-join-integrity/) |

---

**Navigate:** [README](README.md) - [Receipts](RECEIPTS.md) - [Reproduce](REPRODUCE.md) - [Job Evidence Packet](docs/JOB_EVIDENCE_PACKET.md) - [Doc map](docs/INDEX.md)
