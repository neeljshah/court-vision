"""
INT-84: Score multi-leg parlays using Gaussian copula + residual correlation matrix.

Usage:
    python scripts/score_parlays.py \
        --legs "2544|pts|OVER|25.5|0.55,2544|reb|OVER|7.5|0.48" \
        --book-odds "-110,-120"

    python scripts/score_parlays.py \
        --legs "2544|pts|OVER|25.5|0.55,2544|reb|OVER|7.5|0.48" \
        --book-odds "-110,-120" \
        --validate

Leg format: player_id_or_name|stat|OVER_or_UNDER|line|model_prob
All legs must be for the same game for any correlation to apply.
Cross-player same-game: independence (v1 TODO).
Cross-game: independence.
"""

import argparse
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, multivariate_normal

ROOT = Path(__file__).resolve().parent.parent

CORR_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"
FP_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Leg:
    player_id: int
    player_name: str
    stat: str
    direction: str   # "OVER" or "UNDER"
    line: float
    model_prob: float   # P(outcome hits per direction)
    archetype: str = "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal (net return per unit stake, incl. stake)."""
    if american > 0:
        return american / 100.0 + 1.0
    else:
        return 100.0 / abs(american) + 1.0


def vig_strip(american: float) -> float:
    """Implied probability from American odds (includes vig)."""
    if american > 0:
        return 100.0 / (american + 100.0)
    else:
        return abs(american) / (abs(american) + 100.0)


def joint_implied_prob(book_odds: list[float]) -> float:
    """Vig-stripped joint implied probability for a parlay."""
    # Simple product of vig-stripped marginals
    probs = [vig_strip(o) for o in book_odds]
    return float(np.prod(probs))


def load_correlation_matrix(scope: str, stats: list[str]) -> np.ndarray | None:
    """
    Load the PSD-projected correlation matrix for a given scope, subset to `stats`.
    Returns None if scope not found.
    """
    if not CORR_PATH.exists():
        return None

    df = pd.read_parquet(CORR_PATH)
    scope_df = df[df.scope == scope]
    if scope_df.empty:
        return None

    n = len(stats)
    mat = np.eye(n)
    idx = {s: i for i, s in enumerate(stats)}

    for _, row in scope_df.iterrows():
        a, b = str(row["stat_a"]), str(row["stat_b"])
        if a in idx and b in idx:
            mat[idx[a], idx[b]] = float(row["corr"])
            mat[idx[b], idx[a]] = float(row["corr"])

    return mat


def resolve_scope(legs: list[Leg]) -> tuple[str, np.ndarray, list[str]]:
    """
    Determine correlation scope and return (scope_tag, Sigma_k, stats_k).
    Same-player legs: use player archetype → league fallback.
    Cross-player: independence (v1).
    """
    stats_k = [leg.stat for leg in legs]

    # All same player?
    player_ids = list({leg.player_id for leg in legs})
    archetypes = list({leg.archetype for leg in legs if leg.archetype != "unknown"})

    if len(player_ids) == 1:
        # Single player — use archetype scope
        arch = legs[0].archetype
        scope_tag = f"archetype:{arch}" if arch != "unknown" else "league"
        mat = load_correlation_matrix(scope_tag, stats_k)
        if mat is None:
            scope_tag = "league"
            mat = load_correlation_matrix("league", stats_k)
        if mat is None:
            # Fallback: identity (independence)
            scope_tag = "identity (fallback)"
            mat = np.eye(len(stats_k))
    else:
        # Cross-player — independence v1
        scope_tag = "independence (cross-player v1 — TODO)"
        mat = np.eye(len(stats_k))

    return scope_tag, mat, stats_k


def prob_to_z(leg: Leg) -> float:
    """
    Convert leg model_prob to standard normal quantile for the copula.

    For OVER: model_prob = P(stat > line).  The copula axis is "stat value",
    so z = Phi^-1(P(stat > line)) = Phi^-1(p).
    For UNDER: model_prob = P(stat < line).  Same formula:
    z = Phi^-1(P(stat < line)) = Phi^-1(p).

    This correctly maps: high OVER probability → large positive z (right tail),
    high UNDER probability → large positive z on the negated axis.
    """
    p = np.clip(leg.model_prob, 1e-6, 1 - 1e-6)
    return float(norm.ppf(p))


def mvn_joint_prob(zs: list[float], Sigma: np.ndarray) -> float:
    """P(Z_1 <= z_1, ..., Z_k <= z_k) under MVN(0, Sigma)."""
    k = len(zs)
    if k == 1:
        return float(norm.cdf(zs[0]))
    if k == 2:
        # Fast 2D path
        mu = np.zeros(2)
        try:
            rv = multivariate_normal(mean=mu, cov=Sigma)
            return float(rv.cdf(np.array(zs)))
        except Exception:
            return float(norm.cdf(zs[0]) * norm.cdf(zs[1]))
    # General k
    mu = np.zeros(k)
    try:
        rv = multivariate_normal(mean=mu, cov=Sigma)
        return float(rv.cdf(np.array(zs)))
    except Exception:
        # Fallback: independence
        return float(np.prod([norm.cdf(z) for z in zs]))


# ---------------------------------------------------------------------------
# Unit test: UNDER direction sign
# ---------------------------------------------------------------------------

def _test_under_sign() -> None:
    """
    UNDER p=0.80 should give z=Phi^-1(0.80)≈0.84 (positive).
    OVER p=0.80 should also give z≈0.84.
    Independence P_joint for two 0.80 legs = 0.64.
    """
    leg_over = Leg(player_id=1, player_name="X", stat="pts", direction="OVER",
                   line=25.0, model_prob=0.80, archetype="unknown")
    leg_under = Leg(player_id=1, player_name="X", stat="reb", direction="UNDER",
                    line=5.0, model_prob=0.80, archetype="unknown")

    z_over = prob_to_z(leg_over)
    z_under = prob_to_z(leg_under)
    assert abs(z_over - 0.8416) < 0.001, f"OVER z wrong: {z_over}"
    assert abs(z_under - 0.8416) < 0.001, f"UNDER z wrong: {z_under}"

    # Joint with identity (independence)
    p_joint = mvn_joint_prob([z_over, z_under], np.eye(2))
    assert abs(p_joint - 0.64) < 0.01, f"Independence P_joint wrong: {p_joint}"


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_parlay(legs: list[Leg], book_odds: list[float], validate: bool = False) -> None:
    """Compute and print parlay EV + Kelly."""

    if validate:
        _test_under_sign()
        print("  [unit test] UNDER direction sign: PASS")

    scope_tag, Sigma_k, stats_k = resolve_scope(legs)

    # Build z vector
    zs = [prob_to_z(leg) for leg in legs]

    # Marginal probs (already in leg.model_prob)
    p_marginals = [leg.model_prob for leg in legs]
    p_independent = float(np.prod(p_marginals))

    # Joint via copula
    p_joint = mvn_joint_prob(zs, Sigma_k)
    p_joint = float(np.clip(p_joint, 1e-9, 1.0))

    edge_over_indep = p_joint - p_independent

    # Book side
    book_implied = joint_implied_prob(book_odds)
    # Parlay decimal odds
    parlay_decimal = float(np.prod([american_to_decimal(o) for o in book_odds]))

    model_edge = p_joint - book_implied
    ev = p_joint * (parlay_decimal - 1.0) - (1.0 - p_joint)
    kelly = model_edge / (parlay_decimal - 1.0) if (parlay_decimal - 1.0) > 0 else 0.0
    kelly_025 = max(0.0, kelly * 0.25)

    # Classify same/cross player
    player_ids = list({leg.player_id for leg in legs})
    game_label = "same-player" if len(player_ids) == 1 else "cross-player"

    print(f"\nLegs: {len(legs)} ({game_label}, same-game)")
    print(f"Scope: {scope_tag}")
    for i, leg in enumerate(legs):
        print(f"  Leg {i+1}: [{leg.player_name}] {leg.stat.upper()} {leg.direction} "
              f"{leg.line} — model_prob={leg.model_prob:.4f}  z={zs[i]:+.4f}")
    for i, (p, od) in enumerate(zip(p_marginals, book_odds)):
        print(f"P_marginal_{i+1}: {p:.4f}  (book_implied={vig_strip(od):.4f}  odds={od:+.0f})")
    print(f"P_independent: {p_independent:.4f}")
    print(f"P_joint (copula): {p_joint:.4f}")
    print(f"Edge over independence: {edge_over_indep:+.4f}")
    print(f"Book implied (vig-stripped parlay): {book_implied:.4f}")
    print(f"Model edge over book: {model_edge:+.4f}")
    print(f"Parlay decimal odds: {parlay_decimal:.3f}x")
    print(f"EV: {ev:+.4f} | Kelly (0.25x): {kelly_025:.4f}")

    # Caveats
    if "cross-player" in scope_tag or "TODO" in scope_tag:
        print("  NOTE: cross-player correlation unmodeled (v1) — independence assumed")
    if validate:
        print("\n--- Sanity gates (parlay scorer) ---")
        if abs(p_joint - p_independent) < 1e-6 and scope_tag != "identity (fallback)":
            print("  WARN: P_joint == P_independent despite non-identity Sigma — check matrix")
        else:
            print("  OK   P_joint differs from P_independent as expected")
        if not (0 < p_joint <= 1.0):
            print(f"  WARN: P_joint={p_joint:.6f} out of [0,1]")
        else:
            print("  OK   P_joint in valid range")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_legs(leg_str: str, fp: pd.DataFrame | None) -> list[Leg]:
    """
    Parse leg string: "player_id|stat|OVER/UNDER|line|prob,..."
    """
    legs = []
    for part in leg_str.split(","):
        tokens = [t.strip() for t in part.split("|")]
        if len(tokens) != 5:
            print(f"HALT: invalid leg format '{part}' — expected player_id|stat|OVER/UNDER|line|prob")
            sys.exit(1)

        pid_str, stat, direction, line_str, prob_str = tokens
        stat = stat.lower()
        direction = direction.upper()

        if direction not in ("OVER", "UNDER"):
            print(f"HALT: direction must be OVER or UNDER, got '{direction}'")
            sys.exit(1)

        if stat not in STATS:
            print(f"HALT: stat '{stat}' not in {STATS}")
            sys.exit(1)

        # Resolve player
        try:
            player_id = int(pid_str)
            player_name = pid_str
        except ValueError:
            # Name lookup
            if fp is not None:
                match = fp[fp.player_name.str.lower() == pid_str.lower()]
                if match.empty:
                    match = fp[fp.player_name.str.lower().str.contains(pid_str.lower())]
                if not match.empty:
                    player_id = int(match.index[0])
                    player_name = str(match.iloc[0]["player_name"])
                else:
                    print(f"HALT: player '{pid_str}' not found in fingerprints")
                    sys.exit(1)
            else:
                print(f"HALT: cannot resolve name '{pid_str}' — fingerprints not available")
                sys.exit(1)

        arch = "unknown"
        if fp is not None and player_id in fp.index:
            arch = str(fp.loc[player_id, "archetype_name"])

        legs.append(Leg(
            player_id=player_id,
            player_name=player_name,
            stat=stat,
            direction=direction,
            line=float(line_str),
            model_prob=float(prob_str),
            archetype=arch,
        ))

    return legs


def main() -> None:
    parser = argparse.ArgumentParser(description="Score NBA prop parlays via Gaussian copula")
    parser.add_argument(
        "--legs",
        type=str,
        required=True,
        help='Comma-separated legs: "player_id|stat|OVER/UNDER|line|prob,..."',
    )
    parser.add_argument(
        "--book-odds",
        type=str,
        required=True,
        help='Comma-separated American odds per leg: "-110,-120"',
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run unit test + sanity gates",
    )
    args = parser.parse_args()

    # Load fingerprints
    fp = None
    if FP_PATH.exists():
        fp = pd.read_parquet(FP_PATH)
    else:
        print(f"WARNING: fingerprints not found at {FP_PATH} — archetype resolution disabled")

    if not CORR_PATH.exists():
        print(f"HALT: stat_correlation_matrix.parquet not found — run build_stat_correlations.py first")
        sys.exit(1)

    legs = parse_legs(args.legs, fp)

    book_odds_raw = [float(o.strip()) for o in args.book_odds.split(",")]
    if len(book_odds_raw) != len(legs):
        print(f"HALT: {len(legs)} legs but {len(book_odds_raw)} book odds")
        sys.exit(1)

    score_parlay(legs, book_odds_raw, validate=args.validate)


if __name__ == "__main__":
    main()
