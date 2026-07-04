"""domains.basketball_wnba.run_ingame_blend_check -- honest small-n calibration read.

STEP 4 of the LANE-4 brief: evaluate ingame_blend.blend_prob's Brier at
end-Q1 / half / end-Q3 checkpoints vs outcome, against a naive score-diff-only
baseline, for real completed WNBA games.

DATA: ESPN's WNBA scoreboard endpoint carries per-period linescores DIRECTLY on
each completed-event competitor (competitions[0].competitors[].linescores) --
confirmed live 2026-07-03 (401857034/401857035/401857036 all return 4 regulation
periods with numeric values). This means NO per-event summary call is needed --
the already-ingested scoreboard fetch cadence (one call per date) is enough, so
this check IS cheaply available; it is run for real rather than punted to
synthetic-only tests.

METHOD (leak-free by construction -- linescores are realized/historical, and the
walk-forward Elo p0 for each game uses only strictly-prior games, same replay()
convention as ratings.py):
  1. Pull games_df (already ingested espn_scoreboard.parquet) + walk_forward_elo
     -> per-game leak-free p0 (elo_home/elo_away as of that game, pre-update).
  2. Re-fetch each game's date scoreboard (one call per unique date -- the same
     endpoint ingest_espn.py uses) to read linescores for that specific event_id.
  3. Reconstruct cumulative (home_score, away_score) at end-Q1 (period=1,
     clock_s=0), half (period=2, clock_s=0), end-Q3 (period=3, clock_s=0).
  4. blend_prob(p0, state) at each checkpoint vs a naive baseline
     p_naive = sigmoid(K_SCORE_NAIVE * score_diff) (score-diff-only, NO prior,
     NO time-decay -- the honest simplest comparison point).
  5. Brier for both, per checkpoint, over whatever games have parseable
     linescores (small-n; sample size reported, never hidden).

Writes data/domains/wnba/ingame_blend_check.json. EDGE_CLAIMED = False;
calibration/coherence only. No network at import time (http_get injectable).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from domains.basketball_wnba.ingame_blend import LiveState, blend_prob
from domains.basketball_wnba.ingest_espn import _default_http_get, _SCOREBOARD_URL
from domains.basketball_wnba.ratings import walk_forward_elo

log = logging.getLogger(__name__)
EDGE_CLAIMED = False

_REPO = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO / "data" / "domains" / "wnba" / "espn_scoreboard.parquet"
_OUT = _REPO / "data" / "domains" / "wnba" / "ingame_blend_check.json"

# Checkpoint name -> (period, clock_s) at that CUMULATIVE moment (regulation).
_CHECKPOINTS = {"end_q1": (1, 0.0), "half": (2, 0.0), "end_q3": (3, 0.0)}
_K_NAIVE = 0.06  # fixed naive scale (score-diff-only sigmoid); not fit on this sample.


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def fetch_linescores_for_date(date: str, http_get: Optional[Callable] = None) -> Dict[str, Dict]:
    """event_id -> {'home': [q1..q4], 'away': [q1..q4]} for every completed event
    on *date*, read STRAIGHT off the scoreboard payload's competitor.linescores
    (no per-event summary call needed -- see module docstring). {} entries are
    skipped (an event without 4 clean regulation periods is never faked)."""
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(date=date))
    out: Dict[str, Dict] = {}
    for ev in payload.get("events") or []:
        eid = str(ev.get("id") or "")
        comps = ev.get("competitions") or []
        if not eid or not comps:
            continue
        row: Dict[str, List[float]] = {}
        for c in comps[0].get("competitors") or []:
            side = c.get("homeAway")
            if side not in ("home", "away"):
                continue
            ls = c.get("linescores") or []
            vals: List[float] = []
            for x in ls[:4]:
                try:
                    vals.append(float(x.get("value")))
                except (TypeError, ValueError):
                    vals.append(float("nan"))
            if len(vals) != 4 or any(math.isnan(v) for v in vals):
                row = {}
                break
            row[side] = vals
        if "home" in row and "away" in row:
            out[eid] = row
    return out


def _cum(vals: List[float], through_period: int) -> float:
    """Cumulative score through *through_period* (1-based, inclusive)."""
    return float(sum(vals[:through_period]))


def brier(preds: List[float], outcomes: List[float]) -> Optional[float]:
    if not preds:
        return None
    return float(sum((p - y) ** 2 for p, y in zip(preds, outcomes)) / len(preds))


def run_check(
    games_df: Optional[pd.DataFrame] = None,
    http_get: Optional[Callable] = None,
    max_games: int = 150,
) -> Dict:
    """Build the honest calibration read. Returns the same dict written to
    data/domains/wnba/ingame_blend_check.json."""
    games = games_df if games_df is not None else pd.read_parquet(_GAMES_PARQUET)
    wf = walk_forward_elo(games.copy())
    wf = wf.sort_values(["date", "event_id"], kind="mergesort").reset_index(drop=True)
    if max_games:
        wf = wf.tail(max_games).reset_index(drop=True)

    dates = sorted(set(pd.to_datetime(wf["date"]).dt.strftime("%Y%m%d")))
    linescores: Dict[str, Dict] = {}
    for d in dates:
        linescores.update(fetch_linescores_for_date(d, http_get=http_get))

    per_cp: Dict[str, Dict[str, List[float]]] = {
        cp: {"blend": [], "naive": [], "outcome": []} for cp in _CHECKPOINTS
    }
    n_matched = 0
    for _, row in wf.iterrows():
        eid = str(row["event_id"])
        ls = linescores.get(eid)
        if ls is None:
            continue
        n_matched += 1
        p0 = float(row["p_home_elo"])
        outcome = float(row["home_win"])
        for cp, (period, clock_s) in _CHECKPOINTS.items():
            h = _cum(ls["home"], period)
            a = _cum(ls["away"], period)
            state = LiveState(period=period, clock_s=clock_s, home_score=h, away_score=a)
            p_blend = blend_prob(p0, state)
            p_naive = _sigmoid(_K_NAIVE * (h - a))
            per_cp[cp]["blend"].append(p_blend)
            per_cp[cp]["naive"].append(p_naive)
            per_cp[cp]["outcome"].append(outcome)

    result: Dict[str, object] = {
        "edge_claimed": False,
        "n_games_in_window": int(len(wf)),
        "n_games_matched_linescores": int(n_matched),
        "data_availability": (
            "linescores read directly off the ESPN scoreboard payload's "
            "competitor.linescores field -- no per-event summary call needed; "
            "cheaply available."
        ),
        "checkpoints": {},
    }
    for cp in _CHECKPOINTS:
        b = brier(per_cp[cp]["blend"], per_cp[cp]["outcome"])
        nv = brier(per_cp[cp]["naive"], per_cp[cp]["outcome"])
        verdict = "insufficient_n" if n_matched < 20 else (
            "blend_beats_naive" if (b is not None and nv is not None and b < nv)
            else "naive_matches_or_beats_blend__HONEST")
        result["checkpoints"][cp] = {
            "n": len(per_cp[cp]["blend"]),
            "brier_blend": b,
            "brier_naive_score_diff_only": nv,
            "verdict": verdict,
        }
    return result


def write_check(result: Dict, out_path: Optional[Path] = None) -> Path:
    out = out_path or _OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(result, fh, indent=2)
    return out


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_check()
    out = write_check(result)
    print(json.dumps(result, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["fetch_linescores_for_date", "run_check", "write_check", "brier"]
