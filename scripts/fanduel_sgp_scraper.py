"""fanduel_sgp_scraper.py — FanDuel SGP (BetBuilder) price endpoint scraper.

STATUS: SCAFFOLD — endpoint path NOT YET CONFIRMED.
------------------------------------------------------------------------
8 endpoint patterns probed on 2026-06-04 (≤8 GET/POST requests total).
ALL returned 404 from sbapi.nj.sportsbook.fanduel.com:

  Probed paths (all 404):
    GET  /api/sgp-prices               (with selectionIds=, eventId=)
    GET  /api/betbuilder/price         (same params)
    GET  /api/betbuilder/prices        (same params)
    GET  /api/bet-builder/price        (same params)
    POST /api/bet-builder/price        (JSON body)
    POST /api/sgp-prices               (JSON body)
    GET  /api/betbuilder/calculate     (same params)
    POST /api/betbuilder/calculate     (JSON body)

  SSL / DNS failures:
    api2.fanduel.com                   → TLS SSLV3_ALERT_HANDSHAKE_FAILURE (geo-blocked from dev IP)
    sbapi.us.sportsbook.fanduel.com    → DNS not found

CONCLUSION: The FD SGP pricing endpoint is NOT co-located with the single-prop
  NJ REST API (sbapi.nj.sportsbook.fanduel.com/api/content-managed-page).
  It is served from a DIFFERENT host, likely:
    - api2.fanduel.com  (geo-blocked from non-US IP; confirmed TLS block)
    - The BetBuilder widget in the FD app fetches from a different internal domain

HOW TO CONFIRM THE ENDPOINT (owner recipe):
-------------------------------------------
1. Open sportsbook.fanduel.com in Chrome DevTools (Network tab).
2. Navigate to any NBA game page (e.g. NYK vs SAC on 2026-06-06).
3. Click "Same Game Parlay" or "+ BetBuilder" on that game.
4. Add 2 player prop legs (e.g. Brunson AST 5.5+ and Hart FG3M 1.5+).
5. Watch the Network tab for a request that returns a correlated combined price.
   Filter by XHR/Fetch. Look for requests to:
     - Any path containing "sgp", "betbuilder", "bet-builder", "parlay-price",
       "combo-price", or "multi-selection"
     - Any POST request with a body containing your selectionIds
6. Copy the URL + method + request headers (especially Cookie, Authorization)
   and the response JSON structure.
7. Wire those into this file (the scaffold is ready — just fill in URL + auth).

SELECTION IDs FROM 2026-06-04_fd.csv (NYK vs SAC, event_id=35669206):
----------------------------------------------------------------------
Key pair 1 (creator_AST + catch_shoot_FG3M):
  Brunson AST 5.5 over:  734.171511561:21359550  (odds -184)
  Hart FG3M 1.5 over:    734.171511556:16421595  (odds -128)

Key pair 2 (secondary_PTS + secondary_PTS):
  Bridges PTS 9.5 over:  734.171511647:18970813  (odds -225)
  OG Anunoby PTS 9.5:    734.171511647:16012686  (odds -650)

Key pair 3 (creator_AST + catch_shoot_FG3M, SAC):
  Fox AST 3.5 over:      734.171511639:13323008  (odds -670)
  Champagnie FG3M 1.5:   734.171511556:41472494  (odds -330)

Once confirmed, run:
  python scripts/fanduel_sgp_scraper.py --date 2026-06-06
  python scripts/grade_sgp_edge.py --date 2026-06-06

OUTPUT FORMAT (data/lines/<date>_fd_sgp.csv):
  player_a, stat_a, line_a, player_b, stat_b, line_b,
  combined_odds_american, event_id, captured_at, game_date
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as cf_req

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

LINES_DIR = PROJECT_DIR / "data" / "lines"
LINES_DIR.mkdir(parents=True, exist_ok=True)

# ── FD headers (same as probe_R15_curl_cffi_fanduel.py) ──────────────────────
FD_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.fanduel.com/",
    "Origin": "https://sportsbook.fanduel.com",
    "X-Px-Authorization": "3",
}

# ── FILL IN after browser DevTools inspection ─────────────────────────────────
# Set FD_SGP_ENDPOINT_URL to the confirmed path, e.g.:
#   "https://api2.fanduel.com/api/sgp-prices"
FD_SGP_ENDPOINT_URL: Optional[str] = os.environ.get("FD_SGP_URL", None)

# Auth header or cookie if required (set via env var to avoid hardcoding):
#   FD_SGP_COOKIE="__utmz=...; _px3=..."
FD_SGP_COOKIE: Optional[str] = os.environ.get("FD_SGP_COOKIE", None)

SGP_CSV_FIELDS = [
    "captured_at", "game_date", "event_id",
    "player_a", "stat_a", "line_a",
    "player_b", "stat_b", "line_b",
    "combined_odds_american",
    "selection_id_a", "selection_id_b",
]


# ── Known candidate pairs (update as lines are captured) ─────────────────────

def build_candidate_pairs(lines_date: str) -> List[Dict[str, Any]]:
    """Build candidate pairs from today's FD lines file.

    Returns list of pair dicts with:
      player_a, stat_a, line_a, selection_id_a,
      player_b, stat_b, line_b, selection_id_b,
      event_id, pair_type
    """
    lines_path = LINES_DIR / f"{lines_date}_fd.csv"
    if not lines_path.exists():
        print(f"[fd_sgp] No lines file for {lines_date}: {lines_path}")
        return []

    import pandas as pd
    df = pd.read_csv(lines_path)
    df = df.sort_values('captured_at').drop_duplicates(
        subset=['player_name', 'stat', 'line'], keep='first'
    )
    df = df[df['book_selection_id_over'].notna()]

    event_id = df['game_id'].iloc[0] if not df.empty else None

    pairs: List[Dict[str, Any]] = []

    def get_row(player: str, stat: str, line: float) -> Optional[Any]:
        mask = (df['player_name'] == player) & (df['stat'] == stat) & (df['line'] == line)
        r = df[mask]
        return r.iloc[0] if not r.empty else None

    # GENUINE BLIND SPOT pairs (see docs/_audits/SGP_EDGE.md PART A)
    # Pair 1: creator_AST + catch_shoot_FG3M (recal_rho=+0.113 vs naive 0.0)
    targets = [
        # (player_a, stat_a, line_a, player_b, stat_b, line_b, pair_type)
        ("Jalen Brunson", "ast", 5.5, "Josh Hart", "fg3m", 1.5, "creator_AST+catch_shoot_FG3M"),
        ("Jalen Brunson", "ast", 3.5, "Josh Hart", "fg3m", 1.5, "creator_AST+catch_shoot_FG3M"),
        ("De'Aaron Fox", "ast", 3.5, "Julian Champagnie", "fg3m", 1.5, "creator_AST+catch_shoot_FG3M"),
        ("De'Aaron Fox", "ast", 5.5, "Julian Champagnie", "fg3m", 1.5, "creator_AST+catch_shoot_FG3M"),
        # Pair 2: sec_PTS + sec_PTS (recal_rho=-0.007 vs naive -0.15 book assumption)
        ("Mikal Bridges", "pts", 9.5, "OG Anunoby", "pts", 9.5, "sec_PTS+sec_PTS"),
        # Pair 3: creator_AST + roll_man PTS (recal 0.082 vs naive 0.20 -> book overprices)
        ("Stephon Castle", "ast", 3.5, "Victor Wembanyama", "pts", 19.5, "creator_AST+roll_PTS"),
    ]

    for pa_name, sa, la, pb_name, sb, lb, ptype in targets:
        ra = get_row(pa_name, sa, la)
        rb = get_row(pb_name, sb, lb)
        if ra is not None and rb is not None:
            pairs.append({
                'player_a'       : pa_name,
                'stat_a'         : sa,
                'line_a'         : la,
                'selection_id_a' : ra['book_selection_id_over'],
                'player_b'       : pb_name,
                'stat_b'         : sb,
                'line_b'         : lb,
                'selection_id_b' : rb['book_selection_id_over'],
                'event_id'       : event_id,
                'pair_type'      : ptype,
            })

    return pairs


# ── Core SGP price fetcher ────────────────────────────────────────────────────

def fetch_sgp_price(
    selection_id_a: str,
    selection_id_b: str,
    event_id: Any,
    endpoint_url: str,
    extra_headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
) -> Optional[Dict[str, Any]]:
    """Fetch combined SGP price for two legs from the FD BetBuilder endpoint.

    Args:
        selection_id_a: FD selectionId for leg A (format "734.MARKETID:PLAYERID")
        selection_id_b: FD selectionId for leg B
        event_id:       FD eventId (integer or string)
        endpoint_url:   Confirmed FD SGP pricing endpoint URL
        extra_headers:  Additional headers (e.g. Cookie, Authorization)
        method:         "GET" or "POST"

    Returns:
        Parsed JSON response dict, or None on failure.
    """
    headers = dict(FD_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if FD_SGP_COOKIE:
        headers["Cookie"] = FD_SGP_COOKIE

    params = {
        "selectionIds": [selection_id_a, selection_id_b],
        "eventId": str(event_id),
    }

    try:
        if method.upper() == "POST":
            r = cf_req.post(
                endpoint_url,
                headers={**headers, "Content-Type": "application/json"},
                json=params,
                impersonate="chrome120",
                timeout=15,
            )
        else:
            r = cf_req.get(
                endpoint_url,
                headers=headers,
                params=params,
                impersonate="chrome120",
                timeout=15,
            )

        if r.status_code != 200:
            print(f"[fd_sgp] {r.status_code} from {endpoint_url}: {r.text[:200]}")
            return None

        return r.json()

    except Exception as exc:
        print(f"[fd_sgp] fetch error: {type(exc).__name__}: {exc}")
        return None


def parse_sgp_response(resp: Dict[str, Any]) -> Optional[float]:
    """Parse combined SGP price (American odds) from FD BetBuilder response.

    The exact JSON structure depends on the endpoint. Common patterns observed
    in FD BetBuilder network traces:

    Pattern A (combinedPrice field):
      {"combinedPrice": -140, "status": "AVAILABLE"}

    Pattern B (price/odds nested):
      {"price": {"americanOdds": -140}, "status": "OK"}

    Pattern C (selections array with combined):
      {"combined": {"americanOdds": -140}, "legs": [...]}

    Returns American odds (float) or None if unparseable.
    """
    # Pattern A
    if 'combinedPrice' in resp:
        return float(resp['combinedPrice'])
    # Pattern B
    if 'price' in resp and isinstance(resp['price'], dict):
        if 'americanOdds' in resp['price']:
            return float(resp['price']['americanOdds'])
    # Pattern C
    if 'combined' in resp and isinstance(resp['combined'], dict):
        if 'americanOdds' in resp['combined']:
            return float(resp['combined']['americanOdds'])
    # Fallback: look for any key with "Odds" in name at top level
    for key, val in resp.items():
        if 'odds' in key.lower() and isinstance(val, (int, float)):
            return float(val)
    print(f"[fd_sgp] could not parse price from response: {list(resp.keys())}")
    return None


def write_sgp_csv(rows: List[Dict[str, Any]], date_str: str) -> str:
    """Write SGP price rows to data/lines/<date>_fd_sgp.csv."""
    path = LINES_DIR / f"{date_str}_fd_sgp.csv"
    new_file = not path.exists()
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=SGP_CSV_FIELDS, extrasaction='ignore')
        if new_file:
            w.writeheader()
        w.writerows(rows)
    return str(path)


def scrape_sgp_prices(date_str: str) -> List[Dict[str, Any]]:
    """Main entry point: fetch SGP prices for all candidate pairs on date_str.

    Returns list of captured row dicts.
    """
    if not FD_SGP_ENDPOINT_URL:
        print("[fd_sgp] FD_SGP_URL not set.")
        print("  Set env var FD_SGP_URL to the confirmed FD BetBuilder endpoint URL.")
        print("  See the HOW TO CONFIRM recipe at the top of this file.")
        print("  Endpoint path is NOT auto-discovered — requires browser DevTools inspection.")
        return []

    candidates = build_candidate_pairs(date_str)
    if not candidates:
        print(f"[fd_sgp] No candidate pairs for {date_str}")
        return []

    print(f"[fd_sgp] Fetching SGP prices for {len(candidates)} candidate pairs...")
    captured = []
    captured_at = datetime.utcnow().replace(microsecond=0).isoformat()

    for pair in candidates:
        resp = fetch_sgp_price(
            pair['selection_id_a'],
            pair['selection_id_b'],
            pair['event_id'],
            FD_SGP_ENDPOINT_URL,
        )
        if resp is None:
            print(f"  FAILED: {pair['player_a']} {pair['stat_a']} + "
                  f"{pair['player_b']} {pair['stat_b']}")
            time.sleep(1.5)
            continue

        combined_odds = parse_sgp_response(resp)
        if combined_odds is None:
            print(f"  PARSE FAILED: {pair['player_a']} + {pair['player_b']}")
            time.sleep(1.5)
            continue

        row = {
            'captured_at'            : captured_at,
            'game_date'              : date_str,
            'event_id'               : pair['event_id'],
            'player_a'               : pair['player_a'],
            'stat_a'                 : pair['stat_a'],
            'line_a'                 : pair['line_a'],
            'player_b'               : pair['player_b'],
            'stat_b'                 : pair['stat_b'],
            'line_b'                 : pair['line_b'],
            'combined_odds_american' : combined_odds,
            'selection_id_a'         : pair['selection_id_a'],
            'selection_id_b'         : pair['selection_id_b'],
        }
        captured.append(row)
        print(f"  OK: {pair['player_a']} {pair['stat_a']} + {pair['player_b']} {pair['stat_b']}"
              f" → combined {combined_odds:+.0f}")
        time.sleep(1.5)  # polite spacing

    if captured:
        csv_path = write_sgp_csv(captured, date_str)
        print(f"[fd_sgp] Wrote {len(captured)} rows to {csv_path}")

    return captured


# ── Probe mode (DevTools confirmation helper) ─────────────────────────────────

def probe_endpoint(url: str, method: str = "GET") -> None:
    """Probe a single endpoint URL with the candidate pair and print the response.

    Used to confirm a new endpoint path discovered via browser DevTools.
    Safe to call manually from REPL.
    """
    SEL_A = "734.171511561:21359550"  # Brunson AST 5.5 over, 2026-06-04
    SEL_B = "734.171511556:16421595"  # Hart FG3M 1.5 over, 2026-06-04
    EVENT_ID = 35669206

    print(f"Probing {method} {url}")
    resp = fetch_sgp_price(SEL_A, SEL_B, EVENT_ID, url, method=method)
    if resp is not None:
        print("SUCCESS — response:")
        print(json.dumps(resp, indent=2)[:1000])
        price = parse_sgp_response(resp)
        print(f"Parsed combined price: {price}")
    else:
        print("FAILED — see error above.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="FanDuel SGP price scraper (scaffold)")
    ap.add_argument('--date', default=_date.today().isoformat(),
                    help='Lines date (YYYY-MM-DD, default: today)')
    ap.add_argument('--probe', metavar='URL',
                    help='Probe a single endpoint URL and print the response')
    ap.add_argument('--method', default='GET', choices=['GET', 'POST'],
                    help='HTTP method for probe (default: GET)')
    args = ap.parse_args()

    if args.probe:
        probe_endpoint(args.probe, method=args.method)
        return 0

    rows = scrape_sgp_prices(args.date)
    return 0 if rows else 1


if __name__ == '__main__':
    sys.exit(main())
