# S86 -- price EVERY NBA in-play tick, not one per game

Row: `data/cache/inplay_odds/nba_checkpoints_full.parquet` is a complete
state x line x outcome tick corpus (465,249 ticks / 1,593 games) that has never
carried a model side; S58 trial B scored ONE tick per game.

Verdict: **LANDED as a SCREEN -- model BEHIND the in-play line pooled, MATCHING it
in 16 of 27 state cells.** Uncharged: no prereg seal, no ledger read, no ledger
write, no K consumed. **SINGLE-WINDOW** (one corpus, NBA 2024-10-22..2026-06-13).

Calibration measurement only. No dollar, ROI, profit or edge claim. No bar moved
(this row arms no bar). ASCII only.

Module: `scripts/platformkit/eval_gate/s86_nba_every_tick.py` (288 LOC)
Test: `python -m pytest tests/platformkit/ingame/test_s86_nba_every_tick.py -q` = **5 passed**
Archive (Q9): `data/cache/eval_gate/s86_nba_every_tick_2026-09-03.json` +
`...csv` (232,951 per-tick paired-loss rows, one row per scored tick).

---

## 0. STEP 0 -- premise re-measured first (Q8)

| the row says | measured 2026-09-03 | verdict |
|---|---|---|
| 465,249 ticks / 1,593 games | 465,249 rows, 1,593 distinct `game_id`, 2024-10-22..2026-06-13 | CONFIRMED |
| carries period, game_clock_s, score, margin, market_prob, outcome_home_win | all present; **0 nulls in every one of the 13 columns**; `traded` is True on 465,249 / 465,249 rows | CONFIRMED |
| S58 trial B scored one tick per game | `s58_nba_halftime_asof_trial.py:46` -- `cp = df[df["elapsed"] <= ANCHOR].sort_values(["game_id", "elapsed", "ts"]).groupby("game_id").tail(1).copy()` with `ANCHOR = 24.0`; its per-game CSV has 1,593 rows | CONFIRMED |
| `price_checkpoint` is a pure state function | `nba_checkpoint_benchmark.py:105` -- `price_checkpoint(p0, home_score, away_score, period, game_clock_s, margin_sigma=13.5) -> float`; reads no outcome and no other row | CONFIRMED |
| p0 comes from an as-of prior | `domains/basketball_nba/ratings.replay(games, until=game_date)` over **`data/domains/basketball_nba/games.parquet`** (4,846 rows). As-of rule, pinned in that function's docstring: *"process only games with `date < until` (strictly before)"* -- the tick's own game date is excluded | CONFIRMED |
| nothing has scored every tick | **PARTLY.** `data/cache/calibration_grid/nba_reliability_map.json` (2026-07-18) already reports a per-bucket **market** Brier over all 465,249 ticks, but its model side is `model_per_bucket_sampled = 12` -- twelve sampled ticks per bucket, from the sim path, with no CI, no partition and no as-of prior. **No paired per-tick model series exists.** | CONFIRMED (row stands) |

Schema as measured: `game_id int64, game_date object, ts int64, period int64,
game_clock_s float64, score_home int64, score_away int64, margin int64,
market_prob float64, traded bool, market_ticker object, outcome_home_win int64,
venue object`. Period census: P1 44,428 / P2 68,825 / P3 52,645 / P4 284,586 /
OT5 13,152 / OT6 1,613. `outcome_home_win` mean 0.5499.

Premise HOLDS -- proceed.

## 1. Partition (and an honest note about "the same rule S58 trial B used")

**S58 trial B used NO screen/verdict partition.** It was a charged trial and scored
all 1,593 games; its only split is the corpus-unit boundary `2025-08-01`
(2024-25 / 2025-26), which is a replication unit, not a screen side. There was no
rule to inherit.

This row therefore uses the repo's one partition primitive,
`scripts/platformkit/foundry/tiers.partition_corpus(states, seed=0)` -- the same
call, same seed, that the sibling screens S80 and S84 make. Each game is its own
`corpus_unit`, so `basis = "corpus_unit"`, blocks are sorted game ids and side
alternates. Recorded in the artifact:

- basis `corpus_unit`, seed 0
- screen 797 games / **232,951 ticks**; verdict 796 games (untouched here)
- `screen_sha256 = f105c609d2d4e56018a108a4154a81b2074115b533fec8b7e18150999fac8ca3`,
  `verdict_sha256 = 0683cbeab12a48f2bcb146821eaa857160356fe393b31c770c0cf61735ced402`
- sides asserted disjoint by the primitive and again by the per-file test

Everything below is the SCREEN side only.

## 2. The model side, and the two guards on it

`model_t = price_checkpoint(p0_asof(game), score_home_t, score_away_t, period_t,
game_clock_s_t)` -- one call per tick, row-wise, nothing fit on outcomes.

**Guard 1 -- as-of prior.** `elo_until_date == game_date` asserted on every row;
`replay` excludes `date >= until` by contract. The per-file test proves the
consequence rather than trusting the contract: adding a same-day game (and,
separately, a later game) to the games frame leaves p0 **bit-identical**.

**Guard 2 -- no same-tick or later read** (`assert_no_future_read`). Each game's
first 4 ticks are re-priced with **every later tick of that game withheld**;
any cross-row read (a game-level max, a next-tick line, a full-game normaliser)
moves them. Measured: 3,188 ticks re-priced, `max_abs_delta = 0.0` (exactly zero,
not a tolerance). The test plants the classic leak
(`model = groupby(game).transform("last")`) and asserts the guard raises.

**Independent reproduction of the sealed incumbent.** Re-deriving S58 trial B's
own checkpoint selection from this frame and joining to its archived per-game CSV:
797 / 797 screen games matched, `max_abs_elapsed_delta = 0.0`,
`max_abs_p0_delta = 1.11e-16`, `max_abs_model_delta = 1.11e-16`. The x10 series
contains the sealed one-tick result exactly.

## 3. Pooled result (SCREEN side, tick-weighted)

| | value |
|---|---|
| ticks / games | 232,951 / 797 |
| informative ticks (market_prob moved from the previous tick of the same game) | **82,248 (35.31 pct)** |
| Brier model (as-of prior + state repricer) | **0.081922** |
| Brier market (in-play line) | **0.077065** |
| improvement vs market | **-0.004857** (model behind) |
| ICC by game / design effect / n_eff | 0.2420 / 71.46 / **3,260.1** |
| game-clustered DM 95 pct CI | [-0.007355, -0.002359] (excludes 0) |
| DM p (raw, no deflation -- nothing charged) | 0.000146 |

Corpus units: 2024-25 n 100,377 / 328 games, -0.004634, CI [-0.008067, -0.001202];
2025-26 n 132,574 / 469 games, -0.005025, CI [-0.008573, -0.001477]. Both units
agree in sign and magnitude, but this is ONE corpus split by date, so the label
stays **SINGLE-WINDOW** (Q5).

The pooled Brier is small (0.077-0.082) only because 61 pct of the ticks are P4,
where the state has already decided the game. Read the cells, not the pool.

## 4. Period x margin (SCREEN side)

`n_eff` is game-clustered ICC ESS; `inf` = informative ticks.

| period | margin | n | inf | n_eff | Brier model | Brier market | improvement | DM CI95 |
|---|---|---|---|---|---|---|---|---|
| P1 | close_le5 | 14,047 | 11,148 | 896.5 | 0.229316 | 0.219061 | -0.010254 | [-0.018658, -0.001851] |
| P1 | mid_06_12 | 6,935 | 5,482 | 731.3 | 0.212314 | 0.193732 | -0.018582 | [-0.029782, -0.007383] |
| P1 | blowout_gt12 | 1,310 | 997 | 185.2 | 0.162311 | 0.138725 | -0.023586 | [-0.046380, -0.000791] |
| P2 | close_le5 | 13,544 | 9,483 | 716.1 | 0.229775 | 0.226459 | -0.003316 | [-0.012921, 0.006289] |
| P2 | mid_06_12 | 12,799 | 8,646 | 771.6 | 0.210191 | 0.196253 | -0.013938 | [-0.023838, -0.004039] |
| P2 | blowout_gt12 | 8,307 | 5,389 | 407.3 | 0.116603 | 0.102862 | -0.013741 | [-0.023852, -0.003630] |
| P3 | close_le5 | 8,740 | 7,069 | 669.7 | 0.224387 | 0.227292 | **+0.002905** | [-0.006325, 0.012134] |
| P3 | mid_06_12 | 8,769 | 6,999 | 733.4 | 0.180781 | 0.171387 | -0.009395 | [-0.019217, 0.000428] |
| P3 | blowout_gt12 | 8,771 | 6,110 | 514.0 | 0.060838 | 0.058007 | -0.002831 | [-0.008452, 0.002789] |
| P4 | close_le5 | 36,051 | 8,614 | 2,175.2 | 0.051087 | 0.050558 | -0.000529 | [-0.002225, 0.001167] |
| P4 | mid_06_12 | 47,962 | 6,723 | 1,045.6 | 0.017135 | 0.015808 | -0.001327 | [-0.002247, -0.000407] |
| P4 | blowout_gt12 | 57,579 | 4,731 | 2,433.9 | 0.002467 | 0.003065 | **+0.000598** | [-0.000273, 0.001468] |
| OT | close_le5 | 6,000 | 771 | 83.1 | 0.083128 | 0.024913 | **-0.058216** | [-0.076315, -0.040116] |
| OT | mid_06_12 | 2,002 | 84 | 46.5 | 0.010581 | 0.005262 | -0.005319 | [-0.007549, -0.003089] |
| OT | blowout_gt12 | 135 | 2 | 2.0 | 0.007406 | 0.007072 | -0.000334 | [-0.008797, 0.008129] |

The full three-way table (period x margin x time-remaining, 27 cells) is in the
artifact under `by_period_margin_rem`. **16 of the 27 cells have a DM CI that
includes 0** -- i.e. the as-of state price is statistically indistinguishable
from the line there. The largest of them:

| period | margin | time remaining | n | n_eff | model | market | improvement | DM CI95 |
|---|---|---|---|---|---|---|---|---|
| P3 | close_le5 | > 12 min | 8,299 | 663.5 | 0.223524 | 0.226899 | **+0.003375** | [-0.005957, 0.012708] |
| P4 | blowout_gt12 | 2-6 min | 3,339 | 576.7 | 0.003587 | 0.005790 | +0.002203 | [-0.001058, 0.005464] |
| P4 | blowout_gt12 | <= 2 min | 49,171 | 2,448.5 | 0.000000 | 0.000589 | +0.000589 | [-0.000247, 0.001424] |
| P4 | close_le5 | <= 2 min | 29,739 | 3,025.3 | 0.012263 | 0.012216 | -0.000047 | [-0.000761, 0.000666] |

**Does the as-of prior ever match the market?** Yes, and only where the STATE has
already done the work: late-and-decided (P4, any margin, under 6 minutes) and one
genuinely live cell, P3 close games with more than 12 minutes left (+0.003375, CI
crosses 0 -- a MATCH, not an AHEAD; the bar for AHEAD is a CI excluding 0 favouring
the model, and this does not clear it). Everywhere the pregame prior still carries
weight -- all of P1 and P2 -- the model is **significantly behind**, exactly as
expected of a static Elo prior against a live line.

The single worst cell is **OT close games (-0.058216)**: the repricer treats an OT
period as a fresh 5-minute game with the pregame `mu_diff` re-applied, while the
line has already absorbed 48 minutes of information. That is a known model artifact,
not a market finding.

## 5. Reliability of the MARKET itself (S43 max-loser-WP style)

10 equal-width bins on `calib_decomp.bin_edges(10)` -- the one bin rule (S42).
ECE is the market's own, against `outcome_home_win`.

| phase | n | market ECE | model ECE | loser paths | max-loser-WP p90 | > 0.8 |
|---|---|---|---|---|---|---|
| P1 | 22,292 | 0.045002 | 0.068025 | 355 | 0.845 | 51 |
| P2 | 34,650 | 0.035620 | 0.074038 | 355 | 0.851 | 52 |
| P3 | 26,280 | 0.020127 | 0.053143 | 355 | 0.831 | 46 |
| P4 | 141,592 | **0.002923** | 0.009875 | 355 | 0.855 | 53 |
| OT | 8,137 | 0.007463 | 0.158769 | 19 | 0.787 | 2 |

Per period x margin, worst market calibration first:

| cell | n | market ECE | model ECE |
|---|---|---|---|
| **P2 close_le5** | 13,544 | **0.064718** | 0.044219 |
| **P1 close_le5** | 14,047 | **0.055593** | 0.056264 |
| **P3 close_le5** | 8,740 | 0.052485 | 0.031156 |
| P2 mid_06_12 | 12,799 | 0.038792 | 0.101827 |
| P1 blowout_gt12 | 1,310 | 0.038687 | 0.130791 |
| ... | | | |
| P4 mid_06_12 | 47,962 | 0.005264 | 0.012209 |
| **P4 blowout_gt12** | 57,579 | **0.002107** | 0.002246 |

The shape of the P1/P2 close-game miss is consistent and one-directional:

```
P2 | close_le5      (market bins)          P1 | close_le5
 bin      n    mean    obs     gap          bin      n    mean    obs     gap
 0.3-0.4 2043  0.3509  0.4244 +0.0735       0.3-0.4 1770  0.3499  0.3983 +0.0484
 0.4-0.5 2019  0.4501  0.5612 +0.1111       0.4-0.5 1678  0.4478  0.5501 +0.1023
 0.5-0.6 2150  0.5544  0.5991 +0.0447       0.5-0.6 2072  0.5513  0.5994 +0.0481
 0.7-0.8 2019  0.7461  0.6365 -0.1097       0.7-0.8 2158  0.7471  0.6826 -0.0645
 0.8-0.9 1059  0.8378  0.7328 -0.1050       0.8-0.9 1603  0.8451  0.7255 -0.1196
```

Read as calibration: **early in close games the line is too flat in the middle and
too confident at the top** -- the 0.4-0.5 bin realises about 0.55, the 0.8-0.9 bin
about 0.73. Late (P4) the same line is essentially perfectly calibrated
(ECE 0.0021-0.0078). Max-loser-WP is flat across phases (p90 0.83-0.86, 46-53 of
355 loser paths peaking above 0.8), i.e. the phase difference is a *bin-level*
miscalibration, not a few runaway comeback paths.

**Target for the next arm: P1-P2, |margin| <= 5, more than 12 minutes remaining
(27,591 ticks / 20,631 informative on the screen side).** It is the phase with the
worst market calibration (ECE 0.056-0.065), the phase where the model is furthest
behind, and the only phase where informative ticks are the majority (P1 79.1 pct and
P2 67.9 pct of ticks, vs 14.2 pct in P4) -- so a candidate there is scored on real line movement
rather than on held quotes. This memo does NOT claim that gap is exploitable; it
locates where a better-conditioned model has room to close on the line.

## 6. Rails self-check (VERIFIER_CONTRACT B + Q)

- B1 no circular metric -- no row excluded after scoring; the only exclusion
  (`traded == False`) removes 0 rows on this corpus.
- B2 additive -- one new module, one new test; nothing renamed or removed.
- B7 no head-slice -- every tick of every screen game is scored; the partition is
  by whole game, and the corpus-unit split is reported.
- B8 no self-fit -- nothing is fit at all; the prior is as-of and the repricer is
  a fixed closed form.
- B9 denominator -- units reported three ways (n ticks, n_informative, game ESS
  n_eff); no recycled unit.
- B10/Q3 -- no bar moved; this row arms none.
- Q1/Q2 -- **no prereg seal and no ledger charge, because nothing is charged.**
  `_charge_ledger` is not imported; `backtest_fwer.jsonl` is never opened.
- Q4 -- no meta-learner and no fitted parameter, so there is nothing to purge or
  embargo; the leak contract is the as-of prior plus the truncation guard in S2.
- Q5 -- one corpus -> labelled **SINGLE-WINDOW** here and in the register row.
- Q6 -- calibration language only; no retracted figure appears.
- Q7 -- every metric is SCORED with n >= 30 except three deliberately published
  thin cells (OT blowout n 135 / n_eff 2.0 and two INSUFFICIENT reliability bins),
  each carrying its own n.
- Q9 -- per-tick paired-loss series archived (232,951 rows with `loss_model`,
  `loss_market`, `d`, `game_id` cluster, `ts`, `p0_asof`, `elo_until_date`), so
  every CI here recomputes from the artifact alone.

## NOT VERIFIED

- **SINGLE-WINDOW.** One corpus (NBA Polymarket checkpoints). The two corpus units
  are a date split of the same store, not a second corpus; `n_corpora_eff` is not
  claimed and `replication_gate` was not run.
- **Verdict side untouched.** 796 games are held out and unscored. Nothing here may
  be promoted to a charged finding without going through the verdict side.
- **The market-reliability bins are tick-weighted.** ICC by game is 0.24 (deff 71),
  so a bin's `n` overstates its independent information by roughly that factor. The
  bin gaps in S5 carry no CI and gate nothing.
- **OT pricing is a known model artifact** (documented at
  `nba_checkpoint_benchmark.py:17-21`), so the OT cells measure the repricer's OT
  handling, not the OT market.
- **One venue.** `venue` is Polymarket throughout; no Kalshi cross-venue check, and
  the line is a traded mid, not a devigged close.
- **`margin` sign is not used** -- buckets are on `|margin|`, so a home-favourite
  asymmetry inside a bucket is invisible here.
- **The 12-sample-per-bucket model column in
  `data/cache/calibration_grid/nba_reliability_map.json` was NOT reconciled** with
  this series; it comes from a different (sim) path and is quoted nowhere above.
- No charge, no seal, no ledger row. This is a screen, and a BEHIND is an honest
  result.
