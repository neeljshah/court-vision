"""ops.freshness_guard -- source-level freshness classification for the supervisor stack.

Wraps the low-level scripts.platformkit.odds_provider.freshness helpers with a
*per-source* max-age registry so the supervisor can classify any data feed by name
and surface stale/down feeds as explicit status -- never silently trusted.

Three-level scale (matches the existing health_snapshot / slo pattern):
  "fresh"  -- age_sec <= max_age for this source
  "stale"  -- age_sec > max_age but the timestamp was parseable (degraded, not dead)
  "down"   -- timestamp is None / unparseable (source has not reported recently)

Public API
----------
guard_status(source, captured_at, *, now=None, max_age_sec=None) -> dict
    Returns {"status": "fresh"|"stale"|"down", "age_sec": float|None, "source": str,
             "max_age_sec": float}.
    max_age_sec overrides the per-source registry when supplied.

SOURCE_MAX_AGE: dict[str, float]
    Per-source max ages in seconds. ONLY contains sources that a live
    ops.service_registry descriptor can actually reference (no dead config). The
    data-feed thresholds (odds / linescores / games-spine) are DERIVED from the
    declared ``sla_minutes`` in the per-sport ingest manifests so the manifest SLA
    is the single authority and a future source can never become dead config.

live_source_keys() -> list[str]
    The source keys this module will actually classify with a NON-default threshold
    (everything in SOURCE_MAX_AGE except "_default"). Used by tests to prove there
    is no dead/unreachable SLA config.

INVARIANTS: <=300 LOC; ASCII; never raises; pure (time injectable); stdlib only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Reuse the low-level parser from the existing odds_provider module rather than
# duplicating the Z-suffix and naive-tz logic.
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.odds_provider.freshness import (
        _parse_utc,  # noqa: PLC2701
        _utc_now,    # noqa: PLC2701
    )
except ImportError:  # running tests outside the full repo env
    def _parse_utc(ts: Any) -> Optional[datetime]:  # type: ignore[misc]
        if not ts:
            return None
        try:
            s = str(ts).strip().replace("Z", "+00:00")
            if not s:
                return None
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _utc_now(now: Optional[datetime]) -> datetime:  # type: ignore[misc]
        if now is not None:
            dt = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        return datetime.now(timezone.utc)


_DEFAULT_MAX_AGE: float = 900.0  # 15 min fallback when a source has no declared SLA

# ---------------------------------------------------------------------------
# Manifest-derived data SLAs (sla_minutes from domains.<sport>.ingest_manifest).
#
# The ingest manifests are the single authority for how stale a DATA corpus may
# be (e.g. odds=120min, linescores=10min, games=1440min). We map the live
# supervisor data-feed sources onto those corpora so the declared sla_minutes is
# ACTUALLY ENFORCED by the rollup -- not a dead contract. We take the TIGHTEST
# sla_minutes across sports for a corpus (the strictest honest bound).
# ---------------------------------------------------------------------------
# source key -> (manifest corpus whose sla_minutes governs it,
#                operational heartbeat window for the daemon that feeds it).
# The effective threshold is the TIGHTER of the two: the manifest SLA is a hard
# ceiling (data older than it is stale by contract) and the heartbeat window is
# the operational cadence. Taking the min never WEAKENS an honest bound.
_SOURCE_TO_CORPUS: Dict[str, str] = {
    "line_daemon": "odds",        # line_snapshot_daemon keeps the odds corpus fresh
    "inplay_history": "linescores",  # in-play capture feeds in-game linescores
}
# Operational heartbeat cadence for each data-feed source (seconds).
_DATA_FEED_HEARTBEAT: Dict[str, float] = {
    "line_daemon":     300.0,   #  5 min -- line_snapshot_daemon beats
    "inplay_history":  300.0,   #  5 min -- in-play capture runner (P2)
}


def _scan_manifest_slas() -> Dict[str, float]:
    """Return {corpus: tightest sla_seconds} across every domain ingest manifest.

    Pure read of the declared contracts; never raises (a missing/broken manifest
    is simply skipped). Corpora with sla_minutes=None (historical/reference) are
    omitted -- they have no live freshness SLA.
    """
    import importlib

    from scripts.platformkit.ingest_manifest_core import IngestManifest

    sports = ("basketball_nba", "mlb", "nfl", "soccer", "tennis")
    out: Dict[str, float] = {}
    for sport in sports:
        try:
            mod = importlib.import_module(f"domains.{sport}.ingest_manifest")
        except Exception:  # noqa: BLE001 -- a sport without a manifest is fine
            continue
        man = None
        for val in vars(mod).values():
            if isinstance(val, IngestManifest):
                man = val
                break
        if man is None:
            continue
        for src in man.sources:
            sla = getattr(src, "sla_minutes", None)
            if sla is None or sla <= 0:
                continue
            secs = float(sla) * 60.0
            prev = out.get(src.corpus)
            if prev is None or secs < prev:
                out[src.corpus] = secs  # tightest bound wins
    return out


def _build_source_max_age() -> Dict[str, float]:
    """Compose the live-source SLA registry: heartbeat sources + manifest-derived.

    Every key here is a source that a live ops.service_registry descriptor can
    reference (its ``freshness_source``). There is no aspirational / dead config.
    """
    manifest = _scan_manifest_slas()
    reg: Dict[str, float] = {
        # Process-heartbeat sources (no data corpus -- these only age out if the
        # supervised process dies; threshold == how long without a heartbeat we
        # tolerate before declaring the feed unobserved).
        "predict_service":  2700.0,  # ~45 min -- :8099 scheduler heartbeat; >2x the
                                     # slowest enabled scheduler cadence (soccer=1200s)
                                     # + margin, matching m1_paper/m1_line_daemon fresh_sec=2700
        "ingame_live_loop":  300.0,  #  5 min -- live_loop heartbeat; >2x the IDLE
                                     # poll cadence (IDLE_INTERVAL_SEC=120s) + margin
        "paper_loop":       300.0,   #  5 min -- auto_loop (paper trading)
        "m7_ingame_refresh": 7800.0,  # ~2.2h -- in-game refresh loop beats HOURLY (P7)
        "_default":         _DEFAULT_MAX_AGE,
    }
    # Data-feed sources: enforce the manifest corpus SLA as a hard ceiling, but
    # use the tighter operational heartbeat window when that is stricter. The
    # manifest sla_minutes is thus ACTUALLY consulted (no dead contract) and the
    # threshold is never weakened below the operational cadence.
    for source, corpus in _SOURCE_TO_CORPUS.items():
        manifest_sla = manifest.get(corpus, _DEFAULT_MAX_AGE)
        hb = _DATA_FEED_HEARTBEAT.get(source, _DEFAULT_MAX_AGE)
        reg[source] = min(manifest_sla, hb)
    return reg


# Per-source max-age registry (seconds), keyed by lower-cased source name.
# Built once at import; manifest SLAs are the authority for data feeds.
SOURCE_MAX_AGE: Dict[str, float] = _build_source_max_age()


def live_source_keys() -> List[str]:
    """Source keys with a real (non-default) SLA -- proves no dead config."""
    return sorted(k for k in SOURCE_MAX_AGE if k != "_default")


def _resolve_max_age(source: str, override: Optional[float]) -> float:
    """Return the effective max_age: explicit override > registry > default."""
    if override is not None:
        return float(override)
    key = source.lower().strip()
    return SOURCE_MAX_AGE.get(key, _DEFAULT_MAX_AGE)


def guard_status(
    source: str,
    captured_at: Any,
    *,
    now: Optional[datetime] = None,
    max_age_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Classify the freshness of *captured_at* for the named *source*.

    Parameters
    ----------
    source       : logical name of the data feed (looked up in SOURCE_MAX_AGE).
    captured_at  : ISO-8601 string, datetime, or None -- the data's timestamp.
    now          : injectable UTC datetime for testing (default: datetime.now(utc)).
    max_age_sec  : explicit override; if None the registry value for *source* is used.

    Returns
    -------
    dict with keys:
        "status"      : "fresh" | "stale" | "down"
        "age_sec"     : float | None   (None iff timestamp was unparseable)
        "source"      : str            (echoed back for easy logging)
        "max_age_sec" : float          (effective threshold used)

    Never raises -- a breaker or supervisor can always call this safely.
    """
    effective_max = _resolve_max_age(source, max_age_sec)

    dt = _parse_utc(captured_at)
    if dt is None:
        # Cannot determine age -- treat as down (most conservative).
        return {
            "status": "down",
            "age_sec": None,
            "source": source,
            "max_age_sec": effective_max,
        }

    reference = _utc_now(now)
    age_sec = (reference - dt).total_seconds()
    status = "fresh" if age_sec <= effective_max else "stale"
    return {
        "status": status,
        "age_sec": round(age_sec, 3),
        "source": source,
        "max_age_sec": effective_max,
    }


__all__ = [
    "SOURCE_MAX_AGE",
    "guard_status",
    "live_source_keys",
]
