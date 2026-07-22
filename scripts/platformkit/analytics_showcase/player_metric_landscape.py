"""
Player metric landscape: what industry advanced-metric families our box-score
data can honestly approximate vs cannot.

Truth source: docs/JOB_EVIDENCE_PACKET.md. Never claim RAPM-family metrics
(EPM/DARKO/LEBRON/BPM/RAPTOR) as reproduced -- we have no RAPM target, only
unadjusted on-off. All support here is coverage of INPUT COLUMNS only, not a
claim that any branded metric is reproduced.

Input: data/domains/basketball_nba/player_boxscores.parquet (columns-only read)
Output: out/player_metric_landscape.json + docs/img/player_metric_landscape.png
"""
import json
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
OUT_JSON = HERE / "out" / "player_metric_landscape.json"
OUT_PNG = Path(__file__).resolve().parents[3] / "docs" / "img" / "player_metric_landscape.png"
PARQUET = Path(__file__).resolve().parents[3] / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"

BOX_COLS = [
    "min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov",
    "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus",
]

# metric_family: (verdict, why) -- verdict in {supported, partial, not_supported}
# supported  = the raw INPUT COLUMNS this family needs are fully present (>=99% coverage)
# partial    = some inputs present but a required ingredient is missing/subset-only
# not_supported = required inputs absent from this table entirely
METRIC_FAMILIES = {
    "box_only_value_index (APPROX, not BPM/EPM)": (
        "box_cols", "supported",
        "Full box (min/pts/reb/ast/stl/blk/tov/fg/ft/pf/plus_minus) present, "
        "0% missing. Transparent linear weights only -- no RAPM target to fit against.",
    ),
    "on_off_differential (unadjusted precursor to RAPM)": (
        "plus_minus,min", "supported",
        "plus_minus + min present per player-game; already built as "
        "atlas_player_usage_role.on_off_net_diff. Labeled unadjusted/biased, not RAPM.",
    ),
    "box_rate_now_cast (per-36, DARKO-lite BOX ONLY)": (
        "box_cols,min", "supported",
        "Per-36 rate stats computable directly from min + counting stats. "
        "NOT a claim of DPM/DARKO -- box rates only.",
    ),
    "playmaking_creation_profile (APPROX)": (
        "ast,tov,fga", "partial",
        "ast/tov/fga present but no potential-assists, passes-made, or "
        "touches -- creation volume only, not quality.",
    ),
    "shot_selection_descriptor (zone-baseline eFG)": (
        "fga,fg3a,fgm,fg3m", "partial",
        "Makes/attempts by 2/3 present so rim-vs-3 rate and eFG% are computable, "
        "but no shot-location/zone/distance column -- no true zone baseline.",
    ),
    "gravity_proxy (CV subset only)": (
        "none in this table", "partial",
        "Needs broadcast-CV defender-distance tracking; this parquet is box-score "
        "only. CV coverage is a separate 241-game/17,254-row/252-player subset -- "
        "flag cv_coverage, do not extrapolate league-wide.",
    ),
    "lineup_synergy (descriptive, unadjusted)": (
        "none", "not_supported",
        "No on-court lineup / stint identifier column in this table.",
    ),
    "aging_curve": (
        "none", "not_supported",
        "No birthdate/age column; only 3 season snapshots (2023-24..2025-26) -- "
        "too thin even if age were derivable.",
    ),
    "RAPM/xRAPM/EPM/DARKO-DPM/LEBRON/BPM/RAPTOR/qSQ/qSI/qSP/EPV/official_Gravity": (
        "none", "not_supported",
        "Do-not-fake list: all require a league-wide RAPM target or continuous "
        "tracking data we do not have. Never reproduce or label as these metrics.",
    ),
}


def coverage_stats(df: pd.DataFrame) -> dict:
    missing_pct = (df[BOX_COLS].isna().mean() * 100).round(3).to_dict()
    return {
        "rows": int(len(df)),
        "unique_players": int(df["player_id"].nunique()),
        "unique_games": int(df["game_id"].nunique()),
        "seasons": sorted(df["season"].unique().tolist()),
        "box_col_missing_pct": missing_pct,
    }


def build_landscape(df: pd.DataFrame) -> dict:
    return {
        "source": "docs/JOB_EVIDENCE_PACKET.md",
        "note": "Support = raw input-column coverage only, never a claim that a branded metric is reproduced.",
        "coverage": coverage_stats(df),
        "metric_families": {
            name: {"inputs_needed": inputs, "verdict": verdict, "why": why}
            for name, (inputs, verdict, why) in METRIC_FAMILIES.items()
        },
    }


def render_chart(landscape: dict, path: Path) -> None:
    names = list(landscape["metric_families"].keys())
    verdicts = [landscape["metric_families"][n]["verdict"] for n in names]
    color_map = {"supported": "#2a9d5c", "partial": "#d9a021", "not_supported": "#c0392b"}
    colors = [color_map[v] for v in verdicts]

    fig, ax = plt.subplots(figsize=(10, 0.5 * len(names) + 1.5))
    y = range(len(names))
    ax.barh(y, [1] * len(names), color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xticks([])
    ax.invert_yaxis()
    for i, v in enumerate(verdicts):
        ax.text(0.5, i, v.upper(), ha="center", va="center", fontsize=8, color="white", weight="bold")
    ax.set_title("Player metric landscape: honest input-coverage verdict per family", fontsize=10)
    legend_handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in color_map.values()]
    ax.legend(legend_handles, color_map.keys(), loc="lower right", fontsize=7)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    df = pd.read_parquet(PARQUET, columns=["game_id", "season", "player_id", *BOX_COLS])
    landscape = build_landscape(df)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(landscape, indent=2))
    render_chart(landscape, OUT_PNG)
    return landscape


def _check():
    # ponytail: minimal smoke check, not a full test suite
    fake = pd.DataFrame({
        "game_id": [1, 1], "season": ["2023-24", "2023-24"], "player_id": [1, 2],
        **{c: [1, 2] for c in BOX_COLS},
    })
    lm = build_landscape(fake)
    assert lm["coverage"]["rows"] == 2
    assert lm["metric_families"]["box_only_value_index (APPROX, not BPM/EPM)"]["verdict"] == "supported"
    assert lm["metric_families"]["lineup_synergy (descriptive, unadjusted)"]["verdict"] == "not_supported"
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps(result["coverage"], indent=2))
        print(f"wrote {OUT_JSON}")
        print(f"wrote {OUT_PNG}")
