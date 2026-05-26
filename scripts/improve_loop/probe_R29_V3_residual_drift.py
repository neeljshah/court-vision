"""probe_R29_V3_residual_drift.py — R29_V3 residual-drift triage.

After R28_U2 fixed pace, R27_T3 still reports 35/75 MAJOR-drifted features.
This probe categorizes every remaining major-drift feature into one of:

  computation_artifact  — cross-season computation method differs
                          (e.g. R25_R1 backfill writes a different default
                          than fetch_historical_seasons.py).
  data_source_drift     — feature is missing for older or newer season
                          (e.g. lineup splits only cached for 2 of 30 teams
                          in 2025-26).
  window_artifact       — feature naturally varies by time of year
                          (early-season defaults pull reference mean low).
  real_signal           — legitimate league-wide change.

It reports the patch result (n majors before/after applying
scripts/patch_R29_V3_residual_drift.py) and lists the irreducible
remaining majors that need separate investigation.

Safety
------
* No network. No subprocess.
* Read-only except the probe results JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PROBE_RESULTS_PATH = _ROOT / "data" / "cache" / "probe_R29_V3_results.json"

_CURRENT_SEASON = "2025-26"
_REFERENCE_SEASONS = ("2022-23", "2023-24", "2024-25")


# Categorization rule: each known drift_major feature mapped to its verdict
# based on inspection of the season_games files + helper functions in
# src/prediction/win_probability.py. Keys not present here default to
# "window_artifact" (the most common case for L10/season-to-date metrics
# that naturally drift between early-season noise and end-of-season values).
_CATEGORIZATION: Dict[str, Tuple[str, str]] = {
    # === computation_artifact ===
    "home_pnr_ppp": ("computation_artifact",
                     "R25_R1 backfill ran before synergy cache populated; "
                     "cache now exists, just needs re-wire"),
    "away_pnr_ppp": ("computation_artifact",
                     "R25_R1 backfill ran before synergy cache populated; "
                     "cache now exists, just needs re-wire"),
    "iso_matchup_edge": ("computation_artifact",
                         "R25_R1 backfill ran before synergy cache populated; "
                         "cache now exists, just needs re-wire"),
    "home_pace_variance": ("computation_artifact",
                           "historical files hard-default to 2.0 (never "
                           "computed); R25_R1 computes real rolling-20 std"),
    "away_pace_variance": ("computation_artifact",
                           "historical files hard-default to 2.0 (never "
                           "computed); R25_R1 computes real rolling-20 std"),
    "sim_win_prob": ("computation_artifact",
                     "_SIM_NEUTRAL constant (0.5) instead of historical MC values"),
    "sim_score_diff_mean": ("computation_artifact",
                            "_SIM_NEUTRAL constant (0.0) instead of historical MC values"),
    "sim_score_diff_std": ("computation_artifact",
                           "_SIM_NEUTRAL constant (10.0) instead of historical MC values"),
    "sim_pace_adj": ("computation_artifact",
                     "_SIM_NEUTRAL constant (1.0) instead of historical MC values"),
    "home_def_rtg_trend": ("computation_artifact",
                           "historical hard-defaults to 0.0 (never computed); "
                           "R25_R1 computes L10-STD trend"),
    "away_def_rtg_trend": ("computation_artifact",
                           "historical hard-defaults to 0.0 (never computed); "
                           "R25_R1 computes L10-STD trend"),

    # === data_source_drift ===
    "home_top_lineup_net_rtg": ("data_source_drift",
                                "only 2 of 30 teams have 2025-26 lineup_splits "
                                "files (LAL+GSW); rest return 0.0"),
    "away_top_lineup_net_rtg": ("data_source_drift",
                                "only 2 of 30 teams have 2025-26 lineup_splits "
                                "files (LAL+GSW); rest return 0.0"),

    # === window_artifact === (early-season defaults pull ref low; current is end-of-season)
    "home_off_rtg":  ("window_artifact", "expanding-window stat; reference mixes early-season defaults"),
    "away_off_rtg":  ("window_artifact", "expanding-window stat; reference mixes early-season defaults"),
    "home_def_rtg":  ("window_artifact", "expanding-window stat; reference mixes early-season defaults"),
    "away_def_rtg":  ("window_artifact", "expanding-window stat; reference mixes early-season defaults"),
    "home_pace":     ("window_artifact", "ratings stabilize end-of-season"),
    "away_pace":     ("window_artifact", "ratings stabilize end-of-season"),
    "home_ts_pct":   ("window_artifact", "stabilizes end-of-season"),
    "away_ts_pct":   ("window_artifact", "stabilizes end-of-season"),
    "away_tov_pct":  ("window_artifact", "stabilizes end-of-season"),
    "home_off_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 112.0"),
    "home_def_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 112.0"),
    "away_off_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 112.0"),
    "away_def_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 112.0"),
    "home_net_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 0.0"),
    "away_net_rtg_L10": ("window_artifact", "L10 — reference includes early-season default 0.0"),
    "home_efg_L10": ("window_artifact", "L10 — reference includes early-season default 0.50"),
    "away_efg_L10": ("window_artifact", "L10 — reference includes early-season default 0.50"),
    "home_off_rtg_home_L10": ("window_artifact", "venue split L10 — reference includes default 112.0"),
    "away_off_rtg_away_L10": ("window_artifact", "venue split L10 — reference includes default 112.0"),
    "home_elo":        ("window_artifact", "ELO accumulates over season; ref includes 1500 starts"),
    "away_elo":        ("window_artifact", "ELO accumulates over season; ref includes 1500 starts"),
    "elo_differential": ("window_artifact", "derived from home_elo - away_elo"),
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_data_root(explicit: str = "") -> Path:
    cands: List[Path] = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("NBA_AI_ROOT")
    if env:
        cands.append(Path(env) / "data")
    cands.append(_ROOT / "data")
    cands.append(Path(r"C:\Users\neelj\nba-ai-system") / "data")
    for c in cands:
        if (c / "nba" / f"season_games_{_CURRENT_SEASON}.json").exists():
            return c
    return _ROOT / "data"


def categorize_majors(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a list of {feature, verdict, why, ks_stat, mean_z} for every major."""
    out: List[Dict[str, Any]] = []
    for r in features:
        if r.get("class") != "drift_major":
            continue
        name = r.get("feature", "")
        verdict, why = _CATEGORIZATION.get(
            name, ("window_artifact", "unclassified — defaults to window_artifact")
        )
        out.append({
            "feature":  name,
            "verdict":  verdict,
            "why":      why,
            "ks_stat":  r.get("ks_stat"),
            "mean_z":   r.get("mean_z"),
            "ref_mean": r.get("ref_mean"),
            "cur_mean": r.get("cur_mean"),
        })
    out.sort(key=lambda x: -(x.get("ks_stat") or 0.0))
    return out


def _load_drift_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_marker(season_games_path: Path) -> Optional[Dict[str, Any]]:
    if not season_games_path.exists():
        return None
    try:
        payload = json.loads(season_games_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, dict):
        m = payload.get("residual_drift_fixes_R29_V3")
        return m if isinstance(m, dict) else None
    return None


def run(data_root: Path,
        pre_drift_path: Optional[Path] = None,
        post_drift_path: Optional[Path] = None) -> Dict[str, Any]:
    pre = _load_drift_report(pre_drift_path) if pre_drift_path else {}
    post = _load_drift_report(post_drift_path) if post_drift_path else {}

    pre_features = pre.get("features") or []
    post_features = post.get("features") or []

    pre_major = sum(1 for r in pre_features if r.get("class") == "drift_major")
    post_major = sum(1 for r in post_features if r.get("class") == "drift_major")
    pre_stable = sum(1 for r in pre_features if r.get("class") == "stable")
    post_stable = sum(1 for r in post_features if r.get("class") == "stable")

    cats_pre = categorize_majors(pre_features)
    cats_post = categorize_majors(post_features)

    by_verdict_pre: Dict[str, int] = {}
    for r in cats_pre:
        by_verdict_pre[r["verdict"]] = by_verdict_pre.get(r["verdict"], 0) + 1

    by_verdict_post: Dict[str, int] = {}
    for r in cats_post:
        by_verdict_post[r["verdict"]] = by_verdict_post.get(r["verdict"], 0) + 1

    sg_path = data_root / "nba" / f"season_games_{_CURRENT_SEASON}.json"
    marker = _read_marker(sg_path)

    delta = pre_major - post_major
    verdict = "PASS" if delta >= 3 else "INSUFFICIENT"

    summary = {
        "probe":                 "R29_V3",
        "ts":                    _iso_now(),
        "data_root":             str(data_root),
        "drift_count_before":    pre_major,
        "drift_count_after":     post_major,
        "drift_count_delta":     delta,
        "stable_before":         pre_stable,
        "stable_after":          post_stable,
        "verdict":               verdict,
        "fixes_applied":         (marker or {}).get("fixes_applied", []),
        "fixes_applied_count":   len((marker or {}).get("fixes_applied", [])),
        "fix_marker":            marker,
        "categorization_pre":    by_verdict_pre,
        "categorization_post":   by_verdict_post,
        "top_5_majors_pre":      cats_pre[:5],
        "remaining_majors":      cats_post,
        "n_remaining_majors":    len(cats_post),
        "irreducible_majors":    [r for r in cats_post
                                  if r["verdict"] in ("window_artifact", "real_signal")],
        "current_season":        _CURRENT_SEASON,
        "pre_drift_report":      str(pre_drift_path) if pre_drift_path else None,
        "post_drift_report":     str(post_drift_path) if post_drift_path else None,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="", type=str)
    ap.add_argument("--pre-drift",
                    default=str(_ROOT / "data" / "cache" / "drift_post_R28_U2.json"),
                    help="Drift report from BEFORE the R29_V3 patch.")
    ap.add_argument("--post-drift",
                    default=str(_ROOT / "data" / "cache" / "drift_post_R29_V3.json"),
                    help="Drift report from AFTER the R29_V3 patch.")
    args = ap.parse_args()

    root = _resolve_data_root(args.data_root)
    summary = run(root,
                  pre_drift_path=Path(args.pre_drift),
                  post_drift_path=Path(args.post_drift))
    PROBE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROBE_RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    # Compact stdout summary.
    print(json.dumps({
        "probe": summary["probe"],
        "verdict": summary["verdict"],
        "drift_count_before": summary["drift_count_before"],
        "drift_count_after":  summary["drift_count_after"],
        "drift_count_delta":  summary["drift_count_delta"],
        "fixes_applied":      summary["fixes_applied"],
        "categorization_pre": summary["categorization_pre"],
        "categorization_post": summary["categorization_post"],
        "n_remaining_majors": summary["n_remaining_majors"],
    }, indent=2, default=str))
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
