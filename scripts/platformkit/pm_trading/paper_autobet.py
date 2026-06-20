"""paper_autobet.py -- PAPER auto-bet runner that builds a CLV track record.

Closes the honest loop: given a slate of edge candidates (model prob vs the
price you can actually get), it SIZES each with a risk rule (fractional Kelly
or a flat unit, under a max-exposure cap), then RECORDS the survivors to the
CLV ledger as PAPER bets -- and, when a closing line is supplied, SETTLES them
so the CLV summary updates.

   edge  ->  size  ->  paper-record  ->  settle  ->  CLV

HONEST RAILS (binding -- this file can NEVER move real money):
  * NO NETWORK. Pure local function: builds candidates -> writes JSONL.
  * Every recorded bet carries executed=False and channel="paper". It calls
    scripts.platformkit.clv_ledger.record_bet, which itself stamps
    executed=False -- this tool never reaches a venue or a book API.
  * NOT an edge claim. A positive paper CLV here is a HYPOTHESIS to forward-
    test; real money stays gated behind a proven multi-week forward CLV that
    survives the eval_gate (pm_trading.ENABLED is OFF, separately).
  * Devig / CLV math is reused from the vetted clv_ledger, never re-derived.

Build only under scripts/platformkit/; <=300 LOC; no secrets; no $-edge claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.odds_shop import ev_vs_price
from scripts.platformkit.pm_trading.stake_units_normalize import (
    normalize as _normalize_units,
    DEFAULT_UNIT_SIZE,
)

# channel marker proving these are paper records, never a placed/executed bet.
CHANNEL_PAPER = "paper"


@dataclass
class EdgeCandidate:
    """One tradable opportunity on a two-way market.

    *taken_decimal* is the price you could actually get on *side*. Optional
    closing prices let the runner settle immediately into a CLV record; omit
    them to leave the bet open for later settlement.
    """
    sport: str
    matchup: str
    side: str                       # "home" | "away"
    taken_decimal: float
    model_prob: float               # calibrated P(side) in [0, 1]
    taken_book: str = "paper_book"
    event_id: str = ""
    closing_decimal_home: Optional[float] = None
    closing_decimal_away: Optional[float] = None


@dataclass
class AutoBetConfig:
    """Risk rule for paper sizing.

    sizing="kelly": fractional-Kelly fraction-of-bankroll, hard-clamped to
        kelly_cap, then dollar-capped by max_stake.
    sizing="flat":  a flat unit_stake on every +EV candidate.
    Either way, total staked across the slate is capped at max_total_exposure.

    Dollar amounts (bankroll, max_stake, max_total_exposure, unit_stake) are
    used ONLY for internal exposure-cap math and are NEVER recorded in the
    ledger.  The ledger receives normalized stake_units in [0, 10] computed by
    dividing the dollar stake by unit_size before passing to record_bet.
    """
    bankroll: float = 10_000.0
    sizing: str = "kelly"           # "kelly" | "flat"
    kelly_fraction: float = 0.25    # quarter-Kelly
    kelly_cap: float = 0.05         # never risk > 5% of bankroll on one bet
    unit_stake: float = 100.0       # flat-sizing stake (dollars, internal only)
    max_stake: float = 1_000.0      # per-bet dollar cap (internal exposure math)
    max_total_exposure: float = 5_000.0  # total dollars staked cap (internal)
    min_ev: float = 0.0             # require EV per $1 strictly above this
    # Base dollar value of one unit for ledger normalization.  Default $100 so
    # a $100 flat unit records as 1.0u, a $1000 kelly cap records as 10.0u.
    unit_size: float = DEFAULT_UNIT_SIZE


def _kelly_fraction_decimal(prob: float, decimal_odds: float) -> float:
    """Full-Kelly fraction for a decimal-odds bet; 0.0 if no positive edge.

    b = decimal_odds - 1 (net odds). f* = (b*p - (1-p)) / b = p - (1-p)/b.
    """
    p = float(prob)
    b = float(decimal_odds) - 1.0
    if b <= 0.0 or not (0.0 < p < 1.0):
        return 0.0
    f = p - (1.0 - p) / b
    return f if f > 0.0 else 0.0


def size_stake(cand: EdgeCandidate, cfg: AutoBetConfig) -> float:
    """Dollar stake for one candidate under *cfg*. 0.0 => skip (no +EV)."""
    if ev_vs_price(cand.model_prob, cand.taken_decimal) <= cfg.min_ev:
        return 0.0
    if cfg.sizing == "flat":
        return float(min(cfg.unit_stake, cfg.max_stake))
    if cfg.sizing != "kelly":
        raise ValueError("sizing must be 'kelly' or 'flat', got %r" % cfg.sizing)
    full = _kelly_fraction_decimal(cand.model_prob, cand.taken_decimal)
    if full <= 0.0:
        return 0.0
    frac = min(full * cfg.kelly_fraction, cfg.kelly_cap)
    return float(min(frac * cfg.bankroll, cfg.max_stake))


def run_slate(
    candidates: Sequence[EdgeCandidate],
    cfg: Optional[AutoBetConfig] = None,
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Size + paper-record (+ settle when a close is given) a whole slate.

    NO NETWORK. Returns a summary dict with the per-bet rows, the dollars
    staked, and the updated clv_summary over the ledger. Every recorded row is
    executed=False, channel="paper".
    """
    cfg = cfg or AutoBetConfig()
    bets: List[Dict[str, Any]] = []
    staked_total = 0.0
    n_recorded = 0
    n_settled = 0
    for cand in candidates:
        stake = size_stake(cand, cfg)
        if stake <= 0.0:
            bets.append({"matchup": cand.matchup, "side": cand.side,
                         "stake_units": 0.0, "status": "skipped_no_edge"})
            continue
        # total-exposure cap: trim, and stop once there is no room left.
        room = cfg.max_total_exposure - staked_total
        if room <= 0.0:
            bets.append({"matchup": cand.matchup, "side": cand.side,
                         "stake_units": 0.0, "status": "skipped_exposure_cap"})
            continue
        stake = min(stake, room)
        # Normalize dollars -> units before recording; internal $ is kept for
        # exposure-cap math above (staked_total, room) but NEVER written to the
        # ledger.  stake_units_normalize.normalize clamps to [0, 10].
        units = _normalize_units(stake, unit_size=cfg.unit_size)
        rec = _clv.record_bet(
            cand.sport, cand.matchup, cand.side, cand.taken_book,
            cand.taken_decimal, model_prob=cand.model_prob,
            stake_units=units, path=path)
        # mark the paper channel WITHOUT mutating the appended open row: we add
        # the marker to our in-memory copy for the summary only. The ledger row
        # already carries executed=False (record_bet's invariant).
        rec = dict(rec)
        rec["channel"] = CHANNEL_PAPER
        assert rec["executed"] is False  # honesty invariant, belt-and-braces
        staked_total += stake
        n_recorded += 1
        row: Dict[str, Any] = {"matchup": cand.matchup, "side": cand.side,
                               "taken_decimal": cand.taken_decimal,
                               "stake_units": round(units, 6), "executed": False,
                               "channel": CHANNEL_PAPER, "status": "recorded"}
        # settle immediately if a closing line was supplied
        if (cand.closing_decimal_home is not None
                and cand.closing_decimal_away is not None):
            settled = _clv.settle_closing_line(
                rec, cand.closing_decimal_home, cand.closing_decimal_away)
            settled["channel"] = CHANNEL_PAPER
            _clv.append_settlement(settled, path=path)
            row["clv_pct"] = settled["clv_pct"]
            row["beat_close"] = settled["beat_close"]
            row["status"] = "settled"
            n_settled += 1
        bets.append(row)
    summary = _clv.clv_summary(_clv.load_ledger(path))
    return {
        "channel": CHANNEL_PAPER,
        "executed_any": False,           # invariant: never a real bet
        "n_candidates": len(candidates),
        "n_recorded": n_recorded,
        "n_settled": n_settled,
        "staked_total": round(staked_total, 6),
        "max_total_exposure": cfg.max_total_exposure,
        "bets": bets,
        "clv_summary": summary,
    }


def _demo() -> Dict[str, Any]:
    """Deterministic paper demo into a throwaway ledger (no network, no money)."""
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="paper_autobet_")) / "ledger.jsonl"
    slate = [
        # +EV home (1.95 implied 0.513 vs model 0.58); close 1.80/2.10 -> beat
        EdgeCandidate("nba", "BOS@NYK", "home", 1.95, 0.58,
                      closing_decimal_home=1.80, closing_decimal_away=2.10),
        # -EV (model below price) -> skipped, no record
        EdgeCandidate("nba", "LAL@DEN", "away", 2.50, 0.30,
                      closing_decimal_home=1.50, closing_decimal_away=2.70),
    ]
    return run_slate(slate, AutoBetConfig(bankroll=10_000.0, sizing="kelly"),
                     path=tmp)


if __name__ == "__main__":
    out = _demo()
    print("PAPER AUTOBET (demo, NOT a real result -- executed_any=%s, channel=%s)"
          % (out["executed_any"], out["channel"]))
    print("  recorded=%d settled=%d staked=$%.2f / cap $%.0f"
          % (out["n_recorded"], out["n_settled"], out["staked_total"],
             out["max_total_exposure"]))
    print("  CLV:", out["clv_summary"])
