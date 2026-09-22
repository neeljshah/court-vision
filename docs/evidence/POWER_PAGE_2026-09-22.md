# Power page: the minimum detectable effect behind every market-relative row

An interval that spans zero is a non-result, never a tie. This page states, for each of my own
market-relative rows, the smallest effect that row's design could have detected at conventional
power -- its minimum detectable effect (MDE) -- so a reader knows which rows carry information
before reading them. A row whose MDE is several times the smallest effect that could matter was
never able to answer the question it was pointed at, whatever number it printed. Of the eight
market-relative rows, four are informative (one of them only marginally), three are uninformative,
and one sits below the project's own sample floor; the remaining rows in the table are outside the
market-relative frame entirely. This is a resolution statement about the designs, not a claim
about any effect being real.

## Method, and its assumptions

For a two-sided test at alpha = 0.05 with power 0.80, and with a reported 95 percent interval
giving the standard error directly (half-width HW = 1.96 * SE, so SE = HW / 1.96):

```
MDE = (z_0.975 + z_0.80) * SE = (1.96 + 0.84) * SE
    = ((1.96 + 0.84) / 1.96) * HW = 1.43 * HW     <- "about 1.43x the printed half-width"
n_needed = n_current * (MDE_current / target_effect)^2      (SE goes as 1 / sqrt(n_games))
```

Every MDE below uses the constant to four figures, 1.429 (exact z values 1.959964 and 0.841621
give 1.4294; the rounded (1.96 + 0.84) / 1.96 gives 1.4286). The two differ by 0.06 percent and
no row changes label or rounded MDE under either.

Assumptions, stated because they are load-bearing:

1. The interval is symmetric and approximately normal on the estimate's scale. The in-game
   intervals are percentile bootstrap (`scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:81`),
   which is not required to be symmetric, so HW = (hi - lo) / 2 is exact only under symmetry.
2. The standard error under the alternative equals the standard error under the null.
3. The cluster unit is held fixed. Every in-game interval resamples whole games, so the n in the
   scaling formula is n_games and never n_ticks (`:70-82`).
4. This is a post-hoc MDE derived from the realized standard error -- a statement about this
   design's resolution. It is not "observed power" and says nothing about whether an effect exists.
5. Where a row states an n but publishes no interval bounds, the MDE is not computable and the
   interval is recorded as **unknown** rather than invented.

## Smallest interesting effect, per metric

- **Brier delta against a venue mid: 0.004375 (0.4375 pp).** This is the Kalshi maker fee scale,
  `0.0175 * C * P * (1 - P)` at P = 0.5, where `_KALSHI_MAKER_COEF = 0.0175`
  (`scripts/platformkit/execution/venue_fees.py:59`, module header lines 8-20). Why it is the
  floor: a sharpness improvement smaller than the cost of acting on it cannot change a decision,
  whatever its sign. **Caveat, explicit:** a Brier delta and a price quantity in pp are not the
  same unit, the mapping between them is not one-to-one, and it is not measured here. The fee
  scale is an order-of-magnitude floor, not an exchange rate.
- **CRPS delta on total runs: 0.0288 runs**, adopted as 1 percent of the market's own CRPS level
  of 2.8808 (`EVIDENCE.md:34`). This is a **stated convention, not a measurement** -- no fee-scale
  equivalent has been measured for CRPS in runs. It is declared so the column below is readable
  and should be replaced by a measured threshold when one exists.
- **The project's own sample floor: 30 scored games**
  (`scripts/platformkit/ingame/gate_a0_ingame_vs_market.py:24, 84-87`).

**Vocabulary, so the labels do not collide with the artifacts.** This page uses its own three-way
split -- **INFORMATIVE / UNINFORMATIVE / BELOW-FLOOR** -- of the landed module's single
`UNDERPOWERED` verdict, which covers **both** n < 30 **and** an interval containing zero
(`gate_a0_ingame_vs_market.py:84-87`). A reader opening the artifact will therefore see
`UNDERPOWERED` where this page says `UNINFORMATIVE`. The artifact's own verdict word is printed
alongside this page's on every row that has one.

## The table

Every `EVIDENCE.md` row that states an n, plus four Gate A-0 / S347 sub-rows. `HW = (hi - lo) / 2`
from the interval as its source prints it; `MDE = 1.429 * HW`. "x fee" is MDE divided by the
0.004375 Brier anchor (the CRPS row uses its own 0.0288-run anchor instead).

| Row (source) | n | Interval | HW | MDE at 80 pct power | Artifact verdict | This page |
|---|---|---|---|---|---|---|
| NBA pregame Brier vs devigged close (`EVIDENCE.md:32`) | 743 games | [-0.0036, +0.0175] | 0.01055 | **0.01508** (3.45x fee) | `TRAILS_CLOSE` (CI includes 0) | **UNINFORMATIVE** -- spans zero |
| NBA win prob, 3-fold walk-forward (`EVIDENCE.md:33`) | 1,473 | **unknown** (std 0.0084 is fold-to-fold dispersion, not an interval on a market-relative delta) | n/a | not computable | no market baseline in artifact | not a market-relative row |
| MLB total runs, pregame CRPS (`EVIDENCE.md:34`) | 300 games | [-0.1657, 0.0482] | 0.10695 | **0.15283 runs** (5.31x the 0.0288 convention) | `UNDERPOWERED` | **UNINFORMATIVE** -- spans zero |
| NBA player-prop MAE (`EVIDENCE.md:37`) | 20,354 player-games | **unknown** (no interval, no market baseline) | n/a | not computable | accuracy, no market comparison | outside this frame |
| NBA in-game, end of Q1 (`EVIDENCE.md:43`) | 1,592 games | [-0.0161, -0.0008] | 0.00765 | **0.01093** (2.50x fee) | `MARKET_SHARPER_PROVISIONAL` | **INFORMATIVE**, marginally -- see note below |
| NBA halftime / end Q3 / Q4 under 5:00 (`EVIDENCE.md:44`) | 1,593 games | **unknown** -- the row prints only "all CIs include 0" | n/a | not computable | `UNDERPOWERED` | **UNINFORMATIVE** -- spans zero by the row's own statement |
| MLB CRPS, end of innings 6 / 7 / 8 (`EVIDENCE.md:45`) | 49-55 games | **unknown** -- the row prints only "CIs exclude 0" | n/a | not computable | `MODEL_SHARPER_PROVISIONAL` | **INFORMATIVE** -- excludes zero, clears the 30-game floor; bounds must be published before the MDE can be read |
| Soccer home-win, minute 60 / 75 (`EVIDENCE.md:46`) | 22 / 17 games | **unknown** | n/a | not computable | `UNDERPOWERED` | **BELOW-FLOOR** -- both under 30 games |
| **Gate A-0 MLB, overall** (`docs/evidence/ingame/gate_a0_summary.md:5`) | 227 games / 78,986 ticks | [0.01704, 0.04535] | 0.01416 | **0.02023** (4.62x fee) | `BEHIND` | **INFORMATIVE** -- excludes zero; the measured gap (+0.03103) is 7.09x the fee scale and 1.53x its own MDE |
| **Gate A-0 soccer, overall** (`gate_a0_summary.md:6`) | 51 games / 9,003 ticks | [0.04876, 0.12696] | 0.03910 | **0.05587** (12.77x fee) | `BEHIND` | **INFORMATIVE** -- excludes zero and clears the floor, but this design could only ever have seen effects above about 0.056 Brier |
| Gate A-0 MLB, phase 7-9+ (`gate_a0_summary.md:13`) | 171 games | [0.03667, 0.10990] | 0.03661 | **0.05232** (11.96x fee) | `BEHIND` | **INFORMATIVE** -- excludes zero |
| Gate A-0 MLB, 0.6-0.8 price band (`gate_a0_summary.md:21`) | 172 games | [-0.03581, 0.02223] | 0.02902 | **0.04147** (9.48x fee) | `UNDERPOWERED` | **UNINFORMATIVE** -- spans zero |
| Gate A-0 MLB, minutes-to-close < 3 (`gate_a0_summary.md:31`) | 227 games | [-0.00618, 0.01411] | 0.01014 | **0.01450** (3.31x fee) | `UNDERPOWERED` | **UNINFORMATIVE** -- spans zero |
| S347 all_tick overall, arm B Brier (`docs/evidence/ingame/S347_FOUR_ARM_RESULT_2026-09-21.md:26`) | 135 games | [-0.010776, +0.004000] | 0.00739 | **0.01056** (2.41x fee) | `UNDERPOWERED` | **UNINFORMATIVE** -- spans zero; representative of all **96 of 96** cells |
| Conditioning vs a static prior (`EVIDENCE.md:47`) | **no n stated** | **unknown** | n/a | not computable | sharpness vs static, not vs the market | outside this frame |
| Signal discovery, 0 of 60 (`EVIDENCE.md:57`) | 60 classes | n/a -- a multiplicity-corrected count, not an effect estimate | n/a | n/a | `REJECT` | complete result |
| Gate B tracking ablation (`docs/evidence/props/q06_gate_b_tracking_ablation_summary.json`, section C of `EVIDENCE.md`) | **no n stated** | **unknown** | n/a | not computable | `REJECT` (`CEILING_ZERO`) | complete result |
| Prop + defender matchup (`EVIDENCE.md:55`) | **no n stated** | **unknown** | n/a | not computable | `HOLD` | the row itself says CRPS underpowered |

**Note on the end-of-Q1 row.** It excludes zero only marginally: the measured gap is 0.0084
against an MDE of 0.01093, so the gap is **0.77x its own MDE** and the upper bound is -0.0008.
That is a detection at well under 80 percent power, and it should be read as a first indication
rather than a settled one.

**Tally across the eight `EVIDENCE.md` rows that carry a market-relative effect estimate**
(`:32, :34, :43, :44, :45, :46`, and the two Gate A-0 sports carried by `:53`): **four are
INFORMATIVE** (NBA end of Q1 marginally, MLB innings 6/7/8, Gate A-0 MLB, Gate A-0 soccer),
**three are UNINFORMATIVE** (NBA pregame, MLB pregame CRPS, NBA halftime / Q3 / Q4), and **one is
BELOW-FLOOR** (soccer minute 60 / 75). The four remaining Gate A-0 and S347 sub-rows in the table
are not counted in that eight; three of them are UNINFORMATIVE and one INFORMATIVE.

## What sample the next rows need

Every uninformative row is uninformative for the same reason: the design's resolution is several
times the smallest effect that could matter. Scaling by `n_needed = n * (MDE / target_effect)^2`,
with the fee anchor 0.004375 for the Brier rows and the 0.0288-run convention for the CRPS row:

| Row | MDE at current n | n_needed |
|---|---|---|
| NBA pregame (n = 743) | 0.015076 | **8,823 games** -- roughly seven NBA regular seasons |
| NBA in-game end of Q1 (n = 1,592) | 0.010932 | **9,940 games** |
| Gate A-0 MLB (n = 227) | 0.020227 | **4,852 games** |
| Gate A-0 soccer (n = 51) | 0.055874 | **8,318 games** |
| MLB pregame CRPS (n = 300) | 0.152832 runs | **8,448 games** (0.0288-run anchor) |

The recomputed requirement therefore spans **4,852 to 9,940 games**. A 5,000-to-10,000-game band
holds for four of those five rows -- NBA pregame, NBA end of Q1, Gate A-0 soccer and MLB pregame
CRPS; the fifth, Gate A-0 MLB, lands just under the floor at 4,852. Soccer minute 60 / 75
(n = 22 / 17) must first clear the 30-game floor before any interval on it is worth reading.

Two things follow. First, the small-effect question is not answerable by adding games to these
corpora at this rate: every row needs something on the order of five to ten thousand games,
an order of magnitude beyond what is on hand, and no amount of the same data makes the pregame
row informative. Second, the sample worth collecting next is therefore not more of the same. It
is forward capture -- the only route to a genuinely independent second corpus -- and fill realism
measured on a real tape, where the unit of observation is a fill rather than a game. Zero of
either exists today, which is stated plainly as the current position rather than as a plan
already underway.

---

**Last verified 2026-09-22.** Every constant, half-width, MDE, multiplier and required-n figure on
this page was recomputed line by line by an independent check held in the private planning tree
and not published with it; that check returned PUBLISHABLE AFTER CORRECTIONS, and all ten of its
corrections are applied above.

## NOT VERIFIED

- **Nothing was executed against a corpus for this page**: no scripts, no tests, no network. The
  only computation was arithmetic on numbers transcribed from files in this tree.
- `EVIDENCE.md:44, :45, :46` publish no interval bounds. Their underlying JSON artifacts were
  **not opened**, so those three MDEs are recorded as unknown rather than reconstructed.
- The MDE arithmetic is hand-computed from the printed bounds, not run through a power library.
- The 0.0288-run CRPS threshold is a convention declared here, with no measured basis in this
  tree. The 0.004375 Brier anchor is a fee scale in price units, not a measured Brier effect.
- The 95 percent intervals are percentile bootstrap and are not required to be symmetric, so
  `HW = (hi - lo) / 2` is an approximation on every in-game row.
- This page does **not** check whether any measured effect is real, whether any model is
  correctly specified, or whether the corpora behind these rows are free of the join-integrity
  and staleness limitations recorded in `docs/JOB_EVIDENCE_PACKET.md`. It checks resolution only.
