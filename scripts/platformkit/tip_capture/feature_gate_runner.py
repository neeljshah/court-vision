"""scripts.platformkit.tip_capture.feature_gate_runner -- daily LEAK-FREE GATE
over the accrued tip_capture tick corpus.

For each candidate live feature ingame_features.py already computes (winprob
vs devigged market gap, recent scoring run, foul-tail count, star-on-floor,
margin velocity), tests -- on FORWARD-captured rows only, walk-forward split
by game date (first 70% of games chronologically = train, rest = test) --
whether the feature adds OOS information about the final home_win outcome
BEYOND a baseline of (score margin, fraction of game elapsed).

REUSES, never rebuilds: ingame_features.load_day_rows / build_features_frame /
load_top_usage_names for every feature value -- this module only adds the
outcome join, the baseline (frac_elapsed, not in ingame_features), the walk-
forward split, and the paired bootstrap.

METHOD: fit sklearn LogisticRegression(baseline) and LogisticRegression
(baseline+feature) on TRAIN games only, score per-tick log-loss on TEST rows,
average to per-game mean loss, paired-bootstrap (resample games, 2000 iters,
seed 0) the per-game delta (baseline_loss - candidate_loss; positive =
candidate helps). PASS only if the bootstrap CI lower bound > 0 (feature
strictly helps OOS, surviving game-cluster resampling). Fewer than
--min-test-games test games -> INSUFFICIENT. Otherwise NULL. NULL/INSUFFICIENT
are the expected, correct outcome on a young corpus -- honest nulls are
successes here, not failures.

Outcome source: data/cache/ingame_grade/<sport>/<game_id>.jsonl -- the LAST
row with settled truthy and a home_win field. A game with no settled row is
simply excluded (honest gap), never imputed.

HONESTY (binding): no $/roi/edge anywhere; edge_claimed is always False in the
output artifact. Build only under scripts/platformkit/; <=300 LOC; ASCII only;
no network; never writes data/registry/; never flips a flag.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/tip_capture/test_feature_gate_runner.py -q
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.tip_capture import ingame_features as fx

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
DEFAULT_TIP_DIR = fx.DEFAULT_IN_DIR
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "cache" / "benchmarks" / "live_feature_gate.json"
DEFAULT_MIN_TEST_GAMES = 30
CANDIDATE_FEATURES = [
    "winprob_market_gap", "recent_scoring_run", "foul_count_tail",
    "star_on_floor", "margin_velocity",
]


# --------------------------------------------------------------------------- #
# baseline: fraction of game elapsed (ingame_features has no time axis).
# ponytail: linear-clock heuristic (12min/quarter, 9 innings) -- close enough
# for a baseline feature, upgrade to sport-specific pace if it ever matters.
# --------------------------------------------------------------------------- #

def frac_elapsed(row: Dict[str, Any]) -> float:
    period = row.get("period")
    if period is not None:
        try:
            period = float(period)
        except (TypeError, ValueError):
            return fx.NAN
        if period > 4:
            return 1.0
        clock = row.get("clock")
        remaining = float(clock) if clock is not None else 0.0
        elapsed_in_period = max(0.0, min(720.0, 720.0 - remaining))
        return max(0.0, min(1.0, ((period - 1) * 720.0 + elapsed_in_period) / 2880.0))
    inning = row.get("inning")
    if inning is not None:
        try:
            return max(0.0, min(1.0, float(inning) / 9.0))
        except (TypeError, ValueError):
            return fx.NAN
    return fx.NAN


# --------------------------------------------------------------------------- #
# corpus discovery + outcome join
# --------------------------------------------------------------------------- #

def discover_sports(tip_dir: Path) -> List[str]:
    tip_dir = Path(tip_dir)
    if not tip_dir.is_dir():
        return []
    return sorted(p.name for p in tip_dir.iterdir() if p.is_dir())


def load_sport_rows(sport: str, tip_dir: Path) -> List[Dict[str, Any]]:
    sport_dir = Path(tip_dir) / sport.lower()
    if not sport_dir.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for p in sorted(sport_dir.glob("ingame_*.jsonl")):
        rows.extend(fx.load_day_rows(sport, p.stem.replace("ingame_", ""), in_dir=tip_dir))
    return rows


def load_outcomes(sport: str, grade_dir: Path) -> Dict[str, int]:
    """game_id -> home_win (0/1), from the LAST settled=true row per game
    file. Missing dir / no settled row -> honest absence, never guessed."""
    d = Path(grade_dir) / sport.lower()
    if not d.is_dir():
        return {}
    out: Dict[str, int] = {}
    for p in d.glob("*.jsonl"):
        last = None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("settled") and "home_win" in row:
                last = row
        if last is not None and last.get("home_win") is not None:
            out[p.stem] = int(bool(last["home_win"]))
    return out


def assemble_dataset(rows: Sequence[Dict[str, Any]], outcomes: Dict[str, int],
                     star_names: Set[str]) -> pd.DataFrame:
    feats = fx.build_features_frame(rows, star_names=star_names)
    if feats.empty:
        return feats
    aux = pd.DataFrame.from_records([
        {"game_id": r.get("game_id"), "capture_ts": r.get("capture_ts"),
         "frac_elapsed": frac_elapsed(r)}
        for r in rows
    ])
    df = feats.merge(aux, on=["game_id", "capture_ts"], how="left")
    df["home_win"] = df["game_id"].map(outcomes)
    df["game_date"] = df["capture_ts"].astype(str).str.slice(0, 10)
    return df


# --------------------------------------------------------------------------- #
# the gate: walk-forward split + logistic baseline vs baseline+feature +
# game-clustered paired bootstrap on the test-set log-loss delta.
# --------------------------------------------------------------------------- #

def gate_feature(df: pd.DataFrame, feature: str, min_test_games: int,
                 seed: int = 0, n_boot: int = 2000) -> Dict[str, Any]:
    cols = ["score_margin", "frac_elapsed", feature, "home_win"]
    sub = df.dropna(subset=cols).copy()
    if sub.empty:
        return {"verdict": "INSUFFICIENT", "n_test_games": 0,
                "delta_logloss_mean": None, "ci": None, "note": "no usable rows"}
    sub[feature] = sub[feature].astype(float)
    sub["home_win"] = sub["home_win"].astype(int)

    order = sub.groupby("game_id")["game_date"].min().sort_values()
    game_ids = order.index.tolist()
    split = int(len(game_ids) * 0.7)
    train_ids, test_ids = set(game_ids[:split]), set(game_ids[split:])
    train = sub[sub["game_id"].isin(train_ids)]
    test = sub[sub["game_id"].isin(test_ids)]
    n_test_games = test["game_id"].nunique()
    if n_test_games < min_test_games:
        return {"verdict": "INSUFFICIENT", "n_test_games": int(n_test_games),
                "delta_logloss_mean": None, "ci": None,
                "note": f"fewer than {min_test_games} test games"}
    if train["home_win"].nunique() < 2:
        return {"verdict": "INSUFFICIENT", "n_test_games": int(n_test_games),
                "delta_logloss_mean": None, "ci": None, "note": "degenerate train labels"}

    base_cols, cand_cols = ["score_margin", "frac_elapsed"], ["score_margin", "frac_elapsed", feature]
    try:
        base_model = LogisticRegression(max_iter=1000).fit(train[base_cols], train["home_win"])
        cand_model = LogisticRegression(max_iter=1000).fit(train[cand_cols], train["home_win"])
    except Exception as exc:  # noqa: BLE001 -- an honest fit failure is NULL, not a crash
        return {"verdict": "NULL", "n_test_games": int(n_test_games),
                "delta_logloss_mean": None, "ci": None, "note": f"fit_error:{type(exc).__name__}"}

    eps = 1e-9
    y = test["home_win"].to_numpy(dtype=float)
    p_base = np.clip(base_model.predict_proba(test[base_cols])[:, 1], eps, 1 - eps)
    p_cand = np.clip(cand_model.predict_proba(test[cand_cols])[:, 1], eps, 1 - eps)
    loss_base = -(y * np.log(p_base) + (1 - y) * np.log(1 - p_base))
    loss_cand = -(y * np.log(p_cand) + (1 - y) * np.log(1 - p_cand))

    test = test.copy()
    test["_delta"] = loss_base - loss_cand  # positive = candidate beats baseline
    per_game = test.groupby("game_id")["_delta"].mean().to_numpy()
    mean_delta = float(per_game.mean())

    rng = np.random.default_rng(seed)
    n = len(per_game)
    boot = np.array([per_game[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    lo, hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    verdict = "PASS" if lo > 0 else "NULL"
    return {"verdict": verdict, "n_test_games": int(n_test_games),
            "delta_logloss_mean": mean_delta, "ci": [lo, hi], "note": "ok"}


# --------------------------------------------------------------------------- #
# orchestration + artifact
# --------------------------------------------------------------------------- #

def run(tip_dir: Path, grade_dir: Path, out_path: Path,
       min_test_games: int = DEFAULT_MIN_TEST_GAMES,
       history_path: Optional[Path] = None) -> Dict[str, Any]:
    tip_dir, grade_dir, out_path = Path(tip_dir), Path(grade_dir), Path(out_path)
    corpora: Dict[str, Any] = {}
    features_out: Dict[str, Any] = {}
    for sport in discover_sports(tip_dir):
        rows = load_sport_rows(sport, tip_dir)
        outcomes = load_outcomes(sport, grade_dir)
        game_ids = {r.get("game_id") for r in rows if r.get("game_id")}
        dates = sorted({str(r.get("capture_ts"))[:10] for r in rows if r.get("capture_ts")})
        corpora[sport] = {"n_games": len(game_ids), "n_ticks": len(rows),
                          "date_range": [dates[0], dates[-1]] if dates else None}
        star_names = fx.load_top_usage_names(sport)
        df = assemble_dataset(rows, outcomes, star_names)
        feat_results = {}
        if not df.empty:
            for feature in CANDIDATE_FEATURES:
                feat_results[feature] = gate_feature(df, feature, min_test_games)
        features_out[sport] = feat_results

    artifact = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "corpora": corpora,
        "features": features_out,
        "honest_note": ("walk-forward leak-free gate; PASS requires a game-clustered "
                        "bootstrap CI lower bound > 0 on held-out games; NULL/"
                        "INSUFFICIENT are correct honest outcomes on a young corpus, "
                        "not failures."),
        "edge_claimed": False,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    hist_path = Path(history_path) if history_path else out_path.parent / "live_feature_gate_history.jsonl"
    summary = {
        "as_of": artifact["as_of"],
        "corpora": {s: {"n_games": c["n_games"], "n_ticks": c["n_ticks"]} for s, c in corpora.items()},
        "verdicts": {s: {f: r["verdict"] for f, r in fr.items()} for s, fr in features_out.items()},
    }
    with open(hist_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")
    return artifact


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Leak-free walk-forward gate for tip_capture live features vs a margin+elapsed baseline.")
    ap.add_argument("--tip-dir", default=None)
    ap.add_argument("--grade-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-test-games", type=int, default=DEFAULT_MIN_TEST_GAMES)
    a = ap.parse_args(argv)

    tip_dir = Path(a.tip_dir) if a.tip_dir else DEFAULT_TIP_DIR
    grade_dir = Path(a.grade_dir) if a.grade_dir else DEFAULT_GRADE_DIR
    out_path = Path(a.out) if a.out else DEFAULT_OUT_PATH
    artifact = run(tip_dir, grade_dir, out_path, min_test_games=a.min_test_games)
    print(json.dumps({"out_path": str(out_path), "sports": list(artifact["corpora"].keys())}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "DEFAULT_TIP_DIR", "DEFAULT_GRADE_DIR", "DEFAULT_OUT_PATH", "DEFAULT_MIN_TEST_GAMES",
    "CANDIDATE_FEATURES", "frac_elapsed", "discover_sports", "load_sport_rows",
    "load_outcomes", "assemble_dataset", "gate_feature", "run", "main",
]
