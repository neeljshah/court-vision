"""rim_deterrence.py -- descriptive rim-protection leaderboard from real NBA
on/off zone splits.

data/cache/team_system/lineups/zone_onoff_<season>.parquet carries, per
player, the opponent's shot-zone mix and hit rate WITH the player on court vs
off court. The headline metric here is the frequency delta:

    rim_share_allowed_on - rim_share_allowed_off

the share of the opponent's field-goal attempts that come at the rim when the
player is on court, minus that same share when the player is off. A NEGATIVE
delta means the opponent takes FEWER rim shots with the player on -- rim
deterrence. Floor: min_on >= 500 (drop small-sample noise). Ranked ascending
(most negative = best deterrent = rank 1). A secondary rim_efg delta (does
the rim shot also go in less often) is reported alongside the headline number.

THE STORY: the list is face-valid -- Wembanyama, Gobert, Jaren Jackson Jr.
top it, matching the eye test. But on/off bundles the player's teammates and
scheme into the delta: this is descriptive on-court ASSOCIATION, not isolated
individual causation. Opponent-raw, no shot-quality model.

Descriptive only. No edge/ROI claim (edge_claimed:false).

Output: out/rim_deterrence.json (this committed JSON IS the recorded
artifact -- --check reloads it and does not require data/ locally, i.e. is
clone-safe).

Usage:
  python -m scripts.platformkit.analytics_showcase.rim_deterrence
  python -m scripts.platformkit.analytics_showcase.rim_deterrence --check
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "rim_deterrence.json"
LINEUPS_DIR = REPO / "data" / "cache" / "team_system" / "lineups"

MIN_ON_FLOOR = 500
TOP_N = 15
SEASONS = [("2025_26", "2025-26"), ("2024_25", "2024-25")]

METHOD = (
    "On/off split from the real NBA zone shot-mix cache: for each player, "
    "compare the opponent's share of field-goal attempts taken at the rim "
    "while the player is on court vs off court, floored at 500 on-court "
    "minutes, ranked ascending by the on-minus-off delta."
)
METRIC_DEFINITION = (
    "rim frequency deterrence delta = rim_share_allowed_on - "
    "rim_share_allowed_off; negative means the opponent attacks the rim "
    "less often with the player on the floor."
)
CONFOUNDS = [
    "roster confound: teammates and defensive scheme are bundled into the "
    "on-court delta -- this is descriptive on-court association, not "
    "isolated individual causation",
    "opponent-raw: no shot-quality or opponent-strength model",
    "min_on >= 500 floor applied -- on/off is noisy for small on-court "
    "samples, so bench players below the floor are excluded",
]
BANNED_TERMS = ("edge", "roi", "profit", "bankroll", "forecast")


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _season_leaders(parquet_path: Path) -> dict:
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    q = df[df["min_on"] >= MIN_ON_FLOOR].copy()
    q["delta"] = q["rim_share_allowed_on"] - q["rim_share_allowed_off"]
    q = q.sort_values("delta", ascending=True).reset_index(drop=True)

    leaders = []
    for rank, row in enumerate(q.head(TOP_N).itertuples(index=False), start=1):
        entry = {
            "rank": rank,
            "player_name": row.player_name,
            "min_on": round(float(row.min_on), 1),
            "rim_share_allowed_on": round(float(row.rim_share_allowed_on), 4),
            "rim_share_allowed_off": round(float(row.rim_share_allowed_off), 4),
            "delta": round(float(row.delta), 4),
        }
        efg_on, efg_off = row.rim_efg_allowed_on, row.rim_efg_allowed_off
        if math.isfinite(efg_on) and math.isfinite(efg_off):
            entry["rim_efg_delta"] = round(float(efg_on) - float(efg_off), 4)
        leaders.append(entry)

    return {"n_qualified": int(len(q)), "leaders": leaders}


def build() -> dict:
    missing = [s for s, _ in SEASONS
               if not (LINEUPS_DIR / f"zone_onoff_{s}.parquet").exists()]
    if missing:
        return {
            "status": "local_corpus_absent",
            "needed_artifacts": [_rel(LINEUPS_DIR / f"zone_onoff_{s}.parquet") for s in missing],
        }

    seasons_out = []
    for season_key, season_label in SEASONS:
        p = LINEUPS_DIR / f"zone_onoff_{season_key}.parquet"
        block = _season_leaders(p)
        seasons_out.append({
            "season": season_label,
            "n_qualified": block["n_qualified"],
            "min_on_floor": MIN_ON_FLOOR,
            "leaders": block["leaders"],
        })

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Who makes opponents stop attacking the rim: a transparent "
            "on/off rim-deterrence leaderboard -- and the eye test agrees."
        ),
        "method": METHOD,
        "metric_definition": METRIC_DEFINITION,
        "seasons": seasons_out,
        "observation_window": {
            "seasons": [label for _, label in SEASONS],
            "note": "complete NBA seasons from the local stint/zone-onoff cache",
        },
        "confounds": CONFOUNDS,
        "receipt": {
            "source_parquets": [
                _rel(LINEUPS_DIR / f"zone_onoff_{s}.parquet") for s, _ in SEASONS
            ],
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

        seasons = {s["season"]: s for s in result["seasons"]}
        assert set(seasons) == {"2025-26", "2024-25"}

        s2526 = seasons["2025-26"]
        assert s2526["n_qualified"] == 370, s2526["n_qualified"]
        assert len(s2526["leaders"]) <= 15
        assert s2526["leaders"][0]["rank"] == 1
        assert s2526["leaders"][0]["player_name"] == "Victor Wembanyama"
        assert abs(s2526["leaders"][0]["delta"] - (-0.0618)) < 1e-9
        assert s2526["leaders"][0]["min_on"] >= MIN_ON_FLOOR

        s2425 = seasons["2024-25"]
        assert s2425["n_qualified"] == 387, s2425["n_qualified"]
        assert len(s2425["leaders"]) <= 15
        assert s2425["leaders"][0]["rank"] == 1
        assert s2425["leaders"][0]["player_name"] == "Rudy Gobert"
        assert abs(s2425["leaders"][0]["delta"] - (-0.0632)) < 1e-9
        assert s2425["leaders"][0]["min_on"] >= MIN_ON_FLOOR

        for s in result["seasons"]:
            deltas = [row["delta"] for row in s["leaders"]]
            assert deltas == sorted(deltas), f"{s['season']} leaders not ascending by delta"
            assert len(s["leaders"]) <= 15
            for i, row in enumerate(s["leaders"], start=1):
                assert row["rank"] == i

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
                "seasons": [
                    {"season": s["season"], "n_qualified": s["n_qualified"],
                     "rank1": s["leaders"][0]}
                    for s in res["seasons"]
                ],
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
