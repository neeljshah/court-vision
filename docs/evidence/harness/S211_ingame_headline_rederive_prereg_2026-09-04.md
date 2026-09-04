# S211 In-Game Headline Re-Derivation Preregistration

Scope: reproduce the existing NBA and MLB in-game calibration harnesses without
changing a harness, arm, builder, threshold, corpus, evidence page, register, or
ledger. This is a measurement of the published static-to-conditional Brier
headlines and their three-arm decomposition, not a new model comparison.

Predeclared routes and commands, run from `C:\Users\neelj\nba-track-a18`:

```
python -m scripts.platformkit.proof_nba.ingame_accuracy
python -m scripts.platformkit.proof_mlb.ingame_accuracy
python -m scripts.platformkit.s211_headline_rederive --output-dir docs/evidence/harness
```

Predeclared inputs, opened one store at a time and only when below 300 MB:

- NBA default route: `C:\Users\neelj\nba-ai-system\data\domains\basketball_nba\linescores.parquet`.
- MLB default route: `C:\Users\neelj\nba-ai-system\data\domains\mlb\games.parquet`, then `C:\Users\neelj\nba-ai-system\data\domains\mlb\pitchers.parquet`.

Predeclared series: one row per scored game path, retaining every game admitted
by the existing harness. Each row contains the cluster id, source timestamp,
checkpoint count, and sums and means of squared loss for static prior,
score-only, and conditional prior-plus-state arms. Aggregate Brier is each
loss sum divided by the total retained checkpoint count. The score-only share
is `(static - score_only) / (static - conditional)` and the model-prior share
is `(score_only - conditional) / (static - conditional)`. A deterministic
game-cluster bootstrap with 10,000 resamples reports the percentile 95 percent
interval for model-prior share and `n_eff` equal to the retained game-path
count. If fewer than 30 game paths are retained, the interval is not reported.

Predeclared acceptance bar: both sports re-derived (or NOT REPRODUCIBLE with the reason), every published figure either reproduced at max abs diff <= 1e-6 or reported NOT REPRODUCED with its honest value, the prior share carrying a CI, and a per-game differential archived for all three arms. A CI covering zero is the expected valid result, published as a retraction

No charged trial is opened: this reproduces existing fixed routes and does not
propose an AHEAD verdict. No ledger is read or written; K is unread.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
The result memo will identify the machine, code hashes, exact input paths,
bytes, and non-image resolution status.
Seal SHA-256 of the pre-seal content above: `E0E9D792034D39AF5A3662B1EC84EE61B873250C92654ED85BCCE0522F74A410`.
