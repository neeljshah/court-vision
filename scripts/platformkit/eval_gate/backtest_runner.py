"""Frozen odds-corpus backtest runner.

An automated backtest system that does not charge its own trials is a p-hacking machine.
Every invocation therefore appends one row to the cumulative-K ledger before emitting results.
Predictors receive redacted views: training rows retain prior outcomes, while the current
row never includes its outcome or close.  ``close_echo`` is a reference-only exception,
enabled explicitly with ``--allow-reference-close-echo`` and labelled in all output.
"""
from __future__ import annotations

import argparse
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.fwer_budget import cumulative_k, eps_eff
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, log_loss
from scripts.platformkit.eval_gate.walkforward import walk_forward

_MIN_CLUSTERS = 20


def uniform_half(train: Sequence[dict], test: dict, select_inside: bool) -> float:
    """Reference predictor: emits 0.5 without reading any input."""
    return 0.5


def close_echo(train: Sequence[dict], test: dict, select_inside: bool) -> float:
    """Reference-only baseline, valid only when the runner injects its declared field."""
    return float(test["declared_reference_close_prob"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_callable(spec: str) -> Callable[[Sequence[dict], dict, bool], float]:
    module_name, sep, name = spec.partition(":")
    if not sep or not module_name or not name:
        raise ValueError("predictor must use package.path:callable form")
    fn = getattr(importlib.import_module(module_name), name, None)
    if not callable(fn):
        raise ValueError(f"predictor is not callable: {spec}")
    return fn


def _devig(home: object, away: object) -> float | None:
    try:
        home, away = float(home), float(away)
        hd = 1 + (home / 100 if home > 0 else 100 / abs(home))
        ad = 1 + (away / 100 if away > 0 else 100 / abs(away))
        if not np.isfinite(hd + ad) or hd <= 1 or ad <= 1:
            return None
        return float((1 / hd) / ((1 / hd) + (1 / ad)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def load_states(sport: str, start: str, end: str, repo: Path | None = None) -> list[dict]:
    """Join the strength-atlas two-sided close to settled home-win outcomes."""
    root = repo or _repo_root()
    base = root / "data" / "domains" / sport
    odds_path, games_path = base / "odds.parquet", base / "games.parquet"
    if not odds_path.exists() or not games_path.exists():
        raise FileNotFoundError(f"missing frozen corpus: {odds_path} or {games_path}")
    odds, games = pd.read_parquet(odds_path), pd.read_parquet(games_path)
    required_odds = {"date", "home_team", "away_team", "home_ml", "away_ml"}
    required_games = {"date", "home_team", "away_team", "home_win"}
    if not required_odds <= set(odds) or not required_games <= set(games):
        raise ValueError("corpus does not match the verified NBA join schema")
    odds = odds.copy(); games = games.copy()
    odds["date"] = pd.to_datetime(odds["date"], utc=True).dt.date.astype(str)
    games["date"] = pd.to_datetime(games["date"], utc=True).dt.date.astype(str)
    merged = games.merge(odds[list(required_odds)], on=["date", "home_team", "away_team"], how="inner")
    merged = merged[(merged["date"] >= start) & (merged["date"] <= end)].sort_values("date", kind="mergesort")
    states = []
    for row in merged.itertuples(index=False):
        p_close = _devig(row.home_ml, row.away_ml)
        if p_close is None or float(row.home_win) not in (0.0, 1.0):
            continue
        game_id = str(getattr(row, "game_id", f"{row.date}-{row.home_team}-{row.away_team}"))
        states.append({"game_id": game_id, "state_ts": f"{row.date}T12:00:00",
                       "features": {"schedule": 1.0},
                       "feature_avail": {"schedule": f"{row.date}T00:00:00"},
                       "home": str(row.home_team), "away": str(row.away_team),
                       "outcome": int(row.home_win), "devig_close_prob": p_close})
    return states


def _redact(state: dict, *, training: bool, allow_close: bool) -> dict:
    keep = ("game_id", "state_ts", "features", "feature_avail", "home", "away")
    view = {k: state[k] for k in keep}
    if training:
        view["outcome"] = state["outcome"]
    if allow_close and "devig_close_prob" in state:
        view["declared_reference_close_prob"] = state["devig_close_prob"]
    return view


def _reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    out = []
    for lo, hi in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1 else (p >= lo) & (p <= hi)
        out.append({"lo": round(float(lo), 2), "hi": round(float(hi), 2), "n": int(mask.sum()),
                    "mean_prediction": round(float(p[mask].mean()), 6) if mask.any() else None,
                    "observed_rate": round(float(y[mask].mean()), 6) if mask.any() else None})
    return out


def _phase_metrics(records: list[dict]) -> dict:
    dates = sorted({r["ts"][:10] for r in records})
    cuts = (len(dates) // 3, 2 * len(dates) // 3)
    labels = {d: "early" if i < cuts[0] else "mid" if i < cuts[1] else "late" for i, d in enumerate(dates)}
    out: Dict[str, dict] = {}
    for phase in ("early", "mid", "late"):
        rows = [r for r in records if labels[r["ts"][:10]] == phase]
        p, c, y = ([r[k] for r in rows] for k in ("p_model", "p_close", "y"))
        out[phase] = {"n": len(rows), "model_brier": round(brier(p, y), 6),
                      "close_brier": round(brier(c, y), 6), "model_logloss": round(log_loss(p, y), 6),
                      "close_logloss": round(log_loss(c, y), 6)}
    return out


def _charge_ledger(path: Path, spec: str, sport: str, start: str, end: str) -> dict:
    rows = []
    if path.exists():
        rows = [json.loads(line) for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    prior = max((int(r.get("k_cumulative", 0)) for r in rows), default=0)
    row = {"at": datetime.now(timezone.utc).isoformat(), "predictor": spec, "sport": sport,
           "start": start, "end": end, "k_cumulative": cumulative_k(prior, 1)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="ascii") as fh:
        fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
    return row


def run_backtest(spec: str, sport: str, start: str, end: str, *, repo: Path | None = None,
                 ledger_path: Path, allow_reference_close_echo: bool = False) -> dict:
    """Replay one predictor and return the frozen-protocol report."""
    is_echo = spec.endswith(":close_echo")
    if is_echo and not allow_reference_close_echo:
        raise ValueError("close_echo requires --allow-reference-close-echo")
    charge = _charge_ledger(ledger_path, spec, sport, start, end)
    states, predictor = load_states(sport, start, end, repo), _load_callable(spec)
    if not states:
        return {"verdict": "INSUFFICIENT", "reason": "no joined games", "fwer": charge, "predictions": []}

    close_by_game = {s["game_id"]: s["devig_close_prob"] for s in states}

    def guarded(train: Sequence[dict], test: dict, select_inside: bool) -> float:
        view = _redact(test, training=False, allow_close=False)
        if is_echo:
            # walkforward already strips the close; the reference echo gets it
            # from the runner's own side table, clearly labelled.
            view["declared_reference_close_prob"] = close_by_game[view["game_id"]]
        return predictor([_redact(s, training=True, allow_close=False) for s in train],
                         view, select_inside)

    wf = walk_forward(states, guarded)
    records = wf.records
    p, c, y = (np.array([r[k] for r in records], float) for k in ("p_model", "p_close", "y"))
    diff = (c - y) ** 2 - (p - y) ** 2
    dm = diebold_mariano(diff, [r["game_id"] for r in records])
    threshold = eps_eff(0.05, charge["k_cumulative"])
    if dm.n_clusters < _MIN_CLUSTERS:
        verdict = "INSUFFICIENT"
    elif abs(dm.mean_diff) <= 1e-12 or dm.p_value >= threshold:
        verdict = "MATCH"
    else:
        verdict = "BEHIND" if dm.mean_diff < 0 else "MATCH"
    rolling = [{"game_id": records[i]["game_id"], "brier_model": round(brier(p[i-49:i+1], y[i-49:i+1]), 6),
                "brier_close": round(brier(c[i-49:i+1], y[i-49:i+1]), 6)} for i in range(49, len(records))]
    return {"predictor": spec, "sport": sport, "date_range": [start, end], "reference_close_echo": is_echo,
            "n_games": len(records), "fwer": {**charge, "dm_alpha": threshold}, "verdict": verdict,
            "scores": {"model_brier": round(brier(p, y), 6), "close_brier": round(brier(c, y), 6),
                       "model_logloss": round(log_loss(p, y), 6), "close_logloss": round(log_loss(c, y), 6)},
            "dm_vs_close": {"stat": round(dm.dm_stat, 6), "p_value": round(dm.p_value, 6),
                              "mean_loss_diff": round(dm.mean_diff, 8), "n_clusters": dm.n_clusters},
            "reliability_bins": _reliability(p, y), "phase_slices": _phase_metrics(records),
            "rolling_50_game_brier": rolling, "predictions": records}


def ascii_table(report: dict) -> str:
    s, d = report.get("scores", {}), report.get("dm_vs_close", {})
    return "\n".join(["BACKTEST SUMMARY", "predictor                 games  brier    close    logloss  close_ll verdict", "-" * 76,
                      f"{report.get('predictor', 'n/a')[:25]:25} {report.get('n_games', 0):5}  {s.get('model_brier', 0):.6f} {s.get('close_brier', 0):.6f} {s.get('model_logloss', 0):.6f} {s.get('close_logloss', 0):.6f} {report.get('verdict', 'INSUFFICIENT')}",
                      f"DM stat={d.get('stat', 0):.6f} p={d.get('p_value', 1):.6f} clusters={d.get('n_clusters', 0)}"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictor"); parser.add_argument("sport"); parser.add_argument("start"); parser.add_argument("end")
    parser.add_argument("--repo", type=Path, default=None); parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True); parser.add_argument("--allow-reference-close-echo", action="store_true")
    args = parser.parse_args()
    report = run_backtest(args.predictor, args.sport, args.start, args.end, repo=args.repo, ledger_path=args.ledger,
                          allow_reference_close_echo=args.allow_reference_close_echo)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="ascii")
    print(ascii_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
