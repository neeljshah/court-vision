# S85 -- the 25 never-screened families: what each one needs, and what happens once it gets it

Date: 2026-09-03 | Area: signals-pregame | Verdict: **5 FAMILIES OPENED AND SCREENED -- SCREEN NULL;
8 OPENED AND HONESTLY UNCOVERED; 1 CLOSED AT LIMIT**
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked at the end).
No charge, no prereg, no seal. K was never read. An uncharged screen is a NON-FINDING.
Calibration language only.

---

## 0. Premise (Q8) -- re-measured at HEAD FIRST. PARTIALLY FALSIFIED.

The row's claim: *25 of 37 pregame grammar families have never produced a screen -- every
`live_tick` family is refused by leaky name, and the player / pitcher / referee-grain families are
refused as `unavailable` because the real screen predictor cannot supply their columns from the
gate corpora.*

Measured before any edit, by running `screen_predictor.check_feature_name` and
`screen_predictor.source_column` on EVERY member column of EVERY frozen family against the four
real gate corpora (`scripts/platformkit/foundry/screen_predictor.corpus_states`):

| bucket | families | note |
|---|---|---|
| frozen blocks in `FWER_FAMILIES_SPEC_2026-09-03.md` | 40 | |
| `kind` = arm / tickgrid (S89, S102; skipped by the pregame enumerator) | 3 | `ingame_arms_mlb`, `ingame_arms_nba`, `ingame_nba_tickgrid` |
| **`kind` = grid -- the row's 37** | **37** | |
| with >= 1 screened single (S58c / S79) | 12 | |
| `live_tick`, every member refused `leaky` (S82 measured 46/46) | 11 | |
| **pregame, refused -- this row's subject** | **14** | |

**The count is right; the REASON is stale for three of the fourteen.** Re-measured at HEAD:

- **`tennis_features` supplies 15 of 15 member columns today**, 25,512 non-null of the 33,685-state
  tennis corpus. **`tennis_return` supplies 18 of 18**, same coverage. **`tennis_meta` already
  supplied 3 of 12** (`p1_minutes_prior_asof`, `p2_minutes_prior_asof`,
  `diff_minutes_prior_asof`). These three are one-row-per-`event_id` `asof_*` tables whose ids join
  the gate spine directly; the tennis `event_uid` work (S48 / S65) landed AFTER S58c ran and
  nothing re-screened them. They were never *unsuppliable*; they were simply never re-tried.
- **`nba_quarter_shape` is worse than refused: it passes BOTH guards and returns 0 non-null of
  1,814.** `source_column` takes the first of `("event_id", "game_id")` present in the source, and
  `asof_quarter_shape.parquet` carries an ESPN `event_id` (`401809243`) alongside the NBA
  `game_id` (`0022500001`) the gate corpus is keyed by. A silent all-NaN column is a worse failure
  than a refusal, because a screen on it would have run and scored the incumbent's own number.
  Joined on `game_id` the same table covers 583 of 1,814.

The remaining 10 pregame families are refused exactly as the row says.

### 0.1 Per refused PREGAME family: member columns, the verbatim refusal, and the table that carries them

Refusal strings are the literal `ScreenRefused` message. `>1 row per <key>` is the grain guard in
`source_column`; `neither an asof_ column nor a gate-corpus column` and `is a same-game column` are
the two branches of `check_feature_name`.

| family | sport / horizon / market | members | refusal shape (count) | source table on disk | its grain | join key to the gate event |
|---|---|---|---|---|---|---|
| `mlb_bullpen_relief_chains` | mlb / pregame / ml | 6 | `unavailable: <col> is neither an asof_ column nor a gate-corpus column` (6) | `data/domains/mlb/bullpen_relief_chains.parquet` (71,523 x 10) | one row per (game_pk, reliever) | `team` + `date` -> the state's `home`/`away` + `game_date` |
| `mlb_catcher_framing_index` | mlb / pregame / ml | 3 | same, `unavailable` (3) | `data/domains/mlb/catcher_framing_index.parquet` (113 x 8) | ONE row per catcher for the whole `2022_2023` window; no date | **none** -- see 3.3 |
| `nba_opp_allowed` | nba / pregame / prop | 15 | `unavailable: <col> not found one-row-per-event in opp_allowed_asof_*.parquet` (8), `neither an asof_ column nor a gate-corpus column` (7) | `data/cache/pit/opp_allowed_asof_{2023_24,2024_25,2025_26_reg,2026_playoffs}.parquet` (7,538 rows) | one row per (game_date, team); NO event key at all | `team` + `game_date` |
| `nba_player_adv` | nba / pregame / prop | 6 | `unavailable: <col> has >1 row per game_id in asof_player_adv.parquet (player/tick grain)` (5), `neither an asof_ ...` (1, `n_prior`) | `data/domains/basketball_nba/asof_player_adv.parquet` (77,728 x 9) | one row per (player_id, game_id); ~21 players per game, BOTH teams, no team column | `game_id` + `player_id` -> `team` via `player_boxscores.parquet`, then `team` + `date` |
| `nba_player_value_features` | nba / pregame / ml | 4 | `unavailable: roster_value_asof has >1 row per game_id ... (player/tick grain)` (1), `neither an asof_ ...` (3) | `data/domains/basketball_nba/player_value_features.parquet` (7,222 x 7) | **two rows per game, one per team** -- the grain guard's message is wrong about this one | `game_id` + `team_abbr` |
| `nba_quarter_shape` | nba / period / spread | 15 | none -- passes both guards, then serves 0 non-null of 1,814 | `data/domains/basketball_nba/asof_quarter_shape.parquet` (1,313 x 19) | one row per ESPN `event_id`; also carries `game_id` | `game_id` (NOT the ESPN `event_id` the code picks first) |
| `soccer_referee_card_foul_profiles` | soccer / pregame / total | 5 | `leaky: <col> is a same-game column` (4), `neither an asof_ ...` (1, `year`) | `data/domains/soccer/referee_card_foul_profiles.parquet` (10,251 x 8) | one row per match; the totals ARE that match's | `event_id` for the referee ASSIGNMENT; then `referee` + the date in the id, strictly prior |
| `soccer_style_fingerprints` | soccer / pregame / total | 14 | `leaky: ... same-game column` (7), `neither an asof_ ...` (7) | `data/domains/soccer/style_fingerprints.parquet` (1,336 x 16) | one row per (team, season), whole-season aggregate | `team` + `season`, strictly PRIOR seasons |
| `tennis_features` | tennis / pregame / ml | 15 | **none -- suppliable at HEAD** (premise falsified) | `data/domains/tennis/asof_features.parquet` | one row per `event_id` | `event_id` |
| `tennis_meta` | tennis / pregame / ml | 12 | `neither an asof_ ...` (9); 3 already suppliable | `data/domains/tennis/asof_meta.parquet` (30,616 x 15, `event_id` unique) | one row per `event_id` | `event_id` |
| `tennis_return` | tennis / pregame / ml | 18 | **none -- suppliable at HEAD** (premise falsified) | `data/domains/tennis/asof_return.parquet` | one row per `event_id` | `event_id` |
| `tennis_schedule_density` | tennis / pregame / ml | 4 | `neither an asof_ ...` (4) | `data/domains/tennis/schedule_density.parquet` (61,232 x 9) | two rows per `event_id`, one per player, no side flag | `event_id` + `player_id` matched against the id's own p1/p2 tokens |
| `tennis_serve_return_profiles` | tennis / pregame / ml | 5 | `neither an asof_ ...` (5) | `data/domains/tennis/serve_return_profiles.parquet` (1,330 x 9) | one row per (player_id, season), whole-season aggregate | `player_id` + `season`, strictly PRIOR seasons |
| `tennis_travel_scouting` | tennis / pregame / ml | 3 | `neither an asof_ ...` (3) | `data/domains/tennis/travel_scouting.parquet` (55,446 x 11) | two rows per `event_id` with an `is_p1` flag | `event_id` + `is_p1` |

Measured join reach, before any change: `asof_meta` 25,693 of 33,685 tennis events;
`schedule_density` 25,693; `travel_scouting` 25,547; `referee_card_foul_profiles` 6,524 of 16,322
soccer events (6,472 of those with >= 1 strictly-prior match for the same referee);
`player_value_features` 1,814 of 1,814 NBA events; `asof_player_adv` 1,225 of 1,814;
`style_fingerprints` 169 of 169 corpus team names; `bullpen_relief_chains` 24 of 34 corpus MLB
abbreviations verbatim and 11,179 of 39,162 states inside its 2022-04-07..2026-07-02 window.

**Premise verdict: HELD for 11 of 14 families and for the headline count; FALSIFIED for
`tennis_features`, `tennis_return` and a quarter of `tennis_meta`, which the real predictor already
supplies at HEAD; and CORRECTED for `nba_quarter_shape`, whose failure was silent, not a refusal.**
None of the 25 has ever produced a screen, which is the fact the row rests on.

---

## 1. The change: a DECLARED as-of bridge, and nothing wider

`scripts/platformkit/foundry/asof_supply.py` (296 LOC), imported by `screen_predictor`
(`+8` lines of hook, `+2` context columns on `ScreenBinder.frame`). Test
`tests/platformkit/foundry/test_asof_supply.py` = **4 passed in 1.66s**.

A registry maps ONE `(family, column)` pair to a table, a join and an event-level aggregation rule.
A pair that is not listed is refused exactly as before, so **the bridge cannot move a single
already-screened family's values** -- `test_registry_is_additive_and_well_formed` asserts the
registry keys are disjoint from the 12 screened families, that every declared column really is a
member of that frozen family, and that every declared source path exists.

Three rules, and the whole leak contract lives in them:

- **`event`** -- one row per event in the source, served as-is. Legal only for a column settled
  BEFORE the event: entry rank points, seed, draw size, height, and `*_asof` columns whose producer
  already built them as-of.
- **`side`** -- two rows per event, one per side (a team abbreviation, or an `is_p1` flag). The
  event-level value is home-minus-away (p1-minus-p2), or one declared side where a difference would
  be identically zero (`venue_altitude_m`).
- **`prior`** -- `(entity, date)` grain. The served value is the entity's expanding mean over rows
  with date **strictly before** the event's own date, via
  `merge_asof(..., allow_exact_matches=False)`. Under this rule every column of the source becomes
  as-of by construction, *including a same-game total*, because the event's own row is unreachable.

`prior` is what makes a referee's card total or a reliever's batters-faced honest. The referee
ASSIGNMENT is read from the event's own row -- it is published before kick-off -- but that row's
card totals never are. Same for the NBA player-grain roll-up: the roster comes from the game a row
belongs to, which is same-game knowledge, so the rolled `(team, date)` frame is served ONLY through
`prior`, where the event's own game cannot be reached.

**The guard is the test, not the docstring.** `test_prior_rule_is_strictly_before` builds a source
where HOME has 10 on Jan 1 and 100 on Jan 5 and asserts the event on Jan 5 sees 10 (not 100, not
55), the event on Jan 10 sees mean(10, 100) = 55, and the event on Jan 1 sees NaN -- missing, never
the same-day value (B3).

Deliberately NOT supplied, and named: `year`, `season`, `game_pk`, `is_p1`, `player_id`,
`catcher_id`. An identifier is not a signal, and a prior-mean of one is noise wearing a plausible
name. They stay refused and are counted as refusals below.

`MLB_ALIAS` maps 11 gate-corpus MLB abbreviations onto the modern set the bullpen table uses
(`ARI->AZ`, `CUB->CHC`, `KAN->KC`, `LOS->LAD`, `OAK->ATH`, `SDG->SD`, `SFG/SFO->SF`, `TAM->TB`,
`WAS->WSH`, `BRS->BOS`). The EVENT side is mapped into the source vocabulary so no source is
touched.

### 1.1 The registry, as declared

| family | rule | source | key / entity | combine |
|---|---|---|---|---|
| `nba_quarter_shape` | event | `asof_quarter_shape.parquet` | `game_id` | -- |
| `nba_player_value_features` | side | `player_value_features.parquet` | `game_id` + `team_abbr` | home - away |
| `nba_opp_allowed` | prior | `data/cache/pit/opp_allowed_asof_*.parquet` | `team` + `game_date` | home - away |
| `nba_player_adv` | prior | `asof_player_adv.parquet` rolled to (team, date) via `player_boxscores.parquet` | `team` + `date` | home - away |
| `mlb_bullpen_relief_chains` | prior | `bullpen_relief_chains.parquet` | `team` + `date` | home - away |
| `soccer_referee_card_foul_profiles` | prior | `referee_card_foul_profiles.parquet` | `referee` + date from the event_id | the assigned referee only |
| `soccer_style_fingerprints` | prior | `style_fingerprints.parquet` | `team` + `season` | home - away |
| `tennis_meta` | event | `asof_meta.parquet` | `event_id` | -- |
| `tennis_schedule_density` | side | `schedule_density.parquet` | `event_id` + p1/p2 from the id tokens | p1 - p2 |
| `tennis_serve_return_profiles` | prior | `serve_return_profiles.parquet` | `player_id` + `season` | p1 - p2 |
| `tennis_travel_scouting` | side | `travel_scouting.parquet` | `event_id` + `is_p1` | p1 - p2 (`venue_altitude_m`: p1 only) |

`tennis_features` and `tennis_return` need NO entry -- the premise was wrong about them and they
already resolve through the existing family-source join.

### 1.2 Supply coverage after the change, measured column by column

| family | members suppliable | non-null over the whole corpus | refusals remaining |
|---|---|---|---|
| `mlb_bullpen_relief_chains` | 4 / 6 | 10,653-10,678 of 39,162 | `game_pk`, `year` (identifiers) |
| `mlb_catcher_framing_index` | **0 / 3** | -- | all 3, CLOSED AT LIMIT |
| `nba_opp_allowed` | 15 / 15 | 1,814 of 1,814 | none |
| `nba_player_adv` | 6 / 6 | 1,814 of 1,814 | none |
| `nba_player_value_features` | 4 / 4 | 1,814 of 1,814 | none |
| `nba_quarter_shape` | 15 / 15 | 583-584 of 1,814 (was 0) | none |
| `soccer_referee_card_foul_profiles` | 4 / 5 | 6,472 of 16,322 | `year` (identifier) |
| `soccer_style_fingerprints` | 14 / 14 | 15,646 of 16,322 | none |
| `tennis_features` | 15 / 15 | 25,099-25,512 of 33,685 | none |
| `tennis_meta` | 12 / 12 | 8,940-25,693 of 33,685 | none |
| `tennis_return` | 18 / 18 | 21,003-25,512 of 33,685 | none |
| `tennis_schedule_density` | 3 / 4 | 25,152-25,693 of 33,685 | `year` (identifier) |
| `tennis_serve_return_profiles` | 5 / 5 | 14,941 of 33,685 | none |
| `tennis_travel_scouting` | 2 / 3 | 24,882-25,547 of 33,685 | `is_p1` (identifier) |

**13 of the 14 refused pregame families now supply values. 1 is CLOSED AT LIMIT.**

---

## 2. The local factory screen over the newly suppliable families

`scripts/platformkit/foundry_runner.screen_queue(..., predictor="real", allow_charge=False)` with
`run_pass` over a **scratch sqlite in the session scratchpad**, a scratch ledger path that was
never created, and `trials_dir` under the scratchpad. Seed = every member x the frozen 9-transform
grid over all 14 families = 1,125 hypotheses (1,125 distinct hashes). 12 passes, **403.8 s wall**,
**0 charges**.

Partition and window are the harness's own and unmoved: `tiers.PromotionRule.from_spec()` seed
20260903, SCREEN side only, last 800 states, coverage floor 0.8, purge 48 h + embargo 3 d inside
`walk_forward`. The four screen-partition shas recomputed here are **byte-equal** to S58c / S79 /
S108: nba `1a32541d44aa7fcb`, mlb `ad743c924c7c4547`, soccer `5c8d63970b08ce97`, tennis
`c8dde4f3a44c8e58`.

Result rows: **1,302** = 958 T0 (344 COVERED, 614 UNCOVERED) + **344 T1 SCREEN**.

### 2.1 Families now screened: 5 (was 0)

Improvement = `Brier incumbent - Brier model`; positive is better. The CI is the cluster-robust
Diebold-Mariano 95 pct interval on the paired loss difference, **recomputed here from the archived
per-event differential** in the documented direction (`d = loss_incumbent - loss_model`), never
quoted from the stored `dm_stat` -- S79 filed that `tiers._run_screen` passes the sign mirror, and
that finding is unrepaired.

| family | screens | best member / transform | incumbent | Brier incumbent | Brier model | improvement | DM CI 95 | DM p | clusters |
|---|---|---|---|---|---|---|---|---|---|
| `nba_player_value_features` | 32 | `continuity` / `z_vs_league` | p_base (Elo) | 0.205118 | 0.199897 | **+0.005221** | [+0.000244, +0.010199] | 0.0404 | 30 |
| `nba_opp_allowed` | 120 | `opp_fg3m_allowed_vs_league` / `ew` h=20 | p_base (Elo) | 0.205118 | 0.203259 | +0.001858 | [-0.002086, +0.005802] | 0.3432 | 30 |
| `nba_player_adv` | 48 | `usagepercentage_asof` / `rank_in_league` | p_base (Elo) | 0.205118 | 0.204065 | +0.001053 | [-0.002981, +0.005087] | 0.5976 | 30 |
| `soccer_style_fingerprints` | 112 | `z_corners_pm` / `ew` h=20 | **devigged close** | 0.241896 | 0.243054 | -0.001158 | [-0.008504, +0.006187] | 0.5674 | 3 |
| `mlb_bullpen_relief_chains` | 32 | `battersFaced` / `delta_vs_prior` | p_base (Elo) | 0.249660 | 0.252749 | -0.003090 | [-0.007596, +0.001416] | 0.1714 | 30 |

Every row is n = 800 states and 800 UNIQUE event_ids (B9). **Incumbent labelled: the four NBA/MLB
rows are scored against `p_base` = Elo, which is NOT a close. Only `soccer_style_fingerprints` is
close-relative, and it is negative.**

### 2.2 The honest reading: this is a NULL, and the multiplicity says so out loud

Across all **344** screens:

- improvement > 0 in **151** (43.9 pct -- below a coin flip);
- **2** have a DM CI whose lower end is above 0, where **8.6** would be expected by chance at a
  5 pct two-sided level if every null were true. Both are the SAME source column
  (`nba_player_value_features.continuity`, `z_vs_league` +0.005221 and `raw` +0.005172), so they
  are one signal counted twice, not two;
- **33** have a CI whose upper end is BELOW 0 -- also against 8.6 expected. Adding one of these
  columns to the incumbent measurably HURTS about four times as often as chance.

Fewer nominal winners than chance and four times as many nominal losers is the signature of a set
of columns that carry no information the incumbent lacks. `continuity` clears the S79 screen bar of
+0.004, but it clears it against Elo on one 800-game window, at a nominal p of 0.040 out of 344
looks, where the family-relative and global bars both price 344 -- it does not survive either. **No
prereg is drafted and nothing is charged.**

### 2.3 Families now supplying but honestly UNCOVERED: 8

These pass the name and grain guards and serve real values, then land `UNCOVERED` at the FROZEN
0.8 coverage floor because the source does not reach the frozen last-800 screen window. The floor
is a bar; it was not moved (Q3). Each is **CLOSED AT LIMIT for now with its acquisition named and
measured**:

| family | T0 rows | filled / 800 served | whole screen side | what exactly is missing | the acquisition |
|---|---|---|---|---|---|
| `tennis_features` | 125 | 466 (58.2 pct) | 12,999 / 17,352 | the served 800 are 469 ATP (**all present**) + 331 WTA (**all absent**) | build the `_wta` sibling of `asof_features.parquet`, the pattern `asof_hold_wta.parquet` / `asof_setdetail_wta.parquet` already follows, from `data/domains/tennis/wta_matches.parquet` (11,270 rows, carries `p1_id` / `p2_id`) |
| `tennis_return` | 152 | 466 (58.2 pct) | 12,999 / 17,352 | same ATP/WTA split | `asof_return_wta.parquet` |
| `tennis_meta` | 100 | 469 (58.6 pct) | 13,084 / 17,352 | same | `asof_meta_wta.parquet` |
| `tennis_schedule_density` | 24 | 469 (58.6 pct) | 13,096 / 17,352 | same | extend `schedule_density.parquet` to the WTA half |
| `tennis_travel_scouting` | 16 | 445 (55.6 pct) | 12,707 / 17,352 | same | extend `travel_scouting.parquet` to the WTA half |
| `tennis_serve_return_profiles` | 40 | 353 (44.1 pct) | 7,667 / 17,352 | ATP-only AND only 383 of the corpus's 1,235 players | extend to WTA and to every player, not just the frequently-seen ones |
| `soccer_referee_card_foul_profiles` | 32 | 294 (36.8 pct) | 2,654 / 7,656 | the table covers divisions **E0 and E1 only**; the served 800 are E0 294 (all present) + F1 225 + SP1 281 (all absent) | extend `referee_card_foul_profiles.parquet` to F1 and SP1 (and the rest of the corpus divisions) |
| `nba_quarter_shape` | 125 | 282 (35.2 pct) | 282 / 867 | the table has 1,156 distinct `game_id`, covering season 2026 (255/255 of the served window) and only 33 of the served 382 rows in 2025; 2024 is entirely absent | fold the `linescores_2024_25.parquet` shard into the `asof_quarter_shape` producer -- it is on disk (1,321 rows) but keyed by ESPN `event_id`, so it goes through `espn_nba_game_bridge.parquet`, exactly as the 2025-26 shard already does |

Every one of these eight would clear the 0.8 floor at full coverage; none of them is a modelling
limit, all eight are a source-extent limit, and each named acquisition is a file that either exists
on disk unfolded or has a sibling already built for a different family.

### 2.4 CLOSED AT LIMIT with no supply at all: 1

**`mlb_catcher_framing_index`.** `catcher_framing_index.parquet` is 113 rows: ONE row per catcher
covering the whole `2022_2023` window, with no date column and an `as_of` stamp of the build time
(2026-07-05). It is a whole-window aggregate, so no `prior` rule can make it as-of, and there is no
per-date catcher table on disk to roll (`data/cache/ingame/mlb_pitch_states__*.parquet` carry pitch
location and velocity but no catcher id). Even with one, the event-level join needs the STARTING
CATCHER, and `data/domains/mlb/probables.parquet` announces starting PITCHERS and the home-plate
umpire only -- no catcher.

**Acquisition, both halves required:** (a) rebuild the framing index at `(catcher_id, game_date)`
grain from the Statcast pitch corpus so a strictly-prior mean exists, and (b) a pregame
announced-lineup feed carrying the starting catcher per team per game. Neither is on disk. Until
both land this family cannot be screened honestly, and a screen on the current file would be a
whole-window aggregate leaking into every event it covers.

---

## 3. The S79 pick rule, shipped as an option and OFF by default

S79 measured that in 6 of 12 families the top-5 by screen improvement were mostly ONE source column
at several `ew` halflives, so the k=5 combination spent its parameters on redundancy and was worse
than its own k=1 arm in 11 of 12 families.

`promotion.promote(t1_results, rule, distinct_source_columns=False)` now takes that third argument.
`False` -- the default, and the only value any caller passes -- walks the ranked list unchanged, so
the frozen ranking is byte-identical. `True` walks the same ranked list in the same improvement
order but takes at most one hypothesis per source column, so k picks come from k distinct columns.
It changes WHICH hypotheses are promoted, never how many, and touches no bar: `rule.top_n` still
comes off the pinned `FACTORY_TIERS_SPEC` and `PromotionRule` is unchanged.

`test_promote_diversifies_by_source_column_only_when_asked` asserts both directions on a fixture
where one column holds the top three slots: default gives `[a_asof, a_asof, a_asof, ...]`, the flag
gives `[a_asof, b_asof, c_asof]` with no duplicates and never more than `top_n`.

**Not wired into `tiers` or the runner.** Nothing calls it with `True` yet -- an unused opt-in with
zero callers is the honest landing for a pick rule whose value has not itself been screened.

---

## 4. Reproduction (A2) and the archived differential (Q9)

- Per-event paired-loss series for the best hypothesis of each of the five screened families,
  `event_id, ts, cluster, loss_model, loss_incumbent, d`, 800 rows and 800 unique event_ids each:
  `data/cache/eval_gate/s85_screen_2026-09-03_<family>.csv`.
- The five headline improvements recompute **from those CSVs alone**, to
  `<= 8e-16` of the table above:
  `nba_player_value_features` +0.005221372, `nba_opp_allowed` +0.001858423, `nba_player_adv`
  +0.001052808, `soccer_style_fingerprints` -0.001158377, `mlb_bullpen_relief_chains` -0.003089865.
- Full premise table, coverage table and screen summary:
  `data/cache/eval_gate/s85_refused_families_2026-09-03.json`.
- Every T0 and T1 row with its own artifact json (including each screen's own archived
  differential and fit state): `data/cache/eval_gate/s85_screen_2026-09-03.sqlite`.
- The run driver, verbatim: `data/cache/eval_gate/s85_run_screen.py`.

## 5. Self-check against VERIFIER_CONTRACT B and Q

- **B1** nothing is excluded by a metric. The denominators are every frozen grid family (37), every
  member column of the 14 refused pregame families, and every one of the 344 T1 screens; the 614
  UNCOVERED T0 rows and the 8 uncovered families are reported by name, not dropped.
- **B2** additive only. One new module, one new test, one new optional argument with a default that
  reproduces the previous behaviour. No column, status value or field was renamed or removed.
  `check_feature_name`'s signature is untouched (its other caller is `eval_gate/s108_features.py`,
  the S108 lane's file, which this lane did not open). `source_column` gained one optional keyword;
  its only callers are inside `screen_predictor`. `promote`'s two existing callers
  (`tiers.promote` re-export, `foundry_runner._promotions`) pass two arguments and are unchanged.
- **B3** missing is never bad: an unresolved value is NaN, `RealScreenPredictor` falls back to the
  incumbent, and the `prior` rule returns NaN rather than the same-day row.
- **B7** not a head slice: the served window is the LAST 800 screen-side states, the same window
  every S58c / S79 screen used, and all 800 are scored.
- **B9** 800 unique event_ids per screen (`n_unique_events == n == 800` verified from every CSV);
  cluster counts printed (nba/mlb G=30 teams, soccer G=3 divisions).
- **B10 / Q3** no bar moved. Seed 20260903, 800-row window, coverage floor 0.8, ridge 1e-3,
  MIN_FIT 30, refit 50, purge 48 h, embargo 3 d, `top_n` off the pinned spec, and the +0.004 screen
  bar are all quoted from the harness. The eight uncovered families are reported CLOSED AT LIMIT at
  the 0.8 floor; the floor was never lowered to let them through.
- **Q1** no prereg sealed and no scored CLAIM made -- a screen is a NON-FINDING.
- **Q2** nothing charged. `_charge_ledger` is never reached, K was never read, the scratch ledger
  path was never even created, and `data/cache/eval_gate/backtest_fwer.jsonl` is 18 rows,
  md5 `a4ae7c13995672e478d59770591b83ba`, byte-identical before and after this lane.
- **Q4** every number comes through `walk_forward` with purge, embargo and per-row vintage
  assertion; no meta-learner is involved.
- **Q5** no AHEAD is claimed. Every family is a single window by construction -- SINGLE-WINDOW.
- **Q6** calibration language only; no retracted figure appears anywhere in this memo.
- **Q7** n = 800 SCORED rows per screen, above the sampling rail; the premise section is a
  CONSTRUCT enumeration of every member column of every frozen family, not a sample.
- **Q8** premise re-measured first and reported PARTIALLY FALSIFIED (section 0), which is a valid
  result, not a failure.
- **Q9** the per-event differential and the as-of fit state are archived for every screen, and the
  headline recomputes from the CSVs alone.

## 6. NOT VERIFIED -- read this before quoting any number above

1. **The four NBA/MLB rows are not close-relative.** Their incumbent is `p_base` (Elo). Only the
   `soccer_style_fingerprints` row compares against a devigged close, and it is negative.
2. **`continuity` +0.005221 is one nominal hit out of 344 looks, against Elo, on one window.** It
   is reported because hiding it would be dishonest, not because it survives. Priced against 344 it
   is what chance produces; the same table shows 33 nominally NEGATIVE screens against 8.6 expected.
3. **The `event` rule trusts the source's own as-of claim.** `p1_rank_points`, `p1_seed`,
   `draw_size`, `p1_ht` and the `*_asof` columns are served at face value because they are settled
   at draw time or by the producer; nothing in this lane re-derives them from raw match rows.
4. **The referee assignment is assumed pregame-known.** Referee appointments are published before
   kick-off, but the assignment here is read from the event's own row of the same table, so an
   assignment that was actually recorded post-match would be a leak the guard cannot see. Its card
   totals are never read from that row.
5. **The NBA player roll-up uses the boxscore roster of the team's PRIOR game.** That is as-of, but
   it is not the lineup that will play; injuries and rotation changes between the two games are
   invisible to it.
6. **`prior` uses an EXPANDING mean over all history, not a window.** No halflife was chosen for the
   supply itself; the grammar's own `ew` transforms then run on top of that series, which is a
   smoothing of a smoothing for those hypotheses.
7. **The MLB abbreviation alias is 11 hand-checked pairs.** A team the map misses resolves to NaN
   and falls back to the incumbent, so a mapping error shows up as coverage, never as a wrong value
   -- but the map was not derived from a franchise table.
8. **Coverage is measured on the frozen last-800 window.** The whole-screen-side coverage is higher
   for the tennis and soccer families (58 pct vs 75 pct for tennis), so their UNCOVERED verdicts are
   partly a property of which events sit in the most recent 800, not only of the source's extent.
9. **In-sample nothing was selected here**, but nothing was validated either: the verdict partition
   was never built, opened or read by this lane.
10. **`distinct_source_columns` has zero callers** and its value has not been screened; it is an
    unused opt-in.
11. **No pod measurement, no deploy, no flag flipped, no `data/registry/` write, no `--force`,
    nothing read or written under `src/`, `kernel/`, `api/`, `intel/` or `scripts/team_system/`.**
