"""lineup_synergy.py -- descriptive five-man lineup-synergy ledger from the
real NBA stint cache: which units beat the sum of their individual on/off
parts?

data/cache/team_system/lineups/lineup_synergy_2024_25.parquet carries, per
five-man lineup, the observed net rating (net_per48) and an "expected"
net rating built by summing the five members' individual on/off contributions
(expected_net_per48). The headline metric is the residual:

    synergy_residual = net_per48 - expected_net_per48

A positive residual means the lineup OUTPERFORMS the sum of its parts (the
five play better together than their individual on/off numbers predict); a
negative residual means it underperforms. Filtered to qualifies==True (all
five members individually qualified for on/off, min>=100ish on-court
minutes). Player names resolved via on_off_2024_25.parquet's id->name map.

THE STORY: the Grizzlies' Jackson-Morant-Bane-Edey-Wells five topped the
league in 2024-25 at +24.32 net-per-48 above expected. But this is a single
season (only 2024-25 has this stint cache), the minutes floor is low
(~100 on-court minutes for some lineups -- noisy), and the "expected"
baseline itself rests on member on/off splits, which are themselves
roster-confounded. The residual is a descriptive ASSOCIATION, not proof of
causal chemistry. Opponent-raw. Not a forecast.

Descriptive only. No edge/ROI claim (edge_claimed:false).

Output: out/lineup_synergy.json (this committed JSON IS the recorded
artifact -- --check reloads it and does not require data/ locally, i.e. is
clone-safe).

Usage:
  python -m scripts.platformkit.analytics_showcase.lineup_synergy
  python -m scripts.platformkit.analytics_showcase.lineup_synergy --check
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "lineup_synergy.json"
LINEUPS_DIR = REPO / "data" / "cache" / "team_system" / "lineups"
SYNERGY_PARQUET = LINEUPS_DIR / "lineup_synergy_2024_25.parquet"
ONOFF_PARQUET = LINEUPS_DIR / "on_off_2024_25.parquet"

SEASON = "2024-25"
TOP_N = 15
BOTTOM_N = 8
MIN_FLOOR_NOTE = (
    "on-court minutes range 101.6-940.0 across the 102 qualified lineups -- "
    "the low end is a small sample; do not over-read a ~100-minute lineup"
)

METHOD = (
    "For every five-man lineup where all five members individually qualified "
    "for on/off (qualifies==True in the real stint cache), compare the "
    "lineup's observed net rating per 48 to an 'expected' net rating built by "
    "summing the five members' individual on/off contributions, then rank by "
    "the residual."
)
METRIC_DEFINITION = (
    "synergy_residual = net_per48 - expected_net_per48; positive means the "
    "five-man unit outperforms the sum of its individual parts, negative "
    "means it underperforms."
)
CONFOUNDS = [
    "single season: only 2024-25 has this stint cache -- no cross-season "
    "replication is possible yet",
    "small minutes: the floor is roughly 100 on-court minutes for some "
    "lineups, which is noisy and wide-uncertainty -- do not over-read a "
    "~100-minute lineup",
    "the 'expected' baseline itself rests on each member's on/off split, "
    "which is roster-confounded (teammates and role are bundled into it)",
    "descriptive association, not proof of causal chemistry",
    "opponent-raw: no opponent-strength adjustment",
]
BANNED_TERMS = ("edge", "roi", "profit", "bankroll", "forecast")


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _row_entry(rank: int, row, names: list) -> dict:
    return {
        "rank": rank,
        "members": names,
        "team_id": int(row.team_id),
        "n_games": int(row.n_games),
        "min": round(float(row.min), 1),
        "net_per48": round(float(row.net_per48), 2),
        "expected_net_per48": round(float(row.expected_net_per48), 2),
        "synergy_residual": round(float(row.synergy_residual), 2),
    }


def build() -> dict:
    if not SYNERGY_PARQUET.exists() or not ONOFF_PARQUET.exists():
        needed = [p for p in (SYNERGY_PARQUET, ONOFF_PARQUET) if not p.exists()]
        return {
            "status": "local_corpus_absent",
            "needed_artifacts": [_rel(p) for p in needed],
        }

    import pandas as pd

    df = pd.read_parquet(SYNERGY_PARQUET)
    q = df[df["qualifies"] == True].copy()  # noqa: E712

    names_df = pd.read_parquet(ONOFF_PARQUET)[["player_id", "player_name"]].drop_duplicates()
    name_map = {str(pid): name for pid, name in zip(names_df["player_id"], names_df["player_name"])}

    def resolve(lineup_key: str) -> list:
        return [name_map[pid.strip()] for pid in lineup_key.split(",")]

    q_top = q.sort_values("synergy_residual", ascending=False).reset_index(drop=True)
    top = [
        _row_entry(rank, row, resolve(row.lineup_key))
        for rank, row in enumerate(q_top.head(TOP_N).itertuples(index=False), start=1)
    ]

    q_bot = q.sort_values("synergy_residual", ascending=True).reset_index(drop=True)
    bottom = [
        _row_entry(rank, row, resolve(row.lineup_key))
        for rank, row in enumerate(q_bot.head(BOTTOM_N).itertuples(index=False), start=1)
    ]

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Greater than the sum of their parts: which five-man lineups beat "
            "what their individual on/off numbers predict -- the Grizzlies' "
            "Jackson-Morant-Bane-Edey-Wells five topped 2024-25 at +24.32 net "
            "per 48 above expected."
        ),
        "method": METHOD,
        "metric_definition": METRIC_DEFINITION,
        "season": SEASON,
        "n_qualified": int(len(q)),
        "min_floor_note": MIN_FLOOR_NOTE,
        "top": top,
        "bottom": bottom,
        "observation_window": {
            "season": SEASON,
            "note": (
                "single season from the local stint cache; ~100+ on-court-"
                "minute floor, noisy"
            ),
        },
        "confounds": CONFOUNDS,
        "receipt": {
            "source_parquets": [_rel(SYNERGY_PARQUET), _rel(ONOFF_PARQUET)],
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
        assert result["season"] == "2024-25"
        assert result["n_qualified"] == 102, result["n_qualified"]

        top = result["top"]
        assert len(top) <= 15
        assert top[0]["rank"] == 1
        assert abs(top[0]["synergy_residual"] - 24.32) < 1e-9
        assert set(top[0]["members"]) == {
            "Jaren Jackson Jr.", "Ja Morant", "Desmond Bane", "Zach Edey", "Jaylen Wells",
        }
        residuals = [r["synergy_residual"] for r in top]
        assert residuals == sorted(residuals, reverse=True), "top not sorted descending by residual"
        for row in top:
            assert len(row["members"]) == 5

        bottom = result["bottom"]
        assert bottom[0]["rank"] == 1
        assert abs(bottom[0]["synergy_residual"] - (-26.27)) < 1e-9
        for row in bottom:
            assert len(row["members"]) == 5

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
                "n_qualified": res["n_qualified"],
                "top1": res["top"][0],
                "bottom1": res["bottom"][0],
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
