# S296 preregistration correction: empty strict-prior fallback

This sealed correction is committed before any S296 scorer execution. It
supplements, without rewriting,
`docs/evidence/harness/S296_full_boxscore_oof_2026-09-04_prereg.md`, whose
premise, inputs, field set, CPCV design, metrics, `+0.004` bar, and
single-window calibration status remain unchanged.

For a test player-game with no strictly earlier player vector, the candidate
uses the named strict-prior league empirical fallback. On the earliest source
date, when the league prefix is also empty, both candidate and named
strict-prior league empirical baseline use the fixed all-zero vector point
mass. Those source rows remain scored and are never excluded; their
`cold_start_zero` status is archived in the re-emitted and paired tables. This
is an explicit empty-history convention, not a future-label read.

The full-vector scorer and its test are additive files under
`scripts/platformkit/` and `tests/platformkit/`. The generic evaluator still
uses five CPCV date blocks with the inherited purge and a symmetric nonzero
one-day embargo. Every output loss comes from its evaluator-emitted record.

SEAL_SHA256: 71fd96e13acfd97b3ed7832fa42cbb1ace32d5561865a15e98ceb79d6a9fbb22
