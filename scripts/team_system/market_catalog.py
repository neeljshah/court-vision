"""Market catalog for the paper sportsbook engine (V7, gated CV_SPORTSBOOK_ENGINE).

Prices the full book menu from one coherent possession sim result — singles O/U, combo O/U,
milestone ladders, exotics (DD/TD), alt-lines, team totals, spreads, moneylines, and game totals.
Pure function of a GameSimResult + optional paper_lines dict. No real-money path.

PAPER pricing only -- no real-money path. Playoffs have NO proven edge.
ROI requires real captured prices + proven forward CLV.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

# Mirror prop_engine.py sys.path bootstrap (lines 16-17)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from prop_engine import _combos, _qline, SINGLES, MILESTONES, LABEL  # noqa: E402
from prediction.betting_portfolio import _american_to_prob            # noqa: E402

__all__ = ["MARKET_ONTOLOGY", "ontology_count", "price_markets", "fair_american", "devig_two_way"]

_HONESTY = "PAPER pricing only -- no real-money path. Playoffs have NO proven edge. ROI requires real captured prices + proven forward CLV."

# ---------------------------------------------------------------------------
# MARKET ONTOLOGY — exhaustive type catalogue (64 distinct types)
# ---------------------------------------------------------------------------
MARKET_ONTOLOGY: List[Dict] = []

# 13 single O/U
for _s in SINGLES:
    MARKET_ONTOLOGY.append({"category": "single_ou", "stat": _s, "kind": "single_ou", "lines": None})

# 5 combo O/U
for _c in ["pra", "pr", "pa", "ra", "stocks"]:
    MARKET_ONTOLOGY.append({"category": "combo_ou", "stat": _c, "kind": "combo_ou", "lines": None})

# 29 milestone lines across MILESTONES dict
for _ms, _ls in MILESTONES.items():
    for _ml in _ls:
        MARKET_ONTOLOGY.append({"category": "milestone", "stat": _ms, "kind": "milestone", "lines": [_ml]})

# 2 exotics: DD and TD
MARKET_ONTOLOGY.append({"category": "exotic", "stat": None, "kind": "exotic", "lines": None, "exotic": "double_double"})
MARKET_ONTOLOGY.append({"category": "exotic", "stat": None, "kind": "exotic", "lines": None, "exotic": "triple_double"})

# 10 alt-line types: pts/reb/ast/fg3m/pra — each has a q10-based and q90-based alt line
for _as in ["pts", "reb", "ast", "fg3m", "pra"]:
    MARKET_ONTOLOGY.append({"category": "altline", "stat": _as, "kind": "altline", "lines": ["q10"]})
    MARKET_ONTOLOGY.append({"category": "altline", "stat": _as, "kind": "altline", "lines": ["q90"]})

# 3 team market types
MARKET_ONTOLOGY.append({"category": "team", "stat": "team_total", "kind": "team", "lines": None})
MARKET_ONTOLOGY.append({"category": "team", "stat": "spread",     "kind": "team", "lines": None})
MARKET_ONTOLOGY.append({"category": "team", "stat": "moneyline",  "kind": "team", "lines": None})

# 2 game market types
MARKET_ONTOLOGY.append({"category": "game", "stat": "game_total",        "kind": "game", "lines": None})
MARKET_ONTOLOGY.append({"category": "game", "stat": "game_total_ou_2",   "kind": "game", "lines": None})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fair_american(p: float) -> int:
    """Fair probability (no vig) -> American odds integer."""
    p = float(np.clip(p, 1e-4, 0.9999))
    if p >= 0.5:
        return -round(100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def devig_two_way(over_odds: int, under_odds: int) -> Tuple[float, float]:
    """Remove the vig from a two-way market. Returns (no-vig over prob, no-vig under prob)."""
    po = _american_to_prob(over_odds)
    pu = _american_to_prob(under_odds)
    total = po + pu
    return po / total, pu / total


def _payout(odds: int) -> float:
    """Net profit per $1 staked at American odds."""
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


def _paper_lookup(paper_lines: Optional[Dict], key: str) -> Optional[Dict]:
    if paper_lines is None:
        return None
    return paper_lines.get(key)


def _book_fields(
    entity: str,
    market_type: str,
    side: str,
    line: Optional[float],
    paper_lines: Optional[Dict],
) -> Dict:
    """Resolve book_line, book_odds, book_prob, edge, ev from paper_lines."""
    out: Dict = {"book_line": None, "book_odds": None, "book_prob": None, "edge": None, "ev": None}
    if paper_lines is None:
        return out

    # Try two-way key first: "{entity}|{market_type}" -> {line, over_odds, under_odds}
    two_key = f"{entity}|{market_type}"
    two = _paper_lookup(paper_lines, two_key)
    if two and "over_odds" in two and "under_odds" in two:
        out["book_line"] = float(two.get("line", line) or line)
        if side == "over":
            out["book_odds"] = int(two["over_odds"])
            dvo, _ = devig_two_way(two["over_odds"], two["under_odds"])
            out["book_prob"] = dvo
        elif side == "under":
            out["book_odds"] = int(two["under_odds"])
            _, dvu = devig_two_way(two["over_odds"], two["under_odds"])
            out["book_prob"] = dvu
        # 'yes' side: treat over_odds as the yes odds
        else:
            out["book_odds"] = int(two.get("yes_odds", two["over_odds"]))
            out["book_prob"] = _american_to_prob(out["book_odds"])
        return out

    # Try one-sided key: "{entity}|{market_type}|{side}"
    one_key = f"{entity}|{market_type}|{side}"
    one = _paper_lookup(paper_lines, one_key)
    if one:
        out["book_line"] = float(one.get("line", line) or line)
        out["book_odds"] = int(one["odds"])
        out["book_prob"] = _american_to_prob(out["book_odds"])

    return out


def _finalize_ev(row: Dict) -> Dict:
    """Add edge and ev once model_prob and book fields are populated."""
    if row.get("book_prob") is not None and row.get("book_odds") is not None:
        row["edge"] = row["model_prob"] - row["book_prob"]
        row["ev"] = row["model_prob"] * _payout(row["book_odds"]) - (1.0 - row["model_prob"])
    return row


def _model_prob_at_book_line(
    arr: np.ndarray,
    side: str,
    book_line: Optional[float],
    fair_line: float,
) -> float:
    """Return model probability evaluated at the supplied book line (apples-to-apples).

    When a real book line is supplied we evaluate P(stat vs book_line) directly from
    the joint samples so that edge = model_prob(at book line) - devig_implied(at book line).
    When no book line is supplied (None) we fall back to the fair sim-median line so the
    function is backward-compatible.

    For OVER:  P(stat > book_line)
    For UNDER: P(stat < book_line)
    For YES milestone / exotic (side == "yes"): P(stat >= book_line)
    """
    line = book_line if book_line is not None else fair_line
    if side == "over":
        return float((arr > line).mean())
    if side == "under":
        return float((arr < line).mean())
    # "yes" (milestones, exotics — arr already is the boolean/count array passed in)
    return float((arr >= line).mean())


# ---------------------------------------------------------------------------
# ontology_count
# ---------------------------------------------------------------------------

def ontology_count(result) -> int:
    """Return the number of concrete priced markets that price_markets(result) would emit.

    Expands the ontology over the rotation players + 2 teams. Guaranteed >=100 for any
    normal 2-team rotation (singles alone = 13 types x 2 sides x ~20+ players = 520+).
    """
    rotation = [
        pid for pid, d in result.players.items()
        if float(np.median(d["samples"]["pts"])) >= 6.0
    ]
    n = len(rotation)
    # singles: 13 types x 2 sides x n players
    c = 13 * 2 * n
    # combos: 5 types x 2 sides x n players
    c += 5 * 2 * n
    # milestones: 29 (line, stat) pairs x n players (some degenerate — count all, filter later)
    total_ms = sum(len(v) for v in MILESTONES.values())  # 29
    c += total_ms * n
    # exotics: 2 x n players
    c += 2 * n
    # alt-lines: 5 stats x 2 quantile levels x 2 sides x n players
    c += 5 * 2 * 2 * n
    # team markets: 2 teams x (team_total_over + team_total_under + spread_over + spread_under) + 2 moneylines
    c += 2 * 4 + 2
    # game markets: game_total_over + game_total_under + variant_over + variant_under
    c += 4
    return c


# ---------------------------------------------------------------------------
# price_markets — THE main entry point
# ---------------------------------------------------------------------------

def price_markets(
    result,
    paper_lines: Optional[Dict[str, Dict]] = None,
    *,
    min_players_pts: float = 6.0,
) -> List[Dict]:
    """Price every market in the ontology from the sim result samples.

    Returns a list of dicts with keys:
        market_type, entity, entity_name, stat, line, side,
        model_prob, fair_american,
        book_line, book_odds, book_prob, edge, ev,
        honesty_class ("paper").

    paper_lines key convention (frozen):
        "{entity}|{market_type}" -> {"line":float,"over_odds":int,"under_odds":int}
        "{entity}|{market_type}|{side}" -> {"line":float,"odds":int}
    """
    markets: List[Dict] = []

    # --- rotation filter ---
    rotation = [
        pid for pid, d in result.players.items()
        if float(np.median(d["samples"]["pts"])) >= min_players_pts
    ]

    # --- per-player markets ---
    for pid in rotation:
        d = result.players[pid]
        name = d["name"]
        team = d["team"]
        entity = str(pid)
        s = {k: np.asarray(v, float) for k, v in d["samples"].items()}
        c = _combos(s)  # all single + combo arrays

        # -- SINGLES O/U --
        for stat in SINGLES:
            arr = c[stat]
            fair_line = _qline(arr)
            for side in ("over", "under"):
                mtype = f"{stat}_ou"
                bk = _book_fields(entity, mtype, side, fair_line, paper_lines)
                # Evaluate model_prob at the BOOK line when supplied (apples-to-apples).
                mp = _model_prob_at_book_line(arr, side, bk["book_line"], fair_line)
                fa = fair_american(mp)
                line = bk["book_line"] if bk["book_line"] is not None else fair_line
                bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
                bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
                markets.append({
                    "market_type": mtype, "entity": entity, "entity_name": name,
                    "stat": stat, "line": line, "side": side,
                    "model_prob": mp, "fair_american": fa,
                    **bk, "honesty_class": "paper",
                })

        # -- COMBOS O/U --
        for stat in ["pra", "pr", "pa", "ra", "stocks"]:
            arr = c[stat]
            fair_line = _qline(arr)
            for side in ("over", "under"):
                mtype = f"{stat}_ou"
                bk = _book_fields(entity, mtype, side, fair_line, paper_lines)
                # Evaluate model_prob at the BOOK line when supplied (apples-to-apples).
                mp = _model_prob_at_book_line(arr, side, bk["book_line"], fair_line)
                fa = fair_american(mp)
                line = bk["book_line"] if bk["book_line"] is not None else fair_line
                bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
                bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
                markets.append({
                    "market_type": mtype, "entity": entity, "entity_name": name,
                    "stat": stat, "line": line, "side": side,
                    "model_prob": mp, "fair_american": fa,
                    **bk, "honesty_class": "paper",
                })

        # -- MILESTONES X+ --
        for ms_stat, ms_lines in MILESTONES.items():
            arr = c[ms_stat]
            med = float(np.median(arr))
            for ms_line in ms_lines:
                if ms_line > med * 2.5:
                    continue  # degenerate — prob near 0 for this player
                fair_line = float(ms_line)
                mtype = f"{ms_stat}_milestone"
                bk = _book_fields(entity, f"{mtype}_{ms_line}", "yes", fair_line, paper_lines)
                # For milestones, use book_line if supplied; otherwise the nominal ms_line.
                # Re-evaluated as >= threshold (milestone convention).
                eff_line = bk["book_line"] if bk["book_line"] is not None else fair_line
                mp = float((arr >= eff_line).mean())
                fa = fair_american(mp)
                bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
                bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
                markets.append({
                    "market_type": mtype, "entity": entity, "entity_name": name,
                    "stat": ms_stat, "line": eff_line, "side": "yes",
                    "model_prob": mp, "fair_american": fa,
                    **bk, "honesty_class": "paper",
                })

        # -- EXOTICS: double-double, triple-double --
        cnt = (s["pts"] >= 10).astype(int) + (s["reb"] >= 10).astype(int) + (s["ast"] >= 10).astype(int)
        for mtype, threshold in [("double_double", 2), ("triple_double", 3)]:
            mp = float((cnt >= threshold).mean())
            fa = fair_american(mp)
            bk = _book_fields(entity, mtype, "yes", None, paper_lines)
            bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
            bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
            markets.append({
                "market_type": mtype, "entity": entity, "entity_name": name,
                "stat": "pts_reb_ast", "line": None, "side": "yes",
                "model_prob": mp, "fair_american": fa,
                **bk, "honesty_class": "paper",
            })

        # -- ALT-LINES: q10-based and q90-based alt lines for pts/reb/ast/fg3m/pra --
        for alt_stat in ["pts", "reb", "ast", "fg3m", "pra"]:
            arr = c[alt_stat]
            q10_line = round(float(np.quantile(arr, 0.10)) * 2) / 2
            q90_line = round(float(np.quantile(arr, 0.90)) * 2) / 2
            for fair_alt_line, tag in [(q10_line, "q10"), (q90_line, "q90")]:
                for side in ("over", "under"):
                    mtype = f"{alt_stat}_alt"
                    bk = _book_fields(entity, f"{mtype}_{tag}_{side}", side, fair_alt_line, paper_lines)
                    # Evaluate model_prob at the BOOK line when supplied (apples-to-apples).
                    mp = _model_prob_at_book_line(arr, side, bk["book_line"], fair_alt_line)
                    fa = fair_american(mp)
                    line = bk["book_line"] if bk["book_line"] is not None else fair_alt_line
                    bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
                    bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
                    markets.append({
                        "market_type": mtype, "entity": entity, "entity_name": name,
                        "stat": alt_stat, "line": line, "side": side,
                        "model_prob": mp, "fair_american": fa,
                        **bk, "honesty_class": "paper",
                    })

    # --- TEAM markets ---
    home_tri = result.home_tri
    away_tri = result.away_tri
    home_total = np.asarray(result.home_total, float)
    away_total = np.asarray(result.away_total, float)
    margin = home_total - away_total

    for tri, arr in [(home_tri, home_total), (away_tri, away_total)]:
        fair_line = _qline(arr)
        for side in ("over", "under"):
            mtype = "team_total"
            bk = _book_fields(tri, mtype, side, fair_line, paper_lines)
            mp = _model_prob_at_book_line(arr, side, bk["book_line"], fair_line)
            fa = fair_american(mp)
            line = bk["book_line"] if bk["book_line"] is not None else fair_line
            bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
            bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
            markets.append({
                "market_type": mtype, "entity": tri, "entity_name": tri,
                "stat": "team_total", "line": line, "side": side,
                "model_prob": mp, "fair_american": fa,
                **bk, "honesty_class": "paper",
            })

    # Spread (margin O/U)
    fair_spread = _qline(margin)
    for side in ("over", "under"):
        mtype = "spread"
        bk = _book_fields(home_tri, mtype, side, fair_spread, paper_lines)
        mp = _model_prob_at_book_line(margin, side, bk["book_line"], fair_spread)
        fa = fair_american(mp)
        spread_line = bk["book_line"] if bk["book_line"] is not None else fair_spread
        bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
        bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
        markets.append({
            "market_type": mtype, "entity": home_tri, "entity_name": home_tri,
            "stat": "margin", "line": spread_line, "side": side,
            "model_prob": mp, "fair_american": fa,
            **bk, "honesty_class": "paper",
        })

    # Moneylines
    hwp = float(result.home_win_prob)
    awp = 1.0 - hwp
    for tri, wp in [(home_tri, hwp), (away_tri, awp)]:
        fa = fair_american(wp)
        mtype = "moneyline"
        bk = _book_fields(tri, mtype, "yes", None, paper_lines)
        bk["edge"] = wp - bk["book_prob"] if bk["book_prob"] is not None else None
        bk["ev"] = (wp * _payout(bk["book_odds"]) - (1.0 - wp)) if bk["book_odds"] is not None else None
        markets.append({
            "market_type": mtype, "entity": tri, "entity_name": tri,
            "stat": "win", "line": None, "side": "yes",
            "model_prob": wp, "fair_american": fa,
            **bk, "honesty_class": "paper",
        })

    # --- GAME markets ---
    game_total = home_total + away_total
    fair_gt = _qline(game_total)
    for side in ("over", "under"):
        mtype = "game_total"
        bk = _book_fields("GAME", mtype, side, fair_gt, paper_lines)
        mp = _model_prob_at_book_line(game_total, side, bk["book_line"], fair_gt)
        fa = fair_american(mp)
        gt_line = bk["book_line"] if bk["book_line"] is not None else fair_gt
        bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
        bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
        markets.append({
            "market_type": mtype, "entity": "GAME", "entity_name": f"{away_tri}@{home_tri}",
            "stat": "game_total", "line": gt_line, "side": side,
            "model_prob": mp, "fair_american": fa,
            **bk, "honesty_class": "paper",
        })

    # Game total band variant (margin absolute value — exotic)
    margin_abs = np.abs(margin)
    fair_band = _qline(margin_abs)
    for side in ("over", "under"):
        mtype = "winning_margin_band"
        bk = _book_fields("GAME", mtype, side, fair_band, paper_lines)
        mp = _model_prob_at_book_line(margin_abs, side, bk["book_line"], fair_band)
        fa = fair_american(mp)
        band_line = bk["book_line"] if bk["book_line"] is not None else fair_band
        bk["edge"] = mp - bk["book_prob"] if bk["book_prob"] is not None else None
        bk["ev"] = (mp * _payout(bk["book_odds"]) - (1.0 - mp)) if bk["book_odds"] is not None else None
        markets.append({
            "market_type": mtype, "entity": "GAME", "entity_name": f"{away_tri}@{home_tri}",
            "stat": "margin_band", "line": band_line, "side": side,
            "model_prob": mp, "fair_american": fa,
            **bk, "honesty_class": "paper",
        })

    return markets


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Running market_catalog self-test (NYK vs SAS, 1500 sims) ...")
    from prop_engine import run as _run
    result = _run("NYK", "SAS", 1500, None, False)
    markets = price_markets(result)
    n = len(markets)
    print(f"Total concrete markets priced: {n}")
    assert n >= 100, f"FAIL: expected >=100 markets, got {n}"
    print(f"ontology_count(result) = {ontology_count(result)}")
    # Breakdown by market_type category
    from collections import Counter
    by_type = Counter(m["market_type"] for m in markets)
    print("\nTop market types by count:")
    for mt, cnt in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
        print(f"  {mt:30s} {cnt}")
    print(f"\nHonesty class check: {set(m['honesty_class'] for m in markets)}")
    print("PASS")
