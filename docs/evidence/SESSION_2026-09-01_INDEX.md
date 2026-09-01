# Session evidence index - 2026-09-01

This public-safe master index records validation outcomes and engineering
receipts from the organization pass. It is not a betting, ROI, or live-money
claim. Every cited path is tracked at this revision; commit subjects are exact
git-log receipts, with current-session work covered by `git log --oneline -70`.

## Tracking program

| Claim | Existing evidence path | Commit subject |
|---|---|---|
| Frozen sweep: 0 of 173 retained games passed; coordinate-contract rejection dominates and the tennis denominator is explicitly under audit. | `docs/evidence/tracking/harness_sweep_173_games_2026-09-01.md` | `8e245f417 evidence: frozen-harness sweep of all 173 pod games -- 0 pass, 97.7% die at the coordinate contract` |
| Soccer camera-coverage impossibility was falsified by a native-provenance 33-player frame. | `docs/evidence/tracking/soccer_s4_packet_2026-09-01.md` | `e4482b300 docs: record soccer S4 counterexample max 33` |
| The blanket baseball homography-impossibility statement was retracted and rescoped; the corpus is image-pixel-only. | `docs/evidence/tracking/baseball_s4_packet_2026-09-01.md` | `704abc3b1 evidence(baseball): retract blanket S4 homography claim` |
| Football line extraction was confounded by broadcast graphics; diagnostics now constrain line detection to field ROI. | `docs/evidence/tracking/confounder_findings_2026-09-01.md` | `9181a3284 football: constrain LSD to field ROI` |
| Football field-ROI work retained zero joint yard-and-numeral frames, so no scale, adapter, or harness claim was entered. | `docs/evidence/tracking/FOOTBALL_WAVE_6F_FIELD_ROI.md` | `9181a3284 football: constrain LSD to field ROI` |
| NFL hash-mark scale was tested as a rule-fixed physical constant and unresolved geometry remains fail-closed. | `domains/football/tracking/MEASUREMENT_WAVE_6C.md` | `6c46d366a fix(football): verify NFL hash scale` |
| Numeral-anchored football registration retained its denominators and rejected without sufficient correspondences. | `docs/evidence/tracking/FOOTBALL_WAVE_6G_NUMERAL_OCR.md` | `9d046a96d football: measure numeral anchored registration` |
| Football numeral-OCR read-rate sweep terminally failed the joint-numeral gate (best variant 55/444 crops read, 12.39%; 13/74 field frames vs a 30/74 requirement), so no correspondence solve, homography, or harness run was performed. | `docs/evidence/tracking/FOOTBALL_WAVE6H_OCR_REPORT.md` | `0f3febe9e measure football OCR gate on 1080p staging` |
| Tennis classical registration was exhausted against a held-out landmark; improved line detection is not a demonstrated coordinate solve. | `docs/evidence/tracking/tennis_resolution_controlled_2026-09-01.md` | `81fdf6216 evidence(tennis): line-correspondence H arm honestly rejected (704.8 ft median vs <2 ft gate) + wave-7 falsifier probes` |
| Tennis camera-lock (geometric-median lock, 5px drift ceiling) is merged and fail-closed; the one measured section recorded 0/725 fresh-solve accepts, so no lock formed and the mechanism is still untested against an accepting section. | `docs/evidence/tracking/tennis_camera_lock_nyYk_720p_2026-09-01.md` | `1d8a73c3f feat(tennis): add drift-checked camera locks` |
| The TrackNetV3 ball arm cleared its local ball-valid gate on the measured two-match sample; review overlays are retained. | `scripts/platformkit/tennis_tracknetv3_eval.py` | `dcfa59566 feat(tennis): TrackNetV3 ball detection zero-shot -- ball_valid 0.350 (n=80, 2 matches) vs 0.20 gate; MIT incl. checkpoints; overlays verified by eye` |
| Tennis now records decoded-frame completeness, preventing emitted-row coverage from standing in for decoded-frame coverage. | `domains/tennis/tracking/frame_manifest.py` | `2b20730f3 tennis: record decoded-frame manifest (before 1.00 emitted vs 0.42% decoded)` |
| Basketball pod rows were relabelled as image pixels rather than court coordinates; the funnel remains diagnostic-only. | `scripts/platformkit/basketball_relabel_image_px.py` | `b29369580 Relabel pod basketball tracking as image pixels` |
| Synthetic calibration is a testable development path; the tennis judge trace emitter exposes its decision trail. | `scripts/platformkit/synthcal/trace_emitter.py` | `6d52e243f add SynthCal tennis judge trace emitter` |
| Football demo media and review frames for all five sports were published; weak windows were withheld by review. | `docs/evidence/demo/README.md` | `bb3f9e618 evidence(demo): football tracking demo published + review frames for all five sports; weak-window clips held per orchestrator frame review` |

## Harness and evaluation hardening

| Claim | Existing evidence path | Commit subject |
|---|---|---|
| Predictors receive a redacted view; the leak contract preserves feature parity and raises a dedicated violation error. | `scripts/platformkit/eval_gate/schema.py` | `f801f6f47 harden(eval-gate): leak contract -- redacted predictor view + LeakError raises (survives -O) + datetime vintage + feature parity; legacy fixtures updated to the new contract` |
| Tracking liveness rejects vacuous singleton-track passes through an identity-length floor and named jump failures. | `scripts/platformkit/liveness_metrics.py` | `29759be84 harden(tracking-harness): identity floor min_median_track_len=3 + unmeasurable-jump named failure + UNCALIBRATED liveness -- additive stricter-only; kills the vacuous singleton-track pass` |
| Diebold-Mariano comparison fails closed on incompatible inputs and has no IID fallback. | `scripts/platformkit/eval_gate/dm_test.py` | `e64283034 harden(eval-gate): dm_test fails closed (length check, no iid fallback, t(G-1)) -- golden verdicts unchanged, p widened 0.0453->0.0533; fixtures upgraded to datetime availability; -O subprocess test pinned to repo root` |
| The in-game baseline is version-locked with a testable record rather than silently redefined. | `scripts/platformkit/ingame/ingame_baseline_lock.py` | `d9bf219fb Harden baseline lock: old delta -0.0343 raw n 268; new delta -0.03425595343964605 n_games 268 ess 907.1138311847325` |
| Null-ship calibration recorded 0 ships in 200 null runs; the post-hardening report is retained. | `scripts/platformkit/eval_gate/null_ship_calibration.py` | `41595092a test(eval-gate): record post-hardening null revalidation` |
| Romano-Wolf correction retained documented rejections and found zero survivors in the 85-item retro catalog. | `scripts/platformkit/eval_gate/retro_correction_report.txt` | `e0d079140 feat(eval-gate): Romano-Wolf stepdown multiplicity correction + retro catalog pass -- zero survivors at K=85, every documented REJECT preserved` |
| Frozen-odds backtesting has a ledger and composes with redacted inputs; close echoes stay in a labelled side table. | `scripts/platformkit/eval_gate/backtest_runner.py` | `fd1e785c0 fix(eval-gate): backtest runner composes with the leak-contract redaction -- feature parity in states, close-echo via labelled side table` |
| The frozen backtest ledger is an explicit evaluation artifact, not a performance headline. | `scripts/platformkit/eval_gate/reference_runs/fwer_backtest_ledger.jsonl` | `9e200cbef feat(eval-gate): add frozen odds backtest runner` |
| Combinatorial purged cross-validation records a PBO estimate as an overfitting diagnostic, never a profit claim. | `scripts/platformkit/cpcv.py` | `15f0d1c34 feat: 10-module parallel build (quant harness + per-sport tracking features) + portable cache paths` |

## Quant and paper-execution receipts

| Claim | Existing evidence path | Commit subject |
|---|---|---|
| Kalshi in-play capture records venue timestamps and freshness so event-reactive processing can be audited. | `scripts/platformkit/ingame/inplay_tick_latency.py` | `6ff50ea96 feat(ingame): venue-clock latency ledger -- src_ts passthrough, lag_p50/p90, state_age stamp, EVENT_REACTIVE gate` |
| The maker lifecycle is wired into the day-trader with maker-only tests; it remains paper execution. | `scripts/platformkit/execution/paper_maker.py` | `a1fb821c6 Wire paper maker lifecycle into day-trader` |
| MLB Kalshi book capture is a market-data receipt, not evidence of an edge. | `scripts/platformkit/ingame/mlb_book_capture.py` | `d60145a49 Add dense MLB Kalshi book capture` |
| In-game mechanism arms report insufficient evidence or rejection when corpus requirements are unmet. | `scripts/platformkit/ingame/arm_evaluation.py` | `93e6deedc Wire in-game arms: blend INSUFFICIENT, offset INSUFFICIENT, regime INSUFFICIENT` |
| The combination engine is proposal-only and rejects unless every scale-aware validation layer passes. | `scripts/platformkit/combo/combo_gate.py` | `0d6db3cfc feat: all-in-one live AI paper-trading front end + stable production serve` |
| The market-strength atlas corrected a rating-scale defect and is descriptive-only. | `scripts/platformkit/analytics_showcase/market_strength_atlas.py` | `04fc0af3f fix: correct strength atlas rating update scale` |
| The mechanism exposure sheet joins existing validated-ledger facts and introduces no new statistics. | `scripts/platformkit/analytics_showcase/mechanism_exposure.py` | `74d862270 feat(analytics): pregame mechanism exposure sheet -- relevance join over the 191-row validated ledger, no new statistics` |
| Adaptive conformal inference is wired into the live paper stream with a focused shim test. | `scripts/platformkit/ingame/aci_stream_shim.py` | `4ba5df47e Wire ACI into live paper stream` |
| The mechanism ladder is a captured, test-covered research surface; no mechanism result is promoted here. | `scripts/platformkit/ingame/nba_mechanism_ladder.py` | `93e6deedc Wire in-game arms: blend INSUFFICIENT, offset INSUFFICIENT, regime INSUFFICIENT` |
| Artifact-status tools make committed evidence inspectable through the MCP surface. | `scripts/platformkit/mcp_server/artifact_tools.py` | `329f33251 feat(mcp): add artifact status tools` |

The session records disciplined observability: coordinate-producing tracking is
not certified by the frozen harness, failure denominators are preserved, and
proposed fixes remain bounded by their gates. Evaluation and paper-execution
receipts likewise retain rejects, insufficient-data states, provenance, and
operational controls. Nothing here claims market edge, realized return, or
live-money execution.

---
<!-- nav-footer -->
**Navigate:** [Up: evidence hub](README.md) - [Doc map](../INDEX.md) - [Tracking status](../TRACKING.md)
