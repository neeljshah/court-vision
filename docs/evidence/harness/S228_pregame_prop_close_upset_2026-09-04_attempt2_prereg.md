# S228 Attempt 2 Pregame Prop Close Upset Preregistration

This uncharged, read-only calibration retry follows
`docs/evidence/tracking/specs/S228_spec.md` and sections B and Q of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. It corrects only the rejected
Q4 route. No register or ledger is amended.

Seal SHA-256: 83115c8892c0d7a4e0fb511aea16b8670ccd8dab8e059c2ebf19003ffb249617

The seal is the SHA-256 of this exact document with only the `Seal SHA-256:`
declaration line omitted. The route and scored artifacts must name this seal,
and this preregistration must be committed before their fresh generation.

Arms: (1) the named player's as-of empirical boxscore distribution versus the
devigged closing-line representation, scored by CRPS, pinball, and Brier for
P(Over); and (2) the named player's as-of empirical points comparison versus a
cluster-delayed observed tail base-rate comparator, scored by log loss. Both
arms use their identical settled canonical rows.

Frozen bar and verdict rule: parse all 77 files with zero unparsed files. If
fewer than 30 settled game clusters remain, report CLOSED AT LIMIT with the
exact count and do not score. Otherwise report SCORABLE with paired-loss
artifacts. The >=30-cluster bar and all metric definitions remain unchanged.

Fold scheme: chronological, one whole game cluster per scored fold; all rows
from the scored game are held out together. The purge removes every training
row in that game cluster. The symmetric embargo is one distinct game-date
block before and one distinct game-date block after the scored game's date.
For a same-date cluster, the whole date block is purged. Every tail base-rate
update is delayed until every eligible row in its game cluster has been scored;
no row can use an observed outcome from its own cluster.

The implementation must assert for every scored fold that no training row lies
inside its embargo window and that no scored row's own cluster contributed to
its prior. Sources remain read-only, are opened one at a time, and no source
over 300 MB is opened. No output is written under `data/`.
