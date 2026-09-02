"""scripts.platformkit.ingame.ingame_placement_funnel -- WHY does the in-game
day-trader place so few bets? Make the funnel visible.

The ledger shows the in-game channel STARVED (1 paper_ingame row vs 136 pregame),
yet the engine (capture -> live model -> edge gate -> quarter-Kelly -> place) is
fully wired. The bottleneck is invisible: every live tick that fails to bet returns
a one-word reason (no_live_state / no_model_prob / no_home_leg / below_floor /
illiquid / stale / ok), but nothing aggregates them, so we cannot tell whether the
problem is state resolution, the model, leg alignment, or the tier floor.

This module turns the per-game decision rows that inplay_capture_loop.poll_once
already returns into a STAGE FUNNEL -- markets -> live_state -> model_prob ->
home_leg -> priced -> bet -- plus a reason histogram, and writes it to
data/frontend/ops/ingame_placement_funnel.json. During a live slate this shows, at
a glance, exactly which stage drops the volume, so tuning targets the real cause
instead of guessing. Pure aggregation; reads only the decisions; places NO bet,
flips NO flag, no $ field, no edge claim. ASCII; never raises out.

CLI:
    python -m scripts.platformkit.ingame.ingame_placement_funnel            # one poll
    python -m scripts.platformkit.ingame.ingame_placement_funnel --no-write
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_REPO = Path(__file__).resolve().parents[3]
FUNNEL_PATH = _REPO / "data" / "frontend" / "ops" / "ingame_placement_funnel.json"
DEFAULT_SPORTS = ("mlb", "soccer_intl")
COMPONENT = "m_ingame_placement_funnel"

# The ordered drop-off stages. A decision row reaches a stage iff it cleared every
# earlier one; the reason it carries tells us the FIRST stage it failed.
_STAGE_OF_REASON = {
    "no_live_state": "live_state",
    # S107: the ticker DID have a live team-match, but that game belongs to a
    # different date (a series' other night / the other half of a doubleheader),
    # so no live state was bound -- same funnel stage as no_live_state. Mapped
    # explicitly because an UNMAPPED reason falls through as "cleared every
    # stage", which would silently inflate the funnel.
    "bridge_date_mismatch": "live_state",
    "no_model_prob": "model_prob",
    "no_home_leg": "home_leg",
    "bad_price": "priced",
    "illiquid": "priced",
    "stale": "priced",
    "not_justified": "priced",
    "below_floor": "tier_floor",
}
_STAGES = ["markets", "live_state", "model_prob", "home_leg", "priced",
           "tier_floor", "bet"]


def funnel_from_decisions(decisions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-game decision rows into the ordered placement funnel.

    Each row: {action, reason, model_prob, devigged_price, ...}. action=='bet' is a
    placement; otherwise `reason` names the first failed stage. Pure; never raises."""
    reasons: Counter = Counter()
    n_markets = 0
    n_bet = 0
    # cleared[stage] = how many rows got AT LEAST to that stage
    cleared = {s: 0 for s in _STAGES}
    for d in decisions or []:
        n_markets += 1
        reason = str(d.get("reason") or "")
        reasons[reason or "ok"] += 1
        is_bet = d.get("action") == "bet"
        if is_bet:
            n_bet += 1
        failed_stage = _STAGE_OF_REASON.get(reason)
        # Walk the stages: everything strictly before the failed stage was cleared.
        for s in _STAGES[1:]:
            if s == "bet":
                if is_bet:
                    cleared[s] += 1
                continue
            if failed_stage is None or _STAGES.index(s) < _STAGES.index(failed_stage):
                cleared[s] += 1
            else:
                break
    cleared["markets"] = n_markets
    cleared["bet"] = n_bet
    # biggest single drop-off stage (largest count loss between consecutive stages)
    worst = None
    worst_drop = -1
    for i in range(1, len(_STAGES)):
        drop = cleared[_STAGES[i - 1]] - cleared[_STAGES[i]]
        if drop > worst_drop:
            worst_drop, worst = drop, _STAGES[i]
    return {"stages": {s: cleared[s] for s in _STAGES},
            "reasons": dict(reasons.most_common()),
            "n_markets": n_markets, "n_bet": n_bet,
            "biggest_dropoff": worst, "dropoff_count": max(0, worst_drop)}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_doc(sports: Sequence[str] = DEFAULT_SPORTS, *,
              poll_fn: Optional[Callable[..., Dict[str, Any]]] = None
              ) -> Dict[str, Any]:
    """Run one in-game poll and fold its decisions into the funnel doc."""
    pf = poll_fn
    if pf is None:
        from scripts.platformkit.ingame.inplay_capture_loop import poll_once as pf
    res = pf(sports=tuple(sports)) or {}
    decisions: List[Dict[str, Any]] = list(res.get("games") or [])
    fun = funnel_from_decisions(decisions)
    return {"updated_at": _utc(), "component": COMPONENT,
            "note": "in-game placement funnel: markets->live_state->model_prob->"
                    "home_leg->priced->tier_floor->bet. Shows WHERE in-game volume "
                    "is lost. Calibration/diagnostic only; no bet here, no $ edge.",
            "n_live": res.get("n_live"), "as_of": res.get("as_of"),
            **fun}


def write_doc(doc: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = Path(path) if path is not None else FUNNEL_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=0), encoding="ascii")
    tmp.replace(p)


def render(doc: Dict[str, Any]) -> str:
    L = ["=" * 70, "IN-GAME PLACEMENT FUNNEL (where in-game volume is lost)", "=" * 70]
    st = doc.get("stages") or {}
    for s in _STAGES:
        L.append("  %-12s %d" % (s, st.get(s, 0)))
    L.append("-" * 70)
    if doc.get("n_markets", 0) == 0:
        L.append("0 live game markets right now -> 0 in-game bets is CORRECT (no "
                 "live slate). Re-run during games to see the funnel.")
    else:
        L.append("biggest drop-off: %s (-%d). reasons: %s"
                 % (doc.get("biggest_dropoff"), doc.get("dropoff_count", 0),
                    doc.get("reasons")))
    L.append("=" * 70)
    return "\n".join(L)


def run(*, interval_sec: float = 300.0, sports: Sequence[str] = DEFAULT_SPORTS,
        poll_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        path: Optional[Path] = None,
        sleep: Optional[Callable[[float], None]] = None,
        max_ticks: Optional[int] = None,
        should_stop: Optional[Callable[[], bool]] = None) -> int:
    """Write the funnel every ``interval_sec`` (forever or ``max_ticks``). Survives any
    tick failure; returns ticks executed."""
    import time as _time
    _sleep = sleep if sleep is not None else _time.sleep
    ticks = 0
    while True:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                break
        try:
            doc = build_doc(sports, poll_fn=poll_fn)
            write_doc(doc, path)
            st = doc.get("stages") or {}
            print("%s | tick=%d markets=%d bet=%d dropoff=%s"
                  % (COMPONENT, ticks, st.get("markets", 0), st.get("bet", 0),
                     doc.get("biggest_dropoff")), flush=True)
        except Exception as exc:  # noqa: BLE001 - survive any failure
            print("%s | tick=%d ERROR %s" % (COMPONENT, ticks, str(exc)[:160]),
                  flush=True)
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        try:
            _sleep(float(interval_sec))
        except Exception:  # noqa: BLE001
            break
    return ticks


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="in-game placement funnel diagnostic")
    p.add_argument("--no-write", action="store_true", help="print only, do not write")
    p.add_argument("--interval", type=float, default=None,
                   help="loop forever at this cadence (default: single poll)")
    a = p.parse_args(argv)
    if a.interval is not None:
        print("%s | started interval=%ss" % (COMPONENT, a.interval), flush=True)
        run(interval_sec=a.interval)
        return 0
    doc = build_doc()
    if not a.no_write:
        write_doc(doc)
    print(render(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
