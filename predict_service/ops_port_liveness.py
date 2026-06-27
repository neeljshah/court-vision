"""predict_service.ops_port_liveness -- real liveness for port-probed services.

ROOT CAUSE this fixes: ops.health_aggregator deliberately leaves port-probed
servers (m1_api_paper, m1_ui, m1_bankroll, ...) at live=None with no heartbeat --
"the supervisor probe governs them at boot". But the /api/ops/status normalizer
(status_freshness_normalizer.normalize_rows) then coerces every source-less row to
fresh='stale' (missing source = stale). The net effect: services that are demonstrably
serving requests (the very :8099 API answering the poll) read live=no / stale, and a
single critical port-probed row (m1_api_paper) drags overall -> 'degraded'. That is a
FALSE NEGATIVE -- the front end shows red for a healthy stack.

The honest fix: a port-probed service's liveness source IS its listening socket --
the same signal the supervisor uses at boot. This module probes 127.0.0.1:<port>
for rows that (a) have a port and (b) carry no heartbeat-derived liveness
(live is None), and stamps a real verdict:

  - socket open   -> live=True, source_ts=now (so the normalizer derives fresh).
  - socket closed -> live=False, fresh='down'    (a dead port is RED, never green).

It also builds an SLA map from each row's declared fresh_sec so the normalizer judges
a service against its OWN readiness window (e.g. m1_producer's ~25min) instead of a
blanket 300s default -- a producer that ticks every ~7 min must not read false-stale.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; stdlib only;
NEVER raises; no $ field; no edge claim; calibration not edge. A stale/dead feed is
RED, never green; we only turn a row green on a POSITIVE liveness signal (open socket).
"""
from __future__ import annotations

import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_TIMEOUT = 0.35  # seconds; an open local socket returns in <5ms.

# Daemon heartbeat files: data/cache/daemon_heartbeats/<service-name>.txt. Each
# row's NAME matches its heartbeat stem (m1_bankroll -> m1_bankroll.txt), so a
# heartbeat-only daemon (no port, no registered liveness source) can still be
# resolved by name. Resolved relative to the repo root (this file is two levels
# down: <repo>/predict_service/ops_port_liveness.py).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DAEMON_HB_DIR = _REPO_ROOT / "data" / "cache" / "daemon_heartbeats"
_DEFAULT_HB_SLA_SEC = 300.0  # fallback window when a row carries no fresh_sec.


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 'Z' string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tcp_open(host: str, port: int, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """True iff a TCP connection to host:port succeeds within *timeout*. NEVER raises."""
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout)):
            return True
    except Exception:  # noqa: BLE001 -- any failure means "not reachable", never raises
        return False


def build_sla_map(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Map service name -> declared fresh_sec, for rows that carry a positive one.

    Lets the freshness normalizer judge each service against its OWN readiness window
    instead of a blanket default. Rows without a usable fresh_sec are omitted (the
    caller's default_sla_sec still applies to them).
    """
    out: Dict[str, float] = {}
    for r in rows or []:
        name = r.get("name")
        fs = r.get("fresh_sec")
        if name and isinstance(fs, (int, float)) and not isinstance(fs, bool) and fs > 0:
            out[str(name)] = float(fs)
    return out


def _is_port_probed(row: Dict[str, Any]) -> bool:
    """A row whose liveness is governed by a listening socket, not a heartbeat.

    Port-probed == has a port AND the aggregator made no heartbeat claim (live is
    None) AND it has no concrete freshness verdict yet. We must not second-guess a
    row that already carries live True/False or a fresh string -- those came from a
    real heartbeat / freshness source.
    """
    port = row.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
        return False
    if row.get("live") is not None:
        return False
    if row.get("fresh") in ("fresh", "stale", "down"):
        return False
    return True


def apply_port_liveness(
    rows: List[Dict[str, Any]],
    *,
    host: str = _DEFAULT_HOST,
    timeout: float = _DEFAULT_TIMEOUT,
    now_iso: Optional[str] = None,
    prober=None,
) -> List[Dict[str, Any]]:
    """Return NEW rows with a real liveness verdict stamped on port-probed services.

    For each port-probed row (see _is_port_probed): probe host:port. If open, set
    live=True and source_ts=now (the normalizer then derives fresh from age~=0). If
    closed, set live=False and fresh='down' (a dead listener is RED, never green).
    Non-port-probed rows pass through untouched. NEVER raises.

    *prober* is an injectable ``(host, port, timeout) -> bool`` for tests; defaults
    to the real socket probe.
    """
    probe = prober or tcp_open
    stamp = now_iso or _utc_now_iso()
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        try:
            if not _is_port_probed(row):
                out.append(row)
                continue
            nr = dict(row)
            port = int(row["port"])
            if probe(host, port, timeout):
                nr["live"] = True
                nr["source_ts"] = stamp
                nr["age_sec"] = 0.0
                reason = "port %d reachable (socket liveness)" % port
                nr["reason"] = (
                    "%s; %s" % (row["reason"], reason) if row.get("reason") else reason
                )
            else:
                nr["live"] = False
                nr["fresh"] = "down"
                reason = "port %d unreachable (socket probe failed)" % port
                nr["reason"] = (
                    "%s; %s" % (row["reason"], reason) if row.get("reason") else reason
                )
            out.append(nr)
        except Exception as exc:  # noqa: BLE001 -- never let one bad row sink the list
            logger.warning("ops_port_liveness: row probe failed (%s): %s",
                           row.get("name"), exc)
            out.append(row)
    return out


def _hb_age_sec(hb_dir: Path, name: str) -> Optional[float]:
    """Seconds since <hb_dir>/<name>.txt was last written, or None if absent. NEVER raises."""
    try:
        p = hb_dir / ("%s.txt" % name)
        if not p.exists():
            return None
        return max(0.0, datetime.now(timezone.utc).timestamp() - p.stat().st_mtime)
    except Exception:  # noqa: BLE001
        return None


def _is_heartbeat_unresolved(row: Dict[str, Any]) -> bool:
    """A heartbeat-style row the aggregator could not resolve (no port, no claim).

    These are daemons that drop a data/cache/daemon_heartbeats/<name>.txt file but
    are not registered in daemon_registry.json, so liveness_snapshot never saw them.
    We must NOT touch a row that already has a port (port-probed) or a concrete
    live/fresh verdict from a real source.
    """
    if row.get("port"):
        return False
    if row.get("live") is not None:
        return False
    if row.get("fresh") in ("fresh", "stale", "down"):
        return False
    return bool(row.get("name"))


def apply_heartbeat_liveness(
    rows: List[Dict[str, Any]],
    *,
    hb_dir: Optional[Path] = None,
    now_iso: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Resolve unregistered heartbeat-only daemons by their on-disk heartbeat file.

    For each unresolved heartbeat row (see _is_heartbeat_unresolved): read
    <hb_dir>/<name>.txt mtime. If its age is within the row's declared fresh_sec
    window (or _DEFAULT_HB_SLA_SEC), stamp live=True with a source_ts of (now - age)
    so the freshness normalizer derives the SAME age and verdict. If the heartbeat is
    absent or past its window, leave the row untouched so the normalizer coerces it
    to stale -- a dead daemon is RED, never green. NEVER raises.
    """
    base = hb_dir or _DAEMON_HB_DIR
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        try:
            if not _is_heartbeat_unresolved(row):
                out.append(row)
                continue
            age = _hb_age_sec(base, str(row["name"]))
            sla = row.get("fresh_sec")
            window = float(sla) if isinstance(sla, (int, float)) and not isinstance(sla, bool) and sla > 0 else _DEFAULT_HB_SLA_SEC
            if age is None or age >= window:
                out.append(row)  # absent or stale -> let normalizer mark stale (honest)
                continue
            nr = dict(row)
            nr["live"] = True
            nr["age_sec"] = round(age, 1)
            beat = now - timedelta(seconds=age)
            nr["source_ts"] = beat.strftime("%Y-%m-%dT%H:%M:%SZ")
            reason = "heartbeat %s.txt fresh (age %.0fs < %.0fs)" % (row["name"], age, window)
            nr["reason"] = (
                "%s; %s" % (row["reason"], reason) if row.get("reason") else reason
            )
            out.append(nr)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ops_port_liveness: hb resolve failed (%s): %s",
                           row.get("name"), exc)
            out.append(row)
    return out


__all__ = [
    "tcp_open",
    "build_sla_map",
    "apply_port_liveness",
    "apply_heartbeat_liveness",
    "_is_port_probed",
    "_is_heartbeat_unresolved",
]
