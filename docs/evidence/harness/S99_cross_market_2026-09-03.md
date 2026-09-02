# S99 -- one game, all its in-play markets (cross-market screen)

**Verdict: SCREEN, a non-finding. Premise CONFIRMED. The rest-of-game distribution is BEHIND
both markets everywhere it is scored. Bar not met, no prereg DRAFT written, no charge, no seal.**

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S99 (premises L14 + L20 of
`docs/evidence/harness/INGAME_GAP_PREMISES_2026-09-03.md`).
Artifacts: `data/cache/eval_gate/s99_cross_market_2026-09-03.json`,
`data/cache/eval_gate/s99_game_keys.parquet`,
`data/cache/eval_gate/s99_cross_market_2026-09-03_{mlb,soccer_intl}_series.csv`.
Code: `scripts/platformkit/eval_gate/s99_cross_market.py` (218 LOC) +
`scripts/platformkit/eval_gate/s99_corpus.py` (274 LOC) +
`tests/platformkit/ingame/test_s99_cross_market.py` (9 passed).

---

## Step 0 -- the premise (Q8), measured before anything was built

`data/cache/inplay_odds/*_price_series.parquet` carries 12 columns and NO state of any kind:
`sport, venue, game_date, ticker_or_slug, event_key, market_type, side, ts, prob, traded,
close_time, result_where_known`. `market_type` values are `moneyline | spread | total` (mlb)
and `moneyline | spread | team_total` (soccer_intl); `side` is the team code on a moneyline,
the integer strike on an MLB total (`KXMLBTOTAL-26JUL011235CWSBAL-10`, side `10`) and
`<CODE><N>` on a soccer team total (`KXWCTEAMTOTAL-26JUL01BELSEN-BEL3`).

**The row's premise is confirmed exactly.** `event_key` is market-type-specific
(`KXMLBGAME-26JUL011235CWSBAL` vs `KXMLBTOTAL-26JUL011235CWSBAL`), so zero events carry two
market types. **The strip rule is `event_key.split("-", 1)[1]`** -- everything after the first
hyphen. It is applied to Kalshi rows only; the MLB store's other venue is polymarket
(9,260,915 moneyline rows, 2,820 events, keys like `mlb-ari-atl-2025-06-03`), a different key
space with no second market, so it cannot join and is dropped.

After the strip:

| sport | kalshi games | games with >= 2 markets | moneyline ticks | spread | total / team_total |
|---|---|---|---|---|---|
| mlb | 972 | **99** | 334,771 | 130,457 | 526,057 |
| soccer_intl | 96 | **96** | 963,546 | 609,424 | 688,933 |

(tick counts are over the multi-market games only). Both clear the 30-game floor, so the lane
proceeded.

**On-disk state per tick.** `data/cache/ingame_grade_joined/mlb` (227 games) carries
`state_summary = "home_score=.. away_score=.. inning=.. half=.. outs=.. base=.. bos=.. re=..
count=.. pitch_count=.. tto=.."`; `.../soccer_intl` (51 games) carries
`"home_score=.. away_score=.. minute=.."`. Intersecting with the multi-market games:
**MLB 87 of 99, soccer_intl 47 of 96** carry a state series. Outcomes:
`data/domains/mlb/games_current.parquet` (11,179 rows, 2022-04-07..2026-07-12, with
`home_runs`/`away_runs`) covers MLB -- note `games.parquet` stops at 2021 and
`espn_boxscores.parquet` is down to 2 rows, so `games_current` is the only usable MLB final;
soccer finals come from `data/domains/soccer_intl/espn_finals.parquet` through the existing
`ingame.soccer_outcome.SoccerOutcomeResolver` (54 of 96 games resolvable).

**Settlement semantics, measured, not assumed.** For the 917 settled (game, strike) MLB pairs
joinable to `games_current`, the rule `final total >= strike` reproduces
`result_where_known` at **1.000**; `> strike` reproduces it at 0.9237. The soccer team-total
rule `team goals >= N` with the ticker tail read as `<home><away>` reproduces settlement at
**0.9915** mean per-game agreement (the other three code/rule combinations score 0.65-0.83).
The module does **not** use that check to orient games -- home/away comes from the ESPN
finals row the resolver already returns -- it is independent corroboration only.

---

## What was built

**(a) The re-keyed view.** `s99_corpus.rekey(sport)` adds a `game_key` column; `game_key_view()`
aggregates to one row per `(sport, game_key, market_type)` with `n_ticks, n_strikes, ts_min,
ts_max, game_date, n_markets_on_game` and is written to
`data/cache/eval_gate/s99_game_keys.parquet` (1,400 rows). **No store is rewritten** -- the
price parquets and the joined stores are opened read-only, and the venue filter is pushed into
the parquet reader (13.4M -> 4.2M rows for MLB).

**(b) The rest-of-game distribution, analytic.** Sums of independent Poissons are Poisson, so
no simulation is needed. MLB: remaining half-innings from `(inning, half, outs)` of a 9-inning
game (`away = (1 - outs/3) + (9 - inning)` in the top, `home = 10 - inning`, and mirrored in
the bottom), each at the batting team's as-of runs-per-half-inning rate, so the rest-of-game
total is `Poisson(lam_home + lam_away)` and the home-win probability is the Skellam tail of
`(home rest - away rest)` against the current margin, with an exact tie (extras) weighted 0.5.
soccer_intl: `Poisson(rate_team * minutes_left)` per team, `minutes_left = 90 - minute`, and a
draw scored 0 for the home moneyline. **As-of rates, strictly before**: MLB team runs per game
over the same season's prior games in `games_current.parquet` divided by 9 (minimum 5 prior
games, else the prior-games league mean); soccer team goals per match over prior internationals
in `results.parquet` within a 6-year window divided by 90. The strictly-before guard is the leak
contract and is tested with a poison row (a 900-run game dated exactly on the as-of date, which
must not move the rate, and must move it one day later).

**State staleness.** A joined-store series stops when the capture stops but the price series
runs to settlement, so a plain backward as-of join silently carries a two-hour-stale score
forward. Ticks further than **300 s** from their last observed state are dropped, never guessed.
Before that guard the MLB moneyline Brier was 0.3234 against a market 0.2130; after it, 0.2010
against 0.1606 -- i.e. most of the apparent model failure was stale state, and this is recorded
because a lane reading the pre-guard table would have concluded the distribution is worse than
a coin flip.

**(c) Scoring, SCREEN side only** (`foundry.tiers.partition_corpus`, S82's game-first-date
ISO-week basis, seed 0). Nothing is FIT on the scored rows -- the only parameters are the as-of
rates -- so there is no train fold to purge; the leak contract is the strictly-before guard,
not a walk-forward split, and that is stated rather than dressed up as one.

---

## Results (SCREEN side; positive delta = model better than market)

### MLB -- 85 of 99 multi-market games joined (2 doubleheader keys `...G1/G2` fail the ticker regex, 12 have no state series), SCREEN 52 games / 90,915 ticks

| leg | n ticks | n games | Brier model | Brier market | delta (market - model) | game-clustered CI95 |
|---|---|---|---|---|---|---|
| moneyline (home) | 11,124 | 52 | 0.201034 | 0.160624 | **-0.040410** | [-0.069640, -0.011180] |
| total (>= strike) | 79,791 | 50 | 0.160422 | 0.139822 | **-0.020601** | [-0.035143, -0.006058] |

CRPS of the final-total distribution against the realized total: **2.8213** on 11,124 ticks /
52 games (model side only; the market's strike ladder is scored as Brier above, not converted
into a rival distribution -- so this CRPS has no paired market number and is a level, not a
comparison).

### soccer_intl -- 47 of 96 games joined but only 25 with usable ticks, SCREEN 8 games / 4,553 ticks

| leg | n ticks | n games | Brier model | Brier market | delta (market - model) | game-clustered CI95 |
|---|---|---|---|---|---|---|
| moneyline (home) | 498 | 7 | 0.283741 | 0.159716 | **-0.124025** | [-0.257014, +0.008964] |
| team_total (>= N) | 4,055 | 8 | 0.164598 | 0.147692 | **-0.016906** | [-0.067538, +0.033727] |

CRPS of the final-total distribution: **1.0287** on 498 ticks / 7 games.

**Bar (`>= +0.004` with a CI excluding zero on the total leg): NOT MET in either sport, and the
sign is wrong -- both MLB CIs exclude zero on the BEHIND side.** `prereg_draft_warranted` is
False for both sports and **no prereg DRAFT was written**.

---

## (d) Cross-market consistency of the market itself

At each tick carrying both markets, the as-of team **split** `lam_h / (lam_h + lam_a)` is held
fixed and the rest-of-game scoring **volume** `L` is solved (nearest point on a 40-point
log grid over [0.01, 30]) so that the implied home-win probability reproduces the market's own
moneyline. That distribution's implied total probability is then compared with the market's own
total price at the same strike. This is the only identifying restriction that makes the question
non-degenerate: with two free Poisson parameters and two market constraints the market is
consistent by construction, and holding the volume fixed instead makes the answer independent
of the moneyline entirely.

| sport | phase | mean abs inconsistency | n |
|---|---|---|---|
| mlb | inn 1-3 | 0.3339 | 9,794 |
| mlb | inn 4-6 | 0.2421 | 9,118 |
| mlb | inn 7+ | 0.1861 | 7,086 |
| mlb | **all** | **0.2614** | 25,998 (subsample step 3) |
| soccer_intl | min 0-30 | 0.3469 | 981 |
| soccer_intl | min 31-60 | 0.2865 | 1,277 |
| soccer_intl | min 61+ | 0.1753 | 1,021 |
| soccer_intl | **all** | **0.2699** | 3,279 (no subsample) |

Both sports show the same shape: the two markets disagree most early and converge as the game
resolves. **This number is a joint statement about the market AND the fixed as-of split, not a
pure market-internal defect** -- an inconsistency of 0.26 in probability units is far too large
to attribute to the market alone, and the most likely reading is that the as-of split (a
season-to-date team rate with no starter, park, lineup or in-game information) is simply the
wrong shape, which is the same thing the Brier table says. The moneyline was reproducible to
within 0.02 by some grid `L` on **79.5 pct** of MLB ticks and **90.8 pct** of soccer ticks; the
remainder are mostly tied or near-decided states where no scoring volume reproduces the quoted
price under a fixed split, and they are counted in the mean rather than dropped.

---

## Limits and defects found (all measured)

1. **The distribution is behind both markets on every leg scored.** A season-to-date Poisson
   rate is not competitive with an in-play line; the two MLB CIs exclude zero on the behind
   side. Nothing here supports a prereg.
2. **22 of the 47 soccer games with a state file carry `state_summary = "live"`** -- a bare
   string with no score and no minute (every capture before 2026-06-25). They are unusable, and
   they are why soccer falls from 47 joined games to 25 with ticks and to **8 on the SCREEN
   side**. The soccer table is far too thin to gate anything and is reported as such.
3. **The ISO-week partition is lopsided on a tournament corpus.** The 2026 World Cup spans a
   handful of ISO weeks, so the alternating-block rule put 8 games on SCREEN and 17 on VERDICT
   out of 25. No bar was moved and no reseed was tried -- a different seed is a different row.
4. **Two MLB doubleheader keys (`...MILSTLG1`, `...MILSTLG2`) do not parse** and are dropped;
   the ticker regex expects a letters-only team tail and `games_current` would need `game_seq`
   to disambiguate them anyway.
5. **The model is deliberately crude and its ceiling is not measured.** No starting pitcher, no
   park, no lineup, no bullpen, no red cards, no stoppage time; the home team's skipped bottom
   of the 9th and MLB extra innings are not modelled (an exact tie is scored 0.5). Each of these
   inflates rest-of-game variance. What the table shows is that this shape of model is behind --
   not that a distributional model must be.
6. **CRPS has no market counterpart here.** Building a rival distribution from the strike ladder
   is a separate piece of work (`benchmarks/crps_market/market_dist.py` does it for pregame
   lines); the L20 bar asked for a CI excluding zero on CRPS and this run cannot supply one,
   which is reported as a gap rather than substituted with the Brier CI.

---

## Rails

- **No charge, no seal.** `_charge_ledger` is never imported;
  `data/cache/eval_gate/backtest_fwer.jsonl` was never opened and is still **18 rows**
  (mtime 2026-09-02 12:27, before this row ran). K was never read. `data/registry/` untouched.
  No flag flipped, no bar moved (BAR = 0.004 asserted in the module and unchanged), no
  `--force`, no push. Nothing read or written under `src/`, `kernel/`, `api/`, `intel/`,
  `scripts/team_system/`.
- **Q9 archive.** `s99_cross_market_2026-09-03_{mlb,soccer_intl}_series.csv` (150,231 and
  15,336 rows) carry, per tick: `game, ts, market, strike, price, y, y_total`, the full as-of
  state (`cur_h, cur_a, inning, half, outs, minute`), the derived `lam_h, lam_a` (and
  `cur_team, lam_team` for soccer), `p_model`, `loss_model`, `loss_market`, `ml_price`, `phase`
  and `partition_side`. Every headline in this memo recomputes from those CSVs alone -- the
  per-file test asserts it (`test_artifact_headline_reproduces_from_the_archived_differential`
  re-derives each leg's delta to 1e-9 and re-checks the prereg gate).
- **Q5.** No AHEAD is claimed, so no second corpus is owed; two sports were scored and both are
  BEHIND. Each sport is one venue and one window -- SINGLE-WINDOW.
- **Q6.** Calibration language only. An honest BEHIND is a result.
- **NOT VERIFIED:** this is the lane's own report; no verifier re-run.

## Reproduce

```
python -m scripts.platformkit.eval_gate.s99_cross_market
python -m pytest tests/platformkit/ingame/test_s99_cross_market.py -q
```
