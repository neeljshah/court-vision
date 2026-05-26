"""discord_webhook.py — single helper module for Discord push notifications.

Used by every R17/R16 daemon that has a fire-worthy event (URGENT bet,
line-killer lineup change, risk alarm, CONSENSUS_STEAM move, free arb).
Each daemon imports `post_alert` and fires it alongside the existing
vault-Markdown write so the operator gets a phone push on top of the
file-on-disk audit trail.

API
---
    from src.alerts.discord_webhook import post_alert

    post_alert(
        severity="URGENT",                # URGENT|WARN|INFO|STEAM
        source="auto_place_daemon",       # short tag identifying caller
        title="FIRED — Jokic OVER 28.5",  # one-line headline (≤256 chars)
        body="kelly=2.3%  stake=$57.50",  # multi-line detail (≤4000 chars)
        fields=[                          # optional list of {name,value}
            {"name": "edge_pct", "value": "6.4%"},
            {"name": "book",     "value": "fanduel"},
        ],
    )

Returns ``True`` if the HTTP POST succeeded (or was queued to the in-memory
rate-limit bucket); ``False`` if the webhook is unconfigured (no-op),
network-failed, or spilled to the fallback file.  Never raises — callers
fire-and-forget from inside the daemon hot path.

Design rules
------------
* No-op if `DISCORD_WEBHOOK_URL` env var is unset.  Tested explicitly.
* Bucket rate-limit: 5 messages / 5 sec.  Overflow → fallback JSONL.
* `_do_post(url, payload)` is the seam for the unit tests to mock.
* stdlib only — no requests/aiohttp dependency.
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

_DEFAULT_TIMEOUT_SEC = 6
_RATE_LIMIT_BURST = 5            # 5 messages per
_RATE_LIMIT_WINDOW_SEC = 5.0     # 5-second sliding window

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FALLBACK_QUEUE = os.path.join(_PROJECT_DIR, "data", "cache", "discord_fallback_queue.jsonl")

# ---------------------------------------------------------------------------
# Rate limiter — module-level so all callers share the bucket
# ---------------------------------------------------------------------------

_RATE_LOCK = threading.Lock()
_RATE_TIMESTAMPS: deque = deque()  # monotonic seconds of recent POSTs


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
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        return True
    except Exception as exc:
        log.warning("discord fallback write failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public entry point
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
) -> bool:
    """Format and POST an alert to the configured Discord webhook.

    Returns True on success (HTTP 2xx) or graceful no-op outcomes that the
    caller doesn't need to retry; returns False on hard failure.

    Behaviour matrix
    ----------------
    * `DISCORD_WEBHOOK_URL` unset  → no-op, return False (caller sees the
       falsy return and can still rely on the vault-MD write).
    * Rate-limited                → spill payload to fallback JSONL,
       return False (so the bucket fills only with what actually flew).
    * `_do_post` returns False    → spill payload to fallback JSONL.
    * Otherwise                   → True.
    """
    url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        log.debug("DISCORD_WEBHOOK_URL unset — skipping alert (%s/%s)",
                  source, title)
        return False

    fallback = fallback_path or _FALLBACK_QUEUE
    payload = build_embed(severity, source, title, body, fields)

    if not _within_rate_limit():
        log.warning("discord webhook rate-limited — spilling to fallback")
        _spill_to_fallback(payload, reason="rate_limited", path=fallback)
        return False

    ok = _do_post(url, payload)
    if not ok:
        _spill_to_fallback(payload, reason="post_failed", path=fallback)
    return ok


__all__ = [
    "post_alert",
    "build_embed",
    "_do_post",
    "_spill_to_fallback",
    "_within_rate_limit",
    "_reset_rate_limit",
]
