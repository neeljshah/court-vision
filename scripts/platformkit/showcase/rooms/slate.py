"""Slate room builder: today's cards + yesterday's grading + paper-day units.

Source: data/frontend/best_bets.json ('cards' list), grade_summary.json,
paper_today.json. Renames edge_vs_market -> delta_vs_market on export (no
'edge' wording in public copy). Never fabricates a home/away split the source
does not carry -- keeps the raw 'matchup' string alongside SPEC-ish aliases.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..common import FRONTEND, read_json, unavailable

BEST_BETS = FRONTEND / "best_bets.json"
GRADE_SUMMARY = FRONTEND / "grade_summary.json"
PAPER_TODAY = FRONTEND / "paper_today.json"


def _file_asof(path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _map_card(card: dict, asof: str | None) -> dict:
    return {
        "event_id": card.get("game_id"),
        "sport": card.get("sport"),
        "matchup": card.get("matchup"),
        "home": None,
        "away": None,
        "start_utc": card.get("tipoff_utc"),
        "market_type": card.get("market_type"),
        "side": card.get("side"),
        "our_prob_home": card.get("model_prob"),
        "market_prob_home": card.get("market_prob"),
        "market_source": card.get("best_book"),
        "delta_vs_market": card.get("edge_vs_market"),
        "confidence": card.get("confidence"),
        "tier": card.get("tier"),
        "decision": card.get("decision"),
        "clv": card.get("clv"),
        "honest_note": card.get("honest_note"),
        "asof_utc": asof,
    }


def _build_paper_day() -> dict | None:
    day = read_json(PAPER_TODAY)
    if day is None:
        return None
    placed = day.get("placed") or []
    total_units = sum(
        float(p.get("stake_units") or p.get("flat_unit") or 0.0) for p in placed
    )
    return {
        "date": day.get("date"),
        "generated_at": day.get("generated_at"),
        "n_placed": len(placed),
        "total_stake_units": round(total_units, 4),
    }


def build() -> dict[str, Any]:
    bundle = read_json(BEST_BETS)
    if bundle is None:
        return unavailable("data/frontend/best_bets.json missing or unreadable")

    asof = _file_asof(BEST_BETS)
    cards = bundle.get("cards") or []
    slates = [_map_card(c, asof) for c in cards]

    graded = read_json(GRADE_SUMMARY)
    graded_yesterday = graded if graded is not None else {"note": "grade_summary.json missing"}

    result: dict[str, Any] = {
        "slates": slates,
        "graded_yesterday": graded_yesterday,
    }
    paper_day = _build_paper_day()
    result["paper_day"] = paper_day if paper_day is not None else {"note": "paper_today.json missing"}
    return result
