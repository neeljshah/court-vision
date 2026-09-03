# S206 WNBA in-game first score, 2026-09-04

Verdict: SCREEN NULL. This is a calibration screen, not an operational change.
The Stern-state candidate does not clear the unchanged +0.004 bar. No flag,
register, ledger, or file under `data/` was written.

## Premise first

The premise was remeasured before scoring from the named local inputs below.
It holds: 18,650 joined, labeled ticks cover 85 games; the full intersect
in-play denominator is 186,736 ticks; 19,456 are in the PBP span (10.42
percent); state-age median is 15 seconds, p90 is 132 seconds, and zero joined
ticks are older than 300 seconds. Eighty-four of 85 games have at least 100
in-span ticks. The price store has 98 in-play priced events and settlement is
available for all 98.

Inputs opened, one store at a time:

| Path | Bytes | SHA-256 | Use |
| --- | ---: | --- | --- |
| `data/cache/inplay_odds/wnba_checkpoints_full.parquet` | 167408 | `a97392703bb6c710b0713f8421db860236dcb0c1b9dcc6623ca1d4d5e57a76dc` | action-derived as-of state and held-out home-win label |
| `data/cache/inplay_odds/wnba_price_series.parquet` | 3270899 | `3ce89dee6471a04745bcf1e32c6c183fac4238ab781df7dcea53a994e472b8f3` | contract side and in-play probability |
| `docs/evidence/harness/wnba_ingame_census_2026-09-04_per_game.csv` | 5137 | `724bde89aaf39e001ceceb961a8824a2d63c97fa544f11c657c6cc707ea0fb90` | 85-game denominator and in-span accounting |

The checkpoint store preserves contract-side `prob` but not `side`. Before
comparison with the home-win label, the adapter reconstructs a home-win market
probability from the original price row: home side keeps `prob`; away side uses
`1 - prob`. All 18,650 checkpoint rows matched exactly once. Raw contract-side
probabilities are not used as a home-win market comparator.

## Method

The existing `foundry/ingame_screen.py` machinery is used unchanged: `BAR =
0.004`, `assert_tick_asof`, and `walk_forward_feature`. Folds are
game-first-date walk-forward folds, game-disjoint, with the existing one-day
settlement purge and unchanged 1,000-row train floor.

Both arms use identical rows and folds:

- Null: `[1, logit(home_oriented_market)]`.
- Candidate: null plus `margin / sqrt(game_seconds_remaining)`, the Stern
  (1994) state term. Its one fitted coefficient is the free sigma.

The as-of guard passed eight evenly spaced source-row probes:
`[2072, 4144, 6216, 8288, 10360, 12432, 14504, 16576]`.
The candidate source fields (`margin`, `period`, and `game_clock_s`) are
archived with each scored tick, so its action-derived as-of state is
reconstructible.

## Denominator and exclusions

| Named category | Ticks | Game clusters | Treatment |
| --- | ---: | ---: | --- |
| Full intersect in-play denominator | 186736 | 85 | Reported throughout; never filtered before accounting. |
| Outside PBP span | 167280 | 85 | Unjoined; no action-derived state. |
| In-span but not joined by backward 300-second rail | 806 | 85 | Unjoined; named separately. |
| Joined ticks below the existing floor or without prior purged training | 2079 | 10 | Unscored. By first date: 2026-05-31 241, 2026-06-02 685, 2026-06-03 667, 2026-06-04 486. |
| Scored ticks | 16571 | 75 | Both arms fitted and compared. |
| Unscored remainder of full denominator | 170165 | 85 | 167280 + 806 + 2079. |

There are 29 chronological candidate fold dates: 26 are fitted and 3 early
dates are UNFITTABLE at the unchanged train floor. The initial 2026-05-31
game date is also unscored because no earlier game exists. The floor was not
lowered and no window was widened.

## Calibration result

The scored denominator is 16,571 ticks over 75 game clusters. The paired-loss
ICC is 0.443996 and the corresponding game-cluster effective n is 167.97.
The market remains better calibrated by Brier and ECE than either fitted arm.

| Series | Brier | ECE |
| --- | ---: | ---: |
| Home-oriented market | 0.147718 | 0.039777 |
| Walk-forward null | 0.155244 | 0.084453 |
| Null plus Stern state term | 0.154859 | 0.086002 |

Candidate improvement over null is +0.000385 Brier. The game-clustered
Diebold-Mariano statistic is 1.288502, two-sided p is 0.201585, and the 95
percent CI is [-0.000210, +0.000980]. This is below +0.004 and its interval
includes zero, so the screen is NULL. It is not an AHEAD result.

### Reliability: market and null

| Bin | n | Market mean / observed | Null mean / observed |
| --- | ---: | --- | --- |
| 0.0-0.1 | 1564 / 2890 | 0.038935 / 0.040281 | 0.029678 / 0.118339 |
| 0.1-0.2 | 1154 / 948 | 0.152305 / 0.250433 | 0.144780 / 0.316456 |
| 0.2-0.3 | 1289 / 850 | 0.250093 / 0.227308 | 0.249645 / 0.303529 |
| 0.3-0.4 | 1176 / 802 | 0.349481 / 0.416667 | 0.351489 / 0.481297 |
| 0.4-0.5 | 1554 / 837 | 0.449344 / 0.502574 | 0.452321 / 0.540024 |
| 0.5-0.6 | 1673 / 899 | 0.551297 / 0.560072 | 0.550862 / 0.486096 |
| 0.6-0.7 | 1238 / 914 | 0.651139 / 0.737480 | 0.651120 / 0.539387 |
| 0.7-0.8 | 1408 / 991 | 0.752947 / 0.806818 | 0.756211 / 0.627649 |
| 0.8-0.9 | 1758 / 1211 | 0.844084 / 0.787827 | 0.848652 / 0.814203 |
| 0.9-1.0 | 3757 / 6229 | 0.965032 / 0.980037 | 0.982615 / 0.913951 |

### Reliability: market and candidate

| Bin | n | Market mean / observed | Candidate mean / observed |
| --- | ---: | --- | --- |
| 0.0-0.1 | 1564 / 2920 | 0.038935 / 0.040281 | 0.029624 / 0.117466 |
| 0.1-0.2 | 1154 / 959 | 0.152305 / 0.250433 | 0.145118 / 0.311783 |
| 0.2-0.3 | 1289 / 813 | 0.250093 / 0.227308 | 0.250031 / 0.323493 |
| 0.3-0.4 | 1176 / 783 | 0.349481 / 0.416667 | 0.348885 / 0.478927 |
| 0.4-0.5 | 1554 / 850 | 0.449344 / 0.502574 | 0.450502 / 0.543529 |
| 0.5-0.6 | 1673 / 855 | 0.551297 / 0.560072 | 0.548524 / 0.472515 |
| 0.6-0.7 | 1238 / 917 | 0.651139 / 0.737480 | 0.647751 / 0.531080 |
| 0.7-0.8 | 1408 / 1009 | 0.752947 / 0.806818 | 0.754381 / 0.627354 |
| 0.8-0.9 | 1758 / 1208 | 0.844084 / 0.787827 | 0.848240 / 0.812914 |
| 0.9-1.0 | 3757 / 6257 | 0.965032 / 0.980037 | 0.982320 / 0.914336 |

## Reproduction

Run from repository root:

    python -m scripts.platformkit.foundry.ingame_screen_wnba
    python -m pytest scripts/platformkit/foundry/test_s206_wnba_ingame.py -q

The final focused test result was `2 passed`. The CSV
`S206_wnba_ingame_first_score_2026-09-04_paired_loss.csv` has 16,571 rows and
SHA-256 `c8fe133a930379f02f3e9a3b008ba94c5b2b5871c1e8c45273ab92d49704c57f`.
It archives cluster id, timestamp, label, market, both fitted probabilities,
all three losses, paired delta, and the three as-of state fields. Recomputing
from that CSV alone reproduces all three Briers, all three ECEs, and the
game-clustered DM CI to less than 1e-12.

The machine-readable companion is
`S206_wnba_ingame_first_score_2026-09-04_summary.json`; it contains the
fold table, 10-bin reliability rows, denominator accounting, source hashes,
and the guard probes.

## Contract self-check

B1: all 186,736 in-play ticks remain named in the denominator, including
167,280 outside span, 806 in-span-unjoined, and 2,079 joined-unscored ticks.
B2-B6: additive module only; no schema rename, gate behavior, claim loop,
deployment, or moved module. B7-B9: no render or recycled unit; the metric is
tick-weighted and the CI clusters by 75 unique games. B10/Q3: `BAR` is the
unchanged 0.004 imported from `ingame_screen.py`. Q1-Q2 do not apply because a
screen is explicitly a non-finding and no prereg, charge, or K is used. Q4:
walk-forward folds are game-disjoint and purged. Q5 does not apply because the
result is NULL, not AHEAD. Q6: calibration language only. Q7: scored n is 75
game clusters. Q8: premise remeasured first. Q9: paired losses and reconstructible
as-of state are archived beside the summary.

## Not verified

- No second corpus was scored; none is needed for this NULL result.
- No continuous player or lineup state is claimed; the input is score/clock state.
- No conclusion is made for the 170,165 unscored ticks.
- No production behavior, deployment, or feature flag was changed.
