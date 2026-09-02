# Licence ledger -- every data source this repo ingests or holds

Built 2026-09-03 (S62). Format follows `docs/evidence/harness/LICENCE_mlb_close_history.md`:
source, URL, the clause quoted verbatim, the date it was read, what the clause
permits, what WE actually do with the data, and a verdict.

**This is an operational reading of published pages, recorded so a decision is
reviewable. It is not legal advice and no lane may act on it.** The `verdict`
column is Neel's to set; this lane only assembles the evidence.

Verdict key (per the S62 row):

- `OK` -- the clause permits research/personal use and we do not publish the data.
- `DECIDE` -- the clause conflicts with what we actually do with the data. Neel decides.
- `UNREAD` -- the publisher's terms could not be read from this box today, so no
  verdict is possible. Not a pass and not a fail.

Row counts below were read from disk read-only on 2026-09-03. Nothing was
fetched into a corpus by this lane; the only network calls were GETs of the
publishers' own terms pages (plus four HEAD/GET reachability probes noted inline).

---

## Summary

| # | source | our holding (headline) | verdict |
|---|---|---|---|
| 1 | ESPN site API + core API v2 (Disney) | ~50 corpora across 5 sports; 24k+ cached JSON | **DECIDE** |
| 2 | NBA Stats API (stats.nba.com via `nba_api`) | 24,044 JSON under `data/nba/` (524 MB) | **DECIDE** |
| 3 | MLB Stats API / GUMBO (statsapi.mlb.com) | 321,012 + 11,334 + 11,179 rows | **DECIDE** |
| 4 | Statcast / Baseball Savant (MLBAM) | 28 raw day-parquets (763 MB), 32,041 SP-velo rows | **DECIDE** |
| 5 | FotMob | in-game soccer enrichment reads; no corpus stem | **DECIDE** |
| 6 | YouTube broadcast footage | 137 video files, 70.8 GB under `data/videos/` | **DECIDE** |
| 7 | football-data.co.uk | 25,834 matches + 16,322 odds rows | OK |
| 8 | tennis-data.co.uk | 33,952 ATP + 5,194 WTA price rows | OK |
| 9 | StatsBomb open data | 4,235 event files; 2,400 + 400 + 400 rows | OK (conditional) |
| 10 | Sackmann `tennis_atp` / `tennis_wta` / slam pbp | 30,616 + 11,270 matches; 2.40M pbp points | UNREAD |
| 11 | Kalshi public API | 180 line-history files, 5,298,086 ticks (all sports) | UNREAD |
| 12 | Polymarket Gamma API | same tick store as row 11 | UNREAD |
| 13 | sportsbookreviewsonline.com archive | 27,983 games + 28,004 odds + 27,983 pitchers | UNREAD |
| 14 | Hugging Face `Oronto/mlb-game-prediction-data` | downloaded, NOT in any corpus | UNREAD |
| 15 | Kaggle MLB odds datasets | NOT held -- never downloaded | UNREAD |
| 16 | Basketball Reference | 3 cached JSON under `data/external/` | UNREAD |
| 17 | koreabaseball.com (KBO) | 3,276 rows | UNREAD |
| 18 | npb.jp (NPB) | 4,020 rows | UNREAD |
| 19 | DFS prop feeds (Underdog / PrizePicks / FanDuel / DK) | prop capture only, no parquet stem | UNREAD |
| 20 | The Odds API | key-gated; no key held, no rows | UNREAD |
| 21 | RotoWire projected lineups | `data/lineups_<date>.json` (NBA legacy path) | UNREAD |

**Counts: 3 OK (one conditional), 6 DECIDE, 12 UNREAD.**

---

## 1. ESPN site API + core API v2 (The Walt Disney Company) -- DECIDE

- Data URLs: `https://site.api.espn.com/apis/site/v2/sports/<sport>/<league>/{scoreboard,summary,injuries}`
  and `https://sports.core.api.espn.com/v2/sports/.../odds`
- Terms URL: <https://disneytermsofuse.com/english/> -- page states "Last Updated:
  May 24, 2024". Read 2026-09-03 (this ledger reuses the S52 reading; the clauses
  are reproduced from `LICENCE_mlb_close_history.md`, which quoted them from the
  live page that day). `espn.com/terms-of-use` returns 404; the linkage rests on
  the agreement's own scope sentence naming ESPN.
- Clause (a), Prohibited Activities item x, verbatim:

  > "access, monitor, copy or extract the Disney Products using a robot, spider,
  > script, or other automated means, including, for the avoidance of doubt, for the
  > purposes of creating or developing any AI Tool, data mining or web scraping or
  > otherwise compiling, building, creating or contributing to any collection of
  > data, data set or database"

- Clause (b), Consumer License, verbatim:

  > "we grant you a limited, non-exclusive, non-sublicensable, non-transferable
  > license to access and use in the United States such software, content, virtual
  > item or other material for your personal, noncommercial use only, ... with no
  > right to reproduce, distribute, communicate to the public, make available to the
  > public, or transform any Disney Product, including in connection with any use,
  > creation, development, modification, prompting, fine-tuning, training, testing,
  > benchmarking or validation of any artificial intelligence or machine learning
  > tool, model, system, algorithm, product or other technology ("AI Tool")"

- Permitted use per the clause: personal, non-commercial access. Automated
  collection into a data set is barred by name, and so is use for
  testing/benchmarking/validation of a model or algorithm.
- OUR use: training corpora, evaluation and market-relative benchmarking, across
  five sports. Held (row counts read 2026-09-03):
  - `data/domains/basketball_nba/`: `odds.parquet` 1,317, `linescores.parquet` 1,313,
    `espn_boxscores*.parquet` 1,977 + 1,232 + 1,235, `espn_nba_game_bridge.parquet` 1,299
  - `data/domains/mlb/`: `probables.parquet` 11,334 (StatsAPI), `injuries.parquet` 4,427,
    `espn_boxscores.parquet` 2, plus every ESPN-plays-derived state corpus
  - `data/domains/soccer/`: `espn_club_priors.parquet` 8,741, `espn_matchstats.parquet` 185,
    `espn_player_stats.parquet` 1,290
  - `data/domains/tennis/espn_matches.parquet` 14,469
  - `data/domains/soccer_intl/espn_finals.parquet` 62; `data/domains/wnba/espn_scoreboard.parquet` 800,
    `linescores.parquet` 768, `player_boxscores.parquet` 4,697, `injuries.parquet` 42
  - `data/cache/quarter_box/` 7,304 JSON (66 MB), `data/cache/spreads/` 216 JSON (43.5 MB)
  - ESPN is also one of three odds providers in `scripts/platformkit/odds_provider/espn.py`,
    feeding the shared tick store in row 11.
  We do not publish any of it (`data/` is gitignored).
- **Verdict: DECIDE.** This is the same clause pair that closed S52. The conflict is
  not marginal -- clause (b) names benchmarking and validation of a model, which is
  precisely what these corpora are for, and clause (a) names dataset compilation.
  The S62 register row already stands as a hold: do not fetch more ESPN data into
  corpora until this is decided.

## 2. NBA Stats API (stats.nba.com, via `nba_api`) -- DECIDE

- Data URLs: `https://stats.nba.com/stats/{leaguedashplayerstats,playergamelogs,
  shotchartdetail,playbyplayv2,leaguehustlestatsplayer,leaguedashptdefend,
  matchupsrollup,synergyplaytypes,leagueplayerondetails,boxscoreplayertrackv3}`
- Terms URL: <https://www.nba.com/termsofuse> -- page states "Last Updated: July 13,
  2026". Read 2026-09-03.
- Clause, verbatim:

  > "No Basketball Content from the Services may be reproduced, republished, uploaded,
  > posted, modified, reused, transmitted, reproduced, distributed, copied, publicly
  > displayed, linked to, or otherwise used except as provided in these Terms of Use
  > without the written permission of the Operator."

  and:

  > "You may not, however, distribute, reproduce, republish, upload, display, modify,
  > transmit, reuse, repost, link to, or use any materials of the Services for public
  > or commercial purposes on any other Website, social media platform, or otherwise
  > without the written permission of the Operator."

- Permitted use per the clause: personal use of the site. There is no research
  carve-out and no API terms separate from the site terms. The page carries **no
  clause naming robots/scrapers/AI training by name** -- the restriction is the broad
  reproduction bar above. That absence is recorded honestly, not read as permission.
- OUR use: the production NBA feature substrate. Held: 24,044 JSON files / 524.3 MB
  under `data/nba/` (gamelogs, shot charts 221k shots, PBP, hustle, on/off, defender
  zone, matchups, synergy), plus `data/domains/basketball_nba/asof_player_adv.parquet`
  77,728, `player_boxscores.parquet` 77,744, `defender_matchup_states.parquet` 37,395,
  `asof_team_adv.parquet` 3,685, `games.parquet` 4,846. Training + evaluation. Not published.
- **Verdict: DECIDE.** Bulk reproduction into a local corpus is not "as provided in
  these Terms of Use", and no written permission is held. Note the operational fact
  that stats.nba.com is blocked from this box (documented in `docs/DATA.md`), so the
  cache is historical, not actively refreshed.

## 3. MLB Stats API / GUMBO (statsapi.mlb.com) -- DECIDE

- Data URLs: `https://statsapi.mlb.com/api/v1/{schedule,game/<pk>/boxscore}`,
  `https://statsapi.mlb.com/api/v1.1/game/<pk>/feed/live` (GUMBO diffPatch)
- Terms URL: <http://gdx.mlb.com/components/copyright.txt> -- the MLBAM copyright
  notice referenced from MLB data pages. Read 2026-09-03. No last-updated date printed.
- Clause, verbatim:

  > "The accounts, descriptions, data and presentation in the referring page (the
  > "Materials") are proprietary content of MLB Advanced Media, L.P ("MLBAM")."

  > "Only individual, non-commercial, non-bulk use of the Materials is permitted"

  > "Any other use of the Materials is prohibited without prior written authorization
  > from MLBAM."

- Permitted use per the clause: individual, non-commercial, **non-bulk**.
- OUR use: bulk. Held: `player_gamelogs.parquet` 321,012 rows,
  `probables.parquet` 11,334, `games_current.parquet` 11,179,
  `asof_features_current.parquet` 10,458, `asof_park_current.parquet` 10,826, plus the
  GUMBO live-poller tick history. Training, evaluation, and scoring against a market.
- **Verdict: DECIDE.** "non-bulk" is the direct conflict: a 321k-row player-gamelog
  parquet is bulk on any reading. Note also `scripts/platformkit/license_guard.py`
  already denylists the `statsapi` / `mlb_statsapi` *Python packages* as GPL-3.0 --
  that is a code-licence guard and is unrelated to this data-terms question.

## 4. Statcast / Baseball Savant (MLBAM) -- DECIDE

- Data URL: the keyless `baseballsavant.mlb.com` CSV export (the same endpoint
  `pybaseball.statcast` wraps), acquired day-at-a-time by
  `domains/mlb/acquire_statcast_sample.py` with a politeness delay.
- Terms URL: the same MLBAM notice as row 3 (Savant is an MLBAM property).
  Read 2026-09-03. **A Savant-specific terms page was NOT located this lane.**
- Clause: as quoted in row 3 -- "Only individual, non-commercial, non-bulk use of the
  Materials is permitted".
- OUR use: 28 cached raw day-files / 763.2 MB under `data/cache/statcast/`,
  `sp_velo_states.parquet` 32,041 rows, `catcher_framing_index.parquet` 113,
  `umpire_zone_index.parquet` 102, `platoon_split_index.parquet` 394, plus the
  `matchup/` pitch-profile family (12,843 + 9,746 + 7,415 + 5,063). Feeds the
  SP-fatigue K-prop gate. Not published.
- **Verdict: DECIDE.** Same conflict as row 3. The acquisition is deliberately bounded
  and polite (never whole seasons), which is a mitigation, not a permission.

## 5. FotMob -- DECIDE

- Data URL: FotMob public match JSON, read by `domains/soccer/ingame_fotmob.py`
  (in-game xG enrichment) and the enrichment-gate runners in
  `scripts/platformkit/ingame/`.
- Terms URL: <https://www.fotmob.com/terms>. Read 2026-09-03. No last-updated date
  printed on the page.
- Clause, verbatim:

  > "The use of automatic services (robots, crawler, indexing etc.) as well as other
  > methods for systematic or regular use is not permitted."

- Permitted use per the clause: manual, non-systematic use of the site.
- OUR use: programmatic in-game reads on a polling cadence. **No FotMob corpus stem
  exists on disk** -- it is a live enrichment read, not a stored corpus, so there is
  no row count to report.
- **Verdict: DECIDE.** "systematic or regular use" is exactly what a poller is.

## 6. YouTube broadcast footage -- DECIDE (listed, not adjudicated by this lane)

- Source: `youtube.com`, downloaded by `src/ingest/fetcher.py` / yt-dlp (a
  `data/videos/youtube_cookies.txt` is present on disk).
- Terms URL: <https://www.youtube.com/static?template=terms> -- effective date
  December 15, 2023 as printed. Read 2026-09-03.
- Clause, verbatim:

  > "access the Service using any automated means (such as robots, botnets or scrapers)"

  (listed among the prohibited Restrictions, excepted only for public search engines
  obeying robots.txt or with YouTube's prior written permission). The same section
  bars reproducing or downloading any part of the Service except as expressly
  authorised by YouTube and the relevant rights holders.
- Permitted use per the clause: streaming playback; no automated access, no download.
- OUR use: 137 video files / 70.8 GB under `data/videos/` (79 in `full_games/`, 53 in
  `bridge/`, 14 in `reference/`, plus quarantine and probe dirs), consumed by the
  tracking pipeline as a **teacher-only training input** (the runtime student uses APIs
  only -- `product_runtime_contract_2026_09_01`). Broadcast frames also carry the
  broadcaster's and league's own copyright, which is a second and independent
  question this ledger does not attempt to read.
- **Verdict: DECIDE.** Per the S62 lane scope this row is *listed, not judged*:
  the clause is recorded verbatim and the exposure is quantified; the call is Neel's.

## 7. football-data.co.uk -- OK

- Data URL: `https://www.football-data.co.uk/mmz4281/<season>/<div>.csv`
  (`domains/soccer/ingest_footballdata.py`, `ingest_footballdata_matchstats.py`)
- Terms URL: <https://www.football-data.co.uk/> (homepage). Read 2026-09-03.
  `notes.txt` and `disclaimer.php` were also read and contain **no** licence,
  copyright or permitted-use statement.
- Clause, verbatim (homepage body and footer):

  > "My data is free, but for those who want a subscription API service, I am now
  > partnering with TheStatsAPI."

  > "(c) Football-Data. Liability Disclaimer. All Rights Reserved."

- Permitted use per the clause: the data is offered free to download. Copyright is
  reserved and **no** scope is stated -- the page does not distinguish research from
  commercial use, and does not mention redistribution, scraping or AI training.
- OUR use: `data/domains/soccer/matches.parquet` 25,834, `odds.parquet` 16,322,
  `match_stats.parquet` 25,834, `asof_features.parquet` 25,834, plus the derived
  soccer gate corpus. Training, evaluation and scoring against the closing line
  (this is the S02 corpus). Not published; `data/domains/soccer/` is gitignored.
- **Verdict: OK.** Free download is stated, we do not publish or redistribute the data.
- **Correction to the code:** `domains/soccer/ingest_footballdata.py:6` asserts
  "football-data.co.uk data is free for personal/research use only". The page says
  "My data is free" and "All Rights Reserved" -- it does **not** say "personal/research
  use only". The docstring is over-specific in the restrictive direction; the real
  position is "free, scope unstated". Recorded, not edited (the file is outside this
  lane's write scope).

## 8. tennis-data.co.uk -- OK

- Data URL: `http://www.tennis-data.co.uk/{year}/{year}.xlsx` and
  `.../{year}w/{year}.xlsx` (`domains/tennis/ingest_tennisdata_load.py:26-27`)
- Terms URL: <http://www.tennis-data.co.uk/index.php> (homepage). Read 2026-09-03 via
  a plain HTTP GET with a browser user agent; the HTTPS host fails a TLS handshake
  from this box (`TLSV1_ALERT_INTERNAL_ERROR`), which is why the site is HTTP-only in
  the ingester. `alldata.php` and `notes.txt` carry no usage statement.
- Clause, verbatim:

  > "All Data is free to use and accessible via the menu links to the right."

  > "(c) Tennis-Data. Liability Disclaimer. Privacy Policy. All Rights Reserved."

  The same paragraph states the site exists "to help tennis betting enthusiasts
  develop quantitative tennis betting systems".
- Permitted use per the clause: free to use, explicitly for building quantitative
  models. Copyright reserved; redistribution not addressed.
- OUR use: `data/domains/tennis/odds.parquet` 33,952 rows and
  `data/domains/tennis/wta/odds.parquet` 5,194 rows -- the p1/p2-oriented price
  series behind the S03 tennis gate corpus. Evaluation and calibration against the
  close. Not published.
- **Verdict: OK.**
- **Correction to the code:** `domains/tennis/ingest_tennisdata.py:6-8` is
  restriction-only ("PRIVATE: outputs are price-bearing or license-restricted") and
  names no permission, no URL and no date -- exactly the defect the S62 register row
  flags. The publisher's own page grants use in terms broader than the docstring
  implies. Recorded, not edited.

## 9. StatsBomb open data -- OK (conditional)

- Data URL: `https://github.com/statsbomb/open-data` (raw JSON:
  `competitions.json`, `matches/<comp>/<season>.json`, `events/<match_id>.json`),
  fetched bounded + polite by `domains/soccer/ingest_statsbomb_events.py`.
- Terms URL: <https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf>
  ("StatsBomb Public Data User Agreement"). Fetched and text-extracted 2026-09-03.
  No version or last-updated date is printed in the document. **The PDF's text layer
  drops inter-word spaces; the quotes below are the extracted text with word spacing
  restored and nothing else changed.**
- Clauses, verbatim:

  > "Subject to the terms of this Agreement, StatsBomb will provide the User with
  > access to the Service to be used for analysis, research and to facilitate the
  > shared ideas & understanding of the data"

  > "The User may not: ... edit, distort, distribute, reproduce, sell or in any way
  > provide the data to any external or third party; ... commercially exploit the data
  > or any analysis derived from the use of the Service"

  > "The User is required to accredit any publication of analysis formed from StatsBomb
  > Data with the StatsBomb brand logo."

  > "StatsBomb ask that all Users register their interest in our data via our website,
  > www.statsbomb.com/resource-centre"

- Permitted use per the clause: analysis and research, expressly. Barred:
  redistribution to any third party, and commercial exploitation of the data **or of
  any analysis derived from it**.
- OUR use: 4,235 cached event files under `data/cache/statsbomb/events/`, plus
  `asof_ingame.parquet` 2,400, `asof_pregame.parquet` 400, `match_meta.parquet` 400.
  Real-xG feature research on soccer. Not published, not redistributed.
- **Verdict: OK, conditional on two things being true.** (a) The research grant covers
  today's use, but clause 1.2.2 bars commercial exploitation of the data *or any
  derived analysis* -- the moment anything StatsBomb-derived enters a sellable product
  or a paid output, this row becomes DECIDE. (b) Clause 1.4 (accreditation on any
  published analysis) and clause 2.2 (registration) are obligations we have **not
  verified as met** -- no registration record was found in the repo. Both are flagged,
  neither is claimed satisfied.

## 10. Jeff Sackmann `tennis_atp` / `tennis_wta` / `tennis_slam_pointbypoint` -- UNREAD

- Data URLs (from `domains/tennis/ingest_sackmann.py:27-28`):
  `https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master` and
  `.../tennis_wta/master`; point-by-point from
  `github.com/JeffSackmann/tennis_slam_pointbypoint`.
- Terms URL: the repo README / LICENSE. **NOT READABLE 2026-09-03.** Measured:
  `GET https://github.com/JeffSackmann/tennis_atp` -> HTTP 404;
  `GET https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_2024.csv`
  -> HTTP 404; `api.github.com/repos/JeffSackmann/tennis_atp` and `.../tennis_wta` ->
  `"Not Found"`. The GitHub API itself is reachable from this box (the control probe
  `api.github.com/repos/iago-suarez/ELSED` returned `Apache-2.0` in the same command),
  so this is the repo path, not the network.
- Clause: **none read.** The repo's own docstrings assert CC BY-NC-SA
  (`ingest_sackmann.py:3` "Jeff Sackmann's tennis_atp / tennis_wta data is CC
  BY-NC-SA. Private research use only."; `ingest_sackmann_pbp.py:4,11` the same for
  the slam pbp repo). That is **our** claim about the licence, not a clause read from
  the publisher, and it was not re-verified today.
- OUR use: `data/domains/tennis/matches.parquet` 30,616, `wta_matches.parquet` 11,270,
  `players.parquet` 66,912, `match_stats.parquet` 59,312, and every `asof_*` tennis
  corpus built on them; `data/cache/sackmann_pbp/charting_points.parquet` 1,853,115 and
  `slam_points.parquet` 543,772. This is the entire tennis spine (the S03 corpus).
- **Verdict: UNREAD.** Two separate facts for Neel: the licence cannot be confirmed
  today, and the upstream source is no longer resolvable at the URLs the ingester
  uses -- so the tennis spine is a frozen local holding with no live provenance and,
  if CC BY-NC-SA is right, a NonCommercial term that would make this a DECIDE.

## 11. Kalshi public API -- UNREAD

- Data URL: `https://api.elections.kalshi.com/trade-api/v2/{events,markets,...}`.
  Keyless for public market data; `KALSHI_API_TOKEN` is read from ENV only and is not
  needed for reads (`scripts/platformkit/odds_provider/kalshi.py`).
- Terms URL: <https://kalshi.com/regulatory/terms-of-service>. **HTTP 429 on every
  attempt 2026-09-03** (both the fetcher and a browser-UA curl). Not read.
- Clause: **none read.**
- OUR use: the pregame and in-play price capture. Held (shared with row 12, one tick
  store): `data/cache/line_history/` 180 files / 5,298,086 ticks across 8 sports;
  `data/cache/inplay_history/` 4 files / 76,897 ticks; `data/cache/depth_history/`
  82 files / 107,356 ticks. Paper measurement only -- these daemons never place an
  order. Not published.
- **Verdict: UNREAD.** S52 also did not pursue Kalshi's terms (it had already refused
  the source on availability), so this remains the largest unread holding by row count.

## 12. Polymarket Gamma API -- UNREAD

- Data URL: `https://gamma-api.polymarket.com/markets`. No auth for read-only market data.
- Terms URL: <https://polymarket.com/tos>. Fetched 2026-09-03: HTTP 200 but the page
  is client-rendered -- 6,693 characters of shell text containing none of
  "scrape", "robot", "automated", "data mining", "crawl" or "redistribut". The terms
  body was not served to a plain fetcher. `docs.polymarket.com` documents the endpoint
  but states no usage restriction.
- Clause: **none read.**
- OUR use: the same tick store as row 11.
- **Verdict: UNREAD.**

## 13. sportsbookreviewsonline.com odds archive -- UNREAD

- Data URL: <https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlboddsarchives.htm>
  (per-season xlsx), consumed by `domains/mlb/ingest_sbro.py`.
- Terms URL: no terms page located. The archive page itself was read 2026-09-03 (S52)
  and states only:

  > "Historical scores and odds data from past Major League Baseball seasons including
  > runlines, opening and closing moneylines and totals. MLB scores and odds archive
  > will not be updated."

- Clause: **no permitted-use clause exists on the page.** S52 explicitly did not
  pursue the site's terms because the source was already dead on coverage (it stops at
  2021).
- OUR use: `data/domains/mlb/games.parquet` 27,983, `odds.parquet` 28,004,
  `pitchers.parquet` 27,983, `asof_features.parquet` 27,983, `asof_inning.parquet`
  28,004, `postmortem.parquet` 27,983 -- the frozen 2010-2021 MLB spine. Training and
  evaluation. Not published.
- **Verdict: UNREAD.** The largest MLB holding sits on a source whose terms have never
  been read. It is also the archive S52 identified as the near-certain origin of this
  corpus (the 2010-2021 range matches exactly).

## 14. Hugging Face `Oronto/mlb-game-prediction-data` -- UNREAD

- URL: `huggingface.co/datasets/Oronto/mlb-game-prediction-data`. Declared
  `license: mit` in the dataset card. Downloaded and read 2026-09-03 by the S52 lane.
- Clause: the MIT label is the dataset card's own declaration; no upstream provenance
  is named, so the label cannot be traced to a publisher whose terms could be read.
- OUR use: **none.** `vegas_odds.csv` is 1,052 rows and every row carries
  `odds_source = "mock_data"` -- synthetic. It was rejected on authenticity and is in
  no corpus.
- **Verdict: UNREAD.** Kept as a row because the file was downloaded. Standing rule
  from the CV asset ledger applies: a redistributor's licence tag is not provenance.

## 15. Kaggle MLB Vegas-odds datasets -- UNREAD (not held)

- Refused in S52 on coverage (2012-2021) and on needing Kaggle credentials. Never
  downloaded; nothing on disk. Terms not read.
- **Verdict: UNREAD.** Listed for completeness so the enumeration is exhaustive.

## 16. Basketball Reference -- UNREAD

- Data URL: `https://www.basketball-reference.com/` season pages, scraped by
  `src/data/bbref_scraper.py` (TTL 48 h).
- Terms URL: <https://www.sports-reference.com/termsofuse.html>. **Not fetched this
  lane.** Sports Reference publishes both a terms page and a data-use/robots policy;
  neither was read.
- Clause: **none read.**
- OUR use: 3 cached JSON under `data/external/` (advanced stats ~736 players x 4
  seasons, contracts 523 players). Feature inputs to the NBA prop models. Not published.
- **Verdict: UNREAD.** Small holding, unread terms.

## 17. koreabaseball.com (KBO) -- UNREAD

- Data URL: `https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList` (POST,
  browser UA + Referer required -- `domains/baseball_kbo/ingest_kbo.py`).
- Terms URL: not located; the site's terms are Korean-language and were not fetched.
- OUR use: `data/domains/kbo/kbo_results.parquet` 3,276 rows.
- **Verdict: UNREAD.** Note the access pattern is a scrape of an internal endpoint
  with a spoofed Referer, which is a materially different posture from a public API.

## 18. npb.jp (NPB) -- UNREAD

- Data URL: npb.jp monthly schedule/results HTML (`domains/baseball_npb/ingest_npb.py`).
- Terms URL: not located; not fetched.
- OUR use: `data/domains/npb/npb_results.parquet` 4,020 rows.
- **Verdict: UNREAD.**

## 19. DFS prop feeds -- Underdog / PrizePicks / FanDuel / DraftKings -- UNREAD

- Data URLs: `api.underdogfantasy.com/beta/v5/over_under_lines`, the PrizePicks public
  projections JSON, and the FanDuel / DraftKings public sportsbook props JSON
  (`scripts/platformkit/odds_provider/prop_*.py`; `prop_dk.py` is planned, not built).
- Terms URL: four separate operator terms pages. **None fetched this lane.**
- OUR use: prop capture into the paper prop store; no `data/domains/` corpus stem.
- **Verdict: UNREAD.** Sportsbook and DFS operator terms typically bar automated
  access; that is an expectation, not a reading, and is recorded as such.

## 20. The Odds API -- UNREAD (not held)

- `scripts/platformkit/odds_provider/oddsapi_provider.py` exists and is key-gated. No
  key is held and no rows were acquired from it. Its terms are a subscription
  agreement; acquiring one is a purchase decision, not a lane's.
- **Verdict: UNREAD.**

## 21. RotoWire projected lineups -- UNREAD

- `src/ingest/lineup_data.py` scrapes RotoWire for projected starters into
  `data/lineups_<date>.json` (legacy NBA path). Terms not fetched.
- **Verdict: UNREAD.**

---

## The three highest-exposure rows

1. **ESPN / Disney (row 1).** Widest footprint -- corpora in all five sports plus one
   of three odds providers -- against the only clause in this ledger that names
   "testing, benchmarking or validation of any ... model ... [or] algorithm" by name.
   S52 already closed on it. The S62 hold (no further ESPN fetching into corpora) is
   the current mitigation.
2. **MLB Stats API + Statcast (rows 3 and 4).** "Only individual, non-commercial,
   non-bulk use" against 321,012 player-gamelog rows, 763 MB of raw Statcast, and the
   GUMBO live poller. The word "non-bulk" is the sharpest single-word conflict here.
3. **Sackmann tennis (row 10).** The entire tennis spine -- 30,616 ATP + 11,270 WTA
   matches and 2.4M point rows, the corpus behind S03 -- rests on a licence we have
   never read, from repositories that return 404 today. If the docstring's CC BY-NC-SA
   is correct, the NonCommercial term makes it a DECIDE, and there is currently no way
   to check.

Runner-up worth naming: **sportsbookreviewsonline (row 13)**, the frozen 2010-2021 MLB
spine, ~28k rows on a source with no terms page at all.

---

## NOT VERIFIED

- **No source in this ledger has had its terms verified by anyone qualified to read
  them.** Every entry is an operational reading of a published page by an agent, done
  so the decision is reviewable. No legal advice is given or implied.
- Twelve of twenty-one rows are UNREAD. UNREAD is not a pass: it means the question
  is open, not that the use is fine.
- Rows 1 (ESPN/Disney) and 13-14 (sportsbookreviewsonline, Hugging Face) reproduce
  readings made by the S52 lane on 2026-09-03; this lane did not re-fetch those pages.
- The StatsBomb quotes come from a PDF whose text layer omits inter-word spaces. Word
  spacing was restored by hand; no other change was made. A reader checking this
  should re-read the PDF rather than trust the transcription.
- The MLBAM notice at `gdx.mlb.com/components/copyright.txt` governs "the referring
  page". Applying it to `statsapi.mlb.com` and `baseballsavant.mlb.com` is an
  inference from common ownership; a terms page specific to either host was not located.
- The NBA.com terms carry no clause naming robots, scrapers or AI training. The
  DECIDE verdict on row 2 rests on the broad reproduction bar alone.
- Kalshi (429) and Polymarket (client-rendered) could not be read at all. Both were
  attempted twice, with and without a browser user agent.
- The four reachability probes in row 10 (github.com, raw.githubusercontent.com, two
  api.github.com calls) plus the control probe were HTTP GETs against repository
  metadata. No data file was downloaded and no corpus was written by this lane.
- Row counts are `parquet` metadata row counts and file counts read on 2026-09-03;
  they are point-in-time and the capture daemons keep moving rows 11-12.
- Terms were NOT fetched for rows 16-21 (Basketball Reference, KBO, NPB, the four DFS
  feeds, The Odds API, RotoWire). Those rows are enumerated so the census is
  exhaustive, not because they were assessed.
- No enumeration can prove itself complete. This ledger was built from `docs/DATA.md`,
  `domains/*/ingest_*.py`, `scripts/platformkit/odds_provider/`, `scripts/fetch_*.py`
  and a read-only walk of `data/domains/` + `data/cache/`. A source reached only from
  `src/` or from a one-off script outside those paths could be missing.
