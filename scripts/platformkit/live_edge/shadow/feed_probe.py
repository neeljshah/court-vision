"""scripts.platformkit.live_edge.shadow.feed_probe -- D1-PREREQS feed probe.

STEP 0 (premise check, 2026-07-14): bus_ingest.py tees odds:*/injury:*/gumbo:*/
fotmob:* only -- confirmed no player-prop/minutes-market source is wired.
Repo-wide sweep of scripts/platformkit/odds_provider/prop_*.py (the existing
keyless player-prop adapters) found: NO sport-agnostic NBA support anywhere
(prop_draftkings_live._LEAGUE = {"mlb": ...} only; prop_draftkings_v2._SPORT_IDS
= {"mlb": ...} only; prop_fanduel.py has zero "nba"/"minutes" references). This
probe attempts ONE real keyless fetch per NBA-shaped candidate through the
EXISTING shared transport (odds_provider.transport.resilient_get_json --
import only, mirrors news/probe.py's pattern) to check what, if anything, is
reachable for a future minutes/player-prop tee. Never hammers: one request per
candidate, small jittered sleep between, no daemon left running.

Writes an honest per-source REACHABLE/BLOCKED/DEAD verdict to
data/omni/live_edge/shadow/PROBE.md.

Run: python -m scripts.platformkit.live_edge.shadow.feed_probe

INVARIANTS: stdlib + shared transport only; ASCII stdout; <=300 LOC; no $/edge
claims; does not arm any daemon.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.platformkit.odds_provider.transport import resilient_get_json

_OUT_PATH = Path("data/omni/live_edge/shadow/PROBE.md")
_TIMEOUT = 15.0

_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
_FD_HOST = "https://sbapi.nj.sportsbook.fanduel.com/api"
_FD_AK = "FhMFpcPWXMeyZxOx"  # same static public app key prop_fanduel.py uses (keyless, not a secret)
_DK_BASE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1"

# Guessed NBA player-prop/minutes series tickers (no confirmed KXNBA*PROP/MIN
# series is documented anywhere in-repo -- kalshi_series_spec.py only lists
# team-level KXNBAGAME/KXNBASPREAD). A candidate 404/empty result is an
# HONEST negative, not a bug -- we do not have a confirmed ticker to target.
_KALSHI_CANDIDATES = ["KXNBAPTS", "KXNBAMIN", "KXNBAPLAYERPROP"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe_kalshi_series(ticker: str) -> Dict[str, Any]:
    url = f"{_KALSHI_BASE}/markets?" + urllib.parse.urlencode(
        {"series_ticker": ticker, "status": "open", "limit": 3})
    try:
        payload = resilient_get_json(url, timeout=_TIMEOUT)
        markets = payload.get("markets", []) if isinstance(payload, dict) else []
        if markets:
            return {"verdict": "REACHABLE", "status": 200, "n_markets": len(markets)}
        # Kalshi returns 200 + empty list for a series with no open markets
        # AND (per kalshi_series_spec.py's own probes) for a series that does
        # not exist at all -- distinguishing needs a /series/<ticker> lookup,
        # out of scope for a one-shot probe. Honest: reachable transport, zero
        # markets found under this guessed ticker.
        return {"verdict": "BLOCKED", "status": 200, "n_markets": 0,
                "error": "0 open markets under this ticker (may not exist -- unconfirmed)"}
    except urllib.error.HTTPError as exc:
        verdict = "BLOCKED" if exc.code in (401, 403, 404, 406, 429, 451, 503) else "DEAD"
        return {"verdict": verdict, "status": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- honest degrade, never sinks the probe loop
        return {"verdict": "DEAD", "status": None, "error": f"{type(exc).__name__}: {exc}"}


def _probe_fanduel_nba_page() -> Dict[str, Any]:
    url = (f"{_FD_HOST}/content-managed-page?page=CUSTOM&customPageId=nba"
           f"&_ak={_FD_AK}&timezone=America%2FNew_York")
    try:
        payload = resilient_get_json(url, timeout=_TIMEOUT)
        events = (payload.get("attachments", {}).get("events", {})
                  if isinstance(payload, dict) else {})
        if events:
            return {"verdict": "REACHABLE", "status": 200, "n_events": len(events)}
        return {"verdict": "BLOCKED", "status": 200, "n_events": 0,
                "error": "page resolved but 0 NBA events (customPageId guess may be wrong)"}
    except urllib.error.HTTPError as exc:
        verdict = "BLOCKED" if exc.code in (401, 403, 404, 406, 429, 451, 503) else "DEAD"
        return {"verdict": verdict, "status": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "DEAD", "status": None, "error": f"{type(exc).__name__}: {exc}"}


def _probe_dk_leagues() -> Dict[str, Any]:
    """DK's per-league_id/cat_id/sub_id catalog (prop_draftkings_v2._SPORT_IDS)
    has NO nba entry in-repo -- there is no known league_id to target directly.
    Probe the bare /leagues root for a discovery listing; an honest failure
    here means the NBA league_id is genuinely unresolved, not a code bug."""
    url = f"{_DK_BASE}/leagues"
    try:
        payload = resilient_get_json(url, timeout=_TIMEOUT)
        n = len(payload) if isinstance(payload, (list, dict)) else 0
        if n:
            return {"verdict": "REACHABLE", "status": 200, "n_items": n}
        return {"verdict": "BLOCKED", "status": 200, "n_items": 0, "error": "empty response"}
    except urllib.error.HTTPError as exc:
        verdict = "BLOCKED" if exc.code in (401, 403, 404, 406, 429, 451, 503) else "DEAD"
        return {"verdict": verdict, "status": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "DEAD", "status": None, "error": f"{type(exc).__name__}: {exc}"}


_PROBES = {
    "kalshi_KXNBAPTS": lambda: _probe_kalshi_series("KXNBAPTS"),
    "kalshi_KXNBAMIN": lambda: _probe_kalshi_series("KXNBAMIN"),
    "kalshi_KXNBAPLAYERPROP": lambda: _probe_kalshi_series("KXNBAPLAYERPROP"),
    "fanduel_nba_page": _probe_fanduel_nba_page,
    "draftkings_leagues_root": _probe_dk_leagues,
}


def run_probe(probes: Dict[str, Any] | None = None, *, sleep_fn=time.sleep) -> Dict[str, Any]:
    """Attempt one fetch per candidate (jittered pause between). Returns the
    per-source result dict; does not write to disk (caller decides)."""
    fns = probes if probes is not None else _PROBES
    results: Dict[str, Any] = {}
    names = list(fns.keys())
    for i, name in enumerate(names):
        t0 = time.time()
        result = fns[name]()
        result["latency_sec"] = round(time.time() - t0, 3)
        results[name] = result
        if i < len(names) - 1:
            sleep_fn(random.uniform(0.6, 1.4))  # ponytail: polite jitter, not a governor
    return results


def write_probe_md(results: Dict[str, Any], out_path: Path = _OUT_PATH) -> Path:
    lines = [
        "# D1-PREREQS player-prop/minutes-market source-reachability PROBE",
        f"captured_at: {_now_iso()}",
        "",
        "No confirmed NBA player-prop/minutes feed exists in-repo today (see",
        "module docstring: DK/FanDuel adapters cover mlb/soccer only, and the",
        "3 Kalshi series tickers below are UNCONFIRMED guesses -- kalshi_series_spec.py",
        "documents no player-prop series for any sport). This probe's REACHABLE/",
        "BLOCKED/DEAD verdicts are about transport + ticker/page existence, not",
        "proof a usable minutes feed exists.",
        "",
        "| source | verdict | status | evidence |",
        "|---|---|---|---|",
    ]
    for name, r in results.items():
        evidence = r.get("error") or (
            f"n_markets={r['n_markets']}" if "n_markets" in r else
            f"n_events={r['n_events']}" if "n_events" in r else
            f"n_items={r['n_items']}" if "n_items" in r else "")
        lines.append(f"| {name} | {r['verdict']} | {r.get('status')} | {evidence} |")
    lines.append("")
    lines.append("Raw results:")
    lines.append("```json")
    lines.append(json.dumps(results, indent=2, ensure_ascii=True, sort_keys=True))
    lines.append("```")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return out_path


if __name__ == "__main__":
    res = run_probe()
    path = write_probe_md(res)
    print(json.dumps({name: r["verdict"] for name, r in res.items()}))
    print(f"wrote {path}")


__all__ = ["run_probe", "write_probe_md"]
