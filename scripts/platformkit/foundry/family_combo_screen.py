"""S79 -- the FAMILY-LEVEL COMBINATION screen: does a family's top-k together add anything?

Every foundry screen so far is ONE feature vs the corpus incumbent (S58c: 0/600 soccer+tennis
screens beat the devigged close). This module asks the next question on the SCREEN side only:
take a frozen family's top-k singles by their STORED screen improvement, fit ONE L2 logistic on
[1, logit(p_ref), z(f_1..f_k)] walk-forward (the harness's own purge + embargo + vintage), and
compare its paired Brier loss with the incumbent's on the same held-out rows -- beside the k=1
arm, so the reader sees whether combining added anything at all.

IN-SAMPLE SELECTION, SAID PLAINLY: the top-k are chosen BY their screen-side improvement and
then scored on that SAME screen partition. Every number here is a CEILING, not a verdict. The
verdict side (E1/I1/D1 for soccer, the odd ISO-week blocks elsewhere) is never opened, nothing
is charged, no prereg is sealed and the FWER ledger is never read or written.

nba/mlb default to `p_base` (Elo) as the incumbent, LABELLED in every row of output; with
S113's FOUNDRY_CLOSE_INCUMBENT=1 they take the S112 market close instead (label per
close_source) and the window narrows to the close-covered rows.
Calibration language only. ASCII.

Per-file test: python -m pytest tests/platformkit/foundry/test_family_combo_screen.py -q
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from scripts.platformkit.eval_gate import scoring
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.walkforward import walk_forward
from scripts.platformkit.foundry import tiers
from scripts.platformkit.foundry.promotion_report import screens
from scripts.platformkit.foundry.screen_predictor import (MIN_FIT_ROWS, REFIT_EVERY, RIDGE,
                                                          ScreenBinder, ScreenRefused,
                                                          _clip, _logistic, _logit, corpus_states)

SPORTS = ("mlb", "nba", "soccer", "tennis")
SEED = 20260903              # the S58c partition seed; a different seed is a different partition
SCREEN_ROWS = 800            # the S58c screen window, unchanged (Q3: no bar moves)
DEFAULT_K = 5
BAR = 0.004                  # the S79 register row's screen-side bar, quoted from that row
DB_DIR = Path("data/cache/eval_gate/s58_screens")
OUT_PREFIX = Path("data/cache/eval_gate/s79_family_combo_2026-09-03")


def _name(hypothesis) -> str:
    """A per-hypothesis feature key. `feature__transform` alone COLLIDES (three ew halflives of
    one column share it), which would silently screen a k=5 as a k=3."""
    params = "-".join("%s%s" % (key, value) for key, value in hypothesis.params) or "none"
    return "%s__%s__%s" % (hypothesis.feature, hypothesis.transform, params)


class ComboPredictor:
    """walk_forward's predict_fn for k features: logistic on [1, logit(p_ref), z(f_1..f_k)].

    Deliberately the single-feature `RealScreenPredictor` with a wider design matrix -- same
    refit cadence, same ridge, same MIN_FIT_ROWS, same "missing != bad" fallback to the
    incumbent -- so the k=1 arm REPRODUCES the stored S58c screen instead of re-deriving it.
    A row is fit on only when every one of the k is present; a test row missing any one falls
    back to p_ref (B3: absent evidence passes through, it never scores as bad).
    """

    def __init__(self, features: Sequence[str], refit_every: int = REFIT_EVERY) -> None:
        self.features, self.refit_every = list(features), int(refit_every)
        self._path_key, self._fit = None, None
        self.fits: list = []

    def _rows(self, states: Sequence[dict]) -> list:
        out = []
        for state in states:
            values = [state["features"].get(f) for f in self.features]
            if all(v is not None for v in values):
                out.append((state["features"]["p_ref"], values, state["outcome"]))
        return out

    def _refit(self, train: Sequence[dict]) -> None:
        rows = self._rows(train)
        self._fit = None
        if len(rows) >= MIN_FIT_ROWS:
            x = np.array([r[1] for r in rows], dtype=float)
            mu = x.mean(axis=0)
            sd = np.where(x.std(axis=0) > 0.0, x.std(axis=0), 1.0)
            design = np.column_stack([np.ones(len(rows)), [_logit(r[0]) for r in rows],
                                      (x - mu) / sd])
            coef = _logistic(design, np.array([r[2] for r in rows], dtype=float))
            self._fit = (coef, mu, sd)
        self.fits.append({"n_train": len(train), "n_fit": len(rows),
                          "coef": None if self._fit is None else [float(c) for c in self._fit[0]],
                          "mu": None if self._fit is None else [float(m) for m in mu],
                          "sd": None if self._fit is None else [float(s) for s in sd]})

    def __call__(self, train: Sequence[dict], test: dict, select_inside: bool) -> float:
        if not select_inside:
            raise ValueError("the screen fits inside the window only (select_inside=True)")
        p_ref = _clip(test["features"]["p_ref"])
        path_key = (id(train), train[0]["game_id"] if train else "", train[-1]["game_id"] if train else "", len(train) // self.refit_every)
        if path_key != self._path_key:
            self._path_key = path_key
            self._refit(train)
        values = [test["features"].get(f) for f in self.features]
        if self._fit is None or any(v is None for v in values):
            return p_ref
        coef, mu, sd = self._fit
        z = (np.array(values, dtype=float) - mu) / sd
        eta = coef[0] + coef[1] * _logit(p_ref) + float(np.dot(coef[2:], z))
        return _clip(1.0 / (1.0 + math.exp(-eta)))

    def archive(self) -> dict:
        return {"predictor": "combo_logistic_v1", "features": list(self.features),
                "refit_every": self.refit_every, "min_fit_rows": MIN_FIT_ROWS, "ridge": RIDGE,
                "fits": list(self.fits)}


def stored_screens(db_dir: Path = DB_DIR, sports: Sequence[str] = SPORTS) -> dict:
    """{(family, sport): [Screen, ...] sorted by STORED screen improvement, best first}.

    Improvement = brier_close - brier_model (positive = the single beat its incumbent); the
    S58c DB stores both Briers, so nothing is recomputed here and the ranking is exactly the
    one the promotion report printed (which ranks on the negated quantity, `delta`).
    """
    grouped: dict = defaultdict(list)
    for sport in sports:
        path = Path(db_dir) / ("%s.sqlite" % sport)
        if not path.exists():
            continue
        for screen in screens(path):
            grouped[(screen.family, screen.hypothesis.sport)].append(screen)
    return {key: sorted(rows, key=lambda s: (-(s.brier_close - s.brier_model), s.hash))
            for key, rows in grouped.items()}


def screen_side(sport: str) -> tuple:
    """(binder, partition, incumbent) for one sport's SCREEN side -- the verdict side is never
    materialised here, so no leak onto it is even reachable."""
    states, table, incumbent = corpus_states(sport)
    partition = tiers.partition_corpus(states, seed=SEED)
    side = [s for s in states if tiers._event_id(s) in partition.screen_ids]
    return ScreenBinder(sport, side, table, SCREEN_ROWS, incumbent), partition, incumbent


def bind_features(binder: ScreenBinder, picks: Sequence) -> tuple:
    """(states, names, used) -- the served window carrying every pick's as-of value.

    Two picks whose value VECTORS are identical (`p_base` and `p_home_elo` are one column under
    two names) collapse to one, else a k=5 is really a k=3 plus two ridge-shrunk copies.
    """
    columns, names, used = [], [], []
    for pick in picks:
        try:
            values = binder.feature_values(pick.hypothesis).to_numpy(dtype=float)
        except (ScreenRefused, KeyError, ValueError):
            continue
        filled = np.nan_to_num(values, nan=-9e9)
        if any(np.array_equal(filled, np.nan_to_num(c, nan=-9e9)) for c in columns):
            continue
        columns.append(values)
        names.append(_name(pick.hypothesis))
        used.append(pick)
    served = list(zip(binder.states, *columns))[-binder.rows:] if columns else []
    states = []
    for row in served:
        state, values = row[0], row[1:]
        avail = "%sT00:00:00" % state["game_date"]
        new = dict(state)
        new["features"] = {"p_ref": float(state["devig_close_prob"])}
        new["feature_avail"] = {"p_ref": avail}
        for name, value in zip(names, values):
            new["features"][name] = None if not np.isfinite(value) else float(value)
            new["feature_avail"][name] = avail
        states.append(new)
    return states, names, used


def score(states: Sequence[dict], names: Sequence[str], sport: str) -> dict:
    """One walk-forward arm: paired Brier vs the incumbent, cluster-robust DM, per-event series.

    d = loss_incumbent - loss_model, the dm_test contract (positive mean = model better), so
    `mean_diff` IS the improvement and the CI reads in the same direction. `tiers._run_screen`
    passes the NEGATED difference, so a stored screen's dm_stat sign is the mirror of this one
    (its two-tailed p is unaffected).
    """
    predictor = ComboPredictor(names)
    records = walk_forward(list(states), predictor).records
    model, close, y = (np.array([r[key] for r in records], dtype=float)
                       for key in ("p_model", "p_close", "y"))
    by_id = {tiers._event_id(s): s for s in states}
    try:
        cluster_key, clusters = tiers._cluster_ids([by_id[r["game_id"]] for r in records], sport)
    except ValueError:
        cluster_key, clusters = "event_id", [r["game_id"] for r in records]
    loss_model, loss_close = (model - y) ** 2, (close - y) ** 2
    differential = (loss_close - loss_model).tolist()
    dm = diebold_mariano(differential, clusters)
    brier_model, brier_close = float(scoring.brier(model, y)), float(scoring.brier(close, y))
    return {"k": len(names), "features": list(names), "n_events": len(records),
            "n_unique_events": len({r["game_id"] for r in records}),
            "brier_model": brier_model, "brier_incumbent": brier_close,
            "improvement": brier_close - brier_model,
            "dm_stat": dm.dm_stat, "dm_p": dm.p_value, "ci95": list(dm.ci95),
            "n_clusters": dm.n_clusters, "cluster_key": cluster_key,
            "n_eff": tiers._n_eff(differential, clusters),
            "fits": predictor.archive()["fits"],
            "series": [(r["game_id"], r["ts"], c, float(a), float(b), float(b - a))
                       for r, c, a, b in zip(records, clusters, loss_model, loss_close)]}


def run_family(binder: ScreenBinder, sport: str, picks: Sequence, k: int) -> Optional[dict]:
    """The combo arm and the k=1 arm for one family; None when fewer than 2 features bind."""
    states, names, used = bind_features(binder, list(picks)[: max(k, 1) * 3])
    names = names[:k]
    if len(names) < 2:
        return None
    return {"combo": score(states, names, sport), "single": score(states, names[:1], sport),
            "picked": [{"hash": p.hash, "feature": p.hypothesis.feature,
                        "transform": p.hypothesis.transform, "params": list(p.hypothesis.params),
                        "stored_improvement": p.brier_close - p.brier_model}
                       for p in used[:k]]}


def _write_series(path: Path, series: Sequence) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(["event_id", "ts", "cluster", "loss_model", "loss_incumbent", "d"])
        writer.writerows(series)


def run(sports: Sequence[str] = SPORTS, k: int = DEFAULT_K, db_dir: Path = DB_DIR,
        out_prefix: Optional[Path] = OUT_PREFIX) -> dict:
    grouped = stored_screens(Path(db_dir), sports)
    eligible = {key: rows for key, rows in grouped.items() if len(rows) >= 2}
    results = []
    for sport in sports:
        keys = sorted(key for key in eligible if key[1] == sport)
        if not keys:
            continue
        binder, partition, incumbent = screen_side(sport)
        for family, _ in keys:
            got = run_family(binder, sport, eligible[(family, sport)], k)
            if got is None:
                continue
            got.update(family=family, sport=sport, incumbent=incumbent,
                       screen_partition_sha256=partition.screen_sha256,
                       partition_basis=partition.basis,
                       screened_singles=len(eligible[(family, sport)]))
            results.append(got)
            if out_prefix is not None:
                _write_series(Path("%s_%s.csv" % (out_prefix, family)), got["combo"]["series"])
    results.sort(key=lambda r: -r["combo"]["improvement"])
    summary = {"spec": "S79", "seed": SEED, "screen_rows": SCREEN_ROWS, "k_max": k, "bar": BAR,
               "selection": "IN-SAMPLE: top-k chosen by the stored SCREEN improvement and scored "
                            "on that same SCREEN partition -- a ceiling, never a verdict",
               "charged": False, "verdict_side_opened": False,
               "families_eligible": len(eligible), "families_scored": len(results),
               "clears_bar": [r["family"] for r in results if r["combo"]["improvement"] >= BAR],
               "results": results}
    if out_prefix is not None:
        Path("%s.json" % out_prefix).parent.mkdir(parents=True, exist_ok=True)
        Path("%s.json" % out_prefix).write_text(json.dumps(summary, indent=1), encoding="ascii")
    return summary


def render(summary: dict) -> str:
    lines = ["| rank | family | sport | k | n_events | Brier incumbent | Brier k=1 | Brier combo "
             "| improvement combo | DM CI 95 | clears +%.3f |" % summary["bar"],
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for rank, row in enumerate(summary["results"], 1):
        combo, single = row["combo"], row["single"]
        lines.append("| %d | %s | %s | %d | %d | %.6f | %.6f | %.6f | %+.6f | [%+.6f, %+.6f] | %s |"
                     % (rank, row["family"], row["sport"], combo["k"], combo["n_events"],
                        combo["brier_incumbent"], single["brier_model"], combo["brier_model"],
                        combo["improvement"], combo["ci95"][0], combo["ci95"][1],
                        "YES" if combo["improvement"] >= summary["bar"] else "no"))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sport", nargs="+", default=list(SPORTS), choices=list(SPORTS))
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--db-dir", default=str(DB_DIR))
    parser.add_argument("--out-prefix", default=str(OUT_PREFIX))
    args = parser.parse_args()
    summary = run(args.sport, args.k, Path(args.db_dir), Path(args.out_prefix))
    print(render(summary))
    print("")
    print("families scored=%d of %d eligible; clears +%.3f: %s" % (
        summary["families_scored"], summary["families_eligible"], summary["bar"],
        summary["clears_bar"] or "NONE"))
    print("SELECTION: %s" % summary["selection"])


if __name__ == "__main__":
    main()
