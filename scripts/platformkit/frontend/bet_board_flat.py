"""scripts.platformkit.frontend.bet_board_flat -- per-sport market flatteners.

Turns each sport's `pregame["markets"]` surface (built by predict_matchup /
the domain markets modules) into a UNIFORM list of partial bet rows:

    {"group": str, "selection": str, "model_prob": float|None, "line": float|None}

This module is PURE: no network, no predictor calls, no fabricated numbers. It
only RESHAPES an already-computed markets dict. Unknown / missing keys are simply
skipped (never guessed). fair_odds / book shopping / EV / ranking all live in the
bet_board module -- this file just emits the model's probability per selection.

INVARIANTS: never edit src/ or kernel/; reuse the domain markets; <=300 LOC; no
secrets; no $ edge claimed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

Row = Dict[str, Any]


def _row(group: str, selection: str, prob: Optional[float],
         line: Optional[float] = None) -> Row:
    p = float(prob) if isinstance(prob, (int, float)) else None
    ln = float(line) if isinstance(line, (int, float)) else None
    return {"group": group, "selection": selection, "model_prob": p, "line": ln}


def _ou_ladder(group: str, ladder: Any, label: str = "") -> List[Row]:
    """Flatten an over/under ladder ([{line,over,under}, ...]) into rows."""
    out: List[Row] = []
    for item in ladder or []:
        if not isinstance(item, dict):
            continue
        ln = item.get("line")
        pre = f"{label} " if label else ""
        if isinstance(item.get("over"), (int, float)):
            out.append(_row(group, f"{pre}Over {ln}", item.get("over"), ln))
        if isinstance(item.get("under"), (int, float)):
            out.append(_row(group, f"{pre}Under {ln}", item.get("under"), ln))
    return out


# --------------------------------------------------------------------------- #
# NBA
# --------------------------------------------------------------------------- #
def flatten_nba(m: Dict[str, Any], home: str, away: str) -> List[Row]:
    out: List[Row] = []
    ml = m.get("moneyline") or {}
    out.append(_row("Moneyline", home, ml.get("p_home_win")))
    out.append(_row("Moneyline", away, ml.get("p_away_win")))
    sm = m.get("spread_main") or {}
    if sm:
        ln = sm.get("line_home")
        out.append(_row("Spread", f"{home} {ln:+g}" if isinstance(ln, (int, float))
                        else home, sm.get("p_home_cover"), ln))
        out.append(_row("Spread", f"{away} {-ln:+g}" if isinstance(ln, (int, float))
                        else away, sm.get("p_away_cover"),
                        -ln if isinstance(ln, (int, float)) else None))
    for item in m.get("spread_ladder") or []:
        ln = item.get("line")
        out.append(_row("Spread ladder", f"{home} {ln:+g}", item.get("over"), ln))
    out += _ou_ladder("Total", m.get("total_ladder"))
    tth = m.get("team_total_home") or {}
    out += _ou_ladder("Team total", tth.get("ladder"), label=home)
    tta = m.get("team_total_away") or {}
    out += _ou_ladder("Team total", tta.get("ladder"), label=away)
    for key, grp in (("first_half", "First half"), ("q1", "1st quarter"),
                     ("q2", "2nd quarter"), ("q3", "3rd quarter"),
                     ("q4", "4th quarter")):
        pm = m.get(key) or {}
        if pm:
            out.append(_row(grp, f"{home} ML", pm.get("p_home_win")))
            out.append(_row(grp, f"{away} ML", pm.get("p_away_win")))
            tl = pm.get("total_line")
            out.append(_row(grp, f"Over {tl}", pm.get("over"), tl))
            out.append(_row(grp, f"Under {tl}", pm.get("under"), tl))
    return out


# --------------------------------------------------------------------------- #
# MLB
# --------------------------------------------------------------------------- #
def flatten_mlb(m: Dict[str, Any], home: str, away: str) -> List[Row]:
    out: List[Row] = []
    ml = m.get("moneyline") or {}
    out.append(_row("Moneyline", home, ml.get("home")))
    out.append(_row("Moneyline", away, ml.get("away")))
    rl = (m.get("run_line") or {}).get("standard") or {}
    out.append(_row("Run line", f"{home} -1.5", rl.get("home_minus_1.5"), -1.5))
    out.append(_row("Run line", f"{away} +1.5", rl.get("away_plus_1.5"), 1.5))
    out.append(_row("Run line", f"{away} -1.5", rl.get("away_minus_1.5"), -1.5))
    out.append(_row("Run line", f"{home} +1.5", rl.get("home_plus_1.5"), 1.5))
    for alt in (m.get("run_line") or {}).get("alternates") or []:
        ln = alt.get("line")
        out.append(_row("Run line alt", f"{home} -{ln}",
                        alt.get("p_home_cover_minus"), -ln if ln else None))
        out.append(_row("Run line alt", f"{away} -{ln}",
                        alt.get("p_away_cover_minus"), -ln if ln else None))
    out += _ou_ladder("Game total", m.get("game_total"))
    tt = m.get("team_totals") or {}
    out += _ou_ladder("Team total", (tt.get("home") or {}).get("lines"), label=home)
    out += _ou_ladder("Team total", (tt.get("away") or {}).get("lines"), label=away)
    f5 = m.get("first_5_innings") or {}
    if f5:
        out.append(_row("First 5 innings", f"{home} ML", f5.get("f5_ml_home_2way")))
        out.append(_row("First 5 innings", f"{away} ML", f5.get("f5_ml_away_2way")))
        out += _ou_ladder("First 5 innings", f5.get("f5_totals"))
    return out


# --------------------------------------------------------------------------- #
# Soccer (club + international share the flat 1X2 surface)
# --------------------------------------------------------------------------- #
def flatten_soccer(m: Dict[str, Any], home: str, away: str) -> List[Row]:
    out: List[Row] = []
    out.append(_row("1X2", home, m.get("1X2_home")))
    out.append(_row("1X2", "Draw", m.get("1X2_draw")))
    out.append(_row("1X2", away, m.get("1X2_away")))
    out.append(_row("Double chance", f"{home} or Draw", m.get("dc_1X")))
    out.append(_row("Double chance", f"{home} or {away}", m.get("dc_12")))
    out.append(_row("Double chance", f"Draw or {away}", m.get("dc_X2")))
    out.append(_row("Draw no bet", home, m.get("dnb_home")))
    out.append(_row("Draw no bet", away, m.get("dnb_away")))
    out.append(_row("Both teams to score", "Yes", m.get("btts_yes")))
    out.append(_row("Both teams to score", "No", m.get("btts_no")))
    for ln in (0.5, 1.5, 2.5, 3.5, 4.5):
        ov, un = m.get(f"over_{ln}"), m.get(f"under_{ln}")
        if ov is not None:
            out.append(_row("Total goals", f"Over {ln}", ov, ln))
        if un is not None:
            out.append(_row("Total goals", f"Under {ln}", un, ln))
    for side, who in (("home", home), ("away", away)):
        for ln in (0.5, 1.5, 2.5):
            ov = m.get(f"team_{side}_over_{ln}")
            if ov is not None:
                out.append(_row("Team total", f"{who} Over {ln}", ov, ln))
    for key, val in m.items():
        if key.startswith("ah_home_"):
            out.append(_row("Asian handicap", f"{home} {key[8:]}", val))
    cs = m.get("top_correct_scores")  # may live on pregame, attached by caller
    for item in cs or []:
        if isinstance(item, dict):
            out.append(_row("Correct score", str(item.get("score")),
                            item.get("prob")))
    out.append(_row("Clean sheet", f"{home} clean sheet", m.get("cs_home_clean")))
    out.append(_row("Clean sheet", f"{away} clean sheet", m.get("cs_away_clean")))
    for key, val in m.items():
        if key.startswith("wm_"):
            out.append(_row("Winning margin", key[3:].replace("_", " "), val))
    return out


# --------------------------------------------------------------------------- #
# Tennis
# --------------------------------------------------------------------------- #
def flatten_tennis(m: Dict[str, Any], p1: str, p2: str) -> List[Row]:
    out: List[Row] = []
    mw = m.get("match_winner") or {}
    out.append(_row("Match winner", p1, mw.get("p1")))
    out.append(_row("Match winner", p2, mw.get("p2")))
    for score, prob in (m.get("set_score") or {}).items():
        out.append(_row("Set score", str(score), prob))
    ts = m.get("total_sets") or {}
    if ts:
        out.append(_row("Total sets", f"Over {ts.get('line')}", ts.get("over"),
                        ts.get("line")))
        out.append(_row("Total sets", f"Under {ts.get('line')}", ts.get("under"),
                        ts.get("line")))
    for h in m.get("set_handicap") or []:
        who = p1 if h.get("side") == "p1" else p2
        out.append(_row("Set handicap", f"{who} {h.get('line'):+g}",
                        h.get("cover"), h.get("line")))
    for item in (m.get("total_games") or {}).get("ou") or []:
        ln = item.get("line")
        out.append(_row("Total games", f"Over {ln}", item.get("over"), ln))
        out.append(_row("Total games", f"Under {ln}", item.get("under"), ln))
    for h in m.get("game_handicap") or []:
        who = p1 if h.get("side") == "p1" else p2
        out.append(_row("Game handicap", f"{who} {h.get('line'):+g}",
                        h.get("cover"), h.get("line")))
    ps = m.get("per_set_winner") or {}
    out.append(_row("Per-set winner", p1, ps.get("p1")))
    out.append(_row("Per-set winner", p2, ps.get("p2")))
    return out


def flatten(sport: str, markets: Optional[Dict[str, Any]], home: str, away: str,
            extra: Optional[Dict[str, Any]] = None) -> List[Row]:
    """Dispatch to the per-sport flattener. Missing markets -> [] (no fabrication).

    *extra* lets the caller fold pregame-level keys (e.g. soccer's
    top_correct_scores) into the markets dict before flattening.
    """
    if not isinstance(markets, dict):
        return []
    m = dict(markets)
    if extra:
        for k, v in extra.items():
            m.setdefault(k, v)
    s = sport.lower()
    if s in ("nba", "wnba", "npb", "kbo"):
        # wnba/npb/kbo's markets dict only ever populates "moneyline" (see
        # predict_matchup._pregame_block) -- flatten_nba's other keys are
        # guarded .get(...) reads, so reuse gives moneyline-only rows, never
        # fabricated spread/total rows.
        return flatten_nba(m, home, away)
    if s == "mlb":
        return flatten_mlb(m, home, away)
    if s in ("soccer", "soccer_intl"):
        return flatten_soccer(m, home, away)
    if s == "tennis":
        return flatten_tennis(m, home, away)
    return []
