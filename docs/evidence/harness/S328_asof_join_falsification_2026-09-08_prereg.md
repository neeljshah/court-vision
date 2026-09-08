# S328 external as-of replay preregistration

Row: S328. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

This preregistration is sealed before any scored comparison. The preparation lane does not open the
checkpoint parquet, run a replay, fit a model, or compute a calibration metric.

State list: `docs/evidence/harness/S320_timestamp_artifact_audit_2026-09-08b/states.csv`, sealed S320
attempt-2 selection, 313 states across 63 non-empty strata. The finisher must record its input byte size
and SHA-256 before opening it, and must use one evaluator state for every sealed tick (never one state per
game standing in for its ticks).

Arms: the landed S310/S309 grouped-CPCV recalibrated null identity and, when landed, the S321 attempt-2
candidate; otherwise the S320 substitute callback, labelled `S320_SUBSTITUTE`. Delays are exactly 0, 30,
60, and 120 seconds. The external frame for each state contains only source rows with
`ts <= state_ts - delay`; a separate prefix-deletion call supplies the same bounded frame to every arm.

Access rule: each predictor receives only the external frame. The replay installs a recording loader for
the source; any predictor read outside that frame is an access violation. A planted future row must be
absent from the joined frame, and every nonzero delay change must identify at least one record in that
delay window.

Terminal rule: exclude `period >= 4 and game_clock_s == 0` by the S309 mask and report the excluded n.
Bar: zero prediction changes under prefix deletion for every arm; zero reads outside an allowed frame; all
nonzero delay changes traced; focused tests pass; no landed files are edited. A violation blocks later S321
scoring until corrected.

If outcomes are present, a finisher may report descriptive Brier and log-score differences through the
shared evaluator with purge plus a symmetric nonzero embargo and paired game-cluster bootstrap (2,000).
Sign convention: improvement = baseline loss minus candidate loss; positive = candidate better. This row
establishes no gain.

SEAL sha256 fcfe9d6b134781fdc8958fd55b69f738b05fe587b3dc15f676d051d476b5878b
