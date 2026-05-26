"""discord_webhook.py — layered alert helper (Discord + vault + critical stack).

Used by every R17/R16+ daemon that has a fire-worthy event (URGENT bet,
line-killer lineup change, risk alarm, CONSENSUS_STEAM move, free arb,
watchdog restart). Each daemon imports either ``post_alert`` (legacy
signature) or ``alert`` (R21_N3 ergonomic API) and fires alongside the
existing vault-Markdown write.

API — legacy (preserved bit-for-bit for R18_K3 callers)
-------------------------------------------------------
    from src.alerts.discord_webhook import post_alert

    ok = post_alert(
        severity="URGENT",                # URGENT|WARN|INFO|STEAM
        source="auto_place_daemon",       # short tag identifying caller
        title="FIRED — Jokic OVER 28.5",  # one-line headline (≤256 chars)
        body="kelly=2.3%  stake=$57.50",  # multi-line detail (≤4000 chars)
        fields=[                          # optional list of {name,value}
            {"name": "edge_pct", "value": "6.4%"},
            {"name": "book",     "value": "fanduel"},
        ],
    )

API — R21_N3 layered (preferred for new callers)
------------------------------------------------
    from src.alerts.discord_webhook import alert

    result = alert("Watchdog restarted bankroll_monitor (rc=0)",
                   level="critical", tag="daemon_watchdog")
    # result = {"discord_sent": bool, "file_written": bool, "vault_appended": bool}

Behaviour matrix (both APIs share the same backend)
---------------------------------------------------
* Vault append → ALWAYS attempted (``vault/Improvements/alerts.md``,
   append-only, dated, tagged). Durable record even with no Discord.
* Critical stack → written to ``data/cache/alerts/critical_<date>.json``
   when ``level == "critical"`` OR ``DISCORD_WEBHOOK_URL`` is unset.
* Discord POST → fired only when ``DISCORD_WEBHOOK_URL`` is set AND
   rate-limit bucket has capacity; spills overflow to
   ``data/cache/discord_fallback_queue.jsonl``.
* ``post_alert`` legacy return: ``True`` only when Discord HTTP POST
   succeeded (preserves R18_K3 caller assumptions).
* ``alert`` returns the full dict so callers can introspect each layer.

Design rules
------------
* No-op (Discord) if ``DISCORD_WEBHOOK_URL`` env var is unset — but
  vault append + critical stack still fire.
* Bucket rate-limit: 5 messages / 5 sec. Overflow → fallback JSONL.
* ``_do_post(url, payload)`` is the seam for the unit tests to mock.
* stdlib only — no requests/aiohttp dependency.
* All file writes use a module-level lock so concurrent callers don't
  interleave bytes within a single line.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Discord embed colors (decimal RGB).
_SEVERITY_COLORS: Dict[str, int] = {
    "URGENT": 0xE74C3C,  # red
    "WARN":   0xF1C40F,  # yellow
    "INFO":   0x2ECC71,  # green
    "STEAM":  0x3498DB,  # blue
}

# R21_N3 — map the layered `level` ergonomic to the existing severity grid.
_LEVEL_TO_SEVERITY: Dict[str, str] = {
    "info":     "INFO",
    "warn":     "WARN",
    "warning":  "WARN",
    "critical": "URGENT",
}

_DEFAULT_TIMEOUT_SEC = 6
_RATE_LIMIT_BURST = 5            # 5 messages per
_RATE_LIMIT_WINDOW_SEC = 5.0     # 5-second sliding window

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FALLBACK_QUEUE = os.path.join(_PROJECT_DIR, "data", "cache", "discord_fallback_queue.jsonl")

# R21_N3 — durable + critical-stack defaults.
_VAULT_ALERTS_MD = os.path.join(_PROJECT_DIR, "vault", "Improvements", "alerts.md")
_CRITICAL_STACK_DIR = os.path.join(_PROJECT_DIR, "data", "cache", "alerts")

# ---------------------------------------------------------------------------
# Rate limiter — module-level so all callers share the bucket
# ---------------------------------------------------------------------------

_RATE_LOCK = threading.Lock()
_RATE_TIMESTAMPS: deque = deque()  # monotonic seconds of recent POSTs

# R21_N3 — single lock for vault + critical-stack file writes so concurrent
# threads/processes (within one process) never tear a record.
_FILE_LOCK = threading.Lock()


def _within_rate_limit(now: Optional[float] = None) -> bool:
    """True if a new POST is allowed; updates the bucket if so.

    Threadsafe; uses a sliding window of `_RATE_LIMIT_WINDOW_SEC` and a
    cap of `_RATE_LIMIT_BURST` messages within that window.
    """
    now = now if now is not None else time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW_SEC
    with _RATE_LOCK:
        # Evict entries outside the window.
        while _RATE_TIMESTAMPS and _RATE_TIMESTAMPS[0] < cutoff:
            _RATE_TIMESTAMPS.popleft()
        if len(_RATE_TIMESTAMPS) >= _RATE_LIMIT_BURST:
            return False
        _RATE_TIMESTAMPS.append(now)
        return True


def _reset_rate_limit() -> None:
    """Test hook — clear the rate-limit bucket between tests."""
    with _RATE_LOCK:
        _RATE_TIMESTAMPS.clear()


# ---------------------------------------------------------------------------
# Embed formatter
# ---------------------------------------------------------------------------


def build_embed(
    severity: str,
    source: str,
    title: str,
    body: str,
    fields: Optional[List[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Construct a Discord webhook payload (dict ready for json.dumps).

    Discord embed schema:
        {"embeds": [{"title": str, "description": str, "color": int,
                      "fields": [...], "footer": {...}, "timestamp": iso}]}
    """
    sev = (severity or "INFO").upper()
    color = _SEVERITY_COLORS.get(sev, _SEVERITY_COLORS["INFO"])
    # Discord limits: title ≤256, description ≤4096, field name ≤256, value ≤1024.
    safe_title = (title or "(no title)")[:256]
    safe_body = (body or "")[:4000]
    embed: Dict[str, Any] = {
        "title": f"[{sev}] {safe_title}",
        "description": safe_body,
        "color": color,
        "footer": {"text": f"source: {source}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if fields:
        formatted_fields = []
        for f in fields:
            try:
                name = str(f.get("name", ""))[:256]
                value = str(f.get("value", ""))[:1024]
            except AttributeError:
                # tolerate (name, value) tuples
                try:
                    name = str(f[0])[:256]
                    value = str(f[1])[:1024]
                except Exception:
                    continue
            if name and value:
                formatted_fields.append({"name": name, "value": value,
                                          "inline": True})
        if formatted_fields:
            embed["fields"] = formatted_fields
    return {"embeds": [embed]}


# ---------------------------------------------------------------------------
# Transport — seam for tests
# ---------------------------------------------------------------------------


def _do_post(url: str, payload: Mapping[str, Any]) -> bool:
    """Real HTTP POST.  Tests monkeypatch this to capture payloads."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT_SEC) as resp:
            # Discord returns 204 No Content on success.
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        log.warning("discord webhook POST failed: %s", exc)
        return False
    except Exception as exc:  # never raise into caller
        log.exception("discord webhook unexpected error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Fallback queue (overflow / network-down spillover)
# ---------------------------------------------------------------------------


def _spill_to_fallback(payload: Mapping[str, Any],
                       reason: str,
                       path: str = _FALLBACK_QUEUE) -> bool:
    """Append the alert to a JSONL file for later replay."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "payload": payload,
        }
        with _FILE_LOCK:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        return True
    except Exception as exc:
        log.warning("discord fallback write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# R21_N3 — durable vault append + critical-stack JSON
# ---------------------------------------------------------------------------


def _append_vault(message: str,
                  level: str,
                  tag: Optional[str],
                  source: str,
                  vault_path: str) -> bool:
    """Append one dated, tagged line to the vault alerts ledger.

    Format: ``- 2026-05-26T12:34:56Z [LEVEL] [tag/source] message``
    Append-only; never truncates; safe under concurrent callers via
    ``_FILE_LOCK``. Returns True on success, False on any IO error.
    """
    try:
        os.makedirs(os.path.dirname(vault_path), exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tag_str = tag or source or "unknown"
        # Single-line entry so future grep/awk operators don't break.
        safe_msg = (message or "").replace("\n", " ").replace("\r", " ").strip()
        line = f"- {ts} [{level.upper()}] [{tag_str}] {safe_msg}\n"
        with _FILE_LOCK:
            new_header = not os.path.exists(vault_path) or os.path.getsize(vault_path) == 0
            with open(vault_path, "a", encoding="utf-8") as fh:
                if new_header:
                    fh.write("# Alerts Log\n\n")
                    fh.write("Append-only durable record. Each line: "
                             "`- <iso-utc> [LEVEL] [tag] message`.\n\n")
                fh.write(line)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("vault alerts append failed: %s", exc)
        return False


def _push_critical_stack(message: str,
                         level: str,
                         tag: Optional[str],
                         source: str,
                         payload: Optional[Mapping[str, Any]],
                         stack_dir: str) -> bool:
    """Append the alert to today's critical stack (JSON array on disk).

    Path: ``<stack_dir>/critical_<YYYY-MM-DD>.json``. We keep an array
    of records so a separate operator-monitor can ``json.load`` and pop
    in FIFO order. Threadsafe within one process via ``_FILE_LOCK``.
    """
    try:
        os.makedirs(stack_dir, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(stack_dir, f"critical_{today}.json")
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "tag": tag or source or "unknown",
            "source": source,
            "message": message,
            "payload": payload,
        }
        with _FILE_LOCK:
            existing: List[Any] = []
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, OSError):
                    existing = []
            existing.append(record)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, default=str, indent=2)
            os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("critical-stack push failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Layered backend — shared by `alert` and `post_alert`
# ---------------------------------------------------------------------------


def _layered_dispatch(
    *,
    message: str,
    level: str,
    tag: Optional[str],
    source: str,
    severity: str,
    title: str,
    body: str,
    fields: Optional[List[Mapping[str, Any]]],
    webhook_url: Optional[str],
    fallback_path: Optional[str],
    vault_path: Optional[str],
    critical_stack_dir: Optional[str],
) -> Dict[str, Any]:
    """Shared core: vault append + critical stack + Discord POST.

    Returns ``{"discord_sent": bool, "file_written": bool,
               "vault_appended": bool}``.
    """
    vault_path = vault_path or _VAULT_ALERTS_MD
    stack_dir = critical_stack_dir or _CRITICAL_STACK_DIR
    fallback = fallback_path or _FALLBACK_QUEUE

    norm_level = (level or "info").lower()
    if norm_level not in {"info", "warn", "warning", "critical"}:
        norm_level = "info"

    payload = build_embed(severity, source, title, body, fields)

    # 1) Vault append — ALWAYS attempted.
    vault_appended = _append_vault(message, norm_level, tag, source, vault_path)

    # 2) Discord — only if URL set + rate limit ok.
    url = webhook_url
    if url is None:
        url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    url = (url or "").strip()
    discord_sent = False
    if url:
        if _within_rate_limit():
            discord_sent = bool(_do_post(url, payload))
            if not discord_sent:
                _spill_to_fallback(payload, reason="post_failed", path=fallback)
        else:
            log.warning("discord webhook rate-limited — spilling to fallback")
            _spill_to_fallback(payload, reason="rate_limited", path=fallback)

    # 3) Critical stack — written when critical OR no Discord URL configured.
    file_written = False
    if norm_level == "critical" or not url:
        file_written = _push_critical_stack(
            message, norm_level, tag, source, payload, stack_dir
        )

    return {
        "discord_sent": discord_sent,
        "file_written": file_written,
        "vault_appended": vault_appended,
    }


# ---------------------------------------------------------------------------
# Public API — R21_N3 ergonomic
# ---------------------------------------------------------------------------


def alert(
    message: str,
    level: str = "info",
    tag: Optional[str] = None,
    *,
    source: Optional[str] = None,
    body: Optional[str] = None,
    fields: Optional[List[Mapping[str, Any]]] = None,
    severity: Optional[str] = None,
    webhook_url: Optional[str] = None,
    fallback_path: Optional[str] = None,
    vault_path: Optional[str] = None,
    critical_stack_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Layered alert: durable vault record + critical fallback + Discord.

    Parameters
    ----------
    message : str
        Headline / one-line summary. Always written to the vault ledger.
    level : str, default ``"info"``
        One of ``"info"``, ``"warn"``, ``"critical"`` (also accepts
        ``"warning"`` as a synonym for ``warn``).
    tag : str, optional
        Short caller tag (e.g. ``"daemon_watchdog"``). Defaults to
        ``source`` or ``"unknown"`` if neither is given.
    source : str, optional
        Module/daemon identifier surfaced in the Discord embed footer.
    body : str, optional
        Extra detail for the Discord embed description; falls back to
        ``message`` if omitted.
    fields : list of dict/tuple, optional
        Discord embed key/value fields.
    webhook_url, fallback_path, vault_path, critical_stack_dir
        Test seams — default to the production paths under
        ``vault/Improvements/`` and ``data/cache/alerts/``.

    Returns
    -------
    dict
        ``{"discord_sent": bool, "file_written": bool,
           "vault_appended": bool}``.
    """
    norm_level = (level or "info").lower()
    eff_severity = (severity or _LEVEL_TO_SEVERITY.get(norm_level, "INFO")).upper()
    src = source or tag or "alert"
    return _layered_dispatch(
        message=message,
        level=norm_level,
        tag=tag,
        source=src,
        severity=eff_severity,
        title=message,
        body=body if body is not None else message,
        fields=fields,
        webhook_url=webhook_url,
        fallback_path=fallback_path,
        vault_path=vault_path,
        critical_stack_dir=critical_stack_dir,
    )


# ---------------------------------------------------------------------------
# Public API — legacy (R18_K3 callers — DO NOT BREAK)
# ---------------------------------------------------------------------------


def post_alert(
    severity: str,
    source: str,
    title: str,
    body: str,
    fields: Optional[List[Mapping[str, Any]]] = None,
    *,
    webhook_url: Optional[str] = None,
    fallback_path: Optional[str] = None,
    vault_path: Optional[str] = None,
    critical_stack_dir: Optional[str] = None,
) -> bool:
    """Format and POST an alert to the configured Discord webhook.

    Backwards-compatible R18_K3 entry point — return value is purely the
    Discord HTTP outcome (True = 2xx, False = no URL / rate-limited /
    POST failed). The vault append + critical stack run as side effects
    so failures here still leave a durable trail behind.

    Behaviour matrix
    ----------------
    * `DISCORD_WEBHOOK_URL` unset  → Discord no-op (False return), but
       vault append + critical-stack push still happen.
    * Rate-limited                → spill payload to fallback JSONL,
       return False.
    * `_do_post` returns False    → spill payload to fallback JSONL,
       return False.
    * Otherwise                   → True.
    """
    sev_upper = (severity or "INFO").upper()
    # Map R18_K3 severities to R21_N3 levels so the layered backend can
    # route the critical-stack correctly.
    legacy_level = {
        "URGENT": "critical",
        "WARN":   "warn",
        "STEAM":  "warn",
        "INFO":   "info",
    }.get(sev_upper, "info")
    result = _layered_dispatch(
        message=title or "(no title)",
        level=legacy_level,
        tag=source,
        source=source,
        severity=sev_upper,
        title=title,
        body=body,
        fields=fields,
        webhook_url=webhook_url,
        fallback_path=fallback_path,
        vault_path=vault_path,
        critical_stack_dir=critical_stack_dir,
    )
    # Legacy contract: return True ONLY when the Discord POST landed.
    # R18_K3 callers (test_discord_webhook.py) gate on this exact bool.
    return bool(result["discord_sent"])


__all__ = [
    "alert",
    "post_alert",
    "build_embed",
    "_do_post",
    "_spill_to_fallback",
    "_within_rate_limit",
    "_reset_rate_limit",
    "_append_vault",
    "_push_critical_stack",
    "_layered_dispatch",
]
