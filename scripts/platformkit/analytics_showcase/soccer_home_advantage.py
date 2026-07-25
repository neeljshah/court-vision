"""soccer_home_advantage.py -- descriptive home-advantage decomposition for
international soccer, using the neutral-site flag as a natural control.

data/domains/soccer_intl/results.parquet carries a real `neutral` boolean per
match. Splitting on it isolates true home-venue advantage (neutral=False)
from a "neutral" baseline (neutral=True) that still shares crowd/travel/
familiarity confounds -- it is not a clean zero-advantage control, just the
best one available in this corpus (see confounds below).

THE STORY (graduated from the committed mechanism ledger, CONFIRMED_LOCAL):
home advantage is real and the true-home/neutral gap GREW over time, but not
because true-home edge rose (flat: 0.6743 pre-2000 vs 0.6745 after) -- it grew
because the NEUTRAL-venue edge COLLAPSED (0.4556 -> 0.1760), consistent with
genuinely neutral tournament sites replacing quasi-home neutral games in the
modern era. Biggest true-home edge is in Qualifiers (0.6234). Neutral games
concentrate in Finals & continental play (8747 of 13075).

Descriptive only. No edge/ROI/forecast claim (edge_claimed:false).

Output: out/soccer_home_advantage.json (this committed JSON IS the recorded
artifact -- --check reloads it and does not require data/ locally, i.e. is
clone-safe).

Usage:
  python -m scripts.platformkit.analytics_showcase.soccer_home_advantage
  python -m scripts.platformkit.analytics_showcase.soccer_home_advantage --check
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "soccer_home_advantage.json"
RESULTS_PARQUET = REPO / "data" / "domains" / "soccer_intl" / "results.parquet"

METHOD = (
    "Venue-control decomposition: matches are split on the real `neutral` flag "
    "into true-home (neutral=False) vs neutral-site (neutral=True), then goal "
    "difference and win/draw/away rates are compared within era and tournament "
    "type. The neutral split is the natural control -- not a random assignment."
)
CONFOUNDS = [
    "neutral games are non-random (concentrate in tournament finals -- 8747 of "
    "13075)",
    "crowd is never directly observed (NOT_TESTABLE)",
    "no strength-of-schedule / team-quality adjustment (opponent-raw)",
    "draws included in win-rate base",
]
BANNED_TERMS = ("edge", "roi", "profit", "bankroll", "forecast")


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _venue_stats(gd) -> dict:
    n = len(gd)
    return {
        "n": n,
        "home_win_rate": round(float((gd > 0).mean()), 4),
        "draw_rate": round(float((gd == 0).mean()), 4),
        "away_win_rate": round(float((gd < 0).mean()), 4),
        "goal_diff": round(float(gd.mean()), 4),
    }


def _bucket(tournament: str) -> str:
    t = str(tournament).lower()
    if t == "friendly":
        return "Friendlies"
    if "qualification" in t or "qualifier" in t:
        return "Qualifiers"
    return "Finals & continental"


def build() -> dict:
    if not RESULTS_PARQUET.exists():
        return {"status": "local_corpus_absent", "sport": "soccer_intl", "needed_artifacts": [_rel(RESULTS_PARQUET)]}

    import pandas as pd

    df = pd.read_parquet(RESULTS_PARQUET)
    played = df.dropna(subset=["home_score", "away_score"]).copy()
    played["gd"] = played["home_score"] - played["away_score"]

    true_home = _venue_stats(played.loc[~played["neutral"], "gd"])
    neutral = _venue_stats(played.loc[played["neutral"], "gd"])
    hfa_goal_diff = round(true_home["goal_diff"] - neutral["goal_diff"], 4)
    hfa_home_win_rate = round(true_home["home_win_rate"] - neutral["home_win_rate"], 4)

    played["year"] = played["date"].dt.year
    by_era = []
    for era, cond in (("pre-2000", played["year"] < 2000), ("2000+", played["year"] >= 2000)):
        sub = played[cond]
        th_gd = round(float(sub.loc[~sub["neutral"], "gd"].mean()), 4)
        ne_gd = round(float(sub.loc[sub["neutral"], "gd"].mean()), 4)
        by_era.append({
            "era": era,
            "true_home_goal_diff": th_gd,
            "neutral_goal_diff": ne_gd,
            "effect_goal_diff": round(th_gd - ne_gd, 4),
            "n_true_home": int((~sub["neutral"]).sum()),
            "n_neutral": int(sub["neutral"].sum()),
        })

    played["bucket"] = played["tournament"].apply(_bucket)
    by_tournament_type = []
    for bucket in ("Friendlies", "Qualifiers", "Finals & continental"):
        sub = played[played["bucket"] == bucket]
        th = sub.loc[~sub["neutral"], "gd"]
        ne = sub.loc[sub["neutral"], "gd"]
        th_gd = round(float(th.mean()), 4)
        ne_gd = round(float(ne.mean()), 4)
        by_tournament_type.append({
            "bucket": bucket,
            "n": int(len(sub)),
            "true_home_n": int(len(th)),
            "true_home_goal_diff": th_gd,
            "neutral_n": int(len(ne)),
            "neutral_goal_diff": ne_gd,
            "effect_goal_diff": round(th_gd - ne_gd, 4),
        })

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Home advantage is real; the true-home/neutral gap grew not because "
            "true-home rose (it is flat) but because neutral-venue advantage "
            "collapsed over time."
        ),
        "method": METHOD,
        "source_parquet": _rel(RESULTS_PARQUET),
        "observation_window": {
            "first_date": played["date"].min().strftime("%Y-%m-%d"),
            "last_date": played["date"].max().strftime("%Y-%m-%d"),
            "n_matches_played": int(len(played)),
            "note": "the full committed international-results corpus (~150 years, 1872-2026), not a rolling cache",
        },
        "venue": {"true_home": true_home, "neutral": neutral},
        "hfa_effect": {"goal_diff": hfa_goal_diff, "home_win_rate": hfa_home_win_rate},
        "by_era": by_era,
        "by_tournament_type": by_tournament_type,
        "travel_leg": {
            "testable": False,
            "note": (
                "results.parquet carries city/country strings but no coordinates; "
                "a travel-distance residual leg is NOT_TESTABLE from committed "
                "data and is deliberately not estimated."
            ),
        },
        "confounds": CONFOUNDS,
        "receipt": {
            "committed_ledger": "scripts/platformkit/analytics_showcase/out/mechanism_ledger_export.json",
            "mechanisms": [
                "home_advantage_neutral_vs_true_goal_diff",
                "home_advantage_neutral_vs_true_win_rate",
                "home_advantage_neutral_split_half_by_era",
            ],
            "verdict": "CONFIRMED_LOCAL",
        },
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


def _no_nan_inf(obj) -> bool:
    if isinstance(obj, float):
        return not (math.isnan(obj) or math.isinf(obj))
    if isinstance(obj, dict):
        return all(_no_nan_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan_inf(v) for v in obj)
    return True


def _string_values(obj) -> list:
    """Collect string VALUES only (never dict keys) for the banned-term scan --
    field names like edge_claimed are not metric-value prose."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out.extend(_string_values(v))
        return out
    if isinstance(obj, list):
        out = []
        for v in obj:
            out.extend(_string_values(v))
        return out
    return []


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False
        assert result["observation_window"]["n_matches_played"] == 49425

        th, ne = result["venue"]["true_home"], result["venue"]["neutral"]
        assert th["n"] == 36350 and ne["n"] == 13075
        assert abs(th["goal_diff"] - 0.6744) < 1e-9
        assert abs(ne["goal_diff"] - 0.3007) < 1e-9
        assert abs(th["home_win_rate"] - 0.5074) < 1e-9
        assert abs(ne["home_win_rate"] - 0.4418) < 1e-9
        assert abs(result["hfa_effect"]["goal_diff"] - 0.3737) < 1e-9
        assert abs(result["hfa_effect"]["home_win_rate"] - 0.0656) < 1e-9

        eras = {e["era"]: e for e in result["by_era"]}
        assert abs(eras["pre-2000"]["true_home_goal_diff"] - 0.6743) < 1e-9
        assert abs(eras["pre-2000"]["neutral_goal_diff"] - 0.4556) < 1e-9
        assert abs(eras["pre-2000"]["effect_goal_diff"] - 0.2187) < 1e-9
        assert abs(eras["2000+"]["true_home_goal_diff"] - 0.6745) < 1e-9
        assert abs(eras["2000+"]["neutral_goal_diff"] - 0.1760) < 1e-9
        assert abs(eras["2000+"]["effect_goal_diff"] - 0.4985) < 1e-9

        assert len(result["by_tournament_type"]) == 3
        buckets = {b["bucket"]: b for b in result["by_tournament_type"]}
        assert buckets["Qualifiers"]["effect_goal_diff"] == max(
            b["effect_goal_diff"] for b in result["by_tournament_type"]
        )
        assert buckets["Finals & continental"]["neutral_n"] == 8747

        assert _no_nan_inf(result), "NaN/inf found in emitted numbers"

        blob = " ".join(_string_values(result)).lower()
        for term in BANNED_TERMS:
            assert not re.search(rf"\b{term}\b", blob), f"banned term '{term}' found in artifact prose"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        if res["status"] == "ok":
            print(json.dumps({
                "status": "ok",
                "n_matches_played": res["observation_window"]["n_matches_played"],
                "venue": res["venue"],
                "hfa_effect": res["hfa_effect"],
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
