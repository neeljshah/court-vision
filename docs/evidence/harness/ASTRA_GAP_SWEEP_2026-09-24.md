# Astra gap-sweep critique -- 2026-09-24 20:09Z (codex gpt-6-astra, read-only, main tree ca49495be)

Orchestrator note: the ranking and the missed gaps below were adjudicated the same hour (register rows S437-S446). Calibration language only; this is a design critique, not a measurement.

RANKING: S438 > S440 > S439 > S442 > S441 > S437

1. **S438, rank 1: right next row; broaden the handoff slightly.** Kalshi rereads a fixed path, while Polymarket loads its selection only at startup. Both need the same dated handoff contract. [capture_schedule_loader.py:20](scripts/platformkit/ingame/capture_schedule_loader.py:20), [polymarket_live_capture.py:227](scripts/platformkit/ingame/polymarket_live_capture.py:227).
   Keep this small: atomic selection, observed digest, and a midnight test preserving ongoing games. A pointer alone does not refresh Polymarket's cached selection. [polymarket_live_capture.py:227](scripts/platformkit/ingame/polymarket_live_capture.py:227).

2. **S440, rank 2: necessary, but its capture premise is only partly established.** Raw market metadata is retained; discovery requests open events, so eventual settlement receipts are not assured by that mechanism. [local_capture_runner_row.py:63](scripts/platformkit/ingame/local_capture_runner_row.py:63), [local_capture_runner.py:149](scripts/platformkit/ingame/local_capture_runner.py:149).
   Include bounded post-final witnessing, outcome orientation, cancellations and explicit unresolved cases. Separate outcome-score completeness from markout completeness: the latter grades subsequent observations, not the final result. [GO_LIVE_GATES.md:21](docs/GO_LIVE_GATES.md:21).

3. **S439, rank 3: right measurement, underspecified authority.** The four-arm machinery already supplies raw mid A, calibrated-mid B, and mid-plus-state C; reuse it and compare identical supported ticks. [baseline_four_arm.py:105](scripts/platformkit/ingame/baseline_four_arm.py:105).
   Cut exploratory segment proliferation. Freeze segments, information-time rules and model versions before scoring; ?report only, nothing sealed? cannot support scored conclusions under Q1. Preserve paired losses under Q9. [VERIFIER_CONTRACT.md:34](docs/evidence/tracking/VERIFIER_CONTRACT.md:34), [VERIFIER_CONTRACT.md:64](docs/evidence/tracking/VERIFIER_CONTRACT.md:64).

4. **S442, rank 4: useful preparation; not a new-client problem.** An existing client already subscribes to orderbook deltas, writes raw messages, and exits on socket closure. [stream_kalshi.py:61](scripts/stream_kalshi.py:61), [stream_kalshi.py:78](scripts/stream_kalshi.py:78).
   Narrow the row to canonical reconstruction, sequence-gap refusal, reconnect snapshots and trade deduplication. Replace ?socket rows are a superset? with reconstructed-book agreement plus accounted missing intervals; deltas and REST snapshots are different record types. [S442 definition:585](docs/evidence/HARNESS_GAPS_2026-09-03.md:585).

5. **S441, rank 5: premature at one-second resolution.** The documented Polymarket live cadence is ten seconds, and pairing permits five-second receipt skew; one-second bins do not establish one-second ordering. [S436_spec.md:13](docs/evidence/tracking/specs/S436_spec.md:13), [S436_spec.md:17](docs/evidence/tracking/specs/S436_spec.md:17).
   Merge the first pass into S431/S435: bound each move between observations and label overlapping intervals unresolved. Defer finer ordering until measured cadence supports it. [S431/S435 definitions:574](docs/evidence/HARNESS_GAPS_2026-09-03.md:574), [S435:578](docs/evidence/HARNESS_GAPS_2026-09-03.md:578).

6. **S437, rank 6: reject the transport premise.** The NFL poller already preserves adapter fields other than named metadata in `state`; down, distance and timeouts are not discarded there. [local_state_capture_sources.py:262](scripts/platformkit/ingame/local_state_capture_sources.py:262), [local_state_capture_sources.py:290](scripts/platformkit/ingame/local_state_capture_sources.py:290).
   Replace the sibling-block build with S413 completeness verification. Field-position semantics remain genuinely unresolved: the adapter deliberately emits `yardline_100=None`. [ingest_nfl_states.py:213](domains/nfl/ingest_nfl_states.py:213).

7. **Missed gap: weekly fill accounting and markout production.** The week producer hardcodes empty fill-bearing identities and zero fills; the renderer merely consumes separately supplied summaries. [forward_week_report.py:179](scripts/platformkit/ops/forward_week_report.py:179), [weekly_record.py:137](scripts/platformkit/execution/weekly_record.py:137).
   Smallest experiment: one completed synthetic week containing qualified fills, excluded fills, duplicates and missing marks, passed through the complete chain twice.
   Accept exact identity reconciliation, independently reproduced clustered summaries and unchanged second-run output; reject zero placeholders, duplicate counting or unexplained exclusions.

8. **Missed gap: attested licence integration and the first countable week.** Licence digests are declarations, commit time is caller-supplied, and sizing requires eight qualifying weeks before checking seal timing. [microstructure_licence_inputs.py:107](scripts/platformkit/execution/microstructure_licence_inputs.py:107), [microstructure_licence.py:150](scripts/platformkit/execution/microstructure_licence.py:150).
   Smallest experiment: resolve actual committed seals through one decision receipt using 0/7/8-week fixtures, altered artifacts and seals immediately before/after the first Monday.
   Accept authenticated provenance and the existing refusals; explicitly distinguish qualification weeks from licensed quoting weeks. Reject counting pre-seal weeks or treating a well-formed digest as authenticated evidence.

9. **Missed gap: a continuous paper decision history shared across contracts.** S411 creates an empty reservation history for each prepared snapshot; it measures fill sensitivity, not a continuous constrained account. Same-game caps already exist. [fill_realism.py:91](scripts/platformkit/execution/fill_realism.py:91), [position_caps.py:50](scripts/platformkit/execution/position_caps.py:50).
   Smallest experiment: replay simultaneous same-game contracts, partial fills, cancellation expiry and restart through one reservation history.
   Accept identical uninterrupted/restarted decisions, no duplicated fills and no breached declared cap; reject isolated snapshot allowances masquerading as shared exposure. Extend integration, not the cap implementation.

10. **Missed gap: observation support through late play and markout horizons.** Focus ends one hour after scheduled start; the recorded regime census explicitly cannot measure late-game regimes under that profile. [capture_scheduler.py:123](scripts/platformkit/ingame/capture_scheduler.py:123), [RESULTS_LEDGER_SYSTEM.md:750](docs/evidence/RESULTS_LEDGER_SYSTEM.md:750).
    Smallest experiment: a separately declared full-game capture census through terminal state and the final required markout window, retaining every scheduled game.
    Accept complete phase/horizon denominators with explicit missingness; reject all-phase conclusions where phases are unobserved. Preserve the existing qualification thresholds.

11. **Missed gap: forward validation of the market-conditioned residual per sport.** B/C already implement the core comparison; the lagged-mid control is currently NBA-only. Building another generic residual model would duplicate machinery. [baseline_four_arm.py:107](scripts/platformkit/ingame/baseline_four_arm.py:107), [baseline_four_arm.py:122](scripts/platformkit/ingame/baseline_four_arm.py:122).
    Smallest experiment: fold into S439 one sealed, game-separated C-minus-B comparison per sport, with matching receipt-time support and a lagged-mid control.
    Accept a calibration conclusion only under the unchanged chronology, interval and independent-corpus requirements; otherwise publish BEHIND or INSUFFICIENT. [VERIFIER_CONTRACT.md:36](docs/evidence/tracking/VERIFIER_CONTRACT.md:36).

12. **Other candidates:** retain queue/TTL sensitivity, but reject calling it calibrated fill probability without independent fill labels: S411 explicitly lacks observation of its own queue position. State-change markout classes already exist; enrich them within S435 after linkage works. [S411 memo:295](docs/evidence/harness/S411_fill_realism_2026-09-22.md:295), [fill_realism_markout.py:62](scripts/platformkit/execution/fill_realism_markout.py:62).
    Independent settlement belongs in S440; NFL/NBA completeness belongs in the existing verification work. NBA enrichment paths remain recorded as unsourced pending a real census. [RESULTS_LEDGER_SYSTEM.md:754](docs/evidence/RESULTS_LEDGER_SYSTEM.md:754).

13. **NOT VERIFIED:** I performed source/document inspection only: no writes, tests, imports, network calls or reads under `data/`. I could not verify live capture health, tonight's execution, actual fills, settlement coverage or current seal artifacts. The durable page records zero completed weeks; the night memo records no real-night verification. [WEEKLY_RECORD.md:3](docs/evidence/forward/WEEKLY_RECORD.md:3), [S427 memo:242](docs/evidence/harness/S427_paper_night_2026-09-24.md:242).
    These gates establish a market-relative paper proof path, not a comparison against named quant teams; that broader objective remains unverified. [GO_LIVE_GATES.md:19](docs/GO_LIVE_GATES.md:19).