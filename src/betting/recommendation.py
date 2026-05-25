"""recommendation.py -- cycle 104c (loop 5).

Shared formatting helpers for recommender scripts (recommend_endQ2_bets,
compare_to_lines, recommend_pregame). Single source of truth for the
recommendation row schema + the copy-pasteable place_bet command so the
operator can tag bets with the originating strategy on a single line.
"""
from __future__ import annotations

import shlex
from typing import Dict


REQUIRED_FIELDS = ("player", "stat", "line", "side")


def format_recommendation_row(row: Dict, strategy: str) -> str:
    """One-line human-readable summary of a recommendation row.

    Tolerant of missing optional keys so endQ2 + pregame recommenders can
    share the same format string without insisting on the same schema.
    """
    missing = [k for k in REQUIRED_FIELDS if k not in row]
    if missing:
        raise ValueError(f"recommendation row missing fields: {missing}")
    player = str(row["player"])[:22]
    stat   = str(row["stat"]).upper()
    line   = float(row["line"])
    side   = str(row["side"]).upper()
    proj   = row.get("projection", row.get("model"))
    edge   = row.get("edge")
    kp     = row.get("kelly_pct", 0.0) or 0.0
    ks     = row.get("kelly_stake", 0.0) or 0.0
    ev     = row.get("ev_per_dollar", row.get("ev", 0.0)) or 0.0
    proj_s = f"{float(proj):.2f}" if proj is not None else "  -  "
    edge_s = f"{float(edge):+.2f}" if edge is not None else "  -  "
    return (
        f"  {player:<22s} {stat:<4s} L={line:>5.1f} proj={proj_s:>6s} "
        f"edge={edge_s:>6s} {side:<5s} kelly={kp:>5.2f}% (${ks:>6.2f}) "
        f"EV={ev:>+7.4f}  strategy={strategy}"
    )


def to_place_bet_command(row: Dict, strategy: str,
                         book: str = "DK", odds: int = -110) -> str:
    """Emit a copy-pasteable `python scripts/place_bet.py ...` command.

    The command includes ``--strategy <strategy>`` so the operator's bet
    is attributed to the snapshot type that surfaced it. Stakes default
    to the row's kelly_stake (rounded), falling back to $10 if absent.
    """
    missing = [k for k in REQUIRED_FIELDS if k not in row]
    if missing:
        raise ValueError(f"recommendation row missing fields: {missing}")
    player = str(row["player"])
    stat   = str(row["stat"]).lower()
    line   = float(row["line"])
    side   = str(row["side"]).upper()
    game   = str(row.get("game_id") or "")
    team   = str(row.get("team") or "")
    pid    = row.get("player_id")
    stake  = float(row.get("kelly_stake") or 10.0)
    stake  = max(round(stake, 2), 1.0)
    proj   = row.get("projection", row.get("model"))

    parts = [
        "python", "scripts/place_bet.py",
        "--game",   game or "0000000000",
        "--player", shlex.quote(player),
        "--stat",   stat,
        "--line",   f"{line}",
        "--side",   side,
        "--book",   book,
        "--odds",   str(odds),
        "--stake",  f"{stake}",
        "--strategy", strategy,
    ]
    if team:
        parts += ["--team", team]
    if pid is not None:
        parts += ["--player-id", str(pid)]
    if proj is not None:
        try:
            parts += ["--model-pred", f"{float(proj):.4f}"]
        except (TypeError, ValueError):
            pass
    kp = row.get("kelly_pct")
    if kp is not None:
        try:
            parts += ["--kelly-pct", f"{float(kp):.4f}"]
        except (TypeError, ValueError):
            pass
    return " ".join(parts)


def ensure_strategy_registered(strategy: str, bankroll: float = 1000.0,
                                max_bet_pct: float = 0.05) -> Dict:
    """If `strategy` is not in data/ab_strategies.csv, register it.

    Returns the strategy record. Imports locally so callers that don't use
    --register don't take the ab_strategy module dependency.
    """
    from src.betting import ab_strategy as AB  # noqa: PLC0415
    rows = AB.list_strategies()
    for r in rows:
        if r.get("strategy") == strategy:
            return r
    return AB.register_strategy(strategy, bankroll, max_bet_pct)
