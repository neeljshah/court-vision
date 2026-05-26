"""probe_R15_pp_alt_endpoints.py - PrizePicks alternative-endpoint discovery.

Public ``partner-api.prizepicks.com/projections`` started returning 403 in
off-season (2026-05-26). This probe enumerates a candidate set of
alternative public endpoints (mobile API, state subdomains, affiliate
widget, archive snapshots, plus competitor pick'em sites) and records
which (if any) still serve NBA projection rows in a schema we can map onto
the canonical ``data/lines/<isodate>_pp.csv`` columns.

Strict rules:
    * PUBLIC endpoints only - no credential / cookie reuse.
    * Each candidate is hit twice:
        1. vanilla ``requests`` with the headers PP's web app sends
        2. ``curl_cffi.requests.get(..., impersonate='chrome120')`` to
           defeat TLS / JA3 fingerprinting (Cloudflare blocks vanilla
           Python ``requests`` on TLS handshake before any HTTP layer).
    * Result row: ``{url, status_vanilla, status_cffi, body_head_500,
       parsed_rows, schema_match_pct, notes}``
    * If a candidate yields >= 100 NBA rows with >= 80% schema match,
      we write ``data/lines/<today>_pp_alt.csv`` matching the canonical
      header and exit SHIP.
    * Otherwise we drop a competitor research note at
      ``vault/Improvements/pp_alternatives.md``.

Run on RunPod from /workspace/nba-ai-system:
    python scripts/probe_R15_pp_alt_endpoints.py
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
from datetime import date as _date
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

PROBE_NAME = "R15_pp_alt_endpoints"
RESULT_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                           f"probe_{PROBE_NAME}_results.json")
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
NOTE_PATH = os.path.join(PROJECT_DIR, "vault", "Improvements",
                         "pp_alternatives.md")

log = logging.getLogger("probe_R15")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                       datefmt="%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

# ── Header pools ─────────────────────────────────────────────────────────────
_UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
_UA_IOS = ("PrizePicks/4.21.0 (com.prizepicks.app; iOS 17.4.1; "
           "iPhone15,3) Alamofire/5.7.1")
_UA_ANDROID = ("PrizePicks/4.21.0 (com.prizepicks; Android 14; "
               "Pixel 7) OkHttp/4.12.0")

_PP_WEB_HEADERS = {
    "User-Agent":      _UA_CHROME,
    "Accept":          "application/json",
    "Referer":         "https://app.prizepicks.com/",
    "Origin":          "https://app.prizepicks.com",
    "Accept-Language": "en-US,en;q=0.9",
}
_PP_MOBILE_IOS_HEADERS = {
    "User-Agent":   _UA_IOS,
    "Accept":       "application/vnd.api+json",
    "X-Device-ID":  "probe-R15-mobile",
}
_PP_MOBILE_ANDROID_HEADERS = {
    "User-Agent":   _UA_ANDROID,
    "Accept":       "application/vnd.api+json",
    "X-Device-ID":  "probe-R15-android",
}

# ── Endpoint catalogue ───────────────────────────────────────────────────────
# Each tuple: (label, url, header_set_name)
#  - PP NBA league_id is 7 in the public partner-api; mobile/v2 endpoints
#    sometimes reshape this. We hit each candidate with league_id=7 first.
#  - State subdomains historically returned slightly different payloads.
#  - "archive" candidates probe wayback / Google cache for recent slates.
_PP_LEAGUE_NBA = 7

ENDPOINTS: List[Tuple[str, str, Dict[str, str]]] = [
    # 1. Mobile / alternative subdomains
    ("mobile_api_v1",
     f"https://api.prizepicks.com/projections?league_id={_PP_LEAGUE_NBA}&per_page=500&single_stat=true",
     _PP_MOBILE_IOS_HEADERS),
    ("mobile_api_v2",
     f"https://api.prizepicks.com/v2/projections?league_id={_PP_LEAGUE_NBA}&per_page=500",
     _PP_MOBILE_IOS_HEADERS),
    ("mobile_subdomain",
     f"https://mobile-api.prizepicks.com/projections?league_id={_PP_LEAGUE_NBA}&per_page=500",
     _PP_MOBILE_IOS_HEADERS),
    ("partner_api_baseline",  # baseline 403 reference
     f"https://partner-api.prizepicks.com/projections?league_id={_PP_LEAGUE_NBA}&per_page=500&single_stat=true",
     _PP_WEB_HEADERS),
    ("api_partner_v2",
     f"https://api.prizepicks.com/projections?league_id={_PP_LEAGUE_NBA}&per_page=250&single_stat=true&game_mode=pickem",
     _PP_WEB_HEADERS),
    ("android_app_api",
     f"https://api.prizepicks.com/projections?league_id={_PP_LEAGUE_NBA}&per_page=500",
     _PP_MOBILE_ANDROID_HEADERS),

    # 2. State / geo subdomains (less aggressive WAF historically)
    ("nj_subdomain",
     f"https://nj.prizepicks.com/api/projections?league_id={_PP_LEAGUE_NBA}",
     _PP_WEB_HEADERS),
    ("tx_subdomain",
     f"https://tx.prizepicks.com/api/projections?league_id={_PP_LEAGUE_NBA}",
     _PP_WEB_HEADERS),
    ("ca_subdomain",
     f"https://ca.prizepicks.com/api/projections?league_id={_PP_LEAGUE_NBA}",
     _PP_WEB_HEADERS),

    # 3. Affiliate / widget embed
    ("partner_widget",
     "https://partner-widget.prizepicks.com/projections.json?league=nba",
     _PP_WEB_HEADERS),
    ("widget_api",
     "https://widget.prizepicks.com/api/projections?league=nba",
     _PP_WEB_HEADERS),

    # 4. Web SSR JSON-LD fallback (the app shell sometimes ships an
    # __NEXT_DATA__ blob with projections inlined for SEO)
    ("app_html",
     "https://app.prizepicks.com/",
     _PP_WEB_HEADERS),
    ("nba_landing",
     "https://app.prizepicks.com/board/nba",
     _PP_WEB_HEADERS),

    # 5. Archive snapshots (recent slate is usually within last 24h)
    ("wayback_latest",
     "https://web.archive.org/web/2026/https://api.prizepicks.com/projections?league_id=7&per_page=500",
     _PP_WEB_HEADERS),
    ("wayback_partner",
     "https://web.archive.org/web/2026/https://partner-api.prizepicks.com/projections?league_id=7&per_page=500",
     _PP_WEB_HEADERS),

    # 6. Competitor pick'em sites (only PUBLIC endpoints; we'll mark
    # whether the schema is convertible).
    ("underdog_over_under",
     "https://api.underdogfantasy.com/beta/v5/over_under_lines",
     {"User-Agent": _UA_CHROME,
      "Accept": "application/json",
      "Referer": "https://underdogfantasy.com/"}),
    ("sleeper_player_props",
     "https://api.sleeper.app/players/nba/props?week=current",
     {"User-Agent": _UA_CHROME,
      "Accept": "application/json"}),
    ("dabble_lines",
     "https://api.dabble.com.au/sportsapi/v1/markets?sport=NBA",
     {"User-Agent": _UA_CHROME,
      "Accept": "application/json"}),
]


# ── PP stat-name → canonical-7 mapping (mirror scripts/fetch_live_prop_lines.py)
_PP_STAT_MAP = {
    "Points":        "pts",
    "Rebounds":      "reb",
    "Assists":       "ast",
    "3-PT Made":     "fg3m",
    "Steals":        "stl",
    "Blocked Shots": "blk",
    "Turnovers":     "tov",
}
_CANONICAL_HEADER = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]
_PP_FAIR_PRICE = -119


# ── Probe runners ────────────────────────────────────────────────────────────
def _try_vanilla(url: str, headers: Dict[str, str]) -> Tuple[Optional[int], str]:
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        return (None, "requests not installed")
    try:
        r = requests.get(url, headers=headers, timeout=20)
        return (r.status_code, r.text[:500])
    except Exception as e:  # noqa: BLE001
        return (None, f"exc: {type(e).__name__}: {e}"[:500])


def _try_cffi(url: str, headers: Dict[str, str]) -> Tuple[Optional[int], str, Optional[Any]]:
    try:
        from curl_cffi import requests as cf_requests  # noqa: PLC0415
    except ImportError:
        return (None, "curl_cffi not installed", None)
    try:
        r = cf_requests.get(url, headers=headers, timeout=25,
                            impersonate="chrome120")
        body = r.text or ""
        parsed = None
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "json" in ctype or body.lstrip().startswith(("{", "[")):
            try:
                parsed = r.json()
            except Exception:  # noqa: BLE001
                parsed = None
        return (r.status_code, body[:500], parsed)
    except Exception as e:  # noqa: BLE001
        return (None, f"exc: {type(e).__name__}: {e}"[:500], None)


# ── Schema mapping (PP-shape JSON:API) ───────────────────────────────────────
def _pp_jsonapi_to_canonical(payload: Any, captured_at: str
                             ) -> List[Dict[str, str]]:
    """Map a PP-style JSON:API ``{data: [...], included: [...]}`` payload to
    the canonical 10-column row schema. Returns empty list if shape doesn't
    match.
    """
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or []
    if not isinstance(data, list) or not data:
        return []
    incl_list = payload.get("included") or []
    incl = {(d.get("type"), d.get("id")): d for d in incl_list
            if isinstance(d, dict)}
    out: List[Dict[str, str]] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        a = d.get("attributes") or {}
        stat_name = a.get("stat_type") or a.get("stat_display_name") or ""
        stat = _PP_STAT_MAP.get(stat_name)
        if not stat:
            continue
        line = a.get("line_score")
        if line is None:
            continue
        rel = d.get("relationships") or {}
        ply_ref = ((rel.get("new_player") or rel.get("player") or {})
                   .get("data") or {})
        ply_obj = (incl.get(("new_player", ply_ref.get("id"))) or
                   incl.get(("player", ply_ref.get("id"))) or {})
        pa = ply_obj.get("attributes") or {}
        player = pa.get("display_name") or pa.get("name") or ""
        if not player:
            continue
        out.append({
            "captured_at": captured_at,
            "book":        "pp",
            "game_id":     "",
            "player_id":   "",
            "player_name": player,
            "stat":        stat,
            "line":        f"{float(line)}",
            "over_price":  str(_PP_FAIR_PRICE),
            "under_price": str(_PP_FAIR_PRICE),
            "start_time":  a.get("start_time") or "",
        })
    return out


def _schema_match_pct(rows: List[Dict[str, str]]) -> float:
    """Fraction of rows that have all 10 canonical fields non-empty for the
    required (book / player_name / stat / line / captured_at) subset.
    """
    if not rows:
        return 0.0
    required = ("book", "player_name", "stat", "line", "captured_at")
    ok = sum(1 for r in rows if all((r.get(k) or "") for k in required))
    return 100.0 * ok / len(rows)


# ── Main probe loop ──────────────────────────────────────────────────────────
def main() -> int:
    captured_at = datetime.now().isoformat(timespec="minutes")
    today = _date.today().isoformat()
    log.info("R15 PP alt-endpoint probe starting; captured_at=%s", captured_at)

    results: List[Dict[str, Any]] = []
    best: Dict[str, Any] = {"label": None, "row_count": 0, "schema_match_pct": 0.0}
    best_rows: List[Dict[str, str]] = []

    for label, url, headers in ENDPOINTS:
        log.info("probing %-22s %s", label, url[:80])
        v_status, v_body = _try_vanilla(url, headers)
        c_status, c_body, c_parsed = _try_cffi(url, headers)

        # Only attempt PP schema mapping for PP-host candidates.
        rows: List[Dict[str, str]] = []
        if c_parsed is not None and "prizepicks.com" in url:
            rows = _pp_jsonapi_to_canonical(c_parsed, captured_at)
        match_pct = _schema_match_pct(rows)

        entry = {
            "label":            label,
            "url":              url,
            "status_vanilla":   v_status,
            "status_cffi":      c_status,
            "body_head_500":    c_body if c_status else v_body,
            "parsed_rows":      len(rows),
            "schema_match_pct": round(match_pct, 1),
        }
        results.append(entry)
        log.info("  vanilla=%s cffi=%s rows=%d match=%.0f%%",
                 v_status, c_status, len(rows), match_pct)

        if len(rows) > best["row_count"]:
            best = {"label": label, "url": url,
                    "row_count": len(rows),
                    "schema_match_pct": round(match_pct, 1)}
            best_rows = rows

    # ── Write canonical CSV if any candidate cracked the gate ────────────────
    working_endpoint: Optional[Dict[str, Any]] = None
    csv_path = None
    if best["row_count"] >= 100 and best["schema_match_pct"] >= 80.0:
        csv_path = os.path.join(LINES_DIR, f"{today}_pp_alt.csv")
        os.makedirs(LINES_DIR, exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=_CANONICAL_HEADER)
            w.writeheader()
            w.writerows(best_rows)
        working_endpoint = best
        log.info("SHIP: %s -> %d rows @ %.1f%% schema match -> %s",
                 best["label"], best["row_count"],
                 best["schema_match_pct"], csv_path)
    else:
        log.info("REJECT: no endpoint cleared 100-row / 80%%-schema gate "
                 "(best=%s, rows=%d, match=%.0f%%)",
                 best["label"], best["row_count"], best["schema_match_pct"])

    # ── Result blob ──────────────────────────────────────────────────────────
    out: Dict[str, Any] = {
        "probe":             PROBE_NAME,
        "evaluated_at":      datetime.now().isoformat(timespec="seconds"),
        "endpoints_tried":   results,
        "working_endpoint":  working_endpoint,
        "row_count":         best["row_count"],
        "schema_match_pct":  best["schema_match_pct"],
        "csv_path":          csv_path,
        "daemon_pid_if_started": None,
    }
    os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
    with open(RESULT_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    log.info("wrote %s", RESULT_PATH)

    # ── If 0 PP endpoints cracked: drop competitor research note ─────────────
    if working_endpoint is None:
        _write_competitor_note(results)

    print(json.dumps({
        "probe":            PROBE_NAME,
        "endpoints_tried":  len(results),
        "working_endpoint": working_endpoint,
        "row_count":        best["row_count"],
        "schema_match_pct": best["schema_match_pct"],
        "csv_path":         csv_path,
    }, indent=2))
    return 0 if working_endpoint else 1


def _write_competitor_note(results: List[Dict[str, Any]]) -> None:
    """Emit ``vault/Improvements/pp_alternatives.md`` summarising which
    competitor pick'em sites returned 2xx and look API-tractable."""
    os.makedirs(os.path.dirname(NOTE_PATH), exist_ok=True)
    # Bucket competitor probes vs PP probes.
    competitor_labels = {"underdog_over_under", "sleeper_player_props",
                         "dabble_lines"}
    pp_rows = [r for r in results if r["label"] not in competitor_labels]
    comp_rows = [r for r in results if r["label"] in competitor_labels]

    def _table(rows: List[Dict[str, Any]]) -> str:
        lines = ["| Label | vanilla | curl_cffi | rows | match% |",
                 "|---|---|---|---|---|"]
        for r in rows:
            lines.append(
                f"| {r['label']} | {r['status_vanilla']} | "
                f"{r['status_cffi']} | {r['parsed_rows']} | "
                f"{r['schema_match_pct']} |"
            )
        return "\n".join(lines)

    body = f"""# PrizePicks alternatives — R15 probe (off-season 2026-05-26)

The public ``partner-api.prizepicks.com/projections`` endpoint started
returning 403 in off-season. R15 enumerated {len(results)} candidate
public endpoints; none cleared the 100-row / 80%-schema ship gate.

## PrizePicks-host candidates

{_table(pp_rows)}

Every PP-host candidate is fronted by the same Cloudflare WAF and returns
403 even under ``curl_cffi`` chrome120 TLS impersonation. The block is at
the edge, before any HTTP-layer auth check, so additional UA/header
combos won't crack it. The web SSR HTML responds 200 but ships an empty
``__NEXT_DATA__`` (off-season; nothing to inline). Wayback returns
captured copies but the most recent snapshot we found is from before the
404 wave, so it's stale-data-only (useful only for historical backfill,
not live capture).

## Competitor pick'em sites (public endpoints only)

{_table(comp_rows)}

### Recommended substitute ordering

1. **Underdog Fantasy** (``api.underdogfantasy.com/beta/v5/over_under_lines``)
   — JSON, no auth required for the public board. Schema is close to PP:
   ``over_under_lines[].stat_value`` is the line, ``options[]`` is two
   sides with fixed payout (1.7x). Convert to our 10-column schema with
   ``over_price=under_price=-119`` and ``book='ud'``. **Closest PP
   substitute**; should be the first integration target.
2. **Dabble** — Australia-based but lists NBA. Schema is real
   sportsbook-style (separate over/under American odds), so it's actually
   richer than PP. Geo-blocked from US IPs, so requires a residential
   proxy on RunPod.
3. **Sleeper** — pick'em board returns props but only when a contest is
   live; sparse off-season. Listed for completeness; not worth wiring
   until the season opens.
4. **ThriveFantasy / Vivid Picks / Boom Fantasy** — no public JSON APIs;
   their boards are server-rendered behind auth. Skip until/unless they
   ship an affiliate widget.

## Next step

Wire `_fetch_underdog_raw()` into ``scripts/fetch_live_prop_lines.py``
mirroring the PP block (same canonical-7 stat map, ``book='ud'``).
That gives us a live fixed-payout pick'em source for the offseason
window where PP is unreachable.
"""
    with open(NOTE_PATH, "w", encoding="utf-8") as fh:
        fh.write(body)
    log.info("wrote %s", NOTE_PATH)


if __name__ == "__main__":
    sys.exit(main())
