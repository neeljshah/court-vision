"""narrate.py — Deterministic, LLM-free narration backend for the brain package.

This module is the DEFAULT narration backend.  It contains ZERO LLM calls,
ZERO network calls, and NO anthropic import.

Public API
----------
    war_room_brief(summary: dict) -> str
        4-6 line structured brief from a summary dict.
    bet_narrative(pick: dict) -> str
        1-3 sentence deterministic narrative for a single bet pick.
    is_enabled() -> bool
        True iff CV_NARRATE flag is set ON.  NOTE: the *template* is always
        available as the default; CV_NARRATE gates a future optional local
        model, NOT this template engine.

Design
------
* Mirrors the structure of llm_context_layer._template_brief (but standalone).
* Every clause is optional-safe: missing keys produce a skip, never a raise.
* Pure string formatting — O(1), no I/O, no imports beyond stdlib.
* Same input dict always produces the identical output (deterministic).

honesty_class = non-prediction (zero accuracy impact by construction).
"""
from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Flag gate
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    """Return True iff CV_NARRATE is set ON.

    NOTE: The template functions in this module are always available as the
    DEFAULT narration path regardless of this flag.  CV_NARRATE gates an
    OPTIONAL future local model backend, not the template itself.
    """
    from brain.flags import is_on  # lazy, avoids circular at import time
    return is_on("CV_NARRATE")


# ---------------------------------------------------------------------------
# war_room_brief
# ---------------------------------------------------------------------------

def war_room_brief(summary: Dict[str, Any]) -> str:
    """Return a 4-6 line structured war-room brief.

    Parameters
    ----------
    summary : dict
        Expected keys (all optional-safe; missing keys are skipped gracefully):
            home            str  — home team abbreviation / name
            away            str  — away team abbreviation / name
            home_mean       float — simulated home team projected score
            away_mean       float — simulated away team projected score
            total           float — simulated combined total
            home_win_prob   float — home win probability in [0, 1]
            applied_keys    list[str] — validated pregame effect keys active
            scouting_factors list[str] — scouting-only (no marginal) factors
            risk_flags      list[str] — rare / elevated risk flags

    Returns
    -------
    str
        Deterministic multi-line brief, never empty.
    """
    home: str = str(summary.get("home") or "HOME")
    away: str = str(summary.get("away") or "AWAY")

    home_mean = summary.get("home_mean")
    away_mean = summary.get("away_mean")
    total = summary.get("total")
    home_win_prob = summary.get("home_win_prob")
    applied_keys = summary.get("applied_keys") or []
    scouting_factors = summary.get("scouting_factors") or []
    risk_flags = summary.get("risk_flags") or []

    lines: list[str] = []

    # Line 1 — venue + active effects
    if applied_keys:
        effects_str = ", ".join(str(k) for k in applied_keys)
        lines.append(
            f"{home} (home) hosts {away} — {len(applied_keys)} validated pregame "
            f"effect(s) active: {effects_str}."
        )
    else:
        lines.append(
            f"{home} (home) hosts {away} — no validated pregame effects active "
            f"(gate off or conditions unmet)."
        )

    # Line 2 — sim totals + win prob
    sim_parts: list[str] = []
    if home_mean is not None and away_mean is not None:
        sim_parts.append(
            f"{home} {float(home_mean):.0f} / {away} {float(away_mean):.0f}"
        )
    if total is not None:
        sim_parts.append(f"total {float(total):.0f}")
    if home_win_prob is not None:
        sim_parts.append(f"{home} win prob {float(home_win_prob):.1%}")
    if sim_parts:
        lines.append("Sim: " + ", ".join(sim_parts) + ".")

    # Line 3 — scouting factors (no marginal)
    if scouting_factors:
        factors_str = ", ".join(str(f) for f in scouting_factors)
        lines.append(f"Scouting-only factors (no marginal applied): {factors_str}.")
    else:
        lines.append("No scouting-only factors listed.")

    # Line 4 — risk / rare flags
    if risk_flags:
        flags_str = ", ".join(str(f) for f in risk_flags)
        lines.append(f"Risk flags: {flags_str}.")
    else:
        lines.append("No rare risk flags.")

    # Line 5 — honesty footer
    lines.append(
        "honesty_class=research; template backend (CV_NARRATE gates optional "
        "local model, NOT this template); zero LLM/network calls."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# bet_narrative
# ---------------------------------------------------------------------------

_STAT_DISPLAY: Dict[str, str] = {
    "PTS": "points",
    "REB": "rebounds",
    "AST": "assists",
    "FG3M": "three-pointers made",
    "STL": "steals",
    "BLK": "blocks",
    "TOV": "turnovers",
}


def bet_narrative(pick: Dict[str, Any]) -> str:
    """Return a 1-3 sentence deterministic narrative for a single bet pick.

    Parameters
    ----------
    pick : dict
        Expected keys (all optional-safe):
            market      str  — e.g. "player_props" or stat name
            selection   str  — e.g. "OVER" / "UNDER" or player + side
            line        float — the book's line
            edge        float — edge in units (positive = favour)
            model_prob  float — model probability in [0, 1]
            book        str  — book name, e.g. "BetMGM"

    Returns
    -------
    str
        Deterministic 1-3 sentence string, never empty.
    """
    market = str(pick.get("market") or "prop")
    selection = str(pick.get("selection") or "pick")
    line = pick.get("line")
    edge = pick.get("edge")
    model_prob = pick.get("model_prob")
    book = pick.get("book")

    # Sentence 1 — the pick
    line_str = f" {float(line):.1f}" if line is not None else ""
    sentence1 = f"Take the {selection}{line_str} ({market})."

    # Sentence 2 — model edge
    parts: list[str] = []
    if model_prob is not None:
        parts.append(f"model probability {float(model_prob):.1%}")
    if edge is not None:
        edge_val = float(edge)
        direction = "above" if edge_val >= 0 else "below"
        parts.append(f"edge {abs(edge_val):.2f} units {direction} fair value")
    sentence2 = ("Model: " + "; ".join(parts) + ".") if parts else ""

    # Sentence 3 — book / price
    sentence3 = f"Best available at {book}." if book else ""

    sentences = [s for s in [sentence1, sentence2, sentence3] if s]
    return " ".join(sentences)
