# FanDuel NJ sportsbook -- DEEP scrape/acquisition spec (real two-way American props)

_Deep, actionable layer of `_scrapers/data-acquisition.md` B5. Grounds in the live code
`scripts/platformkit/odds_provider/prop_fanduel.py`. ASCII only. No $-edge claims._
_STATUS: BUILT but STRANDED + UNVALIDATED on prop payloads -- the highest-value strand to
un-strand (a real sportsbook two-way price = the best devig/CLV reference for props)._

---

## 1. Endpoints / host (KEYLESS via STATIC public app key)

Two-step navigation; both keyless but require the static app key `_ak` on every URL.
- Static app key: `_ak = "FhMFpcPWXMeyZxOx"` (`prop_fanduel.py:46`) -- a public, baked-in app
  key, NOT a secret/credential. (Region host: NJ. Other states have parallel hosts e.g.
  `sbapi.va.sportsbook.fanduel.com`; the NJ host is what is wired.)
- Host: `https://sbapi.nj.sportsbook.fanduel.com/api` (`_HOST`, `:47`)
1. Content-managed page (lists events for a competition):
   `GET {_HOST}/content-managed-page?page=CUSTOM&customPageId=<pid>&_ak=<ak>&timezone=America%2FNew_York`
   (`_PAGE_URL`, `:48-49`)
2. Event page (markets for ONE event, incl. player props when posted):
   `GET {_HOST}/event-page?_ak=<ak>&eventId=<eid>` (`_EVENT_URL`, `:50`)

Auth: keyless apart from the static `_ak`. Browser UA + `Accept: application/json` (`:51-52`).

## 2. JSON shape + the EXACT join path

Content-managed page -> `attachments.events{ eventId -> {name "Team v Team", openDate,
eventTypeId} }`. `list_event_ids` (`prop_fanduel.py:173-185`) keeps events whose `name`
contains " v " or " @ " (real matches, drops outright/futures cards).

Event page -> two relevant maps under `attachments`:
- `layout.tabs{ tabId -> {title} }` : the prop CATEGORIES (e.g. "Shots", "Saves", "Assists",
  "Cards + Fouls", "Shots on Target"). These name the player-prop groups.
- `attachments.markets{ marketId -> {marketName, bettingType, eventId, runners[]} }`
  runner: `{runnerName, handicap, winRunnerOdds.americanDisplayOdds.americanOdds}`

Join path (player, stat, line, prices), `parse_event_props` (`prop_fanduel.py:108-170`):
```
market.marketName  -> _split_stat(marketName)  -> stat   (canon; None => skip non-prop market)
runner.handicap (!=0)                           -> line   (the O/U line, shared by both runners)
runner.runnerName ~ "Over"/"Under"              -> which side
runner.winRunnerOdds.americanDisplayOdds.americanOdds -> american -> american_to_decimal
                                                -> over_price / under_price (decimal)
a player-named runner (not Over/Under)          -> player (one-sided "X+ / anytime" markets)
events first value.name                         -> match  "Team v Team"
```
`_split_stat` (`:95-105`) matches a known stat fragment in `_PLAYER_STATS` (`:59-62`:
shots on target, shots, saves, tackles, assists, passes, fouls, cards, offsides, clearances,
crosses) so team/match markets (Moneyline, Penalty) are skipped. Player NAME parsing is the
known weak spot (see honesty rules) -- on a true two-runner O/U the player is in the
marketName, not a runner, so `player` falls back to the market name (`:160`).

## 3. Pricing -- TWO-WAY AMERICAN (real sportsbook)

FanDuel posts TWO-WAY American odds per runner. Each side's `americanOdds` is converted via
`american_to_decimal` (`base.py:36-49`) and emitted `payout_type="sportsbook"`
(`prop_fanduel.py:149,151,166`). An O/U prop = two runners ("Over"/"Under") sharing one
`handicap` (the line). One-sided "to score / X+" markets are recorded honestly as the single
side seen. This is a SHARP-er two-way price than Underdog -- it is the best devig/CLV
reference available for props once posted.

## 4. Sports / leagues carried + STRANDED status

Today wired: `_PAGE_ID = {"soccer_intl": "fifa-world-cup"}` (`prop_fanduel.py:55`). FanDuel
covers every US sportsbook league; each is a different `customPageId` (e.g.
`nba`, `mlb`, `nfl`, competition-specific soccer page ids). Map a new sport by adding a
`customPageId`.

STRANDED / UNVALIDATED (honest): this provider is in NO consumer --
`prop_edge._default_providers()` is `[UnderdogProvider(), PrizePicksProvider()]` only
(`prop_edge.py:58-59`). Per its own docstring (`prop_fanduel.py:23-27`), at probe time FanDuel
had posted NO World Cup player-prop markets (the prop TABS existed but carried only Moneyline
+ Penalty markets), so `parse_event_props` has NEVER run against real prop data -- it is
written against the observed market/runner shape of the live moneyline markets. Live path
correctly degrades to `unavailable("no player-prop markets posted")` (`:220-221`).

## 5. Rate-limit / robustness

- N+1 fan-out: 1 content-page GET + 1 event-page GET per listed event (`:205,212-213`). For a
  full WC slate that is ~1 + (#events). Heavier than Underdog's single GET -- cache the
  content-page (event list changes slowly) and only re-pull event-pages near kickoff.
- 12s timeout (`:74`). On ANY error `_default_http_get` returns `{}` (`:76-78`); `fetch_props`
  degrades to `unavailable(...)` and NEVER raises (`:216-222`); a bad event-page is skipped,
  not fatal (`:214-215`).
- Anti-bot posture: FanDuel sbapi is reachable with the static `_ak` + browser UA (no Akamai
  block on the sbapi host, unlike DK's main sportsbook host -- see draftkings-playwright.md).
  If the host starts geofencing the IP, fall back to a different region host.

## 6. Leak / honesty rules (binding)

1. LEAK: `events[eid].openDate` is the event time. A line is valid only if `as_of < openDate`.
   `as_of` is stamped (`_now_iso()` `:124`); `openDate` is NOT yet captured -- ADD it onto the
   row and gate for CLV/grading. Live in-game FanDuel prices are a SEPARATE P2 feed; never
   fold them into a pregame snapshot.
2. DO NOT FABRICATE: a market with no usable Over/Under price or no line is skipped
   (`:154`); no prop markets => honest unavailable. The parser is UNVALIDATED on real prop
   payloads -- treat its first real-data run as a probe to be recorded, not trusted.
3. PLAYER-NAME RISK: on true two-runner O/U props the player identity lives in `marketName`,
   so `player` may be the raw market title (`:160`). Before this is bet/graded, parse the
   player out of `marketName` and resolve it via the same resolver used for the board
   (`domains/<sport>/player_resolver`); a wrong name fabricates a fake edge (the top
   correctness risk per `prop_edge.py` docstring).
4. CALIBRATION TIER: HYPOTHESIS (UNVALIDATED). Cannot be calibration- or CLV-proven until it
   actually returns real prop rows.

## 7. EXACT code change to wire it in (un-strand)

1. Add FanDuel to the consumer behind no-cost inclusion (it self-degrades when no props):
   `scripts/platformkit/prop_edge.py:58-59`
   ```python
   from scripts.platformkit.odds_provider.prop_fanduel import FanDuelProvider
   def _default_providers():
       return [UnderdogProvider(), PrizePicksProvider(), FanDuelProvider()]
   ```
   `_gather` (`prop_edge.py:79-98`) already tolerates an unavailable/erroring provider, so
   adding FanDuel cannot sink the board even while it has no prop markets.
2. Capture the event time: add `openDate` onto each `PropLine` (new optional `scheduled_at`
   field on `PropLine`, `prop_base.py:89-110`) inside `parse_event_props` so leak-gating +
   CLV work.
3. Parse the player from `marketName` in `parse_event_props` (and resolve it) so two-runner
   O/U rows carry a real player, not the market title.
4. Map a new sport: add `customPageId` to `_PAGE_ID` (`prop_fanduel.py:55`), e.g.
   `"nba": "nba"`, and add NBA stat fragments to `_PLAYER_STATS` (`:59-62`) e.g.
   `"points","rebounds","assists","threes","steals","blocks","pts + reb + ast"`, plus the
   `_STAT_CANON` map in `prop_base.py`.
5. Smoke test that RECORDS the real payload: extend
   `scripts/platformkit/test_prop_fanduel.py` with a network-gated test that pulls one live
   event-page, dumps the raw markets/runners JSON to `docs/research/edge-intelligence/_proof/`,
   and asserts `parse_event_props` produces >=1 row IF a prop market is present (skip
   otherwise) -- this is the first validation of the parser on its target shape.

Cross-ref: this is the best two-way devig/CLV reference for props; pair its lines with the
closing-line loop (`prop_line_history.py`) so a FanDuel close exists to measure Underdog/
PrizePicks CLV against (`_scrapers/closing-line-and-clv.md`).
