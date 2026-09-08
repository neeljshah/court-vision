# S293 preregistration, attempt 2: tail metric rail

Attempt 1 (`docs/evidence/harness/S293_tail_metric_rail_prereg_2026-09-07.md`,
scored at `df0f033f67fdd4a9ac6e5b615adf2be6995c89bc`) was REJECTED by
`docs/evidence/harness/S293_VERIFY_2026-09-07.md`. That sealed preregistration is
left untouched. This is a new seal for a new scoring run, written before any
attempt-2 metric is computed.

## What attempt 1 got wrong, and what changed

1. The trailing-side transform was computed in the LEADING team's frame. The
   corrected rule is: the reported probability and outcome are the home team's
   own `p` and `y` when the home margin is negative, and `1-p` / `1-y`
   otherwise.
2. Reliability cells with fewer than 30 rows were published as scored cells.
   Under Q7 a scored cell needs `n >= 30`. The corrected rule SUPPRESSES such a
   cell -- the declared bin is still published with its exact count, and its
   mean probability, empirical rate, reliability gap and log loss are null. No
   bin is dropped and no bin is merged into a neighbour, because merging would
   change the frozen 10-bin grid.
3. The replay rewrote the existing `S293_tail_metric_rail_2026-09-04.md` memo.
   It now emits only new dated artifacts and writes no memo at all.
4. A relative `--output-dir` failed after scoring. Output paths are now resolved
   and reported repo-relative only when they lie inside the repo.

## Premise remeasurement before scoring (Q8)

### Source identities

The historical identities named in the S293 specification body do not match this
worktree. The current source bytes are frozen here and printed again after the
pod run.

```text
cpcv_engine.py 5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5
walkforward.py c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e
s272_ingame_tail_recal.py 83f86f6a653a364c3e8047b58f5976128d69daeecc2a882dc82deffb78ca7c30
ingame_incumbent_nba.py 476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed
```

The S272 paired archive and summary are read-only inputs and must stay byte
identical; their SHA-256 values are
`77eebaa5e82d81d6a428874b937939353e15af21b6270b84f83691489297eeed` and
`1892f277dc7b55683792b7ac2491e8faf5b06ab20ad1f7b6f3ef087b0be70914`.

### Comeback mask count: a premise correction

The S293 specification's VERSION 2026-09-07 clause states the S291 mask as
`remaining_s = (4 - period) * 720 + game_clock_s for period <= 4`, restricted to
`abs(margin) >= 12` and `remaining_s <= 720`, and quotes 133,319 ticks / 1,113
games with an `outcome_home_win` split of 77,516 / 55,803.

Measured now on `data/cache/inplay_odds/nba_checkpoints_full.parquet` (465,249
rows, all of them unique `game_id`/`ts` keys, 1,593 games), the mask AS WRITTEN
measures 133,184 ticks / 1,111 games, split 77,381 / 55,803.

The delta is fully explained and is not a corpus difference. Dropping only the
`period <= 4` clause -- that is, admitting overtime periods 5-6, for which
`(4 - period) * 720 + game_clock_s` is always at or below 720 -- reproduces the
specification's numbers exactly:

```text
133,184 + 135 = 133,319 ticks
  1,111 +   2 =   1,113 games
 77,381 + 135 =  77,516 outcome_home_win = 1
 55,803 +   0 =  55,803 outcome_home_win = 0
```

So the quoted 133,319 / 1,113 is the same mask WITHOUT its own period cap, and
the 135 additional ticks (2 games) are all overtime states that ended in a home
win. The specification also requires overtime to be accounted explicitly and
separately, so this attempt keeps the mask exactly as written (`period <= 4`),
scores 133,184 ticks / 1,111 games, and publishes the 135 excluded overtime
ticks alongside it as the reconciliation. This is a premise correction to the
specification's quoted count, not a change to the mask, the bar, or any
threshold.

## Fixed measurements

- The archive premise is 310,349 rows -- 1,593 `all_game` plus 308,756
  `tail_tick` -- across 1,593 games. Mixed-grain input is refused by the
  sibling helper; every per-tick loss is REGENERATED through the unchanged S272
  route, never replayed off the archive sums.
- Brier is replayed on all ticks for candidate and recal_null and must match the
  S272 summary to within 1e-12.
- Tail ticks use the original S272 tail mask, `market_prob <= 0.10` or
  `market_prob >= 0.90`. Tail Brier and 10-bin ECE must match S272 to 1e-12.
- Log loss uses epsilon `1e-15`. Endpoint rows are clipped and counted; no
  non-finite, out-of-range or zero-probability log score is silently dropped.
  All-tick log loss is printed as an implementation diagnostic only, never as a
  comparison claim. Tail log loss is reported for both arms.
- The sign convention is improvement = baseline loss minus candidate loss;
  positive means lower candidate loss. The frozen Brier comparison bar remains
  `+0.004`; it is neither charged nor moved.
- The S289 diagnostic table publishes every frozen market-probability bin:
  `[0.01,0.05)`, `[0.05,0.10)`, `[0.10,0.20)`, `[0.80,0.90)`, `[0.90,0.95)` and
  `[0.95,0.99)`, each with counts, games, recal_null and market log loss, mean
  probability, empirical outcome rate and reliability gap. Every bin is
  published including any that is worse for recal_null.
- The S291 diagnostic mask is fixed before scoring by margin and clock alone, as
  stated above. The trailing-side transform reports the home team's own `p`/`y`
  when the home margin is negative and `1-p` / `1-y` otherwise. Trailing states
  that LOST are reported; the mask is never restricted to completed comebacks.
  Zero-clock ticks and overtime counts are published.
- Every declared reliability bin is published. A bin with `0 < n < 30` publishes
  its count and null scored fields, flagged `suppressed_below_min_n`. An empty
  bin publishes `n = 0`.
- The all-tick S272 Brier improvement bootstrap interval is reproduced as a
  COMPARISON RESULT only. Its lower bound is compared with `-0.0005`; this
  creates no pass condition and does not alter the `+0.004` bar.

## Inputs, outputs, and machine

The pod is required because the full in-game scoring route loads the complete
tabular corpus and its model dependencies. It runs only in the per-worktree
scratch tree through `/c/Users/neelj/bin/pod_run a14`; neither the deployed tree
nor the data tree is written. Inputs opened are:

| Path | Bytes | Resolution |
|---|---:|---|
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2829826 | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv` | 39159272 | tabular; not applicable |
| `docs/evidence/harness/S272_ingame_tail_recal_screen_2026-09-04_summary.json` | 5290 | JSON; not applicable |

The sole pod command writes exactly two new artifacts,
`docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_summary.json`
and `docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07_paired_losses.csv.gz`.
No existing artifact is rewritten. The dated memo
`docs/evidence/harness/S293_tail_metric_rail_attempt2_2026-09-07.md` is authored
by hand from that summary. The focused test is
`python -m pytest tests/platformkit/test_s293_tail_metric_rail.py -q -p no:cacheprovider`.
No ledger, register or trial-count file is opened or changed, and no trial is
charged.

S293_PREREG_SEAL_SHA256=d8dcfa628f3d0abbaeb2f6486c3b9a08392678a7a226c5313baa873230665e9d
