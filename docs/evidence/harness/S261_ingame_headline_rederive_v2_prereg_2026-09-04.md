# S261 Attempt 1b In-Game Headline Re-Derivation v2 Preregistration

Scope: re-measure the existing NBA and MLB three-arm in-game calibration values
through the shared CPCV evaluator. This is a calibration measurement only. It
does not alter S211 artifacts, either proof harness, a corpus, a public page,
the register, the ledger, or any deployment target.

Premise measured before this preregistration: the committed S211 paired-loss
CSVs reproduce NBA static/score/conditional 0.218832500844/0.172353182740/
0.163246780662 on 1313 game paths and MLB 0.248972824104/0.128228347380/
0.127997559533 on 23279 game paths. The MLB source count is 2458
invalid-inning rows plus 2246 tied-final-score rows; S211 drops both before
scoring and does not name them in its memo.

Predeclared arms, scored inside one callback for every admitted CPCV state:

- static: train-only pregame team-rate prior;
- score_only: neutral-prior state repricing; and
- conditional: train-only pregame prior plus state repricing.

The frozen OOS design is `cpcv_evaluate` with eight timestamp groups, two test
groups, one-day symmetric calendar embargo, 48-hour same-team purge, and
three-day symmetric same-matchup protection. The callback computes every
scored arm. No row outside the callback supplies a score. The evaluator's
strict redaction is enabled. Bootstrap seed is 21120260904 with 10000 game
cluster resamples.

Outputs use only new S261 filenames. The summary preserves the v1 names and
meanings as additive aliases: `checkpoint_count` is the raw number of scored
checkpoints, `finite_resamples` is the number of finite bootstrap draws, and
`reproduction_abs_diff` is the per-arm absolute difference from the public
value. The paired-loss CSV retains per-game static, score, and conditional
losses, cluster id, timestamp, and split identifiers. The denominator note
will name the invalid-inning and tied-row MLB exclusions with their counts.

Frozen public values are NBA 0.209/0.159 and MLB 0.241/0.126. The bar is max
absolute difference <= 1e-6. The exact static differences to print are
0.00983250084408843 for NBA and 0.00797282410431543 for MLB; the exact
conditional differences to print are 0.00424678066236500 for NBA and
0.00199755953257377 for MLB. Any arm above the frozen bar is labelled NOT
REPRODUCED. A CI covering zero is reported without changing that label.

No charged trial is opened. K is unread; no ledger or register is read or
written. The run is local because it is a reproducibility measurement; no file
will be copied to a pod before ACCEPT. If a scorer requires more than 800 MB,
only sample-scale local work may occur before ACCEPT and the full run is
deferred to a successor.

Seal SHA-256 of the LF pre-seal bytes above: `B18A747EA3E602AA56CA1DE23C4C5142874B8062D206104BEAFEA3E31C9C223A`.
