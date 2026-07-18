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
from .schema_snapshot import check_sport as _schema_check_sport
from .transport import mark_stealth_first

_REPO = Path(__file__).resolve().parents[3]
_OUT_PATH = _REPO / "data" / "frontend" / "ops" / "feed_health.json"

GREEN = "GREEN"
RED = "RED"
# A schema-drift status that is PERSISTENT enough to warrant attention but is NOT a
# scraper outage -- it lives ONLY inside the schema_drift overlay and never flips the
# top-level feed_health "overall"/row status to RED, so consumers that only branch on
# 'red' keep their GREEN semantics unchanged.
SOFT_RED = "soft_red"
_DRIFT_COUNTER_PATH = _REPO / "data" / "cache" / "schema_drift_counters.json"
_DRIFT_THRESHOLD = 3   # consecutive drifted scans with a TYPE_CHANGE before soft_red

# "wnba"/"npb" added 2026-07-03 (paper enablement sweep, LANE 5): every provider's
# fetch() degrades cleanly to an "unsupported sport" UNAVAILABLE for a sport it does
# not carry (never raises), which _classify_reason maps to GREEN (a benign, honest
# degrade) -- so widening this list only ADDS real signal (kalshi covers both; a
# provider silently going RED for either sport now becomes visible) and can never
# turn an existing GREEN row RED.
DEFAULT_SPORTS = ("nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba", "npb")

# provider name -> the host its live network calls hit. Sourced from each
# module's own base-URL constant (grepped, not guessed): pinnacle._BASE,
# fanduel._url()'s sbapi.<region>.sportsbook.fanduel.com, espn._SITE,
# kalshi._BASE, polymarket._BASE. Used only by heal() to mark a RED
# auth/blocked host stealth-first for its NEXT fetch (see transport.py).
PROVIDER_HOSTS: Dict[str, str] = {
    "pinnacle": "guest.api.arcadia.pinnacle.com",
    "fanduel": "sbapi.nj.sportsbook.fanduel.com",
    "espn": "site.api.espn.com",
    "kalshi": "api.elections.kalshi.com",
    "polymarket": "gamma-api.polymarket.com",
}

# Reason substrings meaning "this looks like an auth/bot-wall block" -- the
# shape heal() escalates to the stealth transport. Case-insensitive match.
_BLOCKED_REASON_MARKERS = ("401", "403", "forbidden", "auth", "unauthorized")

# Reason substrings that mean "this provider legitimately has nothing to say"
# (unsupported sport for this venue, or an honestly empty slate) -- NOT a break.
_BENIGN_REASON_MARKERS = (
    "unsupported sport", "no events", "no world cup events", "no mlb events",
    "no player-prop markets", "empty fixture", "empty/invalid fixtures",
)

# Reason substrings meaning "a rate-limit blip, not a broken scraper" -- e.g.
# live kalshi 429s from back-to-back capture/snapshot daemons hammering the
# same host (see _default_providers() docstring). Classified GREEN (tagged
# transient_degrade, row still visible) so one rate-limit blip can't flip
# overall RED; a REAL auth/timeout/parse fault on the same provider still
# classifies RED as before.
_TRANSIENT_REASON_MARKERS = ("429", "too many requests")

# A 429/rate-limit blip stays GREEN once, but a provider that is 429ing on
# EVERY scan is not a blip -- it is silently dead (see golive_hardening_backlog
# finding #2). Same persistent-counter shape as the schema-drift counter above;
# promote_persistent_transient() escalates a (sport,provider) pair to RED (not
# soft_red -- an indefinite 429 IS an outage, unlike schema noise) once it has
# been transient_degrade on >=_TRANSIENT_THRESHOLD CONSECUTIVE scans.
_TRANSIENT_COUNTER_PATH = _REPO / "data" / "cache" / "transient_429_counters.json"
_TRANSIENT_THRESHOLD = 3

# Sports that are capture-only / no-model (verdicts come from a resolver like
# kalshi/kbo results, never from a live in-game model dispatch) AND have a
# KNOWN structural venue gap: pinnacle carries no league-id mapping for them
# (confirmed 2026-07-05: pinnacle.py's resolve_league_ids() returns empty for
# 'npb', a permanent map gap, not a transient fault). Verified live same-day:
# npb's pinnacle row reads "pinnacle: no live league ids for 'npb'" and is the
# ONLY red row for the sport (espn/fanduel/polymarket already degrade to their
# own benign "unsupported sport" GREEN; kalshi returns real events). kbo is
# NOT in DEFAULT_SPORTS today (unscanned), so it is deliberately left out here
# until it is actually probed and shows the same structural pattern.
CAPTURE_ONLY_SPORTS = frozenset({"npb"})

# Reason substrings that are a KNOWN structural absence for a capture-only
# sport (see CAPTURE_ONLY_SPORTS) -- a benign, permanent venue gap, not a
# scraper fault. Only applied when the row's sport is in CAPTURE_ONLY_SPORTS,
# so the same reason on a normal sport still classifies RED.
_CAPTURE_ONLY_BENIGN_MARKERS = ("no live league ids",)


def _classify_reason(reason: str, sport: Optional[str] = None) -> str:
    low = (reason or "").lower()
    for marker in _BENIGN_REASON_MARKERS:
        if marker in low:
            return GREEN
    for marker in _TRANSIENT_REASON_MARKERS:
        if marker in low:
            return GREEN
    if sport in CAPTURE_ONLY_SPORTS:
        for marker in _CAPTURE_ONLY_BENIGN_MARKERS:
            if marker in low:
                return GREEN
    return RED  # auth/forbidden/timeout/parse/unexpected-shape/exception -> broken


def _default_providers() -> List[Any]:
    """The same provider stack the live slate uses (reuse, not reinvent).

    BUGFIX (2026-07-07): aggregate's KalshiProvider is unpaced (governor_caller=
    None, untouched here). 7 back-to-back kalshi calls with zero spacing, on top
    of the capture/snapshot daemons hammering the same host, produced live
    "kalshi markets failed: HTTP Error 429" (logs/m30_feed_health.err) -- never a
    ticker/endpoint fault. Swap in a governed KalshiProvider for the probe only.
    """
    from .aggregate import default_providers as _dp
    from .kalshi import KalshiProvider
    provs = _dp(use_cache=False)
    return [KalshiProvider(use_cache=False, governor_caller="feed_health")
            if getattr(p, "name", None) == "kalshi" else p for p in provs]


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
        status = _classify_reason(reason, sport)
        row.update(status=status, reason=reason, n_events=None)
        if status == GREEN and sport in CAPTURE_ONLY_SPORTS and any(
                m in reason.lower() for m in _CAPTURE_ONLY_BENIGN_MARKERS):
            row["capture_only_degrade"] = True
        if status == GREEN and any(m in reason.lower() for m in _TRANSIENT_REASON_MARKERS):
            row["transient_degrade"] = True
        return row
    if isinstance(res, list):
        row.update(status=GREEN, reason=None, n_events=len(res))
        return row
    row.update(status=RED, reason="unexpected return type", n_events=None)
    return row


def _load_drift_counters(path: Path) -> Dict[str, int]:
    """Best-effort read of the persistent per-(sport|provider) drift counter."""
    try:
        if path.exists():
            d = json.loads(path.read_text(encoding="ascii"))
            if isinstance(d, dict):
                return {k: int(v) for k, v in d.items() if isinstance(v, (int, float))}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_drift_counters(counters: Dict[str, int], path: Path) -> None:
    """Atomically persist the drift counter (tmp + os.replace). Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(counters, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(path))
    except Exception:  # noqa: BLE001
        pass


def promote_persistent_drift(notes: Dict[str, Any], *,
                             counter_path: Optional[Path] = None,
                             threshold: int = _DRIFT_THRESHOLD) -> Dict[str, Any]:
    """Stamp status 'soft_red' on any (sport, provider) whose type_changes have
    persisted for >=*threshold* CONSECUTIVE drifted scans, backed by a small
    persistent counter. A scan with NO type_change for a pair resets its counter.
    soft_red lives ONLY in this schema_drift overlay -- it never flips the top-level
    feed_health overall/row status to RED (GREEN semantics preserved for consumers
    that only check 'red'). Mutates + returns *notes*. Never raises."""
    path = counter_path if counter_path is not None else _DRIFT_COUNTER_PATH
    try:
        counters = _load_drift_counters(path)
        seen: set = set()
        for sport, provs in (notes or {}).items():
            for provider, info in (provs or {}).items():
                if not isinstance(info, dict) or not info.get("type_changes"):
                    continue
                key = "%s|%s" % (sport, provider)
                counters[key] = counters.get(key, 0) + 1
                seen.add(key)
                if counters[key] >= threshold:
                    info["status"] = SOFT_RED
                    info["consecutive_type_change_drifts"] = counters[key]
        for key in list(counters):        # reset any pair not drifting-with-type-change now
            if key not in seen:
                counters[key] = 0
        _save_drift_counters(counters, path)
    except Exception:  # noqa: BLE001 -- promotion must never sink feed_health
        pass
    return notes


def promote_persistent_transient(rows: List[Dict[str, Any]], *,
                                 counter_path: Optional[Path] = None,
                                 threshold: int = _TRANSIENT_THRESHOLD) -> List[Dict[str, Any]]:
    """Escalate a (sport, provider) row from GREEN/transient_degrade to RED once
    it has 429'd/rate-limited on >=*threshold* CONSECUTIVE scans, backed by a
    small persistent counter (reuses the schema-drift counter's on-disk shape).
    A scan where the pair is NOT transient this time (real GREEN, a real RED
    fault, or simply absent) resets its counter to 0. Unlike schema-drift's
    soft_red (which never flips the top-level status), this DOES flip the row
    to RED -- an indefinitely-429ing provider is a real outage, not noise.
    Mutates + returns *rows*. Never raises."""
    path = counter_path if counter_path is not None else _TRANSIENT_COUNTER_PATH
    try:
        counters = _load_drift_counters(path)
        seen: set = set()
        for row in rows or []:
            key = "%s|%s" % (row.get("sport"), row.get("provider"))
            seen.add(key)
            if row.get("transient_degrade"):
                counters[key] = counters.get(key, 0) + 1
                if counters[key] >= threshold:
                    row["status"] = RED
                    row["reason"] = "persistent_429:%s" % (row.get("reason") or "")
                    row["consecutive_transient_429"] = counters[key]
            else:
                counters[key] = 0
        for key in list(counters):        # reset any pair not seen this scan
            if key not in seen:
                counters[key] = 0
        _save_drift_counters(counters, path)
    except Exception:  # noqa: BLE001 -- promotion must never sink feed_health
        pass
    return rows


def _schema_drift_notes(sports: Sequence[str], *,
                        counter_path: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort schema-drift overlay per sport. Never raises; a sport with
    no local capture file yet reports {} for that sport (honest, not RED).
    Persistent type_changes (>=3 consecutive drifted scans) promote to soft_red."""
    notes: Dict[str, Any] = {}
    for sport in sports:
        try:
            doc = _schema_check_sport(sport)
            drifted = {p: info for p, info in doc.get("providers", {}).items()
                       if info.get("status") == "drift"}
            if drifted:
                notes[sport] = drifted
        except Exception:  # noqa: BLE001 -- overlay must never sink feed_health
            continue
    return promote_persistent_drift(notes, counter_path=counter_path)


def scan(
    sports: Sequence[str] = DEFAULT_SPORTS,
    *, providers: Optional[Sequence[Any]] = None,
    provider_fn: Optional[Callable[[], Sequence[Any]]] = None,
    transient_counter_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Probe every (provider, sport) pair. Never raises.

    ``providers`` injects a fixed list (offline tests); ``provider_fn`` injects a
    factory (matches aggregate's own laziness); default reuses the live stack.
    ``transient_counter_path`` overrides the persistent 429-streak counter file
    (tests should always pass a tmp_path here so the shared repo counter never
    accumulates state across unrelated test runs).
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

    promote_persistent_transient(rows, counter_path=transient_counter_path)

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
        "schema_drift": _schema_drift_notes(sports),
        "honest_note": (
            "read-only live probe of the SAME providers the real slate uses. RED = "
            "the scraper itself is broken (auth/forbidden/timeout/parse/exception); "
            "GREEN includes an honest empty/unsupported-sport degrade, which is not "
            "an outage. No $ field, no edge claim."
        ),
    }


def heal(doc: Dict[str, Any], *, mark: Callable[..., None] = mark_stealth_first) -> List[str]:
    """Escalate any RED auth/blocked provider to the stealth transport tier.

    For each row in *doc* that is RED with a reason shaped like an auth/bot-wall
    block (401/403/forbidden/auth/unauthorized, case-insensitive), look up that
    provider's host in PROVIDER_HOSTS and mark it stealth-first so its NEXT fetch
    tries the browser-TLS-impersonated path before the plain one. A provider not
    present in PROVIDER_HOSTS, or a RED row that is not blocked-shaped (timeout /
    parse / exception / unexpected-shape), is left alone -- heal() only reacts to
    the specific failure shape stealth is known to fix. Never raises; returns the
    list of hosts marked (may contain duplicates if multiple sports triggered the
    same provider/host -- callers that want a set can dedupe).
    """
    marked: List[str] = []
    try:
        for row in doc.get("rows", []) or []:
            if row.get("status") != RED:
                continue
            reason = (row.get("reason") or "").lower()
            if not any(marker in reason for marker in _BLOCKED_REASON_MARKERS):
                continue
            host = PROVIDER_HOSTS.get(row.get("provider"))
            if not host:
                continue
            try:
                mark(host)
                marked.append(host)
            except Exception:  # noqa: BLE001 -- one bad mark must not sink heal()
                pass
    except Exception:  # noqa: BLE001 -- heal() must never raise
        pass
    return marked


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
    marked = heal(doc)
    if marked:
        print("healed (marked stealth-first): %s" % ", ".join(sorted(set(marked))))
    write_status(doc)
    print("\nwrote %s" % _OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["GREEN", "RED", "SOFT_RED", "DEFAULT_SPORTS", "PROVIDER_HOSTS",
           "CAPTURE_ONLY_SPORTS", "probe_one", "scan", "heal", "write_status",
           "load_status", "render", "promote_persistent_drift",
           "promote_persistent_transient"]
