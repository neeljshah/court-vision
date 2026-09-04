# S211 Attempt 2 In-Game Headline Re-Derivation Preregistration

Scope: re-measure the existing NBA and MLB in-game calibration headlines without
changing either proof harness, any arm, builder, threshold, corpus, evidence
page, register, or ledger. This is a calibration measurement, not a model or
deployment claim.

Predeclared arms, scored for every retained game path:

- static: pregame prior;
- score_only: neutral-prior state; and
- conditional: pregame prior plus state.

Predeclared OOS fold scheme: the shared
`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` uses eight
timestamp groups with two test groups per CPCV split. Its symmetric, nonzero
calendar embargo is one day on both sides of every scored row. It additionally
uses the shared 48-hour same-team purge and symmetric three-day same-matchup
protection. The evaluator asserts that no retained training row is blocked by
the symmetric purge or embargo window of a scored row.

Frozen acceptance bar, byte-for-byte from `S211_spec.md`: both sports
re-derived (or NOT REPRODUCIBLE with the reason), every published figure either
reproduced at max abs diff <= 1e-6 or reported NOT REPRODUCED with its honest
value, the prior share carrying a CI, and a per-game differential archived for
all three arms. A CI covering zero is the expected valid result, published as a
retraction

Verdict rule: the frozen bar is not moved. A result that is NULL, BEHIND, NOT
REPRODUCED, or NOT VERIFIED is a valid completed measurement and is reported
with its calibration values and archived differential. No AHEAD claim is
possible in this attempt.

No charged trial is opened. K is unread; no ledger or register is read or
written. The fresh post-seal process may run the two unmodified proof routes
for route identity only, and it will score this attempt through the shared CPCV
evaluator. It will write only the named evidence artifacts in this worktree,
opening input stores serially and only below 300 MB.

Seal SHA-256 of the pre-seal text above: `E6CE4EEAEA909412EA52321E68B2F507295C05AC1576F6D16B1592CCCC9D913D`.
