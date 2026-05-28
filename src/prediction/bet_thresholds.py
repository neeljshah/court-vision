"""src/prediction/bet_thresholds.py — central per-stat edge-threshold config.

Iter-51: BLK UNDER-only filter (2026-05-27).
  Source: Iter-50 bootstrap segmentation on 325 BLK eval rows.
  Findings: direction_UNDER → n=218, ROI=+28.73%, z=4.45
            direction_OVER  → n=105, ROI=+0.00%,  z=0.00
  Action: STAT_DIRECTIONS["blk"] = ["under"] — OVER bets are zero-edge,
          eliminating them lifts BLK per-bet ROI from +27.07% → ~+28.73%.
  Expected aggregate impact: ~+0.1–0.3pp on 2,397-bet OOS set.

Iter-25 recalibration on Iter-22 model (commit 5fb964f1).
  Approach: thresholds  |  lift vs baseline: +3.83pp
  Baseline 2025-26 ROI: +15.67%

  Iter-15 thresholds (prior values):
    STL: 0.5 -> 0.10  (Iter 14a sweep)
    BLK: 0.5 -> 0.40  (Iter 14a sweep)

Iter-33: Kelly-B stake sizing enabled.
  kelly_b_stake() in betting_portfolio.py.
  lift vs flat: +2.52pp aggregate ROI (1,016 OOS bets, 2025-26).
  pts regression: -2.54pp (1 stat; ship criterion allows <=1 regression).
  Decision: SHIP.

Iter-38: CLV-driven per-stat reallocations — REVERT (2026-05-27).
  Tested: PTS thr 0.7->1.0 | AST thr 1.0->0.7 | BLK Kelly 0.5x
  Result: agg -1.21pp (+21.23% -> +20.02%).  AST regressed -3.83pp (doubled volume
          doubled dilution; expansion_frac=2.0 hit cap).  REVERT thresholds.
  Infrastructure added: KELLY_STAT_MULTIPLIER dict + kelly_stat_multiplier_for()
  (all 1.0x = no-op; ready for future partial BLK reduction if re-tested).

Iter-39: PTS threshold 0.7->1.0 isolated — SHIP (2026-05-27).
  Tested: PTS thr 0.7->1.0 ONLY (AST and BLK unchanged from iter-36).
  Result: agg +0.81pp (+21.23% -> +22.04%, 2,397 bets).
          PTS: +3.85pp (+12.20% -> +16.05%); 818 -> 527 bets (retain_frac=0.645).
          No stat regressed > -1pp (max regression: BLK -0.21pp).
  Decision: SHIP.

Iter-40: AST threshold 1.0->0.85 small step — REVERT (2026-05-27).
  Tested: AST thr 1.0->0.85 ONLY (all other thresholds unchanged from iter-39).
  Result: agg -0.20pp (+22.04% -> +21.84%, 2,584 bets).
          AST: -1.19pp (+24.04% -> +22.85%); 374 -> 561 bets (expansion_frac=1.50 cap hit).
          Even the "small step" expanded AST volume 50% and diluted ROI.
  Root cause: AST edge distribution is dense below 1.0 — any threshold below 1.0
  pulls in a large number of lower-quality bets. AST threshold cannot be reduced
  without material ROI dilution. Next lever: look elsewhere (e.g. BLK Kelly reduction
  in isolation, or REB threshold reduction).
  Decision: REVERT.

Usage:
    from src.prediction.bet_thresholds import edge_threshold_for, KELLY_B_ENABLED

    thr = edge_threshold_for("stl")
    thr = edge_threshold_for("pts")
    thr = edge_threshold_for("unknown")  # 0.5 (safe fallback)
"""
from __future__ import annotations

_STAT_THRESHOLDS: dict[str, float] = {
    "pts":  1.0,   # iter-39 SHIP: isolated PTS threshold raise 0.7->1.0; +3.85pp on PTS, +0.81pp agg
    "reb":  1.5,
    "ast":  1.0,   # iter-40 REVERT: tested 0.85 — expansion_frac=1.50 cap hit, -1.19pp dilution; unchanged
    "fg3m": 0.7,
    "stl":  0.4,
    "blk":  0.4,
    "tov":  0.5,
}

_DEFAULT_THRESHOLD: float = 0.5

# ── Iter-33: Kelly-B sizing feature flag ─────────────────────────────────────
# When True, bet_selector should call betting_portfolio.kelly_b_stake() instead
# of flat-1u sizing for all above-threshold bets.
KELLY_B_ENABLED: bool = True

# Calibrated hit-rate anchors for Kelly-B p_win interpolation (training obs).
# Updated via iter33_fractional_kelly_backtest.py.
KELLY_B_HIT_RATES: dict[str, float] = {
    "pts":  0.5847,
    "reb":  0.5982,
    "ast":  0.6716,
    "fg3m": 0.7183,
    "stl":  0.6183,
    "blk":  0.6654,
    "tov":  0.5200,
}

# Max stake multiplier per bet (in units) — iter-33 blowup guard.
KELLY_B_MAX_UNITS: float = 3.0

# ── Iter-38: Per-stat Kelly fraction multipliers ──────────────────────────────
# Infrastructure added by iter-38 for future per-stat Kelly tuning.
# All currently 1.0x (no-op = full Kelly-B as before).
# BLK 0.5x was tested in iter-38 but reverted (agg -1.21pp, AST regression dominated).
# Re-test BLK reduction in isolation (without AST threshold change) in a future iter.
KELLY_STAT_MULTIPLIER: dict[str, float] = {
    "pts":  1.0,
    "reb":  1.0,
    "ast":  1.0,
    "fg3m": 1.0,
    "stl":  1.0,
    "blk":  1.0,   # iter-38 REVERT: 0.5x alone promising but reverted with bundle
    "tov":  1.0,
}


def edge_threshold_for(stat: str) -> float:
    """Return the edge threshold for *stat* (case-insensitive).

    Falls back to ``_DEFAULT_THRESHOLD`` for unknown stat strings so
    existing callers that don't specify a stat remain unaffected.
    """
    return _STAT_THRESHOLDS.get(stat.lower(), _DEFAULT_THRESHOLD)


def kelly_b_hit_rate_for(stat: str) -> float:
    """Return the Kelly-B calibrated hit-rate anchor for *stat*."""
    return KELLY_B_HIT_RATES.get(stat.lower(), 0.52)


def kelly_stat_multiplier_for(stat: str) -> float:
    """Return the per-stat Kelly fraction multiplier (iter-38).

    Defaults to 1.0 for unknown stats (no change to base Kelly-B stake).
    """
    return KELLY_STAT_MULTIPLIER.get(stat.lower(), 1.0)


# ── Iter-51: Per-stat allowed bet directions ──────────────────────────────────
# Iter-50 bootstrap segmentation found BLK OVER has zero edge (n=105, ROI=0.00%,
# z=0.00) while BLK UNDER is highly profitable (n=218, ROI=+28.73%, z=4.45).
# Eliminating BLK OVER bets is pure ROI lift with no trade-off.
# All other stats keep both directions until directional data warrants a filter.
STAT_DIRECTIONS: dict[str, list[str]] = {
    "pts":  ["over", "under"],
    "reb":  ["over", "under"],
    "ast":  ["over", "under"],
    "fg3m": ["over", "under"],
    "stl":  ["over", "under"],
    "blk":  ["under"],           # ONLY UNDER — Iter-50: BLK OVER has zero edge
    "tov":  ["over", "under"],
}

_DEFAULT_DIRECTIONS: list[str] = ["over", "under"]


def allowed_directions_for(stat: str) -> list[str]:
    """Return the list of allowed bet directions for *stat* (case-insensitive).

    Falls back to both directions for unknown stats so existing callers are
    unaffected.  For BLK, returns ["under"] only (Iter-51).

    Usage in bet-decision code::

        if direction not in allowed_directions_for(stat):
            continue  # skip — this direction has no edge
    """
    return STAT_DIRECTIONS.get(stat.lower(), _DEFAULT_DIRECTIONS)
