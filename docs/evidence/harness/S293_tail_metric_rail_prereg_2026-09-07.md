# S293 preregistration: tail metric rail

## Scope fixed before scoring

This is an additive measurement rail. It does not fit a new candidate. The
unchanged S272 route regenerates one evaluator state per scored game through
`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`, with its symmetric
one-day embargo and shared team/matchup purge. The route's per-tick outputs are
then scored by the additive sibling
`scripts.platformkit.eval_gate.cpcv_tail_metrics`.

The primary replay consumes every row in
`docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv`:
1,593 `all_game` rows plus 308,756 `tail_tick` rows, or 310,349 rows across
1,593 games. No metric is selected from a favorable subset. Mixed-grain input
is refused by the sibling helper; the new per-tick differential is regenerated
from `data/cache/inplay_odds/nba_checkpoints_full.parquet` rather than inferred
from the old game sums.

## Fixed source identities

The historical identities named in the S293 specification were remeasured and
do not match this worktree. This continuation freezes the current source bytes
below; all are printed again after the pod run.

```text
cpcv_engine.py 5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5
walkforward.py c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e
s272_ingame_tail_recal.py 83f86f6a653a364c3e8047b58f5976128d69daeecc2a882dc82deffb78ca7c30
ingame_incumbent_nba.py 476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed
```

The S272 summary and paired archive are read-only inputs and must remain byte
identical. Their SHA-256 values are respectively
`1892f277dc7b55683792b7ac2491e8faf5b06ab20ad1f7b6f3ef087b0be70914` and
`77eebaa5e82d81d6a428874b937939353e15af21b6270b84f83691489297eeed`.

## Fixed measurements

- Brier is replayed on all ticks for candidate and recal_null and must match
  S272 to within 1e-12.
- Tail ticks use the original S272 tail mask: `market_prob <= 0.10` or
  `market_prob >= 0.90`. Tail Brier and 10-bin ECE must match S272 to 1e-12.
- Log loss uses epsilon `1e-15`. Endpoint rows are clipped and counted; no
  non-finite, out-of-range, or zero-probability log score is silently dropped.
  All-tick log loss is printed as an implementation diagnostic, not a
  comparison claim. Tail log loss is reported for both arms.
- The sign convention is improvement = baseline loss minus candidate loss;
  positive means lower candidate loss. The frozen Brier comparison bar remains
  `+0.004` and is not charged or moved.
- The S289 diagnostic table publishes every frozen market-probability bin:
  `[0.01,0.05)`, `[0.05,0.10)`, `[0.10,0.20)`, `[0.80,0.90)`,
  `[0.90,0.95)`, and `[0.95,0.99)`. Each prints counts, games, recal_null and
  market log loss, mean probability, empirical outcome rate, and reliability.
- The S291 diagnostic mask is `period <= 4`, `abs(margin) >= 12`, and
  `(4 - period) * 720 + game_clock_s <= 720`. It is set before scoring.
  The trailing-side transform uses `1-p` and `1-y` only when the home team is
  trailing. It reports both completed and unsuccessful trailing states, plus
  zero-clock and OT counts. OT periods 5-6 are counted outside this mask.
- The all-tick S272 Brier improvement bootstrap interval is reproduced as a
  comparison result only. Its lower bound is compared with `-0.0005`, without
  changing S272's `+0.004` bar or creating a new pass condition.

## Inputs, outputs, and machine

The pod is required because the full in-game scoring route loads the complete
tabular corpus and model dependencies. It runs only in the per-worktree scratch
tree through `/c/Users/neelj/bin/pod_run a14`; the deployed tree and data tree
remain untouched. Inputs opened are:

| Path | Bytes | Resolution |
|---|---:|---|
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2829826 | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv` | 39159272 | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json` | 5290 | JSON; not applicable |

The sole pod command writes a new S293 summary and per-tick paired differential
under `docs/evidence/harness/`. The focused test is
`python -m pytest tests/platformkit/test_s293_tail_metric_rail.py -q -p no:cacheprovider`.
No ledger or register file is opened or changed.

S293_PREREG_SEAL_SHA256=8af6d5591a3b70f983d94dd5ab9b2a34dc659f0d65b18126b7482175e18618e8
