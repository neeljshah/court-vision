# S52 -- external historical MLB moneyline close (2022-2025): CLOSED (licence)

Verdict: **CLOSED (licence)**. Every candidate that actually carries a two-sided
pregame closing MLB moneyline for 2022-2025 is refused by its own terms; every
candidate whose terms are permissive fails on coverage or availability. **No
fetcher was written, no parquet was produced, `data/` was not written, and
nothing was scraped from a site whose terms forbid it.** The full licence record,
with clauses quoted verbatim and dated, is
`docs/evidence/harness/LICENCE_mlb_close_history.md`.

S10 stands unchanged: the modern MLB close join is 8.17 pct (913 / 11,179) and
its memo already named the real fix as "an external historical MLB close source".
This lane measured that there is no free one.

## The source table (all measured or read 2026-09-03)

| source | 2022-2025 coverage | both sides | close labelled | fetch without credentials | licence / terms | verdict |
|---|---|---|---|---|---|---|
| ESPN core API v2 `/odds` | 2022 none; 2023/2024/2025 present (probe below) | yes -- `homeTeamOdds` and `awayTeamOdds` | yes -- explicit `close.moneyLine.value` decimal, separate from `open` and `current` | yes, keyless, HTTP 200 | Disney/ESPN ToU (upd. 2024-05-24): no automated collection into a "collection of data, data set or database"; licence carries "no right to ... transform ... in connection with any use ... testing, benchmarking or validation of any ... model ... [or] algorithm" | **REFUSED (licence)** -- the clause names this corpus's only purpose |
| sportsbookreviewsonline.com Excel archive | **none** -- seasons listed stop at MLB 2021; page says the archive "will not be updated" | yes | yes (open + close moneylines) | yes | not pursued (dead on coverage) | REJECT (coverage). This range matches the existing local `odds.parquet` 2010-2021 exactly -- it is almost certainly its origin |
| Kalshi public API | 2,203 settled 2025 event tickers, 2,095 for 2026, **0 for 2022-2024** | would be, but no markets returned | no -- settlement close, not pregame | yes, keyless | not pursued (dead on availability) | REJECT (availability): 2025 events return `"markets": []` under every status, so no tickers, no candlesticks, no prices; the 2025 ticker also has no `hhmm`, so no first-pitch clock |
| Hugging Face `Oronto/mlb-game-prediction-data` | advertised 2000-2024 | n/a | n/a | yes | declared `license: mit` | REJECT (authenticity): `vegas_odds.csv` is 1,052 rows and every row has `odds_source = "mock_data"` -- synthetic |
| aussportsbetting.com spreadsheets | unconfirmed (MLB never verified) | ? | ? | **no** -- HTTP 403 to every user agent tried, including a full Chrome string | not reachable to read | REJECT (unfetchable) |
| OddsPortal-derived scrapers (OddsHarvester and similar) | 2022-2025 | yes | yes | scraping | oddsportal.com terms forbid automated collection and redistribution | REJECT (terms) -- not probed |
| Covers.com / SportsOddsHistory | n/a | no | no | - | - | REJECT (coverage): the MLB archive is **futures** (World Series and similar), not per-game moneylines |
| Kaggle MLB Vegas odds datasets | 2012-2021 | yes | yes | needs Kaggle credentials | dataset-declared | REJECT (coverage + credentials) |
| The Odds API / Odds Warehouse / SportsDataIO / BigDataBall | 2022-2025 (mid-2020 onward for The Odds API) | yes | yes/snapshot | **no** -- API key + commercial licence | licensed under subscription | DEFERRED: acquiring a commercial licence is a human decision, not a lane's. None contacted |

## ESPN coverage probe (why the licence question was load-bearing)

Before the terms were read, four sample dates were pulled to establish whether the
data existed at all. Rule: for each game, take the highest-listed provider that is
not a "Live Odds" provider and has `close.moneyLine.value` on BOTH seats.

| date | games on the slate | with a two-sided labelled close | provider |
|---|---|---|---|
| 2022-07-23 | 16 | **0** | none |
| 2023-07-23 | 15 | 10 | ESPN BET (10/10) |
| 2024-07-23 | 15 | 14 | ESPN BET (14/14) |
| 2025-07-23 | 15 | 15 | ESPN BET (15/15) |
| **total** | **61** | **39** | |

2022 is structurally absent, not sparse: 2022 games list many providers
(Caesars, PointsBet, Unibet, MGM, consensus and others) and none of them carries
a `close` block. The `close` series begins with ESPN BET, which became ESPN's
book in late 2023 -- which is consistent with 2023 being partial and 2024-2025
near-complete.

Worked example, event 401569953 (Tampa Bay at NY Yankees, 2024-07-20), ESPN BET:
`homeTeamOdds.close.moneyLine.value = 1.625` and
`awayTeamOdds.close.moneyLine.value = 2.35` -- decimal prices on both seats, which
is exactly the pair `close_join.close_column` devigs.

Had the licence permitted it, the full 2022-2025 pull would have been about
**10,500 requests** (about 186 scoreboard dates plus about 2,430 per-game odds
calls per season, times four seasons) and, at the 0.5 s politeness interval the
soccer ingester already uses, about **1.5 hours** of wall time. That estimate is
recorded so the number is not re-derived; **it will not be run.**

## Why this is CLOSED (licence) rather than CLOSED AT LIMIT

CLOSED AT LIMIT means a bar was measured and missed. Here no join rate was
measured at all, because the only source that could have produced one may not be
collected. The distinction matters: if a permissively licensed 2022-2025 close is
ever acquired, `close_join_mlb.py` needs no change to consume it -- its
`_TOKEN_TO_SPINE` alias path and its `(date, home, away) -> event_id` lookup are
source-agnostic. The gap is acquisition, and acquisition is now a licence
question with a named answer.

## What did NOT happen

- `scripts/platformkit/data/fetch_mlb_close_history.py` was **not** written.
- `data/domains/mlb/close_history.parquet` was **not** produced.
- No 2024 season was fetched, so there is no 2024 row count and no join rate to
  report. 2024 in particular has no candidate source at all: ESPN is refused,
  Kalshi has zero 2024 events, and the free archive family stops at 2021.
- `close_join_mlb.py` was not opened for edit; `data/` was not written.

## NOT VERIFIED

- The ESPN coverage probe is **n = 61 games across 4 single dates**, so every
  per-season number above rests on n = 15 or 16 -- far below the n >= 30 rail.
  These are existence probes, not coverage measurements, and no claim rests on
  them. They are reported only to show that the licence, not the data, is the
  blocker.
- Whether ESPN's `close` is a settled closing line or the last pregame snapshot
  ESPN captured was NOT established -- the field is labelled `close` by the
  publisher and was taken at face value. This was not pursued once the terms
  refused the source.
- The Disney terms were read at `disneytermsofuse.com/english/` on 2026-09-03
  (page states "Last Updated: May 24, 2024"); `espn.com/terms-of-use` returns 404
  and the linkage rests on the agreement's own scope sentence naming ESPN.
- No legal advice is given or implied here. This is an operational reading of a
  published terms page, recorded so the decision is reviewable.
- Terms were NOT read for sportsbookreviewsonline.com, Kalshi, Kaggle or the
  commercial feeds -- each was already refused on coverage, availability or
  credentials, so its terms were not pursued.
- aussportsbetting.com was never read at all (403), so its MLB coverage is
  unverified in both directions.
- The commercial feeds' coverage claims are their own marketing copy, unverified.
- No mechanism was re-scored, no ledger row was charged, no bar was moved, and
  the FWER ledger was not opened. The 22 MLB mechanisms stay NOT_TESTABLE against
  a modern close.
