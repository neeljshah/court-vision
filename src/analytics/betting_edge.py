"""
betting_edge.py — Betting edge calculation utilities.

Provides EV, Kelly sizing, and edge detection for sports props.

Public API
----------
    calculate_ev(your_prob, american_odds)         -> float
    kelly_fraction(edge, odds, bankroll, fraction) -> float
    find_edges(props_list, odds_feed)              -> List[BettingEdge]
    BettingEdge                                    dataclass

Usage:
    from src.analytics.betting_edge import calculate_ev, kelly_fraction, find_edges

Notes:
    - American odds: +150 means bet 100 to win 150; -110 means bet 110 to win 100.
    - EV = (your_prob * payout) - (1 - your_prob) = sum of (prob * outcome).
    - Kelly cap: bet size is capped at 2% of bankroll per wager by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

_KELLY_MAX_FRACTION = 0.02   # Hard cap: never bet > 2% of bankroll on one wager


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class BettingEdge:
    """
    A single identified betting edge on a player prop.

    Attributes:
        player:     Player name (e.g. 'LeBron James').
        stat:       Stat type (e.g. 'pts', 'reb', 'ast').
        line:       The bookmaker's line (e.g. 24.5 for over/under 24.5 points).
        direction:  'over' or 'under'.
        your_prob:  Your estimated probability of the bet winning.
        book_prob:  Implied probability from the book's odds.
        edge_pct:   your_prob - book_prob (positive = you have the edge).
        ev:         Expected value per unit staked.
        kelly_size: Recommended bet size (dollars) given Kelly fraction.
    """
    player:     str
    stat:       str
    line:       float
    direction:  str
    your_prob:  float
    book_prob:  float
    edge_pct:   float
    ev:         float
    kelly_size: float


# ── Core functions ─────────────────────────────────────────────────────────────

def american_to_decimal(american_odds: int) -> float:
    """
    Convert American odds to decimal odds.

    Args:
        american_odds: Integer odds (e.g. +150, -110).

    Returns:
        Decimal odds (e.g. 2.5, 1.909).
    """
    if american_odds >= 0:
        return 1.0 + american_odds / 100.0
    else:
        return 1.0 + 100.0 / abs(american_odds)


def implied_probability(american_odds: int) -> float:
    """
    Convert American odds to implied probability (no vig removed).

    Args:
        american_odds: Integer odds (e.g. -110).

    Returns:
        Implied probability in [0, 1].
    """
    decimal = american_to_decimal(american_odds)
    return 1.0 / decimal


def calculate_ev(your_prob: float, american_odds: int) -> float:
    """
    Calculate expected value per unit staked.

    EV = your_prob * payout - (1 - your_prob)

    where payout = decimal_odds - 1 (net winnings per unit bet).

    Args:
        your_prob:      Your estimated probability of winning (0–1).
        american_odds:  Bookmaker's American odds (e.g. -110, +150).

    Returns:
        EV per unit staked. Positive = +EV (you have the edge).

    Examples:
        calculate_ev(0.55, -110)   # near breakeven
        calculate_ev(0.60, +100)   # good edge
    """
    decimal = american_to_decimal(american_odds)
    payout  = decimal - 1.0   # net win per unit staked
    return round(your_prob * payout - (1.0 - your_prob), 6)


def kelly_fraction(
    edge: float,
    american_odds: int,
    bankroll: float,
    fraction: float = 0.25,
) -> float:
    """
    Compute recommended bet size using fractional Kelly criterion.

    Kelly formula: f* = (b*p - q) / b
    where b = decimal_odds - 1, p = win_prob, q = 1 - p.

    Fractional Kelly: multiply by `fraction` for bankroll preservation.
    Hard cap: bet never exceeds `_KELLY_MAX_FRACTION` (2%) of bankroll.

    Args:
        edge:          Your edge = your_prob - book_prob (or set your_prob manually).
                       Used directly as win probability.
        american_odds: Bookmaker's American odds.
        bankroll:      Total bankroll in dollars.
        fraction:      Kelly fraction multiplier (default 0.25 = quarter-Kelly).

    Returns:
        Recommended bet size in dollars (capped at 2% of bankroll).
        Returns 0.0 if edge is non-positive.
    """
    if edge <= 0:
        return 0.0
    if bankroll <= 0:
        return 0.0

    b = american_to_decimal(american_odds) - 1.0
    if b <= 0:
        return 0.0

    # Kelly formula uses win_prob = edge as approximate (caller already computed edge = p - q)
    # More precise: treat edge as the win probability directly when > 0
    p = edge
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0

    fractional = full_kelly * fraction
    max_bet    = bankroll * _KELLY_MAX_FRACTION
    return round(min(fractional * bankroll, max_bet), 2)


def find_edges(
    props_list: List[dict],
    odds_feed: dict,
) -> List[BettingEdge]:
    """
    Find positive-EV betting edges from a list of prop predictions and odds.

    Args:
        props_list: List of dicts with keys:
                    {player, stat, line, direction, your_prob, bankroll (optional)}
        odds_feed:  Dict mapping (player, stat, line, direction) tuple (as str key
                    "{player}|{stat}|{line}|{direction}") to American odds (int).

    Returns:
        List of BettingEdge objects for all props with positive EV,
        sorted by ev descending.
    """
    edges: List[BettingEdge] = []
    for prop in props_list:
        player    = prop.get("player", "")
        stat      = prop.get("stat", "")
        line      = float(prop.get("line", 0))
        direction = prop.get("direction", "over")
        your_prob = float(prop.get("your_prob", 0.5))
        bankroll  = float(prop.get("bankroll", 1000.0))

        key = f"{player}|{stat}|{line}|{direction}"
        if key not in odds_feed:
            continue

        american_odds = int(odds_feed[key])
        book_prob     = implied_probability(american_odds)
        edge_pct      = round(your_prob - book_prob, 6)
        ev            = calculate_ev(your_prob, american_odds)
        kelly_size    = kelly_fraction(your_prob, american_odds, bankroll)

        if ev > 0:
            edges.append(BettingEdge(
                player     = player,
                stat       = stat,
                line       = line,
                direction  = direction,
                your_prob  = your_prob,
                book_prob  = round(book_prob, 6),
                edge_pct   = edge_pct,
                ev         = ev,
                kelly_size = kelly_size,
            ))

    edges.sort(key=lambda e: e.ev, reverse=True)
    return edges


def get_correlation_penalty(player1_id: int | str, player2_id: int | str) -> float:
    """
    Return Pearson r of pts correlation for same-team players.

    Positive r means the players tend to score high together (correlated upside).
    Use this to adjust parlay/SGP confidence — high r means correlated risk.

    Args:
        player1_id: NBA player ID (int or str).
        player2_id: NBA player ID (int or str).

    Returns:
        Pearson r in [-1, 1]. 0.0 if not found or cache missing.
    """
    try:
        from src.analytics.prop_correlation import get_correlation_penalty as _gcpen
        return _gcpen(player1_id, player2_id)
    except Exception:
        return 0.0


def compute_clv(
    home_team: str,
    away_team: str,
    model_spread: float,
) -> Dict:
    """
    Compute Closing Line Value (CLV) for a model spread prediction.

    CLV = model_spread - closing_spread
    Positive = model predicted home better than closing market (beat the line).

    Also returns sharp-money signal (opening vs closing spread movement).
    Use this as a baseline metric before full betting infra (Phase 11).

    Args:
        home_team:    Team abbreviation (e.g. "BOS").
        away_team:    Team abbreviation (e.g. "GSW").
        model_spread: Model's predicted home-team spread (negative = home favoured).

    Returns:
        {
            "clv":            float,        # model_spread - closing_spread
            "sharp_signal":   float,        # opening - closing (positive = sharp on home)
            "closing_spread": float | None, # current closing line
            "model_spread":   float,
            "found":          bool,         # False if no odds data available
        }
    """
    try:
        from src.data.line_monitor import get_game_lines, get_sharp_signal
        lines   = get_game_lines(home_team, away_team)
        closing = lines.get("spread_home")
        sharp   = get_sharp_signal(home_team, away_team)
    except Exception:
        return {
            "clv": 0.0, "sharp_signal": 0.0,
            "closing_spread": None, "model_spread": model_spread,
            "adjusted_model_spread": model_spread, "found": False,
        }

    clv = round(model_spread - closing, 2) if closing is not None else 0.0

    # Sharp signal adjustment: if sharp money is against our predicted direction,
    # reduce confidence by 20% on the spread estimate.
    adjusted_model_spread = model_spread
    if sharp != 0.0:
        predicted_direction = 1.0 if model_spread > 0 else -1.0
        # sharp positive = sharp money on home; negative = sharp on away
        if sharp * predicted_direction < -0.3:
            adjusted_model_spread = round(model_spread * 0.8, 2)

    return {
        "clv":                  clv,
        "sharp_signal":         round(sharp, 4),
        "closing_spread":       closing,
        "model_spread":         model_spread,
        "adjusted_model_spread": adjusted_model_spread,
        "found":                lines.get("found", False),
    }


def backtest_clv(
    seasons: Optional[List[str]] = None,
    model_path: Optional[str] = None,
) -> Dict:
    """
    Backtest CLV (Closing Line Value) across historical seasons.

    Since real sportsbook closing lines are not yet in the data pipeline, this
    uses the actual game margin from ``data/external/historical_lines_*.json``
    (source: ``nba_api_actual_margin``) as the closing-spread proxy.

    CLV = model_spread - actual_margin
    Positive CLV means the model predicted home team to win by more than they did
    (i.e. overestimated home team — not a meaningful edge).  The primary utility
    here is establishing the baseline spread-accuracy for the model before real
    book lines are wired in Phase 11.

    Args:
        seasons:    e.g. ["2022-23", "2023-24", "2024-25"]
        model_path: Path to win_probability.pkl (default: data/models/win_probability.pkl)

    Returns:
        {
            "mean_clv":           float,   # mean (model_spread - actual_margin)
            "std_clv":            float,
            "pct_positive_clv":   float,   # % games where model was high on home
            "pct_correct_winner": float,   # % games model picked correct winner
            "mae_spread":         float,   # mean |model_spread - actual_margin|
            "n_games":            int,
            "by_season":          {season: {mean_clv, pct_correct, n_games}},
            "clv_distribution":   List[float],   # per-game CLV values
        }
    """
    import math
    import json
    import os

    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]

    # Load win prob model
    try:
        from src.prediction.win_probability import load as wp_load
        wp = wp_load(model_path)
    except Exception as exc:
        return {"error": f"Could not load win prob model: {exc}", "n_games": 0}

    _EXT_CACHE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "external",
    )

    all_clv: List[float] = []
    correct_winner = 0
    by_season: Dict = {}

    for season in seasons:
        path = os.path.join(_EXT_CACHE, f"historical_lines_{season}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            games = json.load(f)

        season_clv: List[float] = []
        season_correct = 0

        for g in games:
            home = g.get("home_team", "")
            away = g.get("away_team", "")
            actual_margin = g.get("closing_spread")   # actual home_pts - away_pts
            game_date = g.get("date")

            if not home or not away or actual_margin is None:
                continue
            try:
                actual_margin = float(actual_margin)
                if math.isnan(actual_margin):
                    continue
            except (TypeError, ValueError):
                continue

            try:
                pred = wp.predict(home, away, season=season, game_date=game_date)
                model_spread = pred["margin_est"]   # (prob - 0.5) * 30
            except Exception:
                continue

            clv = round(model_spread - actual_margin, 2)
            season_clv.append(clv)
            all_clv.append(clv)

            # Correct winner: model_spread and actual_margin on same side of 0
            if (model_spread >= 0) == (actual_margin >= 0):
                season_correct += 1

        if season_clv:
            correct_winner += season_correct
            n = len(season_clv)
            mean = round(sum(season_clv) / n, 3)
            pct_correct = round(season_correct / n * 100, 1)
            by_season[season] = {
                "mean_clv":      mean,
                "pct_correct":   pct_correct,
                "n_games":       n,
            }

    if not all_clv:
        return {"error": "No games processed", "n_games": 0}

    n_total = len(all_clv)
    mean_clv = round(sum(all_clv) / n_total, 3)
    std_clv  = round(math.sqrt(sum((x - mean_clv) ** 2 for x in all_clv) / n_total), 3)
    pct_pos  = round(sum(1 for x in all_clv if x > 0) / n_total * 100, 1)
    mae      = round(sum(abs(x) for x in all_clv) / n_total, 3)
    pct_win  = round(correct_winner / n_total * 100, 1)

    return {
        "mean_clv":           mean_clv,
        "std_clv":            std_clv,
        "pct_positive_clv":   pct_pos,
        "pct_correct_winner": pct_win,
        "mae_spread":         mae,
        "n_games":            n_total,
        "by_season":          by_season,
        "clv_distribution":   all_clv,
    }
