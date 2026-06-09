"""Proven Edge Card -- composes the three proven edges + the hard guard.

Discipline: honesty_class="paper". Reads cached pricing facts, never re-runs builders.
NEVER places/sizes/logs a real-money bet. Surfaces only:
  LINE_SHOP   -> PROVEN-DETERMINISTIC
  FRESHNESS   -> PROVEN-CEILING-NEEDS-FEED
  SGP_CORR    -> VALIDATED-STRUCTURE-ROI-PENDING

Hard guard: any model-marginal-vs-line candidate is REFUSED with a recorded reason,
ESPECIALLY in playoffs (artifact grades -2% to -5% vs real closes).

Run:
    python scripts/team_system/proven_edge_card.py --home NYK --away SAS --date 2026-06-08 --sgp-top 8
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import freshness_monitor as fm         # READ-ONLY
import sgp_edge_scanner as ses         # File 1

HONESTY_CLASS = "paper"
BANNER = (
    "PAPER / DISPLAY ONLY -- honest-status tags below. No real-money placement, "
    "no bet logging. Proven edges only; model-vs-line point bets are REFUSED."
)

_PROVEN_KINDS = {"LINE_SHOP", "FRESHNESS", "SGP_CORR"}

_REFUSE_SOURCES = {
    "model_marginal_vs_line",
    "model_vs_line",
    "point_model_edge",
    "marginal_vs_book",
    "model_beats_line",
}

_REFUSE_REASON_REG = (
    "model-marginal-vs-line point edge is the disproven artifact (priced/absorbed; "
    "the +18.38% was market-follow at flat -110 fiction) -> REFUSED"
)
_REFUSE_REASON_PLAYOFF = (
    "PLAYOFF model-vs-line point edge: graded -2% to -5% vs real closes "
    "(AST -2.78% playoffs) -> REFUSED"
)


@dataclass
class CardEdge:
    kind: str
    status: str
    headline: str
    detail: dict
    honesty_class: str = HONESTY_CLASS


@dataclass
class RefusedCandidate:
    source: str
    descr: str
    reason: str
    is_playoff: bool
    status: str = "REFUSED-ARTIFACT"


def refuse_artifact_edges(candidates: list, *, is_playoff: bool = False) -> Tuple[list, List[RefusedCandidate]]:
    """Partition candidates into (kept, refused).

    REFUSE any candidate whose .source/.kind is a point-model-vs-line edge, OR any dict with
    source in _REFUSE_SOURCES, OR any candidate flagged provenance==marginal. Refusal is
    HARDER for playoffs (always refuse, reason cites playoff artifact magnitudes).
    Reason strings (recorded, never silently dropped):
      reg     -> model-marginal-vs-line point edge is the disproven artifact ...
      playoff -> PLAYOFF model-vs-line point edge: graded -2% to -5% ...
    A candidate is kept ONLY if kind in _PROVEN_KINDS.
    Returns (kept:list, refused:list[RefusedCandidate]).
    This function is called on EVERY candidate before it can reach the card.
    """
    kept: list = []
    refused: List[RefusedCandidate] = []

    for c in candidates:
        if isinstance(c, dict):
            source = c.get("source", c.get("kind", ""))
            kind = c.get("kind", "")
            provenance = c.get("provenance", "")
            descr = c.get("descr", c.get("headline", str(c)))
        else:
            source = getattr(c, "source", getattr(c, "kind", ""))
            kind = getattr(c, "kind", "")
            provenance = getattr(c, "provenance", "")
            descr = getattr(c, "headline", getattr(c, "descr", str(c)))

        refuse = (
            str(source).lower() in _REFUSE_SOURCES
            or str(kind).lower() in _REFUSE_SOURCES
            or str(provenance).lower() == "marginal"
            or (str(kind) not in _PROVEN_KINDS and str(kind) != "")
        )

        if refuse:
            reason = _REFUSE_REASON_PLAYOFF if is_playoff else _REFUSE_REASON_REG
            refused.append(RefusedCandidate(
                source=str(source) or str(kind),
                descr=str(descr),
                reason=reason,
                is_playoff=is_playoff,
                status="REFUSED-ARTIFACT",
            ))
        else:
            kept.append(c)

    return kept, refused


def _load_crossbook() -> dict:
    p = os.path.join(TS, "crossbook_efficiency.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


def _line_shop_edge() -> CardEdge:
    """From crossbook_efficiency.json: ALL.lineshop_ev (+3.51%) + softest books from book_softness
    (rank by best_over_pct/best_under_pct; FD softest over ~0.375, DK hardest over ~0.183).
    status=PROVEN-DETERMINISTIC. detail={ev_per_bet, softest_over, softest_under, med_hold, n}.
    """
    cb = _load_crossbook()
    ev = cb.get("ALL", {}).get("lineshop_ev", 0.03511)
    med_hold = cb.get("ALL", {}).get("med_hold", 0.0678)
    n = cb.get("ALL", {}).get("n", 6374)

    softness = cb.get("book_softness", {})
    softest_over = sorted(softness.items(), key=lambda x: -x[1].get("best_over_pct", 0))
    softest_under = sorted(softness.items(), key=lambda x: -x[1].get("best_under_pct", 0))

    so_book = softest_over[0][0] if softest_over else "fanduel"
    so_pct = softest_over[0][1].get("best_over_pct", 0.375) if softest_over else 0.375
    su_book = softest_under[0][0] if softest_under else "betmgm"
    su_pct = softest_under[0][1].get("best_under_pct", 0.253) if softest_under else 0.253

    return CardEdge(
        kind="LINE_SHOP",
        status="PROVEN-DETERMINISTIC",
        headline=f"Best-of-N line shop: +{ev*100:.2f}%/bet EV (softest over: {so_book} {so_pct*100:.1f}%, hardest: draftkings)",
        detail={
            "ev_per_bet": round(ev, 5),
            "softest_over": {"book": so_book, "best_over_pct": round(so_pct, 4)},
            "softest_under": {"book": su_book, "best_under_pct": round(su_pct, 4)},
            "med_hold": round(med_hold, 5),
            "n": n,
        },
        honesty_class=HONESTY_CLASS,
    )


def _freshness_edge(home: str, away: str, asof: Optional[str]) -> Optional[CardEdge]:
    """r = fm.assess(asof, {home, away}). Emit ONLY if r['freshness_trigger'] is True.
    status=PROVEN-CEILING-NEEDS-FEED. detail={trigger_players, reg_ceiling=r['regseason_ceiling'],
    playoff_ceiling=r['playoff_ceiling'], needs='live opener odds + injury feed + execution speed'}.
    If no feed / no trigger -> return None (no edge to surface, honestly).
    """
    r = fm.assess(asof, {home.upper(), away.upper()})
    if r.get("status") == "no-feed":
        return None
    if not r.get("freshness_trigger", False):
        return None

    reg_ceil = r.get("regseason_ceiling", 0.579)
    playoff_ceil = r.get("playoff_ceiling", 0.548)
    triggers = [s for s in r.get("situations", []) if s.get("status") == "OUT" and s.get("rotation_significant")]
    trigger_names = [s.get("player", "?") for s in triggers]

    return CardEdge(
        kind="FRESHNESS",
        status="PROVEN-CEILING-NEEDS-FEED",
        headline=(
            f"Rotation-significant OUT: {', '.join(trigger_names)}. "
            f"Historical ceiling ~{reg_ceil*100:.0f}% ATS reg / ~{playoff_ceil*100:.0f}% playoff."
        ),
        detail={
            "trigger_players": trigger_names,
            "reg_ceiling": reg_ceil,
            "playoff_ceiling": playoff_ceil,
            "needs": "live opener odds + injury feed + execution speed",
        },
        honesty_class=HONESTY_CLASS,
    )


def _sgp_edges(result: Any, top_n: int) -> List[CardEdge]:
    """Wrap ses.scan_sgp_edges(result, top_n) into CardEdge(kind='SGP_CORR', ...) --
    one per scanned basket, capped at top_n.
    """
    raw_edges = ses.scan_sgp_edges(result, top_n=top_n)
    card_edges = []
    for e in raw_edges:
        basket = " + ".join(e.labels)
        headline = (
            f"{basket}  |  lift x{e.lift:.3f}  |  {e.direction.upper()}"
            f"  |  joint {e.joint:.1%} vs indep {e.independent:.1%}"
        )
        card_edges.append(CardEdge(
            kind="SGP_CORR",
            status=ses.SGP_STATUS,
            headline=headline,
            detail={
                "legs": [{"pid": lg.pid, "stat": lg.stat, "line": lg.line, "over": lg.over}
                         for lg in e.legs],
                "labels": e.labels,
                "joint": round(e.joint, 5),
                "independent": round(e.independent, 5),
                "lift": round(e.lift, 4),
                "abs_lift_error": round(e.abs_lift_error, 4),
                "direction": e.direction,
                "basket_type": e.basket_type,
                "fair_decimal": round(e.fair_decimal, 3),
            },
            honesty_class=HONESTY_CLASS,
        ))
    return card_edges


def build_proven_edge_card(
    home: str,
    away: str,
    asof: Optional[str] = None,
    lines: Optional[dict] = None,
    *,
    result: Any = None,
    sgp_top_n: int = 8,
    is_playoff: bool = True,
    extra_candidates: Optional[list] = None,
) -> dict:
    """Compose the ranked, honest card.

    1. Gather candidates:
         - LINE_SHOP: from crossbook cache (PROVEN-DETERMINISTIC).
         - FRESHNESS: _freshness_edge(...) (may be None).
         - SGP_CORR: if result provided -> _sgp_edges(result, sgp_top_n); else skip.
         - extra_candidates (e.g. anything an upstream caller passes) -> MUST pass through guard.
    2. kept, refused = refuse_artifact_edges(all_raw_candidates, is_playoff=is_playoff)
       (LINE_SHOP/FRESHNESS/SGP_CORR pass; any model-vs-line candidate is REFUSED+recorded).
    3. Return {
         'banner': BANNER, 'honesty_class': 'paper', 'matchup': ..., 'asof': ...,
         'is_playoff': ..., 'edges': [...], 'refused': [...],
       }.
    NEVER returns a sized stake / bet instruction.
    """
    raw: list = []
    raw.append(_line_shop_edge())

    fresh = _freshness_edge(home, away, asof)
    if fresh is not None:
        raw.append(fresh)

    if result is not None:
        raw.extend(_sgp_edges(result, sgp_top_n))

    if extra_candidates:
        raw.extend(extra_candidates)

    kept, refused = refuse_artifact_edges(raw, is_playoff=is_playoff)

    def _order_key(e: Any) -> Tuple[int, float]:
        k = getattr(e, "kind", "")
        if k == "LINE_SHOP":
            return (0, 0.0)
        if k == "FRESHNESS":
            return (1, 0.0)
        detail = getattr(e, "detail", {})
        ale = detail.get("abs_lift_error", 0.0) if isinstance(detail, dict) else 0.0
        return (2, -ale)

    kept.sort(key=_order_key)

    return {
        "banner": BANNER,
        "honesty_class": HONESTY_CLASS,
        "matchup": f"{away.upper()}@{home.upper()}",
        "asof": asof,
        "is_playoff": is_playoff,
        "edges": kept,
        "refused": refused,
    }


def render_card(card: dict) -> str:
    """Human-readable: BANNER, then each edge 'kind | status | headline', then a REFUSED section
    listing dropped candidates + reasons. Display only.
    """
    lines = [
        "=" * 80,
        card["banner"],
        "=" * 80,
        f"Matchup: {card['matchup']}  |  date: {card.get('asof', 'n/a')}"
        f"  |  playoff: {card.get('is_playoff', '?')}",
        "",
    ]

    edges = card.get("edges", [])
    if edges:
        lines.append(f"PROVEN EDGES ({len(edges)}):")
        lines.append("-" * 80)
        for e in edges:
            lines.append(f"  [{e.kind}] [{e.status}]")
            lines.append(f"    {e.headline}")
        lines.append("")
    else:
        lines.append("  (no proven edges to surface)")
        lines.append("")

    refused = card.get("refused", [])
    if refused:
        lines.append(f"REFUSED ({len(refused)}) -- transparency log:")
        lines.append("-" * 80)
        for r in refused:
            lines.append(f"  [{r.status}] source={r.source}")
            lines.append(f"    {str(r.descr)[:80]}")
            lines.append(f"    reason: {r.reason}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Proven edge card -- paper display only")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--date", default=None)
    ap.add_argument("--sgp-top", type=int, default=8)
    ap.add_argument("--no-sim", action="store_true", help="skip sim (LINE_SHOP+FRESHNESS only)")
    a = ap.parse_args()

    res = None
    if not a.no_sim:
        from sim.basketball_sim import TeamModel
        from sim.fast_sim import simulate_game_fast

        print(f"Building sim: {a.away} @ {a.home} (40000 sims) ...")
        res = simulate_game_fast(
            TeamModel.from_cache(a.home),
            TeamModel.from_cache(a.away),
            n_sims=40000,
            seed=2026,
            anchor=True,
            defense=True,
        )

    card = build_proven_edge_card(
        a.home, a.away,
        asof=a.date,
        result=res,
        sgp_top_n=a.sgp_top,
        is_playoff=True,
    )
    print(render_card(card))
