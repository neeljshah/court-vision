# S62 -- licence ledger for every ingested/held data source: LEDGER BUILT (decision stays human)

Verdict: **LEDGER BUILT.** `docs/evidence/LICENCE_LEDGER.md` now carries one row per
data source the repo ingests or holds, in the S52 format (source, URL, clause quoted
verbatim, date read, permitted use, our use, verdict). **No decision was made and no
gap was closed** -- S62 is a human-gated row and this lane only assembled the evidence
Neel decides from. Nothing was fetched into a corpus; the only network calls were GETs
of publishers' terms pages plus five repository-reachability probes.

## Counts

**21 rows: 6 DECIDE, 3 OK (one conditional), 12 UNREAD.**

| verdict | n | rows |
|---|---|---|
| DECIDE | 6 | ESPN/Disney; NBA Stats API; MLB Stats API/GUMBO; Statcast/Savant; FotMob; YouTube footage |
| OK | 3 | football-data.co.uk; tennis-data.co.uk; StatsBomb open data (conditional) |
| UNREAD | 12 | Sackmann ATP/WTA/slam-pbp; Kalshi; Polymarket; sportsbookreviewsonline; HF `Oronto/...`; Kaggle (not held); Basketball Reference; KBO; NPB; DFS prop feeds; The Odds API; RotoWire |

UNREAD is not a pass. It means the publisher's page could not be read from this box
today, or was never fetched, so no verdict is possible either way.

## The three highest-exposure rows

1. **ESPN / Disney.** The widest footprint in the repo -- corpora in NBA, MLB, soccer,
   soccer_intl, tennis and WNBA, plus one of the three odds providers -- against the
   only clause in the ledger that names "testing, benchmarking or validation of any ...
   model ... [or] algorithm" by name, alongside a bar on compiling "any collection of
   data, data set or database". This is the identical clause pair that closed S52. The
   S62 register hold (no further ESPN fetching into corpora) is the current mitigation.
2. **MLB Stats API + Statcast/Savant.** The MLBAM notice permits "Only individual,
   non-commercial, non-bulk use of the Materials". We hold 321,012 player-gamelog rows,
   11,334 probables, 11,179 current games, 763.2 MB of raw Statcast and a GUMBO live
   poller. "non-bulk" is the sharpest single-word conflict in the ledger.
3. **Sackmann tennis.** The entire tennis spine -- 30,616 ATP + 11,270 WTA matches,
   66,912 player rows, 2,396,887 point-by-point rows, i.e. the S03 gate corpus --
   rests on a licence that has never been read from the publisher. Measured today:
   `github.com/JeffSackmann/tennis_atp` -> 404, the raw CSV URL the ingester uses -> 404,
   and `api.github.com` reports Not Found for both repos while resolving a control repo
   in the same command. Our CC BY-NC-SA claim is a docstring assertion, not a clause.
   If it is right, the NonCommercial term makes this a DECIDE and there is no way to check.

Runner-up: **sportsbookreviewsonline**, the frozen 2010-2021 MLB spine (~28k rows on
each of six corpora), from a source with no terms page at all.

## Two corrections to code docstrings (recorded, NOT applied)

Both are the defect the S62 register row names, and both point the opposite way from
what the docstring says -- the publishers are more permissive than we assumed:

- `domains/soccer/ingest_footballdata.py:6` asserts football-data.co.uk is "free for
  personal/research use only". The page says "My data is free" and "All Rights
  Reserved"; it states **no** scope at all. The docstring invents a restriction.
- `domains/tennis/ingest_tennisdata.py:6-8` is restriction-only ("license-restricted"),
  names no permission, no URL and no date. The publisher's homepage says "All Data is
  free to use" and describes the site's purpose as helping users "develop quantitative
  tennis betting systems".

`domains/` is outside this lane's write scope, so neither file was touched.

## What did NOT happen

- No corpus was fetched, built or extended. `data/` was not written.
- No verdict was decided. Every DECIDE stays Neel's.
- No gap was closed; S62 stays OPEN and human-gated.
- No ledger row was charged, no bar was moved, no mechanism was re-scored.

## NOT VERIFIED

- No source has had its terms verified by anyone qualified to read them. Every entry
  is an operational reading of a published page. No legal advice is given or implied.
- 12 of 21 rows are UNREAD; 6 of those 12 (Basketball Reference, KBO, NPB, DFS feeds,
  The Odds API, RotoWire) were never fetched at all -- they are enumerated so the
  census is exhaustive, not because they were assessed.
- Rows for ESPN/Disney, sportsbookreviewsonline and the Hugging Face dataset reproduce
  the S52 lane's readings of 2026-09-03; those pages were not re-fetched here.
- The StatsBomb quotes come from a PDF whose text layer omits inter-word spaces; word
  spacing was restored by hand and nothing else changed.
- The MLBAM notice governs "the referring page"; applying it to statsapi.mlb.com and
  baseballsavant.mlb.com is an inference from common ownership, not a host-specific
  terms page.
- NBA.com's terms name no robot/scraper/AI clause; that DECIDE rests on the broad
  reproduction bar alone.
- Kalshi returned HTTP 429 on every attempt and Polymarket's terms are client-rendered
  (HTTP 200, 6,693 chars of shell, none of the searched terms present). Both unread.
- Row counts are parquet metadata and file counts read 2026-09-03; the capture daemons
  keep moving the Kalshi/Polymarket tick totals.
- The enumeration cannot prove itself complete. It was built from `docs/DATA.md`,
  `domains/*/ingest_*.py`, `scripts/platformkit/odds_provider/`, `scripts/fetch_*.py`
  and a read-only walk of `data/domains/` + `data/cache/`. A source reached only from
  `src/` or a one-off script outside those paths could be missing.
