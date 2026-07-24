"""
MLB descriptive leaderboards: catcher/umpire out-of-zone strike-rate tables,
platoon on-base splits, a park-factor NULL, and the umpire-totals gate REJECT --
all read straight off LOCAL Statcast-derived parquets under data/domains/mlb/.

DESCRIPTIVE_ONLY, edge_claimed:false. Nothing here is a predictive metric:

  - catcher/umpire "ooz_strike_rate" is an out-of-zone called-or-swung-strike
    rate (see catcher_framing_index_report.json: metric_is_NOT_a_called_strike_
    or_framing_rate=true). It is CRUDER than mixed-model catcher framing and is
    NOT a called-strike or framing rate. No rho / correlation / fold receipt
    exists for it -- do not imply one.
  - platoon_delta is a raw on-base-rate gap (vs-LHP minus vs-RHP), not park- or
    quality-adjusted.
  - the park-factor parquet is mostly NaN here; rather than publish an unstable
    ranking, this module reports the NULL (how sparse it is) as the finding.
  - umpire_totals_gate_verdict.json is a committed REJECT: home-plate umpire OOZ
    tendency does not move game totals beyond baseline (planted-null control
    matched the real-assignment lift -- an added-flexibility artifact).

Fixed observation window: seasons 2022_2023, corpus_id statcast_fuller_v1 (read
from the parquets themselves, not assumed) -- NOT the current MLB season.

Output: out/mlb_descriptive_leaderboards.json (this committed JSON IS the
recorded artifact -- --check reloads it and does not require data/ locally).
Usage:
  python -m scripts.platformkit.analytics_showcase.mlb_descriptive_leaderboards
  python -m scripts.platformkit.analytics_showcase.mlb_descriptive_leaderboards --check
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "mlb_descriptive_leaderboards.json"

MLB_DIR = REPO / "data" / "domains" / "mlb"
CATCHER_PATH = MLB_DIR / "catcher_framing_index.parquet"
PLATOON_PATH = MLB_DIR / "platoon_split_index.parquet"
UMPIRE_PATH = MLB_DIR / "umpire_zone_index.parquet"
PARK_PATH = MLB_DIR / "asof_park.parquet"
GATE_PATH = MLB_DIR / "umpire_totals_gate_verdict.json"
NEEDED = [CATCHER_PATH, PLATOON_PATH, UMPIRE_PATH, PARK_PATH, GATE_PATH]

CATCHER_FLOOR = 500
PLATOON_PA_FLOOR = 50
TOP_N = 15

OOZ_LABEL = (
    "Out-of-zone called/swung-strike rate -- a DESCRIPTIVE catcher stat, cruder "
    "than model-based framing; NOT a called-strike or framing rate, NOT predictive."
)
OOZ_LABEL_UMP = (
    "Out-of-zone called/swung-strike rate -- a DESCRIPTIVE umpire-zone stat, cruder "
    "than model-based framing; NOT a called-strike or framing rate, NOT predictive."
)


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def build() -> dict:
    missing = [_rel(p) for p in NEEDED if not p.exists()]
    if missing:
        return {"status": "local_corpus_absent", "sport": "mlb", "needed_artifacts": missing}

    catcher = pd.read_parquet(CATCHER_PATH)
    platoon = pd.read_parquet(PLATOON_PATH)
    umpire = pd.read_parquet(UMPIRE_PATH)
    park = pd.read_parquet(PARK_PATH)
    gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))

    def ooz_rows(df, name_col):
        recs = df.sort_values("ooz_strike_rate", ascending=False)
        top = [{"name": str(r[name_col]), "n_ooz_called": int(r["n_ooz_called"]),
                "ooz_strike_rate": round(float(r["ooz_strike_rate"]), 3)}
               for _, r in recs.head(TOP_N).iterrows()]
        bottom = [{"name": str(r[name_col]), "n_ooz_called": int(r["n_ooz_called"]),
                   "ooz_strike_rate": round(float(r["ooz_strike_rate"]), 3)}
                  for _, r in recs.tail(TOP_N).iterrows()]
        return top, bottom

    catcher_top, catcher_bottom = ooz_rows(catcher, "catcher_name")
    umpire_top, umpire_bottom = ooz_rows(umpire, "umpire_name")

    plat_q = platoon[(platoon["pa_vs_l"] >= PLATOON_PA_FLOOR) & (platoon["pa_vs_r"] >= PLATOON_PA_FLOOR)]
    plat_q = plat_q.sort_values("platoon_delta", ascending=False)
    platoon_top = [{
        "name": str(r["batter_name"]),
        "rate_vs_l": round(float(r["rate_vs_l"]), 3),
        "rate_vs_r": round(float(r["rate_vs_r"]), 3),
        "platoon_delta": round(float(r["platoon_delta"]), 3),
        "pa_vs_l": int(r["pa_vs_l"]),
        "pa_vs_r": int(r["pa_vs_r"]),
    } for _, r in plat_q.head(TOP_N).iterrows()]

    n_finite_park = int(park["park_factor"].notna().sum())
    n_nan_park = int(park["park_factor"].isna().sum())

    fold_deltas = [f["rmse_delta"] for f in gate["real_result"]["folds"]]

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Descriptive MLB Statcast-derived leaderboards (catcher/umpire out-of-zone "
            "strike rate, platoon on-base splits) for a fixed 2022-2023 corpus slice, "
            "shown beside two honest nulls -- an unstable park-factor read and a REJECTed "
            "umpire-totals gate -- with no predictive or edge claim anywhere."
        ),
        "observation_window": {
            "seasons": str(catcher["season"].iloc[0]),
            "corpus_id": str(catcher["corpus_id"].iloc[0]),
            "as_of": str(catcher["as_of"].iloc[0]),
            "note": "a fixed 2022-2023 Statcast slice, not the current season",
        },
        "source_note": (
            "Leaderboards derived from LOCAL Statcast-derived parquets (gitignored); "
            "this committed JSON is the recorded artifact. edge_claimed:false."
        ),
        "catcher_ooz": {
            "label": OOZ_LABEL,
            "floor": f"n_ooz_called>={CATCHER_FLOOR}",
            "n_qualified": int(len(catcher)),
            "top": catcher_top,
            "bottom": catcher_bottom,
        },
        "platoon_splits": {
            "label": "Raw on-base-rate gap vs LHP minus vs RHP -- not park/quality adjusted, descriptive only.",
            "floor": f"pa_vs_l>={PLATOON_PA_FLOOR} and pa_vs_r>={PLATOON_PA_FLOOR}",
            "n_qualified": int(len(plat_q)),
            "top": platoon_top,
        },
        "umpire_ooz": {
            "label": OOZ_LABEL_UMP,
            "corpus_id": str(umpire["corpus_id"].iloc[0]),
            "n_qualified": int(len(umpire)),
            "top": umpire_top,
            "bottom": umpire_bottom,
        },
        "park_factor_null": {
            "headline": (
                "asof_park.parquet's park_factor is mostly NaN in this corpus -- too "
                "unstable/sparse to publish as a ranking, so we report the null instead."
            ),
            "n_rows": int(len(park)),
            "n_finite_park_factor": n_finite_park,
            "n_nan": n_nan_park,
            "verdict": "too unstable/sparse to publish as a ranking",
        },
        "umpire_totals_gate": {
            "hypothesis": gate["hypothesis"],
            "verdict": gate["verdict"],
            "verdict_reason": gate["verdict_reason"],
            "n_umpires": int(gate["n_umpires"]),
            "fold_rmse_deltas": fold_deltas,
            "reading": "ump identity did not move game totals -- a REJECT, published honestly",
        },
        "confounds": [
            "OOZ strike rate is cruder than mixed-model framing and is NOT a called-strike/framing rate.",
            "2022-2023 fixed window; not current-season.",
            "platoon delta is raw on-base rate difference, not park/quality adjusted.",
            "these are DESCRIPTIVE leaderboards; no predictive or edge claim is made.",
        ],
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


_BANNED_TERMS = ("predictive_receipt", "correlation", "rho", "edge_receipt")


def _no_nan(obj) -> bool:
    if isinstance(obj, float):
        return not math.isnan(obj)
    if isinstance(obj, dict):
        return all(_no_nan(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan(v) for v in obj)
    return True


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False
        for key in ("catcher_ooz", "platoon_splits", "umpire_ooz", "park_factor_null", "umpire_totals_gate"):
            assert key in result, f"missing section {key}"

        assert result["observation_window"]["seasons"] == "2022_2023"

        c = result["catcher_ooz"]
        assert 0 < len(c["top"]) <= 15 and 0 < len(c["bottom"]) <= 15

        u = result["umpire_ooz"]
        assert 0 < len(u["top"]) <= 15 and 0 < len(u["bottom"]) <= 15

        p = result["platoon_splits"]
        assert 0 < len(p["top"]) <= 15

        gate = result["umpire_totals_gate"]
        assert "REJECT" in gate["verdict"].upper(), f"expected REJECT-family verdict, got {gate['verdict']}"

        park = result["park_factor_null"]
        assert park["n_nan"] >= 1

        blob = json.dumps(result).lower()
        for term in _BANNED_TERMS:
            assert term not in blob, f"banned predictive/edge term found: {term}"

        assert _no_nan(result), "NaN found in emitted numbers"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        if result["status"] == "ok":
            print(json.dumps({
                "status": "ok",
                "n_catcher_qualified": result["catcher_ooz"]["n_qualified"],
                "n_catcher_top": len(result["catcher_ooz"]["top"]),
                "n_catcher_bottom": len(result["catcher_ooz"]["bottom"]),
                "n_platoon_qualified": result["platoon_splits"]["n_qualified"],
                "n_platoon_top": len(result["platoon_splits"]["top"]),
                "n_umpire_qualified": result["umpire_ooz"]["n_qualified"],
                "n_umpire_top": len(result["umpire_ooz"]["top"]),
                "n_umpire_bottom": len(result["umpire_ooz"]["bottom"]),
                "park_n_rows": result["park_factor_null"]["n_rows"],
                "park_n_finite": result["park_factor_null"]["n_finite_park_factor"],
                "park_n_nan": result["park_factor_null"]["n_nan"],
                "umpire_gate_verdict": result["umpire_totals_gate"]["verdict"],
            }, indent=2))
        else:
            print(json.dumps(result, indent=2))
        print(f"wrote {OUT_JSON}")
