"""Online Hedge (exponential-weights) combiner over K in-game shadow arms.

CALIBRATION ONLY -- no edge/ROI claim; judged on Brier/gap-to-market like the
sibling arms (gap_blend_arm, gap_regime_arm). <=300 LOC; ASCII only; no network
at import; no data/registry write, no flag flip, no autostart.

ANTI-LOOKAHEAD (binding): weights predicting tick t reflect only settle events
strictly EARLIER than date(t) -- the floor gap_blend_arm._walk_forward asserts,
because same-day cross-game settlement order is unreliable. A game straddling
two dates is pinned to its EARLIEST tick date. Rounds are SETTLED GAMES, not
ticks (per-tick rounds let a denser-logged game dominate; cf. gap_effective_n).
eta = sqrt(8*ln(K)/T), T PRE-REGISTERED per experiment and recorded in the
report -- never read off the realized corpus. Updates BATCH by date, so the
bound's Hoeffding term runs over date-batches, and Hedge and comparator losses
must sum over the IDENTICAL round set (see regret_bound, _regret_vs_best_arm).

Per-file test: python -m pytest scripts/platformkit/ingame/test_hedge_combiner.py -q
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import gap_effective_n

__all__ = ["HedgeState", "initial_state", "predict", "fold_settlement",
           "regret_bound", "evaluate", "render"]


@dataclass(frozen=True)
class HedgeState:
    arm_names: tuple[str, ...]
    weights: tuple[float, ...]          # sums to 1.0
    eta: float
    t_rounds: int                        # pre-registered T used to derive eta
    games_folded: frozenset[str]         # settle-events already applied (idempotency)


def _finite(value: Any) -> float | None:
    """Float, or None when missing or non-finite. A NaN would permanently poison
    the weight vector (exp(-eta*NaN) -> NaN everywhere), so non-finite is treated
    as ABSENT -- already a first-class state here. Drops are counted."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def initial_state(arm_names: Sequence[str], t_rounds: int) -> HedgeState:
    """Uniform-weight Hedge state (no prior favorite), eta tuned for T rounds."""
    names = tuple(arm_names)
    if len(names) < 1:
        raise ValueError("initial_state requires at least one arm")
    if t_rounds < 1:
        raise ValueError("t_rounds must be a positive expected settled-game count")
    k = len(names)
    eta = math.sqrt(8.0 * math.log(k) / t_rounds)  # log(1) == 0 -> eta == 0 for K=1
    return HedgeState(arm_names=names, weights=tuple(1.0 / k for _ in names),
                      eta=eta, t_rounds=t_rounds, games_folded=frozenset())


def predict(state: HedgeState, arm_probs: Mapping[str, float | None]) -> float | None:
    """Weighted average over arms with a usable prob, renormalized. An arm
    absent, None, or non-finite is dropped from both sums -- never defaulted.
    Returns None if no arm is available."""
    total_w = total_wp = 0.0
    for name, w in zip(state.arm_names, state.weights):
        p = _finite(arm_probs.get(name))
        if p is None:
            continue
        total_w += w
        total_wp += w * p
    return (total_wp / total_w) if total_w > 0.0 else None


def _brier(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    values = [(float(p) - float(y)) ** 2 for p, y in zip(probabilities, outcomes)]
    return float(sum(values) / len(values)) if values else float("nan")


def fold_settlement(state: HedgeState, game_id: str,
                    per_arm_tick_probs: Mapping[str, Sequence[float]],
                    outcome: float) -> HedgeState:
    """Apply one game's batched Hedge update; idempotent on a repeated game_id.
    An arm with no usable tick has its loss undefined this round: its weight is
    left UNCHANGED, then the vector is renormalized -- keeping max weight >= 1/K,
    so the denominator cannot reach zero and no long-horizon underflow to a
    degenerate weight vector is reachable."""
    gid = str(game_id)
    if gid in state.games_folded:
        return state
    y = _finite(outcome)
    if y is None:
        raise ValueError("fold_settlement requires a finite settled outcome")
    new_weights = []
    for name, w in zip(state.arm_names, state.weights):
        clean = [p for p in (_finite(v) for v in per_arm_tick_probs.get(name) or ()) if p is not None]
        if not clean:
            new_weights.append(w)
            continue
        new_weights.append(w * math.exp(-state.eta * _brier(clean, [y] * len(clean))))
    total = sum(new_weights)
    return HedgeState(arm_names=state.arm_names, weights=tuple(w / total for w in new_weights),
                      eta=state.eta, t_rounds=state.t_rounds,
                      games_folded=state.games_folded | {gid})


def regret_bound(eta: float, start_weight: float, loss_range_squares: float) -> float:
    """ln(1/w_start)/eta + eta*sum_d(R_d^2)/8 -- fixed eta, any horizon.

    ``start_weight`` is the comparator's weight at the FIRST compared round (1/K
    from a uniform start); burn-in updates before it shrink the comparator and
    are charged here, never assumed away. ``loss_range_squares`` is sum_d(M_d^2)
    over batches of M_d unit-range losses -- equal to T for one loss per batch,
    collapsing to sqrt(T*ln(K)/2) at eta=sqrt(8*ln(K)/T)."""
    if eta <= 0.0:
        return 0.0                       # K == 1: nothing to regret against
    if not 0.0 < start_weight <= 1.0:
        raise ValueError("start_weight must lie in (0, 1]")
    return math.log(1.0 / start_weight) / eta + eta * loss_range_squares / 8.0


def _assert_prior_date(train_date_max: str, test_date: str) -> None:
    """Mirror gap_blend_arm/gap_regime_arm's walk-forward ordering invariant."""
    assert train_date_max < test_date, "walk-forward date ordering violated"


def _game_and_date(row: Mapping[str, Any]) -> tuple[str, str]:
    """Tick identity: game id plus its YYYY-MM-DD date."""
    value = row.get("game_date", row.get("date", row.get("timestamp")))
    if row.get("game") is None or value is None:
        raise ValueError("each tick requires a game id and game_date/date/timestamp")
    return str(row["game"]), str(value)[:10]


def _group_games(ticks: Sequence[Mapping[str, Any]], arm_probs: Mapping[str, Sequence[Any]],
                 arm_names: Sequence[str]) -> tuple[dict[str, dict[str, Any]], int]:
    """Group settled ticks into per-game rounds; return (games, n_nonfinite_dropped)."""
    games: dict[str, dict[str, Any]] = {}
    dropped = 0
    for i, row in enumerate(ticks):
        if row.get("outcome") is None:
            continue
        (gid, date), outcome = _game_and_date(row), float(row["outcome"])
        entry = games.setdefault(gid, {"date": date, "outcome": outcome,
                                       "arm_ticks": {name: [] for name in arm_names},
                                       "indices": []})
        if entry["outcome"] != outcome:
            raise ValueError("game %s has conflicting settled outcomes" % gid)
        entry["date"] = min(entry["date"], date)   # pin to earliest tick date
        entry["indices"].append(i)
        for name in arm_names:
            probs = arm_probs.get(name) or ()
            raw = probs[i] if i < len(probs) else None
            value = _finite(raw)
            if value is None:
                dropped += 1 if raw is not None else 0
                continue
            entry["arm_ticks"][name].append(value)
    return games, dropped


def _metrics(rows: pd.DataFrame) -> dict[str, Any]:
    hedge_brier, market_brier = (_brier(rows[c], rows["outcome"]) for c in ("hedge_prob", "market_prob"))
    return {"n_games": int(rows["game"].nunique()), "n_ticks": int(len(rows)),
            "hedge_brier": hedge_brier, "market_brier": market_brier,
            "gap": hedge_brier - market_brier}


def _slice_report(rows: pd.DataFrame, bootstrap_iterations: int) -> dict[str, Any]:
    usable = rows.dropna(subset=["hedge_prob", "market_prob"])
    if usable.empty:
        return {"metrics": None, "game_clustered_ci_90_gap": None}
    boot = gap_effective_n.cluster_bootstrap(usable, lambda sample: _metrics(sample)["gap"],
                                             iterations=bootstrap_iterations, game_column="game")
    return {"metrics": _metrics(usable),
            "game_clustered_ci_90_gap": [float(np.quantile(boot, .05)), float(np.quantile(boot, .95))]}


def _regret_vs_best_arm(games: Mapping[str, Mapping[str, Any]], scored_rows: Sequence[Mapping[str, Any]],
                        start_weights: Sequence[float], arm_names: Sequence[str],
                        eta: float) -> dict[str, Any] | None:
    """Regret over exactly the rounds Hedge PREDICTED, vs arms present on all.
    Both sums run over one identical, deterministically ordered round set; an arm
    absent on some rounds is excluded, since it would accrue an unfairly small
    cumulative loss and win the hindsight comparison."""
    hedge_by_game: dict[str, list[float]] = defaultdict(list)
    date_by_game: dict[str, str] = {}
    for row in scored_rows:
        if row["hedge_prob"] is not None:
            hedge_by_game[row["game"]].append(float(row["hedge_prob"]))
            date_by_game[row["game"]] = row["date"]
    rounds = sorted(hedge_by_game)
    if not rounds:
        return None
    batches = Counter(date_by_game[gid] for gid in rounds)
    summary = {"status": "OK", "n_rounds": len(rounds), "n_batches": len(batches),
               "loss_range_squares": float(sum(size * size for size in batches.values()))}
    eligible = [name for name in arm_names if all(games[gid]["arm_ticks"][name] for gid in rounds)]
    if not eligible:
        return {**summary, "status": "NO_COMPARABLE_ARM"}

    def _loss(probs: Sequence[float], gid: str) -> float:
        return _brier(probs, [games[gid]["outcome"]] * len(probs))

    cumulative_arm = {name: sum(_loss(games[gid]["arm_ticks"][name], gid) for gid in rounds)
                      for name in eligible}
    cumulative_hedge = sum(_loss(hedge_by_game[gid], gid) for gid in rounds)
    best_arm = min(cumulative_arm, key=cumulative_arm.get)
    bound = regret_bound(eta, start_weights[list(arm_names).index(best_arm)],
                         summary["loss_range_squares"])
    regret = cumulative_hedge - cumulative_arm[best_arm]
    return {**summary, "best_arm": best_arm, "eligible_arms": eligible,
            "cumulative_hedge_loss": cumulative_hedge,
            "cumulative_best_arm_loss": cumulative_arm[best_arm],
            "regret": regret, "bound": bound, "within_bound": bool(regret <= bound + 1e-9)}


def evaluate(ticks: Sequence[Mapping[str, Any]], arm_probs: Mapping[str, Sequence[float | None]],
             t_rounds: int, bootstrap_iterations: int = 300) -> dict[str, Any]:
    """Fold each date's settled prior games, then predict that date's ticks with
    PRE-fold weights. Mirrors gap_blend_arm.evaluate's fold/slice shape."""
    arm_names = tuple(arm_probs.keys())
    if not arm_names or not ticks:
        return {"status": "INSUFFICIENT", "folds": [], "slices": {}}
    games, dropped = _group_games(ticks, arm_probs, arm_names)
    if not games:
        return {"status": "INSUFFICIENT", "folds": [], "slices": {}}
    dates = sorted({g["date"] for g in games.values()})
    by_date: dict[str, list[str]] = defaultdict(list)
    for gid, game in games.items():
        by_date[game["date"]].append(gid)
    state = initial_state(arm_names, t_rounds)
    start_weights: tuple[float, ...] | None = None
    scored_rows: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    for idx in range(1, len(dates)):
        test_date, prev_date = dates[idx], dates[idx - 1]
        _assert_prior_date(prev_date, test_date)
        for gid in sorted(by_date[prev_date]):
            game = games[gid]
            per_arm = {name: probs for name, probs in game["arm_ticks"].items() if probs}
            state = fold_settlement(state, gid, per_arm, game["outcome"])
        if start_weights is None:
            start_weights = state.weights          # weights entering the first scored round
        before = len(scored_rows)
        for gid in sorted(by_date[test_date]):
            game = games[gid]
            for i in game["indices"]:
                per_tick = {name: (arm_probs[name][i] if i < len(arm_probs[name]) else None)
                            for name in arm_names}
                scored_rows.append({"game": gid, "date": test_date, "outcome": game["outcome"],
                                    "market_prob": ticks[i].get("market_prob"),
                                    "hedge_prob": predict(state, per_tick),
                                    "in_window": bool(ticks[i].get("in_window", True))})
        folds.append({"test_date": test_date, "train_date_max": prev_date, "status": "OK",
                      "games_folded": len(state.games_folded),
                      "scored_ticks": len(scored_rows) - before})
    if not scored_rows:
        return {"status": "INSUFFICIENT", "folds": folds, "slices": {}}
    frame = pd.DataFrame(scored_rows)
    slices = {"all_ticks": frame, "in_window_ticks": frame[frame["in_window"]]}
    return {"status": "OK", "t_rounds": t_rounds, "eta": state.eta,
            "arm_names": list(arm_names), "folds": folds,
            "n_nonfinite_arm_probs_dropped": dropped,
            "slices": {name: _slice_report(rows, bootstrap_iterations) for name, rows in slices.items()},
            "regret_vs_best_arm": _regret_vs_best_arm(games, scored_rows, start_weights,
                                                      arm_names, state.eta)}


def render(report: Mapping[str, Any]) -> str:
    """Render slice Brier/gap metrics plus the empirical regret-bound check."""
    if report.get("status") != "OK":
        return "HEDGE_COMBINER | INSUFFICIENT"
    lines = ["SLICE | STATUS | N_GAMES | N_TICKS | HEDGE_BRIER | MARKET_BRIER | GAP | CI_90"]
    for name, section in report.get("slices", {}).items():
        metrics = section.get("metrics")
        if metrics is None:
            lines.append("%s | INSUFFICIENT | - | - | - | - | - | -" % name)
            continue
        ci = section.get("game_clustered_ci_90_gap")
        interval = "-" if not ci else "[%.6f, %.6f]" % (ci[0], ci[1])
        lines.append("%s | OK | %d | %d | %.6f | %.6f | %.6f | %s" %
                     (name, metrics["n_games"], metrics["n_ticks"], metrics["hedge_brier"],
                      metrics["market_brier"], metrics["gap"], interval))
    regret = report.get("regret_vs_best_arm") or {}
    if regret.get("status") == "OK":
        lines.append("REGRET | %.6f | BOUND | %.6f | BEST_ARM | %s | N_ROUNDS | %d | WITHIN_BOUND | %s" %
                     (regret["regret"], regret["bound"], regret["best_arm"], regret["n_rounds"],
                      regret["within_bound"]))
    elif regret:
        lines.append("REGRET | %s | N_ROUNDS | %d" % (regret["status"], regret["n_rounds"]))
    if report.get("n_nonfinite_arm_probs_dropped"):
        lines.append("DROPPED_NONFINITE_ARM_PROBS | %d" % report["n_nonfinite_arm_probs_dropped"])
    return "\n".join(lines)
