"""scripts.platformkit.live_edge.compose.run_compose -- COMPOSE-2 orchestrator.

Runs the general composition test for two observables (team scoring rate,
player scoring rate -- the highest-claim-count families with a real
baseline; minutes is already answered by C1/minutes_combiner.py, not
rebuilt here) and writes
data/omni/live_edge/compose/COMPOSE_REPORT.md: per observable, baseline vs
best-composed-model OOS pinball delta (both seeds), plus the permutation
attribution table (which claim-context features matter).

Verdict per observable: COMPOSE_BEATS_BASELINE if the best of {GBM
raw-context, EN greedy-interaction} beats baseline-only pinball on the
UNTOUCHED reserve slice; HONEST_NULL otherwise (an expected, reportable
outcome per the rails -- the reserve gate never loosens).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_compose.py -q
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from scripts.platformkit.io_atomic import write_text_atomic
from scripts.platformkit.live_edge.compose import compose as cp
from scripts.platformkit.live_edge.compose import context_gate as cg

_OUT_DIR = pathlib.Path("data/omni/live_edge/compose")
_REPORT_JSON = "COMPOSE_REPORT.json"
_REPORT_MD = "COMPOSE_REPORT.md"


def run_one_observable(name: str, frame: dict[str, Any], min_rows: int = 200) -> dict[str, Any]:
    """Two-part gate, kept separate on purpose (methodology fix,
    2026-07-14): (1) raw-baseline vs best-composed -- the headline
    "combined-vs-baseline" number the program asks for; (2) SAME-MODEL-FAMILY
    baseline-only vs composed -- isolates whether context features add
    anything, independent of a model-class switch (ElasticNet fit-on-scalar
    vs HistGB fit-on-many-features is not a fair "does context help"
    comparison by itself -- both must be checked or a model-family artifact
    could be mistaken for a context-gating win)."""
    discovery, reserve = frame["discovery"], frame["reserve"]
    target, baseline_col = frame["target"], frame["baseline_col"]
    if len(discovery) < min_rows or len(reserve) < min_rows:
        return {"observable": name, "blocked": True,
                "reason": f"insufficient rows (discovery={len(discovery)}, reserve={len(reserve)})"}

    baseline_raw_pinball = cg._pinball_median(reserve[target].to_numpy(), reserve[baseline_col].to_numpy())

    baseline_only_gbm = cg.evaluate_track(discovery, reserve, [baseline_col], target, "hist_gb")
    baseline_only_en = cg.evaluate_track(discovery, reserve, [baseline_col], target, "elastic_net")

    gbm_cols = [baseline_col] + frame["dummy_cols"]
    gbm_track = cg.evaluate_track(discovery, reserve, gbm_cols, target, "hist_gb")

    selected = cg.greedy_select_en(discovery, baseline_col, frame["inter_cols"], target)
    en_cols = [baseline_col] + selected
    en_track = cg.evaluate_track(discovery, reserve, en_cols, target, "elastic_net") if selected else None

    candidates = [("gbm_raw_context", gbm_track, baseline_only_gbm)]
    if en_track:
        candidates.append(("en_greedy_interaction", en_track, baseline_only_en))
    best_name, best_track, best_track_baseline = min(candidates, key=lambda t: t[1]["avg_pinball"])

    beats_raw_baseline = best_track["avg_pinball"] < baseline_raw_pinball
    beats_same_model_baseline = best_track["avg_pinball"] < best_track_baseline["avg_pinball"]
    beats_both = beats_raw_baseline and beats_same_model_baseline

    attr_cols = best_track["features"]
    attr_model = "hist_gb" if best_name == "gbm_raw_context" else "elastic_net"
    attribution = cg.permutation_attribution(discovery, reserve, attr_cols, target, attr_model)

    return {
        "observable": name, "blocked": False,
        "n_discovery": int(len(discovery)), "n_reserve": int(len(reserve)),
        "baseline_raw_pinball": baseline_raw_pinball,
        "baseline_only_same_model_pinball": best_track_baseline["avg_pinball"],
        "best_track": best_name, "best_avg_pinball": best_track["avg_pinball"],
        "best_per_seed": best_track["per_seed_pinball"],
        "gbm_track": {"avg_pinball": gbm_track["avg_pinball"], "per_seed": gbm_track["per_seed_pinball"],
                      "baseline_only_hist_gb": baseline_only_gbm["avg_pinball"]},
        "en_track": ({"selected_features": selected, "avg_pinball": en_track["avg_pinball"],
                       "per_seed": en_track["per_seed_pinball"],
                       "baseline_only_elastic_net": baseline_only_en["avg_pinball"]} if en_track else
                      {"selected_features": [], "note": "greedy selection added nothing (corr gate or no OOS-val gain)"}),
        "delta_vs_raw_baseline": baseline_raw_pinball - best_track["avg_pinball"],
        "delta_vs_same_model_baseline": best_track_baseline["avg_pinball"] - best_track["avg_pinball"],
        "verdict": "COMPOSE_BEATS_BASELINE" if beats_both else (
            "MODEL_FAMILY_ARTIFACT_ONLY" if beats_raw_baseline else "HONEST_NULL"),
        "permutation_attribution": attribution,
        "seeds": list(cg.SEEDS),
    }


def run_compose(out_dir: pathlib.Path | None = None, possessions_source=None, box_source=None,
                 scorer_dir=None, scorer_source=None) -> dict[str, Any]:
    team_frame = cp.build_team_frame(possessions_source, box_source)
    player_frame = cp.build_player_frame(possessions_source, box_source, scorer_dir, scorer_source)
    results = {
        "team_scoring_rate": run_one_observable("team_scoring_rate", team_frame),
        "player_scoring_rate": run_one_observable("player_scoring_rate", player_frame),
        "minutes": {"observable": "minutes", "blocked": True,
                    "reason": "already answered by C1 (minutes_combiner.py) -- not rebuilt"},
    }
    _write_report(results, out_dir)
    return results


def _write_report(results: dict[str, Any], out_dir: pathlib.Path | None) -> None:
    d = out_dir or _OUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    write_text_atomic(d / _REPORT_JSON, json.dumps(results, indent=2, default=str))
    lines = ["# COMPOSE-2 report -- general composition + context-gating vs state-only baseline\n"]
    for name, r in results.items():
        lines.append(f"## {name}\n")
        if r.get("blocked"):
            lines.append(f"BLOCKED: {r['reason']}\n")
            continue
        lines.append(f"verdict: **{r['verdict']}**\n")
        lines.append(f"- n_discovery={r['n_discovery']} n_reserve={r['n_reserve']} seeds={r['seeds']}")
        lines.append(f"- raw state-only baseline pinball@median: {r['baseline_raw_pinball']:.5f}")
        lines.append(f"- same-model-family baseline-only pinball@median: {r['baseline_only_same_model_pinball']:.5f}")
        lines.append(f"- best track: {r['best_track']} avg pinball@median: {r['best_avg_pinball']:.5f} "
                     f"({r['best_per_seed']})")
        lines.append(f"- delta vs raw baseline: {r['delta_vs_raw_baseline']:.5f} (positive = composed wins)")
        lines.append(f"- delta vs SAME-MODEL baseline-only (isolates context contribution): "
                     f"{r['delta_vs_same_model_baseline']:.5f}")
        lines.append(f"- EN greedy-selected features: {r['en_track'].get('selected_features')}")
        lines.append("- permutation attribution (which claim-context features matter):")
        for feat, imp in sorted(r["permutation_attribution"].items(), key=lambda kv: -kv[1])[:10]:
            lines.append(f"  - {feat}: {imp:.5f}")
        lines.append("")
    write_text_atomic(d / _REPORT_MD, "\n".join(lines) + "\n")


if __name__ == "__main__":
    out = run_compose()
    for obs, r in out.items():
        print(f"[compose] {obs}: verdict={r.get('verdict', r.get('reason'))}")


__all__ = ["run_one_observable", "run_compose"]
