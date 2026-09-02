# S58 in-game trial B -- NBA halftime checkpoint on the AS-OF Elo prior vs the Polymarket in-play price (2026-09-03)

## VERDICT: BEHIND (replicated on 0 of 2 corpus_units) -- valid, expected; S63 is now a measured, reconstructible number

The four preregistered AHEAD conditions on the pooled 1,593 halftime checkpoints (one per
game; the LAST traded tick with elapsed <= 24.0; 2024-10-22..2026-06-13):

| condition | bar | measured | pass |
|---|---|---|---|
| (1) paired Brier improvement (market - model) | >= 0.004 | **-0.006583359358100532** (model 0.17136012175609178 vs market 0.16477676239799124) | FAIL |
| (2) DM 95 pct CI of d (d > 0 = model better), cluster = game, lower bound > 0 | > 0 | **[-0.011503050350979545, -0.0016636683652215658]**, DM stat -2.6248, 1,593 clusters -- excludes 0 in the WRONG direction | FAIL |
| (3) deflated_p(raw p, K at launch) < 0.05 | < 0.05 | raw p 0.008754206657702974, **deflated_p 0.148822 at K = 17** | FAIL |
| (4) family bar (family of one, fdr_bh; fdr_by printed) | q = 0.05 | bh_adj_p 0.00875421 | pass (direction-blind) |

BEHIND per the prereg rule: Brier(model) > Brier(market) pooled. Replication (Q5 / S08):
n_corpora = 0 (neither unit has improvement >= 0.004 with DM lower bound > 0);
`replication_fields` -> verdict_replicated BEHIND, min_corpora_eff(0 -> 1, K=17) = 2.

| corpus_unit | n | model | market | neutral_0.5 | p0_only | improvement | DM CI 95 | raw p |
|---|---|---|---|---|---|---|---|---|
| 2024-25 | 656 | 0.177839 | 0.166264 | 0.183874 | 0.225342 | -0.011575 | [-0.019090, -0.004060] | 0.00259 |
| 2025-26 | 937 | 0.166824 | 0.163736 | 0.175203 | 0.220877 | -0.003089 | [-0.009593, 0.003415] | 0.352 |

The bars line, verbatim (direction-blind; the verdict is the prereg's rule, which fails
(1), (2) and (3)):

    verdict=NOT AHEAD blocked_by=global raw_p=0.00875421 | GLOBAL k=17 deflated_p=0.148822 alpha=0.05 pass=False | FAMILY - q=0.05 n=1 bh_adj_p=0.00875421 pass=True | rule=fdr_bh fdr_bh_adj_p=0.00875421 pass=True fdr_by_adj_p=0.00875421 pass=True | spec=s14-families-v1@62702554f6e5

## Seal and charge (Q1 / Q2)

- Prereg docs/evidence/harness/S58_TRIALB_PREREG_2026-09-03.md committed ALONE first
  (a6f5e614f); SHA-256 5dbdff4299ccdc29672d65fb9b6495b3981f35a4c9b7e65a909091e496b30ecc
  (git blob 280ac1fc57f673071e2bcbceaa4550105ce9b4fd) pinned as PREREG_SHA256 in the
  module, verified by run_trial before the charge, embedded in the trial JSON, the per-game
  CSV header and the ledger row.
- Charge: ledger 16 -> 17 rows exactly once (md5 acd5199f2a2780bcdbd005eb5bef8491 ->
  303a7d82cf525d338e258ef565c71d02). Row: {"at": "2026-09-02T17:02:10.816363+00:00",
  "predictor": "scripts.platformkit.eval_gate.s58_nba_halftime_asof_trial:nba_halftime_asof_v1",
  "sport": "nba", "start": "2024-10-22", "end": "2026-06-13", "k_cumulative": 17, "family":
  "ingame_nba_halftime_asof", "k_family": 1, "tier": "T2", "hypothesis_hash": "621615aa...",
  "prereg_sha256": "5dbdff42..."}. K = 17 read from the row at launch is the only K used;
  global bar raw p < 0.05/17 = 0.002941 as preregistered. Serial slot: row 16 is trial A's
  charge (this lane), no other charge between the two.

## What was measured (calibration language only)

- The as-of Elo prior + realised halftime margin (pure repricer, nothing fit on outcomes)
  trails the halftime Polymarket price by 0.0066 Brier pooled, significantly in 2024-25
  (-0.0116, CI excludes 0) and not separably in 2025-26 (-0.0031, CI includes 0).
- Calibration (10 equal-count bins): ECE model 0.054303 vs market 0.017047 -- the model is
  the less calibrated of the two at halftime; premature confidence: the model put > 0.8 on
  the eventual loser in 11.39 pct of lost games vs the market's 5.63 pct (S43's tail
  diagnostic reproduced on a second sport).
- The old artifact's -0.0040 (run-time Elo, per-game deltas never archived) is NOT
  reproduced: the honest as-of number is -0.0066 with a CI that excludes 0. The run-time
  state was the more flattering one, which is the direction a leaked prior is expected to
  move a score.
- Descriptive references: neutral_0.5 0.178774 (state only, no prior) and p0_only 0.222716
  (prior only, no state) pooled; PBO over [model, neutral_0.5, p0_only] 0.0 (n_obs 1,593,
  1,000 splits).
- prior_stale sub-slice (78 games dated after games.parquet's 2026-04-12 end, 2026
  playoffs): model 0.190893 vs market 0.197692, improvement +0.006799, DM CI [-0.017365,
  0.030964] -- n = 78, not separable, descriptive only, never excluded from the pooled set.

## Path used and why

NOT tiers.run_tier (pregame states, one prediction per event); the charge goes through
`_charge_ledger` with the S13 fields and `dual_bar_verdict` by hand, as in S58 trials 1 and
A. Family `ingame_nba_halftime_asof` is NOT in the frozen FWER_FAMILIES_SPEC (62702554f):
family of one, labelled; through tiers it would be NOT_IN_FROZEN_FAMILIES and uncharged.

## Denominator accounting (non-tautology)

Corpus 465,249 traded rows / 1,593 games; every game reaches elapsed 24.0 (min checkpoint
elapsed 23.0067), so 1,593/1,593 games are scored -- 0 dropped, 0 excluded. Team codes:
PHO -> PHX, WSH -> WAS aliased; every other ticker code matches games.parquet. Counts
(1,593 / 656 / 937) asserted BEFORE the charge. The replay `until` equals the game_date on
every row (asserted after pricing).

## Files, tests

- scripts/platformkit/eval_gate/s58_nba_halftime_asof_trial.py (new, 165 LOC; reuses
  price_checkpoint / _elapsed_minutes, ratings.replay + _p_home, _charge_ledger,
  dual_bar_verdict, replication_fields, cscv_pbo, diebold_mariano). Per-file test
  tests/platformkit/eval_gate/test_s58_nba_halftime_asof_trial.py: 3 passed (checkpoint
  never past the anchor + aliases; replay until == game_date and stale flag; seal-before-
  charge on a tmp ledger, K from the row, per-game CSV reproduces the pooled Brier).
- Artifacts (gitignored, local): data/cache/eval_gate/s58_trialB_nba_halftime_asof_2026-09-03.json
  and s58_trialB_nba_halftime_asof_pergame_2026-09-03.csv (1,593 rows; header line carries
  the seal and K; columns game_id, game_date, unit, home, away, elapsed, score_home,
  score_away, elo_until_date, prior_stale, p0_asof, model, neutral_0.5, market, y,
  loss_model, loss_market, d) -- the verifier recomputes both Briers, the DM CI and
  deflated_p(p, 17) from the CSV alone (Q9 satisfied; the model side is reconstructible from
  games.parquet + the archived elo_until_date).

## NOT VERIFIED

- No CPCV / walk_forward fold was run: the trial fits nothing, so Q4's fold machinery has
  no parameter to protect; the leak contract is the strictly-before-date replay and the
  checkpoint rule, both asserted. A verifier who wants the fold form anyway files a gap.
- The repricer constants (margin sigma 13.5, mu 113) were set on other data and not
  re-derived here; a per-season as-of sigma would be a different (uncharged) hypothesis.
- games.parquet ends 2026-04-12; the 78 playoff checkpoints use a stale prior (flagged).
- Polymarket in-play prices are traded quotes, not devigged closes; no vig treatment was
  applied to market_prob (the corpus carries one number per tick).
