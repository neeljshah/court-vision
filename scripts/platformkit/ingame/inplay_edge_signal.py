"""scripts.platformkit.ingame.inplay_edge_signal -- PURE in-play price-divergence signal.

At one LIVE tick this answers a single question and NOTHING else: given the leak-free
in-game MODEL probability (P(home win), from predictor.predict_live -- read-only here)
and the LIVE liquid in-play PRICE, is there a calibration-justified, liquid, fresh edge
worth a paper unit, and at what tier?

    edge = model_prob - devig(live in-play price)          (HOME-aligned)

It is the in-play sibling of pm_trading.edge_signal, but it REUSES (never rebuilds):
  * the devig  -> odds_shop.devig_twoway (the vetted Shin solver), fed the Kalshi
    YES/NO pair so the price we compare against is the no-vig fair P(home).
  * the EV+tier-> odds_shop.ev_vs_price (EV = p*odds-1) -> pm_trading.policy.tier
    (the pre-registered .02/.04/.08 floors, +.01 proxy penalty). NO new floors.
  * the liquidity gate -> odds_provider.inplay_kalshi.is_liquid is applied UPSTREAM by
    the fetcher; here we additionally require a caller-supplied is_liquid flag True.

WHEN A DIVERGENCE IS LEGITIMATE vs NOISE (the load-bearing distinction):
  A divergence is tradeable ONLY when ALL hold:
    1. calibration_justified=True -- the model's lean comes from the PROVEN prior-
       conditioning or a GATE-PASSED layer (the caller asserts this; an un-gated raw
       micro-state lean is NOISE and is passed False -> no_bet).
    2. is_liquid=True            -- the price cleared inplay_kalshi.is_liquid.
    3. is_fresh=True             -- the snapshot is fresh (stale-never-green).
    4. EV clears a tier floor    -- below floor -> no_bet (tier None).
  Any failure -> action="no_bet" with an explicit reason. We NEVER trade an untraded /
  illiquid / stale price as if liquid, and NEVER trade an un-justified divergence.

HONESTY (binding): UNITS / probability only -- there is NO $ / roi / pnl / stake$ /
edge_dollars field anywhere. edge_claimed is always False. CLV (graded downstream by the
existing replay/aggregate harness) is the ONLY yardstick; a positive edge here is a
PROPOSAL to capture+grade, never a realized profit. LEAK-FREE: model_prob is computed by
the caller from state-as-of-this-tick only; the close is never an input here.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; PURE (no file/
network IO, no placement, no global state); never edits src/kernel/live_grade/policy.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from scripts.platformkit import odds_shop as _shop
from scripts.platformkit.econ.cost_model import kalshi_fee_per_contract

try:  # package import (normal runtime)
    from scripts.platformkit.pm_trading import policy as _policy
except Exception:  # pragma: no cover -- policy import must not be load-bearing at import
    _policy = None  # type: ignore[assignment]

# The side both numbers are aligned to (mirrors live_grade.PAIR_SIDE -- a misaligned pair
# manufactures fake edge). model_prob = P(home win); devigged price = no-vig P(home).
SIDE = "home"


def _clip01(p: Any) -> Optional[float]:
    """Coerce to a prob in [0,1]; None if non-numeric / out of range (never fabricated)."""
    try:
        v = float(p)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def devig_home_price(yes_home_prob: float,
                     yes_away_prob: Optional[float] = None) -> Optional[float]:
    """No-vig fair P(home) from the in-play YES(home)/YES(away) implied-prob pair.

    Reuses odds_shop.devig_twoway (the vetted Shin solver) on decimal odds derived from
    the two YES legs. When only the home leg is known (a single liquid side), the away
    leg is taken as its complement (1 - home) -- a proper two-way book Kalshi always
    quotes; the Shin solver still removes the (small) overround. Returns the fair P(home)
    in [0,1], or None if the legs are unusable (VOID -- never a fabricated price).
    """
    ph = _clip01(yes_home_prob)
    if ph is None or ph <= 0.0 or ph >= 1.0:
        return None
    pa = _clip01(yes_away_prob)
    if pa is None or pa <= 0.0 or pa >= 1.0:
        pa = 1.0 - ph
    try:
        if (ph + pa) < 1.0 - 1e-9:
            # booksum<=1: devig_twoway now normalizes instead of raising
            # (634fdd1a) -- a degenerate pair stays VOID here, never a signal.
            return None
        dh, da = 1.0 / ph, 1.0 / pa  # implied prob -> decimal odds
        fair_h, _fair_a = _shop.devig_twoway(dh, da)
    except Exception:  # noqa: BLE001 -- a degenerate pair is VOID, not a crash
        return None
    return _clip01(fair_h)


def evaluate(*, model_prob: Any,
             yes_home_prob: Any,
             yes_away_prob: Any = None,
             obtainable_decimal: Any = None,
             calibration_justified: bool,
             is_liquid: bool,
             is_fresh: bool = True,
             clv_is_proxy: bool = True,
             min_ev: Any = None) -> Dict[str, Any]:
    """PURE: evaluate ONE live in-play tick into a tiered, gated paper signal.

    Computes the devigged home price, the edge = model_prob - devigged_price, and the EV
    at the OBTAINABLE price (default = the devigged fair, i.e. the no-vig line you face),
    then tiers via the pre-registered policy floors. Returns a dict with action in
    {"bet","no_bet"}, tier in {"A","B","C",None}, side, edge, model_prob, devigged_price,
    ev, and a reason. NEVER raises. No $ field. edge_claimed=False.

    GATES (all must pass for action="bet"):
      calibration_justified AND is_liquid AND is_fresh AND tier is not None.
    A failure of any -> action="no_bet" with a specific reason (illiquid / stale /
    not_justified / below_floor / bad_price).
    """
    out: Dict[str, Any] = {
        "action": "no_bet", "tier": None, "side": SIDE,
        "model_prob": None, "devigged_price": None, "edge": None, "ev": None,
        "calibration_justified": bool(calibration_justified),
        "is_liquid": bool(is_liquid), "is_fresh": bool(is_fresh),
        "clv_is_proxy": bool(clv_is_proxy), "reason": "", "edge_claimed": False,
        "units": "probability",
    }
    mp = _clip01(model_prob)
    if mp is None:
        out["reason"] = "bad_model_prob"
        return out
    devig_p = devig_home_price(yes_home_prob, yes_away_prob)
    if devig_p is None:
        out["reason"] = "bad_price"
        return out
    out["model_prob"] = mp
    out["devigged_price"] = devig_p
    out["edge"] = mp - devig_p

    # Liquidity / freshness / justification gates BEFORE any EV claim -- an illiquid or
    # stale or un-justified divergence is NOISE and is never tiered into a bet.
    if not bool(is_liquid):
        out["reason"] = "illiquid"
        return out
    if not bool(is_fresh):
        out["reason"] = "stale"
        return out
    if not bool(calibration_justified):
        out["reason"] = "not_calibration_justified"
        return out

    # TWO-SIDED EV. The model_prob / devigged_price kept above stay HOME-aligned (the grade
    # series is always home-aligned -- a misaligned pair manufactures fake edge). But the BET
    # may be on EITHER side: when the model's lean is on the AWAY team (mp < devig_p) the home
    # EV is negative while the away EV is positive. The old code evaluated ONLY home and so
    # silently discarded every away-side edge (~half the opportunity space) -- the dominant
    # reason the in-game channel placed almost nothing. We now price both legs at the no-vig
    # fair line and take the +EV side. (A LARGE EV here usually means the in-game MODEL is
    # miscalibrated, not a real edge; CLV grades the truth -- paper/measurement, never a $ claim.)
    dec_home = _to_decimal(obtainable_decimal)
    if dec_home is None:
        dec_home = 1.0 / devig_p if devig_p > 0.0 else None
    away_fair = 1.0 - devig_p
    dec_away = 1.0 / away_fair if away_fair > 0.0 else None
    if dec_home is None or dec_home <= 1.0 or dec_away is None or dec_away <= 1.0:
        out["reason"] = "bad_price"
        return out
    ev_home = _shop.ev_vs_price(mp, dec_home)
    ev_away = _shop.ev_vs_price(1.0 - mp, dec_away)
    # Take the side with the higher EV (exactly one is positive when mp != devig_p).
    if ev_away > ev_home:
        side, ev, bet_mp, bet_fair, dec = "away", ev_away, 1.0 - mp, away_fair, dec_away
    else:
        side, ev, bet_mp, bet_fair, dec = "home", ev_home, mp, devig_p, dec_home
    # The paper day-trader quotes at the selected model fair probability. Apply
    # the verified maker curve before its existing tier threshold is consumed.
    # The value is deliberately named units: no currency amount is exposed.
    maker_fee_units = kalshi_fee_per_contract(bet_mp, "maker")
    net_ev = ev - maker_fee_units
    out["side"] = side
    out["gross_ev"] = ev
    out["maker_fee_units"] = maker_fee_units
    out["ev"] = net_ev
    out["obtainable_decimal"] = dec
    out["bet_model_prob"] = bet_mp
    out["bet_devigged_price"] = bet_fair

    tier = _tier(ev=net_ev, model_prob=bet_mp, market_prob=bet_fair, clv_is_proxy=clv_is_proxy)
    # RELAXED in-game floor (opt-in via min_ev): when the pre-registered policy floor is not
    # cleared but the EV still beats an explicit lower floor, assign the marginal tier "C".
    # This is a LOWER-CONFIDENCE, honestly-graded paper bet (CLV will tell the truth) -- it is
    # NOT a claim of edge. Default min_ev=None -> behaviour is identical to the strict floor.
    relaxed = False
    if tier is None and min_ev is not None:
        try:
            if net_ev >= float(min_ev) and net_ev > 0.0:
                tier, relaxed = "C", True
        except (TypeError, ValueError):
            pass
    out["tier"] = tier
    out["relaxed_floor"] = relaxed
    if tier is None:
        out["reason"] = "below_floor"
        return out
    out["action"] = "bet"
    out["reason"] = "ok_relaxed" if relaxed else "ok"
    return out


def _to_decimal(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 1.0 else None


def _tier(*, ev: float, model_prob: float, market_prob: float,
          clv_is_proxy: bool) -> Optional[str]:
    """Delegate to pm_trading.policy.tier (pre-registered floors). None if policy absent."""
    if _policy is None:  # pragma: no cover -- defensive only
        return None
    return _policy.tier(ev=ev, model_prob=model_prob, market_prob=market_prob,
                        clv_is_proxy=clv_is_proxy)


__all__ = ["SIDE", "devig_home_price", "evaluate"]
