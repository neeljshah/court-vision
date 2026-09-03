# S119 -- MLB in-game supply: the unsupplied members, and S82 re-quoted on real games

Date: 2026-09-03 | Area: signals-ingame | Verdict: **PREMISE-STOP (supply absent on the screen
side, 1 of 5 members) + SCREEN_NULL re-quoted on the corrected 88 real-game clusters**
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in section 6).
Calibration language only (Q6). Uncharged: no prereg sealed, K never read, ledger never opened.

---

## 0. STEP 0 PREMISE (Q8) -- re-measured first, and it FIRES THE ROW'S OWN STOP RULE

The S119 row asks for tick-time builders for the members S82 reported NOT_SUPPLIED and a re-run
of the tier with them. **The supply does not exist on the SCREEN side.** Every number below is
measured at HEAD by `ingame_supply_mlb.supply_probe()`, which reads the real files at call time;
it is reproduced in the artifact's `supply_probe` block.

### 0a. The 7 members S82 named NOT_SUPPLIED, what each needs, and whether it can be served now

| # | member (S82 `NOT_SUPPLIED`) | what it needs at tick time | source that could serve it | join key | suppliable on the SCREEN side |
|---|---|---|---|---|---|
| 1 | `pitch_velocity` | per-pitch Statcast velo at the tick | no pitch-grain feed is joined to the Kalshi tick store | - | **NO** (no source) |
| 2 | `pitch_loc_x` | per-pitch plate location | same | - | **NO** (no source) |
| 3 | `pitch_loc_y` | per-pitch plate location | same | - | **NO** (no source) |
| 4 | `velo_decline_vs_early` | within-game velo trend | same | - | **NO** (no source) |
| 5 | `atbat_pitch_number` | pitch number within the at-bat | store carries `mlb_pitcher_pitch_count` (game cumulative), never the at-bat number | (game_id, ts) | **NO** (wrong grain) |
| 6 | `p0` | the pregame prior | already inside `model_prob`; adding it is the degenerate hypothesis `score_diff` already demonstrates | - | **NO** (by construction) |
| 7 | `outcome` | the label | never a feature | - | **NO** (by construction) |

### 0b. The 5 members the S119 row names, per member, with the source and the join key

| member | source named | join key | measured | suppliable on the SCREEN side |
|---|---|---|---|---|
| starter TTO from the REAL pitcher id + batters faced so far | tick `mlb_pitcher_id` (S83) + the tick stream strictly before | `(game_id, ts)` | `mlb_pitcher_id` is non-null on **8,287 of 78,986** joined ticks, over **53 game_ids**; every one of those ticks is dated **2026-07-09..07-12** and every one of the 53 game_ids has game-first-date **2026-07-08..07-12** -- **ISO week 28 for 53 of 53**, i.e. the S82 **VERDICT** side (screen = 2026-W27). The raw store agrees: 8,384 identity ticks over 56 game_ids on 07-09, 07-10, 07-11, 07-12, 07-19, 07-27 -- **nothing earlier** | **NO** -- zero identity ticks on the screen side, and the only corpus that carries them is the side this lane must never read |
| bullpen availability as-of (relievers used in the prior 2 days) | `data/domains/mlb/bullpen_relief_chains.parquet` (`game_pk, player_id, team, date, battersFaced, rest_days, is_b2b, appearances_last_3d`); the `prior` rule of `foundry/asof_supply.py` already declares this family | `(team, date)` strictly before the game date, MLB abbreviations through `asof_supply.MLB_ALIAS` | 71,523 rows, **last date 2026-07-02, and that day holds 8 rows over 2 teams**. The S82 screen's scored fold dates are **07-03, 07-04, 07-05**. Prior-2-days is therefore computable only for 07-03 games and even then off a near-empty 07-02; 07-04 and 07-05 have no source at all | **NO** -- censored by the source's end date, not missing at random |
| batter platoon vs pitcher hand as-of | tick `mlb_batter_id` + a pitcher-hand column (`probables.home_sp_hand` / `away_sp_hand`), then `platoon_split_index.parquet` (394 batters) | `(batter_id, pitcher hand)` | **doubly absent**: batter id has the same W28-only coverage as pitcher id (8,287 ticks), AND `home_sp_hand` / `away_sp_hand` are **0 non-null of 459 rows** over 2026-06-20..07-15. The only other hand columns in the domain (`postmortem.parquet`) cover 2010-2021 and have **0 rows** in the window | **NO** |
| catcher (pregame as-of) | the row names `probables.parquet` | - | `probables.parquet` has **19 columns and no catcher column** (`has_catcher_column: false`). The only catcher table is `catcher_framing_index.parquet` (113 rows: `catcher_id`, `ooz_strike_rate`) -- a SKILL index with no per-game assignment. `player_gamelogs.parquet` carries `position` but ends 2026-07-02 and is same-game knowledge anyway | **NO** -- no assignment source exists |
| umpire (pregame as-of) | `probables.hp_umpire_id` -> `umpire_zone_index.parquet.ooz_strike_rate` (102 umpires, 2022_2023 corpus) | `(game_date, team pair)` -> `game_pk` -> `hp_umpire_id` -> `umpire_id` | `hp_umpire_id` is non-null on **317 of 459** window rows and present on **every date 06-20..07-12** (316 games in window). `umpire_assignments.parquet` exists but its `game_date` span is 2026-07-09..07-16, verdict-side only -- probables is the screen-side source | **YES** |

**Count: 1 of 5 suppliable. The row's own rule is "if < 3 members are suppliable, STOP after the
premise."** It fires. **No `ingame_supply_mlb` as-of builder was written and the S82 tier was NOT
re-run with new members** -- screening the umpire alone would be one member, not the tier the row
specifies, and inventing proxies for the other four would be a bar moved by another name.

Premise verdict: **CONFIRMED for the mislabelled-clusters half, FALSIFIED for the supply half.**
The row assumes the S83 identity columns make these members screenable; measured, they make them
screenable only on the VERDICT side.

---

## 1. What IS delivered: the row's other half, from the archive alone

S82's intervals were quoted against `game_id`, and `game_id` is a Kalshi ticker that parks several
nights under one key (S105/S106). The S82 screen side's **41 game_ids are 88 REAL games** -- exactly
the "expect NULL at 88 clusters" the row predicted.

`requote` recomputes every S82 interval from the **archived per-tick paired losses** (Q9,
`s82_ingame_screen_series_2026-09-03.csv`, 219,828 rows) on the corrected cluster
`(game_id, real_game_seq)`. Nothing is refitted: `p_null` and `p_candidate` are the archived
walk-forward predictions, no row is added or dropped, so the point estimates are identical by
construction and only the interval moves. This is a re-quote of a non-finding, not a new screen.

**A2 reproduction.** Re-clustering by `game_id` reproduces S82's published table from the archive:
max |improvement difference| over the 14 features = **2.8e-17**, max |CI bound difference| =
**1.4e-17**, and `brier_e4` / `brier_null_recal` / `brier_candidate` / `brier_market` agree to
1e-12 on all 14. The split itself reproduces S106: **227 game_ids -> 392 real games**, 122 multi,
22,768 ticks reassigned, boundaries `inning_decrease` 156, `score_reset` 6, `ts_gap` 3.

---

## 2. Ranked table -- MLB, S82 SCREEN side, n = 15,702 ticks, 41 game_ids = 88 real games

`improvement_vs_null` is the gain over the SAME walk-forward fit without the feature term (the
arms differ only by the feature). Bar **+0.004, frozen, not moved (Q3/B10)**.

| rank | feature | improvement vs null | CI95 by game_id (41) | half | **CI95 by real game (88)** | **half** | half ratio | n_informative | n_eff |
|---|---|---|---|---|---|---|---|---|---|
| 1 | tick_index_in_game | +0.003332 | [-0.001971, +0.008636] | 0.005304 | [-0.003705, +0.010370] | **0.007038** | 1.327 | 15,528 | 120.7 |
| 2 | leverage_proxy | +0.001148 | [-0.000106, +0.002403] | 0.001255 | [-0.000219, +0.002515] | 0.001367 | 1.090 | 5,367 | 388.3 |
| 3 | times_through_order | +0.001063 | [-0.000770, +0.002897] | 0.001834 | [-0.000728, +0.002854] | 0.001791 | 0.977 | 7,606 | 1,849.9 |
| 4 | pitch_tempo_seconds | +0.000651 | [-0.001025, +0.002327] | 0.001676 | [-0.000612, +0.001914] | 0.001263 | 0.754 | 9,531 | 419.1 |
| 5 | pitch_count | +0.000612 | [-0.000550, +0.001773] | 0.001161 | [-0.000565, +0.001789] | 0.001177 | 1.013 | 12,329 | 1,857.1 |
| 6 | balls | +0.000203 | [-0.000218, +0.000624] | 0.000421 | [-0.000238, +0.000645] | 0.000441 | 1.048 | 8,219 | 1,204.4 |
| 7 | strikes | +0.000005 | [-0.000228, +0.000238] | 0.000233 | [-0.000244, +0.000253] | 0.000248 | 1.065 | 8,373 | 2,026.9 |
| 8 | outs | -0.000010 | [-0.000251, +0.000231] | 0.000241 | [-0.000322, +0.000301] | 0.000311 | 1.291 | 6,049 | 4,240.6 |
| 9 | score_change_recency | -0.000241 | [-0.000540, +0.000058] | 0.000299 | [-0.000518, +0.000037] | 0.000278 | 0.929 | 15,557 | 280.1 |
| 10 | inning_progress | -0.000268 | [-0.001334, +0.000798] | 0.001066 | [-0.001385, +0.000848] | 0.001116 | 1.047 | 5,408 | 456.7 |
| 11 | base_out_state | -0.000315 | [-0.000977, +0.000348] | 0.000662 | [-0.001109, +0.000479] | 0.000794 | 1.199 | 6,867 | 1,616.9 |
| 12 | run_expectancy | -0.000438 | [-0.001269, +0.000392] | 0.000831 | [-0.001304, +0.000427] | 0.000866 | 1.042 | 6,871 | 1,536.9 |
| 13 | base_state | -0.000479 | [-0.001229, +0.000272] | 0.000750 | [-0.001335, +0.000377] | 0.000856 | 1.141 | 5,482 | 846.9 |
| 14 | score_diff | -0.018007 | [-0.039827, +0.003814] | 0.021820 | [-0.038664, +0.002650] | 0.020657 | 0.947 | 4,261 | 144.3 |

**Clearing the +0.004 bar on the corrected clusters: 0 of 14.** No CI's lower end is above zero
either. Brier anchors are unchanged from S82 (same rows): `e4` 0.208211, `market` 0.195704.

**The half-width the row asks for.** On the corrected 88 real-game clusters the achieved 95 pct
half-width is **0.007038 for the leader** (`tick_index_in_game`) and **0.000991 at the median** of
the 14 features (game_id median 0.000948). **10 of 14 widened, 4 narrowed** -- splitting a ticker
raises the cluster count but also concentrates the within-cluster correlation, so the correction is
not uniformly a widening; it is a re-quote against the honest unit, in both directions.

`n_informative` (S87) is per feature because the informativeness test asks whether the market OR
that feature's own candidate probability moved; 15,528 of 15,702 for `tick_index_in_game` down to
4,261 for `score_diff`. The informative-only CIs are in the artifact and carry the same sign in all
14; `score_diff`'s is the only interval that excludes zero, on the NEGATIVE side
([-0.014809, -0.002261]) -- the degenerate sanity anchor stays detectable.

**Power at this cluster count.** Holding each point estimate and dispersion fixed, the leader's CI
would exclude zero at about **393 scored real games**; `times_through_order` at about 250 and
`leverage_proxy` at about 125. The whole joined store holds **392 real games** in total, of which
88 are scored on this screen side.

---

## 3. A correction the corrected clusters expose: the S82 screen side is not calendar-clean

Splitting the tickers shows **495 of the 15,702 scored screen ticks (3.2 pct) are dated 2026-07-06
and 07-07** -- ISO week 28 -- pulled onto the "2026-W27" screen side by their parent ticker's first
date. No verdict-side `game_id` was read (the partition is by game_id membership and that is
unchanged), but the screen window is not the calendar week it is quoted as.

Sensitivity, ticks dated <= 2026-07-05 only (**n = 15,207, 85 real games**), same archive:

| feature | improvement vs null | CI95 by real game | half |
|---|---|---|---|
| tick_index_in_game | **+0.001628** (was +0.003332) | [-0.004828, +0.008084] | 0.006456 |
| leverage_proxy | +0.001220 | [-0.000188, +0.002627] | 0.001407 |
| times_through_order | +0.001080 | [-0.000763, +0.002923] | 0.001843 |
| pitch_tempo_seconds | +0.000688 | [-0.000616, +0.001992] | 0.001304 |
| pitch_count | +0.000661 | [-0.000547, +0.001869] | 0.001208 |

**0 of 14 clear the bar here either.** The S82 leader loses **half its point estimate** (+0.003332
-> +0.001628) when 3.2 pct of ticks are removed; a ranking that fragile on 495 of 15,702 rows was
never a signal, and this is stated as a weakness of the S82 leader, not as a new result.

---

## 4. Honest verdict

**No prereg DRAFT is written.** The row conditions a draft on a feature clearing +0.004 vs the line
with a CI excluding zero and beating the null. Nothing clears it on the corrected clusters, on the
calendar-clean subset, or on the informative subset. Every feature also remains behind the in-play
market line (market 0.195704 vs null 0.201671); matching the line within noise is the honest
description and nothing here does better.

Two things the row asked that are now answered:
1. **The unsupplied members are not a screening gap, they are a corpus gap** -- the identity that
   would supply them exists only on the verdict side, and the hand/catcher columns do not exist at
   all. This does not close by writing a builder; it closes by capturing identity on more dates.
2. **The mislabelled clusters did not change any verdict** -- 41 game_ids are 88 real games, the
   point estimates are untouched, the intervals move in both directions, and the tier stays NULL.

---

## 5. Artifacts and reproduction

- Code: `scripts/platformkit/foundry/ingame_supply_mlb.py` (254 LOC). Imports `ingame_screen` /
  `asof_supply` nothing -- it reuses `eval_gate/real_game_split.assign_real_game_seq` (S106),
  `eval_gate/dm_test.diebold_mariano` and `eval_gate/tick_informative.attach_informative_summary`
  (S87). No file owned by another lane was touched.
- Run: `python -m scripts.platformkit.foundry.ingame_supply_mlb`
- Summary: `data/cache/eval_gate/s119_real_game_requote_2026-09-03.json` -- the supply probe, the
  split summary, both CI families per feature, the informative block, the calendar-clean block.
- **Q9 differential**: `data/cache/eval_gate/s119_real_game_series_2026-09-03.csv` (33,377,586
  bytes; 219,828 rows) = the S82 archive plus `real_game_seq`, so every interval above recomputes
  from that CSV alone.
- Test: `python -m pytest tests/platformkit/foundry/test_ingame_supply_mlb.py -q` = **4 passed in
  0.53s** -- one ticker holding two nights splits into two real games; the re-quote leaves the
  point estimate identical to 1e-12 while producing an interval the single-game_id clustering
  cannot (`ci95` None at 1 cluster) and its half-width equals (hi-lo)/2; an archived tick the store
  does not carry RAISES rather than being silently dropped; the probe's stop rule holds (1 < 3),
  every refusal names a source and a reason, and the module body contains none of
  `_charge_ledger / backtest_runner / backtest_fwer / charge_tier / prereg_sha256 / PREREG` with
  the real ledger bytes asserted unchanged.

**Uncharged (Q1/Q2).** `data/cache/eval_gate/backtest_fwer.jsonl` md5
`a4ae7c13995672e478d59770591b83ba`, 18 rows, before and after -- never opened. No prereg sealed. K
never read. `data/registry/` untouched. No flag flipped on. No `--force`. No pod contact, no push.
Nothing read or written under `src/`, `kernel/`, `api/`, `intel/`, `scripts/team_system/`.

---

## 6. Contract self-check (B and Q)

B1 the metric excludes no row -- all 15,702 archived screen ticks are scored, and the one exclusion
(section 3) is a NAMED sensitivity beside the headline, not the headline. B2 additive: one new
module, one new test, no column or status renamed; `requote` only ADDS `real_game_seq` / `cluster`.
B3 a tick with no parsed state inherits its segment (S106's own rule); nothing is quarantined on
absent evidence. B7 not a head slice: the whole screen side is scored, and the split's boundary
reasons are counted over all 227 game_ids. B9 the denominator is 88 REAL games, which is the point
of the row -- the recycled unit (41 tickers) is reported beside it, never instead of it.
B10/Q3 the bar is +0.004, byte-identical to S82. Q4 no new fit was made; the archived predictions
come from S82's purged, embargoed walk-forward. Q5 **SINGLE-WINDOW** -- one sport, one corpus, one
window; no AHEAD is claimed and none could be. Q6 calibration language only; no retracted figure
appears. Q7 the ranked table is a SCORED metric at n = 15,702 over 88 clusters. Q8 the premise was
re-measured first and is FALSIFIED on the supply half -- reported, not fixed. Q9 the per-tick
differential is archived with its cluster ids.

---

## 7. NOT VERIFIED

- **No new feature was screened.** The row's BUILD step did not run: 1 of 5 members is suppliable
  and the row's own rule stops the lane. The umpire member is suppliable and was NOT screened
  (screening it alone is not the tier the row specifies); that remains open work.
- The umpire "suppliable" verdict is a COVERAGE measurement, not a completed join: the
  `(game_date, team pair) -> game_pk` bridge from a Kalshi ticker to `probables.parquet` was not
  built or exercised, and `umpire_zone_index.parquet` is a frozen 2022_2023 index whose `as_of`
  stamp (2026-07-05) postdates two of the three fold dates even though its source rows do not.
- The re-quote inherits every S82 limitation unchanged: one hypothesis form (a single additive
  logistic term), 24 base-out states collapsed to an ordinal, `batters_faced_continuous` not
  screened, 13,184 of 28,886 screen ticks unscored (the two NO_TRAIN fold dates), capture-time
  rather than event-time tick stamps, and the incumbent `e4_gd` series taken as given.
- The real-game split uses `gap_hours = 5.0`, S106's default; no sensitivity to that threshold was
  run here, and 3 of the 165 boundaries come from the time-gap rule.
- The `(game_id, ts) -> real_game_seq` map is asserted single-valued (0 of 77,327 pairs straddle a
  boundary) on THIS store only; the joined store still holds 1,659 duplicate `(game_id, ts)` rows
  (S83), which this row reports and does not fix.
- The power figures in section 2 are back-of-envelope: they hold each point estimate and dispersion
  fixed and scale the half-width as 1/sqrt(clusters). They are a scale, not a design.
- The VERDICT side (2026-W28) was never read. Every identity-carrying tick lives there, which is
  precisely why this row could not screen the members it names.
- Lane's own report; no verifier re-run.
