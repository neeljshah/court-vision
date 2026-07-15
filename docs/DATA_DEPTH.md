# Data Depth -- every data point has to mean something

> **Funnel position:** this is the machine-readable floor under **stage 1 (DATA)** and the
> standing input queue for the autonomous discovery loop (**stage 7 (SELF-IMPROVE)**). See the
> full funnel in [../README.md](../README.md) and [INDEX.md](INDEX.md). Honesty rail: this doc
> claims no edge -- it is an inventory of what's on disk, what's derivable, and what's still
> unbuilt. Truth-source for any number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

## What this is

`data/frontend/ops/data_census.json` is a **machine-readable census**, regenerated on demand, that
answers one question per sport: *what raw data exists, what can be derived from it, and what has
actually been built?* It is the **standing queue input** the autonomous loop reads to decide what
to build next -- not documentation written by hand and left to rot. `edge_claimed: false` is
stamped on the file itself; this is a calibration/intelligence inventory, never a betting claim.

```
CENSUS  ->  DIFF  ->  FACTORY
```

- **CENSUS**: walk every source path per sport, record row counts, coverage windows, and fields on
  disk today (`sources` below).
- **DIFF**: for each source, list the claim families that are *derivable* from it and their
  status -- `BUILT`, `PARTIAL`, or `UNBUILT` -- so the gap between "the data exists" and "the claim
  is validated" stays explicit, never assumed closed.
- **FACTORY**: `UNBUILT` families with a `leverage_rank` feed the standing priority queue
  ([top10_unbuilt](#top10-unbuilt-the-priority-queue) below); the claims factory
  (`scripts/platformkit/intel_validation/`) and its independent validator turn a recipe into a
  VERIFIED claim, gated the same way every other claim in the system is (see
  [INTELLIGENCE.md](INTELLIGENCE.md) and [signal-inventory.md](signal-inventory.md)).

Closed classes are stamped `do_not_reopen` and never re-enter the queue -- a family adversarially
gated to REJECT stays REJECT; re-running it burns cycles on a question already answered. This is
how the platform finds what to build next without re-deriving "what's missing" from scattered
notes every session: the census is the single source for that question, diffed, not rewritten,
each time it runs.

---

## Per-sport inventory

Each table is: what's on disk (`sources`), what can be derived from it (`derivable_families`,
status BUILT / PARTIAL / UNBUILT), the single biggest data gap, and any closed classes for that
sport. Row counts and coverage windows are copied verbatim from the census (generated
2026-07-08) -- they drift as ingest continues; regenerate the census rather than trusting this
snapshot indefinitely.

### NBA

| Source | Rows / coverage | Fields |
|---|---|---|
| `pbp_full` -- `data/cache/team_system/pbp/*.json` | 196 games x ~605 actions, 2025-26 only | substitutions, 2pt/3pt, rebound, foul, FT, TO, steal, block, timeout; `personId`, shot `x`/`y`, `shotDistance`, `shotResult`, clock, period, possession, running score |
| `quarter_box` -- `data/cache/quarter_box/<gid>_q{1-4}.json` | 6,275 files (~1,569 games), 2024-25 + 2025-26 | player_id, min, pts, fga, fg3a, fta, reb, ast, pf, plus_minus, start_position |
| `player_boxscores.parquet` | 51,237 rows, 2024-10..2026-04 (full season backfill landed 07-07) | full player box, starter flag, plus_minus |
| `games` / `odds` / `linescores` parquets | 1.3k-4.8k rows, 2022-10..2026-04 | rest, b2b, travel, ml/total/spread, q1-q4 |
| `possessions` (`pbp_possessions` + `legacy_possessions`) | 39.5k + 508.9k rows, multi-season | pts, transition, second_chance, ato, in-penalty, is_clutch, poss_dur |
| `defender_matchup_states.parquet` | 37,395 rows, prior + realized | fg_pct_allowed, switches, matchup_min |
| market (`line_history/nba`) | 596 rows, 2026-06-18..07-08 | book, odds, devigged_prob (inplay_history + depth_history are empty offseason stubs) |

**Biggest absence:** full pbp with substitutions covers only 196 games of 2025-26; no multi-season
sub-level pbp or shot x/y outside them. In-play tick + depth history are empty (offseason).

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `lineup_reconstruction` | `pbp_lineups.py` walks quarter_box `start_position` + substitution actions into `stints_2025_26.parquet` (10,124 stints) | BUILT | -- |
| `on_off_splits` | `on_off.py` joins stints to possession outcomes -> `on_off_2025_26.parquet` (550 player-rows, net_rating_on/off_per48) | BUILT | -- |
| `gravity_proxy` | `gravity_spacing.py` teammate eFG on vs. off -> `gravity_proxy_2025_26.parquet` (43 players; thin, bounded by the 196-game subset) | BUILT | -- |
| `lineup_spacing_from_shot_xy` | `gravity_spacing.py` zone mix per lineup_key -> `lineup_spacing_2025_26.parquet` (3,043 rows) | BUILT | -- |
| `lineup_vs_lineup_matchups` | `lineup_matchups.py` joins opposing stint windows -> `lineup_matchups_{2023_24,2024_25,2025_26}.parquet` | BUILT | -- |
| `player_foul_trouble_states` | per-player foul count vs. minutes-remaining from foul actions | PARTIAL | -- |
| `timeout_run_dynamics` | ato flag in pbp_possessions + runvar asof | BUILT | -- |
| `clutch_playtype_profiles` | pbp_possession_features + atlas iso/PnR/clutch | BUILT | -- |
| `quarter_shape_fatigue` | asof_quarter_shape from quarter_box | BUILT | -- |
| `box_rate_claims` | nba_player_box_rate / nba_team_box_rate / shooting / schedule claim families | BUILT | -- |
| `defender_suppression` | defender_matchup_states priors + reclaim gates | BUILT | -- |

**Closed classes:** `ingame_hot_night`, `ingame_scheme_fit` (see [do_not_reopen](#do-not-reopen-closed-classes)).

The first four rows of this table are the **keystone** -- see
[The keystone: NBA lineup reconstruction](#the-keystone-nba-lineup-reconstruction) below.

### MLB

| Source | Rows / coverage | Fields |
|---|---|---|
| `statcast_pitch` | ~721k/season, 2022-2023 | release_speed, spin, pitch_type, zone, plate_x/z, launch_speed, xwOBA, events, stand, p_throws, if/of fielding alignment |
| `pitch_states` | ~70k/season, 2022-2026 | count, runners, outs, sp_pitch_count_prior, velo_decline, base_run_value, leverage_bucket, p0, outcome |
| `atbat_states` | 13k-42k/season, 2021-2026 | half_inning, count, runners, outs, base_out_known |
| `gumbo_live` | 47 games x ~104 ticks, 2026 live | inning/half, base_state, outs, count, batter/pitcher ids, pitcher_pitches, scores |
| `games` / `odds` / `pitchers` parquets | ~28k rows, 2010-2021 | ml open/close, runline, OU, SP names, innings |
| `starter_table` | ~1,048/season, 2022-2023 | mean_velo, velo_decline_slope, pitch_mix_entropy, frac_breaking |
| `injuries` / `espn_boxscores` / `catcher_framing_index` | 113-3,837 rows, current era | injury status, 108-col team box, OOZ strike rate |
| market | 3.5k lines / 260k ticks / 2.2k depth, 2026-06/07 | devigged books, Kalshi ticks, order-book levels |

**Biggest absence:** the odds corpus (2010-2021) and the pitch-level corpus (2022-2026) are
disjoint -- no historical odds on disk for the statcast era, so pitch-derived families cannot be
market-joined historically.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `times_through_order` | at_bat_number x pitcher -> TTO splits | BUILT | -- |
| `count_leverage_transitions` | per-count run-value transition table from pitch_states base_run_value | PARTIAL | -- |
| `bullpen_fatigue_chains` | trailing 1-3-day reliever pitch counts -> availability/effectiveness claims (descriptive; the SP-velo in-game class stays CLOSED) | UNBUILT | 7 |
| `fielding_alignment_conditioning` | if/of_fielding_alignment x batter stand -> BABIP/xwOBA descriptive splits | UNBUILT | -- |
| `pitch_arsenal_profiles` | per-reliever pitch-mix entropy + platoon-specific arsenal splits | PARTIAL | -- |
| `batted_ball_quality_profiles` | launch_speed/xwOBA percentile profiles per batter/pitcher | PARTIAL | -- |
| `catcher_framing` | OOZ called-strike rate index | BUILT | -- |
| `umpire_zone` | umpire_zone_claims | BUILT | -- |
| `platoon_splits` | platoon_split_claims | BUILT | -- |
| `plate_discipline` | mlb_plate_discipline_claims | BUILT | -- |
| `base_out_state_conditioning` | ingame_baseout + gumbo diffPatch live capture | BUILT | -- |
| `park_factors` | asof_park (current-era coverage gap known) | BUILT | -- |

**Closed classes:** `ingame_sp_velo_fatigue`, `mlb_pregame_stack_L3`.

### Club soccer

| Source | Rows / coverage | Fields |
|---|---|---|
| `statsbomb_events` | 400 matches x ~3,490 events, 2015-2021 open data | type, possession id, play_pattern, team, minute/second, tactics (formations, XIs), duration |
| `match_stats.parquet` | 25,834 rows, 2015-2026 | shots, sot, corners, fouls, yellow/red, referee |
| `odds.parquet` | 16,322 rows, O/U open/close | b365/avg/max over-under (raw decimal odds -- devig landmine, see below) |
| `espn_player_stats.parquet` | 1,290 rows, current | minutes, sub in/out, shots, cards, goals |
| market | 5,940 rows, 2026-06/07 | devigged books (inplay_history is an empty stub) |

**Biggest absence:** event data covers only 400 StatsBomb matches ending 2021 -- none of the
25,834-match odds corpus has events; club in-play tick history is an empty stub.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `possession_value_xg_chains` | statsbomb possession ids + play_pattern -> per-chain value, buildup vs. counter | UNBUILT | -- |
| `momentum_windows` | rolling within-match press/shot swing from events (10-min cuts built) | PARTIAL | -- |
| `formation_lineup_effects` | tactics field (formations + XIs) x outcomes | UNBUILT | -- |
| `referee_card_foul_profiles` | referee col across 25,834 matches -> per-official card/foul rates (the WNBA referee producer is the template) | UNBUILT | 6 |
| `corner_card_volume` | corners/cards claim families from match_stats | UNBUILT | -- |
| `sot_ratio_xg_proxy` | asof_features + asof_xg_proxy | BUILT | -- |
| `pressing_intensity` | press_diff_asof at 10-min cuts | PARTIAL | -- |

**Closed classes:** `home_sot_replication`.

> `odds.parquet`'s `p_over`/`p_under` fields are **raw decimal odds, not probabilities** -- a
> known landmine; devig through the adapter, never read the column as a probability directly.

### International soccer (World Cup / national teams)

| Source | Rows / coverage | Fields |
|---|---|---|
| `results.parquet` | 49,477 rows, 1872-2026 | scores, tournament, city, country, neutral |
| `travel_scouting.parquet` | 98,954 rows, per-team-match | miles_flown_in, venue_altitude_m |
| `fotmob` (live + backfill) | 330 live + 38 backfill matches, 2026 | xg/xgot, sot_diff, big_chance_diff, momentum_last10, red_card_state, cutoff_min |
| market | 52 lines / 127k ticks / 1.6k depth, 2026-06/07 | Kalshi WC markets |

**Biggest absence:** no historical odds before 2026-06 (52 pregame rows) and only 38
xG-backfilled matches -- the 49k-match corpus is scores-only.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `team_strength_form_h2h` | soccer_intl strength/form/h2h claim families | BUILT | -- |
| `travel_altitude_conditioning` | travel_scouting + team_travel_rate claims | BUILT | -- |
| `live_xg_repricing` | fotmob live capture + xg crossfit/tier calibration | BUILT | -- |
| `tournament_context_splits` | tournament/neutral cols -> competitive-vs-friendly, knockout-vs-group splits across 49k matches | UNBUILT | -- |
| `confederation_era_strength` | era/confederation-normalized strength | PARTIAL | -- |

**Closed classes:** none.

### Tennis

| Source | Rows / coverage | Fields |
|---|---|---|
| `matches.parquet` | 30,616 rows, 2015-2025 ATP+WTA | surface, level, round, best_of, ranks, score, retirement, minutes |
| `match_stats.parquet` | 59,312 rows, per-match serve lines | ace, df, svpt, 1stIn/1stWon/2ndWon, SvGms, bpSaved/bpFaced |
| `odds.parquet` | 33,952 rows, 2015-2025 | b365 + pinnacle winner/loser |
| `sackmann_pbp/` | 0 rows -- EMPTY | -- |
| market | 39k lines / 119k ticks / 767 depth, 2026-07 | Kalshi + pinnacle |

**Biggest absence:** point-by-point data is absent (`sackmann_pbp/` is an empty directory) --
true pressure-point splits (deuce / BP-as-played / tiebreak sequences) are not derivable; only
match-aggregate serve lines exist.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `hold_return_surface_splits` | asof_hold/asof_return (+WTA) | BUILT | -- |
| `set_detail` | asof_setdetail (tiebreak, close-set) | BUILT | -- |
| `playstyles_h2h` | atlas_playstyles + atlas_h2h + claim families | BUILT | -- |
| `pressure_aggregate_bp` | bp_saved/converted pct (point-order splits blocked by pbp absence) | PARTIAL | -- |
| `fatigue_schedule_density` | minutes col + match dates -> trailing 7/14-day court-time claims (port the WNBA schedule_density producer) | UNBUILT | 9 |
| `retirement_risk_descriptors` | retirement flag across 30k matches | UNBUILT | -- |
| `rank_gap_round_splits` | higher_rank_wins conditioned on round | PARTIAL | -- |

**Closed classes:** none.

### WNBA

| Source | Rows / coverage | Fields |
|---|---|---|
| `cdn_backfill_states.parquet` (+168 games raw) | 504 rows, 3 checkpoints/game | lineup_home/away, team_fouls, in_bonus, run_last_3min, foul_trouble_flags |
| `espn_scoreboard` / `linescores` | ~770 rows, 2024-05..2026-07 | q1-q4, half, end_q3, neutral_site |
| `injuries` / `referee_crew_foul_rate` / `schedule_density` / `arena_attendance_context` | 35-1,540 rows, current | injury status, fouls_per_game, games_last_7d/14d, attendance/sellout |
| market | 20k lines / 200k ticks / 1.6k depth, 2026-07 | Kalshi |

**Biggest absence:** no player boxscores and no play-by-play on disk -- player trait profiles
(the NBA-atlas equivalent) are not derivable; lineups exist only as 3 checkpoints/game.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `elo_pregame_strength` | elo refresh + wnba_claims + pregame gate | BUILT | -- |
| `referee_crew_foul_rates` | referee_crew_foul_rate claims | BUILT | -- |
| `schedule_density` | games_last_7d/14d claims | BUILT | -- |
| `foul_bonus_ingame_states` | cdn_backfill_states -> in-game blend | BUILT | -- |
| `lineup_exposure_descriptors` | checkpoint lineup strings -> most-used units / continuity claims | UNBUILT | 10 |
| `run_momentum_conditioning` | run_last_3min captured, not yet a claim family | PARTIAL | -- |
| `quarter_shape` | NBA-style quarter margins from linescores | PARTIAL | -- |

**Closed classes:** none.

### NPB / KBO

Both leagues sit on results-only corpora today; the census tracks them separately because their
ingest paths and market-capture cadences differ.

| Source | Rows / coverage | Fields |
|---|---|---|
| `npb_results.parquet` | 3,976 rows, 2022-03..2026-07 | date, teams, scores, home_win, tied |
| `kbo_results.parquet` | 3,263 rows, 2022-04..2026-07 | same 8 cols as NPB |
| `naver_relay_live_sample` (KBO) | 1 probe | live inning/base/out reachable -- recipe proven, not yet an accrued corpus |
| `slate_*.json` (KBO) | daily, 2026-07 | slate + close reports |
| market (each) | 12.9k/46.8k lines/ticks (NPB), 10.8k/57k (KBO), since 2026-07-04 | Kalshi |

**Biggest absence:** results-only below team-game grain for both leagues; no player-, pitch-, or
lineup-level data of any kind. KBO's Naver relay live-state capture is proven as a recipe but no
accumulated in-game state corpus exists yet -- see `naver_relay_state_accrual` below, rank 5.

| Derivable family | Sport | Recipe | Status | Leverage rank |
|---|---|---|---|---|
| `team_strength_pregame` | NPB | npb_kbo_claims + pregame gate | BUILT | -- |
| `ingame_base_model` | NPB | ingame_base_fit (post model-wire fix) | BUILT | -- |
| `tie_rate_conditioning` | NPB | tied col -> extra-innings-rule tie-rate claims | UNBUILT | -- |
| `run_environment_trends` | NPB | season-level scoring environment from results | UNBUILT | -- |
| `team_strength_pregame` | KBO | kbo_team_strength_snapshot + npb_kbo_claims | BUILT | -- |
| `ingame_base_model` | KBO | ingame_base_fit verdict | BUILT | -- |
| `naver_relay_state_accrual` | KBO | persistent Naver relay capture -> base-out states (the MLB gumbo_live equivalent) | UNBUILT | 5 |
| `tie_run_environment` | KBO | as NPB | UNBUILT | -- |

**Closed classes:** none for either league.

### Cross-sport market data

Market capture (line/inplay/depth history) is captured on one shared pipeline across every sport
above, so it gets its own census entry rather than repeating per sport.

| Source | Rows / coverage | Fields |
|---|---|---|
| `line_history/<sport>/<date>.jsonl` | 0.6k-39k rows/sport, 2026-06-18..07-08 (varies) | book, odds, devigged_prob, market_type, captured_at |
| `inplay_history/<sport>/<date>.jsonl` | 47k-261k ticks/sport (nba + club soccer are empty offseason stubs), 2026-07-02..07-08 | ticker, prob, phase, ts |
| `depth_history/<sport>/<date>.jsonl` | 0.8k-2.2k rows/sport (nba + soccer 0), since 2026-07-05 | yes_bids/asks levels, depth_totals |
| `book_depth/kalshi/*.jsonl` | ~15k rows, 2026-07 | best_bid/ask, book_thinness, n_levels |

**Biggest absence:** `depth_history` + `inplay_history` are empty for NBA and club soccer
(offseason stubs) -- this is a seasonal gap, not a missing pipeline.

| Derivable family | Recipe | Status | Leverage rank |
|---|---|---|---|
| `tick_tail_bias` | ingame_tail_scan/verdict per sport | BUILT | -- |
| `same_venue_reconcile_grading` | inplay ledger + grade files | BUILT | -- |
| `depth_imbalance_descriptors` | bid/ask level asymmetry + thinness-vs-spread joint states from depth_history (execution-quality context, calibration only) | UNBUILT | 8 |
| `book_disagreement_dispersion` | cross-book devigged-prob dispersion as a claim family (best_price_scan exists) | PARTIAL | -- |

**Closed classes:** none.

---

## top10_unbuilt: the priority queue

The census ranks every `UNBUILT` family with a `leverage_rank` across all nine sports into one
cross-sport queue -- this is literally what the autoloop reads to decide what to build next.

| Rank | Sport | Family | Why |
|---|---|---|---|
| 5 | kbo | `naver_relay_state_accrual` | ports the proven MLB base-out state machine to a live-daily sport in the execution lane |
| 6 | soccer | `referee_card_foul_profiles` | cheapest new family (WNBA producer template) at 25k-match scale |
| 7 | mlb | `bullpen_fatigue_chains` | late-inning in-game context; descriptive, distinct from the closed SP-velo class |
| 8 | cross_sport_market | `depth_imbalance_descriptors` | fill-quality awareness for the paper execution lane, data flowing daily |
| 9 | tennis | `fatigue_schedule_density` | direct port of the built WNBA producer; highest-tick-volume Kalshi sport |
| 10 | wnba | `lineup_exposure_descriptors` | only non-NBA lineup data; opens the lineup class in a second sport |

Ranks are copied verbatim from the census, which no longer assigns ranks 1-4 -- the NBA lineup
keystone (`lineup_reconstruction`, `on_off_splits`, `gravity_proxy`, `lineup_spacing_from_shot_xy`)
moved from `UNBUILT` to `BUILT` on 2026-07-08 (see [the keystone section](#the-keystone-nba-lineup-reconstruction)
below), so it dropped out of the unbuilt queue.

---

## do_not_reopen: closed classes

Four hypothesis classes were run through the leak-free gate, adversarially challenged, and
returned an honest REJECT or NOT_TESTABLE. They are stamped `do_not_reopen` in the census so the
autoloop never re-spends a cycle re-litigating a question already answered:

- `nba ingame hot_night/scheme_fit`
- `mlb ingame SP velo fatigue`
- `soccer home_sot`
- `mlb pregame stack L3`

An honest REJECT is a recorded success, not a gap to keep poking at -- see
[signal-inventory.md](signal-inventory.md) and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for
the full reject ledger and the standard this bar is held to.

---

## Latency audit: what "fast" actually means here

Before building any in-game family that depends on *being first*, the platform ran a leak-free
audit (`data/frontend/ops/latency_audit.json`, 2026-07-04..07-07 measurement window) asking one
question: does our own live-state capture ever observe a game event ahead of the market moving?

**Method.** For 154 Kalshi NBA-market events, the audit forward-searched for the nearest matching
price move after each event and measured the lag. 135/154 matched (join_success_rate 1.0), median
lag 34.0s (p25 16.0s, p75 86.0s), and a naive read of `pct_events_we_led` came back 1.0 -- every
matched event "led" the price move.

**The forward-search-tautology lesson.** That 1.0 is **not evidence of a real lead** -- it is a
tautology of the method. A forward-only search only ever finds a price move *after* the event by
construction (lag >= 0 always), so it cannot detect a case where the market moved *first*. The
audit caught this and re-ran with a 10-minute-before lookback: **129/135 (95.6%) of the same
matched events already showed Kalshi's price moving >= 2pp before our tick even registered the
event** -- the more honest signal, and it points the opposite direction from the naive forward
search. `feasibility_verdict`: **not established** -- the available evidence leans toward Kalshi
moving first, not us.

**Why the gap exists -- capture cadence.** The root cause is a coarseness mismatch, not a modeling
gap: Kalshi's own quote capture cadence is a median **7s** poll, while our gumbo live-state capture
cadence -- as measured in this audit -- was a median **54s** poll with real-world gaps stretching up
to **~102 minutes** (restarts, stale windows). A depth-of-book join for the leading moments also
failed to resolve (0/135) on a side-name-to-ticker-abbreviation format mismatch. At that resolution
mismatch the dataset cannot resolve true lead/lag either way -- a measurement-power problem, not a
proven absence of lead. **Same-day response:** the capture was upgraded the evening of the audit
(2026-07-07) to a ~10s live-game window using GUMBO diffPatch (see docs/INGEST_PIPELINES.md),
verified writing rows every 11-18s across 11 concurrent live games; the audit is queued to re-run
on the fine-grained captures, and the lead/lag verdict stays NOT_ESTABLISHED until that
re-measurement lands. (The Kalshi depth-ladder capture used by the paper fill-simulation layer runs
coarser still, ~20 minutes per ticker -- fine for pricing a fill against a recent book, not for a
lead/lag race.)

This audit is why in-game family builds in this doc are framed as *calibration and context*, never
as a latency edge -- the honest verdict on latency itself is NOT_ESTABLISHED, and no claim here
overrides it.

---

## The keystone: NBA lineup reconstruction

`on_off_splits`, `gravity_proxy`, `lineup_spacing_from_shot_xy`, and `lineup_vs_lineup_matchups`
all blocked on the same missing table: **which 5 players are on the floor, possession by
possession.** As of the 2026-07-08 census, that table is `BUILT` and all four downstream families
are `BUILT` off it.

**What's on disk today.** `data/cache/team_system/pbp/*.json` has full play-by-play with
substitution actions for 196 games of the 2025-26 season -- `actionType` includes `substitution`
with `personId`, `clock`, and `period`, plus shot `x`/`y` and `shotDistance` on every shot action.
`data/cache/quarter_box/<gid>_q{1-4}.json` (6,275 files, ~1,569 games across 2024-25 + 2025-26)
carries `start_position` per player per quarter -- the seed for the floor-5 at the start of each
quarter.

**The recipe, as built.**
1. `domains/basketball_nba/lineups/pbp_lineups.py` seeds the on-court 5 at the start of each
   quarter from `quarter_box`'s `start_position`, then walks the pbp's `substitution` actions in
   clock order (`personId`, subType in/out) to update the on-court set possession by possession
   into `stints_2025_26.parquet` (10,124 stints).
2. That per-possession lineup table is the single join key for everything downstream:
   - **`on_off_splits`** -- `on_off.py` joins the stints to possession outcomes for ORtg/DRtg with
     player X on vs. off the floor -> `on_off_2025_26.parquet` (550 player-rows).
   - **`gravity_proxy`** -- `gravity_spacing.py` computes teammate eFG with X on vs. off court from
     the same join -> `gravity_proxy_2025_26.parquet` (43 players; thin, bounded by the 196-game
     subset). This is the flagship intelligence claim: a real, measured gravity number, not the
     currently-VERIFIED `gravity_score` atlas claim, which is a **modeled composite**, not an
     on/off measurement (see `compose_profile.py`'s `UNBUILT_AXES` -- the shooter trait profile
     already reports this gap honestly rather than fabricating an on/off gravity axis from the
     modeled score).
   - **`lineup_spacing_from_shot_xy`** -- `gravity_spacing.py` computes zone mix / corner-3 / rim
     rate per 5-man unit from the shot `x`/`y` fields -> `lineup_spacing_2025_26.parquet` (3,043
     rows).
   - **`lineup_vs_lineup_matchups`** -- `lineup_matchups.py` joins opposing teams' stint windows
     per possession into `lineup_matchups_{2023_24,2024_25,2025_26}.parquet`, the joinable key for
     synergy/counter claims.

**Coverage constraint, stated honestly.** The keystone table is built today only from the 196
games that have full substitution-level pbp (2025-26 only) -- that corpus did not grow between the
07-07 and 07-08 census runs, so `gravity_proxy` in particular is a thin 43-player sample. The
6,275-file `quarter_box` corpus gives quarter-start lineups for far more games (~1,569), but
without substitution events in between, only the quarter-boundary lineup is known there, not the
in-quarter changes. Any claim built on the keystone should report which games it drew a full
possession-level lineup for versus a quarter-boundary-only lineup, rather than silently treating
the two as equivalent coverage.

**Tracking as the future measured-gravity tier.** The CV tracking pipeline
(`src/pipeline/unified_pipeline.py`, see [DATA.md](DATA.md)) already produces player court
coordinates and spacing/velocity fields per frame for processed games. Once on/off and
gravity-proxy are BUILT from pbp/box data alone, the natural next tier conditions the same gravity
measurement on **tracked spacing** rather than box-derived shot zones -- does a shooter's gravity
(measured teammate eFG on/off) correlate with *measured* defender displacement from tracking, not
just shot-location mix. That tier is explicitly future work: it needs both the on/off keystone
above and a tracked-game overlap with the 196-game pbp corpus, which does not yet exist. It is
named here so the roadmap from "box-derived proxy" to "tracking-measured" is visible, not so it
reads as already built.

---

The census (`data/frontend/ops/data_census.json`) is regenerated by the autoloop's depth-building
pass, not hand-edited -- the counts and statuses above are a snapshot (generated 2026-07-07);
treat drift as expected and re-run the census rather than trusting an old split indefinitely.

---

*Honesty rail: every family status above is descriptive (what's derivable / what's built), never
a claim of predictive edge. `edge_claimed: false` is stamped in the source census. Truth-source
for any number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).*

**Siblings:** [DATA.md](DATA.md) (ingest pipeline + CV track) *
[INTELLIGENCE.md](INTELLIGENCE.md) (80-artifact intelligence-layer manifest) *
[signal-inventory.md](signal-inventory.md) (feature catalog + SHIP/REJECT verdicts) *
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) * [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) *
[full doc map](INDEX.md).

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
