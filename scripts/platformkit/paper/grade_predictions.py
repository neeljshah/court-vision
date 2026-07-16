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
fair_odds is the decimal we settle at (the honest model price). CLV tiers,
best first (see _clv_fields): true_close (our own captured line history at
lock, prediction_close_attach) > proxy (a same-cycle close_proxy snapshot,
_clv_from_proxy) > no_close (no tradeable price captured -- most rows).

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

from scripts.platformkit.clv_ledger import compute_clv, event_ckey as _event_ckey
from scripts.platformkit.clv_ledger_migrate import BANNED_KEYS
from scripts.platformkit.paper import finals_fetch as _ff
from scripts.platformkit.paper import market_resolver as _mr
from scripts.platformkit.paper import prediction_close_attach as _pca

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


_NO_CLOSE = {"clv_pct": None, "beat_close": None,
            "clv_status": "no_close", "clv_is_proxy": False}


def _clv_fields(row: Dict[str, Any], home_team: str, away_team: str
                ) -> Dict[str, Any]:
    """true_close (our own captured line history) first, else the close_proxy
    fallback, else no_close. Neither tier ever fabricates."""
    true_close = _pca.attach_true_close(row, home_team, away_team)
    return (true_close if true_close["clv_status"] == "true_close"
           else _clv_from_proxy(row, home_team, away_team))


def _clv_from_proxy(row: Dict[str, Any], home_team: str, away_team: str
                    ) -> Dict[str, Any]:
    """Real CLV vs the two-way close PROXY captured at logging time, when present.

    _log_unpriced (run_paper_today.py) only fills close_proxy for a row whose
    selection literally equals the home or away team name (moneyline pick with
    no tradeable book price) -- so a non-null close_proxy always maps to a real
    side here. Everything else (derived/spread/total markets -- the majority of
    this ledger) never gets a close_proxy at all: for those, "no tradeable book
    price captured" remains the honest, unchanged verdict.
    """
    proxy = row.get("close_proxy")
    if not isinstance(proxy, dict):
        return dict(_NO_CLOSE)
    ch, ca = proxy.get("close_decimal_home"), proxy.get("close_decimal_away")
    if ch is None or ca is None:
        return dict(_NO_CLOSE)
    selection = row.get("selection")
    if selection == home_team:
        side = "home"
    elif selection == away_team:
        side = "away"
    else:
        return dict(_NO_CLOSE)
    dec = row.get("fair_odds")
    if not dec or float(dec) <= 1.0:
        return dict(_NO_CLOSE)
    try:  # arb/degenerate proxy close (booksum<1) -> Shin devig asserts; no CLV
        clv = compute_clv(side, float(dec), float(ch), float(ca))
    except Exception:  # noqa: BLE001 -- mirrors _log_unpriced's own devig guard
        return dict(_NO_CLOSE)
    # clv_status="proxy" (mirrors grade_paper.py's sibling convention exactly):
    # the "close" is a same-cycle book snapshot at LOG time, not a true
    # post-commence closing line, so it must NOT satisfy clv_scoreboard's
    # _is_measurable (== "true_close" only) -- an honest proxy stays out of the
    # true-close aggregate, never silently inflating it.
    return {"clv_pct": clv["clv_pct"], "beat_close": clv["clv_pct"] > 0.0,
            "clv_status": "proxy", "clv_is_proxy": True}


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
        **_clv_fields(row, home_team, away_team),  # true_close > proxy > no_close
        "pred_key": pred_key(row),  # additive cross-ledger join key via clv_ledger.event_ckey
        "ckey": _event_ckey({"sport": row.get("sport"), "matchup": row.get("matchup"),
            "market": row.get("group"), "game_date": str(row.get("commence_time") or row.get("logged_at") or "")[:10]}),
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
