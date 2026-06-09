"""portfolio_optimizer.py — V7 sportsbook engine: correlation-aware paper Kelly portfolio.

PAPER pricing only -- no real-money path. Playoffs have NO proven edge.
ROI requires real captured prices + proven forward CLV.

Builds a simultaneous correlation-aware paper Kelly portfolio whose correlation
comes DIRECTLY from the joint sim samples (not an assumed matrix).  Candidate
markets (those with a supplied paper book line and positive EV) are ranked by EV,
then sized via betting_portfolio.kelly_corr with the empirical per-sim correlation
as the penalty term.

Public API
----------
    sample_covariance(result, markets) -> (corr_matrix KxK, kept_markets)
    build_portfolio(result, markets, *, bankroll, min_edge, max_bets,
                    max_bet_pct, frac) -> dict
    PaperBet  (dataclass)
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

# sys.path bootstrap mirrors prop_engine.py lines 16-17
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
))

from prediction.betting_portfolio import kelly_corr  # noqa: E402

__all__ = ["build_portfolio", "sample_covariance", "PaperBet"]

_CAVEAT = (
    "PAPER pricing only -- no real-money path. "
    "Playoffs have NO proven edge. "
    "ROI requires real captured prices + proven forward CLV."
)

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PaperBet:
    """One paper-only bet in the portfolio."""
    market_type: str
    entity: str
    entity_name: str
    stat: str
    line: Optional[float]
    side: str
    model_prob: float
    book_odds: int
    edge: float
    ev: float
    corr_to_book: float   # avg abs correlation to already-selected markets
    stake: float          # dollars
    kelly_pct: float      # stake / bankroll, clamped to <=0.25


# ---------------------------------------------------------------------------
# Helper: build per-sim binary hit indicator for a single market
# ---------------------------------------------------------------------------

def _hit_indicator(m: Dict, result) -> Optional[np.ndarray]:
    """Return boolean (0/1) array shape (nsims,) for market m using sim samples.

    Returns None for degenerate / unresolvable markets.
    """
    kind = m.get("market_type", "")
    side = m.get("side", "over")
    line = m.get("line")
    entity = m.get("entity", "")

    # ---- team / game markets ----
    if kind == "team_total":
        if "home" in entity.lower() or entity == getattr(result, "home_tri", ""):
            arr = result.home_total
        else:
            arr = result.away_total
        if line is None:
            return None
        return (arr > line).astype(float) if side == "over" else (arr < line).astype(float)

    if kind == "spread":
        margin = result.home_total - result.away_total
        if line is None:
            return None
        return (margin > line).astype(float) if side == "over" else (margin < line).astype(float)

    if kind == "moneyline":
        if entity == getattr(result, "home_tri", ""):
            return (result.home_total > result.away_total).astype(float)
        return (result.away_total > result.home_total).astype(float)

    if kind == "game_total":
        game_total = result.home_total + result.away_total
        if line is None:
            return None
        return (game_total > line).astype(float) if side == "over" else (game_total < line).astype(float)

    # ---- player markets ---- entity is a pid (str or int)
    try:
        pid = int(entity)
    except (ValueError, TypeError):
        return None

    if pid not in result.players:
        return None

    s = result.players[pid]["samples"]

    # derive the stat array (handles combos)
    stat = m.get("stat", "")
    if stat == "pra":
        arr = s["pts"] + s["reb"] + s["ast"]
    elif stat == "pr":
        arr = s["pts"] + s["reb"]
    elif stat == "pa":
        arr = s["pts"] + s["ast"]
    elif stat == "ra":
        arr = s["reb"] + s["ast"]
    elif stat == "stocks":
        arr = s["stl"] + s["blk"]
    elif stat in s:
        arr = s[stat]
    else:
        return None

    if line is None:
        # milestone / exotic with no numeric line => treat as yes/no with line=0
        return (arr >= 1).astype(float)

    if side == "over":
        return (arr > line).astype(float)
    elif side == "under":
        return (arr < line).astype(float)
    else:  # "yes" / milestone
        return (arr >= line).astype(float)


# ---------------------------------------------------------------------------
# Public: sample_covariance
# ---------------------------------------------------------------------------

def sample_covariance(
    result,
    markets: List[Dict],
) -> Tuple[np.ndarray, List[Dict]]:
    """Build an empirical correlation matrix from joint sim samples.

    Constructs H: (nsims, K) binary hit-indicator matrix where column k is the
    per-sim hit boolean for markets[k] evaluated on the same sample arrays from
    result.  The empirical correlation np.corrcoef(H.T) is the joint between-
    market correlation — this is why one coherent sim is required: SGP / portfolio
    leg correlation is MEASURED, not guessed.

    Degenerate columns (std==0) are dropped.

    Returns
    -------
    corr_matrix : np.ndarray shape (K', K')
    kept_markets : List[Dict] length K' (subset of input with non-degenerate indicators)
    """
    cols: List[np.ndarray] = []
    kept: List[Dict] = []

    for m in markets:
        indicator = _hit_indicator(m, result)
        if indicator is None:
            continue
        if np.std(indicator) == 0.0:
            continue   # drop degenerate (always hit or never hit)
        cols.append(indicator)
        kept.append(m)

    if len(cols) < 2:
        # Return identity (no correlation info) when too few markets
        k = len(cols)
        return np.eye(k), kept

    H = np.column_stack(cols)   # (nsims, K)
    corr = np.corrcoef(H.T)     # (K, K)
    return corr, kept


# ---------------------------------------------------------------------------
# Public: build_portfolio
# ---------------------------------------------------------------------------

def build_portfolio(
    result,
    markets: List[Dict],
    *,
    bankroll: float = 1000.0,
    min_edge: float = 0.03,
    max_bets: int = 20,
    max_bet_pct: float = 0.04,
    frac: float = 0.25,
) -> Dict:
    """Build a simultaneous correlation-aware paper Kelly portfolio.

    Only markets with edge >= min_edge AND ev > 0 (i.e. where a paper book line
    was supplied and the model is +EV) are candidates.  Fair-only markets (no
    book line => edge is None) are never bettable.

    Greedy selection ranked by ev descending, up to max_bets.  For each candidate,
    the avg abs correlation to already-selected markets is extracted from the
    empirical correlation matrix and passed to kelly_corr as corr_with_open.  This
    makes kelly_corr's built-in correlation penalty shrink stakes on co-moving legs.

    PAPER ONLY: never calls log_bet / record_clv; never touches bet_log.json.

    Returns
    -------
    dict with keys: bets, total_stake, n_candidates, bankroll, honesty_class, caveat
    """
    # -- candidates: must have a real edge and positive EV --
    candidates = [
        m for m in markets
        if m.get("edge") is not None
        and m["edge"] >= min_edge
        and (m.get("ev") or 0.0) > 0.0
    ]
    n_candidates = len(candidates)

    if not candidates:
        return {
            "bets": [],
            "total_stake": 0.0,
            "n_candidates": 0,
            "bankroll": bankroll,
            "honesty_class": "paper",
            "caveat": _CAVEAT,
        }

    # Rank by ev descending, take top max_bets
    candidates.sort(key=lambda m: -(m.get("ev") or 0.0))
    candidates = candidates[:max_bets]

    # Build empirical correlation matrix over all candidates
    corr_matrix, kept_markets = sample_covariance(result, candidates)

    # Map each candidate to its index in kept_markets (may drop degenerate)
    kept_keys = [
        (m.get("entity"), m.get("market_type"), m.get("side"), m.get("stat"), m.get("line"))
        for m in kept_markets
    ]

    def _market_key(m: Dict):
        return (m.get("entity"), m.get("market_type"), m.get("side"), m.get("stat"), m.get("line"))

    # Greedy simultaneous sizing
    selected_indices: List[int] = []   # indices into kept_markets / corr_matrix
    selected_bets: List[PaperBet] = []
    running_exposure: float = 0.0

    for m in candidates:
        key = _market_key(m)
        if key not in kept_keys:
            continue   # was dropped as degenerate
        k_idx = kept_keys.index(key)

        # avg abs correlation to already-selected markets
        if selected_indices:
            corrs = [abs(corr_matrix[k_idx, j]) for j in selected_indices]
            avg_abs_corr = float(np.mean(corrs))
        else:
            avg_abs_corr = 0.0

        book_odds = m.get("book_odds")
        if book_odds is None:
            continue

        # Kelly sizing via betting_portfolio.kelly_corr (real signature verified)
        stake = kelly_corr(
            edge=m["edge"],
            odds=book_odds,
            bankroll=bankroll,
            corr_with_open=avg_abs_corr,
            existing_exposure=running_exposure,
            win_prob_override=m["model_prob"],
        )

        # Double-cap: kelly_corr already applies quarter-Kelly + MAX_BET_PCT=0.04
        stake = min(stake, max_bet_pct * bankroll)
        if stake <= 0.0:
            continue

        kelly_pct = min(stake / bankroll, 0.25)

        bet = PaperBet(
            market_type=m.get("market_type", ""),
            entity=m.get("entity", ""),
            entity_name=m.get("entity_name", ""),
            stat=m.get("stat", ""),
            line=m.get("line"),
            side=m.get("side", "over"),
            model_prob=m["model_prob"],
            book_odds=book_odds,
            edge=m["edge"],
            ev=m.get("ev", 0.0),
            corr_to_book=avg_abs_corr,
            stake=round(stake, 2),
            kelly_pct=round(kelly_pct, 4),
        )
        selected_bets.append(bet)
        selected_indices.append(k_idx)
        running_exposure += stake

    total_stake = round(sum(b.stake for b in selected_bets), 2)

    return {
        "bets": [asdict(b) for b in selected_bets],
        "total_stake": total_stake,
        "n_candidates": n_candidates,
        "bankroll": bankroll,
        "honesty_class": "paper",
        "caveat": _CAVEAT,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """Synthetic self-test: 6 priced markets, 2 sharing a player (correlated),
    plus a team total.  Runs build_portfolio and prints the ranked portfolio.
    """
    import types

    NSIMS = 10_000
    rng = np.random.default_rng(42)

    # --- Minimal fake sim result ---
    # Player 1: scorer  (mean ~22 pts, ~5 reb, ~6 ast)
    pts1 = rng.gamma(shape=5.0, scale=4.4, size=NSIMS)
    reb1 = rng.gamma(shape=2.0, scale=2.5, size=NSIMS)
    ast1 = rng.gamma(shape=3.0, scale=2.0, size=NSIMS)
    stl1 = rng.poisson(1.2, size=NSIMS).astype(float)
    blk1 = rng.poisson(0.5, size=NSIMS).astype(float)

    # Player 2: big man  (mean ~14 pts, ~9 reb, ~3 ast)
    pts2 = rng.gamma(shape=4.0, scale=3.5, size=NSIMS)
    reb2 = rng.gamma(shape=4.5, scale=2.0, size=NSIMS)
    ast2 = rng.gamma(shape=1.5, scale=2.0, size=NSIMS)

    # Team totals: correlated with player pts
    home_total = pts1 + pts2 + rng.gamma(shape=8.0, scale=5.0, size=NSIMS)
    away_total = rng.gamma(shape=22.0, scale=5.0, size=NSIMS)

    result = types.SimpleNamespace(
        home_tri="NYK",
        away_tri="SAS",
        home_total=home_total,
        away_total=away_total,
        home_win_prob=float((home_total > away_total).mean()),
        players={
            101: {
                "name": "TestScorer",
                "team": "NYK",
                "mean": {"pts": float(pts1.mean()), "reb": float(reb1.mean()), "ast": float(ast1.mean())},
                "samples": {
                    "pts": pts1, "reb": reb1, "ast": ast1,
                    "stl": stl1, "blk": blk1,
                    "fga": pts1 * 0.5, "fgm": pts1 * 0.4, "fg3a": pts1 * 0.2,
                    "fg3m": pts1 * 0.1, "fta": pts1 * 0.3, "ftm": pts1 * 0.25,
                    "oreb": reb1 * 0.2, "dreb": reb1 * 0.8, "tov": rng.poisson(2.0, NSIMS).astype(float),
                    "pf": rng.poisson(2.0, NSIMS).astype(float),
                },
            },
            102: {
                "name": "TestBigMan",
                "team": "NYK",
                "mean": {"pts": float(pts2.mean()), "reb": float(reb2.mean()), "ast": float(ast2.mean())},
                "samples": {
                    "pts": pts2, "reb": reb2, "ast": ast2,
                    "stl": rng.poisson(0.8, NSIMS).astype(float),
                    "blk": rng.poisson(1.1, NSIMS).astype(float),
                    "fga": pts2 * 0.5, "fgm": pts2 * 0.4, "fg3a": pts2 * 0.1,
                    "fg3m": pts2 * 0.05, "fta": pts2 * 0.4, "ftm": pts2 * 0.33,
                    "oreb": reb2 * 0.35, "dreb": reb2 * 0.65, "tov": rng.poisson(1.5, NSIMS).astype(float),
                    "pf": rng.poisson(2.5, NSIMS).astype(float),
                },
            },
        },
    )

    # --- 6 synthetic priced markets (paper_lines supplied -> edge computed) ---
    # Lines set BELOW sim medians so model_prob > book_implied -> positive edge.
    # (Medians: pts1~20.6, ast1~5.3, pra1~30.1, reb2~8.3, home_total~74.4)
    # Book lines are set even lower, creating clear +EV opportunities for testing.

    def model_over_prob(pid, stat, line):
        s = result.players[pid]["samples"]
        if stat == "pra":
            arr = s["pts"] + s["reb"] + s["ast"]
        else:
            arr = s[stat]
        return float((arr > line).mean())

    def devig(over_odds, under_odds):
        from prediction.betting_portfolio import _american_to_prob as _atp  # type: ignore
        p_o = _atp(over_odds); p_u = _atp(under_odds)
        total = p_o + p_u
        return p_o / total, p_u / total

    markets = []

    # Market 1: Scorer PTS over 18.5 — book line below median ~20.6 -> model ~60%
    mp = model_over_prob(101, "pts", 18.5)
    bp, _ = devig(-130, +110)   # book shading under, model prob > devigged
    edge1 = round(mp - bp, 4)
    markets.append({
        "market_type": "pts_ou", "entity": "101", "entity_name": "TestScorer",
        "stat": "pts", "line": 18.5, "side": "over",
        "model_prob": mp, "fair_american": int(-round(100 * mp / (1 - mp))),
        "book_line": 18.5, "book_odds": -130, "book_prob": bp,
        "edge": edge1,
        "ev": round(mp * (100 / 130) - (1 - mp), 4),
        "honesty_class": "paper",
    })

    # Market 2: Scorer AST over 4.5 — book line below median ~5.3 -> model ~60%
    mp = model_over_prob(101, "ast", 4.5)
    bp, _ = devig(-130, +110)
    markets.append({
        "market_type": "ast_ou", "entity": "101", "entity_name": "TestScorer",
        "stat": "ast", "line": 4.5, "side": "over",
        "model_prob": mp, "fair_american": int(-round(100 * mp / (1 - mp))),
        "book_line": 4.5, "book_odds": -130, "book_prob": bp,
        "edge": round(mp - bp, 4),
        "ev": round(mp * (100 / 130) - (1 - mp), 4),
        "honesty_class": "paper",
    })

    # Market 3: Scorer PRA over 28.5 (correlated with markets 1+2, book -120)
    mp = model_over_prob(101, "pra", 28.5)
    bp, _ = devig(-120, +100)
    markets.append({
        "market_type": "pra_ou", "entity": "101", "entity_name": "TestScorer",
        "stat": "pra", "line": 28.5, "side": "over",
        "model_prob": mp, "fair_american": int(-round(100 * mp / (1 - mp))),
        "book_line": 28.5, "book_odds": -120, "book_prob": bp,
        "edge": round(mp - bp, 4),
        "ev": round(mp * (100 / 120) - (1 - mp), 4),
        "honesty_class": "paper",
    })

    # Market 4: BigMan REB over 7.5 — book below median ~8.3 -> model ~57%
    mp = model_over_prob(102, "reb", 7.5)
    bp, _ = devig(-130, +110)
    markets.append({
        "market_type": "reb_ou", "entity": "102", "entity_name": "TestBigMan",
        "stat": "reb", "line": 7.5, "side": "over",
        "model_prob": mp, "fair_american": int(-round(100 * mp / (1 - mp))),
        "book_line": 7.5, "book_odds": -130, "book_prob": bp,
        "edge": round(mp - bp, 4),
        "ev": round(mp * (100 / 130) - (1 - mp), 4),
        "honesty_class": "paper",
    })

    # Market 5: NYK team total over 68.5 — below sim median ~74.4 -> model ~70%
    game_total_arr = result.home_total
    mp5 = float((game_total_arr > 68.5).mean())
    bp, _ = devig(-140, +120)
    markets.append({
        "market_type": "team_total", "entity": result.home_tri, "entity_name": "NYK",
        "stat": "pts", "line": 68.5, "side": "over",
        "model_prob": mp5, "fair_american": int(-round(100 * mp5 / max(1 - mp5, 1e-4))),
        "book_line": 68.5, "book_odds": -140, "book_prob": bp,
        "edge": round(mp5 - bp, 4),
        "ev": round(mp5 * (100 / 140) - (1 - mp5), 4),
        "honesty_class": "paper",
    })

    # Market 6: fair-only (no book line) -> should NOT appear in portfolio
    markets.append({
        "market_type": "pts_ou", "entity": "101", "entity_name": "TestScorer",
        "stat": "pts", "line": 25.5, "side": "over",
        "model_prob": model_over_prob(101, "pts", 25.5),
        "fair_american": -140,
        "book_line": None, "book_odds": None, "book_prob": None,
        "edge": None, "ev": None,
        "honesty_class": "paper",
    })

    print("=== PORTFOLIO OPTIMIZER SELF-TEST ===")
    print(f"Input markets: {len(markets)}  (1 fair-only, 5 with book lines)")
    print()

    # Show model probs
    for m in markets:
        edge_str = f"edge={m['edge']:.4f}" if m["edge"] is not None else "fair-only"
        print(f"  {m['entity_name']:12s} {m['market_type']:10s} {m['stat']:5s} "
              f"line={m['line']}  model_p={m['model_prob']:.3f}  {edge_str}")
    print()

    # Run optimizer
    portfolio = build_portfolio(
        result, markets,
        bankroll=1000.0,
        min_edge=0.02,   # lower threshold so test markets qualify
        max_bets=20,
        max_bet_pct=0.04,
    )

    print(f"Candidates (edge>=0.02 & EV>0): {portfolio['n_candidates']}")
    print(f"Bets selected: {len(portfolio['bets'])}")
    print(f"Total stake: ${portfolio['total_stake']:.2f} / $1000 bankroll")
    print(f"Honesty class: {portfolio['honesty_class']}")
    print()

    if portfolio["bets"]:
        hdr = f"{'#':>2}  {'entity':12s} {'market':10s} {'stat':5s} {'line':6s} {'side':5s} "
        hdr += f"{'mp':6s} {'odds':6s} {'edge':6s} {'ev':6s} {'corr':5s} {'stake$':7s} {'k%':5s}"
        print(hdr)
        print("-" * len(hdr))
        for i, b in enumerate(portfolio["bets"], 1):
            print(
                f"{i:>2}  {b['entity_name']:12s} {b['market_type']:10s} {b['stat']:5s} "
                f"{str(b['line']):6s} {b['side']:5s} "
                f"{b['model_prob']:6.3f} {b['book_odds']:6d} {b['edge']:6.4f} "
                f"{b['ev']:6.4f} {b['corr_to_book']:5.3f} "
                f"${b['stake']:6.2f} {b['kelly_pct']*100:4.1f}%"
            )
    else:
        print("  (no +EV markets above min_edge threshold)")

    print()
    print(f"CAVEAT: {portfolio['caveat']}")

    # Also verify sample_covariance directly
    print()
    print("=== SAMPLE COVARIANCE (5 bettable markets) ===")
    bettable = [m for m in markets if m.get("edge") is not None]
    corr_mat, kept = sample_covariance(result, bettable)
    print(f"Kept markets: {len(kept)}")
    print(f"Correlation matrix ({len(corr_mat)}x{len(corr_mat[0])}):")
    labels = [f"{m['entity_name'][:6]}/{m['stat']}" for m in kept]
    print("         " + "  ".join(f"{l:10s}" for l in labels))
    for i, row in enumerate(corr_mat):
        print(f"{labels[i]:8s} " + "  ".join(f"{v:10.3f}" for v in row))
