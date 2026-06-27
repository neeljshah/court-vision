"""scripts.platformkit.paper.market_resolver -- resolve a paper prediction vs a FINAL.

grade_paper.grade_one only resolves a two-way moneyline (home/away win). The logged
paper predictions (data/frontend/paper_predictions.jsonl) span many derivative markets
(game total, run line / spread, Asian handicap, 1X2, BTTS, clean sheet, team total,
double chance, winning margin). This module resolves the subset that is FULLY
DETERMINED by the final FULL-GAME score, and EXPLICITLY DECLINES the rest.

HONESTY (binding): we NEVER fabricate a result. A market that a full-game final score
cannot decide -- any period / half / inning / quarter segment (First 5 innings, First
half, 1st quarter), or a market needing per-team realized stats we do not have -- is
returned as outcome=None (ungradable -> the bet stays OPEN). Pushes are real pushes.

resolve(group, selection, line, sport, home_team, away_team, home_score, away_score)
  -> "win" | "loss" | "push" | None   (None == cannot grade from the final score)

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_market_resolver.py -q
"""
from __future__ import annotations

import re
from typing import Optional

# Market groups a full-game final score CANNOT decide -> always ungradable (open).
_SEGMENT_GROUPS = {
    "first 5 innings", "first half", "1st quarter", "first quarter",
    "1st half", "second half", "1st period", "2nd quarter",
}


def _toks(text: str) -> str:
    """Lowercased alnum-only collapse of a label, for tolerant team-name matching."""
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def _side_of(selection: str, home_team: str, away_team: str) -> Optional[str]:
    """Which team a selection names: 'home' | 'away' | None (neither/ambiguous)."""
    sel = _toks(selection)
    h, a = _toks(home_team), _toks(away_team)
    in_h = bool(h) and h in sel
    in_a = bool(a) and a in sel
    if in_h and not in_a:
        return "home"
    if in_a and not in_h:
        return "away"
    return None


def _num_in(text: str) -> Optional[float]:
    """First signed decimal number in *text* (e.g. '-1.5', '+2', '216.5')."""
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(text))
    return float(m.group(0)) if m else None


def _ou(selection: str) -> Optional[str]:
    """'over' | 'under' | None from a selection string."""
    s = str(selection).lower()
    if "over" in s:
        return "over"
    if "under" in s:
        return "under"
    return None


def _resolve_total(total: float, line: float) -> str:
    """Over/Under push-aware resolution helper given the realized total and a line."""
    if total == line:
        return "push"
    return "over" if total > line else "under"  # caller compares to selection's o/u


def resolve(
    group: str, selection: str, line: Optional[float], sport: str,
    home_team: str, away_team: str, home_score: int, away_score: int,
) -> Optional[str]:
    """win | loss | push | None for one paper prediction given the FINAL score.

    None means "the full-game final score cannot decide this market" -> the bet is
    left OPEN (never fabricated). See module docstring for the honesty contract.
    """
    g = str(group or "").strip().lower()
    if g in _SEGMENT_GROUPS:
        return None  # period/half/inning segment -> not in the full-game final
    hs, as_ = int(home_score), int(away_score)
    total = hs + as_
    margin = hs - as_  # positive => home won by margin
    sel = str(selection or "")

    # --- Totals: Game total / Total / Total goals / Team total ---------------
    if g in ("game total", "total", "total goals", "team total"):
        ln = line if line is not None else _num_in(sel)
        ou = _ou(sel)
        if ln is None or ou is None:
            return None
        if g == "team total":
            side = _side_of(sel, home_team, away_team)
            if side is None:
                return None
            realized = hs if side == "home" else as_
        else:
            realized = total
        res = _resolve_total(float(realized), float(ln))
        if res == "push":
            return "push"
        return "win" if res == ou else "loss"

    # --- Run line / Spread / Spread ladder / Asian handicap -----------------
    if g in ("run line", "run line alt", "spread", "spread ladder", "asian handicap"):
        side = _side_of(sel, home_team, away_team)
        ln = line if line is not None else _num_in(sel)
        if side is None or ln is None:
            return None
        # Spread handicap applied to the backed side's margin.
        side_margin = margin if side == "home" else -margin
        adj = side_margin + float(ln)
        if g == "asian handicap" and float(ln) == int(ln):
            # Whole-number Asian line: an exact 0 is a push (stake refunded).
            if adj == 0:
                return "push"
        if adj == 0:
            return "push"  # exact landing on a whole spread = push
        return "win" if adj > 0 else "loss"

    # --- 1X2 straight winner (Draw, or a named team) ------------------------
    if g == "1x2":
        if sel.strip().lower() == "draw":
            return "win" if margin == 0 else "loss"
        side = _side_of(sel, home_team, away_team)
        if side is None:
            return None
        won = (margin > 0) if side == "home" else (margin < 0)
        return "win" if won else "loss"

    # --- Double chance ('X or Y' covers two of three outcomes) --------------
    if g == "double chance":
        return _resolve_double_chance(sel, home_team, away_team, margin)

    # --- Both teams to score -------------------------------------------------
    if g == "both teams to score":
        both = hs > 0 and as_ > 0
        yes = "yes" in sel.lower()
        return "win" if (yes == both) else "loss"

    # --- Clean sheet: '<team> clean sheet' wins iff opponent scored 0 -------
    if g == "clean sheet":
        side = _side_of(sel, home_team, away_team)
        if side is None:
            return None
        opp = as_ if side == "home" else hs
        return "win" if opp == 0 else "loss"

    # --- Winning margin: 'draw' / 'home by N' / 'away by N' / '<team> by N' --
    if g == "winning margin":
        return _resolve_winning_margin(sel, home_team, away_team, margin)

    return None  # any other / unknown market -> ungradable, stays open


def _resolve_double_chance(
    sel: str, home_team: str, away_team: str, margin: int
) -> Optional[str]:
    """Double chance 'A or B' covers two of {home win, draw, away win}.

    Selections are team-named, e.g. 'Austria or Draw', 'Austria or Jordan'. We test
    each of the (up to two) named outcomes against the realized result.
    """
    s = sel.lower()
    home_won, draw, away_won = margin > 0, margin == 0, margin < 0
    covers_draw = "draw" in s
    sel_h = _toks(home_team)
    sel_a = _toks(away_team)
    covers_home = bool(sel_h) and sel_h in _toks(sel)
    covers_away = bool(sel_a) and sel_a in _toks(sel)
    if not (covers_draw or covers_home or covers_away):
        return None
    won = (covers_draw and draw) or (covers_home and home_won) or \
          (covers_away and away_won)
    return "win" if won else "loss"


def _resolve_winning_margin(
    sel: str, home_team: str, away_team: str, margin: int
) -> Optional[str]:
    """Resolve a 'winning margin' selection: draw / home by N / away by N / team by N."""
    s = sel.strip().lower()
    if "draw" in s:
        return "win" if margin == 0 else "loss"
    n = _num_in(s)
    if n is None:
        return None
    side = None
    if "home" in s:
        side = "home"
    elif "away" in s:
        side = "away"
    else:
        side = _side_of(sel, home_team, away_team)
    if side is None:
        return None
    realized = margin if side == "home" else -margin
    return "win" if realized == int(n) else "loss"


__all__ = ["resolve"]
