"""scripts.platformkit.live_edge.news.probe -- A2 Day-1 source-reachability probe.

Attempts ONE real fetch per candidate keyless source through the EXISTING
3-tier transport (odds_provider.transport.resilient_get_json for JSON hosts;
a plain polite urllib GET for non-JSON RSS/HTML hosts -- import only, no
shared module edited). Writes an honest per-source REACHABLE/BLOCKED/DEAD
verdict to data/omni/live_edge/news/PROBE.md. Never hammers: one request per
source, small jittered sleep between them.

Run: python -m scripts.platformkit.live_edge.news.probe
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.platformkit.odds_provider.transport import resilient_get_json

_OUT_PATH = Path("data/omni/live_edge/news/PROBE.md")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TIMEOUT = 15.0

# Each candidate: (name, kind, url). kind = "json" (via resilient_get_json,
# JSON-decoding transport) or "text" (plain GET, RSS/HTML/anything non-JSON).
_CANDIDATES = [
    ("espn_nba_injuries_json", "json",
     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"),
    ("espn_nba_news_json", "json",
     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"),
    ("nba_official_injury_report", "text",
     "https://www.nba.com/players/injury-report"),
    ("nba_stats_api", "text",
     "https://stats.nba.com/stats/leaguedashplayerstats?Season=2024-25&SeasonType=Regular+Season"),
    ("espn_nba_rss_feed", "text",
     "https://www.espn.com/espn/rss/nba/news"),
    ("nitter_public_instance", "text",
     "https://nitter.net/search?q=NBA+injury+report&f=tweets"),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _probe_text(url: str) -> Dict[str, Any]:
    # ponytail: no Accept header -- an explicit "Accept: */*" tripped an
    # edge/CDN anti-bot heuristic on espn.com (200-shaped 202-empty response)
    # that a bare UA-only request does not; a real browser default Accept is
    # closer to what these hosts expect than a wildcard.
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # nosec - GET only
            body = resp.read()
            if len(body) == 0:
                # A 2xx with an empty body is NOT real content. Observed on both
                # espn.com/rss (a cold isolated call got 200/9632 bytes; repeat
                # calls in this same session degraded to 202/0 bytes -- a soft
                # anti-bot rate signature, not a permanent host death) and
                # nitter.net (200/0 bytes from the very first call -- consistent
                # with the widely-known public-instance shutdown, a dead
                # placeholder shell, not a rate reaction). Labeled BLOCKED
                # either way since neither yielded usable content.
                return {"verdict": "BLOCKED", "status": resp.status, "n_bytes": 0,
                        "error": "2xx-shaped but empty body (soft block or dead placeholder)"}
            return {"verdict": "REACHABLE", "status": resp.status, "n_bytes": len(body)}
    except urllib.error.HTTPError as exc:
        return {"verdict": "BLOCKED", "status": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- DNS/timeout/reset -> DEAD, not a code bug
        return {"verdict": "DEAD", "status": None, "error": f"{type(exc).__name__}: {exc}"}


def _probe_json(url: str) -> Dict[str, Any]:
    try:
        payload = resilient_get_json(url, timeout=_TIMEOUT)
        n = len(payload) if isinstance(payload, (list, dict)) else 0
        return {"verdict": "REACHABLE", "status": 200, "n_items": n}
    except urllib.error.HTTPError as exc:
        verdict = "BLOCKED" if exc.code in (401, 403, 406, 429, 451, 503) else "DEAD"
        return {"verdict": verdict, "status": exc.code, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- honest degrade, never sinks the probe loop
        return {"verdict": "DEAD", "status": None, "error": f"{type(exc).__name__}: {exc}"}


def run_probe(candidates=None, *, sleep_fn=time.sleep) -> Dict[str, Any]:
    """Attempt one fetch per candidate (jittered pause between). Returns the
    per-source result dict; does not write to disk (caller decides)."""
    cands = candidates if candidates is not None else _CANDIDATES
    results: Dict[str, Any] = {}
    for i, (name, kind, url) in enumerate(cands):
        fn = _probe_json if kind == "json" else _probe_text
        t0 = time.time()
        result = fn(url)
        result["url"] = url
        result["kind"] = kind
        result["latency_sec"] = round(time.time() - t0, 3)
        results[name] = result
        if i < len(cands) - 1:
            sleep_fn(random.uniform(0.6, 1.4))  # ponytail: polite jitter, not a governor
    return results


def write_probe_md(results: Dict[str, Any], out_path: Path = _OUT_PATH) -> Path:
    lines = [
        "# A2 news/injury source-reachability PROBE",
        f"captured_at: {_now_iso()}",
        "",
        "| source | verdict | status | evidence |",
        "|---|---|---|---|",
    ]
    for name, r in results.items():
        evidence = r.get("error") or f"n_bytes={r.get('n_bytes')}" \
            if r.get("n_bytes") is not None else (r.get("error") or f"n_items={r.get('n_items')}")
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
