"""
MLB velo bands (in-season drift): ONE column-selective pass over the local 2025
statcast pull (statcast_fuller__2025.parquet) that measures the LEAGUE
release-speed distribution two ways --

  (a) velo-band shares per pitch type  -- what fraction of each pitch type's
      pitches land in fixed 3-mph bands (a distribution shape, not a ranking);
  (b) monthly median velo per pitch type -- an in-season drift descriptor
      (velocity tends to ramp up from the cold March/April opening toward
      mid-summer, then hold; reported descriptively, not modeled).

DESCRIPTIVE_ONLY: this is a distribution / data-coverage exhibit. It does NOT
model, forecast, price, or claim an edge on anything -- release_speed here is a
raw physical measurement in mph, and the "drift" is a known ramp-up effect
reported as-is. No edge/ROI/$ claim. See docs/JOB_EVIDENCE_PACKET.md.

Floors (declared, applied):
  - band-share table reports only pitch types with >= MIN_PT_PITCHES pitches;
  - a monthly (pitch_type, month) drift cell is reported only with
    >= MIN_CELL_PITCHES pitches;
  - the chart plots the top-6 pitch types by total count.
Thin edge-of-season months (Mar/Oct) typically fall below the cell floor and are
DROPPED, not smoothed or extrapolated. Pitches with no pitch_type / no
release_speed are excluded from both analyses (raw vs analyzed counts are both
reported so the coverage gap is visible).

Output: out/mlb_velo_bands.json + docs/img/mlb_velo_bands.png.
Run:    python -m scripts.platformkit.analytics_showcase.mlb_velo_bands
Check:  python -m scripts.platformkit.analytics_showcase.mlb_velo_bands --check
"""
import calendar
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "mlb_velo_bands.json"
OUT_PNG = REPO / "docs" / "img" / "mlb_velo_bands.png"

STATCAST_PATH = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"

# column-selective read: only the three fields the two distributions need.
NEEDED_COLS = ["pitch_type", "release_speed", "game_date"]

MIN_PT_PITCHES = 500      # band-share table: drop pitch types thinner than this
MIN_CELL_PITCHES = 200    # drift table: drop (pitch_type, month) cells thinner than this
TOP_N_CHART = 6           # chart: top-6 pitch types by total count

# fixed 3-mph bands spanning slow breaking balls (~78) .. FF/SI (~95) .. elite (100+).
# left-closed / right-open (pd.cut right=False); labels count == len(edges) - 1.
BAND_EDGES = [0, 80, 83, 86, 89, 92, 95, 98, 101, 200]
BAND_LABELS = ["<80", "80-83", "83-86", "86-89", "89-92", "92-95", "95-98", "98-101", "101+"]

CAVEAT = (
    "DESCRIPTIVE_ONLY: league release-speed distribution and in-season median-velo "
    "drift for the local 2025 statcast pull. Not a predictive, edge, or ROI claim -- "
    "nothing here is modeled, forecast, or priced. In-season velo ramp-up is a known "
    "physical effect, reported descriptively. See docs/JOB_EVIDENCE_PACKET.md."
)
FLOORS = {
    "band_share_min_pitches_per_type": MIN_PT_PITCHES,
    "drift_min_pitches_per_cell": MIN_CELL_PITCHES,
    "chart_top_n_pitch_types": TOP_N_CHART,
    "note": (
        "pitch types / (type,month) cells below floor are dropped, not smoothed; thin "
        "edge-of-season months (Mar/Oct) typically fall below the cell floor and vanish"
    ),
}


def build_velo_bands() -> dict:
    if not STATCAST_PATH.exists():
        rel = str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")
        return {"status": "local_corpus_absent", "sport": "mlb",
                "needed_artifact": rel, "paths_tried": [rel]}

    df = pd.read_parquet(STATCAST_PATH, columns=NEEDED_COLS)
    n_raw = len(df)
    df = df.dropna(subset=["pitch_type", "release_speed"]).copy()
    n_analyzed = len(df)
    # month robust to str ISO or datetime game_date; coerce bad values to NaT -> dropped in drift.
    df["_month"] = pd.to_datetime(df["game_date"], errors="coerce").dt.month
    df["_band"] = pd.cut(df["release_speed"], bins=BAND_EDGES, labels=BAND_LABELS, right=False)

    # (a) velo-band shares by pitch type (only types clearing the floor)
    band_by_pt = []
    for pt, g in df.groupby("pitch_type"):
        if len(g) < MIN_PT_PITCHES:
            continue
        counts = g["_band"].value_counts()
        shares = {lab: round(100 * int(counts.get(lab, 0)) / len(g), 2) for lab in BAND_LABELS}
        band_by_pt.append({
            "pitch_type": str(pt), "n": int(len(g)),
            "median_velo": round(float(g["release_speed"].median()), 1),
            "band_share_pct": shares,
        })
    band_by_pt.sort(key=lambda r: -r["n"])

    # (b) monthly median-velo drift per pitch type (only cells clearing the cell floor)
    drift = []
    for pt, g in df.groupby("pitch_type"):
        if len(g) < MIN_PT_PITCHES:
            continue
        months = []
        for m, gm in g.dropna(subset=["_month"]).groupby("_month"):
            if len(gm) < MIN_CELL_PITCHES:
                continue
            months.append({
                "month": int(m), "n": int(len(gm)),
                "median_velo": round(float(gm["release_speed"].median()), 1),
                "mean_velo": round(float(gm["release_speed"].mean()), 2),
            })
        months.sort(key=lambda r: r["month"])
        if len(months) < 2:  # need >=2 reported months to describe any drift
            continue
        drift.append({
            "pitch_type": str(pt), "n": int(len(g)), "n_months": len(months),
            "first_month": months[0]["month"], "last_month": months[-1]["month"],
            # descriptive delta of the monthly median (mph), first -> last reported month.
            "median_velo_delta_first_to_last_mph": round(
                months[-1]["median_velo"] - months[0]["median_velo"], 1),
            "months": months,
        })
    drift.sort(key=lambda r: -r["n"])

    return {
        "status": "ok",
        "sport": "mlb",
        "caveat": CAVEAT,
        "floors": FLOORS,
        "source": str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/"),
        "n_pitches_raw": int(n_raw),
        "n_analyzed": int(n_analyzed),
        "band_edges_mph": BAND_EDGES,
        "band_labels": BAND_LABELS,
        "velo_band_shares_by_pitch_type": band_by_pt,
        "monthly_drift_by_pitch_type": drift,
        "chart_pitch_types": [d["pitch_type"] for d in drift[:TOP_N_CHART]],
    }


def render_chart(result: dict, path: Path) -> None:
    drift = result["monthly_drift_by_pitch_type"][:TOP_N_CHART]
    fig, ax = plt.subplots(figsize=(9, 5))
    all_months: set = set()
    for d in drift:
        xs = [m["month"] for m in d["months"]]
        ys = [m["median_velo"] for m in d["months"]]
        all_months.update(xs)
        ax.plot(xs, ys, marker="o", linewidth=1.8, label=f"{d['pitch_type']} (n={d['n']:,})")

    months = sorted(all_months)
    ax.set_xticks(months)
    ax.set_xticklabels([calendar.month_abbr[m] for m in months])
    ax.set_xlabel("month of 2025 MLB season")
    ax.set_ylabel("median release_speed (mph)")
    ax.set_title(
        f"MLB 2025 in-season velo drift: monthly median by pitch type "
        f"(top {len(drift)} by count, n={result['n_analyzed']:,} classified pitches)",
        fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, title="pitch type", loc="best")
    fig.text(
        0.01, 0.01,
        f"source: {result['source']}  |  floor: cell n>={MIN_CELL_PITCHES}  |  "
        f"DESCRIPTIVE_ONLY -- no edge/ROI claim",
        fontsize=6, ha="left", va="bottom", color="#555555")
    fig.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    result = build_velo_bands()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="ascii")
    if result["status"] == "ok":
        render_chart(result, OUT_PNG)
    return result


def _check():
    # Asserts the built OUTPUTS exist and are nonzero (run the module once, no --check, first).
    # ponytail: reads the written artifact rather than re-reading the 693k-row parquet -- the
    # task's contract is "outputs exist nonzero", and check_all.py treats a never-built
    # artifact as a real FAIL, so this is the honest signal.
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["n_analyzed"] > 0, "zero analyzed pitches"
        assert result["n_analyzed"] <= result["n_pitches_raw"], "analyzed exceeds raw"
        bands = result["velo_band_shares_by_pitch_type"]
        drift = result["monthly_drift_by_pitch_type"]
        assert bands, "empty velo-band-share table"
        assert drift, "empty monthly-drift table"
        # band shares are a partition of each pitch type -> must sum to ~100%.
        for r in bands:
            total = sum(r["band_share_pct"].values())
            assert abs(total - 100.0) < 1.0, f"{r['pitch_type']} band shares sum to {total}, not ~100"
        # each drift row has >=2 sorted, floor-clearing monthly cells.
        for d in drift:
            assert d["n_months"] >= 2
            ms = [c["month"] for c in d["months"]]
            assert ms == sorted(ms)
            assert all(c["n"] >= MIN_CELL_PITCHES for c in d["months"])
        assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, f"missing/empty {OUT_PNG}"
    else:
        assert "needed_artifact" in result
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "status": result["status"],
            "n_analyzed": result.get("n_analyzed"),
            "n_pitch_types_banded": len(result.get("velo_band_shares_by_pitch_type", [])),
            "n_pitch_types_drift": len(result.get("monthly_drift_by_pitch_type", [])),
        }, indent=2))
        print(f"wrote {OUT_JSON}")
        if result["status"] == "ok":
            print(f"wrote {OUT_PNG}")
