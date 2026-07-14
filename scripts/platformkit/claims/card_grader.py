"""scripts.platformkit.claims.card_grader -- per-card POOLED grading (P4).

Pools ALL firings of a condition-class across every settled game, never a
per-game verdict. Reuses the in-game grading stack's own settled-row source
and math: data/cache/ingame_grade/<sport>/<game_id>.jsonl (claim_tags merged
in additively at capture by condition_tagger, see inplay_daytrader.on_tick),
live_grade._load_pairs, ingame_clv_per_segment._discover, and the same
game-clustered-bootstrap-CI Brier-delta pattern as ingame_outcome_verdict.

STEP 0 FINDING: run_paper_today._record_priced computes PREGAME claim_tags
but never persists them -- clv_ledger.record_bet's stored record has no
claim_tags field, so pregame cards have ZERO on-disk source today; graded
OPEN "accruing" honestly. Fixing that is outside this lane's OWNS list.

VERDICT (ALL FOUR required to VALIDATE; below MIN_FIRED_PER_HALF in either
date-half -> OPEN "accruing"; STARVED closes a dead card):
  1. n_fired >= MIN_FIRED_PER_HALF in EACH half.
  2. fired-rows mean CLV (model_prob - market_prob) sign matches
     card.expected_sign in BOTH halves.
  3. fired-rows Brier improvement > not-fired-rows improvement, BOTH halves.
  4. game-clustered bootstrap CI on the per-game Brier delta excludes zero
     in BOTH halves -- per-row pooling inflates significance ~3.3x.
Clears the n_fired gate but fails 2/3/4 -> REJECTED. STARVED: <1% fire rate
after 45 days open -> closed. Paper-only, no $/roi/pnl, edge_claimed False.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/claims/test_card_grader.py -q
"""
from __future__ import annotations

import logging
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.claims import card_registry as _reg
from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
from scripts.platformkit.ingame import ingame_outcome_verdict_multi as _ovm
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.io_atomic import append_jsonl_atomic

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = _REPO_ROOT / "data" / "cache" / "claims" / "card_ledger.jsonl"

MIN_FIRED_PER_HALF = 60
STARVED_DAYS = 45
STARVED_FIRE_RATE = 0.01
_BOOTSTRAP_ITERS = 1000

OutcomeFn = Callable[[str, str], Optional[float]]  # (sport, game_id) -> y in {0,1} or None

_ALL_SPORTS = ["mlb"] + list(_ovm.SPORTS)

def _build_resolver(sport: str) -> Callable[[str], Optional[float]]:
    try:
        if sport == "mlb":
            from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
            res = MlbOutcomeResolver()
            return res.home_win if res.available else (lambda _g: None)
        factory = _ovm._OUTCOME_FACTORY.get(sport)
        return factory() if factory is not None else (lambda _g: None)
    except Exception:  # noqa: BLE001
        return lambda _g: None

def _default_outcome_fn() -> OutcomeFn:
    """(sport, game_id) -> y, lazily building + caching one resolver per sport."""
    cache: Dict[str, Callable[[str], Optional[float]]] = {}

    def _fn(sport: str, game_id: str) -> Optional[float]:
        if sport not in cache:
            cache[sport] = _build_resolver(sport)
        try:
            y = cache[sport](game_id)
        except Exception:  # noqa: BLE001
            return None
        return None if y is None else float(y)

    return _fn

def _discover_files(grade_dir: Optional[Path], sports: Sequence[str]) -> List[Tuple[str, Path]]:
    out: List[Tuple[str, Path]] = []
    for sp in sports:
        out.extend((sp, p) for p in _seg._discover(grade_dir, sp))
    return out

def _collect_rows(card_id: str, files: Sequence[Tuple[str, Path]],
                  outcome_fn: OutcomeFn) -> List[Dict[str, Any]]:
    """One row per tagged tick with a resolvable outcome. Never raises."""
    rows: List[Dict[str, Any]] = []
    for sport, p in files:
        try:
            pairs = _lg._load_pairs(Path(p))
        except Exception:  # noqa: BLE001
            pairs = []
        if not pairs:
            continue
        gid = str(pairs[0].get("game_id") or Path(p).stem)
        y = outcome_fn(sport, gid)
        if y is None:
            continue
        for r in pairs:
            tags = r.get("claim_tags")
            if not isinstance(tags, dict) or card_id not in tags:
                continue
            ts = str(r.get("ts", ""))
            rows.append({
                "game_id": gid, "sport": sport, "date": ts[:10],
                "fired": bool(tags[card_id]),
                "model_prob": float(r["model_prob"]), "market_prob": float(r["market_prob"]),
                "y": y,
            })
    return rows

def _split_halves(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Date-split ALL rows (both arms share one boundary). <2 dates -> all in A."""
    dates = sorted({r["date"] for r in rows if r["date"]})
    if len(dates) < 2:
        return list(rows), []
    mid = max(len(dates) // 2, 1)
    set_a = set(dates[:mid])
    half_a = [r for r in rows if r["date"] in set_a]
    half_b = [r for r in rows if r["date"] not in set_a]
    return half_a, half_b

def _pool(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-game mean Brier delta + CLV; game is the clustering unit."""
    by_game: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_game[r["game_id"]].append(r)
    per_game_delta: List[float] = []
    per_game_clv: List[float] = []
    for grs in by_game.values():
        n = len(grs)
        bm = sum((r["model_prob"] - r["y"]) ** 2 for r in grs) / n
        bk = sum((r["market_prob"] - r["y"]) ** 2 for r in grs) / n
        per_game_delta.append(bm - bk)
        per_game_clv.append(sum(r["model_prob"] - r["market_prob"] for r in grs) / n)
    n_games = len(by_game)
    return {
        "n_rows": len(rows), "n_games": n_games,
        "brier_delta": (sum(per_game_delta) / n_games) if n_games else 0.0,
        "clv": (sum(per_game_clv) / n_games) if n_games else 0.0,
        "per_game_delta": per_game_delta,
    }

def _ci(per_game_delta: Sequence[float], *, seed: int = 42) -> Tuple[float, float]:
    """Game-clustered bootstrap 95% CI for the pooled per-game Brier delta."""
    g = len(per_game_delta)
    if g == 0:
        return (0.0, 0.0)
    if g == 1:
        return (per_game_delta[0], per_game_delta[0])
    rng = random.Random(seed)
    means = sorted(
        sum(per_game_delta[rng.randrange(g)] for _ in range(g)) / g
        for _ in range(_BOOTSTRAP_ITERS)
    )
    lo = means[int(0.025 * (_BOOTSTRAP_ITERS - 1))]
    hi = means[int(0.975 * (_BOOTSTRAP_ITERS - 1))]
    return (lo, hi)

def _grade_half(half_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    fired = _pool([r for r in half_rows if r["fired"]])
    notfired = _pool([r for r in half_rows if not r["fired"]])
    if fired["n_rows"] < MIN_FIRED_PER_HALF:
        return {"status": "accruing", "fired": fired, "notfired": notfired}
    lo, hi = _ci(fired["per_game_delta"])
    return {"status": "graded", "fired": fired, "notfired": notfired,
            "ci_lo": round(lo, 6), "ci_hi": round(hi, 6), "significant": hi < 0.0}

def _days_since(ts: str, now: datetime) -> float:
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return 0.0
    return (now - dt).total_seconds() / 86400.0

def grade_card(card: Dict[str, Any], files: Sequence[Tuple[str, Path]], *,
              outcome_fn: Optional[OutcomeFn] = None,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    """Grade ONE card by pooling every settled firing across every game. Never raises."""
    now = now or datetime.now(timezone.utc)
    card_id = card["card_id"]
    scope = (card.get("condition") or {}).get("scope")
    base = {"card_id": card_id, "graded_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "units": "probability", "edge_claimed": False}
    if scope != "ingame":
        return {**base, "verdict": "OPEN", "reason":
                "accruing: no persisted claim_tags source for scope=%s (see module docstring)" % scope,
                "n_fired": 0}
    try:
        rows = _collect_rows(card_id, files, outcome_fn or _default_outcome_fn())
    except Exception as exc:  # noqa: BLE001
        return {**base, "verdict": "OPEN", "reason": "accruing: collect failed %s" % type(exc).__name__,
                "n_fired": 0}

    n_total = len(rows)
    n_fired = sum(1 for r in rows if r["fired"])
    days_open = _days_since(str(card.get("registered_ts", "")), now)
    fire_rate = (n_fired / n_total) if n_total else 0.0
    if days_open >= STARVED_DAYS and fire_rate < STARVED_FIRE_RATE:
        return {**base, "verdict": "STARVED",
                "reason": "fired on %.4f%% of %d eligible rows after %.0f days" % (
                    fire_rate * 100.0, n_total, days_open),
                "n_fired": n_fired, "n_total": n_total}

    half_a, half_b = _split_halves(rows)
    ga, gb = _grade_half(half_a), _grade_half(half_b)
    if ga["status"] != "graded" or gb["status"] != "graded":
        return {**base, "verdict": "OPEN",
                "reason": "accruing: n_fired=%d/%d (half A=%d half B=%d), need >=%d each half" % (
                    n_fired, n_total, ga["fired"]["n_rows"], gb["fired"]["n_rows"], MIN_FIRED_PER_HALF),
                "n_fired": n_fired, "n_total": n_total}

    exp = 1 if card.get("expected_sign") == "+" else -1
    sign_a = 1 if ga["fired"]["clv"] > 0 else (-1 if ga["fired"]["clv"] < 0 else 0)
    sign_b = 1 if gb["fired"]["clv"] > 0 else (-1 if gb["fired"]["clv"] < 0 else 0)
    cond_sign = sign_a == exp and sign_b == exp
    imp_a_fired, imp_a_ctrl = -ga["fired"]["brier_delta"], -ga["notfired"]["brier_delta"]
    imp_b_fired, imp_b_ctrl = -gb["fired"]["brier_delta"], -gb["notfired"]["brier_delta"]
    cond_beats_control = imp_a_fired > imp_a_ctrl and imp_b_fired > imp_b_ctrl
    cond_significant = ga["significant"] and gb["significant"]
    validated = cond_sign and cond_beats_control and cond_significant

    def _half_detail(g: Dict[str, Any]) -> Dict[str, Any]:
        return {"n_fired": g["fired"]["n_rows"], "n_games": g["fired"]["n_games"],
                "brier_delta": round(g["fired"]["brier_delta"], 6), "clv": round(g["fired"]["clv"], 6),
                "ci95": [g["ci_lo"], g["ci_hi"]], "control_brier_delta": round(g["notfired"]["brier_delta"], 6)}

    detail = {"half_a": _half_detail(ga), "half_b": _half_detail(gb),
              "cond_n_fired": True, "cond_sign_match": cond_sign,
              "cond_beats_control": cond_beats_control, "cond_game_clustered_significant": cond_significant}
    return {**base, "verdict": "VALIDATED" if validated else "REJECTED",
            "reason": "all 4 conditions met" if validated else "failed: %s" % ",".join(
                k for k, v in (("sign", cond_sign), ("beats_control", cond_beats_control),
                               ("significant", cond_significant)) if not v),
            "n_fired": n_fired, "n_total": n_total, "detail": detail}

def grade_all(*, grade_dir: Optional[Path] = None, sports: Optional[Sequence[str]] = None,
             outcome_fn: Optional[OutcomeFn] = None, now: Optional[datetime] = None,
             ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Grade every OPEN card, peek-lock + close + promote + ledger-append. Never raises."""
    now = now or datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lpath = Path(ledger_path) if ledger_path is not None else LEDGER_PATH
    files = _discover_files(grade_dir, sports or _ALL_SPORTS)
    open_cards = _reg.get_open()
    results: List[Dict[str, Any]] = []
    counts = {"VALIDATED": 0, "REJECTED": 0, "STARVED": 0, "OPEN": 0}
    for card in open_cards:
        card_id = card["card_id"]
        if not card.get("outcomes_peeked", False):
            _reg.mark_peeked(card_id, ts)
        try:
            result = grade_card(card, files, outcome_fn=outcome_fn, now=now)
        except Exception as exc:  # noqa: BLE001 -- one bad card must never sink the pass
            result = {"card_id": card_id, "verdict": "OPEN",
                      "reason": "accruing: grade_card failed %s" % type(exc).__name__,
                      "n_fired": 0, "graded_at": ts, "units": "probability", "edge_claimed": False}
        try:
            append_jsonl_atomic(lpath, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("card_ledger append failed for %s: %s", card_id, exc)
        verdict = result.get("verdict", "OPEN")
        counts[verdict] = counts.get(verdict, 0) + 1
        results.append(result)
        if verdict in ("VALIDATED", "REJECTED", "STARVED"):
            _reg.close_card(card_id, verdict, result.get("reason", ""), ts)
    promoted = _reg.promote_queued(ts) if any(
        r.get("verdict") in ("VALIDATED", "REJECTED", "STARVED") for r in results) else []
    return {"graded_at": ts, "n_cards": len(open_cards), "counts": counts,
            "promoted": promoted, "results": results, "edge_claimed": False}

def format_report(summary: Dict[str, Any]) -> str:
    lines = ["=== card_grader (pooled, honest) ===",
             "n_cards=%d  %s" % (summary.get("n_cards", 0), summary.get("counts", {}))]
    for r in summary.get("results", []):
        lines.append("%-14s %-10s n_fired=%-5d %s" % (
            r["card_id"], r.get("verdict"), r.get("n_fired", 0), r.get("reason", "")[:80]))
    if summary.get("promoted"):
        lines.append("promoted from QUEUED: %s" % summary["promoted"])
    lines.append("edge_claimed: False")
    return "\n".join(lines)

def main(argv: Optional[Sequence[str]] = None) -> int:
    summary = grade_all()
    print(format_report(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["LEDGER_PATH", "MIN_FIRED_PER_HALF", "STARVED_DAYS", "STARVED_FIRE_RATE",
           "grade_card", "grade_all", "format_report"]
