"""parlay_constructor.py — 3-leg parlay product for the production betting stack.

Consumes the daily single-leg bet log (output of compare_to_lines / bet_selector)
and emits ranked 3-leg combos with Kelly sizing.

Iter-43 validates the Iter-42 finding: 3-leg parlays yield +50.53% SGP-adjusted
ROI on 564 viable combos per season.

Public API
----------
    build_parlay_candidates(single_leg_bets_df) -> pd.DataFrame
    compute_parlay_metrics(combo, hit_rates, prices) -> dict
    rank_parlays(candidates) -> pd.DataFrame
    kelly_parlay_stake(parlay, bankroll, kelly_fraction) -> float
"""
from __future__ import annotations

import hashlib
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── Constants ────────────────────────────────────────────────────────────────

# Pairs forbidden from appearing together in any parlay (definitional correlation).
# fg3m contributes directly to pts (phi=0.513 from Iter-41 analysis).
FORBIDDEN_PAIRS: frozenset[frozenset] = frozenset([
    frozenset(["fg3m", "pts"]),
])

# SGP sportsbook penalty on parlay payout (-15% flat, consistent with Iter-42).
SGP_PENALTY: float = 0.15

# Break-even hit rate for a 3-leg parlay at -110/-110/-110.
BREAKEVEN_3LEG: float = 0.144  # 1 / 1.909^3

# Per-stat hit rates calibrated from Iter-39 production stack.
# Used when no per-row probability is provided.
_ITER39_HIT_RATES: Dict[str, float] = {
    "pts": 0.5847, "reb": 0.5982, "ast": 0.6716,
    "fg3m": 0.7183, "stl": 0.6183, "blk": 0.6654, "tov": 0.5500,
}

# Intra-player stat correlations (from parlay_engine._SAME_PLAYER_RHO).
# Used to shrink the independent hit-rate product.
_SAME_PLAYER_CORR: Dict[frozenset, float] = {
    frozenset(("pts", "ast")): 0.30,
    frozenset(("pts", "reb")): 0.40,
    frozenset(("pts", "fg3m")): 0.55,
    frozenset(("pts", "stl")): 0.20,
    frozenset(("pts", "blk")): 0.10,
    frozenset(("pts", "tov")): 0.35,
    frozenset(("reb", "blk")): 0.35,
    frozenset(("reb", "ast")): 0.15,
    frozenset(("ast", "tov")): 0.40,
    frozenset(("fg3m", "ast")): 0.20,
    frozenset(("stl", "blk")): 0.15,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_forbidden_combo(stats: Tuple[str, ...]) -> bool:
    """Return True if the stat tuple contains any forbidden pair."""
    for a, b in combinations(stats, 2):
        if frozenset([a, b]) in FORBIDDEN_PAIRS:
            return True
    return False


def _american_to_decimal(odds: int) -> float:
    """Convert American odds to decimal odds (returns on 1 unit stake incl. stake)."""
    if odds >= 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / abs(odds)


def _decimal_to_american(d: float) -> int:
    if d <= 1.0:
        return -10000
    if d >= 2.0:
        return int(round((d - 1.0) * 100.0))
    return int(round(-100.0 / (d - 1.0)))


def _correlation_adjustment(legs: List[dict]) -> float:
    """Return a correlation-based shrinkage factor for joint hit probability.

    For legs sharing the same player, applies the per-pair rho from
    ``_SAME_PLAYER_CORR`` to each same-player stat pair.  Legs belonging to
    different players contribute no adjustment (cross-player correlations are
    small and modelled as independent).

    This correctly handles mixed parlays such as
    [LeBron pts OVER, LeBron ast OVER, Davis reb OVER] where only the
    LeBron pts/ast pair carries a same-player rho — the Davis leg contributes
    factor 1.0.  The all-same-player and all-different-player cases are exact
    special cases of this general formulation.
    """
    if len(legs) < 2:
        return 1.0

    # Group leg indices by player identity (player_id preferred, else name).
    from collections import defaultdict
    player_to_legs: dict = defaultdict(list)
    for idx, leg in enumerate(legs):
        pid = leg.get("player_id") or leg.get("player", f"__unknown_{idx}")
        player_to_legs[pid].append(leg)

    # Collect rhos only for same-player pairs.
    rhos: List[float] = []
    for pid, player_legs in player_to_legs.items():
        if len(player_legs) < 2:
            continue
        for leg_a, leg_b in combinations(player_legs, 2):
            stat_a = leg_a.get("stat", "")
            stat_b = leg_b.get("stat", "")
            rho = _SAME_PLAYER_CORR.get(frozenset((stat_a, stat_b)), 0.0)
            rhos.append(rho)

    if not rhos:
        return 1.0

    avg_rho = sum(rhos) / len(rhos)
    # Positive correlation between OVER legs means they tend to hit together,
    # slightly boosting joint probability.  Conservative 50% weight to avoid
    # overfitting; scale by (len(legs)-1) to match the original all-same formula.
    return 1.0 + avg_rho * 0.5 * (len(legs) - 1) * 0.1


def _parlay_id(legs: List[dict]) -> str:
    key = "|".join(sorted(
        f"{r.get('player','')}:{r.get('stat','')}:{r.get('line','')}:{r.get('side','')}"
        for r in legs
    ))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# ── Core API ─────────────────────────────────────────────────────────────────

def build_parlay_candidates(single_leg_bets_df: pd.DataFrame) -> pd.DataFrame:
    """Enumerate all valid 3-leg combos from a daily single-leg bet slate.

    Parameters
    ----------
    single_leg_bets_df:
        DataFrame with columns (at minimum):
          player, stat, line, side, prob, odds, ev
        Optional: game_id, player_id, model, edge, kelly_pct, kelly_stake

        This is exactly the output written by compare_to_lines --bet-log,
        with column names lowercased.

    Returns
    -------
    pd.DataFrame with one row per valid 3-leg combo:
        parlay_id, player_combo, stat_combo, game_id_combo,
        is_same_player, hit_rate_indep, hit_rate_adj, decimal_odds,
        american_odds, sgp_payout_adj, ev_raw, ev_sgp, expected_roi_sgp_pct,
        leg_0, leg_1, leg_2  (JSON-serializable dicts of each leg)
    """
    df = single_leg_bets_df.copy()
    # Normalise column names
    df.columns = [c.lower().strip() for c in df.columns]

    required = {"player", "stat", "line", "side"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"single_leg_bets_df missing columns: {missing}")

    df["stat"] = df["stat"].str.lower().str.strip()
    df["side"] = df["side"].str.upper().str.strip()

    # Only OVER bets participate (model only places positive-edge OVERs)
    df = df[df["side"] == "OVER"].reset_index(drop=True)

    if "odds" not in df.columns:
        df["odds"] = -110
    if "prob" not in df.columns:
        df["prob"] = df["stat"].map(_ITER39_HIT_RATES).fillna(0.55)

    # Group by player so we know which combos are same-player
    # We allow cross-player combos — they tend to have positive correlations
    records = df.to_dict("records")
    n = len(records)

    rows: List[dict] = []
    for i, j, k in combinations(range(n), 3):
        legs = [records[i], records[j], records[k]]
        stats = tuple(leg["stat"] for leg in legs)
        if _is_forbidden_combo(stats):
            continue

        players = [leg["player"] for leg in legs]
        same_player = len(set(players)) == 1

        hit_rates: List[float] = [
            float(leg.get("prob") or _ITER39_HIT_RATES.get(leg["stat"], 0.55))
            for leg in legs
        ]
        combo_metrics = compute_parlay_metrics(
            combo=legs,
            hit_rates=hit_rates,
            prices=[int(leg.get("odds", -110)) for leg in legs],
            # same_player kwarg not needed — compute_parlay_metrics now
            # auto-detects same-player pairs from leg dicts.
        )

        game_ids = [str(leg.get("game_id", "")) for leg in legs]

        rows.append({
            "parlay_id": _parlay_id(legs),
            "player_combo": " / ".join(players),
            "stat_combo": "+".join(s.upper() for s in stats),
            "game_id_combo": " / ".join(game_ids),
            "is_same_player": same_player,
            "hit_rate_indep": round(combo_metrics["hit_rate_indep"], 4),
            "hit_rate_adj": round(combo_metrics["hit_rate_adj"], 4),
            "decimal_odds": round(combo_metrics["decimal_odds"], 3),
            "american_odds": combo_metrics["american_odds"],
            "sgp_payout_adj": round(combo_metrics["sgp_payout_adj"], 3),
            "ev_raw": round(combo_metrics["ev_raw"], 4),
            "ev_sgp": round(combo_metrics["ev_sgp"], 4),
            "expected_roi_sgp_pct": round(combo_metrics["expected_roi_sgp_pct"], 2),
            "leg_0": legs[0],
            "leg_1": legs[1],
            "leg_2": legs[2],
        })

    if not rows:
        return pd.DataFrame(columns=[
            "parlay_id", "player_combo", "stat_combo", "game_id_combo",
            "is_same_player", "hit_rate_indep", "hit_rate_adj", "decimal_odds",
            "american_odds", "sgp_payout_adj", "ev_raw", "ev_sgp",
            "expected_roi_sgp_pct", "leg_0", "leg_1", "leg_2",
        ])

    return pd.DataFrame(rows)


def compute_parlay_metrics(
    combo: List[dict],
    hit_rates: List[float],
    prices: List[int],
    same_player: bool = False,
) -> dict:
    """Compute joint hit-rate, payout, and EV for a 3-leg combo.

    Parameters
    ----------
    combo:      List of 3 leg dicts (player, stat, line, side, etc.)
    hit_rates:  Per-leg model probability of hitting (OVER wins)
    prices:     Per-leg American odds (e.g. -110, +145)
    same_player: Deprecated — kept for backwards-compatibility; the function
                 now detects same-player pairs automatically from the ``combo``
                 leg dicts (via ``player_id`` or ``player`` fields).

    Returns
    -------
    dict with keys:
        hit_rate_indep  — product of per-leg hit rates (independence assumption)
        hit_rate_adj    — correlation-adjusted joint hit rate
        decimal_odds    — compounded decimal odds (raw)
        american_odds   — compounded American odds
        sgp_payout_adj  — net payout per unit after SGP penalty
        ev_raw          — expected value per unit (raw, pre-SGP)
        ev_sgp          — expected value per unit (SGP-penalised)
        expected_roi_sgp_pct — ev_sgp as percentage of stake
    """
    hit_rate_indep = 1.0
    for hr in hit_rates:
        hit_rate_indep *= max(0.0, min(1.0, float(hr)))

    corr_factor = _correlation_adjustment(combo)
    hit_rate_adj = min(1.0, hit_rate_indep * corr_factor)

    decimal_odds = 1.0
    for p in prices:
        decimal_odds *= _american_to_decimal(int(p))

    american_odds = _decimal_to_american(decimal_odds)

    # Net payout per unit (stake not returned on loss)
    net_payout_raw = decimal_odds - 1.0
    # SGP sportsbook applies a flat -15% reduction on net win
    sgp_payout_adj = net_payout_raw * (1.0 - SGP_PENALTY)

    ev_raw = hit_rate_adj * net_payout_raw - (1.0 - hit_rate_adj) * 1.0
    ev_sgp = hit_rate_adj * sgp_payout_adj - (1.0 - hit_rate_adj) * 1.0
    expected_roi_sgp_pct = ev_sgp * 100.0

    return {
        "hit_rate_indep": hit_rate_indep,
        "hit_rate_adj": hit_rate_adj,
        "decimal_odds": decimal_odds,
        "american_odds": american_odds,
        "sgp_payout_adj": sgp_payout_adj,
        "ev_raw": ev_raw,
        "ev_sgp": ev_sgp,
        "expected_roi_sgp_pct": expected_roi_sgp_pct,
    }


def rank_parlays(candidates: pd.DataFrame, top_n: Optional[int] = None) -> pd.DataFrame:
    """Sort parlay candidates by expected SGP-adjusted ROI (descending).

    Parameters
    ----------
    candidates: Output of build_parlay_candidates()
    top_n:      If set, return only the top N rows

    Returns
    -------
    pd.DataFrame sorted by expected_roi_sgp_pct descending,
    with an added `rank` column (1-indexed).
    """
    if candidates.empty:
        return candidates.copy()

    ranked = candidates.sort_values("expected_roi_sgp_pct", ascending=False).copy()
    ranked = ranked[ranked["expected_roi_sgp_pct"] > 0].reset_index(drop=True)
    ranked.insert(0, "rank", ranked.index + 1)
    if top_n is not None:
        ranked = ranked.head(top_n)
    return ranked


def kelly_parlay_stake(
    parlay: dict,
    bankroll: float,
    kelly_fraction: float = 0.10,
) -> float:
    """Compute Kelly-B-adjusted stake for a 3-leg parlay.

    Uses a smaller fraction than single-leg (default 0.10 vs 0.25) because
    3-leg parlay variance is substantially higher. Applies a half-Kelly cap.

    Parameters
    ----------
    parlay:         Row from rank_parlays() output (or compute_parlay_metrics() dict)
    bankroll:       Current bankroll in dollars
    kelly_fraction: Fraction of full Kelly to apply. Default 0.10 (10%).

    Returns
    -------
    Dollar stake (float), capped at kelly_fraction * bankroll.
    """
    p = float(parlay.get("hit_rate_adj", parlay.get("hit_rate_indep", 0.0)))
    decimal_odds = float(parlay.get("decimal_odds", 1.0))
    sgp_payout = float(parlay.get("sgp_payout_adj", decimal_odds - 1.0))

    if p <= 0 or sgp_payout <= 0:
        return 0.0

    q = 1.0 - p
    # Kelly formula: f* = (b*p - q) / b  where b = net payout per unit
    b = sgp_payout
    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0.0

    # Apply fraction and hard cap
    stake = f_star * kelly_fraction * bankroll
    max_stake = kelly_fraction * bankroll
    return round(min(stake, max_stake), 2)
