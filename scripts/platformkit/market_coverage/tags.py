"""market_coverage.tags -- the THINNESS + VALIDATABLE taxonomy.

Two orthogonal honesty axes attached to EVERY enumerated market so a consumer
knows (a) how thinly the market is policed -> where being smartest *can* pay, and
(b) whether the model's price can be VALIDATED offline at all or only via forward
capture. These tags are descriptive metadata, NOT edge claims.

THINNESS (how much sharp money polices the line):
  LIQUID  -- mainline sides/totals/ML on major games; razor-efficient. We MATCH;
             an in-sample "beat" here is almost surely noise. Record honestly.
  SEMI    -- core single player props (star pts/reb/ast O/U); moderately policed.
  THIN    -- combos, alt-lines, team/quarter/half derivatives, prop overs/unders
             on role players; soft, slow-moving, frequently stale.
  EXTREME -- longshots, deep SGPs, scenario/exotic, in-game micro; little/no sharp
             money. The mispricing lane -- but also the least-reliable model cell.

VALIDATABLE (can we confirm the price offline / how):
  HAS_CLOSE     -- a real historical close exists locally for this shape (mainline
                   ML / total) -> gate it now vs the SHIN-devigged close.
  PRICE_ONLY    -- we can PRICE + CALIBRATE the marginal now (prop-model WF MAE)
                   but have no captured book close for THIS exact line offline.
  FORWARD_ONLY  -- no historical close locally at all (most obscure/SGP/in-game
                   micro) -> PRICED now, VALIDATED only by forward CLV capture.

THE CATCH (binding honesty): most obscure markets are FORWARD_ONLY -- a price you
trust by calibration, not a $ edge, and any survivor needs the forward_capture
clock. Real $ is additionally CAPPED by book limits on thin markets.

Stdlib only. <=300 LOC. Per-file test: tests/test_market_coverage_tags.py.
"""
from __future__ import annotations

from typing import Dict

# The 7 enumerated category keys (the build contract).
CATEGORIES = (
    "player-props-core",
    "player-props-combos",
    "team-quarter-half",
    "game-scenario-longshot",
    "sgp-correlation",
    "mlb-soccer-tennis",
    "ingame-micro",
)

THINNESS = ("LIQUID", "SEMI", "THIN", "EXTREME")
VALIDATABLE = ("HAS_CLOSE", "PRICE_ONLY", "FORWARD_ONLY")

# Default thinness per category (a starting point; per-market overrides below).
_CAT_THINNESS: Dict[str, str] = {
    "player-props-core": "SEMI",
    "player-props-combos": "THIN",
    "team-quarter-half": "THIN",
    "game-scenario-longshot": "EXTREME",
    "sgp-correlation": "EXTREME",
    "mlb-soccer-tennis": "SEMI",
    "ingame-micro": "EXTREME",
}

# Default validatability per category. HAS_CLOSE is reserved for the mainline
# shapes (ML / game total) we actually have a local historical close for.
_CAT_VALIDATABLE: Dict[str, str] = {
    "player-props-core": "PRICE_ONLY",
    "player-props-combos": "FORWARD_ONLY",
    "team-quarter-half": "FORWARD_ONLY",
    "game-scenario-longshot": "FORWARD_ONLY",
    "sgp-correlation": "FORWARD_ONLY",
    "mlb-soccer-tennis": "PRICE_ONLY",
    "ingame-micro": "FORWARD_ONLY",
}


def category_thinness(category: str) -> str:
    if category not in _CAT_THINNESS:
        raise KeyError(f"unknown category {category!r}; one of {CATEGORIES}")
    return _CAT_THINNESS[category]


def category_validatable(category: str) -> str:
    if category not in _CAT_VALIDATABLE:
        raise KeyError(f"unknown category {category!r}; one of {CATEGORIES}")
    return _CAT_VALIDATABLE[category]


def is_mainline(market_name: str, kind: str) -> bool:
    """A liquid mainline = full-game moneyline / spread / total. These are the
    razor-efficient lines we MATCH (HAS_CLOSE). Recognizes the book_builder naming
    ('home_ml'/'away_ml', 'home_spread', 'game_total') and the predictor naming
    ('match_winner'). Excludes team-totals, quarters, halves (those are derivatives)."""
    m = market_name.lower()
    if kind not in ("side", "scenario", "team", "single"):
        return False
    # a quarter/half segment prefix (q1_/q2_/h1_/...) is never a full-game mainline.
    if any(m.startswith(p) for p in ("q1_", "q2_", "q3_", "q4_", "h1_", "h2_")):
        return False
    if "team_total" in m or "quarter" in m or "half" in m:
        return False
    full = ("game_total" in m or "_ml" in m or m.startswith("moneyline")
            or "match_winner" in m or "_spread" in m or "game_spread" in m)
    return bool(full)


def thinness_for(category: str, market_name: str, kind: str, prob: float) -> str:
    """Resolve a market's thinness: mainlines are LIQUID; deep tails escalate to
    EXTREME; otherwise inherit the category default."""
    # in-game micro is thin/unpoliced by nature; never call a live line LIQUID.
    if category != "ingame-micro" and is_mainline(market_name, kind):
        return "LIQUID"
    base = category_thinness(category)
    # a deep-tail single/combo is effectively unpoliced -> escalate.
    if prob < 0.04 or prob > 0.96:
        return "EXTREME" if base != "LIQUID" else base
    return base


def validatable_for(category: str, market_name: str, kind: str) -> str:
    """Resolve validatability: mainline shapes have a local close (HAS_CLOSE);
    everything else inherits the category default (PRICE_ONLY/FORWARD_ONLY).

    EXCEPTION: ingame-micro is ALWAYS FORWARD_ONLY -- a live re-priced number has no
    historical close to gate against (even a live moneyline), so it can only be
    validated by forward capture."""
    if category == "ingame-micro":
        return "FORWARD_ONLY"
    if is_mainline(market_name, kind):
        return "HAS_CLOSE"
    return category_validatable(category)


def needs_forward_clv(validatable: str) -> bool:
    """Any market without a usable historical close needs the forward_capture
    clock before ANY $ statement -- the binding honesty rail."""
    return validatable in ("PRICE_ONLY", "FORWARD_ONLY")


def honesty_note(thinness: str, validatable: str) -> str:
    if validatable == "HAS_CLOSE":
        return ("liquid mainline: we MATCH the devigged close (calibration, not edge); "
                "gate vs SHIN close.")
    if thinness == "EXTREME":
        return ("thinly/unpoliced market: PRICED + CALIBRATED only; SUGGESTIVE not a $ claim; "
                "needs forward CLV; book limits cap real $.")
    return ("soft market: price + calibration are the product; any beat is SUGGESTIVE; "
            "needs forward CLV.")
