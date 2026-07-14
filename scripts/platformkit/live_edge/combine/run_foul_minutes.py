"""scripts.platformkit.live_edge.combine.run_foul_minutes -- LIVE-EDGE CYCLE 5
FOUL-MINUTES experiment: does the possession-grain foul_state substrate
(foul_minutes.py) improve C1's minutes combiner
(scripts/platformkit/live_edge/combine/minutes_combiner.py) OOS?

SAME walk-forward split, SAME loss (pinball@median), SAME seeds as C1 --
only the candidate feature set differs (gate baseline comparability rail).
Never edits minutes_combiner.py; imports it read-only.

Method: greedy forward selection starting from C1's OWN best combiner
(baseline_min + foul_rate_prior, hist_gb) as the floor to beat. Each
candidate foul_state feature is tried one at a time; kept only if it
(a) has |corr| <= CORR_SKIP_THRESHOLD with every feature already kept and
(b) reduces reserve pinball vs the running-best set. Every candidate's
marginal delta is reported whether kept or not.

DONE bar: verdict = whether ANY foul_state feature beats C1's OWN combiner
OOS (not just the plain baseline) -- 2 pinned seeds, honest null if not.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_foul_minutes.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

import numpy as np
import pandas as pd

from scripts.platformkit.io_atomic import write_text_atomic
from scripts.platformkit.live_edge.combine import foul_minutes as fm
from scripts.platformkit.live_edge.combine import minutes_combiner as mc
from scripts.platformkit.omni import k_sweep_nba as ksn

_OUT_DIR = pathlib.Path("data/omni/live_edge/combine/foul_minutes")
_CANDIDATES = ["early_foul_q1_rate_prior", "team_foultrouble_exposure_prior"]
SEEDS = mc.SEEDS
CORR_SKIP_THRESHOLD = mc.CORR_SKIP_THRESHOLD


def _pinball_seeds(discovery: pd.DataFrame, reserve: pd.DataFrame, cols: list[str]) -> list[float]:
    y_train, y_test = discovery["min"].to_numpy(), reserve["min"].to_numpy()
    out = []
    for seed in SEEDS:
        _, y_pred = mc._fit_predict("hist_gb", discovery[cols].to_numpy(), y_train, reserve[cols].to_numpy(), seed)
        out.append(mc._pinball_median(y_test, y_pred))
    return out


def run_foul_minutes(source=None, foul_seasons_dir: pathlib.Path | None = None,
                      out_dir: pathlib.Path | None = None) -> dict[str, Any]:
    if isinstance(source, pd.DataFrame) and source.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = ksn._load_sweep_frame(source)  # noqa: SLF001 -- same shared loader C1 uses
    if df.empty:
        return {"blocked": True, "reason": "empty sweep frame"}
    df = mc._add_features(df)  # C1's own baseline_min + foul_rate_prior, unchanged

    per_game = fm.build_per_game_foul_features(foul_seasons_dir)
    if per_game.empty:
        return {"blocked": True, "reason": "foul_state substrate empty/absent"}
    df = fm.add_foul_state_features(df, per_game)

    base_cols = ["baseline_min", "foul_rate_prior"]
    discovery, reserve = ksn.split_discovery_reserve(df)
    discovery = discovery.dropna(subset=base_cols)
    reserve = reserve.dropna(subset=base_cols)
    if len(discovery) < 50 or len(reserve) < 50:
        return {"blocked": True, "reason": f"insufficient rows after cold-start drop "
                                            f"(discovery={len(discovery)}, reserve={len(reserve)})"}

    c1_seeds = _pinball_seeds(discovery, reserve, base_cols)
    c1_avg = float(np.mean(c1_seeds))

    kept = list(base_cols)
    running_best_avg = c1_avg
    running_best_seeds = c1_seeds
    running_n = (len(discovery), len(reserve))
    candidate_results: dict[str, Any] = {}
    for cand in _CANDIDATES:
        cd = discovery.dropna(subset=[cand])
        cr = reserve.dropna(subset=[cand])
        if len(cd) < 50 or len(cr) < 50:
            candidate_results[cand] = {"verdict": "INSUFFICIENT_DATA", "n_discovery": len(cd), "n_reserve": len(cr)}
            continue
        corrs = {c: float(np.corrcoef(cd[c], cd[cand])[0, 1]) for c in kept}
        if any(abs(v) > CORR_SKIP_THRESHOLD for v in corrs.values()):
            candidate_results[cand] = {"verdict": "SKIPPED_CORRELATED", "correlations": corrs}
            continue

        # Both sides of the comparison MUST use the identical row subset
        # (kept vs kept+cand, both dropna'd on kept+[cand]) -- comparing
        # against running_best_avg/c1_avg directly would be invalid: those
        # were computed on a DIFFERENT (larger) population whenever a
        # candidate restricts rows (team_foultrouble_exposure_prior is
        # lineup-era-only, 2024-25+). Population size is reported alongside
        # every delta so a smaller-n win can be judged accordingly.
        base_seeds_here = _pinball_seeds(cd, cr, kept)
        base_avg_here = float(np.mean(base_seeds_here))
        trial_seeds = _pinball_seeds(cd, cr, kept + [cand])
        trial_avg = float(np.mean(trial_seeds))
        marginal_delta = base_avg_here - trial_avg  # positive = candidate helped, on the SAME rows
        improves = marginal_delta > 0

        candidate_results[cand] = {
            "verdict": "IMPROVES" if improves else "NULL",
            "n_discovery": len(cd), "n_reserve": len(cr), "correlations": corrs,
            "same_population_base_pinball_avg": base_avg_here,
            "marginal_delta_pinball": marginal_delta,
            "trial_pinball_seeds": trial_seeds, "trial_pinball_avg": trial_avg,
        }
        if improves:
            kept.append(cand)
            running_best_avg = trial_avg
            running_best_seeds = trial_seeds
            running_n = (len(cd), len(cr))

    verdict = "FOUL_STATE_IMPROVES_C1_COMBINER" if len(kept) > len(base_cols) else "HONEST_NULL"
    report = {
        "observable": "minutes", "extends": "c1_minutes_combiner",
        "c1_baseline_features": base_cols,
        "c1_combiner_pinball_avg": c1_avg, "c1_combiner_pinball_seeds": c1_seeds,
        "c1_n_discovery": len(discovery), "c1_n_reserve": len(reserve),
        "candidates_tested": _CANDIDATES, "candidate_results": candidate_results,
        "final_kept_features": kept, "final_pinball_avg": running_best_avg,
        "final_pinball_seeds": running_best_seeds,
        "final_n_discovery": running_n[0], "final_n_reserve": running_n[1],
        "note": "each candidate's marginal delta is computed vs the SAME row "
                "subset (dropna over kept+candidate) -- never compared across "
                "populations of different size; final_n_* may be smaller than "
                "c1_n_* if a kept feature (team_foultrouble_exposure_prior) is "
                "only available in the lineup-store era (2024-25+).",
        "verdict": verdict, "seeds": list(SEEDS),
    }
    _write_report(report, out_dir)
    return report


def _write_report(report: dict, out_dir: pathlib.Path | None) -> None:
    d = out_dir or _OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    write_text_atomic(d / "report.json", json.dumps(report, indent=2, default=str))
    lines = ["# foul_minutes report (LIVE-EDGE CYCLE 5 FOUL-MINUTES)", "",
             f"verdict: **{report['verdict']}**", "",
             f"- C1 combiner (baseline_min+foul_rate_prior) pinball avg: {report['c1_combiner_pinball_avg']:.4f}",
             f"- final kept features: {report['final_kept_features']}",
             f"- final pinball avg: {report['final_pinball_avg']:.4f}", ""]
    for cand, r in report["candidate_results"].items():
        lines.append(f"## {cand}: {r.get('verdict')}")
        for k, v in r.items():
            if k != "verdict":
                lines.append(f"- {k}: {v}")
    write_text_atomic(d / "report.md", "\n".join(lines) + "\n")


if __name__ == "__main__":
    out = run_foul_minutes()
    for k, v in out.items():
        if k != "candidate_results":
            print(f"[foul_minutes] {k}: {v}")


__all__ = ["run_foul_minutes"]
