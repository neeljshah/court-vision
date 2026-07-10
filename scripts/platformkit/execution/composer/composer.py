"""scripts.platformkit.execution.composer.composer -- best-bets portfolio
composer (Lane B4). Answers "given everything the system believes RIGHT NOW,
what is the best SIMULTANEOUS set of paper positions" across sports. Sizes
are in UNITS (the flat_unit stake pm_trading.policy.stake_units already
stamped on every card as card['units'] -- this module never resizes a stake,
it only caps how many concurrent CORRELATED positions are allowed). CLV-
expectation language only; no $/ROI/bankroll claim.

PIPELINE (score/collapse/cap are pure and independently testable; only
collect_candidates() touches live feeds):
  1. collect_candidates(sports) -- READ ONLY pull of bettable cards per sport
     from predict_service.bestbets_compute (the same compute layer the live
     board uses; never re-derives model/market prices).
  2. score_candidate(card)      -- calibrated divergence x confidence, reusing
     divergence_rank.divergence_score (the same metric bestbets_compute
     already ranks by) times the composite sharpness 'confidence' field
     compute_wiring already stamped (BBQ5-2).
  3. collapse_correlated(cards) -- SAME-GAME cap: within one (sport, game_id)
     only the single best-scored leg survives (moneyline/spread/total/both
     sides of the same event are correlated legs of ONE outcome).
  4. cap_exposure(cards)        -- SLATE caps: PER_TEAM_SLATE_CAP concurrent
     positions sharing a team token (covers doubleheaders / back-to-backs
     without banning them outright), SLATE_MAX_POSITIONS overall. Caps the
     COUNT of positions; never rescales a stake.
  5. compose(cards)             -- 1-4 composed, ranked by score descending.

NEVER weights or gates by the retired meta-label divergence-bucket table
(scripts/platformkit/execution/fill_model/meta_label_buckets.py):
ARTIFACT_CONFIRMED, no bucket replicates out-of-corpus (2026-07-11 replication
run) -- see test_composer.py::test_no_meta_label_weighting.

INVARIANTS: UNITS not $; no bankroll/pnl/roi field; leak-free (as-of the
instant collect_candidates() is called, nothing peeks forward); <=300 LOC;
ASCII only; pure functions never raise (garbage in -> [] / 0.0 out).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from scripts.platformkit.bestbets.divergence_rank import DEFAULT_SIGMA, divergence_score

# Sports the entry-timing lane (B1) already covers -- mirrored here so the
# composer's operational timing hint (see cli.py) always has a matching key.
SPORTS_DEFAULT: Tuple[str, ...] = (
    "nba", "mlb", "tennis", "soccer", "soccer_intl", "wnba", "npb", "kbo",
)

# Pre-registered caps (not tuned per-slate).
PER_TEAM_SLATE_CAP: int = 2     # a team appears in at most this many composed positions
SLATE_MAX_POSITIONS: int = 20   # overall portfolio cap

_BETTABLE_TIERS = frozenset({"A", "B", "C"})


def score_candidate(card: Dict[str, Any]) -> float:
    """calibrated divergence x confidence. Reuses divergence_rank.divergence_score
    (the metric bestbets_compute already ranks by) and the composite 'confidence'
    field already on the card (compute_wiring / confidence_score.score_card).
    Never raises; garbage input -> 0.0."""
    if not isinstance(card, dict):
        return 0.0
    try:
        sigma = card.get("sigma")
        div = divergence_score(card.get("model_prob"), card.get("market_prob"),
                               sigma if sigma is not None else DEFAULT_SIGMA)
        conf = float(card.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(div) or not math.isfinite(conf):
        return 0.0
    return div * conf


def _team_tokens(card: Dict[str, Any]) -> Tuple[str, ...]:
    """Best-effort team names parsed from 'matchup' ("Home vs Away"); empty
    tuple when unparseable (fails open -- no team-cap applied to that card)."""
    m = str(card.get("matchup") or "")
    if " vs " not in m:
        return ()
    home, _, away = m.partition(" vs ")
    return tuple(t.strip() for t in (home, away) if t.strip())


def _is_bettable(card: Any) -> bool:
    return (isinstance(card, dict)
            and str(card.get("decision", "")) == "bet"
            and str(card.get("tier") or "").upper() in _BETTABLE_TIERS)


def collapse_correlated(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """SAME-GAME cap: keep only the best-scored leg per (sport, game_id).
    Requires '_score' already set on each card (compose() sets it before
    calling this). Empty input -> []."""
    best: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for c in cards:
        key = (str(c.get("sport", "")), str(c.get("game_id", "")))
        if key not in best or c.get("_score", 0.0) > best[key].get("_score", 0.0):
            best[key] = c
    return list(best.values())


def cap_exposure(cards: List[Dict[str, Any]], *,
                  per_team_cap: int = PER_TEAM_SLATE_CAP,
                  slate_max: int = SLATE_MAX_POSITIONS) -> List[Dict[str, Any]]:
    """SLATE caps: admit highest-'_score' cards first, skipping any that would
    push a team token over per_team_cap or the slate over slate_max. Caps the
    COUNT of concurrent positions; never resizes a stake. Empty input -> []."""
    ordered = sorted(cards, key=lambda c: c.get("_score", 0.0), reverse=True)
    team_counts: Dict[str, int] = {}
    admitted: List[Dict[str, Any]] = []
    for c in ordered:
        if len(admitted) >= slate_max:
            break
        teams = _team_tokens(c)
        if any(team_counts.get(t, 0) >= per_team_cap for t in teams):
            continue
        admitted.append(c)
        for t in teams:
            team_counts[t] = team_counts.get(t, 0) + 1
    return admitted


def compose(cards: List[Dict[str, Any]], *,
            per_team_cap: int = PER_TEAM_SLATE_CAP,
            slate_max: int = SLATE_MAX_POSITIONS) -> List[Dict[str, Any]]:
    """Full pipeline: filter bettable -> score -> collapse same-game -> cap
    exposure -> rank by score descending. Pure; never raises; [] on empty or
    all-garbage input."""
    if not cards:
        return []
    bettable = [c for c in cards if _is_bettable(c)]
    for c in bettable:
        c["_score"] = score_candidate(c)
    survivors = collapse_correlated(bettable)
    capped = cap_exposure(survivors, per_team_cap=per_team_cap, slate_max=slate_max)
    capped.sort(key=lambda c: c.get("_score", 0.0), reverse=True)
    return capped


def collect_candidates(sports: Tuple[str, ...] = SPORTS_DEFAULT) -> List[Dict[str, Any]]:
    """IO: pull today's bettable cards per sport from bestbets_compute (READ
    ONLY reuse of the live compute layer). Never raises: a sport whose compute
    call errors contributes no cards."""
    from predict_service.bestbets_compute import compute_best_bets  # noqa: PLC0415
    out: List[Dict[str, Any]] = []
    for sport in sports:
        try:
            res = compute_best_bets(sport)
            if isinstance(res, dict):
                out.extend(res.get("cards") or [])
        except Exception:  # noqa: BLE001 -- one sport's feed failure never sinks the board
            continue
    return out


__all__ = [
    "SPORTS_DEFAULT", "PER_TEAM_SLATE_CAP", "SLATE_MAX_POSITIONS",
    "score_candidate", "collapse_correlated", "cap_exposure", "compose",
    "collect_candidates",
]
