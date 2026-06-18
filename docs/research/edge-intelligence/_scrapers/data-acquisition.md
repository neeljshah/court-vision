# DATA-ACQUISITION INTELLIGENCE -- every source, what it unlocks, ranked by edge value

_Part of the edge-intelligence corpus (_scrapers/). The complete census of every data
source the system uses, should use, or is missing -- with the schema, endpoint, keyless/
keyed status, refresh cadence, leak rules, and wired/stranded/missing state for each.
Grounded in project-deep-dive 03 (odds + prop scrapers) and 12 (data inventory + ops) and
in the live code under `scripts/platformkit/odds_provider/` and `domains/<sport>/`.

Honesty rails (binding): markets are efficient; the north star is CALIBRATION vs the
devigged close, NOT a $-edge. Every "edge" a source unlocks is a CANDIDATE (tier:
HYPOTHESIS) until calibration- then CLV-proven. Sources are ranked by EDGE-UNLOCK VALUE
= how much they move us toward a beatable pocket (per the beatable-pocket thesis in
edge-theory.md), not by raw data volume. ASCII only._

---

## How to read the ranking

Each source is tagged with:
- STATUS: WIRED (a consumer reads it today) / STRANDED (built, no consumer) / MISSING
  (not built; would need new ingest) / PARTIAL (built but single-sport or single-venue).
- KEY: KEYLESS (no auth) / KEYED (needs an API key) / STATIC-KEY (public app key baked in).
- EDGE-UNLOCK: which beatable pocket (P1 DFS props, P2 live lag, P3 stale/soft lines,
  P4 prediction-market divergence, P5 SGP correlation, P6 niche) it feeds, or "efficient /
  decision-support only" if it only helps us match the close (a CUT-list market).
- TIER: the highest evidence tier any edge built on it has reached (HYPOTHESIS by default).

The blunt summary: the sources that move the needle are the ones that feed **soft DFS prop
pricing (P1)**, **same-day freshness** (the one unmodeled lever per MEMORY), and **true
closing lines** (so CLV becomes computable). Everything that only republishes a sharp
mainline is decision-support, not an edge source.

---

## TIER A -- highest edge-unlock (the beatable pockets + the levers we cannot currently see)

### A1. Underdog Fantasy props -- `prop_underdog.py` -- WIRED (soccer_intl only) / KEYLESS
- Provides: real two-sided player O/U props with TRUE decimal odds. Per
  `prop_underdog.py:39` endpoint `https://api.underdogfantasy.com/beta/v5/over_under_lines`;
  multi-sport payload filtered by `_SPORT_ID = {"soccer_intl": "FIFA"}` (`:44`).
- Schema (probed 2026-06-17, `prop_underdog.py:7-24`): top-level `over_under_lines[]`
  (carries `stat_value` = the numeric line, `options[]` = higher/lower sides, and
  `over_under.appearance_stat.{appearance_id, display_stat}`); `appearances[]`
  (id -> player_id/team_id/match_id, the join hub); `players[]`; `games[]` (match_id ==
  game id, with `scheduled_at`). Each option carries `american_price`, `decimal_price`
  (the real vig-adjusted price, line_type "balanced"), and `payout_multiplier` -- the
  latter two DISAGREE (1+0.75=1.75 != 1.53), so the code correctly uses `decimal_price`
  and labels `payout_type="sportsbook"` (`:18-22`).
- Refresh cadence: on-demand per `fetch_props`; no cache (provider ignores `http_cache`,
  raw urllib GET, 12s timeout). For CLV capture it must be polled up-to-kickoff.
- Leak rules: `scheduled_at` on the game is the event time; only props with `as_of` <
  kickoff are valid; never use a line logged after first ball.
- EDGE-UNLOCK: **P1 (soft/DFS props)** -- THE primary pocket. It is the ONLY current prop
  source emitting a real two-way price, so it is the only one where EV-vs-priced (devig +
  EV) is honest rather than a model_view gap.
- WHY IT'S THE TOP LEVER: per cut-list KEEP list, soft DFS props in proven stats is where
  effort should go. Underdog gives a devig-able price to measure CLV against.
- GAP: WIRED for `soccer_intl` only. Underdog publishes NBA/MLB/NFL on the SAME endpoint
  under different `sport_id`s -- adding those ids is the single highest-value scraper
  change (unlocks props in sports with deep multi-season corpora; see A8/deep-dive 03 plan
  item 6).
- TIER: HYPOTHESIS for the price-vs-model edge; the WC prop calibration is "suggestive on
  24 matches" (deep-dive 03 sec 5), not established.

### A2. PrizePicks projections -- `prop_prizepicks.py` -- WIRED (soccer_intl) / KEYLESS
- Provides: DFS pick'em projections (lines only, NO two-sided price). Two calls
  (`prop_prizepicks.py:42-43`): `https://api.prizepicks.com/leagues` then
  `https://api.prizepicks.com/projections?league_id=<id>&per_page=250&single_stat=true`.
  League resolved BY NAME: `_LEAGUE_NAME = {"soccer_intl": "WORLD CUP"}` (`:49`),
  `find_league_id` (`:75`) exact-normalized-name match.
- Schema: `/leagues` -> `data[]` each `{id, attributes.name}`; `/projections` -> rows with
  player + stat + line. All rows are `payout_type="dfs_pickem"`, prices None.
- EDGE-UNLOCK: **P1, but structural (the fixed-payout DFS crack from edge-theory.md)**.
  Because PrizePicks cannot move its payout, a genuinely mispriced projection STAYS
  mispriced -- the cleanest structural inefficiency. BUT: no two-way close => CLV-vs-close
  is UNDEFINED (edge-theory.md DFS note). Proof path is P(over)-calibration vs realized +
  fixed-payout ROI + line MOVEMENT, not CLV.
- HONEST CAVEAT: every PrizePicks edge is `edge_basis="model_view"` (gap from 0.5), never
  a priced EV (deep-dive 03 sec 5). goblin/demon flex odds are acknowledged but NOT parsed
  -- a real coverage gap on their highest-payout lines.
- TIER: HYPOTHESIS.

### A3. SAME-DAY LINEUPS / STARTING PITCHERS / LATE SCRATCHES -- MISSING / mostly KEYLESS
- Provides (would provide): confirmed starting lineups (NBA), confirmed starting pitchers
  (MLB), late scratches, injury actives -- i.e. the FRESHNESS lever.
- WHY IT'S TIER A despite being unbuilt: MEMORY and both deep-dives name freshness as
  THE one unmodeled lever. cut-list CUT 2 says NBA pregame team markets are at the
  data ceiling and "the real fix = same-day freshness/availability"; deep-dive 12 sec 7
  names "same-day lineups, late scratches, weather, and true closing lines" as the levers
  "we mostly cannot see keylessly." MLB pitchers.parquet covers only 2010-2021 -> current
  MLB runs PITCHER-BLIND on 2022-26 (deep-dive 12 sec 5, limitation 4).
- Where to get it KEYLESS:
  - MLB probable pitchers: `statsapi.mlb.com/api/v1/schedule?sportId=1&hydrate=probablePitcher`
    -- the SAME keyless StatsAPI already used by `domains/mlb/ingest_current.py` (no key,
    browser UA to avoid 406). This is the highest-ROI MISSING ingest: extend
    `ingest_pitchers` to 2022-26 (deep-dive 12 plan item 6).
  - NBA actives/inactives: ESPN summary already fetched (`espn.py`) exposes injuries; NBA
    StatsAPI also keyless. The signal exists; nothing consumes it yet.
- Leak rules: a lineup/pitcher is only usable once OFFICIALLY confirmed AND timestamped
  before tip/first-pitch; "expected" lineups can flip. Stamp `confirmed_at`.
- EDGE-UNLOCK: feeds P1 (player-prop distributions condition heavily on minutes/role and
  on the opposing pitcher) AND lifts pregame calibration where books already price it.
- TIER: HYPOTHESIS (unbuilt). Highest expected calibration lift per the project's own
  ceiling diagnosis.

### A4. CLOSING LINES (true close capture) -- PARTIAL / KEYLESS via existing feeds
- Provides: the closing price on each market = the input that makes CLV (the bridge metric
  to "would make money") COMPUTABLE. See the companion file `closing-line-and-clv.md` for
  the full capture plan.
- Current state: `prop_line_history.py` (the closing-line capture module) EXISTS and works
  (`log_board_lines` -> `data/frontend/prop_line_history.jsonl`, last logged line = close
  proxy). But the history file currently holds essentially ONE placeholder row
  ("A vs B"/"P", verified live) -- i.e. almost NO real closing prop data has accrued.
  Team-side: `odds_snapshots/snapshots.jsonl` exists per domain (NBA 18 lines, MLB 180
  lines) but is single-venue (ESPN's one republished book).
- EDGE-UNLOCK: cross-cutting -- it does not create an edge, it PROVES one (or kills it).
  Per cut-list/proof-standards, CLV is the final bar for real money.
- TIER: capability HYPOTHESIS until the loop runs up-to-kickoff over a full slate.

---

## TIER B -- real but execution-only or thin (decision-support, line-shopping, divergence)

### B1. ESPN scoreboard + summary (pickcenter moneylines) -- `espn.py` -- WIRED / KEYLESS
- Provides: per-game two-way moneylines republished from ONE sportsbook, plus the
  scoreboard (event ids, home/away, scheduled time) and athlete/injury context.
- Endpoint: `https://site.api.espn.com/apis/site/v2/sports/<league>/scoreboard` then
  `.../summary?event=<id>` -> `pickcenter[].{provider.name, homeTeamOdds.moneyLine,
  awayTeamOdds.moneyLine}` (`espn.py:30`, parse at `:49`). League map (`:31`):
  nba->basketball/nba, mlb->baseball/mlb, soccer->soccer/eng.1 (EPL),
  soccer_intl->soccer/fifa.world. `max_events` default 20 -> up to 21 requests/sport/miss
  (N+1: 1 scoreboard + 1 summary per event).
- Refresh: 60s TTL disk cache (`http_cache.py`, `~/.cache/courtvision_odds`).
- Leak rules: scoreboard carries the game time; pregame lines only; in-game ESPN lines are
  live (P2) and must be timestamped.
- EDGE-UNLOCK: **mostly EFFICIENT / decision-support** -- a single republished book is a
  mainline price (CUT 1). It degenerates "multi-book best-line/arb" to one venue
  (deep-dive 03 sec 5). Its real value: (a) the scoreboard backbone for matching, (b) a
  free CLV reference for mainlines, (c) live in-game moneylines = a P2 (live-lag) feed if
  polled fast. SECONDARY value: ESPN athlete-overview / injuries (A3 freshness).
- TIER: efficient for $-edge; useful as a calibration yardstick + scoreboard spine.

### B2. The Odds API (h2h/spreads/totals) -- `odds_shop.fetch_odds` -- WIRED-optional / KEYED
- Provides: genuine MULTI-BOOK odds (the only path to real line-shopping + honest arb).
  `fetch_odds(sport_key)` (`odds_shop.py:214`), `ODDS_API_KEY` from env; absent key or any
  failure -> status "unavailable". The ONLY keyed path; isolated from the keyless stack.
- EDGE-UNLOCK: **P3 (stale/soft-line line-shopping)** -- the durable EXECUTION edge (best
  price across books), NOT a predictive edge (cut-list CUT 6: arb is not a profit center;
  line-shopping is). Multi-book is what makes `best_line`/`detect_arb` meaningful.
- HONEST CAVEAT: keyed/quota-limited; the project intentionally keeps it as an optional
  "more books" mode behind the keyless default (deep-dive 03 plan item 7).
- TIER: HYPOTHESIS (execution edge; thin, transient, limit-constrained per cut-list).

### B3. Kalshi public market data -- `kalshi.py` -- WIRED / KEYLESS
- Provides: prediction-market YES asks -> two-way team-winner lines. Base
  `https://api.elections.kalshi.com/trade-api/v2` (`kalshi.py:32`), `GET /markets?limit=200
  &status=open`, filter by `event_ticker` prefix `_SERIES_HINT` (`:37`: nba->KXNBA,
  mlb->KXMLB, soccer->KXEPL, soccer_intl->KXWC), group by event_ticker, emit only events
  with EXACTLY two team markets each carrying a usable YES ask (`:87`). Optional
  `KALSHI_API_TOKEN` read but NOT attached to headers in the keyless path (effectively
  dead code, deep-dive 03 sec 5 "Other").
- EDGE-UNLOCK: **P4 (prediction-market vs sportsbook divergence)** -- a DIFFERENT crowd. A
  Kalshi/book gap is a candidate signal.
- HONEST CAVEAT: NOT a sportsbook. YES ask carries its own vig/skew; liquidity is low,
  spreads wide; mixing it into `best_line` can surface a "best" price not bettable at size
  (deep-dive 03 sec 5). Orientation depends entirely on name-matching; a label the resolver
  doesn't know can flip a side. KEEP IT SEPARATELY LABELED (plan item 3: tag venue type).
- TIER: HYPOTHESIS (divergence as a signal is unmeasured here).

### B4. Polymarket Gamma -- `polymarket.py` -- WIRED (best-effort) / KEYLESS
- Provides: two-outcome sports markets -> two-way lines. Base
  `https://gamma-api.polymarket.com` (`polymarket.py:30`), `GET /markets?active=true&
  closed=false&limit=200`, filter by sport keyword in slug/question (`:35`),
  `parse_market` (`:65`) reads JSON-STRING `outcomes`/`outcomePrices` arrays (outcome[0]
  ->home, [1]->away). Non-two-way -> None.
- EDGE-UNLOCK: **P4** (same as Kalshi -- a second prediction-market crowd).
- HONEST CAVEAT: same prediction-market caveats as B3; "best-effort" parser; slug/question
  keyword filter is loose.
- TIER: HYPOTHESIS.

### B5. FanDuel NJ sportsbook props -- `prop_fanduel.py` -- STRANDED / STATIC-KEY
- Provides (would provide): real two-way American-odds player props from a true
  sportsbook. Host `https://sbapi.nj.sportsbook.fanduel.com/api` (`:47`), content-managed
  page `?page=CUSTOM&customPageId=fifa-world-cup&_ak=<static app key>` (`:48`) then
  `event-page?eventId=<eid>` (`:50`). `_PAGE_ID = {"soccer_intl": "fifa-world-cup"}` (`:55`).
- STATUS: BUILT but STRANDED -- in NO consumer (`prop_edge._default_providers` is
  Underdog+PrizePicks only) and per its docstring FanDuel had posted no WC prop markets at
  probe time, so the prop parser has NEVER run against real prop data (only the
  moneyline/penalty shape). UNVALIDATED on its target payload (deep-dive 03 sec 5).
- EDGE-UNLOCK: **P1 + P3** -- a real sportsbook two-way price is the best devig/CLV
  reference for props AND a second venue for line-shopping. This is the highest-value
  STRANDED asset; deep-dive 03 plan item 2 = wire it in behind a flag + live-probe smoke
  test that records the real payload.
- TIER: HYPOTHESIS (unvalidated).

---

## TIER C -- prediction corpora ingest (the as-of feature backbone; mostly EFFICIENT markets)

These feed pregame predictors. Per cut-list, the markets they price (mainlines, NBA pregame
team markets) are largely EFFICIENT -- they are decision-support + calibration yardsticks,
NOT edge sources. They earn their place by being clean, keyless, leak-free, and the base for
player-prop distributions (which IS a pocket).

### C1. MLB StatsAPI -- `domains/mlb/ingest_current.py` -- WIRED / KEYLESS
- Provides: FINAL game results extending the frozen 2010-2021 SBR corpus to current.
  `statsapi.mlb.com` (`sportId=1, gameType=R`, no key, browser UA to avoid 406). Maps full
  team names onto the non-standard SBR 3-letter codes so `games_current.parquet` (10,826
  rows, 2022-04-07..2026-06-16) concatenates with `games.parquet` (27,983 rows, 2010-2021)
  and the SAME `walk_forward_elo` replays across both (deep-dive 12 sec 2.1).
- Refresh: keyless, idempotent, finals-only (leak-free). Manual/loop-driven (not scheduled).
- EDGE-UNLOCK: efficient mainline ML (CUT 1) -- BUT it is also the keyless source for the
  MISSING pitcher + probable-pitcher data (A3) which IS edge-relevant. Same host.
- TIER: calibration / decision-support.

### C2. Jeff Sackmann tennis CSVs -- `domains/tennis/ingest_sackmann.py` -- WIRED / KEYLESS
- Provides: ATP/WTA match history from
  `raw.githubusercontent.com/JeffSackmann/tennis_atp|tennis_wta` (CC BY-NC-SA),
  idempotent (skip if present, size>0). Corpora: ATP 30,616 rows (2015-2025), WTA 11,270.
- EDGE-UNLOCK: efficient pregame ATP/WTA mainlines. Deep multi-season corpus = good for
  CALIBRATION cross-validation; the prop layer (if ever added) would be a pocket.
- TIER: calibration.

### C3. football-data.co.uk + ESPN soccer -- `domains/soccer/ingest_footballdata*.py` + `ingest_espn_*` -- WIRED / KEYLESS
- Provides: club football match history (`matches.parquet` 25,834 rows, 2015-2026) +
  ESPN player stats / WC rosters (`espn_player_stats.parquet` ~1241 rows / 48 teams = ONE
  WC tournament -- the prop model corpus). soccer_intl `results.parquet` = 49,477 rows back
  to 1872.
- EDGE-UNLOCK: the WC player-stats parquet is the model backbone for the A1/A2 prop board.
  HONEST: it is data-starved (24 matches; isotonic recal OVERFITS, opponent-adjust NULL --
  deep-dive 12 sec 5 limitation 3). This thinness is the binding cap on the current prop
  vertical's calibration claims.
- TIER: calibration (suggestive only at current N).

### C4. NBA ingest (boxscores/odds/linescores/schedule) -- `domains/basketball_nba/ingest_*` -- WIRED / KEYLESS
- Provides: NBA team-game results (`games.parquet` 4,846 rows 2022-2026) + player
  boxscores (`player_boxscores.parquet` 27,816 rows) + leak-free `asof_features.parquet`.
- EDGE-UNLOCK: pregame team markets are CUT (CUT 2, at data ceiling). The player boxscores
  are the corpus for an NBA PROP board via the MC-sim ladder when season returns -- THAT is
  the pocket (cut-list KEEP). The only durable NBA model edge is AST pregame (~+7%, prop).
- TIER: pregame = efficient; AST prop = CALIBRATION-PROVEN (per MEMORY, RAW, never playoffs).

---

## TIER D -- MISSING sources that would unlock NEW edge (ranked)

### D1. Sofascore / FotMob deeper player + lineup stats -- MISSING / KEYLESS-ish
- Would provide: far deeper soccer player stats (per-90 rates, xG/xA, positional minutes,
  confirmed lineups) than the ~1241-row ESPN WC parquet. This directly attacks the binding
  cap on the prop vertical (C3 thinness) and the freshness gap (A3).
- EDGE-UNLOCK: deepens P1 (better-calibrated per-player prop distributions) + freshness.
  Per the deepest-data north star (MEMORY), depth in a beatable pocket is the lever that
  moves the ceiling.
- CAVEATS: unofficial endpoints, anti-bot, fragile (same risk class as Underdog/PrizePicks
  per deep-dive 03 sec 5). Honest-degrade contract required. Validate stat parity vs ESPN.
- TIER: HYPOTHESIS. Rank: highest among MISSING for the active soccer vertical.

### D2. Underdog/PrizePicks NBA + MLB league ids -- MISSING (same keyless endpoints)
- Would provide: NBA/MLB DFS props on the SAME endpoints already wired for WC (A1/A2 just
  need new `sport_id`/league-name entries). Joins to the DEEP NBA boxscore corpus (C4) and
  MLB corpus -- where calibration can actually be cross-validated over many seasons, unlike
  24 WC matches (deep-dive 03 plan item 6).
- EDGE-UNLOCK: P1 in sports with real data depth. The single highest-value MISSING wiring
  (low effort, high unlock).
- TIER: HYPOTHESIS.

### D3. Weather (MLB/soccer outdoor) -- MISSING / KEYLESS (NWS / open-meteo)
- Would provide: park/wind/temp for MLB totals + player props; rain for soccer. A freshness
  input books price but our pregame model cannot see (deep-dive 12 sec 7).
- EDGE-UNLOCK: feeds P1 (totals/HR/strikeout distributions) + pregame totals calibration.
- CAVEATS: marginal lift; books already integrate it -> mostly closes the gap, rarely opens
  one. Lower priority than D1/D2. TIER: HYPOTHESIS.

### D4. A second real sportsbook (DraftKings-class) -- MISSING / deliberately scoped OUT
- Would provide: genuine multi-book breadth for line-shopping (P3) + arb detection.
- STATUS / DECISION: deep-dive 03 plan item 10 explicitly says do NOT build a
  Playwright/headless browser scraper (fragile, ToS-hostile, out of scope). Only add a book
  if a legitimate public JSON endpoint exists (mirroring the FanDuel sbapi approach). The
  keyed The Odds API (B2) is the sanctioned "more books" path.
- TIER: deferred by policy.

---

## Cross-source matching (the load-bearing correctness risk -- applies to ALL team sources)

`teams_match` (`aggregate.py:65`) is deliberately STRICT, biased to FALSE NEGATIVES (no
odds) over FALSE POSITIVES (wrong game's price). Code-resolver path for NBA/MLB
(`team_resolver.canonical`, 30-team maps) + name-rule fallback (last-token nickname +
Jaccard>=0.5) for soccer/tennis. This is the RIGHT risk posture and must be kept. Cost:
aliases ("Man City"/"Manchester City"), accents, WC neutral-site naming MISS -> silent
no-odds, degrading coverage exactly where the board needs it (deep-dive 03 sec 5). Fix =
expand the static alias map (plan item 5), never loosen the matcher.

---

## The leak-rule summary (binding across every source)

1. To price event E, use ONLY data timestamped < E (kickoff / tip / first-pitch). Stamp
   `as_of` / `confirmed_at` on every row.
2. Finals-only for result corpora (no in-progress scores) -- already enforced in MLB/NBA
   ingest.
3. Live (in-game) lines are a SEPARATE timestamped feed (P2); never fold a live price into
   a pregame snapshot.
4. Lineups/pitchers usable only once OFFICIALLY confirmed and timestamped before the event;
   "expected" can flip.
5. Closing line = the LAST line logged before kickoff (a proxy); only as honest as the
   poll cadence (see closing-line-and-clv.md).

---

## Bottom line (where acquisition effort should go)

CONCENTRATE: (A1/D2) Underdog+PrizePicks across NBA/MLB on their existing keyless endpoints;
(A3) same-day pitchers via the StatsAPI we already hit + lineups via ESPN we already fetch;
(A4) actually run the closing-line capture loop up-to-kickoff so CLV becomes real; (D1)
Sofascore/FotMob depth for the data-starved soccer prop vertical; (B5) un-strand FanDuel as
a real two-way prop reference.
CUT / DEPRIORITIZE: chasing more mainline books beyond the optional keyed Odds API (CUT 1/6);
treating prediction markets as bettable book lines (keep them as labeled P4 divergence
signals only); a browser-scraped DraftKings (scoped out).
