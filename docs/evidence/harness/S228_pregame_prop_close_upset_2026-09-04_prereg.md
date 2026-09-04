# S228 Pregame Prop Close Upset Preregistration

This uncharged, read-only calibration comparison follows
`docs/evidence/tracking/specs/S228_spec.md` and self-checks sections B and Q
of `docs/evidence/tracking/VERIFIER_CONTRACT.md`.  It is sealed before the
fresh scoring run.  It does not amend a register or ledger.

Seal timestamp: 2026-09-03T23:15:19-05:00

Route file: `scripts/platformkit/s228_pregame_prop_close_upset.py`

Route SHA-256: `be64d79055a2ed87b83a0eb43b5be8e36a326e515b3ce99e06bc673573219d70`

Inputs are `data/cache/cv_fix/closing_props` (77 JSON payloads, 6,491,336
bytes total; each file is opened separately) and
`data/domains/basketball_nba/player_boxscores.parquet` (1,118,538 bytes,
selected columns only).  No source over 300 MB is opened, and no output is
written under `data/`.

The primary unit is a paired Over/Under player-stat quote.  Every complete
price pair is retained in the tidy census.  Scoring selects one closest-to-even
line per game, player, stat, and book; both model and devigged market losses
use exactly those settled rows.  The model distribution is the named player's
empirical box-score history strictly before that game's UTC date.  The code
asserts the date filter by construction and does not use a snapshot store.

CRPS uses that empirical distribution.  The market CRPS proxy is its devigged
Over probability represented on the two integer outcomes adjacent to the
closing half-point line.  Pinball uses the median of each corresponding
distribution.  Brier scores P(Over closing line).  Each metric has a
deterministic 500-resample game-cluster interval (seed 228).  Brier also
retains ten fixed reliability bins for model and devigged market probabilities.

For the tail target, the favourite scorer is the player with the highest
closest-to-even player-points line for that game.  Each other named player is
scored on whether that player outscores the favourite.  The model probability
is the exact independent comparison of both players' strictly prior empirical
point histories.  The comparator is the observed prior tail base rate with a
one-success, one-failure initialization.  Model and base log loss use identical
tail rows and the same game-cluster interval procedure.

No threshold is changed: scoring proceeds only when at least 30 settled game
clusters exist.  The generated paired-loss CSVs retain the game identifier,
date, target, losses, and as-of history counts required to reproduce each
summary.  This preregistration makes no selection, deployment, or calibration
claim until the fresh run is complete.
