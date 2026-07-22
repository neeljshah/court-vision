"""
Statcast showcase: ONE column-selective pass over the local 2025 statcast pull
(693k pitches) -- pitch-type distribution, velo percentiles by pitch type, and
coverage of the columns the framing PREDICTIVE_VERIFIED claim's borderline-
called-strike metric is built from. Descriptive/data-coverage only -- does NOT
recompute the framing predictive-validity result, just cites the existing
receipt as context.

Output: out/statcast_showcase.json + docs/img/statcast_showcase.png.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "statcast_showcase.json"
OUT_PNG = REPO / "docs" / "img" / "statcast_showcase.png"

STATCAST_PATH = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"
FRAMING_RECEIPT_PATH = (
    REPO / "data" / "cache" / "predictive_validity"
    / "mlb_framing__borderline_called_strike_rate_asof.json"
)

# columns the framing claim's borderline-called-strike classification is built from
FRAMING_INGREDIENT_COLS = ["plate_x", "plate_z", "sz_top", "sz_bot", "zone", "type", "fielder_2", "balls", "strikes"]
NEEDED_COLS = ["pitch_type", "release_speed"] + FRAMING_INGREDIENT_COLS

CAVEAT = (
    "Descriptive data-coverage showcase only -- pitch-type mix, velo percentiles, "
    "and column completeness for the local 2025 statcast pull. Does NOT recompute "
    "any predictive-validity result. No edge/ROI/$ claim."
)


def _load_framing_receipt() -> dict:
    if not FRAMING_RECEIPT_PATH.exists():
        return {
            "status": "local_corpus_absent",
            "needed_artifact": str(FRAMING_RECEIPT_PATH.relative_to(REPO)).replace("\\", "/"),
        }
    raw = json.loads(FRAMING_RECEIPT_PATH.read_text(encoding="ascii", errors="ignore"))
    return {
        "status": "ok",
        "source": str(FRAMING_RECEIPT_PATH.relative_to(REPO)).replace("\\", "/"),
        "verdict": raw["verdict"],
        "mean_rho_metric": raw["mean_rho_metric"],
        "mean_rho_baseline": raw["mean_rho_baseline"],
        "n_folds": raw["n_folds"],
        "sign_holds_folds": raw["sign_holds_folds"],
        "caveat": raw["caveat"],
        "honest_note": raw["honest_note"],
        "cited_as": "context only -- this showcase does not recompute the rho above",
    }


def build_showcase() -> dict:
    if not STATCAST_PATH.exists():
        return {
            "status": "local_corpus_absent",
            "sport": "mlb",
            "needed_artifact": str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/"),
            "paths_tried": [str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")],
        }

    df = pd.read_parquet(STATCAST_PATH, columns=NEEDED_COLS)
    n = len(df)

    pitch_counts = df["pitch_type"].value_counts(dropna=False)
    pitch_type_dist = [
        {"pitch_type": (pt if pd.notna(pt) else "UNK"), "n": int(c), "pct": round(100 * c / n, 2)}
        for pt, c in pitch_counts.items()
    ]

    velo = df.dropna(subset=["release_speed", "pitch_type"])
    velo_percentiles = []
    for pt, g in velo.groupby("pitch_type"):
        if len(g) < 20:
            continue
        q = g["release_speed"].quantile([0.10, 0.50, 0.90])
        velo_percentiles.append({
            "pitch_type": pt, "n": int(len(g)),
            "p10": round(float(q[0.10]), 1), "p50": round(float(q[0.50]), 1), "p90": round(float(q[0.90]), 1),
        })
    velo_percentiles.sort(key=lambda r: -r["n"])

    framing_coverage = [
        {"column": c, "non_null_pct": round(100 * df[c].notna().mean(), 2)}
        for c in FRAMING_INGREDIENT_COLS
    ]

    return {
        "status": "ok",
        "sport": "mlb",
        "caveat": CAVEAT,
        "source": str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/"),
        "n_pitches": int(n),
        "pitch_type_distribution": pitch_type_dist,
        "velo_percentiles_by_pitch_type": velo_percentiles,
        "framing_ingredient_coverage": framing_coverage,
        "framing_claim_context": _load_framing_receipt(),
    }


def render_chart(showcase: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    dist = sorted(showcase["pitch_type_distribution"], key=lambda r: -r["n"])[:10]
    axes[0].barh([r["pitch_type"] for r in dist][::-1], [r["pct"] for r in dist][::-1], color="#2a6fbf")
    axes[0].set_xlabel("% of pitches")
    axes[0].set_title(f"pitch-type mix (n={showcase['n_pitches']:,})", fontsize=9)

    velo = showcase["velo_percentiles_by_pitch_type"][:8]
    y = list(range(len(velo)))[::-1]
    axes[1].hlines(y, [v["p10"] for v in velo], [v["p90"] for v in velo], color="#999")
    axes[1].scatter([v["p50"] for v in velo], y, color="#c0392b", zorder=3, label="p50")
    axes[1].set_yticks(y)
    axes[1].set_yticklabels([v["pitch_type"] for v in velo])
    axes[1].set_xlabel("release_speed mph (p10-p90, dot=p50)")
    axes[1].set_title("velo range by pitch type", fontsize=9)
    axes[1].legend(fontsize=7)

    fig.suptitle("statcast 2025 local pull: data-coverage showcase (descriptive only)", fontsize=9)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    showcase = build_showcase()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(showcase, indent=2))
    if showcase["status"] == "ok":
        render_chart(showcase, OUT_PNG)
    return showcase


def _check():
    # ponytail: minimal smoke check, not a fixture suite
    showcase = build_showcase()
    assert showcase["status"] in ("ok", "local_corpus_absent")
    if showcase["status"] == "ok":
        assert showcase["n_pitches"] > 0
        assert sum(r["n"] for r in showcase["pitch_type_distribution"]) == showcase["n_pitches"]
        assert len(showcase["framing_ingredient_coverage"]) == len(FRAMING_INGREDIENT_COLS)
    else:
        assert "needed_artifact" in showcase
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "status": result["status"],
            "n_pitches": result.get("n_pitches"),
        }, indent=2))
        print(f"wrote {OUT_JSON}")
        if result["status"] == "ok":
            print(f"wrote {OUT_PNG}")
