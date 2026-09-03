# S159 Public Repository Sweep

Verdict: **NOT VALIDATED**.

The in-scope documentation defects were repaired, but the fixed acceptance bar is not met. The public HEAD still tracks 61 prohibited-tree paths, and one RETRACTED figure remains unframed in a Python docstring. Both are outside this docs-only lane. The 343 missing citation occurrences are listed below, as required; no artifact was fabricated.

## Scope and reproduction contract

Baseline SHA: `c03c2d597fe4df3a649ea04045e0e7efca30a2b5`.

All before counts were measured read-only on that HEAD before any repository edit. Existence means present in `git ls-files` at the measured revision, because this is a public-repository audit rather than a local-cache audit. A directory exists when at least one tracked path has that prefix. For citations, a basename may resolve to a unique or repeated tracked suffix. A braced template requires every expansion; a glob requires at least one tracked match.

The citation construct scans extension-bearing memo/artifact tokens (`md`, `jsonl`, `parquet`, `sqlite`, `yaml`, `json`, `csv`, `txt`, `yml`, `npz`, `npy`, `pkl`) plus backticked artifact directories. Repeated identical tokens on the same source line count once. External host paths are not relative repository citations. `H:<line>` below means `docs/evidence/HARNESS_GAPS_2026-09-03.md`; `L:<line>` means `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.

## Acceptance metric

| Component | Before | After | Result |
|---|---:|---:|---|
| Broken relative links | 1 | 0 | Bar met |
| Missing citation occurrences | 343 | 343 | Listed; artifacts were not fabricated |
| Tracked-path hygiene hits | 61 | 61 | Bar not met; outside docs-only authority |
| Unframed RETRACTED figures | 1 | 1 | Bar not met; occurrence is in Python |
| Top-level index gaps | 12 | 0 | Bar met |
| **Metric total** | **418** | **405** | **NOT VALIDATED** |

The metric is additive and exhaustive over the stated constructs. No failing row was excluded.

## (a) Relative Markdown links

| Entry point | Before links | Before broken | After links | After broken |
|---|---:|---:|---:|---:|
| `README.md` | 64 | 0 | 64 | 0 |
| `docs/INDEX.md` | 160 | 0 | 172 | 0 |
| `docs/PUBLIC_EVIDENCE.md` | 23 | 0 | 23 | 0 |
| `docs/JOB_EVIDENCE_PACKET.md` | 4 | 0 | 4 | 0 |
| `docs/INTELLIGENCE.md` | 19 | 0 | 19 | 0 |
| `docs/PLATFORM.md` | 17 | 0 | 17 | 0 |
| `CLAUDE.md` | 10 | 1 | 9 | 0 |
| `AGENTS.md` | 14 | 0 | 14 | 0 |
| **Total** | **311** | **1** | **322** | **0** |

The sole broken link was `CLAUDE.md` -> `.planning/NOW.md`. That target is documented as gitignored and was absent from HEAD. The repair keeps the local-path guidance as code text and removes the broken hyperlink.

## (b) Register and results-log citations

| Source | Citation occurrences | Unique tokens | Missing occurrences | Unique missing tokens |
|---|---:|---:|---:|---:|
| `docs/evidence/HARNESS_GAPS_2026-09-03.md` | 186 | 162 | 56 | 46 |
| `docs/evidence/RESULTS_LEDGER_SYSTEM.md` | 473 | 311 | 287 | 150 |
| **Combined, de-duplicated only where the same token overlaps** | **659** | **427** | **343** | **165** |

These source files were not changed, so the after counts equal the before counts. The complete unique missing-token list with every citing line follows in Appendix A.

## (c) Tracked-path hygiene

### Prohibited prefixes

| Prefix | Before | After |
|---|---:|---:|
| `data/` | 60 | 60 |
| `vault/` | 0 | 0 |
| `.planning/` | 0 | 0 |
| `docs/research/` | 1 | 1 |
| `docs/strategy/` | 0 | 0 |
| **Total** | **61** | **61** |

The one tracked research path is `docs/research/validation-methodology.md`. The 60 `data/` paths consist of public README/package files, JSON reference data, and model-metric JSON files. The fixed S159 scope says not to move any `data/` file, so none was removed.

### Secret-pattern classification

| Pattern | Files with literal substring | Credential-shaped candidates | Verified secret hits |
|---|---:|---:|---:|
| the OpenAI-style key prefix | 191 | 1 fake test fixture | 0 |
| `AKIA` | 4 | 0 | 0 |
| `ghp_` | 3 | 0 | 0 |
| `gho_` | 1 | 0 | 0 |
| `api_key=` | 12 | 0 literal values | 0 |
| `token=` | 26 | 5 identifier placeholders | 0 |
| tracked environment files with values | 2 example templates, 14 non-secret defaults | 0 real environment files | 0 |

The key-prefix raw count is dominated by ordinary substrings such as `risk-` and `task-`. The one credential-shaped value is the deliberately fake `<fake fixture value, redacted: key-shaped string>` fixture in `tests/platformkit/showcase/test_lint_bundle.py`. The `token=` candidates bind names such as `_valid_token`; they are not credentials. The two tracked environment files are `.env.example` and `webapp/.env.local.example`; neither is a live environment file and neither contains a credential. Verified secret count is zero before and after.

## (d) RETRACTED-figure classification

The exact-token grep produced 501 occurrences. Every occurrence was classified:

| RETRACTED token | Raw occurrences |
|---|---:|
| RETRACTED `+18.38%` | 106 |
| RETRACTED `0.119` | 103 |
| RETRACTED `+54%` | 67 |
| RETRACTED `78.11` | 83 |
| RETRACTED `8.94` | 70 |
| RETRACTED `54.57` | 72 |
| **Total** | **501** |

Classification totals are 485 explicit RETRACTED/guard contexts, 15 unrelated numeric collisions, and 1 unframed RETRACTED occurrence. The 15 collisions are:

- `scripts/build_cv_coverage_gates.py:74` (`0.119`, sigmoid value)
- `scripts/build_intel_pdf_premium.py:363` (`0.119`, event probability)
- `scripts/build_intel_pdf_v3.py:1211` (`0.119`, event probability)
- `scripts/build_position_scheme_matrix.py:100` (`-0.119`, descriptive coefficient)
- `scripts/platformkit/analytics_showcase/out/atlas_tennis_manifest.json:320` (`0.119`, descriptive statistic)
- `scripts/platformkit/analytics_showcase/out/ctx_lineup_proxy.json:1969,5649` (`0.119` and `-0.119`, descriptive statistics)
- `scripts/validate_cv_coverage_gate.py:316` (`0.119`, numerical floor)
- `webapp/public/data/showcase/atlas_tennis_manifest.json:320` (`0.119`, descriptive statistic)
- `webapp/public/data/showcase/ctx_lineup_proxy.json:1969,5649` (`0.119` and `-0.119`, descriptive statistics)
- `docs/evidence/tracking/g46_court_scale_premise_2026-09-02.md:251,274,284,296` (`78.11`, measured tennis court coordinates)

The sole unframed RETRACTED occurrence is `api/courtvision_router.py:1384`, whose docstring calls `+18.38%` a walk-forward result without retraction framing. S159 forbids code edits, so it is reported and preserved. No documentation occurrence required reframing.

## (e) Top-level docs index

Before: 65 listed / 77 present, with 12 gaps. After: 77 listed / 77 present, with 0 gaps.

The added entries are `AI_CONSUMER_CONTRACT.md`, `ANALYTICS_CONTRACT.md`, `INDEX.md`, `IN_GAME_SHOWCASE.md`, `MCP_SERVER.md`, `README.md`, `ROADMAP.md`, `START_HERE.md`, `USE_WITH_CLAUDE.md`, `experiments.md`, `improvements.md`, and `repository_structure.md`.

## (f) README numerical reconciliation

The directly comparable opening/funnel claim occurrences were checked against `docs/JOB_EVIDENCE_PACKET.md`. The player-prop values and 20,354-row denominator, win-probability values, in-game conditioning values, six-corpus market comparison, and 0-of-60 signal result already matched. Two README intelligence-corpus references said approximately 100 files while the packet's canonical count is 151. Both were changed to 151 without changing the packet.

Two other funnel-block counts are NOT VERIFIED against the packet: `5 sports` and `44 atlases`. The packet does not state matching ingest-sport or atlas totals, so S159 neither invented replacements nor changed them.

## Focused test

Command:

```text
python -m pytest scripts/platformkit/ops/test_public_repo_links.py -q
```

Result: `1 passed in 2.28s`. The test is skip-free and walks all 322 post-change relative-link occurrences in the eight fixed entry points against `git ls-files`.

## Verifier self-check: B and Q

| Rule | S159 self-check |
|---|---|
| B1 | Additive counts include every enumerated occurrence; no failing set was removed. |
| B2 | No schema, status, or field changed. |
| B3 | Missing citations remain visible in Appendix A; absence is not called a pass. |
| B4 | No claim/retry path exists in this documentation construct. |
| B5 | No deployment or remote contact occurred. |
| B6 | No module moved or retired. |
| B7 | Not applicable; this is exhaustive reproduction, not a head slice. |
| B8 | No fit or residual was computed. |
| B9 | Denominators are exhaustive citation/link/file occurrences, not recycled units. |
| B10 | No bar or threshold moved. |
| Q1-Q2 | Not applicable: no scored trial and no charge. |
| Q3 | The acceptance bar is unchanged; the honest verdict is NOT VALIDATED. |
| Q4-Q5 | Not applicable: no out-of-sample comparison or AHEAD verdict. |
| Q6 | Calibration language only; every RETRACTED figure printed here is explicitly labelled RETRACTED. |
| Q7 | Counts are CONSTRUCT enumerations; every case is included. |
| Q8 | All six premises were measured first on untouched HEAD. |
| Q9 | Not applicable: no scored differential. |

## NOT VERIFIED

- 343 missing citation occurrences (165 unique tokens) do not exist in the tracked public HEAD; they are listed below and were not fabricated.
- 61 prohibited-prefix paths remain tracked because removing or moving them is outside the docs-only lane and conflicts with the S159 must-not-move rule for `data/`.
- The unframed RETRACTED figure in `api/courtvision_router.py:1384` remains because code edits are forbidden.
- External URLs, Markdown anchors, and link-target content were not tested; S159 enumerates relative target existence only.
- Git history was not scanned; the measured boundary is worktree HEAD.
- The README funnel counts `5 sports` and `44 atlases` have no directly matching packet totals.
- No push, deployment, feature-flag change, or private artifact write occurred.

## Appendix A: missing citation tokens

### Private or local-only paths

- `.claude/rules/data-vault-nocommit.md` -- H:69
- `.claude/rules/no-edge-claims.md` -- L:45, L:123; rule-path citation, not a claim
- `.claude/settings.local.json` -- H:69, L:6
- `.claude/skills/{tracking-lane,harness-lane}/SKILL.md` -- L:6
- `Users/neelj/nba-ai-system/data/frontend/clv_ledger.jsonl` -- L:35
- `data/*.parquet` -- L:184
- `data/ab_reports/foundry_runner.heartbeat.json` -- L:196
- `data/backups/eval_gate/` -- L:28
- `data/cache/analytics_verify/harness_health.json` -- L:21
- `data/cache/combo/gate_corpus_*.parquet` -- L:184
- `data/cache/combo/gate_corpus_mlb.parquet` -- H:88, L:44
- `data/cache/combo/gate_corpus_soccer.parquet` -- H:43
- `data/cache/combo/gate_corpus_tennis.parquet` -- H:44
- `data/cache/daemon_heartbeats/m1_paper.txt` -- L:142
- `data/cache/eval_gate/` -- H:70
- `data/cache/eval_gate/backtest_fwer.jsonl` -- H:54, H:70, H:265, H:295, L:12, L:35, L:41, L:44, L:49, L:67, L:74, L:78, L:82, L:108, L:117, L:119, L:127, L:134, L:136, L:185, L:225, L:231, L:322, L:328, L:331, L:332, L:362
- `data/cache/eval_gate/combo_fwer.json` -- L:272
- `data/cache/eval_gate/hedge_trial_2026-09-01.json` -- L:199
- `data/cache/eval_gate/hypotheses.sqlite` -- H:56, L:74, L:196
- `data/cache/eval_gate/hypotheses_s16hour_2026-09-03.sqlite` -- L:219
- `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` -- L:257
- `data/cache/eval_gate/s102_nba_sweep_top10_series.parquet` -- L:266
- `data/cache/eval_gate/s106_requote_2026-09-03.json` -- L:268
- `data/cache/eval_gate/s115_ingame_models_2026-09-03.csv` -- L:289
- `data/cache/eval_gate/s116_pooled_ingame_2026-09-03.csv` -- H:258, L:345, L:363
- `data/cache/eval_gate/s119_real_game_series_2026-09-03.csv` -- L:301
- `data/cache/eval_gate/s121_requote_2026-09-03.json` -- L:312
- `data/cache/eval_gate/s137_rebaseline_2026-09-03.json` -- H:239, L:339
- `data/cache/eval_gate/s148_live_requote_2026-09-03.json` -- L:354
- `data/cache/eval_gate/s58_trial1_e2_slice_2026-09-03.json` -- L:173
- `data/cache/eval_gate/s58_trial2_nba_halftime_2026-09-03.json` -- L:174
- `data/cache/eval_gate/s80_player_grain_2026-09-03.csv` -- L:230
- `data/cache/eval_gate/s81_soccer_2026-09-03.csv` -- L:278
- `data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv` -- L:235, L:312
- `data/cache/eval_gate/s84_nba_lineup_2026-09-03.csv` -- L:233
- `data/cache/eval_gate/s93_mlb_every_tick_premise_2026-09-03.json` -- L:243
- `data/cache/eval_gate/s94_nba_early_shrinkage_2026-09-03.json` -- L:245
- `data/cache/eval_gate/s96_nba_overreaction_2026-09-03.json` -- L:252
- `data/cache/eval_gate/s98_nba_better_prior_2026-09-03.json` -- L:255
- `data/cache/eval_gate/s99_cross_market_2026-09-03.json` -- L:259
- `data/cache/eval_gate/s99_game_keys.parquet` -- H:181, L:259
- `data/cache/ingame_books/mlb/2026-09-02.jsonl` -- L:91, L:112, L:267
- `data/cache/ingame_grade/*/*.jsonl` -- H:75
- `data/cache/ingame_grade/mlb/*.jsonl` -- L:240
- `data/cache/ingame_grade/mlb/KXMLBGAME-26JUL061915NYMATL.jsonl` -- L:268
- `data/cache/inplay_odds/mlb_price_series.parquet` -- L:114, L:243, L:278
- `data/cache/inplay_odds/nba_checkpoints_full.parquet` -- H:160, L:174, L:236, L:322
- `data/cache/mcp_server/artifact_refresh_heartbeat.jsonl` -- L:196
- `data/cache/pit/*.parquet` -- H:147
- `data/cache/settled_bets.json` -- L:240
- `data/domains/basketball_nba/games.parquet` -- L:236
- `data/domains/mlb/asof_espn_box.parquet` -- L:272
- `data/domains/mlb/close_history.parquet` -- L:143
- `data/domains/mlb/espn_boxscores.parquet` -- H:166, L:232, L:240
- `data/domains/mlb/games.parquet` -- L:127
- `data/domains/mlb/games_current.parquet` -- L:44
- `data/domains/soccer/asof_event_features.parquet` -- L:189
- `data/domains/soccer/asof_xg_proxy.parquet` -- H:108, L:134
- `data/domains/soccer/matches.parquet` -- L:331
- `data/domains/soccer/odds.parquet` -- L:17, L:278
- `data/domains/soccer_intl/results.parquet` -- L:134
- `data/domains/tennis/odds.parquet` -- L:78, L:148
- `data/frontend/analytics/execution_status.json` -- H:61, L:35, L:216
- `data/frontend/analytics/harness_health.json` -- L:21, L:121
- `data/frontend/clv_ledger.jsonl` -- L:240
- `data/frontend/grade_summary.json` -- L:126
- `data/frontend/ops/forward_evidence_scoreboard.json` -- L:41
- `data/registry/` -- L:185
- `data/registry/signal_registry.parquet` -- L:140
- `docs/research/organization-sprint/MASTER_ROADMAP_2026-09-03.md` -- H:19
- `docs/research/organization-sprint/PROPOSED-S120-job-evidence-signals.md` -- H:216, L:307
- `docs/research/organization-sprint/PROPOSED-S134-ledger-alias-transitive.md` -- L:316
- `docs/research/organization-sprint/PROPOSED-S89-next-k-family-alias.md` -- L:238

### Templates, globs, or abbreviated paths with no tracked match

- `*_trial_*.json` -- L:28
- `..._2026-09-03.json` -- L:231
- `..._embargo0.csv` -- L:230, L:233
- `_*_profiles.parquet` -- L:96
- `_2026-09-03.csv` -- L:272
- `_close.parquet` -- H:204, L:282
- `_fullmodel.csv` -- L:282
- `_mlb_series.csv` -- L:259
- `_reliability_2026-09-03.json` -- H:134, L:216
- `_screens.csv` -- L:303, L:335
- `_series.csv` -- L:303, L:335
- `_soccer_intl_series.csv` -- L:259
- `_ticks.csv` -- L:257
- `asof_*.parquet` -- H:147, H:197, L:272
- `statcast/savant_full__*.parquet` -- L:243
- `wp_diagnostics_*.json` -- L:83

### Named artifacts with no tracked public match

- `.bot_state/live_status.json` -- L:71
- `2026-09-01.jsonl` -- L:112
- `E4_PROMOTION_RESULT_2026-09-01.md` -- H:42
- `PROPOSED-S134-ledger-alias-transitive.md` -- H:234
- `asof_espn_box.parquet` -- L:240
- `asof_park.parquet` -- L:64
- `asof_player_adv.parquet` -- H:168
- `asof_quarter_shape.parquet` -- L:285
- `asof_xg_proxy.parquet` -- H:108, L:134
- `auth.json` -- L:6, L:9
- `backtest_fwer.jsonl` -- H:70, L:9, L:17, L:21, L:24, L:28, L:32, L:57, L:60, L:64, L:71, L:83, L:84, L:94, L:104, L:108, L:122, L:145, L:179, L:189, L:198, L:207, L:213, L:219, L:230, L:232, L:233, L:234, L:235, L:236, L:238, L:240, L:242, L:245, L:247, L:248, L:249, L:252, L:255, L:257, L:258, L:259, L:264, L:266, L:267, L:268, L:272, L:275, L:278, L:282, L:285, L:289, L:292, L:294, L:298, L:301, L:303, L:306, L:312, L:314, L:316, L:317, L:326, L:335, L:337, L:339, L:345, L:346, L:348, L:351, L:354, L:357, L:363
- `bullpen_relief_chains.parquet` -- L:301
- `calibration_grid/nba_reliability_map.json` -- L:236
- `docs/evidence/CONNECTIVITY_2026-09-04.md` -- H:301
- `e4_promotion_trial_2026-09-01.json` -- L:28, L:84, L:122
- `espn_nba_game_bridge.parquet` -- L:233
- `execution_status.json` -- L:307
- `games_current.parquet` -- H:51, L:64, L:114, L:240, L:258, L:259
- `gate_corpus_mlb.parquet` -- L:114
- `gate_corpus_nba.parquet` -- L:89
- `gate_corpus_soccer.parquet` -- L:9, L:117
- `gate_corpus_tennis.parquet` -- L:117
- `gate_manifest.json` -- H:70, H:114, L:28, L:122
- `hedge_trial_2026-09-01.json` -- L:28, L:84, L:122
- `hypotheses.sqlite` -- H:70, L:28, L:136
- `hypotheses_s16hour_2026-09-03.sqlite` -- H:57
- `ingame_eval_cache.parquet` -- H:156, L:230, L:233
- `latest.json` -- L:169
- `linescores_2024_25.parquet` -- H:202, L:275
- `lineup_signatures.json` -- L:222
- `mlb_clean/` -- L:24
- `mlb_price_series.parquet` -- H:151
- `mlb_profile_claims.jsonl` -- L:100
- `models/` -- H:100
- `nba_checkpoints_full.parquet` -- H:156, L:233, L:245, L:266, L:278, L:354
- `nba_close_corpus.parquet` -- H:204, L:278, L:282, L:322
- `nba_player_box_rate.jsonl` -- L:100
- `nba_price_series.parquet` -- L:278
- `openapi.json` -- H:100, L:91, L:129
- `player_gamelogs.parquet` -- L:230
- `pnl_ledger.csv` -- L:240
- `postmortem.parquet` -- L:134, L:301
- `probables.parquet` -- H:214, L:275, L:301
- `quarter_signatures.json` -- L:222
- `referee_card_foul_profiles.parquet` -- L:134
- `s06_stacker_trial_2026-09-03.json` -- L:84
- `s102_nba_sweep.sqlite` -- L:335
- `s106_requote_s131corrected_2026-09-03.json` -- L:345
- `s108_pregame_full_model_2026-09-03.json` -- L:272
- `s116_pooled_ingame_2026-09-03.csv` -- H:227, H:247, L:339
- `s119_real_game_requote_2026-09-03.json` -- L:301
- `s121_requote_s131corrected_2026-09-03.json` -- L:345
- `s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv` -- L:345
- `s81_mlb_2026-09-03.csv` -- L:278
- `s82_ingame_screen_2026-09-03.json` -- L:235
- `s85_refused_families_2026-09-03.json` -- L:275
- `s85_screen_2026-09-03.sqlite` -- L:275
- `s87_requote_2026-09-03.json` -- L:234, L:345
- `s87_requote_2026-09-03_premise.json` -- L:234
- `schedule_density.parquet` -- H:220, H:237, L:317
- `schedule_density_wta.parquet` -- L:317
- `scripts/platformkit/analytics_showcase/out/harness_health.json` -- L:21
- `signal_registry.parquet` -- H:113, L:198
- `soccer_intl/` -- L:24
- `soccer_intl/results.parquet` -- H:108
- `style_fingerprints.parquet` -- L:134
- `tick_segment_backfill.json` -- L:264
- `tipoff_predictability_signals.json` -- L:222
- `tmp/s60_mods.txt` -- L:160
- `tracking_data.csv` -- L:222
- `travel_scouting.parquet` -- H:220, H:237, L:317
- `travel_scouting_wta.parquet` -- L:317
- `vegas_odds.csv` -- L:143
- `venue_history/nba_close_corpus.parquet` -- L:278
- `wta/_raw_td/` -- L:148
- `wta_matches.parquet` -- H:158, H:202, H:220, L:148, L:275, L:285, L:317

Appendix total: 165 unique missing tokens covering 343 missing source-line occurrences.
