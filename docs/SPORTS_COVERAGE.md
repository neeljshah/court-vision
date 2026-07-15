# Per-sport coverage matrix -- data, claims, models, market benchmark

> **Funnel position:** this is the cross-sport ledger for stages 1-6 (DATA through INTELLIGENCE)
> -- what corpus exists on disk per sport, what's derived from it, and how the resulting model
> compares to the devigged closing line. See [docs/INTELLIGENCE.md](INTELLIGENCE.md) for the NBA
> intelligence-layer manifest and [docs/ASK_SURFACES.md](ASK_SURFACES.md) for how these claims are
> queried. Source of truth for the sources/gaps below: `data/frontend/ops/data_census.json`
> (generated 2026-07-08, `edge_claimed: false`, standing queue input for the autoloop).

The platform runs the same six-stage funnel -- data, claims, calibration, capture, market
benchmark -- across seven sport surfaces. Coverage is deliberately uneven: NBA and MLB have the
deepest corpora because they carry the richest public play-by-play, while WNBA/NPB/KBO run on
results-only or checkpoint-only data and are honest about it. Nothing here is padded to look more
complete than it is; a sport's `biggest_absence` line below is copied straight from the census, not
softened.

**Claim totals** are VERIFIED rows counted from every `*_validation.json` summary under
`data/cache/intel_claims/` and `data/frontend/ops/`, `verdict == "VERIFIED"` only (matches the
scale in [`docs/ASK_SURFACES.md`](ASK_SURFACES.md)). Total across all stores: **101,104 VERIFIED
claim rows** as of 2026-07-10 (nearly double the 52,381 counted on 2026-07-07).

---

## NBA

**Data on disk:** the deepest corpus in the platform. `player_boxscores.parquet` (51,237 rows,
2024-10..2026-04, full season backfill landed 07-07), `games/odds/linescores.parquet` (1.3k-4.8k rows, 2022-10..2026-04, rest/b2b/
travel/ml/total/spread/quarter splits), possession-level tables (39.5k + 508.9k rows, transition/
second-chance/ATO/clutch flags), defender-matchup states (37,395 rows), and full play-by-play with
substitutions for 196 2025-26 games (~605 actions/game -- `data/cache/team_system/pbp/*.json`) plus
6,275 quarter-box files (~1,569 games, 2024-25 + 2025-26).

**Capture cadence:** `scripts/platformkit/capture/capture_nba.py` (boxscore/schedule capture) plus
the cross-sport `line_history` / `inplay_history` / `depth_history` loops
(`data/cache/{line,inplay,depth}_history/nba/`). In-play tick and depth-history are currently
**empty stubs for NBA** (offseason) -- the market-side capture only comes alive in-season.

**Claims/intelligence:** ~61,665 VERIFIED claim rows -- dominated by `nba_player_box_rate`
(59,268 rows) and `nba_team_box_rate` (2,160), plus the shooter-quality/canonical-shooter/profile/
schedule/fit-ingredient families (`nba_shooting_claims`, `nba_canonical_shooter_claims`,
`nba_shooter_profile_claims`, `nba_schedule_claims`, `nba_fit_ingredient_claims`,
`nba_fit_sweep_claims`, `nba_context_shooting_claims`, `nba_quality_claims`). This is also the
sport with the deepest composer layer -- `compose_best`/`compose_profile`/`compose_fit` in
[docs/ASK_SURFACES.md](ASK_SURFACES.md) are all NBA-first.

**Model + vs-close verdict:** moneyline **MATCH** (Brier 0.1735 vs close 0.1672, n=372, gap
+0.0063 -- within sampling noise, MOV-aware Elo). Totals (O/U) **BEHIND on freshness** (RMSE
19.172 vs close 18.114, n=372, gap +1.058 -- the possessions/efficiency model cannot see injuries/
lineups the market prices in).

**Biggest gap:** full pbp with substitutions covers only 196 games of 2025-26; no multi-season
sub-level pbp or shot x/y outside them. The `lineup_reconstruction` family (walk substitution
actions into a per-possession lineup table) is `PARTIAL` and is the platform's #1-ranked unbuilt
family -- on/off splits, gravity proxies, lineup-vs-lineup matchups, and shot-location spacing all
block on it. **Closed classes (do not reopen):** `ingame_hot_night`, `ingame_scheme_fit`.

---

## MLB

**Data on disk:** Statcast pitch-level (`statcast_fuller__{2022,2023}.parquet`, ~721k rows/season,
release speed/spin/zone/launch data), in-game pitch and at-bat state tables (2021-2026, count/
runners/outs/leverage/SP-fatigue-adjacent fields), 123 games of GUMBO live-tick capture (~104
ticks/game, 2026), a pre-Statcast-era odds+pitchers corpus (~28k rows, 2010-2021), and injury/
framing context (`catcher_framing_index.parquet` etc).

**Capture cadence:** `data/domains/mlb/gumbo_live/<pk>.jsonl` -- the live diffPatch capture loop
that also seeds the KBO/NPB in-game push described below. Cross-sport market capture:
`data/cache/{line,inplay,depth}_history/mlb/` (3.5k lines / 260k ticks / 2.2k depth entries,
2026-06/07 -- the deepest in-play tick coverage of any sport in the platform).

**Claims/intelligence:** ~21,377 VERIFIED claim rows -- `mlb_bullpen_fatigue_chains` (9,060, now
`BUILT`), `mlb_batter_rate` (7,452), and `mlb_pitcher_rate` (4,434) dominate, plus `mlb_team_rate`
(186), `mlb_tto_claims` (times-through-order, 4), and single-row-but-live families:
`catcher_framing_claims`, `umpire_zone_claims`, `platoon_split_claims`, `mlb_plate_discipline_claims`,
`mlb_pitcher_claims`.

**Model + vs-close verdict:** moneyline **MATCH** (Brier 0.2429 vs close 0.239, n=13,992, gap
+0.0039 -- walk-forward MOV-Elo; the tiny deficit is pitcher-blindness, since the close prices the
starting pitcher directly). Totals (O/U) **BEHIND on freshness** (RMSE 4.719 vs close 4.441,
n=1,679, gap +0.2777 -- park/weather/SP/lineup information the run-rate model does not see).

**Biggest gap:** the odds corpus (2010-2021) and the pitch-level corpus (2022-2026) are disjoint
-- no historical odds exist on disk for the Statcast era, so pitch-derived families cannot be
market-joined historically. **Closed classes:** `ingame_sp_velo_fatigue` (velocity-decline
in-game class -- REJECT, both NOT_TESTABLE and honest-REJECT arms closed), `mlb_pregame_stack_L3`.

---

## Soccer (club)

**Data on disk:** 400 matches of StatsBomb open event data (2015-2021, ~3,490 events/match --
possession IDs, play patterns, formations), a 25,834-row match-stats corpus (2015-2026, shots/SOT/
corners/fouls/cards/referee), and a 16,322-row odds corpus.

**Capture cadence:** cross-sport market loops write `line_history/soccer` (5,940 rows, 2026-06/07);
club-level in-play tick history is an **empty stub** -- club soccer's live conditioning is not yet
capturing.

**Claims/intelligence:** `sot_ratio_xg_proxy` and `pressing_intensity` (10-minute cuts) are
`BUILT`/`PARTIAL`; `soccer_referee_card_foul_profiles` is now `BUILT` (2,736 VERIFIED claim rows
across the 25,834-match corpus, as of 2026-07-10). Possession-value xG chains and formation/lineup
effects remain `UNBUILT`.

**Model + vs-close verdict:** O/U-2.5 **MATCH** (Brier 0.2465 vs close 0.239, n=7,558, gap
+0.0076 -- EW-Poisson + finishing + pooled-Platt calibration vs the devigged Pinnacle close). 1X2
is **absent by design**: the football-data corpus carries O/U-2.5 prices only, no 1X2 closing odds
exist locally to devig against.

**Biggest gap:** the 400-match StatsBomb event window ends in 2021 and never overlaps the
25,834-match odds corpus -- none of the priced matches have event-level data, and the club in-play
tick stub is empty. **Closed classes:** `home_sot_replication`.

---

## Soccer (international -- World Cup / national teams)

**Data on disk:** the platform's deepest historical footprint by calendar span -- `results.parquet`
(49,477 matches, 1872-2026, scores/tournament/venue/neutral), `travel_scouting.parquet` (98,954
per-team-match rows, miles flown + venue altitude), and live FotMob capture (330 live + 38
backfilled 2026 matches with xG/xGOT/SOT-diff/big-chance-diff/momentum/red-card-state).

**Capture cadence:** the FotMob live loop is the sport's distinctive in-game feed -- keyless,
xG-grade, and the basis for the `live_xg_repricing` claim family. Market capture: 52 pregame lines
/ 127k in-play ticks / 1.6k depth entries (2026-06/07, Kalshi World Cup markets).

**Claims/intelligence:** ~1,461 VERIFIED claim rows -- `soccer_intl_team_travel_rate` carries 1,458
of them (travel/altitude conditioning), with strength/form/h2h claim families each contributing a
handful more. `team_strength_form_h2h`, `travel_altitude_conditioning`, and `live_xg_repricing` are
all `BUILT`.

**Model + vs-close verdict:** not in the current 4-sport beat-the-close scoreboard run (see
[Cross-sport summary](#cross-sport-summary) below for the sports that are measured); the strength/
form/h2h pregame gate and the live xG-repricing calibration are the sport's shipped surfaces.

**Biggest gap:** no historical odds before 2026-06 (52 pregame rows total) and only 38 xG-backfilled
matches against a 49,477-match results corpus -- the vast majority of the historical record is
scores-only, with no market or shot-quality context to join against it. **Closed classes:** none.

---

## Tennis (ATP + WTA)

**Data on disk:** `matches.parquet` (30,616 matches, 2015-2025, surface/level/round/ranks/score/
retirement), `match_stats.parquet` (59,312 rows, per-match serve lines -- aces, double faults,
1st/2nd serve win%, break points), and a 33,952-row odds corpus (2015-2025, bet365 + Pinnacle).
Point-by-point data is **absent** -- `data/cache/sackmann_pbp/` is an empty directory.

**Capture cadence:** in-play market capture is the heaviest of any sport measured here -- 39k
pregame lines / 119k in-play ticks / 767 depth entries (2026-07, Kalshi + Pinnacle).

**Claims/intelligence:** ~13,677 VERIFIED claim rows -- `tennis_fatigue_schedule_density` (10,914,
now `BUILT`) dominates, followed by `tennis_p1_match_context` (1,312) and `tennis_p2_match_context`
(1,346), plus `tennis_claims_v3`/`v4`, `hold_claims`, `h2h_claims`, and `h2h_index_claims`.
`hold_return_surface_splits`, `set_detail`, and `playstyles_h2h` are `BUILT`.

**Model + vs-close verdict:** match-win **BEHIND on freshness** (Brier 0.2177 vs close 0.2028,
n=7,374 ATP, gap +0.0149 -- surface-Elo + Platt calibration vs the devigged Pinnacle close; ATP
closes are very efficient). WTA runs its own live recalibrator (temperature T=1.36, holdout ECE
0.045 -> 0.019) -- a calibration win, reported as calibration, not a market row.

**Biggest gap:** true pressure-point splits (deuce sequences, break-point-as-played, tiebreak
sequencing) are not derivable at all without point-by-point data -- only match-aggregate serve
lines exist, so `pressure_aggregate_bp` stays `PARTIAL` and any point-order claim is out of reach
until that corpus exists. **Closed classes:** none.

---

## WNBA

**Data on disk:** the shallowest per-player footprint of any built sport -- no player boxscores
and no play-by-play on disk. `cdn_backfill_states.parquet` (504 rows, 3 checkpoints/game across
168 games) carries lineup strings, team fouls, bonus state, and run-momentum flags; scoreboard/
linescore data spans 2024-05..2026-07 (~770 rows); context tables cover injuries, referee-crew foul
rates, schedule density, and attendance.

**Capture cadence:** cross-sport market loops (`line/inplay/depth` history, 20k lines / 200k ticks
/ 1.6k depth entries, 2026-07, Kalshi) -- the CDN checkpoint capture itself is snapshot-based (3
checkpoints/game), not a continuous tick feed.

**Claims/intelligence:** 8 VERIFIED claim rows (`wnba_claims`). Small in count, but the underlying
family set is real and shipped: `elo_pregame_strength`, `referee_crew_foul_rates`,
`schedule_density`, and `foul_bonus_ingame_states` are all `BUILT`.

**Model + vs-close verdict:** not in the current beat-the-close scoreboard run (offseason cadence
at time of writing); the pregame Elo gate and in-game foul/bonus blend are the sport's shipped
calibration surfaces.

**Biggest gap:** no player boxscores and no play-by-play means player-trait profiles (the NBA
atlas equivalent) are not derivable at all from what's on disk -- lineups exist only as 3
checkpoints per game, not a continuous state. **Closed classes:** none.

---

## NPB (Nippon Professional Baseball)

**Data on disk:** results-only. `npb_results.parquet` (3,976 rows, 2022-03..2026-07) carries date,
teams, scores, home-win flag, and tie flag -- 8 columns total, no player-, pitch-, or lineup-level
data of any kind.

**Capture cadence:** cross-sport market loops only (12.9k lines / 46.8k ticks / 883 depth entries,
since 2026-07-04, Kalshi) -- the results corpus itself updates game-by-game, not live-tick.

**Claims/intelligence:** 4 VERIFIED claim rows (half of the shared `npb_kbo_claims` store: team
win%, run-diff/game, home win%, away win%, `full_asof`). `team_strength_pregame` and
`ingame_base_model` are `BUILT` on top of that team-level table.

**Model + vs-close verdict:** not in the current beat-the-close scoreboard run; the team-strength
pregame gate and post-fix in-game base model are the sport's shipped surfaces.

**Biggest gap:** below team-game grain there is nothing -- no player, pitch, or lineup data, and
odds history only starts 2026-07-04, so anything requiring a longer market history is blocked.
**Closed classes:** none.

---

## KBO (Korea Baseball Organization)

**Data on disk:** results-only, the same 8-column shape as NPB (`kbo_results.parquet`, 3,263 rows,
2022-04..2026-07). One live-capture recipe has been proven but not yet run continuously: a single
Naver relay probe (`naver_relay_live_sample_2026-07-05.json`) confirmed live inning/base/out state
is reachable through that feed.

**Capture cadence:** cross-sport market loops (10.8k lines / 57k ticks / 1.6k depth entries, since
2026-07-04, Kalshi) plus daily slate/close-report snapshots (`data/domains/kbo/slate_*.json`). The
Naver relay live-state feed is **recipe-proven, not yet accruing** a persistent corpus.

**Claims/intelligence:** 4 VERIFIED claim rows (the other half of `npb_kbo_claims`: team win%,
run-diff/game, home win%, away win%). `team_strength_pregame` and `ingame_base_model` are `BUILT`.

**Model + vs-close verdict:** not in the current beat-the-close scoreboard run; same shipped
surfaces as NPB (team-strength pregame gate, in-game base model verdict).

**Biggest gap:** results-only below team-game grain, same as NPB -- but KBO additionally has a
proven-but-unbuilt path to a live base-out state corpus (the platform's #5-ranked unbuilt family,
porting the MLB GUMBO state-machine pattern to a live-daily sport). **Closed classes:** none.

---

## Cross-sport summary

**Beat-the-close scoreboard** (`scripts/platformkit/beat_the_close_scoreboard.py`, honest framing
verbatim: *"our model vs the devigged closing line on the SAME real outcomes. MATCH = within
sampling noise; BEHIND = the market's freshness (injury/lineup) edge a public/box model cannot
see. Calibration/accuracy only -- NOT a $ edge."*):

| Sport | Market | Metric | n | Our model | Close | Gap | Verdict |
|---|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 372 | 0.1735 | 0.1672 | +0.0063 | MATCH |
| NBA | total (O/U) | RMSE | 372 | 19.172 | 18.114 | +1.058 | BEHIND (freshness) |
| MLB | moneyline | Brier | 13,992 | 0.2429 | 0.239 | +0.0039 | MATCH |
| MLB | total (O/U) | RMSE | 1,679 | 4.719 | 4.441 | +0.2777 | BEHIND (freshness) |
| Soccer | O/U-2.5 | Brier | 7,558 | 0.2465 | 0.239 | +0.0076 | MATCH |
| Tennis (ATP) | match-win | Brier | 7,374 | 0.2177 | 0.2028 | +0.0149 | BEHIND (freshness) |

On team-strength win markets (NBA and MLB moneyline) the model MATCHES the devigged close within
noise; MLB's small deficit is pitcher-blindness (the close prices the starting pitcher, the model
does not, yet). On totals and derived markets (NBA totals, MLB totals, soccer O/U-2.5, ATP
match-win) the gap is the market's freshness edge -- injuries, lineups, weather, park, starting
pitcher -- information a public/box-score model does not see and a closing line does. Closing the
remaining gaps needs either a freshness feed (forward-looking build) or deeper in-game
conditioning, not a cleverer pregame model.

**Claim corpus by sport** (VERIFIED rows, `data/cache/intel_claims/*_validation.json` +
`data/frontend/ops/*validation*.json`, 2026-07-10):

| Sport | VERIFIED claims | Dominant store |
|---|---|---|
| NBA | ~61,665 | `nba_player_box_rate` (59,268) |
| MLB | ~21,377 | `mlb_bullpen_fatigue_chains` (9,060) + `mlb_batter_rate` (7,452) + `mlb_pitcher_rate` (4,434) |
| Tennis | ~13,677 | `tennis_fatigue_schedule_density` (10,914) + `tennis_p1/p2_match_context` (2,658 combined) |
| Soccer (intl) | ~1,461 | `soccer_intl_team_travel_rate` (1,458) |
| WNBA | 8 | `wnba_claims` |
| NPB | 4 | `npb_kbo_claims` (NPB half) |
| KBO | 4 | `npb_kbo_claims` (KBO half) |
| Cross-sport (gate verdicts) | ~16 | `intel_verdict_claims` |

**Platform-wide top-10 unbuilt families** (from the census, ranked by leverage; as of 2026-07-10,
three families formerly on this list -- soccer `referee_card_foul_profiles`, MLB
`bullpen_fatigue_chains`, and tennis `fatigue_schedule_density` -- have shipped `BUILT` with
VERIFIED claim rows and are covered in their sport sections above, not repeated here): NBA
`lineup_reconstruction` (#1, keystone -- on/off, gravity, lineup-vs-lineup, and spacing all block
on it), NBA `on_off_splits` (#2), NBA `gravity_proxy` (#3), NBA `lineup_spacing_from_shot_xy` (#4),
KBO `naver_relay_state_accrual` (#5), cross-sport `depth_imbalance_descriptors` (#6), WNBA
`lineup_exposure_descriptors` (#7). NBA lineup reconstruction is the single highest-leverage build
because four other unbuilt families depend on it directly.

**Do-not-reopen list** (closed with a recorded honest REJECT, cited so a future pass does not
re-run the same test): NBA in-game hot-night/scheme-fit, MLB in-game SP-velocity fatigue, soccer
home-SOT replication, MLB pregame stack L3.

---

*Related: [`docs/INTELLIGENCE.md`](INTELLIGENCE.md) - [`docs/ASK_SURFACES.md`](ASK_SURFACES.md) - [`docs/MARKET_EFFICIENCY_PROOF.md`](MARKET_EFFICIENCY_PROOF.md) - [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-07-10*

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
