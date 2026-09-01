# Preregistration: baseball framing teacher

Registered 2026-09-01 before a joined teacher-label corpus exists.

Target: P(called_strike | pitch taken), using taken pitches with a binary
called-strike label. Evaluation is date-walk-forward held-out Brier score and
log-loss on independent 2023 and 2024 corpora, both directions required.

Baseline: shrunk prior-only catcher and pitcher fixed effects, plus handedness,
count, location, strike-zone bounds, and an in-zone predicate. Catcher effects
use only earlier catcher pitches. A feature that only recovers catcher identity
must lose to this baseline.

Candidate columns are `command_target_dev_x_ft` and
`command_target_height_ft`. The `command_*` prefix intentionally classifies
them as TRAINING_ONLY, excluding them from live inference.

With K=2, the per-test threshold is 0.025 and both corpora are required. The
candidate needs lower held-out Brier in both corpora, clustered testing by
catcher below that threshold in both directions, planted-null rejection, and a
skillful baseline. A one-corpus or one-direction result is insufficient.

Pre-declared blockers: no joined teacher-label data currently exists; each
corpus needs at least 400 confident-target taken pitches from two broadcasts.
The teacher-to-label game identity join is also required. This document
registers the test and reports no result.
