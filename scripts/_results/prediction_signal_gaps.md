# Prediction Signal Gap Analysis (cycle 78d research)

Research-only, no code change. Synthesizes industry consensus (Unabated,
RotoWire, RotoGrinders, DailyFantasyFuel, FTA, NBAstuffer, Action Network,
Wager Wisdom) on what sharp NBA-prop models use, vs what
`prop_pergame.feature_columns()` currently feeds the 7 stat models.

Master cross-referenced: `f198b0ce` (cycle 45 rejected probes) + `CLAUDE.md`
`Saturated angles` section + the `prop_pergame.py` inline cycle-N comments.

---

## Already in the system

From `prop_pergame.feature_columns()` (cycle 47 production, ~85 columns):

**Player form (per-stat × {pts, reb, ast, fg3m, stl, blk, tov, min}):**
- `l5_<stat>`, `l10_<stat>`, `std_<stat>`, `ewma_<stat>`, `prev_<stat>`

**Game context:**
- `rest_days`, `is_home`, `games_played`
- `days_since_last_game` (unclamped to 100d), `games_since_long_absence`
  (rampup signal — first game back from 7+ day absence)

**Opponent defense:** `opp_def_{stat}` for all 7 stats — to-date allowed/league
ratio, leak-free bisect.

**Travel/rest:** `is_b2b`, `is_b3b`, `miles_traveled`, `altitude_ft`
(parquet-backed).

**Play-type frequency (Synergy, per player-season):** `pt_isolation_freq`,
`pt_prballhandler_freq`, `pt_prrollman_freq`, `pt_postup_freq`,
`pt_spotup_freq`, `pt_handoff_freq`, `pt_cut_freq`, `pt_offscreen_freq`,
`pt_transition_freq`.

**BBRef advanced (per player-season):** `usg_pct`, `ts_pct`, `three_par`, `ftr`,
`ast_pct`, `stl_pct`, `blk_pct`, `tov_pct`, `ws_per_48`, `per`, `obpm`, `dbpm`,
`dws`, `ows`, `vorp`.

**Contracts:** `salary_log`, `cap_hit_pct`, `year` (contract-year flag),
`years_remaining`.

**Ratio:** `pts_share_3pt` (cycle-4 ratio surviver).

**Auxiliary (built/dormant, NOT in feature_cols):** officials crew, prior-season
player tracking (Drives/Passing/CatchShoot), per-game advanced rolling stats —
all WIRED but disabled after walk-forward regressions.

**Live ops infra already shipped (cycles 43-71):** ESPN+NBA injury fetchers,
Rotowire lineups, DraftKings/Odds-API line ingest, daily orchestrator, bet log,
settlement, ledger summary, calibrated quantile intervals, Kelly sizer. The
serving layer KNOWS about injuries/lineups (skips OUT players, scales by
status), but the MODELS DO NOT — features are still computed as if everyone
plays.

---

## TIER 1 — High-impact gaps NOT YET TRIED

| Signal | Source | Effort hrs | Expected impact | Sketch |
|---|---|---|---|---|
| **Vegas game total + spread (point-in-time)** | DK / Odds API → `data/lines/<date>.csv` (already ingested) | 4 | MEDIUM-LARGE (–1 to –3% MAE on PTS/REB; biggest single non-injury gap) | Add `vegas_total`, `vegas_spread`, `implied_team_total = total/2 - spread/2` as 3 features; historical: scrape from oddsshark/sbrforum CSV or backfill via odds-API archive |
| **Projected minutes (replaces `l5_min` blindly)** | Rotowire lineups + injury report (both already fetched) | 6 | LARGE (industry consensus says minutes IS the prop edge) | Project minutes from {starter_status, depth_chart_position, teammate availability, blowout-risk-from-spread, b2b}; replace `l5_min` family with `proj_min` + keep form features for per-minute rates |
| **Teammate-out usage absorption** | injury_report + lineups + per-player usage% | 8 | MEDIUM-LARGE | When a 25%+ USG teammate is OUT, compute that USG redistribution to remaining starters (weighted by their own usage). Add `teammate_usg_absorbed` per row |
| **Blowout-risk feature** | Vegas spread + own team's pace | 1 | SMALL-MEDIUM (specifically helps PTS over/under bias) | `blowout_risk = |spread| / 7.0` clipped 0-1.5; interacts with starter status to depress projected late-game minutes |
| **Vegas implied team total × player USG** | Vegas + bbref_usg_pct (already loaded) | 1 | SMALL-MEDIUM | `proj_team_pts = implied_team_total`; `expected_pts_from_usg = proj_team_pts × usg_pct × ts_pct`. Cheap interaction trees can't easily learn from raw fields |
| **Defender matchup at position (DvP, not just team)** | NBA Stats `leaguedashptdefend` by position | 6 | MEDIUM (current `opp_def_*` is team-level only) | `def_vs_pos_<stat>` — opponent's allowed FPP for the player's listed position. Industry calls DvP the single most-used DFS edge |
| **Position-aware opponent defense** | nba_api `commonplayerinfo` (position) + existing opp factors | 2 | SMALL-MEDIUM | Same data we have, but split `opp_def_pts` into `opp_def_pts_vs_C/F/G` so a player's position picks the right matchup factor |
| **Sportsbook line as a feature** | DK ingest (already shipped cycle 59) | 2 | LARGE for ROI / SMALL for raw MAE | The line embeds the market's full information set. Adding `book_line` as a feature acts as a teacher; predict residual vs line, ship the recentered prediction |
| **Pace (true possessions/48) of both teams** | NBA Stats `leaguedashteamstats` `PACE` | 2 | SMALL-MEDIUM | `team_pace`, `opp_pace`, `combined_pace`. We have `opp_def_*` but not raw pace — pace drives volume on ALL counting stats |
| **Recent-minutes-only form (vs total form)** | Filter existing gamelog by MIN >= 20 | 1 | SMALL | Adds `l5_when_starting_pts` etc. — strips out garbage games where the player got pulled. NBAstuffer specifically calls out "L10 is a trap when minutes vary" |

---

## TIER 2 — Medium-impact gaps

| Signal | Source | Effort hrs | Expected impact |
|---|---|---|---|
| **Days since last 30+ min game** (sandbagging detector) | gamelog | 2 | SMALL |
| **Opponent injury status (their stars OUT lowers defense)** | injury_report cross-team | 4 | SMALL-MEDIUM |
| **Foul-rate × ref-crew interaction** (officials infra exists) | `data/officials_features.parquet` (already built, was rejected solo) | 3 | SMALL — re-test ONLY as interaction with `bbref_ftr` |
| **Coach rotation tendency** (does this coach play starters in blowouts?) | Hand-built table from L20 blowouts per coach | 6 | SMALL-MEDIUM |
| **Same-game player correlations** (for SGP/parlay edge, not MAE) | model output covariance from MC sims | 6 | LARGE for parlay ROI, ZERO for single-leg MAE |
| **Closing-line movement as a feature** (line drift = sharp signal) | DK historical poll | 8 | SMALL — directional info already in closing line |
| **Public bet %** (fade public) | Action Network scrape / SBR | 4 | SMALL-MEDIUM for ROI, near-zero for MAE |
| **Recent shot quality (xFG from CV)** | CourtVision pipeline (10 games processed) | 20+ | MEDIUM eventually, blocked by data volume — see CLAUDE.md moat |
| **Player tracking IN-SEASON aggregates** (not prior-season) | leaguedashptstats current season cumulative | 6 | SMALL — prior-season version regressed (cycle 14), in-season might survive |
| **Per-month adv stats** (vs current per-game) | aggregate existing parquet by month | 3 | SMALL — addresses cycle-6/8 covariate-shift complaint |

---

## TIER 3 — Long shots

| Signal | Source | Effort hrs | Expected impact |
|---|---|---|---|
| Beat-writer Twitter sentiment 90 min pre-tip | Twitter API ($) + LLM | 20 | SMALL — noisy, lagged behind official report |
| Weather (only matters for road game energy via flights) | NWS API | 4 | NONE-SMALL |
| Refs assigned (single ref tendency, not crew) | already cached, was disabled cycle 15 | 2 | NONE — already proven negative |
| Player props prop-prop arbitrage across books | DK + FD + MGM scrape | 16 | LARGE for arb, ZERO for MAE |
| Crowd attendance / TV audience | unreliable | – | NONE |

---

## REJECTED ANGLES (don't re-test)

From `prop_pergame.py` inline comments and `f198b0ce`:

- **Tweedie loss for TOV** (cycle 25) — regressed.
- **HGB-q50, q50-bag5, shift_q45/q55, robust-median q40+50+60** (cycles 31-34).
- **CatBoost as 4th NNLS learner** (cycle 13) — max -0.0035 MAE.
- **Prior-season player tracking (Drives/Passing/CatchShoot) as features**
  (cycle 14) — regressed 5/7 stats. Year-over-year role drift.
- **Officials crew tendencies (fouls, FTA, home win pct) as standalone
  features** (cycle 15) — regressed all 7 stats on walk-forward.
- **Per-game advanced rolling stats (USG/TS/AST%/REB%/PIE L5/L10/EWMA)**
  (cycles 6, 8) — regressed 5/7. Form features already span this signal.
- **WinProb residual MLP / Beta calibration / focal loss** (cycle 45) — WinProb
  model architecture saturated. Remaining WP gains are DATA, not algorithm.
- **Multitask bootstrap for AST/STL** (cycle 45) — same-data seed averaging
  already extracts the diversity.
- **Huber on log1p for the 6 log stats** (cycle 19) — washed except PTS, where
  sqrt+Huber already shipped (cycle 18).
- **Per-minute rates as features** (cycle 4) — 95% collinear with `l5_min`
  × counting stat already learnable by trees.
- **AST q50 dispatch** (cycle 27) — WF 4/4 positive BUT prod single-split
  regressed +0.0157. Don't ship q50 for AST.
- **Older seasons (4+) in training set** (cycle 19, WinProb) — 2-season default
  beats 4-season. Recency > volume. (Per-prop pipeline currently uses recency-
  decay weighting, similar effect.)

Almost recommended but caught:
- "Per-player tracking features" — saturated (cycle 14).
- "Officials crew" — saturated (cycle 15).
- "Per-game advanced rolling" — saturated (cycles 6, 8).
- "Older-season weighting tweak" — recency_decay=0.5 already tuned.
- "CatBoost as a 4th learner" — saturated (cycle 13).

---

## Recommended next 3 cycles

### Cycle 78e — Vegas total + spread + implied team total as 3 features

The single biggest unrepresented signal class. Game environment (pace,
projected score) is what every industry model uses first and it's missing
here. Backfill historical: write `scripts/fetch_historical_lines.py` against
sbrforum / oddsshark CSV exports (5 NBA seasons of game-level open/close
spreads/totals). Add to `feature_columns()`:
`vegas_total`, `vegas_spread`, `implied_team_total = total/2 -
sign(home)*spread/2`. Train on the 70% of historical rows where we have
coverage; impute neutral (`total=225, spread=0`) for the rest. Walk-forward
gate as always. Expected: -1 to -3% MAE on PTS/REB; smaller on STL/BLK/TOV.

### Cycle 78f — Projected minutes feature (replaces blind L5_min trust)

We already have lineups + injury fetchers. Build a `proj_min` function:
`base = ewma_min` clipped by lineup status (STARTER=1.0×, QUESTIONABLE=0.75×,
BENCH=0.30×, OUT=0.0×, NO-GAME=0.0×). Add `proj_min` and `min_uncertainty =
|ewma_min - l5_min|` as features. Critically, COMPUTE per-minute rates
(`l5_pts_per_min` etc.) and let the trees blend them with `proj_min`. The
industry consensus is unanimous: minutes is the #1 driver of prop accuracy.
RotoWire, RotoGrinders, FTA all lead with this. Risk: features need to be
HISTORICALLY available (we don't have historical lineup tags). Use
`MIN > 20 = starter` as historical proxy; live features come from the
already-shipped fetchers.

### Cycle 78g — Teammate-out usage absorption + DvP (position-aware defense)

Two cheap signals that interact. (a) For each row, look up which 25%+-USG
teammates were OUT that game (`fetch_historical_injuries.py` already exists)
and compute `teammate_usg_absorbed = sum(out_teammate_usg) × this_player_role_weight`.
(b) Pull `leaguedashptdefend` once per season, split `opp_def_*` into
`opp_def_*_vs_pos` using `commonplayerinfo.position`. Industry calls DvP the
single most-cited DFS edge. Walk-forward gate. Expected: small-medium for both,
but the historical-injury linkage will compound the projected-minutes signal
from 78f (when a star is OUT, his teammate's USG absorbs AND his minutes go up).

---

## Closing note

The CLAUDE.md "remaining gains are DATA problems" call is correct. The 3
proposed cycles are all data wires, not new algorithm probes. Each leverages
infra already shipped in cycles 43-71 (lineups, injuries, DK lines, historical
injuries) — only requires HISTORICAL backfill + wire-in to
`feature_columns()`. Per the dual ship gate (4/4 WF folds + single-split MAE
strictly down) baked into every cycle this loop.
