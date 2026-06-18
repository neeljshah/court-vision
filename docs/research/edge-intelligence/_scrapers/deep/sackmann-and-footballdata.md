# DATASOURCE: Sackmann (tennis) + football-data.co.uk (soccer) -- keyless RESULT corpora + odds history

_Part of the edge-intelligence corpus (_scrapers/deep/). Per-source deep spec for the two
keyless historical CORPUS sources: Jeff Sackmann ATP/WTA CSVs and football-data.co.uk club
CSVs. These are NOT live `OddsEvent` feeds -- they are as-of feature backbones (and, for
football-data, a HISTORICAL closing-odds series). Grounded in
`domains/tennis/ingest_sackmann.py`, `domains/soccer/ingest_footballdata.py`, and
_scrapers/data-acquisition.md C2/C3 + project-deep-dive 12. ASCII only._

EDGE-UNLOCK: mostly EFFICIENT pregame MAINLINES (cut-list CUT 1) -> CALIBRATION / decision-
support, NOT a $-edge. Their real value: (a) deep multi-season corpora for OOS calibration
cross-validation (the >=2-corpora discipline), (b) football-data's real *C closing columns =
the ONLY genuine captured CLOSE anywhere in the corpus (a CLV reference), (c) the substrate a
future tennis/soccer PROP layer (a P1 pocket) would sit on. TIER: calibration.

---

## A. JEFF SACKMANN ATP/WTA -- `domains/tennis/ingest_sackmann.py`

### A.1 Endpoint + auth
- Base: `https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master` and `.../tennis_wta/
  master` (`ingest_sackmann.py:27-28`). KEYLESS raw-GitHub CSV. UA
  `tennis-domain-ingest/1.0 (private research; github.com/JeffSackmann)` (`:29`).
- Files: per-tour `<tour>_players.csv` (always re-fetched, mutable) and per-year
  `<tour>_matches_<yr>.csv` (`fetch_raw`, `:99-140`). Idempotent: a cached match file with
  size>0 is SKIPPED unless `--force` or it is the current year (`:133`). Politeness 0.5s,
  3 retries with backoff; HTTP 404 RECORDED not raised (`:91-93`).
- LICENSE: CC BY-NC-SA -- private research only; nothing derived goes to the public repo
  (`:3-4` + data-vault-nocommit rule). `data/domains/tennis/` is never tracked.

### A.2 What it covers / corpus size
- ATP + WTA match history: winner/loser ids, names, ranks, surface, round, best_of, score,
  minutes, tourney level. Corpora: ATP 30,616 rows (2015-2025), WTA 11,270
  (data-acquisition C2). NO odds, NO props, NO in-match points (point-by-point lives in a
  separate Sackmann repo, not ingested).
- Tour-level filter keeps G/M/A/F/D/O + numeric 250/500, DROPS Q/C challengers
  (`ingest_sackmann.py:242-243`).

### A.3 Schema + the LEAK-FREE orientation rule (load-bearing)
- `matches.parquet` contract `MATCHES_REQUIRED_COLS` (`:45-50`): `event_id, date, tour,
  tourney_id/name/level, surface, best_of, round, match_num, p1_id/p2_id, p1_name/p2_name,
  p1_rank/p2_rank, winner, score, retirement, minutes`.
- **Outcome-blind orientation (kills label leak):** `p1 = min(winner_id, loser_id)`
  (`_transform_matches:211-219`); `winner` is then 1 or 2. Orientation does NOT encode who won,
  so a model cannot peek at the result via row order. This is the binding leak rule for any
  tennis feature/predictor built on it.
- `event_id` = `YYYYMMDD-tour-tourney_id-p1_id-p2_id-match_num` (`:231-235`), deterministic,
  with deterministic dedup suffixing (`:246-251`). `load_matches` (`:257`) is the single
  authoritative loader and re-applies the pinned chronological sort.

### A.4 Relationship to OddsEvent / odds_shop
- NONE directly. Sackmann has NO prices, so it never produces an `OddsEvent` and never enters
  the `aggregate`/`odds_shop` seam. It feeds the tennis PREDICTOR (`domains/tennis/predictor`,
  `elo*`) whose probabilities can then be devigged-compared to a LIVE tennis line from The Odds
  API (`tennis_atp_*` sport_key, see deep/the-odds-api.md). The corpus is the model side; the
  market side must come from a live odds feed.

### A.5 Closing-line capture plan (tennis)
- Sackmann has NO odds at all -> NO closing line is derivable from it. True tennis CLV REQUIRES
  a live two-way feed captured up-to-first-serve: The Odds API `tennis_atp_*`/`tennis_wta_*`
  (keyed, deep/the-odds-api.md sec 6) is the only sanctioned path. The capture plan is the same
  as any sportsbook source: poll to start, last row before first serve = close,
  `clv_ledger.compute_clv` vs the taken price.
- If a tennis PROP layer is ever added (a P1 pocket), it would be Underdog/PrizePicks tennis
  ids on the existing keyless prop endpoints (data-acquisition D2 pattern) -> `prop_line_history`
  capture, not Sackmann.

### A.6 Verdict
KEEP as a clean keyless calibration corpus. CUT any expectation of edge from it alone -- pregame
ATP/WTA mainlines are efficient (CUT 1). Its job is OOS cross-validation depth and the future
prop substrate. Keep the min-id orientation rule INVIOLATE.

---

## B. FOOTBALL-DATA.CO.UK -- `domains/soccer/ingest_footballdata.py`

### B.1 Endpoint + auth
- Base via `URL_TEMPLATE.format(season=sc, div=div)` from `domains/soccer/config` (CSV per
  league-season, e.g. `mmz4281/<season>/<div>.csv`). KEYLESS. UA
  `soccer-domain-ingest/1.0 (private research; football-data.co.uk)` (`:30`). Idempotent: a
  cached file with size>0 is SKIPPED unless `--force` or within the last ~2 years (`:136`).
  404 recorded not raised (`:101-103`). Free for personal/research use only (`:5-6`); private,
  never tracked.

### B.2 What it covers / corpus size
- Club football match RESULTS + a per-match ODDS HISTORY across many books. `matches.parquet`
  25,834 rows (2015-2026; data-acquisition C3). Currently the OVER/UNDER 2.5 totals market is
  the modeled one (`build_matches` derives `target_over25 = total_goals>=3`, `:167-168`).
- This is the ONLY source in the whole corpus that ships BOTH a pre-match AND a real CLOSING
  odds column per match.

### B.3 Schema -> two parquets
- `matches.parquet` `MATCHES_COLS` (`:33-36`): `event_id, date, season, div, home_team,
  away_team, fthg, ftag, total_goals, target_over25, ftr`. `event_id` =
  `YYYYMMDD-div-slug(home)-slug(away)` (`_make_event_id:53-57`), deterministic.
- `odds.parquet` `ODDS_COLS` (`:37-45`): per-event O/U-2.5 prices with explicit PRE-MATCH vs
  CLOSE legs and a best-price fallback book.

### B.4 The PRE-MATCH-vs-CLOSE data contract (BINDING -- the genuine closing line + the leak trap)
From `build_odds` docstring (`ingest_footballdata.py:184-196`), the load-bearing distinction:
- `ou_prematch_*` / `book_prematch` come from the NON-C columns (`P>2.5`, `Avg>2.5`, `B365>2.5`)
  = the scraped pre-match price (a near-close / latest weekly SNAPSHOT), **NOT a true exchange
  OPENER**.
- `ou_close_*` / `book_close` come from the explicit *C series (`PC>2.5`, `AvgC>2.5`,
  `B365C>2.5`) = the genuine CLOSING price.
- **DO NOT compute CLV / line movement as `(close - prematch)`** -- the prematch leg is NOT a
  genuine opener, so any such delta is FABRICATED (`:190-193`). This is an explicit
  anti-fabrication guard and must be respected anywhere CLV/line-movement is touched. True CLV
  needs a real captured opener from a LIVE feed; football-data gives you a real CLOSE but not a
  real opener.
- Best-price fallback (`_best_price:64-85`): pre-match `P>2.5 -> Avg>2.5 -> B365>2.5`; close
  `PC>2.5 -> AvgC>2.5 -> B365C>2.5`. `_safe_float` (`:59-62`) nulls any decimal <=1.0.

### B.5 Relationship to OddsEvent / odds_shop -- the CLOSE reference
- football-data does NOT emit live `OddsEvent`s (it is a historical batch corpus), so it is not
  in `aggregate`. BUT its `ou_close_over`/`ou_close_under` ARE a genuine two-way close that can
  be devigged with the SAME `odds_shop.devig_twoway` (Shin) used everywhere else -> a fair-close
  probability for the O/U-2.5 totals market. That makes it the one place a HISTORICAL backtest
  can compute true CLV-vs-close (taken pre-match price vs devigged close) WITHOUT a live capture
  loop -- the cleanest market-efficiency proof we have for soccer totals (cf. the NBA full-season
  backtest "CLV ~0" result, MEMORY).
- Honest limit: it is O/U-2.5 only and historical (no forward, no props), so it proves
  efficiency / calibrates the totals model; it is NOT a forward CLV ledger and does NOT gate
  real money (that still needs the live up-to-kickoff capture in closing-line-and-clv.md).

### B.6 Closing-line capture plan (soccer)
- HISTORICAL close: already captured -> just use `ou_close_*` (devig via `odds_shop.devig_twoway`)
  as the close in any soccer-totals backtest. NEVER pair it with `ou_prematch_*` as an opener
  for line-movement (B.4 guard).
- FORWARD close (for real-money gating): football-data is weekly/batch and lands AFTER matches,
  so it CANNOT provide a forward close. Forward soccer CLV needs a live feed captured to
  kickoff -- ESPN `soccer/eng.1` moneyline (single-venue) or The Odds API `soccer_epl` (keyed,
  multi-book), logged per the closing-line-and-clv.md plan. football-data's role is the
  historical/calibration anchor; the live feed is the forward CLV gate.
- A soccer PROP layer (P1) would come from Underdog/PrizePicks soccer ids (already wired for
  soccer_intl) -> `prop_line_history`, not football-data.

### B.7 Verdict
KEEP football-data as the calibration corpus AND the one free historical CLOSING-odds reference
(devig the *C columns). CUT any line-movement metric that treats `prematch` as an opener
(explicit fabrication guard). Pregame soccer totals are efficient (CUT 1); the corpus calibrates
the model and proves efficiency, it is not itself an edge. The genuine edge pockets for soccer
remain P1 props and P2 live lag, which this source does not feed.

---

## Cross-cutting note

Both sources are KEYLESS, idempotent, leak-disciplined (Sackmann min-id orientation;
football-data prematch-is-not-opener guard), and license-restricted (never to public repo).
Neither produces a live `OddsEvent`, so neither touches `aggregate`/`best_line`. Their edge
contribution is indirect: deep OOS calibration corpora + (football-data) a real historical
close for an honest soccer-totals CLV-vs-close proof. The forward, bettable, real-money CLV
still requires the live keyless/keyed feeds documented in the other deep/ specs.
