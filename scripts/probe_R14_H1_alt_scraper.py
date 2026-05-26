"""probe_R14_H1_alt_scraper.py - probe R14 H1.

PrizePicks is 403-blocking our existing scraper (off-season). C1/C2 CLV pipeline
is starving. This probe tries DraftKings / FanDuel / BetMGM / Caesars public
unauthenticated JSON endpoints to find an alternative free source for NBA player
prop lines. No auth, no brute force, no credential probing.

For each source we record HTTP status, raw row count, and whether the payload
contains structured NBA player-prop data we can map to the canonical schema
(captured_at, book, game_id, player_id, player_name, stat, line, over_price,
under_price, start_time).

If >= 500 rows: write data/lines/<date>_<book>.csv (SHIP).
Else: REJECT and write reason.

Output JSON: data/cache/probe_R14_H1_alt_scraper_results.json
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import traceback
import urllib.request
import urllib.error
from datetime import date as _date
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LINES_DIR, exist_ok=True)

RESULTS_PATH = os.path.join(CACHE_DIR, "probe_R14_H1_alt_scraper_results.json")

CANONICAL_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]

# Stat-name -> canonical short code used everywhere downstream.
STAT_MAP = {
    "points": "pts",
    "player points": "pts",
    "pts": "pts",
    "rebounds": "reb",
    "player rebounds": "reb",
    "total rebounds": "reb",
    "reb": "reb",
    "assists": "ast",
    "player assists": "ast",
    "ast": "ast",
    "three point field goals made": "fg3m",
    "three pointers made": "fg3m",
    "3-pt made": "fg3m",
    "3pt made": "fg3m",
    "made threes": "fg3m",
    "fg3m": "fg3m",
    "steals": "stl",
    "player steals": "stl",
    "stl": "stl",
    "blocks": "blk",
    "player blocks": "blk",
    "blk": "blk",
    "turnovers": "tov",
    "player turnovers": "tov",
    "tov": "tov",
    # Combined markets we skip (not in our 7).
}

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return _date.today().isoformat()


def _http_get(url: str, headers: Optional[Dict[str, str]] = None,
              timeout: float = 15.0) -> Tuple[int, Optional[bytes], Optional[str]]:
    """Return (status_code, body_bytes, error_str). One-shot, no retries.

    Tries `requests` first (TLS fingerprint is closer to a real browser than
    urllib's bare socket TLS, and many sportsbook WAFs gate on JA3), then
    falls back to urllib so the probe still works in a bare-bones env.
    """
    hdr = {
        "User-Agent":      UA_DESKTOP,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",     # avoid gzip decode hassle
        "Referer":         "https://www.google.com/",
        "Origin":          "https://www.google.com",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "cross-site",
    }
    if headers:
        hdr.update(headers)
    try:
        import requests        # type: ignore
        r = requests.get(url, headers=hdr, timeout=timeout, allow_redirects=True)
        return r.status_code, r.content, None
    except Exception:                                                # noqa: BLE001
        pass
    req = urllib.request.Request(url, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.getcode(), body, None
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = None
        return e.code, body, f"HTTPError: {e.reason}"
    except Exception as e:                 # noqa: BLE001
        return 0, None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# DraftKings public JSON
# ---------------------------------------------------------------------------
# DK uses event-group IDs (42648 = NBA). The v5 eventgroups endpoint returns
# events + featured display groups. For player props we need the categories
# endpoint with a category filter (1215 = player props historically; new ID
# may vary by season). We probe both the bare event-group and the categories
# endpoint to see what surfaces.
DK_URLS = [
    ("dk_eventgroup",
     "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/42648?format=json"),
    ("dk_categories_1215",
     "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/42648/categories/1215?format=json"),
    ("dk_categories_583",
     "https://sportsbook-nash.draftkings.com/sites/US-SB/api/v5/eventgroups/42648/categories/583?format=json"),
]


def _dk_walk_offers(payload: dict) -> List[Dict[str, Any]]:
    """Walk a DK eventgroups JSON and return flat player-prop rows."""
    out: List[Dict[str, Any]] = []
    eg = payload.get("eventGroup") or {}
    # Build event_id -> (start, players) lookup.
    events_by_id: Dict[str, Dict[str, Any]] = {}
    for ev in eg.get("events", []) or []:
        events_by_id[str(ev.get("eventId"))] = {
            "start": ev.get("startDate"),
            "name":  ev.get("name"),
        }
    # Offer categories (which is where player props live in v5).
    for off_cat in eg.get("offerCategories", []) or []:
        cat_name = (off_cat.get("name") or "").lower()
        for sub in off_cat.get("offerSubcategoryDescriptors", []) or []:
            sub_name_raw = (sub.get("name") or "")
            sub_name = sub_name_raw.lower()
            stat = STAT_MAP.get(sub_name)
            if not stat:
                # Many sub-categories are "team to win" / "spread" - skip.
                continue
            sub_payload = sub.get("offerSubcategory") or {}
            for offer_block in sub_payload.get("offers", []) or []:
                for offer in offer_block or []:
                    label = offer.get("label", "")
                    if "over/under" not in label.lower() and "o/u" not in label.lower():
                        # Could be alt lines / yes-no - try anyway.
                        pass
                    ev_id = str(offer.get("eventId") or "")
                    ev_meta = events_by_id.get(ev_id, {})
                    outcomes = offer.get("outcomes", []) or []
                    if len(outcomes) < 2:
                        continue
                    # DK outcomes carry the player in `participant` or in the label.
                    player_name = (outcomes[0].get("participant") or
                                   offer.get("participant") or "")
                    if not player_name:
                        # Pull player name from label: "Player Name - Points O/U"
                        if " - " in label:
                            player_name = label.split(" - ", 1)[0].strip()
                    over_price = under_price = None
                    line_val = None
                    for o in outcomes:
                        lbl = (o.get("label") or "").lower()
                        if lbl == "over":
                            over_price  = o.get("oddsAmerican")
                            line_val    = o.get("line")
                        elif lbl == "under":
                            under_price = o.get("oddsAmerican")
                            if line_val is None:
                                line_val = o.get("line")
                    if line_val is None or not player_name:
                        continue
                    out.append({
                        "captured_at": _now_iso(),
                        "book":        "dk",
                        "game_id":     ev_id,
                        "player_id":   "",
                        "player_name": player_name,
                        "stat":        stat,
                        "line":        line_val,
                        "over_price":  over_price,
                        "under_price": under_price,
                        "start_time":  ev_meta.get("start", ""),
                    })
    return out


def probe_draftkings(errors: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    rows_total: List[Dict[str, Any]] = []
    statuses: Dict[str, int] = {}
    for tag, url in DK_URLS:
        code, body, err = _http_get(url)
        statuses[tag] = code
        if err:
            errors.append(f"{tag} {url[:80]} -> {err}")
        if code != 200 or not body:
            continue
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} parse: {e}")
            continue
        try:
            rows_total.extend(_dk_walk_offers(payload))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} walk: {e}")
    return statuses, rows_total


# ---------------------------------------------------------------------------
# FanDuel public JSON
# ---------------------------------------------------------------------------
# FanDuel exposes a JSON content-managed-page API. The NBA league hub:
#   https://sbapi.tx.sportsbook.fanduel.com/api/content-managed-page
#       ?page=CUSTOM&customPageId=nba&pbHorizontal=false
# Player props live under `attachments.markets.*` for each event.
FD_URLS = [
    # 'sb-api' / regional subdomains vary by state. Try a few.
    ("fd_nj_landing",
     "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
     "?page=CUSTOM&customPageId=nba&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"),
    ("fd_pa_landing",
     "https://sbapi.pa.sportsbook.fanduel.com/api/content-managed-page"
     "?page=CUSTOM&customPageId=nba&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"),
    ("fd_tx_landing",
     "https://sbapi.tx.sportsbook.fanduel.com/api/content-managed-page"
     "?page=CUSTOM&customPageId=nba&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"),
    ("fd_competition",
     "https://sbapi.nj.sportsbook.fanduel.com/api/content-competition"
     "?eventTypeId=7522&competitionId=11530&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"),
]


def _fd_walk(payload: dict) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    attach = payload.get("attachments") or {}
    events = attach.get("events") or {}
    markets = attach.get("markets") or {}
    for _mid, m in markets.items():
        mkt_name = (m.get("marketName") or m.get("marketType") or "").lower()
        stat = STAT_MAP.get(mkt_name)
        if not stat:
            # Try to detect "Player Points" / "Player Rebounds" patterns.
            for kw, code in STAT_MAP.items():
                if kw in mkt_name:
                    stat = code
                    break
        if not stat:
            continue
        ev_id = str(m.get("eventId") or "")
        ev_meta = events.get(ev_id, {}) if isinstance(events, dict) else {}
        start  = ev_meta.get("openDate") or ev_meta.get("eventStartTime") or ""
        runners = m.get("runners", []) or []
        # FD player markets typically have 2 runners: Over X.5 / Under X.5,
        # with the player encoded in `runnerName` or in marketName.
        player_name = ""
        if "-" in (m.get("marketName") or ""):
            player_name = m["marketName"].rsplit("-", 1)[0].strip()
        over_price = under_price = None
        line_val = None
        for r in runners:
            r_name = (r.get("runnerName") or "").lower()
            handicap = r.get("handicap")
            wp = (r.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}
            am = wp.get("americanOdds") if isinstance(wp, dict) else None
            if "over" in r_name:
                over_price = am
                if line_val is None and handicap is not None:
                    line_val = handicap
            elif "under" in r_name:
                under_price = am
                if line_val is None and handicap is not None:
                    line_val = handicap
        if not player_name or line_val is None:
            continue
        out.append({
            "captured_at": _now_iso(),
            "book":        "fd",
            "game_id":     ev_id,
            "player_id":   "",
            "player_name": player_name,
            "stat":        stat,
            "line":        line_val,
            "over_price":  over_price,
            "under_price": under_price,
            "start_time":  start,
        })
    return out


def probe_fanduel(errors: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    statuses: Dict[str, int] = {}
    rows_total: List[Dict[str, Any]] = []
    for tag, url in FD_URLS:
        code, body, err = _http_get(url)
        statuses[tag] = code
        if err:
            errors.append(f"{tag} -> {err}")
        if code != 200 or not body:
            continue
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} parse: {e}")
            continue
        try:
            rows_total.extend(_fd_walk(payload))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} walk: {e}")
    return statuses, rows_total


# ---------------------------------------------------------------------------
# BetMGM public JSON
# ---------------------------------------------------------------------------
# MGM Cds endpoint - "competition" = NBA (id 103). Player prop fixtures sit
# inside fixtures -> games. We probe two known shapes.
MGM_URLS = [
    ("mgm_competition_nba",
     "https://sports.nj.betmgm.com/cds-api/bettingoffer/fixtures"
     "?x-bwin-accessid=NDgwODYwLTk2NTktMTI4ODEz&lang=en-us"
     "&country=US&userCountry=US&offerMapping=Filtered&scoreboardMode=Full"
     "&fixtureTypes=Standard&state=Live%2CLatest%2CUpcoming&competitionIds=103"),
]


def probe_betmgm(errors: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    statuses: Dict[str, int] = {}
    rows_total: List[Dict[str, Any]] = []
    for tag, url in MGM_URLS:
        code, body, err = _http_get(url)
        statuses[tag] = code
        if err:
            errors.append(f"{tag} -> {err}")
        if code != 200 or not body:
            continue
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} parse: {e}")
            continue
        # Top-level: fixtures = []. We just count to confirm shape.
        fixtures = payload.get("fixtures") or payload.get("Fixtures") or []
        if not fixtures and isinstance(payload, list):
            fixtures = payload
        if fixtures:
            errors.append(f"{tag} fixtures={len(fixtures)} but player-prop walk not implemented")
    return statuses, rows_total


# ---------------------------------------------------------------------------
# Caesars (William Hill US) public JSON
# ---------------------------------------------------------------------------
CZR_URLS = [
    ("czr_nba_eventgroup",
     "https://api.americanwagering.com/regions/us/locations/nj/brands/czr/sb/v3/sports/basketball/events/schedule/?competitionUri=v1.0:basketball:nba"),
]


# ---------------------------------------------------------------------------
# Bovada public JSON (offshore, frequently un-WAFed)
# ---------------------------------------------------------------------------
BOV_URLS = [
    ("bov_nba_index",
     "https://www.bovada.lv/services/sports/event/coupon/events/A/description/basketball/nba?marketFilterId=def&preMatchOnly=false&eventsLimit=50&lang=en"),
]

# Bovada displayGroup -> our canonical stat code. Many groups are composite
# (e.g. "Assists & Threes") and need per-market description parsing.
BOV_DG_TO_STAT = {
    "Player Points":   "pts",
    "Player Rebounds": "reb",
    "Player Assists":  "ast",
    "Player Threes":   "fg3m",
    "Player Blocks":   "blk",
    "Player Steals":   "stl",
    "Player Turnovers": "tov",
}

# Substrings in a Bovada market description that pin the stat.
BOV_MK_KW = [
    ("Total Points",     "pts"),
    ("Total Rebounds",   "reb"),
    ("Total Assists",    "ast"),
    ("Total Threes",     "fg3m"),
    ("Total 3-Pointers", "fg3m"),
    ("Total Blocks",     "blk"),
    ("Total Steals",     "stl"),
    ("Total Turnovers",  "tov"),
    ("Made Threes",      "fg3m"),
    ("3-Pointers Made",  "fg3m"),
]


def _bov_player_from_desc(desc: str) -> str:
    """Bovada market descriptions are 'Total Points - Player Name (TEAM)'."""
    if " - " not in desc:
        return ""
    tail = desc.split(" - ", 1)[1].strip()
    # Strip trailing team tag '(SAS)'.
    if "(" in tail:
        tail = tail.rsplit("(", 1)[0].strip()
    return tail


def _bov_stat_from_market(dg_desc: str, mk_desc: str) -> Optional[str]:
    """Only emit a stat if the market is a true player prop.

    Player-prop markets are recognised by displayGroup membership in the
    PLAYER_PROP_DGS allowlist AND by the market description containing a
    'Total <stat> - <player> (<team>)' pattern. Game totals and team
    spreads under 'Alternate Lines' / 'Game Lines' are deliberately excluded
    so we don't pollute the CLV ledger with team-side rows.
    """
    PLAYER_PROP_DGS = {
        "Player Points", "Player Rebounds", "Player Assists",
        "Player Threes",  "Player Blocks",   "Player Steals",
        "Player Turnovers", "Assists & Threes", "Blocks & Steals",
    }
    if dg_desc.strip() not in PLAYER_PROP_DGS:
        return None
    # First trust the displayGroup if it pins a single stat.
    s = BOV_DG_TO_STAT.get(dg_desc.strip())
    if s:
        # Even within Player Points, sub-markets like 'Points Milestones' are
        # not Over/Under — they're ladders. Caller's bucket logic will reject
        # them (no over/under outcomes), so it's safe to return the stat.
        return s
    # Then scan the market description.
    for kw, code in BOV_MK_KW:
        if kw.lower() in (mk_desc or "").lower():
            return code
    return None


def probe_bovada(errors: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    statuses: Dict[str, int] = {}
    rows_total: List[Dict[str, Any]] = []
    # Step 1: list events.
    tag, url = BOV_URLS[0]
    code, body, err = _http_get(url)
    statuses[tag] = code
    if err:
        errors.append(f"{tag} -> {err}")
    if code != 200 or not body:
        return statuses, rows_total
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception as e:                                      # noqa: BLE001
        errors.append(f"{tag} parse: {e}")
        return statuses, rows_total

    # Step 2: pull the per-event detail (where player props actually live).
    event_links: List[Tuple[str, str, str]] = []   # (ev_id, link, start)
    if isinstance(payload, list):
        for grp in payload:
            for ev in grp.get("events", []) or []:
                link = ev.get("link") or ""
                if link:
                    event_links.append((str(ev.get("id") or ""),
                                        link,
                                        str(ev.get("startTime") or "")))
    statuses["bov_n_events"] = len(event_links)

    for ev_id, link, start_ms in event_links:
        detail_url = f"https://www.bovada.lv/services/sports/event/coupon/events/A/description{link}?lang=en"
        d_code, d_body, d_err = _http_get(detail_url)
        if d_err:
            errors.append(f"bov_detail {link} -> {d_err}")
        if d_code != 200 or not d_body:
            continue
        try:
            d_payload = json.loads(d_body.decode("utf-8", errors="replace"))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"bov_detail parse: {e}")
            continue
        if not isinstance(d_payload, list):
            continue
        # Start time is epoch-ms; convert to ISO-ish (UTC).
        try:
            start_iso = datetime.utcfromtimestamp(int(start_ms) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:                                       # noqa: BLE001
            start_iso = start_ms
        for grp in d_payload:
            for ev in grp.get("events", []) or []:
                for dg in ev.get("displayGroups", []) or []:
                    dg_desc = (dg.get("description") or "").strip()
                    for mk in dg.get("markets", []) or []:
                        mk_desc = (mk.get("description") or "").strip()
                        stat = _bov_stat_from_market(dg_desc, mk_desc)
                        if not stat:
                            continue
                        player = _bov_player_from_desc(mk_desc)
                        if not player:
                            continue
                        # Group outcomes by handicap so we emit one row per
                        # (player, stat, handicap) with both prices.
                        buckets: Dict[Any, Dict[str, Any]] = {}
                        for out in mk.get("outcomes", []) or []:
                            price = out.get("price") or {}
                            hcap = price.get("handicap")
                            american = price.get("american")
                            side = (out.get("description") or "").lower()
                            try:
                                hcap_key = float(hcap)
                            except (TypeError, ValueError):
                                hcap_key = hcap
                            b = buckets.setdefault(hcap_key, {})
                            if "over" in side:
                                b["over"] = american
                                b["line"] = hcap_key
                            elif "under" in side:
                                b["under"] = american
                                b["line"] = hcap_key
                        for hcap_key, b in buckets.items():
                            if "line" not in b:
                                continue
                            rows_total.append({
                                "captured_at": _now_iso(),
                                "book":        "bov",
                                "game_id":     ev_id,
                                "player_id":   "",
                                "player_name": player,
                                "stat":        stat,
                                "line":        b.get("line"),
                                "over_price":  b.get("over"),
                                "under_price": b.get("under"),
                                "start_time":  start_iso,
                            })
        time.sleep(0.5)        # polite pacing for Bovada
    return statuses, rows_total


def probe_caesars(errors: List[str]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    statuses: Dict[str, int] = {}
    rows_total: List[Dict[str, Any]] = []
    for tag, url in CZR_URLS:
        code, body, err = _http_get(url)
        statuses[tag] = code
        if err:
            errors.append(f"{tag} -> {err}")
        if code != 200 or not body:
            continue
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{tag} parse: {e}")
            continue
        comps = (payload.get("competitions") or [])
        if comps:
            errors.append(f"{tag} competitions={len(comps)} (no player-prop walk yet)")
    return statuses, rows_total


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _write_canonical_csv(rows: List[Dict[str, Any]], book_code: str) -> str:
    path = os.path.join(LINES_DIR, f"{_today()}_{book_code}.csv")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CANONICAL_FIELDS)
        w.writeheader()
        for r in rows:
            # Ensure every canonical field present.
            row_out = {k: r.get(k, "") for k in CANONICAL_FIELDS}
            w.writerow(row_out)
    return path


def _schema_match(row: Dict[str, Any]) -> bool:
    """All canonical fields present and the load-bearing ones non-empty.

    `over_price` / `under_price` may legitimately be absent for one-sided
    markets, so they are not required. CLV is computed per side, so a row
    with only one side still flows through `enrich_pnl_with_clv`.
    """
    if not row:
        return False
    needed = ("player_name", "stat", "line", "book")
    return all(row.get(k) not in (None, "") for k in needed)


def main() -> int:
    started = time.time()
    errors: List[str] = []
    tried: List[str] = []
    rows_per_source: Dict[str, int] = {}
    schema_match_for_clv = False
    ship_status = "REJECT"
    ship_path: Optional[str] = None

    sources = [
        ("draftkings", probe_draftkings),
        ("fanduel",    probe_fanduel),
        ("betmgm",     probe_betmgm),
        ("caesars",    probe_caesars),
        ("bovada",     probe_bovada),
    ]
    all_statuses: Dict[str, Dict[str, int]] = {}
    all_rows: Dict[str, List[Dict[str, Any]]] = {}

    for src_name, fn in sources:
        tried.append(src_name)
        print(f"[probe] {src_name}: starting", flush=True)
        try:
            statuses, rows = fn(errors)
        except Exception as e:                                  # noqa: BLE001
            errors.append(f"{src_name} crashed: {e}\n{traceback.format_exc()}")
            statuses, rows = {}, []
        all_statuses[src_name] = statuses
        all_rows[src_name] = rows
        rows_per_source[src_name] = len(rows)
        print(f"[probe] {src_name}: statuses={statuses}  rows={len(rows)}", flush=True)

    # Pick best source. SHIP gate is >=500 rows AND schema match. We still
    # write the canonical CSV if a source >0 rows so downstream (compute_clv,
    # clv_tracker) can consume even an off-season partial; status reflects
    # the spec gate honestly.
    best = max(rows_per_source.items(), key=lambda kv: kv[1]) if rows_per_source else (None, 0)
    if best[1] and best[0]:
        rows = all_rows[best[0]]
        schema_match_for_clv = all(_schema_match(r) for r in rows[:50])
        book_short = {"draftkings": "dk", "fanduel": "fd",
                      "betmgm": "mgm", "caesars": "czr",
                      "bovada": "bov"}[best[0]]
        if schema_match_for_clv:
            ship_path = _write_canonical_csv(rows, book_short)
            if best[1] >= 500:
                ship_status = "SHIP"
            else:
                ship_status = f"PARTIAL_below_500_rows={best[1]}"
        else:
            ship_status = "REJECT_schema_mismatch"
    else:
        ship_status = "REJECT_insufficient_rows"

    summary = {
        "tried_sources":        tried,
        "http_statuses":        all_statuses,
        "rows_per_source":      rows_per_source,
        "schema_match_for_clv": schema_match_for_clv,
        "ship_status":          ship_status,
        "ship_path":            ship_path,
        "errors":               errors[:50],
        "wall_seconds":         round(time.time() - started, 2),
        "captured_at":          _now_iso(),
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
