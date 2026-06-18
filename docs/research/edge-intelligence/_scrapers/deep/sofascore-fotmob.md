# DATASOURCE -- Sofascore / FotMob (deeper per-player soccer stats: tackles/passes/xG)

_Deep per-datasource spec. Part of the edge-intelligence corpus (_scrapers/deep/). This
is the D1 MISSING source: the deeper per-player soccer stats that ESPN does NOT expose --
tackles, interceptions, passes, key passes, touches, dribbles, xG, xA, progressive
carries, positional minutes -- which drive most soft DFS soccer props. It directly
attacks the binding thinness cap on the WC prop vertical (espn-summary.md / deep-dive 12
sec 5) and the freshness gap (confirmed lineups, A3). Per the deepest-data north star,
DEPTH in a beatable pocket is the lever that moves the ceiling. UNBUILT. Markets are
efficient; this adds DATA DEPTH, not an asserted edge. ASCII only._

STATUS: MISSING (no code under domains/ or scripts/ references sofascore/fotmob -- grep
confirms zero hits). KEY: KEYLESS-ish (unofficial public JSON endpoints; anti-bot risk).
EDGE-UNLOCK: P1 (better-calibrated per-player prop distributions) + A3 freshness. TIER:
HYPOTHESIS. RANK: highest among MISSING for the active soccer vertical.

---

## What it fills (the gap, concretely)

ESPN summary + athlete-overview give shots/SOT/fouls/cards/assists/offsides/saves only.
The soft DFS soccer prop ladder (PrizePicks/Underdog) routinely lists: tackles,
shots-on-target, passes, passes-attempted, fouls, fouls-drawn, shots, clearances,
crosses, dribbles, plus goal/assist. The stats in **bold gap** below have NO keyless
source today:
- HAVE (ESPN): shots, SOT, fouls committed/suffered, cards, assists, offsides, saves.
- **MISSING (this source): tackles, interceptions, total/accurate passes, key passes,
  touches, dribbles/take-ons, clearances, blocks, xG, xA, progressive passes/carries,
  duels, positional minutes, and CONFIRMED pre-match lineups.**

## Candidate endpoints (unofficial public JSON -- probe, do not assume stable)

These are the publicly observable JSON backends. Treat every shape as UNVERIFIED until
probed and recorded (mirror the FanDuel-probe discipline, data-acquisition.md B5).

Sofascore (`api.sofascore.com/api/v1`):
```
GET /sport/football/scheduled-events/{YYYY-MM-DD}     # event ids for a date
GET /event/{eventId}/lineups                           # confirmed lineups + per-player
                                                       #   statistics{} block (the depth)
GET /event/{eventId}/player/{playerId}/statistics      # per-player per-match stats
GET /player/{playerId}/statistics/...                  # club-season aggregates (prior)
```
FotMob (`www.fotmob.com/api`):
```
GET /matches?date=YYYYMMDD          # match ids for a date
GET /matchDetails?matchId={id}      # content.lineup + content.playerStats (tackles,
                                    #   passes, xG, fotmob rating, etc.)
GET /playerData?id={playerId}       # season per-90 + percentile stats (prior)
```

Acquisition notes (keyless-ish):
- No API key, but both employ ANTI-BOT (UA checks, rate limits, occasionally a rotating
  header / signed param). Sofascore lineups/statistics have historically been fetchable
  with a plain browser UA + modest rate limiting; FotMob's `matchDetails` is the more
  stable JSON. Expect breakage; this is the SAME fragile risk class as Underdog/
  PrizePicks (deep-dive 03 sec 5).
- HARD CONSTRAINT (data-acquisition.md D4 / deep-dive 03 plan item 10): do NOT build a
  Playwright/headless-browser scraper. Only ingest via a legitimate public JSON endpoint
  reachable with urllib + a browser UA (the espn/statsapi pattern). If an endpoint needs
  a signed token or JS execution to fetch, it is OUT OF SCOPE -- skip it, do not automate
  a browser.

## Proposed per-player schema (the ingest contract to BUILD)

A new `domains/soccer/ingest_sofascore.py` (or `ingest_fotmob.py`) mirroring
`ingest_espn_players.py`: injectable `http_get`, pure parse fn, honest-degrade to []
on any error, write/merge a parquet dedup on `(event_id, player_id)`. One row per player
per match:

| column | meaning |
|---|---|
| `event_id`, `provider`, `league`, `date` | join + as-of key; `provider` tags source |
| `player_id_src`, `player`, `position`, `team_abbr`, `home_away` | id is the SOURCE's id |
| `espn_player_id` | RESOLVED ESPN id (the cross-source join target; see resolver below) |
| `minutes`, `started` | exposure (these sources give REAL minutes, not the 90-surrogate) |
| `tackles`, `interceptions`, `clearances`, `blocks`, `duels_won` | defensive props |
| `passes`, `passes_accurate`, `key_passes`, `crosses` | passing props |
| `touches`, `dribbles`, `take_ons` | involvement props |
| `shots`, `shots_on_target`, `xg`, `xa` | shooting (xG/xA are the NEW depth) |
| `fouls`, `fouls_drawn`, `offsides` | discipline |
| `as_of` | ingest date |

## Which engine would consume it

- `domains/soccer/player_rates.py` -- ADD the new stat columns to `CANON_TO_COLS`
  (`player_rates.py:35`) so `player_rate` produces shrunk per-90 priors for tackles/
  passes/xG exactly as it does for shots today. REAL minutes from this source replace the
  `starts`-as-90 surrogate (espn-athlete-overview.md) -> a genuinely better denominator.
- `domains/soccer/prop_engine.py` -- ADD the new canonical stats to the prop board so it
  can price tackles/passes/SOT/etc. (the markets soft books actually post).
- `domains/soccer/player_resolver.py` -- the join hub: resolve `player_id_src` ->
  `espn_player_id` so this source BLENDS with the ESPN corpus rather than forking it
  (name + team + position match, biased to false-negatives like `teams_match`).
- xG/xA additionally feed FINISHING priors (`domains/soccer/finishing_prior.py` /
  `finishing_asof.py`) -- a player's xG vs realized goals is a finishing-skill signal.

## Refresh cadence

- Per-match post-match (final stats): once a match completes, same as ESPN players.
- CONFIRMED LINEUPS (the freshness lever): poll `/lineups` / `matchDetails` from ~1 hour
  pre-kickoff until kickoff; stamp `confirmed_at`. A confirmed start vs bench flips a
  player's minutes prior entirely -> this is the A3 freshness unlock for soccer props.

## Leak rules (as-of, binding)

1. Post-match per-player stats are REALIZED -> a player's own row for match M is never a
   feature for M. As-of join on `date < kickoff` (same guard as ESPN players).
2. Club-season aggregates (`/player/.../statistics`, `playerData`) are PRIOR FORM; same
   as-of caveat as the ESPN club prior -- trim any in-progress-season split that spans
   PAST the target kickoff before using it as a prior (espn-athlete-overview.md leak gap).
3. CONFIRMED lineups are usable only once OFFICIALLY confirmed AND timestamped before
   kickoff; "predicted/probable" lineups flip -- stamp `confirmed_at`, never feed a
   probable lineup as confirmed.
4. xG is a MODEL output of the provider (not a raw count); treat it as a provider-derived
   feature with its own noise, validate parity across Sofascore vs FotMob before trusting.

## Proof method (how to validate before trusting it for the board)

1. PARITY: for the overlapping ESPN stats (shots, SOT, fouls, cards, assists), the
   Sofascore/FotMob per-match value must MATCH the ESPN value within rounding on a sample
   of matches. A systematic disagreement = a parsing/definition bug, not new signal.
2. LEAK-FREE CALIBRATION: with the new tackles/passes/xG priors wired, re-run the soccer
   prop signal-audit (the real leak-free gate) and compare OOS Brier/BSS of the prop
   `P(over)` to the ESPN-only baseline. SHIP only on a multi-fold, >=2-corpus improvement;
   single-fold lifts are artifacts (proof-standards.md).
3. CLV (final bar, real money): once Underdog/PrizePicks soccer props are wired (a
   devig-able price), measure CLV on the new-stat props vs the close.

## Honest caveats / gaps

- FRAGILE + ToS-sensitive: unofficial endpoints, anti-bot, no stability guarantee. Build
  an honest-degrade contract (return [] on any failure, never fabricate) and a live-probe
  smoke test that RECORDS the real payload shape (it WILL drift). Do not block the board
  on it.
- The depth only helps if the MARKET posts those props AND we can devig them -- pair this
  build with the Underdog/PrizePicks soccer prop wiring (D2) so the new stats are testable
  against a price, not just a model_view.
- This is a HYPOTHESIS-tier unlock: it plausibly lifts prop calibration in the data-
  starved soccer vertical, but no calibration or CLV evidence exists yet. Rank it the top
  MISSING soccer build, behind only un-stranding a devig-able prop price to grade it.
