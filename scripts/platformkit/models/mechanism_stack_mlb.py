"""scripts.platformkit.models.mechanism_stack_mlb -- mechanism-stacked MLB
total_runs challenger: the SAME market-implied Gaussian(mu, sigma) the
crps_market runner scores against, plus a bounded additive pregame mu-shift
from ledger-backed mechanisms whose trigger condition is knowable before the
game starts. No training, no optimizer -- baseline + capped additive shifts.

Mechanism source: domains/mlb/knowledge/knowledge.jsonl. Binding selection
filter (label contains REPLICATED, or CONFIRMED_LOCAL w/ >=2 corpora, or
CONFIRMED w/ n>=1000) is applied in select_mechanisms(). Of the rows that
clear that filter, only ones whose condition is knowable PREGAME from data
already used by the crps_market runner are wired into the model (currently
one: staff-wide day-after fatigue) -- the rest are universal within-PA/
in-game dynamics identical in every game, SKIPPED with a reason.

Reuses (never reimplements): market_dist.fit_market_gaussian/devig_points,
crps_gaussian (sim2.simulator), _bootstrap_ci (run_mlb.py) for scoring;
validate_staff_dayafter_chain.team_day_table for the fatigue-flag derivation.
crps_baseline_model is read from last_run_mlb.json, not recomputed (that
run's engine simulation is expensive and orthogonal to this challenger).

CLI: python -m scripts.platformkit.models.mechanism_stack_mlb
Tests: python -m pytest scripts/platformkit/models/test_mechanism_stack_mlb.py -q
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from domains.mlb.knowledge._data import load_season
from domains.mlb.knowledge.validate_staff_dayafter_chain import team_day_table, HIGH_Q
from domains.mlb.pitch_engine.corpus import FIT_SEASON, load_pitch_frame, build_pa_frame
from domains.basketball_nba.sim2.simulator import crps_gaussian

from scripts.platformkit.knowledge.query import load_knowledge
from scripts.platformkit.benchmarks.crps_market.mlb_join import (
    build_game_join, load_line_history_totals, load_statcast_games,
)
from scripts.platformkit.benchmarks.crps_market.market_dist import (
    devig_points, fit_market_gaussian,
)
from scripts.platformkit.benchmarks.crps_market.run_mlb import _bootstrap_ci

_OUT = Path(__file__).resolve().parents[3] / "data" / "domains" / "mlb" / "mechanism_stack_benchmark.json"
_LAST_RUN_MLB = Path(__file__).resolve().parent.parent / "benchmarks" / "crps_market" / "last_run_mlb.json"

_MAX_SHIFT_PER_MECH = 0.5
_MAX_TOTAL_SHIFT = 1.0

# ponytail: whether a mechanism's trigger is knowable pregame is a judgment
# call per mechanism, not something to auto-detect from free text -- a small
# allow-list of mechanism titles is the honest, lazy way to record that call.
_PREGAME_KNOWABLE = {
    "Team staff-wide high-pitch-count day precedes next-day run-prevention degradation",
}


def _parse_ci_midpoint(ci) -> float | None:
    if not ci:
        return None
    try:
        lo, hi = (float(x) for x in str(ci).split(","))
        return (lo + hi) / 2.0
    except (ValueError, TypeError):
        return None


def select_mechanisms(rows: List[dict]) -> Tuple[List[dict], List[dict]]:
    """Binding label filter + numeric-effect requirement + pregame-knowable
    gate. Returns (selected, skipped) -- skipped covers every row that
    cleared the label filter but was not wired into the model, each with a
    reason. Rows that never clear the label filter at all are not the
    candidate pool and are not reported (that's most of the ledger)."""
    selected, skipped = [], []
    for r in rows:
        label = r.get("label") or ""
        corpora = r.get("corpora") or []
        n = r.get("n")
        mechanism = r.get("mechanism") or ""
        has_replicated = "REPLICATED" in label
        is_confirmed_local = label.startswith("CONFIRMED_LOCAL")
        is_confirmed = label.startswith("CONFIRMED") and not is_confirmed_local
        label_ok = (has_replicated
                    or (is_confirmed_local and len(corpora) >= 2)
                    or (is_confirmed and isinstance(n, (int, float)) and n >= 1000))
        if not label_ok:
            continue
        if not (isinstance(r.get("effect"), (int, float)) and isinstance(n, (int, float))):
            skipped.append({"mechanism": mechanism, "label": label,
                             "reason": "no numeric effect+n in the ledger row, cannot form a shift"})
            continue
        if not any(k in mechanism for k in _PREGAME_KNOWABLE):
            skipped.append({"mechanism": mechanism, "label": label,
                             "reason": "universal within-PA/in-game dynamic, identical in every game "
                                       "-- no per-game pregame-knowable trigger condition"})
            continue
        selected.append(r)
    return selected, skipped


def mechanism_shift_runs(row: dict) -> float:
    """Ledgered effect CI midpoint (already in runs for the selected
    mechanism), scaled 1:1 (no unit conversion needed) and capped."""
    mid = _parse_ci_midpoint(row.get("ci"))
    raw = mid if mid is not None else float(row["effect"])
    return float(np.clip(raw, -_MAX_SHIFT_PER_MECH, _MAX_SHIFT_PER_MECH))


def _fatigue_threshold(fit_season: int) -> float:
    """75th-pct team-day pitch count from FIT_SEASON only (fixed pregame,
    same discipline as the champion's sigma_clim) -- never the eval window."""
    td = team_day_table(load_season(fit_season))
    return float(td["pitches"].quantile(HIGH_Q))


def fatigue_flags(eval_pitch: pd.DataFrame, statcast_games: pd.DataFrame,
                   threshold: float) -> Dict[int, bool]:
    """game_pk -> True iff either team played the calendar day before
    (gap_days==1) with a staff pitch count >= the FIT_SEASON top-quartile
    threshold -- exactly the validate_staff_dayafter_chain trigger."""
    td = team_day_table(eval_pitch)
    td_dates = pd.to_datetime(td["game_date"]).dt.date
    by_team_day = {(t, d): p for t, d, p in zip(td["team"], td_dates, td["pitches"])}
    flags: Dict[int, bool] = {}
    for pk, gdate, home, away in zip(statcast_games["game_pk"], statcast_games["game_date"],
                                      statcast_games["home_team"], statcast_games["away_team"]):
        prior = gdate - timedelta(days=1)
        flags[int(pk)] = any(by_team_day.get((team, prior), 0) >= threshold for team in (home, away))
    return flags


def _sigma_clim(fit_season: int) -> float:
    """Same formula as run_mlb.py's _fit_engine sigma_clim -- recomputed here
    (not the full 4-model engine fit, which this challenger does not need)."""
    tr_pa = build_pa_frame(load_pitch_frame(fit_season))
    m = tr_pa.groupby("game_pk")[["post_home_score", "post_away_score"]].max()
    return float((m["post_home_score"] + m["post_away_score"]).std())


def _baseline_model_crps() -> float | None:
    if not _LAST_RUN_MLB.exists():
        return None
    return json.loads(_LAST_RUN_MLB.read_text(encoding="utf-8")).get("model_crps_mean")


def _mech_summary(row: dict, shift: float) -> dict:
    return {
        "mechanism": row["mechanism"], "label": row["label"], "effect": row.get("effect"),
        "n": row.get("n"), "corpora": row.get("corpora") or [], "ci": row.get("ci"),
        "applied_mu_shift_runs": round(shift, 4),
    }


def run(start: str = "2026-06-18", end: str = "2026-07-08") -> dict:
    selected, skipped = select_mechanisms(load_knowledge(["mlb"]))
    doc = {"sport": "mlb", "market": "total_runs", "edge_claimed": False,
           "selected_mechanisms": [_mech_summary(r, mechanism_shift_runs(r)) for r in selected],
           "skipped_mechanisms": skipped}
    if not selected:
        doc["verdict"] = "NOT_BUILDABLE"
        doc["blocker"] = "zero ledger mechanisms cleared the label+numeric filter with a pregame-knowable trigger"
        return doc

    statcast_games = load_statcast_games(2026)
    line_totals = load_line_history_totals(start, end)
    join = build_game_join(statcast_games, line_totals)
    doc["n_line_history_games"] = int(line_totals["game_id"].nunique()) if len(line_totals) else 0
    doc["n_joined_game_pk"] = len(join)
    if not join:
        doc["verdict"] = "NOT_TESTABLE"
        doc["blocker"] = "zero unambiguous game_pk<->game_id joins"
        return doc

    gpk_realized = statcast_games.set_index("game_pk")["realized_total"].to_dict()
    sigma_clim = _sigma_clim(FIT_SEASON)
    threshold = _fatigue_threshold(FIT_SEASON)
    fatigued = fatigue_flags(load_season(2026), statcast_games, threshold)
    # ponytail: single selected-mechanism shift today; sum-and-cap below
    # already generalizes if a 2nd pregame-knowable mechanism is added.
    mech_shift = {r["mechanism"]: mechanism_shift_runs(r) for r in selected}

    rows_by_gid = {gid: g.to_dict("records") for gid, g in line_totals.groupby("game_id")}
    stack_crps, market_crps = [], []
    for gid, gpk in join.items():
        realized = gpk_realized.get(gpk)
        if realized is None or (isinstance(realized, float) and np.isnan(realized)):
            continue
        try:
            points = devig_points(rows_by_gid[gid])
            mu, sigma, _n_used = fit_market_gaussian(points, sigma_clim)
        except (ValueError, KeyError):
            continue
        game_shift = sum(shift for m, shift in mech_shift.items() if fatigued.get(gpk, False))
        game_shift = float(np.clip(game_shift, -_MAX_TOTAL_SHIFT, _MAX_TOTAL_SHIFT))
        stack_crps.append(crps_gaussian(mu + game_shift, sigma, float(realized)))
        market_crps.append(crps_gaussian(mu, sigma, float(realized)))

    n = len(stack_crps)
    doc["n"] = n
    doc["n_fatigued_games"] = int(sum(1 for gpk in join.values() if fatigued.get(gpk, False)))
    if n < 5:
        doc["verdict"] = "NOT_TESTABLE"
        doc["blocker"] = "fewer than 5 games survived join + market-fit filters"
        return doc

    sc = np.array(stack_crps)
    kc = np.array(market_crps)
    delta = kc - sc  # positive => market crps higher => stack sharper
    ci = _bootstrap_ci(delta)
    if n < 30:
        verdict = "UNDERPOWERED"
    elif ci[0] > 0:
        verdict = "SHARPER"
    elif ci[1] < 0:
        verdict = "WORSE"
    else:
        verdict = "UNDERPOWERED"

    doc.update({
        "crps_stack": round(float(sc.mean()), 4),
        "crps_market": round(float(kc.mean()), 4),
        "crps_baseline_model": _baseline_model_crps(),
        "paired_delta_mean": round(float(delta.mean()), 4),
        "paired_delta_95ci": [round(ci[0], 4), round(ci[1], 4)],
        "verdict": verdict,
        "honest_note": "CRPS sharpness only, no dollar edge. Stack = market-implied Gaussian(mu,sigma) "
                        "(same fit as the champion) + bounded pregame mechanism mu-shift(s). "
                        "crps_baseline_model is the pitch_engine ensemble's CRPS reused from "
                        "last_run_mlb.json, not recomputed this run.",
    })
    return doc


def _main() -> int:
    doc = run()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(doc, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
