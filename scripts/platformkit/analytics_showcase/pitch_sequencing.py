"""MLB pitch-sequencing transition matrices: ONE column-selective pass over the
local 2025 statcast pull -- for each count-leverage class, the pitch-to-pitch
transition matrix P(next pitch type | previous pitch type) within a plate
appearance.

SCOPE (DESCRIPTIVE_ONLY): a transition is an adjacent (prev -> next) pitch pair
INSIDE one plate appearance -- grouped by game_pk + at_bat_number + pitcher,
ordered by pitch_number, with a STRICT pitch_number diff == 1 so a pitch missing
from the pull never fabricates a false adjacency and a mid-PA pitching change
never bridges two pitchers. Each transition is assigned to leverage classes by
the COUNT ON THE NEXT (to) PITCH -- the decision state for the pitch being
chosen -- reusing mlb_count_leverage's pitcher-POV partition: behind
(balls>strikes), even, ahead (strikes>balls); plus two OVERLAPPING lenses,
two_strike (strikes==2) and three_ball (balls==3); plus an unconditional "all"
class. It is NOT a predictor and claims NO market/ROI/$ edge -- it is a
scouting/sequencing descriptive over a completed 2025 pull.

CORPUS LIMIT (honest): pitch_type is statcast's auto-classified code; missing/UNK
codes and types outside the top-N set are dropped from the matrix axes (per-class
`coverage` reported, never silently re-bucketed). Pitch-TYPE sequencing only (no
swing/take split exists in this pull).

FLOORS (declared):
  - TOP_N: matrix axes are the top-N pitch types by league frequency; each class
    reports `coverage` = share of its transitions with BOTH ends in that set.
  - ROW_MIN_N: a previous-pitch row below this many transitions is flagged
    below_floor (its conditional probs are still shown but marked noisy).
  - CLASS_MIN_TRANS: a class below this many transitions is reported below_floor, no matrix.
  - Every P(next|prev) uses row_n_from (all transitions from that prev type) as denom, so rows sum to <=1; the chart plots the "all"-class matrix only.

Truth source for claim discipline: docs/JOB_EVIDENCE_PACKET.md.
Output: out/pitch_sequencing.json + docs/img/pitch_sequencing.png.
CLI: python -m scripts.platformkit.analytics_showcase.pitch_sequencing [--check]
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "pitch_sequencing.json"
OUT_PNG = REPO / "docs" / "img" / "pitch_sequencing.png"
STATCAST_PATH = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"

NEEDED_COLS = ["game_pk", "at_bat_number", "pitch_number", "pitcher",
               "pitch_type", "balls", "strikes"]
KEY_COLS = ["game_pk", "at_bat_number", "pitch_number", "pitcher"]
VALID_BALLS = [0, 1, 2, 3]
VALID_STRIKES = [0, 1, 2]

TOP_N = 8
ROW_MIN_N = 200
CLASS_MIN_TRANS = 2000
CLASS_ORDER = ["all", "behind", "even", "ahead", "two_strike", "three_ball"]
LEVERAGE_DEFS = {
    "all": "every transition (unconditional; charted matrix)",
    "behind": "balls > strikes on the next pitch (pitcher behind)",
    "even": "balls == strikes on the next pitch",
    "ahead": "strikes > balls on the next pitch (pitcher ahead)",
    "two_strike": "strikes == 2 on the next pitch (putaway lens -- OVERLAPS partition)",
    "three_ball": "balls == 3 on the next pitch (must-throw lens -- OVERLAPS partition)",
    "partition_note": "behind/even/ahead is a mutually-exclusive partition; two_strike/"
                      "three_ball are overlapping lenses (NOT additive); 'all' is the union.",
}
CAVEAT = (
    "DESCRIPTIVE_ONLY pitch-sequencing showcase over the local 2025 statcast pull: "
    "P(next pitch type | previous pitch type) within a plate appearance, one matrix "
    "per count-leverage class (leverage taken on the NEXT pitch). pitch_type is "
    "statcast's auto-classified code; matrix axes are the top-N league types "
    "(per-class coverage reported). Not a predictor; no edge/ROI/$ claim."
)


def _leverage(trans: pd.DataFrame) -> pd.Series:
    """Pitcher-POV partition on the NEXT pitch's count (matches mlb_count_leverage)."""
    lev = pd.Series("even", index=trans.index)
    lev[trans["strikes"] > trans["balls"]] = "ahead"
    lev[trans["balls"] > trans["strikes"]] = "behind"
    return lev


def _class_sub(trans: pd.DataFrame, cls: str) -> pd.DataFrame:
    if cls == "all":
        return trans
    if cls == "two_strike":
        return trans[trans["strikes"] == 2]
    if cls == "three_ball":
        return trans[trans["balls"] == 3]
    return trans[trans["lev"] == cls]


def _matrix_for(sub: pd.DataFrame, types: list) -> dict:
    """Transition matrix over the top-N `types` axis; row denom = ALL transitions from
    that prev type, so each conditional row sums to <= 1 (remainder = off-axis nexts)."""
    ct = pd.crosstab(sub["from_type"], sub["to_type"]).reindex(
        index=types, columns=types, fill_value=0)
    counts = ct.to_numpy(dtype=int)
    fc = sub["from_type"].value_counts()
    row_n = np.array([int(fc.get(t, 0)) for t in types])  # from-count, incl. off-axis nexts
    prob, row_below = [], []
    for i in range(len(types)):
        rn = int(row_n[i])
        row_below.append(rn < ROW_MIN_N)
        prob.append([None] * len(types) if rn == 0
                    else [round(float(counts[i, j]) / rn, 4) for j in range(len(types))])
    ti, tj = divmod(int(counts.argmax()), len(types))
    top = {"from": types[ti], "to": types[tj], "n": int(counts[ti, tj]),
           "p_given_from": (round(float(counts[ti, tj]) / row_n[ti], 4)
                            if row_n[ti] else None)}
    n_in_matrix = int(counts.sum())
    return {
        "n_transitions_in_class": int(len(sub)),
        "n_in_matrix": n_in_matrix,
        "coverage": round(n_in_matrix / len(sub), 4) if len(sub) else None,
        "row_n_from": [int(x) for x in row_n],
        "row_below_floor": row_below,
        "count_matrix": counts.tolist(),
        "prob_matrix": prob,
        "top_transition": top,
    }


def build_transitions(df: pd.DataFrame) -> pd.DataFrame:
    """One-pass adjacent-pitch transitions within (game_pk, at_bat_number, pitcher)."""
    df = df.sort_values(["game_pk", "at_bat_number", "pitch_number"])
    g = df.groupby(["game_pk", "at_bat_number", "pitcher"], sort=False)
    df["from_type"] = g["pitch_type"].shift(1)
    df["prev_pnum"] = g["pitch_number"].shift(1)
    adj = (df["pitch_number"] - df["prev_pnum"]) == 1
    to_valid = df["balls"].isin(VALID_BALLS) & df["strikes"].isin(VALID_STRIKES)
    mask = df["from_type"].notna() & adj & to_valid
    trans = df.loc[mask, ["from_type", "pitch_type", "balls", "strikes"]].rename(
        columns={"pitch_type": "to_type"})
    trans["balls"] = trans["balls"].astype(int)
    trans["strikes"] = trans["strikes"].astype(int)
    trans["lev"] = _leverage(trans)
    return trans


def build_showcase() -> dict:
    if not STATCAST_PATH.exists():
        rel = str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")
        return {"status": "local_corpus_absent", "sport": "mlb",
                "needed_artifact": rel, "paths_tried": [rel]}

    df = pd.read_parquet(STATCAST_PATH, columns=NEEDED_COLS)
    n_total = int(len(df))
    for c in KEY_COLS + ["balls", "strikes"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=KEY_COLS + ["pitch_type"]).copy()
    df["pitch_type"] = df["pitch_type"].astype(str)
    n_kept = int(len(df))

    rel_source = str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")
    as_of = datetime.now(timezone.utc).isoformat()
    if n_kept == 0:
        return {"status": "insufficient_data", "sport": "mlb", "source": rel_source,
                "n_pitches_total": n_total, "n_pitches_kept": 0,
                "note": "no rows with a non-null pitch_type + PA keys"}

    types = [str(k) for k in df["pitch_type"].value_counts().head(TOP_N).index]
    trans = build_transitions(df)
    n_trans = int(len(trans))
    if n_trans == 0:
        return {"status": "insufficient_data", "sport": "mlb", "source": rel_source,
                "n_pitches_total": n_total, "n_pitches_kept": n_kept, "n_transitions": 0,
                "note": "no adjacent same-PA pitch pairs (pitch_number diff == 1) found"}

    by_class = []
    for cls in CLASS_ORDER:
        sub = _class_sub(trans, cls)
        entry = {"class": cls, "overlapping": cls in ("two_strike", "three_ball"),
                 "definition": LEVERAGE_DEFS[cls]}
        if len(sub) < CLASS_MIN_TRANS:
            entry.update({"n_transitions_in_class": int(len(sub)),
                          "status": "below_floor", "floor": CLASS_MIN_TRANS})
        else:
            entry.update(_matrix_for(sub, types))
        by_class.append(entry)

    return {
        "status": "ok",
        "sport": "mlb",
        "label": "DESCRIPTIVE_ONLY",
        "caveat": CAVEAT,
        "source": rel_source,
        "as_of": as_of,
        "n_pitches_total": n_total,
        "n_pitches_kept": n_kept,
        "n_transitions": n_trans,
        "floors": {
            "top_n_pitch_types": TOP_N,
            "row_min_n": ROW_MIN_N,
            "class_min_transitions": CLASS_MIN_TRANS,
            "adjacency": "strict pitch_number diff == 1 within (game_pk, at_bat_number, pitcher)",
            "leverage_basis": "count on the NEXT (to) pitch",
            "prob_note": "each P(next|prev) is over ALL transitions from that prev type "
                         "(row_n_from); rows sum to <=1, remainder = next types off the top-N axis",
        },
        "leverage_definitions": LEVERAGE_DEFS,
        "pitch_types": types,
        "chart_class": "all",
        "by_class": by_class,
        "chart": str(OUT_PNG.relative_to(REPO)).replace("\\", "/"),
    }


def render_chart(showcase: dict, path: Path) -> None:
    all_cls = next(e for e in showcase["by_class"] if e["class"] == "all")
    types = showcase["pitch_types"]
    n = len(types)
    M = np.array([[np.nan if v is None else v for v in row]
                  for row in all_cls["prob_matrix"]], dtype=float)
    vmax = float(np.nanmax(M)) if np.isfinite(M).any() else 1.0

    fig, ax = plt.subplots(figsize=(1.0 * n + 2.6, 1.0 * n + 1.9))
    im = ax.imshow(M, cmap="Blues", vmin=0.0, vmax=vmax)
    ax.set_xticks(range(n)); ax.set_xticklabels(types, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n)); ax.set_yticklabels(types, fontsize=8)
    ax.set_xlabel("next pitch type", fontsize=9)
    ax.set_ylabel("previous pitch type", fontsize=9)
    for i in range(n):
        for j in range(n):
            v = M[i, j]
            if np.isfinite(v) and v > 0:
                ax.text(j, i, "%d" % round(v * 100), ha="center", va="center",
                        fontsize=7, color="white" if v > vmax * 0.6 else "#222222")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="P(next | prev), cells = %")
    ax.set_title("MLB 2025 pitch sequencing: P(next pitch type | previous), all counts\n"
                 "(per-leverage-class matrices in JSON)", fontsize=9, fontweight="bold")
    footer = "source: %s  |  floor: top-%d types, row n>=%d  |  as_of: %s" % (
        showcase["source"], showcase["floors"]["top_n_pitch_types"],
        showcase["floors"]["row_min_n"], showcase["as_of"])
    fig.text(0.01, 0.01, footer, fontsize=6, ha="left", va="bottom", color="#555555")
    fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=6.5, ha="right", va="bottom",
             color="#b33333", fontweight="bold")
    fig.tight_layout(rect=(0.0, 0.05, 1.0, 1.0))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> dict:
    showcase = build_showcase()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(showcase, indent=2), encoding="ascii")
    if showcase["status"] == "ok":
        render_chart(showcase, OUT_PNG)
    return showcase


def _check():
    # ponytail: build+write, then assert the outputs exist nonzero (the task's check)
    showcase = main()
    assert showcase["status"] in ("ok", "local_corpus_absent", "insufficient_data")
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, "JSON output missing/empty"
    loaded = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert loaded["status"] == showcase["status"]
    if showcase["status"] == "ok":
        assert showcase["n_transitions"] > 0
        types = showcase["pitch_types"]
        assert 0 < len(types) <= TOP_N
        all_cls = next(e for e in showcase["by_class"] if e["class"] == "all")
        assert "count_matrix" in all_cls, "'all' class fell below floor -- unexpected"
        assert len(all_cls["count_matrix"]) == len(types)
        assert all(len(r) == len(types) for r in all_cls["count_matrix"])
        assert all_cls["n_in_matrix"] > 0
        assert 0.0 < all_cls["coverage"] <= 1.0
        assert all_cls["top_transition"]["n"] > 0
        for i, row in enumerate(all_cls["prob_matrix"]):
            for p in row:
                assert p is None or 0.0 <= p <= 1.0
            if not all_cls["row_below_floor"][i] and all_cls["row_n_from"][i] > 0:
                assert sum(row) <= 1.0001, "conditional row exceeds 1"
        assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, "PNG output missing/empty"
    else:
        assert "needed_artifact" in showcase or "note" in showcase
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "status": result["status"],
            "n_transitions": result.get("n_transitions"),
            "pitch_types": result.get("pitch_types"),
        }, indent=2))
        print("wrote %s" % OUT_JSON)
        if result["status"] == "ok":
            print("wrote %s" % OUT_PNG)
