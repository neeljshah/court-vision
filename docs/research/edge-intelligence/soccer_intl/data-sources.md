# soccer_intl -- DATA SOURCES (have / missing / how-to-get) + the freshness gap

_Part of the edge-intelligence corpus. Every data source the WC prop vertical needs, what we
HAVE (path, rows, freshness), what is MISSING, and HOW-TO-GET (keyless where possible). Grounded
in domains/soccer/ingest_* + the live parquets under data/domains/soccer/. ASCII only._

## HAVE (on disk, observed 2026-06-18)

| Source | Path | Shape / freshness | Role | Built by |
|---|---|---|---|---|
| WC per-player post-match box | `data/domains/soccer/espn_player_stats.parquet` | 1241 rows, 23 cols, 24 events, 1241 distinct player_id, **every player exactly 1 WC match**; dates 2026-06-11..06-17 (updated 06-18 09:08) | settlement source + WC-history rate substrate | `domains/soccer/ingest_espn_players.py` (keyless ESPN) |
| Club-season priors | `data/domains/soccer/espn_club_priors.parquet` | 8741 rows, 6 cols (player_id, stat_canonical, total, starts, per_start, as_of), 960 players (960/1241 WC players covered) | the "0 -> reliable edges" unlock; lifts ~1-match players to non-thin rates | `domains/soccer/ingest_espn_athlete.py` (keyless ESPN athlete-overview) |
| Per-stat OOS calibration cache | `data/domains/soccer/prop_calibration.json` | overall n=6620, 662/stat, mode "strict leak-free +opp-adj"; Saves bss +0.3365, Fouls +0.0339 | the tier source the board reads | `scripts/platformkit/props_eval.py --cache` |
| Isotonic recal knots | `data/domains/soccer/prop_recal.json` | ~100KB fitted; **DEFERRED** (not applied at board) | recal candidate (stranded; overfit) | `domains/soccer/prop_recal.py` |
| Match stats (team) | `data/domains/soccer/espn_matchstats.parquet`, `match_stats.parquet` | 61KB / 732KB | team scoreline model substrate (NOT consumed by props) | `ingest_espn_box.py`, `ingest_footballdata_matchstats.py` |
| Matches / odds | `matches.parquet` (467KB), `odds.parquet` (591KB) | club-history corpus | team-model backtest (separate vertical) | `ingest_footballdata.py` |
| As-of features | `asof_features.parquet` (3.3MB) | club corpus | team model | `asof_features.py` |
| Paper ledgers | `data/frontend/prop_ledger.jsonl` (~1MB), `prop_line_history.jsonl` | prop_ledger ~1MB; **prop_line_history ~1 line** | paper accrual + (intended) CLV | `prop_paper.py`, `prop_line_history.py` |

### Column inventory (espn_player_stats.parquet)
`event_id, league, team_abbr, home_away, player_id, player, position, starter, subbed_in,
subbed_out, minutes, minutes_estimated, totalShots, shotsOnTarget, foulsCommitted, foulsSuffered,
yellowCards, redCards, goalAssists, offsides, totalGoals, saves, date`. These 11 raw stat columns
map to the 10 canonical props via `CANON_TO_COLS` (player_rates.py:35). Position is granular
(CD-R/CM-L/AM/G/SUB etc -- 683 are "SUB"), giving a real role signal for position-conditioned
dispersion (model-levers.md lever 6). `minutes_estimated` is all-False today (minutes are observed,
not imputed).

## MISSING (the gaps that cap the vertical)

| Missing source | Why it matters | Current consequence |
|---|---|---|
| **Closing prop lines** | CLV is the only bridge from calibration to $ (edge-theory.md). | `prop_line_history.jsonl` ~1 line -> EVERY CLV metric is None (06 sec 5 #3). No edge can ever graduate. THE #1 gap. |
| **Predicted/confirmed lineups (pre-kickoff)** | Minutes projection is the biggest unmeasured live-board error (04 sec 5). | `player_minutes.expected_minutes` (player_minutes.py:29) projects from the player's OWN priors only -- with 1 prior match it is near-blind; no injury/rotation/lineup signal. |
| **Deeper per-match event stats (Sofascore-grade)** | xG, key passes, touches in box, shot location, duels -- richer rate inputs + joint-prop structure. | We only have ESPN box counts; Shots/SOT can't be jointly modeled coherently (independent marginals -- 04 sec 6 #10). |
| **Point-in-time club-season series** | club_priors is a single `as_of` snapshot (per_start, as_of=2026-06-17) -> the club-augmented calibration mode has a documented mild lookahead (04 sec 5). | Shipped cache uses strict leak-free mode (correct), so club-prior calibration is unmeasured leak-free. |
| **Sub-appearance minutes for club per90** | `ingest_espn_athlete` uses `starts` as the per-90 denominator (ignores sub apps) -> per_start->per90 is a mild OVER-estimate, nudging lam up for rotation players (04 sec 5). | Systematic upward lam bias for rotation players. |
| **Multi-tournament prior corpus** | A 2nd independent corpus (prior WC / continental / club leagues) to confirm per-stat skill OOS before promoting (04 sec 6 #11). | Every "proven" claim rests on ONE small tournament -> selection-artifact risk. |
| **DFS line snapshots over time (PrizePicks/Underdog movement)** | DFS pick'em has no two-way close (edge-theory.md); the honest proof is P(over) calibration + realized ROI + LINE MOVEMENT. | We scrape current lines (prop_prizepicks.py / prop_underdog.py) but do not store the movement series. |

## HOW-TO-GET (keyless-first)

- **WC box + athlete club priors:** already keyless via ESPN (`ingest_espn_players.ingest_range`,
  `ingest_espn_athlete.build_club_priors`). ACTION: keep ticking after each matchday -- the dominant
  lever is simply more rounds (04 sec 6 #1). This is the cheapest improvement and unblocks
  leak-free per-player WC rates (which barely exist until players reach 2+ matches).
- **Closing prop lines (keyless):** schedule a `prop_loop`/`schedule`-agent tick every ~10-15 min up
  to kickoff so `prop_line_history.log_board_lines` accrues a closing snapshot (06 sec 6 #1). The
  code exists; it is a scheduling/ops fix, not a code gap.
- **Predicted lineups (keyless-ish):** ESPN match preview / lineup endpoints expose probable XIs
  near kickoff; a coarse "in probable XI? yes/no" flag would already sharpen `expected_minutes`
  far beyond the 1-prior-match estimate (04 sec 6 #9).
- **Sofascore deeper stats:** richer per-player event data (xG, touches, key passes) -- the biggest
  data-depth unlock named in the task. Acquisition is harder (rate-limited / anti-bot); document
  the scraper under `_scrapers/` before relying on it; treat as a medium bet, not a quick win.
- **DFS line movement:** extend the existing PrizePicks/Underdog providers to append each scrape to
  a movement log (reuse prop_line_history schema), giving the DFS-pick'em proof path its movement
  signal.

## The same-day FRESHNESS gap (the structural ceiling here, as everywhere)
The model prices off priors (WC box + club season). The two same-day facts it CANNOT see are
(a) **who actually starts / how long** (lineup + rotation -- projected via 1 prior match only), and
(b) **late line movement** (we don't store the closing snapshot). Both are the freshness lever that
the project repeatedly finds to be the only unmodeled edge (MEMORY: NBA/MLB "real fix = same-day
freshness"). For soccer_intl specifically, LINEUP freshness is the dominant one: a star left on the
bench collapses every prop for that player, and the model has no signal for it until kickoff. Capturing
predicted lineups + closing lines converts both unmeasured risks into measured ones.
