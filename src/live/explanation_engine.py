"""explanation_engine.py — turn raw events into human-readable "why" strings.

Inputs are the same dicts that already flow over the Live Engine v2
event bus; this module enriches them with 4 categories of context:

  1. recent PBP context        (foul, made-shot, sub trail in last ~3 plays)
  2. line movement context     (recent line + odds drift across books)
  3. projection source path    (which models fired, in what order)
  4. foul / minute pressure    (foul trouble, learned vs heuristic minutes)

The output is a structured dict — UI consumers pick which categories
to show. There is no I/O here; the engine takes everything it needs
as constructor args / kwargs, so it's easy to test and to call from
both terminal and web UIs.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("explanation_engine")


# ── data classes ────────────────────────────────────────────────────────
@dataclass
class PBPCrumb:
    """One PBP event remembered for explanation context."""
    ts: float
    period: Any
    clock: Any
    topic: str
    description: str
    player_id: Optional[int]
    player_name: Optional[str]
    team_tricode: Optional[str]


@dataclass
class LineTick:
    """One line observation per (book, player_id, stat)."""
    ts: float
    book: str
    line: float
    over_price: int
    under_price: int


# ── engine ──────────────────────────────────────────────────────────────
class ExplanationEngine:
    """Aggregates PBP + line + projection metadata; renders 'why' strings.

    Designed to be a singleton inside the orchestrator. Stores rolling
    buffers, indexes by (game_id, player_id, stat). All buffers are
    bounded so memory stays flat over long games.
    """

    def __init__(self, *, pbp_window: int = 24, line_window: int = 16) -> None:
        # Per-game PBP trail. Bounded ring.
        self._pbp: Dict[str, Deque[PBPCrumb]] = {}
        # Per-(game_id, player_id, stat) → per-book → recent ticks.
        self._lines: Dict[Tuple[str, Any, str], Dict[str, Deque[LineTick]]] = {}
        self.pbp_window = pbp_window
        self.line_window = line_window

    # ── ingest ──────────────────────────────────────────────────────
    def ingest_pbp(self, event: Dict[str, Any]) -> None:
        gid = event.get("game_id") or "unknown"
        buf = self._pbp.setdefault(gid, deque(maxlen=self.pbp_window))
        buf.append(PBPCrumb(
            ts=event.get("ts") or _now(),
            period=event.get("period"), clock=event.get("clock"),
            topic=str(event.get("topic") or event.get("action_type") or ""),
            description=str(event.get("description") or ""),
            player_id=_safe_int(event.get("player_id")),
            player_name=event.get("player_name"),
            team_tricode=event.get("team_tricode"),
        ))

    def ingest_line_tick(self, *, game_id: str, player_id: Any, stat: str,
                         book: str, line: float, over_price: int,
                         under_price: int, ts: Optional[float] = None) -> None:
        key = (game_id, player_id, (stat or "").lower())
        per_book = self._lines.setdefault(key, {})
        ticks = per_book.setdefault(book, deque(maxlen=self.line_window))
        ticks.append(LineTick(
            ts=ts or _now(), book=book, line=float(line),
            over_price=int(over_price), under_price=int(under_price),
        ))

    # ── explain ─────────────────────────────────────────────────────
    def explain_bet(self, bet: Dict[str, Any],
                    snapshot: Optional[Dict[str, Any]] = None,
                    projection_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a full multi-section explanation for a single bet.

        Parameters
        ----------
        bet : dict
            The ``bet.recommended`` event payload.
        snapshot : dict, optional
            The current snapshot for this game — used for foul/minute pressure.
        projection_row : dict, optional
            The matching projection row — has projection_source,
            matchup_reason, foul_factor, blow_factor, heat_check_shrinkage.

        Returns
        -------
        dict
            ``{
                "summary": str,
                "sections": [
                    {"kind": "...", "title": "...", "body": "..."},
                    ...
                ]
            }``
        """
        sections: List[Dict[str, str]] = []

        proj_section = self._render_projection_path(bet, projection_row)
        if proj_section:
            sections.append(proj_section)

        pbp_section = self._render_pbp_context(bet)
        if pbp_section:
            sections.append(pbp_section)

        line_section = self._render_line_movement(bet)
        if line_section:
            sections.append(line_section)

        foul_section = self._render_foul_pressure(bet, snapshot, projection_row)
        if foul_section:
            sections.append(foul_section)

        return {
            "summary": self._render_summary(bet, sections),
            "sections": sections,
        }

    # ── section renderers ───────────────────────────────────────────
    @staticmethod
    def _render_projection_path(bet: Dict[str, Any],
                                row: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
        if row is None:
            row = {}
        src = str(row.get("projection_source") or "")
        if not src:
            return None
        # Pretty-format the model chain.
        legs = [leg.strip() for leg in src.split("+") if leg.strip()]
        chain = " → ".join(_pretty_model_name(leg) for leg in legs)
        details: List[str] = []
        if row.get("foul_factor") not in (None, 1.0):
            details.append(f"foul_factor={row.get('foul_factor'):.2f}")
        if row.get("blow_factor") not in (None, 1.0):
            details.append(f"blow_factor={row.get('blow_factor'):.2f}")
        if row.get("heat_check_shrinkage") not in (None, 1.0):
            details.append(f"heat_check={row.get('heat_check_shrinkage'):.2f}x")
        if row.get("matchup_reason") and str(row["matchup_reason"]).startswith(
                "matchup_applied"):
            details.append(str(row["matchup_reason"]))
        suffix = (" — " + ", ".join(details)) if details else ""
        return {
            "kind": "projection_path",
            "title": "Projection source",
            "body": f"{chain}{suffix}",
        }

    def _render_pbp_context(self, bet: Dict[str, Any]) -> Optional[Dict[str, str]]:
        gid = bet.get("game_id")
        pid = _safe_int(bet.get("player_id"))
        if not gid:
            return None
        crumbs = list(self._pbp.get(gid, deque()))
        if not crumbs:
            return None
        # Take last ~3 events. If we have a player_id, prioritize their events.
        focus = [c for c in crumbs[-8:] if pid is None or c.player_id == pid]
        if not focus:
            focus = crumbs[-3:]
        else:
            focus = focus[-3:]
        if not focus:
            return None
        lines = []
        for c in focus:
            who = c.player_name or "?"
            tag = c.topic.replace("pbp.", "")
            lines.append(f"  Q{c.period} {c.clock} — {tag} ({who})")
        return {
            "kind": "pbp_context",
            "title": f"Last {len(focus)} play(s)",
            "body": "\n".join(lines),
        }

    def _render_line_movement(self, bet: Dict[str, Any]) -> Optional[Dict[str, str]]:
        gid = bet.get("game_id")
        pid = bet.get("player_id")
        stat = (bet.get("stat") or "").lower()
        key = (gid, pid, stat)
        per_book = self._lines.get(key) or {}
        if not per_book:
            return None
        lines = []
        # Sort books for deterministic output.
        for book in sorted(per_book.keys()):
            ticks = list(per_book[book])
            if not ticks:
                continue
            first, last = ticks[0], ticks[-1]
            drift = last.line - first.line
            arrow = "↑" if drift > 0 else ("↓" if drift < 0 else "→")
            age_s = max(0, int(last.ts - first.ts))
            lines.append(
                f"  {book}: {first.line} {arrow} {last.line} "
                f"({drift:+.1f} in {age_s}s, last O{last.over_price:+d}/U{last.under_price:+d})")
        # Cross-book max spread (arb / middle signal).
        latest = {b: list(t)[-1].line for b, t in per_book.items() if t}
        if len(latest) >= 2:
            spread = max(latest.values()) - min(latest.values())
            if spread >= 0.5:
                lines.append(f"  spread across books: {spread:+.1f} — possible middle window")
        return {
            "kind": "line_movement",
            "title": "Line movement",
            "body": "\n".join(lines),
        }

    @staticmethod
    def _render_foul_pressure(bet: Dict[str, Any],
                              snapshot: Optional[Dict[str, Any]],
                              row: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
        pid = _safe_int(bet.get("player_id"))
        if snapshot is None or pid is None:
            return None
        # Locate the player.
        player = None
        for p in snapshot.get("players") or []:
            if _safe_int(p.get("player_id")) == pid:
                player = p
                break
        if player is None:
            return None
        pf = _safe_int(player.get("pf")) or 0
        cur_min = _safe_float(player.get("min")) or 0.0
        period = snapshot.get("period")
        clock = snapshot.get("clock")
        lines: List[str] = []
        # Foul-trouble call-out
        pressure = None
        if pf >= 5:
            pressure = "foul-out risk imminent"
        elif pf == 4 and (period or 0) <= 4:
            pressure = "one away from foul-out"
        elif pf >= 3 and (period or 0) <= 3:
            pressure = "early foul trouble"
        if pressure:
            lines.append(f"  {player.get('name', '?')} on {pf} PF — {pressure}")
        lines.append(f"  through {cur_min:.0f} min, period={period}, clock={clock}")
        if row and (row.get("projection_source") or "").startswith(
                "learned_q4_minutes"):
            lines.append("  learned_q4_minutes active (replaces heuristic foul_factor)")
        return {
            "kind": "foul_pressure",
            "title": "Foul / minute pressure",
            "body": "\n".join(lines),
        } if lines else None

    @staticmethod
    def _render_summary(bet: Dict[str, Any],
                        sections: List[Dict[str, str]]) -> str:
        side = (bet.get("side") or "").upper()
        stat = (bet.get("stat") or "").upper()
        ev = bet.get("ev") or 0.0
        kelly = bet.get("kelly") or 0.0
        # Pick the loudest section as the headline (projection source first).
        return (
            f"{bet.get('name', bet.get('player_id') or '?')} "
            f"{stat} {side} {bet.get('line')} @ {bet.get('book')} "
            f"{bet.get('odds', 0):+d} | "
            f"proj {bet.get('projected_final', '?')} "
            f"(EV {ev*100:+.1f}%, K {kelly*100:.1f}%) | "
            f"{len(sections)} reason(s)"
        )


# ── helpers ─────────────────────────────────────────────────────────────
_MODEL_NAMES = {
    "cycle_88_linear": "pace-extrapolation",
    "endQ1_head": "endQ1 LightGBM head",
    "endQ2_head": "endQ2 LightGBM head",
    "learned_q4_minutes_v1": "learned Q4 minutes",
    "residual_head": "endQ3 residual head",
    "residual_head_endq2": "endQ2 residual head",
    "defender_matchup": "defender matchup",
    "foul_residual": "foul residual",
    "blowout_residual": "blowout residual",
    "heat_check": "heat-check shrinkage",
}


def _pretty_model_name(name: str) -> str:
    return _MODEL_NAMES.get(name, name)


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _now() -> float:
    import time
    return time.time()
