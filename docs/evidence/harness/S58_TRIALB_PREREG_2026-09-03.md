# S58 in-game trial B prereg (sealed 2026-09-03) -- NBA halftime checkpoint on the AS-OF Elo prior (S63, reconstructible version)

Sealed BEFORE any metric: this file is committed ALONE, its SHA-256 is pinned as
`PREREG_SHA256` in `scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py`, verified
by `run_trial` before the ledger charge, and embedded in the trial JSON, the per-game CSV
header and the memo (Q1). The charge -- `_charge_ledger(data/cache/eval_gate/backtest_fwer.jsonl,
"scripts.platformkit.eval_gate.s58_nba_halftime_asof_trial:nba_halftime_asof_v1", "nba",
"2024-10-22", "2026-06-13", family="ingame_nba_halftime_asof", tier="T2",
prereg_sha256=<seal>)` -- is the first statement after the seal check and the appended row's
`k_cumulative` is the only K used anywhere (Q2). The ledger holds 16 rows at sealing (md5
acd5199f2a2780bcdbd005eb5bef8491; row 16 is trial A's charge, serial slot held by this lane);
this charge appends row 17, so launch K = 17 and the global bar is raw DM p < 0.05/17 =
0.002941 (deflated_p(raw_p, 17) < 0.05). ONE charge; ONE model variant.

## Why this is the top-ranked remaining hypothesis (stated before looking)

S58 trial 2 found the NBA halftime artifact (n 1,593, CI [-0.009833, 0.001536], the
closest-to-resolving in-game row) NOT RECONSTRUCTIBLE: its model used the Elo state at run
time and its per-game deltas were never archived (S63 / Q9). The reconstructible version is
cheap on disk today: the checkpoint corpus is present, `ratings.replay(games, until=date)` is
strictly-before-date (0.1 s per date), and `nba_checkpoint_benchmark.price_checkpoint` is a
PURE function of (p0, score, period, clock) with no fitted parameter. Information the market
anchor may lack at halftime: Polymarket in-play liquidity is thin and the halftime price is a
traded quote, not a devigged close; a rating prior conditioned on the realised margin is a
principled forecaster. Expected outcome: BEHIND or NULL (the run-time model trailed the market
by 0.004 in the old artifact). Either is a valid result; it also gives the first NBA in-game
verdict with two corpus_units (Q5).

## Corpus (STEP 0 counts, measured 2026-09-03 before sealing; no Brier computed)

`data/cache/inplay_odds/nba_checkpoints_full.parquet`: 465,249 rows / 1,593 games,
game_date 2024-10-22..2026-06-13, venue polymarket, traded=True on every row.
Halftime checkpoint = `crps_market.ingame_nba_winprob.checkpoint_row` rule: the LAST tick of
the game with `_elapsed_minutes(period, game_clock_s) <= 24.0` (never a later tick):
**1,593 checkpoints / 1,593 games** (elapsed min 23.0067, median 24.0, max 24.0).
corpus_units by game_date: **2024-25 = game_date < 2025-08-01: 656 games; 2025-26: 937**.
Teams from `market_ticker` "nba-{away}-{home}-{date}" upper-cased; aliases PHO -> PHX,
WSH -> WAS (the two ticker codes absent from games.parquet; every other code matches).
`main` asserts (1,593, 656, 937) BEFORE the charge; any drift stops the trial uncharged.

## Model (K = 1; nothing fit on outcomes)

p0 = the as-of Elo prior exactly as `domains/basketball_nba/adapter.py:121
baseline_probability`: `state = ratings.replay(games.parquet with season mapped by
_season_to_int, until=game_date)` (games strictly BEFORE the game's date), `p0 =
_p_home(state.elo.get(home, ELO_MEAN), state.elo.get(away, ELO_MEAN))`. The replay is run
once per distinct game_date (deterministic; identical to a per-game call). games.parquet:
4,846 games 2022-10-18..2026-04-12, so the 78 checkpoints dated after 2026-04-12 (2026
playoffs) use the Elo state as of the end of games.parquet -- STALE but leak-free; flagged
`prior_stale` per game and reported as a descriptive sub-slice, never excluded.
model = `price_checkpoint(p0, score_home, score_away, period, game_clock_s)` with the
module's `_DEF_MARGIN_SIGMA` 13.5 and `_DEF_MU` 113 (constants, not tuned here).
Descriptive, uncharged references beside it: `neutral_0.5` (= price_checkpoint(0.5, ...),
the benchmark's existing variant) and `p0_only` (the prior with no state).
Q4: no meta-learner and no fitted parameter exists in this trial, so no CPCV/walk-forward
fold is run; the leak contract is the strictly-before-date Elo replay plus the
checkpoint-row rule, both asserted in code (every replay `until` == game_date; every
checkpoint elapsed <= 24.0).

## Incumbent

`market_prob` on the SAME checkpoint tick (the Polymarket in-play home-win price).

## Verdict rule (frozen; no bar moves, Q3)

Let d = loss(market) - loss(model) per game (d > 0 = model better); one row per game, so
the cluster is the game. AHEAD iff ALL FOUR on the pooled 1,593:
  (1) paired Brier improvement = Brier(market) - Brier(model) >= 0.004;
  (2) Diebold-Mariano 95 pct CI of d (cluster = game) excludes 0 with lower bound > 0;
  (3) deflated_p(raw DM p, K read at launch) < 0.05;
  (4) the family bar: `dual_bar_verdict(raw_p, K, [raw_p], q=0.05, family=None)` -- a
      FAMILY OF ONE (ingame_nba_halftime_asof is NOT in the frozen FWER_FAMILIES_SPEC
      62702554f; labelled NOT FROZEN; through tiers it would be NOT_IN_FROZEN_FAMILIES).
Replication (Q5, S08 gate): n_corpora = the number of corpus_units (2024-25, 2025-26) on
which BOTH per-unit improvement >= 0.004 AND per-unit DM CI lower bound > 0; the pooled
verdict passes through `replication_gate.replication_fields(verdict, n_corpora, K)` and the
downgraded `verdict_replicated` is the verdict of record (an AHEAD that replicates on fewer
than min_corpora_eff units is SINGLE-WINDOW).
Else BEHIND iff Brier(model) > Brier(market) pooled; else NULL.

## Reported beside the verdict (always)

Per-unit table (n, Brier model / market / neutral_0.5 / p0_only, improvement, DM CI, raw p);
the prior_stale sub-slice (78) descriptively; PBO via cscv_pbo over [model, neutral_0.5,
p0_only] (descriptive); ECE (10 equal-count bins) of model and market; both bars'
`render_bars` line quoted verbatim (direction-blind); the per-game CSV (Q9: game_id,
game_date, unit, home, away, elapsed, score_home, score_away, elo_until_date, prior_stale,
p0_asof, model, neutral_0.5, market, y, loss_model, loss_market, d).

## Leak risks named

- Checkpoint selection: last tick <= 24.0 elapsed, never later (asserted).
- Prior vintage: replay(until=game_date) excludes the game's own date and everything after;
  the 78 stale-prior games are flagged, not dropped.
- Ticker parse: away/home order is "nba-{away}-{home}"; a swapped parse would invert p0 --
  guarded by asserting that the corpus outcome column is `outcome_home_win` and by the
  descriptive p0_only Brier (a swapped prior would score far worse than 0.25).
- Repricer constants (13.5 / 113) come from the module and were set on other data; they are
  not tuned here and not moved.

Artifacts: data/cache/eval_gate/s58_trialB_nba_halftime_asof_2026-09-03.json (+ _pergame
CSV), memo docs/evidence/harness/S58_trialB_nba_halftime_asof_2026-09-03.md.
Must not move: BAR 0.004, ALPHA 0.05, q 0.05, anchor 24.0, unit boundary 2025-08-01,
_DEF_MARGIN_SIGMA 13.5, _DEF_MU 113, the aliases, deflated_p, min_corpora_eff,
replication_verdict, cscv_pbo, diebold_mariano, every threshold under
scripts/platformkit/eval_gate/, the ledger except the one appended row, data/registry/**
(never written). Calibration language only.
