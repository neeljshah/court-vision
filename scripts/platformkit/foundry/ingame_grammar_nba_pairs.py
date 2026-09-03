"""S144: frozen systematic NBA in-game pairwise state grammar.

The 14 non-combined S102 state bases form 91 unordered pairs.  For each pair this
module enumerates a product and an ordered safe ratio, under the same six phase
conditionings as S102: 1,092 hypotheses in the additive `ingame_nba_pairs`
family.  The two already-frozen combined bases are deliberately not inputs here.
All standardisation is expanding and per game, so a tick only uses itself and
earlier ticks.  The ratio denominator is sign-preservingly floored at 1e-3 in
these causal standardised units.  This is an uncharged SCREEN grammar.
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.foundry import ingame_grammar_nba as nba
from scripts.platformkit.foundry.grammar import Hypothesis, semantic_hash

FAMILY = "ingame_nba_pairs"
SPORT, HORIZON, MARKET = nba.SPORT, nba.HORIZON, nba.MARKET
EXCLUDED_BASES = ("margin_x_rem", "margin_over_sqrt_rem")
BASE: Tuple[str, ...] = tuple(base for base in nba.BASE if base not in EXCLUDED_BASES)
OPERATORS = ("product", "safe_ratio")
DENOMINATOR_FLOOR = 1e-3


def pair_name(left: str, right: str, operator: str) -> str:
    """Return the stable source-order label for one closed pair construction."""
    return "pair__%s__%s__%s" % (left, right, operator)


def pair_members() -> Tuple[str, ...]:
    """Return all 182 pair-operation columns before phase conditioning."""
    return tuple(pair_name(left, right, operator)
                 for left, right in combinations(BASE, 2) for operator in OPERATORS)


def _causal_standardised(src: pd.DataFrame) -> pd.DataFrame:
    """Causally standardise every allowed base inside its own game's history."""
    state = nba.build_state(src)[list(BASE)]
    frame = state.assign(game=src["game"].to_numpy(), ts=src["ts"].to_numpy())
    frame = frame.sort_values(["game", "ts"], kind="stable")
    group = frame.groupby("game", sort=False)[list(BASE)]
    mean = group.expanding().mean().reset_index(level=0, drop=True)
    std = group.expanding().std(ddof=0).reset_index(level=0, drop=True)
    z = (frame[list(BASE)] - mean) / std.replace(0.0, np.nan)
    return z.fillna(0.0).reindex(src.index)


def _safe_denominator(values: pd.Series) -> np.ndarray:
    """Floor an ordered ratio denominator without discarding its sign."""
    array = values.to_numpy(dtype=float)
    return np.where(np.abs(array) < DENOMINATOR_FLOOR,
                    np.where(array < 0.0, -DENOMINATOR_FLOOR, DENOMINATOR_FLOOR), array)


def build_grid(src: pd.DataFrame) -> pd.DataFrame:
    """Build all causal pair columns, returned in the original source row order."""
    standardised = _causal_standardised(src)
    out = {}
    for left, right in combinations(BASE, 2):
        out[pair_name(left, right, "product") + "|raw"] = standardised[left] * standardised[right]
        out[pair_name(left, right, "safe_ratio") + "|raw"] = (
            standardised[left].to_numpy(dtype=float) / _safe_denominator(standardised[right]))
    return pd.DataFrame(out, index=src.index)


def enumerate_hypotheses() -> List[Hypothesis]:
    """Enumerate the closed pair family, deduped by the shared semantic hash."""
    seen: Dict[str, Hypothesis] = {}
    for member in pair_members():
        for phase in (None,) + nba.PHASES:
            conditioning = frozenset() if phase is None else frozenset({"phase=%s" % phase})
            hypothesis = Hypothesis(SPORT, member, "raw", (), conditioning,
                                    HORIZON, MARKET, FAMILY, True)
            seen.setdefault(semantic_hash(hypothesis), hypothesis)
    return [seen[key] for key in sorted(seen)]


def grid_summary() -> Dict[str, object]:
    """Return the closed construction counts without reading the corpus."""
    hypotheses = enumerate_hypotheses()
    return {"family": FAMILY, "sport": SPORT, "horizon": HORIZON, "market": MARKET,
            "n_base": len(BASE), "n_pairs": len(tuple(combinations(BASE, 2))),
            "n_operators": len(OPERATORS), "n_conditionings": 1 + len(nba.PHASES),
            "n_hypotheses": len(hypotheses), "members": list(pair_members()),
            "excluded_bases": list(EXCLUDED_BASES), "denominator_floor": DENOMINATOR_FLOOR}


def main() -> int:
    summary = grid_summary()
    print("frozen NBA pair grammar: %d bases -> %d pairs x %d operators x %d conditionings = %d hypotheses"
          % (summary["n_base"], summary["n_pairs"], summary["n_operators"],
             summary["n_conditionings"], summary["n_hypotheses"]))
    print("family %s | excluded frozen bases: %s" % (FAMILY, ", ".join(EXCLUDED_BASES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
