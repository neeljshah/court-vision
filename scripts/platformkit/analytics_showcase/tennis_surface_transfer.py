"""
Tennis surface-split transfer: per-player clay<->hard win-rate gap and grass
adaptability, read straight off the tennis surface-context SNAPSHOT store and
summarized as floored distributions + top/bottom leans.

SCOPE (DESCRIPTIVE_ONLY): one column-selective pass over the four snapshot
parquets the surface-context producer already wrote
(tennis_surface_context_snapshot_{atp,wta}_{career,recent_form}.parquet). For
each (tour x window) combo it reports, using the store's OWN derived fields:
  - clay<->hard gap    = clay_minus_hard = clay_wr - hard_wr   (>0 = clay-leaning)
  - grass adaptability = grass_adapt     = grass_wr - ov_wr    (>0 = over-performs on grass)
as a distribution (mean/std/p10/p50/p90/min/max/share-positive) plus the top-5
and bottom-5 players on each. It is NOT a forecast of any future match and
claims NO market/ROI/$ edge -- it describes matches ALREADY PLAYED.

FLOORS (declared -- copied VERBATIM from the producer's prereg floors,
scripts/platformkit/intel_validation/tennis_surface_context_claims.py, never
retuned here):
  - clay<->hard gap: clay_n >= 25 AND hard_n >= 25 (MIN_GAP_FLOOR).
  - grass adaptability: grass_n >= 15 (MIN_GRASS_FLOOR -- grass is scarce on
    tour, a stricter floor would empty the ranking).
A floor that empties a combo publishes NO ranking (honest skip), never [].

CONFOUNDS (carried from the store, stated not papered over): opponent-strength
is NOT controlled -- surface draws are not random, so a gap partly reflects
scheduling/seeding, not surface skill alone; retirement rows are counted as
decided matches; Hard/Clay/Grass only (Unknown/Carpet excluded upstream).

Truth source for claim discipline: docs/JOB_EVIDENCE_PACKET.md.
Output: out/tennis_surface_transfer.json + docs/img/tennis_surface_transfer.png.
CLI: python -m scripts.platformkit.analytics_showcase.tennis_surface_transfer [--check]
"""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "tennis_surface_transfer.json"
OUT_PNG = REPO / "docs" / "img" / "tennis_surface_transfer.png"
STORE_DIR = REPO / "data" / "cache" / "intel_claims"

# floors copied verbatim from the producer -- not retuned to any result
GAP_FLOOR = 25    # each of clay_n / hard_n (producer MIN_GAP_FLOOR)
GRASS_FLOOR = 15  # grass_n (producer MIN_GRASS_FLOOR)
TOP = 5

COMBOS = [("atp", "career"), ("atp", "recent_form"), ("wta", "career"), ("wta", "recent_form")]
NEEDED_COLS = ["player_id", "player_name", "clay_n", "clay_wr", "hard_n", "hard_wr",
               "grass_n", "grass_wr", "ov_wr"]
_FIELD_EXPR = {"clay_minus_hard": "clay_wr - hard_wr", "grass_adapt": "grass_wr - ov_wr"}

CAVEAT = (
    "Per-player surface-split transfer off the tennis surface-context snapshot store: "
    "the store's own clay_minus_hard (clay_wr - hard_wr) gap and grass_adapt "
    "(grass_wr - ov_wr) adaptability index, floored and summarized per tour x window. "
    "DESCRIPTIVE_ONLY -- describes matches already played, no forecast, no market/ROI/$ edge."
)


def _num(x, nd=4):
    """Round to nd places, mapping non-finite (NaN/inf) to None so the JSON stays valid."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


def _dist(s: pd.Series) -> dict:
    return {
        "n": int(s.size),
        "mean": _num(s.mean()),
        "std": _num(s.std(ddof=1)) if s.size > 1 else None,
        "p10": _num(s.quantile(0.10)),
        "p50": _num(s.quantile(0.50)),
        "p90": _num(s.quantile(0.90)),
        "min": _num(s.min()),
        "max": _num(s.max()),
        "share_positive": _num((s > 0).mean()),
    }


def _rows(sub: pd.DataFrame, metric: str, extra_cols: list) -> list:
    out = []
    for r in sub.itertuples(index=False):
        entry = {
            "player_name": str(getattr(r, "player_name")).encode("ascii", "replace").decode(),
            metric: _num(getattr(r, metric)),
        }
        for c in extra_cols:
            v = getattr(r, c)
            entry[c] = int(v) if c.endswith("_n") else _num(v)
        out.append(entry)
    return out


def _metric_block(frame: pd.DataFrame, metric: str, floor: str, extra_cols: list,
                  hi_label: str, lo_label: str) -> dict:
    block = {
        "field": "%s = %s" % (metric, _FIELD_EXPR[metric]),
        "floor": floor,
        "n_qualifying": int(len(frame)),
    }
    if frame.empty:
        block["distribution"] = None
        block["note"] = "floor eliminated every player in this combo -- nothing to rank (no empty ranking published)"
        block[hi_label] = []
        block[lo_label] = []
        return block
    block["distribution"] = _dist(frame[metric])
    hi = frame.sort_values([metric, "player_id"], ascending=[False, True]).head(TOP)
    lo = frame.sort_values([metric, "player_id"], ascending=[True, True]).head(TOP)
    block[hi_label] = _rows(hi, metric, extra_cols)
    block[lo_label] = _rows(lo, metric, extra_cols)
    return block


def _combo_from_frame(df: pd.DataFrame) -> dict:
    """Pure computation on one snapshot frame -- the two floored metrics."""
    gap = df[(df["clay_n"] >= GAP_FLOOR) & (df["hard_n"] >= GAP_FLOOR)].copy()
    gap["clay_minus_hard"] = gap["clay_wr"] - gap["hard_wr"]
    gap = gap.dropna(subset=["clay_minus_hard"])

    adapt = df[df["grass_n"] >= GRASS_FLOOR].copy()
    adapt["grass_adapt"] = adapt["grass_wr"] - adapt["ov_wr"]
    adapt = adapt.dropna(subset=["grass_adapt"])

    return {
        "n_players_in_snapshot": int(len(df)),
        "clay_hard_gap": _metric_block(
            gap, "clay_minus_hard",
            "clay_n>=%d AND hard_n>=%d" % (GAP_FLOOR, GAP_FLOOR),
            ["clay_wr", "hard_wr", "clay_n", "hard_n"],
            "most_clay_favoring", "most_hard_favoring"),
        "grass_adaptability": _metric_block(
            adapt, "grass_adapt",
            "grass_n>=%d" % GRASS_FLOOR,
            ["grass_wr", "ov_wr", "grass_n"],
            "most_adaptive", "least_adaptive"),
    }


def compute_combo(tour: str, window: str) -> dict:
    path = STORE_DIR / ("tennis_surface_context_snapshot_%s_%s.parquet" % (tour, window))
    if not path.exists():
        return {"status": "local_corpus_absent",
                "needed_artifact": str(path.relative_to(REPO)).replace("\\", "/")}
    df = pd.read_parquet(path, columns=NEEDED_COLS)
    block = _combo_from_frame(df)
    block["status"] = "ok"
    block["source"] = str(path.relative_to(REPO)).replace("\\", "/")
    return block


def build_showcase() -> dict:
    combos = {"%s_%s" % (t, w): compute_combo(t, w) for t, w in COMBOS}
    any_ok = any(b.get("status") == "ok" for b in combos.values())
    return {
        "label": "DESCRIPTIVE_ONLY",
        "sport": "tennis",
        "status": "ok" if any_ok else "local_corpus_absent",
        "caveat": CAVEAT,
        "truth_source": "docs/JOB_EVIDENCE_PACKET.md",
        "store": "tennis_surface_context snapshots "
                 "(producer: scripts/platformkit/intel_validation/tennis_surface_context_claims.py)",
        "store_fields_used": {
            "clay_hard_gap": "clay_minus_hard = clay_wr - hard_wr (store's own gap field)",
            "grass_adaptability": "grass_adapt = grass_wr - ov_wr (store's own adaptability field)",
        },
        "floors": {
            "clay_hard_gap": "clay_n>=%d AND hard_n>=%d" % (GAP_FLOOR, GAP_FLOOR),
            "grass_adaptability": "grass_n>=%d" % GRASS_FLOOR,
            "note": "floors copied verbatim from the producer's prereg floors "
                    "(MIN_GAP_FLOOR / MIN_GRASS_FLOOR), not retuned here",
        },
        "confounds": [
            "opponent-strength NOT controlled -- surface draws are not random, a gap partly "
            "reflects scheduling/seeding, not surface skill alone",
            "retirement rows counted as DECIDED matches (winner column authoritative) -- upstream store choice",
            "Hard/Clay/Grass only; Unknown/Carpet excluded upstream",
            "DESCRIPTIVE_ONLY -- describes matches already played; NOT a forecast, NO market/ROI/$ edge",
        ],
        "combos": combos,
    }


def render_chart(showcase: dict, path: Path) -> None:
    labels, gap_stats, adapt_stats = [], [], []
    for key in ("atp_career", "atp_recent_form", "wta_career", "wta_recent_form"):
        b = showcase["combos"].get(key)
        if not b or b.get("status") != "ok":
            continue
        labels.append(key.replace("_", " ").replace("recent form", "recent"))
        gap_stats.append(b["clay_hard_gap"]["distribution"])
        adapt_stats.append(b["grass_adaptability"]["distribution"])
    if not labels:
        return
    y = list(range(len(labels)))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    panels = (
        (axes[0], gap_stats, "clay<->hard gap  (clay_wr - hard_wr)", "gap  (>0 = clay-favoring)"),
        (axes[1], adapt_stats, "grass adaptability  (grass_wr - ov_wr)", "adapt  (>0 = over-performs on grass)"),
    )
    for ax, stats, title, xlabel in panels:
        for yi, st in zip(y, stats):
            if not st or st.get("p50") is None:
                continue
            ax.hlines(yi, st["min"], st["max"], color="#cccccc", lw=1)
            ax.hlines(yi, st["p10"], st["p90"], color="#2a6fbf", lw=4)
            ax.scatter([st["p50"]], [yi], color="#c0392b", zorder=3)
        ax.axvline(0, color="#444444", ls="--", lw=1)
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.set_title(title, fontsize=9)
    fig.suptitle("tennis surface-split transfer: per-player gap + adaptability distributions\n"
                 "(DESCRIPTIVE_ONLY -- bar=p10-p90, dot=p50, thin line=min-max; floors declared)", fontsize=9)
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
    # ponytail: (a) pure-logic check on a synthetic snapshot frame, (b) real-disk consistency
    fake = pd.DataFrame({
        "player_id": [1, 2, 3],
        "player_name": ["ClayCat", "HardHat", "GrassGuru"],
        "clay_n": [40, 40, 10], "clay_wr": [0.80, 0.40, 0.50],
        "hard_n": [40, 40, 40], "hard_wr": [0.40, 0.80, 0.50],
        "grass_n": [20, 5, 20], "grass_wr": [0.30, 0.50, 0.90], "ov_wr": [0.50, 0.60, 0.55],
    })
    block = _combo_from_frame(fake)
    gap, adapt = block["clay_hard_gap"], block["grass_adaptability"]
    assert gap["n_qualifying"] == 2, gap["n_qualifying"]              # player 3 fails clay_n>=25
    assert gap["most_clay_favoring"][0]["player_name"] == "ClayCat"
    assert gap["most_hard_favoring"][0]["player_name"] == "HardHat"
    assert 0.0 <= gap["distribution"]["share_positive"] <= 1.0
    assert adapt["n_qualifying"] == 2, adapt["n_qualifying"]          # player 2 fails grass_n>=15
    assert adapt["most_adaptive"][0]["player_name"] == "GrassGuru"

    showcase = build_showcase()
    assert showcase["status"] in ("ok", "local_corpus_absent")
    if showcase["status"] == "ok":
        ok = [b for b in showcase["combos"].values() if b.get("status") == "ok"]
        assert ok, "status ok but no ok combo"
        assert any(b["clay_hard_gap"]["n_qualifying"] > 0
                   or b["grass_adaptability"]["n_qualifying"] > 0 for b in ok), "every ok combo empty"
    else:
        assert all("needed_artifact" in b for b in showcase["combos"].values())
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        summary = {"status": result["status"]}
        for k, b in result["combos"].items():
            summary[k] = ({"gap_n": b["clay_hard_gap"]["n_qualifying"],
                           "adapt_n": b["grass_adaptability"]["n_qualifying"]}
                          if b.get("status") == "ok" else b.get("status"))
        print(json.dumps(summary, indent=2))
        print("wrote %s" % OUT_JSON)
        if result["status"] == "ok":
            print("wrote %s" % OUT_PNG)
