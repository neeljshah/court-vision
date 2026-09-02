# Licence record -- historical MLB moneyline close, 2022-2025 (S52)

Assessed 2026-09-03. Purpose of the intended corpus: a two-sided pregame closing
moneyline per MLB game, joined onto `data/domains/mlb/games_current.parquet`, used
to score and calibrate a forecasting model. That purpose is what each licence
below is read against. Calibration evidence only.

**Verdict: no permissive source was found. NOTHING WAS FETCHED INTO A CORPUS and
no fetcher was landed.**

---

## 1. ESPN (Disney) -- the only free source that carries the data. BLOCKED.

- Data URL probed: `https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/events/<event>/competitions/<competition>/odds`
- Terms URL: <https://disneytermsofuse.com/english/>
- Terms last updated (as printed on the page): **May 24, 2024**. Read 2026-09-03.

ESPN is inside the scope of this agreement (Introduction):

> "certain websites, software, applications, content, products, and services in
> any media format or channel, now known or hereafter devised ("Disney Products"
> and "Products"), which may be branded Disney, ABC, ESPN, Marvel, Pixar,
> Lucasfilm, FX, Searchlight Pictures, 20th Century Studios, National Geographic,
> or another brand owned or licensed by Disney."

Two independent clauses block this use.

**(a) Prohibited Activities, item x** -- forbids automated collection into a data
set, by name:

> "access, monitor, copy or extract the Disney Products using a robot, spider,
> script, or other automated means, including, for the avoidance of doubt, for the
> purposes of creating or developing any AI Tool, data mining or web scraping or
> otherwise compiling, building, creating or contributing to any collection of
> data, data set or database (other than for a public search engine's use of
> spiders for creating search indices to the extent not disallowed by Disney,
> including through the applicable robots.txt files or NOINDEX or NOFOLLOW
> meta-tags)"

**(b) Consumer License** -- forbids the downstream use even if the data were
already held:

> "we grant you a limited, non-exclusive, non-sublicensable, non-transferable
> license to access and use in the United States such software, content, virtual
> item or other material for your personal, noncommercial use only, ... with no
> right to reproduce, distribute, communicate to the public, make available to the
> public, or transform any Disney Product, including in connection with any use,
> creation, development, modification, prompting, fine-tuning, training, testing,
> benchmarking or validation of any artificial intelligence or machine learning
> tool, model, system, algorithm, product or other technology ("AI Tool"), in any
> media format or channel now known or hereafter devised"

Clause (b) names "testing, benchmarking or validation of any ... model ...
[or] algorithm". Scoring a forecaster against a close IS benchmarking and
validation of a model. There is no reading of this corpus's purpose that falls
outside the clause, so the source is refused on licence, not on feasibility.

Disclosure of what was done before the terms were read: about 95 read-only
requests were issued to ESPN endpoints to establish whether the data existed at
all (see the coverage probe in `S52_mlb_close_acquisition_2026-09-03.md`). No
file was written under `data/`, no corpus was built, and no fetcher exists.

## 2. sportsbookreviewsonline.com -- the source of the EXISTING local corpus. Coverage ends 2021.

- URL: <https://www.sportsbookreviewsonline.com/scoresoddsarchives/mlb/mlboddsarchives.htm>
  (HTTP 200 on 2026-09-03 with a browser user agent; HTTP 404 to a plain fetcher).
- Page text, verbatim:

> "Historical scores and odds data from past Major League Baseball seasons
> including runlines, opening and closing moneylines and totals. MLB scores and
> odds archive will not be updated."

- Seasons listed on the page: MLB 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014,
  2013, 2012, 2011, 2010. **Nothing after 2021.**
- This range (2010..2021) matches `data/domains/mlb/odds.parquet` exactly
  (28,004 rows, 2010-04-04..2021-11-02, per S10), so this archive is almost
  certainly where the existing local MLB corpus came from. It is dead for the
  S52 window regardless of its terms, so its terms were not pursued.

## 3. Kalshi public API -- permissive access, but the 2025 markets are empty. UNAVAILABLE.

- URL: `https://api.elections.kalshi.com/trade-api/v2/...`, keyless, HTTP 200.
- Measured 2026-09-03: `GET /events?series_ticker=KXMLBGAME&status=settled`
  paged 22 times and returned **4,298 settled MLB game events -- 2,203 with a
  2025 ticker and 2,095 with a 2026 ticker**.
- But `GET /events/KXMLBGAME-25OCT31LADTOR?with_nested_markets=true` returns
  `"markets": []`, and `GET /markets?event_ticker=...` returns 0 markets under
  every status tried (unset / settled / finalized). The same call on a 2026 event
  (`KXMLBGAME-26SEP012140PHIAZ`) returns populated markets.
- So for 2025 there are no market tickers, hence no candlesticks and no prices.
  A second, independent problem: the 2025 event ticker is `KXMLBGAME-25OCT31LADTOR`
  with **no `hhmm` field**, so it carries no first-pitch clock either (the 2026
  ticker does -- that is the clock S10 used).
- Refused on availability, not on licence; the licence was therefore not pursued.

## 4. Sources refused on their own terms (not fetched, not probed)

- **OddsPortal-derived scrapers** (`OddsHarvester` and similar): the data would be
  taken from oddsportal.com, whose terms forbid automated collection and
  redistribution. Not probed.
- **Covers.com / SportsOddsHistory**: the MLB page is a **futures** archive
  (World Series and similar), confirmed 2026-09-03 -- it carries no per-game
  moneyline at all, so the terms question does not arise.

## 5. Sources refused on authenticity

- **Hugging Face `Oronto/mlb-game-prediction-data`**, declared `license: mit`,
  advertised as MLB 2000-2024 with "Vegas odds". Downloaded and read 2026-09-03:
  `vegas_odds.csv` is **1,052 rows and every row carries `odds_source = "mock_data"`**.
  It is synthetic. An MIT label on redistributed prices also does not launder the
  upstream publisher's terms where the provenance is unnamed, as it is here.

## 6. Commercially licensed feeds -- not a lane decision

The Odds API (historical from mid-2020), Odds Warehouse, SportsDataIO and
BigDataBall all sell a licensed historical MLB moneyline series covering
2022-2025. Each requires credentials and a paid licence, so acquiring one is an
orchestrator/human purchase decision, not something a lane may do. None was
contacted and none was probed.

---

## What would have to be true to re-open S52

A source that is (a) free of a clause forbidding model benchmarking or automated
collection, (b) covers 2022-2025, (c) carries both sides, and (d) is fetchable
without credentials. No candidate met all four on 2026-09-03.
