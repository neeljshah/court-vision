"""alert_dedup.py — smart alert filtering for Live Engine v2.

Operator wants 5 great alerts an hour, not 200 noisy ones. This
module wraps every potential alert with:

  * cooldown — same (player, stat, side) suppressed for 5 min
  * delta threshold — drop if projection moved < 0.3 stat units
  * severity tiers — high / medium / low (matches webhook_alerts)
  * digest bundling — alerts within a 60s window flush as one
    multi-line message instead of N individual posts

Each ``maybe_alert(...)`` call returns ONE of:

  ("emit",     formatted_str, severity)   — fire it now
  ("digest",   accumulator_id, None)      — added to pending digest
  ("drop",     reason, None)              — suppressed

For digest flushing the caller polls ``pending_digests()`` every
loop tick.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("alert_dedup")

COOLDOWN_SEC_DEFAULT = 300.0          # 5 min
DELTA_FLOOR_DEFAULT = 0.3             # stat units
DIGEST_WINDOW_SEC_DEFAULT = 60.0      # bundle window


@dataclass
class _DigestBucket:
    opened_at: float
    severity: str
    lines: List[str] = field(default_factory=list)


class AlertDedup:
    """Cooldown + delta-floor + severity gating + digest bundling."""

    def __init__(self, *,
                 cooldown_sec: float = COOLDOWN_SEC_DEFAULT,
                 delta_floor: float = DELTA_FLOOR_DEFAULT,
                 digest_window_sec: float = DIGEST_WINDOW_SEC_DEFAULT,
                 min_severity: str = "low") -> None:
        self.cooldown_sec = cooldown_sec
        self.delta_floor = delta_floor
        self.digest_window_sec = digest_window_sec
        self.min_severity = min_severity.lower()
        # Last-emit timestamp per dedupe key.
        self._last_emit: Dict[Tuple[str, str, str], float] = {}
        # Per-severity open digest bucket — we flush + replace when window passes.
        self._digest: Dict[str, _DigestBucket] = {}
        # Recent emits for diagnostics.
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=64)

    # ── public API ──────────────────────────────────────────────────
    def maybe_alert(self, *, player: str, stat: str, side: str,
                    line: float, book: str, odds: int,
                    projection_old: Optional[float],
                    projection_new: float, ev_new: float,
                    ev_old: Optional[float] = None,
                    severity: str = "medium") -> Tuple[str, Any, Optional[str]]:
        """Decide what to do with a single candidate alert.

        Returns ``(action, payload, severity)`` where action is one of
        ``"emit" | "digest" | "drop"``.
        """
        severity = (severity or "medium").lower()
        if not self._meets_min_severity(severity):
            return "drop", "below_min_severity", None

        key = (player.lower(), stat.lower(), side.lower())
        now = time.time()

        # Delta gate — drop if projection barely moved.
        if projection_old is not None:
            delta = abs(projection_new - projection_old)
            if delta < self.delta_floor:
                return "drop", "delta_below_floor", None

        # Cooldown gate.
        last = self._last_emit.get(key)
        if last is not None and (now - last) < self.cooldown_sec:
            # Cooldown active — funnel into the digest bucket.
            line_str = self._format_line(
                player=player, stat=stat, side=side, line=line,
                book=book, odds=odds,
                projection_old=projection_old, projection_new=projection_new,
                ev_new=ev_new, ev_old=ev_old, severity=severity,
            )
            bucket = self._digest.get(severity)
            if bucket is None or (now - bucket.opened_at) > self.digest_window_sec:
                bucket = _DigestBucket(opened_at=now, severity=severity)
                self._digest[severity] = bucket
            bucket.lines.append(line_str)
            return "digest", severity, None

        # Cleared all gates — emit immediately.
        self._last_emit[key] = now
        formatted = self._format_line(
            player=player, stat=stat, side=side, line=line, book=book,
            odds=odds, projection_old=projection_old,
            projection_new=projection_new, ev_new=ev_new, ev_old=ev_old,
            severity=severity,
        )
        self._recent.append({"ts": now, "severity": severity, "msg": formatted})
        return "emit", formatted, severity

    def pending_digests(self) -> List[Tuple[str, str]]:
        """Return + clear any digests whose window has elapsed.

        Output is a list of ``(severity, body)``.
        """
        now = time.time()
        out: List[Tuple[str, str]] = []
        for sev in list(self._digest.keys()):
            bucket = self._digest[sev]
            if (now - bucket.opened_at) < self.digest_window_sec:
                continue
            if not bucket.lines:
                del self._digest[sev]
                continue
            n = len(bucket.lines)
            body = f"[DIGEST {sev.upper()}] {n} alert(s) in last 60s:\n" + \
                "\n".join(bucket.lines)
            out.append((sev, body))
            del self._digest[sev]
        return out

    def flush_all(self) -> List[Tuple[str, str]]:
        """Force-flush every open digest immediately. For shutdown."""
        out: List[Tuple[str, str]] = []
        for sev, bucket in self._digest.items():
            if not bucket.lines:
                continue
            body = f"[DIGEST {sev.upper()}] {len(bucket.lines)} alert(s):\n" + \
                "\n".join(bucket.lines)
            out.append((sev, body))
        self._digest.clear()
        return out

    def recent(self) -> List[Dict[str, Any]]:
        """Last ~64 fired alerts (for the dashboard alerts pane)."""
        return list(self._recent)

    # ── internals ───────────────────────────────────────────────────
    _SEV_RANK = {"low": 0, "info": 0, "medium": 1, "high": 2}

    def _meets_min_severity(self, severity: str) -> bool:
        return self._SEV_RANK.get(severity, 0) >= \
               self._SEV_RANK.get(self.min_severity, 0)

    @staticmethod
    def _format_line(*, player: str, stat: str, side: str, line: float,
                     book: str, odds: int, projection_old: Optional[float],
                     projection_new: float, ev_new: float,
                     ev_old: Optional[float], severity: str) -> str:
        sev_tag = severity.upper()
        proj_part = (f"{projection_old:.1f}→{projection_new:.1f} "
                     f"(Δ{projection_new - projection_old:+.1f})"
                     if projection_old is not None
                     else f"{projection_new:.1f}")
        ev_part = (f"EV {ev_new*100:+.1f}% (was {ev_old*100:+.1f}%)"
                   if ev_old is not None else f"EV {ev_new*100:+.1f}%")
        # Reason inferred from delta direction.
        reason = "PROJ_UP" if (projection_old is not None and
                               projection_new > projection_old) else "PROJ_DOWN"
        if projection_old is None:
            reason = "NEW_EDGE"
        return (
            f"[{sev_tag}][{reason}] {player} {stat.upper()} "
            f"{side.upper()} {line} @ {book} {odds:+d} — "
            f"projection {proj_part} — {ev_part}"
        )
