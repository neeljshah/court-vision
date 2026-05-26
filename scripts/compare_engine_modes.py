"""compare_engine_modes.py — R32_Y6 multi5 vs MLP engine-mode compare.

Runs the R23_P8 live recommendation engine TWICE — once with
``M2_FAMILY_USE_MLP=0`` (multi5 ensemble) and once with
``M2_FAMILY_USE_MLP=1`` (R31_X3 multitask MLP) — and quantifies how the
operator's bet slate would differ.

The flag itself flips game-level total/spread/home_pts/away_pts predictions
(scripts/game_models.py `_predict_m2_family`). When the player-prop pipeline
references those values (directly or via cached features), the recommended
slate diverges. When it does not, the comparison correctly reports a
jaccard of 1.0 — that is the load-bearing finding the operator needs:
*"would I have placed different bets today?"*.

Public API
----------
    compare_modes(
        bankroll: float = 1000.0,
        top: int = 20,
        date: str | None = None,
        min_edge: float = 0.03,
        top_overlap_k: list[int] = (5, 10, 20),
        predictions_path: str | None = None,
        lines_dir: str | None = None,
        injury_parquet_path: str | None = None,
    ) -> dict

CLI
---
    python scripts/compare_engine_modes.py \
        --bankroll 1000 --top 20 --min-edge 0.03 --top-overlap-k 5,10,20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date_cls
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


# ============================================================================ #
# Bet identity + jaccard math                                                   #
# ============================================================================ #
def _bet_key(b: Dict[str, Any]) -> Tuple[str, str, str, str, float]:
    """A bet is uniquely identified by (player, stat, side, book, line)."""
    return (
        str(b.get("player", "")).strip().lower(),
        str(b.get("stat", "")).strip().lower(),
        str(b.get("side", "")).strip().upper(),
        str(b.get("book", "")).strip().lower(),
        round(float(b.get("line", 0.0)), 2),
    )


def jaccard(a: Iterable, b: Iterable) -> float:
    """Jaccard similarity of two iterables interpreted as sets.

    Both empty -> 1.0 (degenerate but consistent: identical means identical).
    """
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not (sa | sb):
        return 1.0
    return len(sa & sb) / len(sa | sb)


def topk_overlap(
    recs_a: List[Dict[str, Any]],
    recs_b: List[Dict[str, Any]],
    k: int,
) -> Dict[str, Any]:
    """Compute set-level top-K overlap between two ranked rec lists."""
    ka = [_bet_key(b) for b in recs_a[:k]]
    kb = [_bet_key(b) for b in recs_b[:k]]
    sa, sb = set(ka), set(kb)
    return {
        "k":             int(k),
        "n_a":           len(sa),
        "n_b":           len(sb),
        "overlap":       len(sa & sb),
        "jaccard":       round(jaccard(sa, sb), 4),
        "only_a":        sorted([list(t) for t in (sa - sb)]),
        "only_b":        sorted([list(t) for t in (sb - sa)]),
    }


# ============================================================================ #
# Per-bet delta on overlapping bets                                             #
# ============================================================================ #
def overlap_deltas(
    recs_a: List[Dict[str, Any]],
    recs_b: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """For bets in BOTH slates, summarise the edge / kelly / stake deltas."""
    idx_a = {_bet_key(b): b for b in recs_a}
    idx_b = {_bet_key(b): b for b in recs_b}
    shared = sorted(set(idx_a) & set(idx_b))
    per_bet: List[Dict[str, Any]] = []
    sum_edge = 0.0
    sum_kelly = 0.0
    sum_stake = 0.0
    abs_edge = 0.0
    abs_kelly = 0.0
    abs_stake = 0.0
    for key in shared:
        a = idx_a[key]
        b = idx_b[key]
        d_edge = float(b.get("edge", 0.0)) - float(a.get("edge", 0.0))
        d_kelly = float(b.get("kelly_pct", 0.0)) - float(a.get("kelly_pct", 0.0))
        d_stake = float(b.get("stake_dollars", 0.0)) - float(a.get("stake_dollars", 0.0))
        sum_edge += d_edge
        sum_kelly += d_kelly
        sum_stake += d_stake
        abs_edge += abs(d_edge)
        abs_kelly += abs(d_kelly)
        abs_stake += abs(d_stake)
        per_bet.append({
            "player":      a.get("player"),
            "stat":        a.get("stat"),
            "side":        a.get("side"),
            "book":        a.get("book"),
            "line":        a.get("line"),
            "edge_multi5": a.get("edge"),
            "edge_mlp":    b.get("edge"),
            "edge_delta":  round(d_edge, 4),
            "kelly_multi5": a.get("kelly_pct"),
            "kelly_mlp":    b.get("kelly_pct"),
            "kelly_delta":  round(d_kelly, 4),
            "stake_multi5": a.get("stake_dollars"),
            "stake_mlp":    b.get("stake_dollars"),
            "stake_delta":  round(d_stake, 2),
        })
    n = len(shared)
    return {
        "n_shared":               n,
        "mean_edge_delta":        round(sum_edge / n, 4) if n else 0.0,
        "mean_abs_edge_delta":    round(abs_edge / n, 4) if n else 0.0,
        "mean_kelly_delta":       round(sum_kelly / n, 4) if n else 0.0,
        "mean_abs_kelly_delta":   round(abs_kelly / n, 4) if n else 0.0,
        "total_stake_delta":      round(sum_stake, 2),
        "total_abs_stake_delta":  round(abs_stake, 2),
        "per_bet":                per_bet,
    }


# ============================================================================ #
# Orchestrator                                                                  #
# ============================================================================ #
def _run_engine_with_flag(flag: str, **kwargs) -> Dict[str, Any]:
    """Run the live engine with M2_FAMILY_USE_MLP set to `flag` for this call.

    Restores the prior env value on the way out so callers' environments
    are not mutated. Reads from os.environ at engine call-time which means
    the engine's own `_m2_family_use_mlp()` (re-read each call) sees our
    override immediately.
    """
    prior = os.environ.get("M2_FAMILY_USE_MLP")
    os.environ["M2_FAMILY_USE_MLP"] = str(flag)
    try:
        # Local import keeps a missing dep from breaking pure-math tests.
        from scripts.live_recommendation_engine import run_engine  # noqa: PLC0415
        return run_engine(**kwargs)
    finally:
        if prior is None:
            os.environ.pop("M2_FAMILY_USE_MLP", None)
        else:
            os.environ["M2_FAMILY_USE_MLP"] = prior


def compare_modes(
    bankroll: float = 1000.0,
    top: int = 20,
    date: Optional[str] = None,
    min_edge: float = 0.03,
    top_overlap_k: Iterable[int] = (5, 10, 20),
    predictions_path: Optional[str] = None,
    lines_dir: Optional[str] = None,
    injury_parquet_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run both modes back-to-back and return a structured comparison."""
    date_str = date or _date_cls.today().isoformat()
    common_kw = dict(
        bankroll=float(bankroll),
        top=int(top),
        date=date_str,
        min_edge=float(min_edge),
        predictions_path=predictions_path,
        lines_dir=lines_dir,
        injury_parquet_path=injury_parquet_path,
    )

    payload_multi5 = _run_engine_with_flag("0", **common_kw)
    payload_mlp    = _run_engine_with_flag("1", **common_kw)

    recs_multi5 = payload_multi5.get("recommendations", []) or []
    recs_mlp    = payload_mlp.get("recommendations", []) or []

    overlap_buckets = {
        f"top_{int(k)}": topk_overlap(recs_multi5, recs_mlp, int(k))
        for k in top_overlap_k
    }
    deltas = overlap_deltas(recs_multi5, recs_mlp)

    # New-in-MLP / dropped-from-MLP at top-N (top, not all candidates) — the
    # operator's actionable question is "what changed in my slate?".
    keys_multi5 = {_bet_key(b) for b in recs_multi5}
    keys_mlp    = {_bet_key(b) for b in recs_mlp}
    only_in_mlp = []
    for b in recs_mlp:
        if _bet_key(b) not in keys_multi5:
            only_in_mlp.append({
                "player": b.get("player"),
                "stat":   b.get("stat"),
                "side":   b.get("side"),
                "book":   b.get("book"),
                "line":   b.get("line"),
                "edge":   b.get("edge"),
                "edge_pct": b.get("edge_pct"),
                "kelly_pct": b.get("kelly_pct"),
                "stake_dollars": b.get("stake_dollars"),
                "reason": "new-in-MLP: not present in multi5 top-N",
            })
    only_in_multi5 = []
    for b in recs_multi5:
        if _bet_key(b) not in keys_mlp:
            only_in_multi5.append({
                "player": b.get("player"),
                "stat":   b.get("stat"),
                "side":   b.get("side"),
                "book":   b.get("book"),
                "line":   b.get("line"),
                "edge":   b.get("edge"),
                "edge_pct": b.get("edge_pct"),
                "kelly_pct": b.get("kelly_pct"),
                "stake_dollars": b.get("stake_dollars"),
                "reason": "dropped-from-MLP: not present in MLP top-N",
            })

    return {
        "generated_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date":           date_str,
        "bankroll":       float(bankroll),
        "top":            int(top),
        "min_edge":       float(min_edge),
        "top_overlap_k":  [int(k) for k in top_overlap_k],
        "engine_version": payload_multi5.get("engine_version"),
        "multi5": {
            "n_predictions_available": payload_multi5.get("n_predictions_available"),
            "n_snapshots_loaded":      payload_multi5.get("n_snapshots_loaded"),
            "n_evaluated":             payload_multi5.get("n_evaluated"),
            "n_candidates_pos_edge":   payload_multi5.get("n_candidates_pos_edge"),
            "n_recs":                  payload_multi5.get("n_recs", len(recs_multi5)),
            "total_stake_post_cap":    payload_multi5.get("total_stake_post_cap"),
            "slate_cap_dollars":       payload_multi5.get("slate_cap_dollars"),
            "reason":                  payload_multi5.get("reason"),
        },
        "mlp": {
            "n_predictions_available": payload_mlp.get("n_predictions_available"),
            "n_snapshots_loaded":      payload_mlp.get("n_snapshots_loaded"),
            "n_evaluated":             payload_mlp.get("n_evaluated"),
            "n_candidates_pos_edge":   payload_mlp.get("n_candidates_pos_edge"),
            "n_recs":                  payload_mlp.get("n_recs", len(recs_mlp)),
            "total_stake_post_cap":    payload_mlp.get("total_stake_post_cap"),
            "slate_cap_dollars":       payload_mlp.get("slate_cap_dollars"),
            "reason":                  payload_mlp.get("reason"),
        },
        "overlap":         overlap_buckets,
        "shared_bets":     deltas,
        "only_in_multi5":  only_in_multi5,
        "only_in_mlp":     only_in_mlp,
        # Verbatim top-K for downstream renderers (dashboard).
        "top_multi5":      recs_multi5[: int(top)],
        "top_mlp":         recs_mlp[: int(top)],
        "operator_would_change_bets": (
            len(only_in_mlp) > 0 or len(only_in_multi5) > 0
        ),
    }


# ============================================================================ #
# Human-readable table                                                          #
# ============================================================================ #
def format_table(cmp_payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("=" * 100)
    lines.append(
        f"ENGINE-MODE COMPARE — multi5 vs MLP  "
        f"({cmp_payload.get('date','')})  "
        f"engine={cmp_payload.get('engine_version','')}"
    )
    lines.append("=" * 100)
    m5 = cmp_payload.get("multi5", {})
    mp = cmp_payload.get("mlp", {})
    lines.append(
        f"multi5: n_evaluated={m5.get('n_evaluated',0)} "
        f"n_recs={m5.get('n_recs',0)} "
        f"stake=${m5.get('total_stake_post_cap',0):.2f}"
    )
    lines.append(
        f"mlp   : n_evaluated={mp.get('n_evaluated',0)} "
        f"n_recs={mp.get('n_recs',0)} "
        f"stake=${mp.get('total_stake_post_cap',0):.2f}"
    )
    lines.append("-" * 100)
    for k_label, bucket in cmp_payload.get("overlap", {}).items():
        lines.append(
            f"{k_label:<10} "
            f"jaccard={bucket.get('jaccard',0):.4f}  "
            f"overlap={bucket.get('overlap',0)}/"
            f"{max(bucket.get('n_a',0), bucket.get('n_b',0))}"
        )
    shared = cmp_payload.get("shared_bets", {})
    lines.append("-" * 100)
    lines.append(
        f"Shared bets: {shared.get('n_shared',0)}  "
        f"mean|d_edge|={shared.get('mean_abs_edge_delta',0):.4f}  "
        f"total|d_stake|=${shared.get('total_abs_stake_delta',0):.2f}"
    )
    lines.append(
        f"only-in-multi5: {len(cmp_payload.get('only_in_multi5', []))}  "
        f"only-in-MLP:    {len(cmp_payload.get('only_in_mlp', []))}  "
        f"operator would change bets: "
        f"{cmp_payload.get('operator_would_change_bets')}"
    )
    return "\n".join(lines)


# ============================================================================ #
# CLI                                                                           #
# ============================================================================ #
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--date", type=str, default=None,
                    help="ISO date (defaults to today)")
    ap.add_argument("--min-edge", type=float, default=0.03)
    ap.add_argument("--top-overlap-k", type=str, default="5,10,20",
                    help="comma-separated K values for top-K Jaccard")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of a table")
    ap.add_argument("--out", type=str, default=None,
                    help="optional path to also write payload JSON to")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    ks = [int(x.strip()) for x in args.top_overlap_k.split(",") if x.strip()]
    cmp_payload = compare_modes(
        bankroll=args.bankroll,
        top=args.top,
        date=args.date,
        min_edge=args.min_edge,
        top_overlap_k=ks,
    )
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(cmp_payload, fh, indent=2, default=str)
    if args.json:
        print(json.dumps(cmp_payload, indent=2, default=str))
    else:
        print(format_table(cmp_payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
