"""scripts.platformkit.odds_provider.feed_health -- per-provider scraper health scoreboard.

THE GAP: aggregate.default_providers() silently tolerates a down/blocked source
(a provider raising or degrading -> that venue just vanishes from the merged
slate, e.g. today's live Pinnacle 401 on soccer_intl). Nobody notices a dark
scraper unless they read logs. This module makes that visible: for each
(provider, sport) pair it classifies the result as GREEN (returned real data,
or an HONEST "no events"/"unsupported sport" degrade -- both are healthy, not
an outage) or RED (an error-shaped degrade: auth/forbidden/timeout/parse
failure/unexpected-shape/exception -- the scraper itself is broken).

HONEST RAILS: read-only network probes (reuses the SAME providers the live
slate uses, so this measures the REAL path, not a synthetic ping); never
raises; no $ field; no flag flip; no data/registry/ write; no edge claim.

Run:  python -m scripts.platformkit.odds_provider.feed_health
Per-file test: scripts/platformkit/odds_provider/test_feed_health.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .base import is_unavailable

_REPO = Path(__file__).resolve().parents[3]
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "feed_health.json"

GREEN = "GREEN"
RED = "RED"

DEFAULT_SPORTS = ("mlb", "soccer_intl")

# Reason substrings that mean "this provider legitimately has nothing to say"
# (unsupported sport for this venue, or an honestly empty slate) -- NOT a break.
_BENIGN_REASON_MARKERS = (
    "unsupported sport", "no events", "no world cup events", "no mlb events",
    "no player-prop markets", "empty fixture", "empty/invalid fixtures",
)


def _classify_reason(reason: str) -> str:
    low = (reason or "").lower()
    for marker in _BENIGN_REASON_MARKERS:
        if marker in low:
            return GREEN
    return RED  # auth/forbidden/timeout/parse/unexpected-shape/exception -> broken


def _default_providers() -> List[Any]:
    """The same provider stack the live slate uses (reuse, not reinvent)."""
    from .aggregate import default_providers as _dp
    return _dp(use_cache=False)


def probe_one(provider: Any, sport: str) -> Dict[str, Any]:
    """GREEN/RED verdict for one (provider, sport) live fetch. Never raises."""
    name = getattr(provider, "name", type(provider).__name__)
    row: Dict[str, Any] = {"provider": name, "sport": sport}
    try:
        res = provider.fetch(sport)
    except Exception as exc:  # noqa: BLE001 -- a provider exception is a RED finding
        row.update(status=RED, reason="exception:%s" % type(exc).__name__, n_events=None)
        return row
    if is_unavailable(res):
        reason = str(res.get("reason") or "unavailable")
        row.update(status=_classify_reason(reason), reason=reason, n_events=None)
        return row
    if isinstance(res, list):
        row.update(status=GREEN, reason=None, n_events=len(res))
        return row
    row.update(status=RED, reason="unexpected return type", n_events=None)
    return row


def scan(
    sports: Sequence[str] = DEFAULT_SPORTS,
    *, providers: Optional[Sequence[Any]] = None,
    provider_fn: Optional[Callable[[], Sequence[Any]]] = None,
) -> Dict[str, Any]:
    """Probe every (provider, sport) pair. Never raises.

    ``providers`` injects a fixed list (offline tests); ``provider_fn`` injects a
    factory (matches aggregate's own laziness); default reuses the live stack.
    """
    if providers is not None:
        provs = list(providers)
    elif provider_fn is not None:
        provs = list(provider_fn())
    else:
        provs = _default_providers()

    rows: List[Dict[str, Any]] = []
    for prov in provs:
        for sport in sports:
            rows.append(probe_one(prov, sport))

    n_red = sum(1 for r in rows if r["status"] == RED)
    by_provider: Dict[str, Any] = {}
    for r in rows:
        b = by_provider.setdefault(r["provider"], {"green": 0, "red": 0})
        b["green" if r["status"] == GREEN else "red"] += 1

    return {
        "sports": list(sports),
        "rows": rows,
        "n_probed": len(rows),
        "n_red": n_red,
        "by_provider": by_provider,
        "overall": RED if n_red else GREEN,
        "honest_note": (
            "read-only live probe of the SAME providers the real slate uses. RED = "
            "the scraper itself is broken (auth/forbidden/timeout/parse/exception); "
            "GREEN includes an honest empty/unsupported-sport degrade, which is not "
            "an outage. No $ field, no edge claim."
        ),
    }


def write_status(doc: Dict[str, Any], *, out_path: Optional[Path] = None,
                  now: Optional[float] = None) -> bool:
    """Atomically write the scan result (tmp + os.replace). Never raises."""
    try:
        path = Path(out_path) if out_path is not None else _OUT_PATH
        ts = float(now) if now is not None else time.time()
        full = dict(doc)
        full["generated_at"] = ts
        full["component"] = "m_feed_health"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(full, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
        return True
    except Exception:  # noqa: BLE001 -- write must never crash the caller
        return False


def load_status(*, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Best-effort read of the last written scan. None on any failure/missing file."""
    try:
        p = Path(path) if path is not None else _OUT_PATH
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001
        return None


def render(doc: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append("FEED HEALTH -- per-provider scraper scoreboard (%s)"
                 % ",".join(doc.get("sports", [])))
    lines.append("=" * 78)
    for name, b in sorted(doc.get("by_provider", {}).items()):
        status = RED if b.get("red", 0) else GREEN
        lines.append("%-14s %s  green=%d red=%d" % (name, status, b.get("green", 0),
                                                     b.get("red", 0)))
    for r in doc.get("rows", []):
        if r["status"] == RED:
            lines.append("  RED  %-14s %-12s %s" % (r["provider"], r["sport"], r["reason"]))
    lines.append("-" * 78)
    lines.append("OVERALL: " + doc.get("overall", "?"))
    lines.append("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    doc = scan()
    print(render(doc))
    write_status(doc)
    print("\nwrote %s" % _OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GREEN", "RED", "DEFAULT_SPORTS", "probe_one", "scan", "write_status",
           "load_status", "render"]
