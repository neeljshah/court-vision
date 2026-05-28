"""scraper_probe.py — fire curl_cffi chrome120 GET against candidate book
endpoints FROM the Railway production IP and report what responds.

Local dev IPs get WAF-blocked by most US sportsbooks, so we cannot tell
from a laptop whether an endpoint is genuinely unscrapable or just
network-conditional. Running the same probe from Railway distinguishes
the two and tells us which book to invest scraper LOC in next.

GET /api/scraper-probe/{book}?token=...
  → {"book": "<bookkey>", "attempts": [{...}]}

The candidate URL registry lives in this file. Add new books by appending
to PROBE_TARGETS and redeploying. The probe is auth-gated so it is not
public.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from curl_cffi import requests as cf_req

PROBE_TARGETS: Dict[str, List[tuple[str, str]]] = {
    "dk": [  # baseline that works locally — confirms the probe itself works
        ("nash sportscontent leagues/42648/cat/1215",
         "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1/leagues/42648/categories/1215"),
    ],
    "betrivers": [
        # Legacy operator keys (retired) — left for regression evidence
        ("kambi rsi nba listView",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsi/listView/basketball/nba.json?lang=en_US&market=US-NJ&client_id=2"),
        ("kambi rsinj nba listView",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsinj/listView/basketball/nba.json?lang=en_US&market=US-NJ&client_id=2"),
        ("americas betrivers regions us-nj lobby",
         "https://api.americas.betrivers.com/regions/us-nj/lobby/bookies?cgroup=BetRivers"),
        ("nj betrivers api service sportsbook lobby",
         "https://nj.betrivers.com/api/service/sportsbook/lobby/bookies?cgroup=BetRivers"),
        # 2026 current operator key = rsiusia (extracted from www.betrivers.com bundle)
        ("kambi rsiusia nba listView US-IA",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsiusia/listView/basketball/nba.json?lang=en_US&market=US-IA&client_id=2"),
        ("kambi rsiusia nba listView US-NJ",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsiusia/listView/basketball/nba.json?lang=en_US&market=US-NJ&client_id=2"),
        ("kambi rsiusia event/group nba (event-list only)",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsiusia/event/group/1000093652.json?lang=en_US&market=US-IA&client_id=2"),
        # Sample per-event betoffer (event id will rotate, kept for shape evidence)
        ("kambi rsiusia betoffer event 1027678168",
         "https://eu.offering-api.kambicdn.com/offering/v2018/rsiusia/betoffer/event/1027678168.json?lang=en_US&market=US-IA&client_id=2&includeParticipants=true"),
    ],
    "espnbet": [
        ("espnbet www landing",
         "https://www.espnbet.com/"),
        ("api espnbet sports",
         "https://api.espnbet.com/sports-data/basketball/leagues/nba/events"),
        ("penn energy espnbet api",
         "https://espnbet-api.penn.energy/api/v1/sports/basketball/nba/events"),
    ],
    "pointsbet": [
        ("nj pointsbet competitions",
         "https://api.nj.pointsbet.com/api/v2/sports/basketball/competitions"),
        ("api pointsbet mes v3 events",
         "https://api.pointsbet.com/api/mes/v3/events/upcoming?key=basketball-nba"),
    ],
    "pp": [
        ("projections league_id=7",
         "https://api.prizepicks.com/projections?league_id=7&per_page=250"),
        ("leagues",
         "https://api.prizepicks.com/leagues"),
    ],
    "underdog": [
        ("v6 over_under_lines",
         "https://api.underdogfantasy.com/beta/v6/over_under_lines"),
        ("v5 pickem_search",
         "https://api.underdogfantasy.com/beta/v5/pickem_search"),
    ],
    "hardrock": [
        ("app hardrock bet sports",
         "https://app.hardrock.bet/api/v1/sports"),
        ("www hardrock bet bsy api",
         "https://www.hardrock.bet/bsy/sportsbook/api/v1/sports"),
        # Discovered 2026-05-27 in app.hardrock.bet/dist/bundle.3.33.12766.js
        # Amelco platform; baseApiURL = https://api.hardrocksportsbook.com
        # Both 200 JSON from any IP (GeoIP filters to empty list off-US-state).
        ("amelco events tree NJ",
         "https://api.hardrocksportsbook.com/sportsbook/api/public/events/tree"
         "?channel=NJ&segment=DEFAULT&region=us&language=enus"),
        ("amelco events tree FL",
         "https://api.hardrocksportsbook.com/sportsbook/api/public/events/tree"
         "?channel=FL&segment=DEFAULT&region=us&language=enus"),
        ("amelco events tree AZ",
         "https://api.hardrocksportsbook.com/sportsbook/api/public/events/tree"
         "?channel=AZ&segment=DEFAULT&region=us&language=enus"),
        ("amelco events tree bare",
         "https://api.hardrocksportsbook.com/sportsbook/api/public/events/tree"),
        # Player-prop lines endpoint (needs a real eventId from the tree).
        # 400 with a fake UUID confirms the route is live.
        ("amelco player markets probe",
         "https://api.hardrocksportsbook.com/java-graphql/players/markets/"
         "00000000-0000-0000-0000-000000000000/lines?channel=NJ"),
    ],
    "fanatics": [
        ("fanatics sportsbook landing",
         "https://sportsbook.fanatics.com/"),
        ("fanatics edge nba events",
         "https://api.sportsbook.fanatics.com/edge/api/v1/sports/basketball/leagues/nba/events"),
        # 2026-05-27 research: Akamai-shielded; /index.html bypasses shim but
        # only serves a Next.js pre-launch marketing page (no API hostnames in
        # HTML or bundles). api.*/edge.*/book-api.* subdomains DNS-fail. Same-
        # origin /api/* returns S3 NoSuchKey XML. Probes below confirm blocker
        # so we can re-check periodically once Fanatics exits pre-launch.
        ("fanatics index unshimmed",
         "https://sportsbook.fanatics.com/index.html"),
        ("fanatics same-origin api (expect s3 NoSuchKey)",
         "https://sportsbook.fanatics.com/api/v1/sports"),
        ("fanatics cds-api same-origin",
         "https://sportsbook.fanatics.com/cds-api/sports-data/sports/"
         "basketball/leagues/nba/events"),
    ],
}

_BASE_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
}


def _one_probe(label: str, url: str) -> Dict[str, Any]:
    """Fire a single curl_cffi chrome120 GET and summarise the response."""
    headers = dict(_BASE_HEADERS)
    # Derive Referer/Origin from URL host so each book sees a plausible referrer
    try:
        scheme_host = url.split("/", 3)
        headers["Referer"] = f"{scheme_host[0]}//{scheme_host[2]}/"
        headers["Origin"] = f"{scheme_host[0]}//{scheme_host[2]}"
    except Exception:  # noqa: BLE001
        pass
    out: Dict[str, Any] = {"label": label, "url": url}
    try:
        r = cf_req.get(url, headers=headers, impersonate="chrome120",
                       timeout=15, verify=False)
    except Exception as exc:  # noqa: BLE001
        out.update({"status": None, "error": f"{type(exc).__name__}: {exc}"})
        return out
    out["status"] = r.status_code
    out["bytes"] = len(r.content)
    out["content_type"] = r.headers.get("content-type", "")
    if "json" in out["content_type"].lower():
        try:
            j = r.json()
            if isinstance(j, dict):
                out["parsed_keys"] = list(j.keys())[:12]
                for k in ("events", "data", "over_under_lines",
                          "items", "markets", "selections"):
                    if isinstance(j.get(k), list):
                        out[f"n_{k}"] = len(j[k])
            elif isinstance(j, list):
                out["parsed_list_len"] = len(j)
        except Exception as exc:  # noqa: BLE001
            out["parse_error"] = str(exc)[:120]
    else:
        out["preview"] = r.text[:160].replace("\n", " ")
    return out


async def probe_book(book: str) -> Dict[str, Any]:
    """Run all candidate probes for one book in a threadpool."""
    targets = PROBE_TARGETS.get(book)
    if not targets:
        return {"book": book, "error": f"no PROBE_TARGETS for '{book}'",
                "known_books": sorted(PROBE_TARGETS.keys())}
    loop = asyncio.get_event_loop()
    attempts = await asyncio.gather(
        *(loop.run_in_executor(None, _one_probe, label, url)
          for label, url in targets),
        return_exceptions=False,
    )
    return {"book": book, "n_attempts": len(attempts), "attempts": attempts}
