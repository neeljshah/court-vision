"""scripts.platformkit.paper.grade_predictions -- settle logged model predictions.

data/frontend/paper_predictions.jsonl holds 3,284 logged MODEL VIEWS (no result, no
CLV): {logged_at, sport, matchup, group, selection, model_prob, line, fair_odds,
event_id, ...}. This pass settles each row whose game is FINAL (fetched by event_id
via finals_fetch) and whose market the FULL-GAME final score can decide
(market_resolver), writing a graded twin with a flat 1-unit stake and the unit_result
grade_paper already defines (win -> +(dec-1), loss -> -1, push -> 0).

HONESTY (binding):
  * Flat 1.0-unit stake (these rows have no stake) -- a pure unit count, never $.
  * No final yet, or a segment/unsupported market -> row stays UNGRADED (skipped),
    never fabricated.
  * UNITS ONLY: BANNED_KEYS stripped on write; executed=False; edge_claimed=False.
  * Idempotent: a pred already graded (by pred_key) is skipped.

Output ledger: data/frontend/paper_predictions_graded.jsonl (append-only twins).
The pregame fair price (fair_odds) is the decimal we settle at -- the honest model
price; with no tradeable book price these rows have no CLV (clv_status="no_close").

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/paper/test_grade_predictions.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.paper import finals_fetch as _ff
from scripts.platformkit.paper import market_resolver as _mr

_HERE = Path(__file__).resolve().parent
_FRONTEND = _HERE.parents[2] / "data" / "frontend"
DEFAULT_PREDICTIONS = _FRONTEND / "paper_predictions.jsonl"
DEFAULT_GRADED = _FRONTEND / "paper_predictions_graded.jsonl"

FlatFinalFetch = Callable[[str, str], Optional[Dict[str, Any]]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_banned(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    for k in BANNED_KEYS:
        out.pop(k, None)
    return out


def pred_key(row: Dict[str, Any]) -> str:
    """Durable identity of one prediction row (independent of logged_at)."""
    return "|".join(str(row.get(k, "")) for k in
                    ("sport", "event_id", "matchup", "group", "selection", "line"))


def _matchup_teams(matchup: str) -> Optional[tuple]:
    """Split 'Away@Home' / 'Away vs Home' into (away, home). ESPN '@' = away@home."""
    s = str(matchup)
    for sep in ("@", " vs ", " v ", " - ", " at "):
        if sep in s:
            a, _, b = s.partition(sep)
            return a.strip(), b.strip()
    return None


def _unit_result(outcome: Optional[str], dec: float, units: float) -> Optional[float]:
    """UNITS won/lost at the settle price. win -> +(dec-1)*u; loss -> -u; push -> 0."""
    if outcome == "win":
        return round((float(dec) - 1.0) * float(units), 6)
    if outcome == "loss":
        return round(-float(units), 6)
    if outcome == "push":
        return 0.0
    return None


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def grade_one_pred(
    row: Dict[str, Any], final: Dict[str, Any], *, stake_units: float = 1.0
) -> Optional[Dict[str, Any]]:
    """Graded twin of a prediction *row* from a FINAL game dict, or None if ungradable.

    Resolves the market vs the full-game final score; None outcome -> None (skip).
    """
    teams = _matchup_teams(row.get("matchup", ""))
    home_name = final.get("home")
    away_name = final.get("away")
    # Prefer the feed's home/away labels (authoritative orientation).
    home_team = home_name or (teams[1] if teams else "")
    away_team = away_name or (teams[0] if teams else "")
    hs = int(final["home_score"])
    as_ = int(final["away_score"])
    outcome = _mr.resolve(
        row.get("group", ""), row.get("selection", ""), row.get("line"),
        row.get("sport", ""), home_team, away_team, hs, as_,
    )
    if outcome is None:
        return None  # ungradable from the final score -> stays open, not fabricated
    dec = float(row.get("fair_odds") or 0.0)
    if dec <= 1.0:
        return None  # no usable settle price -> cannot assign a unit result honestly
    graded = _strip_banned(row)
    graded.update({
        "status": "settled",
        "graded": True,
        "settled_at": _now_iso(),
        "outcome": outcome,
        "home_team": home_team, "away_team": away_team,
        "home_score": hs, "away_score": as_,
        "settle_decimal": dec,
        "stake_units": float(stake_units),
        "unit_result": _unit_result(outcome, dec, stake_units),
        "executed": False,
        "edge_claimed": False,
        # No tradeable book price was ever captured -> CLV genuinely unavailable.
        "clv_pct": None, "clv_status": "no_close", "clv_is_proxy": False,
        "pred_key": pred_key(row),
        "channel": "paper_prediction",
    })
    return graded


def _append_graded(rows: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(_strip_banned(r), default=str) + "\n")


def grade_predictions(
    predictions_path: Optional[Path] = None,
    graded_path: Optional[Path] = None,
    *,
    final_fetch: Optional[FlatFinalFetch] = None,
    stake_units: float = 1.0,
) -> Dict[str, Any]:
    """Settle every prediction whose game is FINAL + market is full-game-resolvable.

    *final_fetch* (event_id, sport) -> final dict | None is injectable for tests.
    Default fetches ESPN summary by event_id. One final fetched per (event_id, sport)
    and cached for the pass. Idempotent: already-graded pred_keys are skipped.
    """
    ppath = Path(predictions_path) if predictions_path else DEFAULT_PREDICTIONS
    gpath = Path(graded_path) if graded_path else DEFAULT_GRADED
    preds = _load_jsonl(ppath)
    done = {r.get("pred_key") for r in _load_jsonl(gpath) if r.get("pred_key")}

    fetch = final_fetch if final_fetch is not None else (
        lambda eid, sp: _ff.final_for_event(eid, sp))
    final_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    graded_now: List[Dict[str, Any]] = []
    n_skip_done = n_no_final = n_ungradable = 0
    for row in preds:
        key = pred_key(row)
        if key in done:
            n_skip_done += 1
            continue
        eid = str(row.get("event_id") or "").strip()
        sp = str(row.get("sport") or "").lower()
        if not eid:
            n_no_final += 1
            continue
        cache_key = "%s|%s" % (sp, eid)
        if cache_key not in final_cache:
            try:
                final_cache[cache_key] = fetch(eid, sp)
            except Exception:  # noqa: BLE001
                final_cache[cache_key] = None
        final = final_cache[cache_key]
        if final is None:
            n_no_final += 1
            continue
        twin = grade_one_pred(row, final, stake_units=stake_units)
        if twin is None:
            n_ungradable += 1
            continue
        graded_now.append(twin)
        done.add(key)

    if graded_now:
        _append_graded(graded_now, gpath)

    wins = sum(1 for r in graded_now if r["outcome"] == "win")
    losses = sum(1 for r in graded_now if r["outcome"] == "loss")
    return {
        "n_predictions": len(preds),
        "n_graded_now": len(graded_now),
        "n_win": wins, "n_loss": losses,
        "n_push": sum(1 for r in graded_now if r["outcome"] == "push"),
        "n_skip_already": n_skip_done,
        "n_no_final": n_no_final,
        "n_ungradable_market": n_ungradable,
        "graded_path": str(gpath),
        "honest_note": ("Flat 1-unit paper stakes; only FINAL games + full-game-"
                        "resolvable markets settled; segment markets stay open. "
                        "No tradeable price -> CLV unavailable. UNITS only, no $."),
        "edge_claimed": False,
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Grade logged paper predictions vs finals.")
    ap.add_argument("--predictions", default=None)
    ap.add_argument("--graded", default=None)
    a = ap.parse_args(argv)
    res = grade_predictions(
        Path(a.predictions) if a.predictions else None,
        Path(a.graded) if a.graded else None,
    )
    print(json.dumps(res, indent=2, default=str))
    return 0


__all__ = ["grade_predictions", "grade_one_pred", "pred_key", "DEFAULT_GRADED"]


if __name__ == "__main__":
    raise SystemExit(_main())
