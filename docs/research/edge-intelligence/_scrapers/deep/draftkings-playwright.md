# DraftKings -- DEEP scrape/acquisition spec (Playwright-FALLBACK; keyless host found)

_Deep, actionable layer of `_scrapers/data-acquisition.md` D4. Grounds in the existing probe
`scripts/draftkings_scraper.py` (NBA player props, curl_cffi). ASCII only. No $-edge claims._
_POLICY NOTE: data-acquisition.md D4 originally scoped a browser-scraped DK OUT. THIS SPEC
SUPERSEDES that on one point: a legitimate keyless JSON host (`sportsbook-nash`) DOES exist and
is the sanctioned path; Playwright is the documented FALLBACK only (the main sportsbook host
returns 403 Akamai on a direct GET)._

---

## 1. Endpoints / host -- the 403 wall and the keyless way around it

- BLOCKED (do NOT use directly): the legacy main host
  `https://sportsbook.draftkings.com/sites/US-SB/api/v5/...` returns **403 (Akamai bot wall)**
  on a plain GET. This is the reason DK was scoped out as "browser-scrape only".
- WORKING KEYLESS host (use this): `https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1`
  (`draftkings_scraper.py:_BASE`). Returns **200 + valid JSON** when `curl_cffi` impersonates
  `chrome120`. NO cookie priming required. NO API key. This is a JSON endpoint, not a browser
  scrape -- so it is the SANCTIONED path under the "only add a book with a real public JSON
  endpoint" rule (data-acquisition.md D4).
- Per-stat URL (pregame O/U):
  `{_BASE}/leagues/{leagueId}/categories/{cat}/subcategories/{sub}`
  (`fetch_subcategory`, `draftkings_scraper.py`). NBA `leagueId=42648`.

curl_cffi is REQUIRED here (not plain urllib): the TLS/JA3 fingerprint of `impersonate=
"chrome120"` is what gets past the edge. Headers (`_HEADERS`): browser UA + `Referer`/`Origin`
= `https://sportsbook.draftkings.com/`.

### Category/subcategory map (NBA, the load-bearing magic numbers)
Pregame (LEGACY) O/U categories -- fetch these PRIMARY:
```
pts  -> cat 1215 / sub 12488    reb  -> cat 1216 / sub 12492
ast  -> cat 1217 / sub 12495    fg3m -> cat 1218 / sub 12497
```
Live (in-play) O/U categories -- `cat in {1686,1687,1688,1689}`. These are a PRE-TIP EMPTY-
FALLBACK ONLY and MUST NOT be fetched while any game is live (in-play contamination guard;
see leak rules). STL/BLK/TOV have NO dedicated DK subcategory -> skip in v1 (honest gap).

## 2. JSON shape + the EXACT join path

A subcategory payload has three arrays: `events[]`, `markets[]`, `selections[]`
(`normalize`, `draftkings_scraper.py`).
```
events:   {id -> {startEventDate, ...}}
markets:  [{id, eventId}]
selections: [{marketId, label "Over"/"Under", points (the line), displayOdds.american,
              participants[], id}]
```
Join path (player, stat, line, prices):
```
group selections by selection.marketId
market.eventId -> events[eventId].startEventDate     -> start_time
selection.participants[type=="Player"] (exactly one) -> player_name, player_id
selection.label=="over" -> line=points, over_price=american
selection.label=="under"-> line=points, under_price=american
```
Gotchas already handled: `displayOdds.american` uses U+2212 (true minus) not ASCII '-' --
`_parse_odds` normalizes it. Multi-player Combined/H2H markets (participants != 1) are skipped.
"Milestones" selections (`points is None`) are skipped.

## 3. Pricing -- TWO-WAY AMERICAN (sharp sportsbook)

DK posts two-way American odds (Over/Under) per market. Convert each via `american_to_decimal`
(`base.py:36-49`) and emit `payout_type="sportsbook"`. DK is a SHARP mainline book for props --
its two-way close is the BEST CLV reference of all four sources (sharper than FanDuel,
far sharper than Underdog/PrizePicks). Its value is therefore mostly as a CLV/devig REFERENCE
and a second line-shopping venue (P3), NOT as a soft pocket to attack.

## 4. Sports / leagues carried

Probe is NBA-only (`leagueId=42648`). DK serves all US sportsbook leagues on the same
`sportscontent/dkusil/v1` host -- each is a different `leagueId` with its own category/
subcategory ids (the cat/sub numbers above are NBA-specific and must be re-probed per sport).
MLB/NFL/etc. each need their own `{leagueId, cat, sub}` map.

## 5. Playwright FALLBACK (only if `sportsbook-nash` ever blocks)

If `sportsbook-nash` starts returning 403/JS-challenge to curl_cffi, the documented fallback is
a headless Playwright session that loads the real sportsbook page, lets Akamai's JS run, then
reads the SAME JSON via the page's `fetch` or by intercepting the XHR:
- Launch chromium headless with a real UA + viewport; navigate to the prop page; wait for the
  network-idle XHR to `.../sportscontent/dkusil/v1/...`; capture the response body (same shape
  as sec 2, so `normalize` is REUSED unchanged).
- Robustness: Playwright is fragile + ToS-hostile + heavy. It is the LAST resort, behind a flag,
  rate-limited hard (one slate refresh per minute, jittered), and it must DEGRADE to
  `unavailable(...)` (never raise) exactly like the keyless providers. Prefer the keyless
  curl_cffi host until it actually breaks.
- Keep curl_cffi (sec 1) as PRIMARY; Playwright is invoked only when curl_cffi returns 403
  three times in a row.

## 6. Rate-limit / robustness

- N stats x 1 GET each (4 NBA stats = 4 GETs/slate/refresh). `--daemon` loops with
  `--interval` (default 30s); >= 30s, jittered.
- `fetch_subcategory` returns None on non-200/error and logs it; the daemon survives a missing
  stat. A new prop provider class wrapping this MUST honor the provider contract: return
  `unavailable(...)` not None, and NEVER raise.
- curl_cffi `impersonate="chrome120"` is mandatory; plain requests/urllib -> 403.

## 7. Leak / honesty rules (binding)

1. IN-PLAY CONTAMINATION GUARD (the load-bearing rule, already implemented): the live category
   ids 1686-1689 serve in-play prices. When ANY NBA event is IN_PROGRESS/STARTED, fetch ONLY
   the legacy 1215-1218 pregame categories and NEVER 1686-1689 -- an in-play price written under
   `book="dk"` would contaminate pregame edges/CLV. Data-loss-safe variant: if liveness
   detection fails (treat as UNKNOWN), behave as the no-live branch, and only THEN may
   1686-1689 be used as an empty-fallback when a legacy category returns zero rows pre-tip. The
   `_DK_LIVE_CAT_IDS` assert enforces "no live cat fetched while a game is live."
2. LEAK: `events[eid].startEventDate` is the tip time -> set as `start_time` and gate
   `as_of < start_time`; live lines are a separate P2 feed.
3. SHARP-BOOK FRAMING: DK is sharp; an "edge vs DK" is almost certainly a name-match error or
   a stale line, NOT a real edge. Use DK as a CLV/devig REFERENCE and line-shopping venue,
   not as a soft pocket. Tier any DK-priced edge skeptically.
4. STL/BLK/TOV are not exposed -> honest coverage gap, do not synthesize them.

## 8. EXACT code change to wire it as a PropProvider

The existing `scripts/draftkings_scraper.py` writes a CSV (`data/lines/<date>_dk.csv`) and is
NOT a `PropProvider`. To plug DK into the prop board, add a NEW provider in the platformkit
package mirroring the keyless providers (build in `scripts/platformkit/`, NOT in `src/`):

- New file `scripts/platformkit/odds_provider/prop_draftkings.py` with class
  `DraftKingsProvider` (`name="draftkings"`), `fetch_props(sport)` ->
  `list[PropLine] | unavailable(...)`:
  - inject `http_get` like the other providers, but the DEFAULT uses
    `from curl_cffi import requests as cf_req; cf_req.get(url, headers=_HEADERS,
    impersonate="chrome120", timeout=15)` (NOT plain urllib).
  - for each `(stat, (cat, sub))` in an NBA stat map, GET the subcategory, REUSE the `events/
    markets/selections` join from `draftkings_scraper.normalize` to build `PropLine` rows with
    `over_price/under_price = american_to_decimal(american)`, `payout_type="sportsbook"`,
    `source="draftkings"`, `as_of=now`, `scheduled_at=startEventDate`.
  - apply the in-play guard (sec 7.1): skip 1686-1689 if any event is live.
  - degrade to `unavailable(...)` on any failure; NEVER raise.
- Add stat-label mapping to `prop_base.py:_STAT_CANON` for NBA (PTS/REB/AST/FG3M).
- Include it in `prop_edge._default_providers()` (`prop_edge.py:58-59`) once NBA is a
  `_SUPPORTED` sport with an NBA distribution model (see prizepicks.md/underdog.md sec 7).
- Add `scripts/platformkit/odds_provider/test_prop_draftkings.py` with `normalize`-on-canned-
  JSON unit tests + a network-gated live smoke test that records the real payload.

Bottom line: DK is the SHARP CLV reference, reachable keylessly via the `sportsbook-nash` JSON
host with curl_cffi chrome120 impersonation. Playwright is the documented fallback, not the
plan. Use DK to MEASURE edges (devig/CLV) and shop lines, not as a pocket to beat.
