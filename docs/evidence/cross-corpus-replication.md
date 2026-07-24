# Cross-Corpus Replication -- one corpus is an anecdote, two is a finding

> The single truth-source for any figure is [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md).
> Every number on this page is copied verbatim from a committed artifact, cited inline. No
> $/edge/ROI claim appears here -- these are calibration/effect findings only, and an honest
> FAILED_REPLICATION is a success of the gate, not a shortfall.

---

## What replication means here

A finding that shows up once, on one slice of one corpus, is indistinguishable from a lucky
calendar window or an overfit grid search. The discipline in this repo is: **a hypothesis is
not "confirmed" until the same effect, at the same pre-declared bar, reproduces on a second
corpus that is independent of the one it was discovered on** -- a disjoint season, a disjoint
competition group, a disjoint tour, or a held-out reserve slice. The verdict taxonomy is
recorded in `scripts/platformkit/analytics_showcase/out/mechanism_survival.json`: only
`CONFIRMED_LOCAL`, `CONFIRMED_LOCAL_incl_2026_OOS`, and `REPLICATED` count as confirmed;
`FAILED_REPLICATION` and `ARTIFACT_CONFIRMED` are tested-not-confirmed. Single-fold positives
are kept in the ledger and labelled, never quietly dropped.

The strongest example is a **true bidirectional cross-corpus gate**: fit on corpus A, test on
held-out corpus B, then fit on B and test on A. A finding only replicates if it survives both
directions. Below are the receipts, verbatim.

---

## Replicated claims (both corpus results shown verbatim)

### Tennis pregame prior -- bidirectional ATP <-> WTA cross-corpus, verdict REPLICATED

Source: `data/frontend/ingame/gate_tennis.json`, surfaced in
`scripts/platformkit/analytics_showcase/out/tennis_showcase.json`
(`pregame_prior_cross_corpus`). Design: `true cross-corpus A<->B; DM clustered by game_id`.
Base model `sigmoid((a+b*frac_elapsed)*state_diff)` with `a,b` FIT per corpus (no basketball
constant). `vs_close: UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge`.

- **atp_train_wta_test**: n_train_states 14559, n_test_states 40516, brier_base 0.1698,
  brier_prior 0.1597, brier_delta 0.01005, dm_p 0.0, prior_beats_base true.
- **wta_train_atp_test**: n_train_states 40516, n_test_states 14559, brier_base 0.155,
  brier_prior 0.1432, brier_delta 0.01184, dm_p 0.0, prior_beats_base true.

The prior beats the (state,time) base in **both** directions -- fit on ATP tested on WTA, and
fit on WTA tested on ATP -- which is why the verdict is REPLICATED rather than
CONFIRMED_LOCAL. Coverage: a_games 29572 / a_states 40516, b_games 11016 / b_states 14559.
Caveat carried verbatim: DM clustered by game_id (per-state iid SE would over-state
significance); no in-play odds, so the verdict is calibration, never a market edge.

### MLB umpire strike-zone dispersion -- 2025 -> 2024 replication, verdict REPLICATED

Source: `domains/mlb/knowledge/validation_ledger.jsonl`. Discovered as CONFIRMED_LOCAL on 2025
(phi=1.389, n=2406); replicated on `savant_full__2024`: quasi-binomial dispersion ratio
phi=1.392 (chi2=3379.1, df=2427, p=1.36e-34) vs pure-noise phi=1.0, pooled called-strike rate
on taken borderline (zone 11-14) pitches=0.0634, n=2428 games.

### MLB "compassionate umpire" count-zone effect -- split-half replication, verdict REPLICATED

Source: `domains/mlb/knowledge/validation_ledger.jsonl`, corpus `savant_full__2024`,
split-half by date at the same 0.05/p<0.01 bar: h1 (p=9.87e-64, eff=-0.09924); h2
(p=1.10e-63, eff=-0.10264), n=50058.

### NBA fast-break / paint / assist persistence -- disjoint-season second corpus, verdict REPLICATED

Source: `domains/basketball_nba/knowledge/validation_ledger.jsonl`, corpus
`replication_wave1_second_corpus` = `espn_boxscores_2024_25.parquet` (1,235 games,
2024-10-22..2025-04-13, 0 event_id overlap with the original's `espn_boxscores.parquet`):

- fast_break_pts: split-half team persistence r=0.7033 p=1.46e-05 (n=30 teams); same-game
  margin relation r=0.2809 p=7.556e-46 (n=2460 team-games).
- paint_pts: persistence r=0.763 p=9.452e-07; margin r=0.248 p=8.311e-36 (n=2460).
- assists: persistence r=0.8386 p=7.24e-09; margin r=0.4164 p=9.34e-104 (n=2460).

### NBA timeout interrupts opponent run -- disjoint-season 2022-23, verdict REPLICATED

Source: `domains/basketball_nba/knowledge/validation_ledger.jsonl`. 2022-23 season (1230 local
pbp games, fully disjoint from the original's 2023-24-dominant pool); original bar ALPHA=0.01
MIN_EFFECT=0.3 MIN_GROUP_N=20 unchanged. Split-half by date: h1 (p=6.27e-58, eff=-0.6917); h2
(p=1.84e-48, eff=-0.6564).

### NBA largest-lead persistence -- 3-season pooled, CONFIRMED_LOCAL -> REPLICATED

Source: same ledger, corpus `espn_boxscores_3season_pooled_2023_24_thru_2026`: persist seasons
r=[0.7790, 0.6967, 0.8021] Fisher p=6.758e-16, pooled r=0.4587 CI95[0.1179,0.7028] PASS;
margin seasons r=[0.8447, 0.8130, 0.8138] Fisher p=0, pooled r=0.8210 CI95[0.8128,0.8289]
PASS. Label transition recorded verbatim: `old(CONFIRMED_LOCAL, 1 corpus)->new(REPLICATED)`.

### Soccer xG-supremacy persistence -- disjoint competition groups, verdict REPLICATED

Source: `domains/soccer/knowledge/validation_ledger.jsonl`, corpus `disjoint_competition_group`
(25,834-match corpus, >=10 games/half): English pyramid (div E0/E1) split-half r=0.8469 p=1.74e-14
(n=49 teams); continental top-4 (D1/F1/I1/SP1) r=0.9495 p=1.45e-46 (n=91 teams). Two disjoint
competition groups, same effect.

---

## Claims that FAILED replication (single-fold artifacts, honestly buried)

These looked positive on discovery and are kept in the ledgers with their failure verdict so
the record cannot be cherry-picked. This is the point of the discipline, not an embarrassment.

- **MLB meta-label divergence bucket table** (`domains/mlb/knowledge/validation_ledger.jsonl`).
  A flagged n=186 table where every quartile read >50% CLV-positive. On the independent
  no-selection corpus `ingame_grade_joined_mlb_synthetic_checkpoints_disjoint`, no quartile
  replicates: Q1 9/20 (p=0.824), Q2 6/19 (p=0.167), Q3 6/19 (p=0.167), Q4 6/18 (p=0.238) --
  all at or below coin. Family verdict `ARTIFACT_CONFIRMED`: "the positivity is an
  ORDER-SELECTION artifact of the paper flow, not a divergence-magnitude meta-signal. Do not
  weight orders by these buckets."

- **NBA shot-interaction candidates** (`data/cache/intel_claims/interaction_factory_ledger.jsonl`).
  Several batch1 offense-x-offense/state interactions that were significant on the discovery
  season sign-shrank on `player_offense_events_2024_25`:
  `halfcourt_efg x transition_efg` (batch1 effect 0.005768 p=1.5e-04 -> repl effect 0.002508
  p=0.166), `late_clock_efg x transition_efg` (batch1 0.006646 p=6.8e-04 -> repl 0.001456
  p=0.442), `late_clock_efg x zone_efg_paint` (batch1 0.007788 p=2.4e-05 -> repl 0.001363
  p=0.460). Verdict `FAILED_REPLICATION_POWER_ANNOTATED`. Only two of the batch survived:
  `halfcourt_efg x late_clock_efg` (repl effect 0.00427 p=0.007, n=16627) and
  `halfcourt_efg x zone_efg_rim` (repl effect 0.00501 p=0.001, n=15437), verdict REPLICATED.

- **Tennis as-of interaction candidates** (same interaction ledger). Discovery-significant
  effects that collapsed on the disjoint 2026 ESPN-bridge corpus:
  `diff_2nd_win_asof x diff_ace_rate_asof` (discovery effect -0.037785 p=0.003948 n=29179 ->
  repl effect -0.007503 p=0.916 n=647); the wave-22 knowledge-sourced
  `avg_games_per_set_asof_diff x diff_break_pct_asof` (discovery -0.047896 p=0 -> repl -0.024763
  p=0.539); reserve-slice `days_since_last_match_diff x diff_break_pct_asof` (discovery 0.05768
  p=1.76e-04 -> repl 0.012451 p=0.677). All `FAILED_REPLICATION_POWER_ANNOTATED`.

- **Soccer substitution-timing moderation** (`domains/soccer/knowledge/validation_ledger.jsonl`).
  On the big-4 2015-16 disjoint group the effect vanished: effect 0.01861 p=0.152 (n=1691),
  verdict FAILED_REPLICATION -- one competition group replicating (p=6.1e-06 elsewhere) is not
  enough when a genuinely independent group nulls out.

---

## The discipline rule: two corpora or it is an artifact

The self-audit scoreboards keep the honest denominator. `honesty_exhibit.json` headline:
"nulls (351) outnumber confirms (168) 2.1x -- we publish our nulls". The evidence packet
(`docs/JOB_EVIDENCE_PACKET.md`) records the rule directly: every candidate signal was
**rejected across >=2 independent corpora, including signals that looked positive full-sample
then reversed sign out-of-sample** -- the overfit signature -- and the multi-corpus calibration
acceptance gate (`scripts/validate_calibration_multicorpus.py`) ships a recalibration only if
it beats raw on >=2 independent OOS corpora.

The rule in one line: **a single-fold positive is a hypothesis, not a result. Two independent
corpora at the pre-declared bar, or it stays an artifact and gets labelled as one.**

---
**Sources (all committed):** `data/frontend/ingame/gate_tennis.json` ·
`scripts/platformkit/analytics_showcase/out/tennis_showcase.json` ·
`domains/{basketball_nba,mlb,soccer,tennis}/knowledge/validation_ledger.jsonl` ·
`data/cache/intel_claims/interaction_factory_ledger.jsonl` ·
`scripts/platformkit/analytics_showcase/out/{mechanism_survival,honesty_exhibit}.json` ·
[docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md)
