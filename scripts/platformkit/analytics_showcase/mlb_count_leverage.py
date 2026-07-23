"""MLB count-leverage showcase: ONE column-selective pass over the local 2025
statcast pull -- how a pitcher's PITCH MIX and available per-pitch OUTCOME
PROXIES shift across count-leverage classes.

SCOPE (DESCRIPTIVE_ONLY): partitions every pitch by its count state into a
pitcher-POV leverage PARTITION -- ahead (strikes>balls), even (strikes==balls),
behind (balls>strikes) -- plus two OVERLAPPING putaway lenses that cut across
that partition: two_strike (strikes==2) and three_ball (balls==3). For each
class it reports the pitch-type mix and the outcome proxies this corpus can
honestly support. It is NOT a predictor and claims NO market/ROI/$ edge -- it
is a data-coverage / scouting descriptive over a completed 2025 pull.

CORPUS LIMITS (honest, not papered over):
  - `type` is S/B/X only: the "strike" rate here CONFLATES called + swinging +
    foul strikes and CANNOT be split into swing/take -- this corpus has no
    per-pitch swing/take/description column (see
    domains/mlb/matchup/pitch_mix_profiles.py CORPUS LIMIT). So the proxies are
    strike/ball/in-play SHARE and in-zone SHARE, nothing finer.
  - in_zone_rate is from statcast `zone` (1-9 = in the 3x3 strike zone, 11-14 =
    shadow/out); computed over NON-NULL zone only, denominator reported.

FLOORS (declared):
  - CLASS_MIN_N: a leverage class must clear this many pitches to be reported.
  - Every proxy rate is over its own NON-NULL denominator (n_type / n_zone
    reported per class), never over the raw class count.
  - The chart plots only the overall top-CHART_TOP_PT pitch types (the mix-shift
    signal); the full per-class top-MIX_TOP mix lives in the JSON. two_strike /
    three_ball OVERLAP the partition (a lens, not additive) and are so labelled.

Truth source for claim discipline: docs/JOB_EVIDENCE_PACKET.md.
Output: out/mlb_count_leverage.json + docs/img/mlb_count_leverage.png.
CLI: python -m scripts.platformkit.analytics_showcase.mlb_count_leverage [--check]
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

try:  # package-qualified when run via -m; bare when run as a script (check_all path)
    from scripts.platformkit.analytics_showcase.atlas_factory import card_figure
except ImportError:
    from atlas_factory import card_figure

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "mlb_count_leverage.json"
OUT_PNG = REPO / "docs" / "img" / "mlb_count_leverage.png"
STATCAST_PATH = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2025.parquet"

NEEDED_COLS = ["balls", "strikes", "pitch_type", "type", "zone"]
VALID_BALLS = [0, 1, 2, 3]
VALID_STRIKES = [0, 1, 2]
IN_ZONE = [1, 2, 3, 4, 5, 6, 7, 8, 9]  # statcast grid: 1-9 in-zone, 11-14 shadow/out

CLASS_MIN_N = 500
CHART_TOP_PT = 5
MIX_TOP = 10
CLASS_ORDER = ["behind", "even", "ahead", "two_strike", "three_ball"]
LEVERAGE_DEFS = {
    "behind": "balls > strikes (pitcher behind; hitter's count)",
    "even": "balls == strikes",
    "ahead": "strikes > balls (pitcher ahead)",
    "two_strike": "strikes == 2 (putaway lens -- OVERLAPS the partition)",
    "three_ball": "balls == 3 (must-throw-strike lens -- OVERLAPS the partition)",
    "partition_note": "behind/even/ahead is a mutually-exclusive, exhaustive "
                      "partition; two_strike/three_ball are overlapping lenses "
                      "(counts NOT additive with the partition).",
}
CAVEAT = (
    "DESCRIPTIVE_ONLY count-leverage showcase over the local 2025 statcast pull: "
    "pitch-type mix and per-pitch outcome PROXIES (type S/B/X share, in-zone "
    "share) by count-leverage class. `type`==S conflates called+swinging+foul "
    "(no per-pitch swing/take in this corpus). Not a predictor; no edge/ROI/$ claim."
)


def _proxies(g: pd.DataFrame) -> dict:
    """Per-pitch outcome proxies over their own non-null denominators."""
    t = g["type"]
    n_type = int(t.notna().sum())
    z = g["zone"]
    n_zone = int(z.notna().sum())
    n_in = int(z.isin(IN_ZONE).sum())
    rate = lambda num, den: round(num / den, 4) if den else None
    return {
        "n_type": n_type,
        "strike_rate_type_S": rate(int((t == "S").sum()), n_type),
        "ball_rate": rate(int((t == "B").sum()), n_type),
        "inplay_rate_type_X": rate(int((t == "X").sum()), n_type),
        "n_zone": n_zone,
        "in_zone_rate": rate(n_in, n_zone),
    }


def _pitch_mix(g: pd.DataFrame, top: int) -> tuple[int, list]:
    pt = g["pitch_type"]
    n = int(pt.notna().sum())
    vc = pt.value_counts()  # drops NaN
    mix = [{"pitch_type": str(k), "n": int(v), "pct": round(100 * v / n, 2)}
           for k, v in vc.items()]
    return n, mix[:top]


def _class_frame(df: pd.DataFrame, cls: str) -> pd.DataFrame:
    if cls == "two_strike":
        return df[df["strikes"] == 2]
    if cls == "three_ball":
        return df[df["balls"] == 3]
    return df[df["lev"] == cls]


def build_showcase() -> dict:
    if not STATCAST_PATH.exists():
        rel = str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")
        return {"status": "local_corpus_absent", "sport": "mlb",
                "needed_artifact": rel, "paths_tried": [rel]}

    df = pd.read_parquet(STATCAST_PATH, columns=NEEDED_COLS)
    n_total = int(len(df))

    b = pd.to_numeric(df["balls"], errors="coerce")
    s = pd.to_numeric(df["strikes"], errors="coerce")
    valid = b.isin(VALID_BALLS) & s.isin(VALID_STRIKES)
    df = df[valid].copy()
    df["balls"] = b[valid].astype(int)
    df["strikes"] = s[valid].astype(int)
    n_valid = int(len(df))

    as_of = datetime.now(timezone.utc).isoformat()
    rel_source = str(STATCAST_PATH.relative_to(REPO)).replace("\\", "/")
    if n_valid == 0:
        return {"status": "insufficient_data", "sport": "mlb", "source": rel_source,
                "n_pitches_total": n_total, "n_pitches_valid_count": 0,
                "note": "no rows with a valid MLB count (balls 0-3, strikes 0-2)"}

    # pitcher-POV partition (mutually exclusive); overlapping lenses handled in _class_frame
    df["lev"] = "even"
    df.loc[df["strikes"] > df["balls"], "lev"] = "ahead"
    df.loc[df["balls"] > df["strikes"], "lev"] = "behind"

    chart_types = [str(k) for k in df["pitch_type"].value_counts().head(CHART_TOP_PT).index]

    by_class = []
    for cls in CLASS_ORDER:
        g = _class_frame(df, cls)
        n = int(len(g))
        if n < CLASS_MIN_N:
            by_class.append({"class": cls, "overlapping": cls in ("two_strike", "three_ball"),
                             "n": n, "status": "below_floor",
                             "floor": CLASS_MIN_N})
            continue
        pt_n, mix = _pitch_mix(g, MIX_TOP)
        by_class.append({
            "class": cls,
            "overlapping": cls in ("two_strike", "three_ball"),
            "definition": LEVERAGE_DEFS[cls],
            "n": n,
            "pitch_type_n": pt_n,
            "pitch_mix_top": mix,
            "outcome_proxies": _proxies(g),
        })

    # exact-count grid (12 states): one compact row each
    by_count = []
    for (bb, ss), g in df.groupby(["balls", "strikes"]):
        pt_n, mix = _pitch_mix(g, 1)
        top = mix[0] if mix else {"pitch_type": None, "pct": None}
        px = _proxies(g)
        by_count.append({
            "balls": int(bb), "strikes": int(ss),
            "leverage_class": g["lev"].iloc[0], "n": int(len(g)),
            "top_pitch_type": top["pitch_type"], "top_pitch_pct": top["pct"],
            "strike_rate_type_S": px["strike_rate_type_S"], "in_zone_rate": px["in_zone_rate"],
        })
    by_count.sort(key=lambda r: (r["balls"], r["strikes"]))

    return {
        "status": "ok",
        "sport": "mlb",
        "label": "DESCRIPTIVE_ONLY",
        "caveat": CAVEAT,
        "source": rel_source,
        "as_of": as_of,
        "n_pitches_total": n_total,
        "n_pitches_valid_count": n_valid,
        "floors": {
            "class_min_n": CLASS_MIN_N,
            "chart_top_pitch_types": CHART_TOP_PT,
            "mix_top_per_class": MIX_TOP,
            "proxy_note": "every rate is over its own non-null denominator "
                          "(n_type / n_zone), never the raw class count",
        },
        "leverage_definitions": LEVERAGE_DEFS,
        "chart_pitch_types": chart_types,
        "by_leverage_class": by_class,
        "by_exact_count": by_count,
        "chart": str(OUT_PNG.relative_to(REPO)).replace("\\", "/"),
    }


def render_chart(showcase: dict, path: Path) -> dict:
    by = {e["class"]: e for e in showcase["by_leverage_class"]}
    types = showcase["chart_pitch_types"]
    xs = [0, 1, 2, 3.4, 4.4]  # partition (0-2) then overlapping lenses (gap) 3.4/4.4
    labels = ["behind", "even", "ahead", "2strk*", "3ball*"]

    def _axis(ax):
        ax.axvline(2.7, color="#bbbbbb", ls=":", lw=0.8)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=30, ha="right")

    def share(cls, pt):  # pct of pitches; 0.0 if pitch type absent / class below floor
        e = by.get(cls, {})
        for r in e.get("pitch_mix_top", []):
            if r["pitch_type"] == pt:
                return r["pct"]
        return 0.0

    def proxy(cls, key):
        e = by.get(cls, {})
        v = e.get("outcome_proxies", {}).get(key)
        return v * 100 if v is not None else float("nan")

    def panel_mix(ax):
        for pt in types:
            ax.plot(xs, [share(c, pt) for c in CLASS_ORDER], marker="o", ms=3, lw=1, label=pt)
        _axis(ax)
        ax.set_ylabel("% of pitches", fontsize=6)
        ax.legend(fontsize=5, ncol=2, loc="best")
        ax.text(3.55, ax.get_ylim()[1] * 0.02, "*overlaps partition", fontsize=4.5, color="#888")

    def panel_proxy(ax):
        for lbl, key in [("strike(S)", "strike_rate_type_S"), ("in-zone", "in_zone_rate"),
                         ("in-play(X)", "inplay_rate_type_X")]:
            ax.plot(xs, [proxy(c, key) for c in CLASS_ORDER], marker="s", ms=3, lw=1, label=lbl)
        _axis(ax)
        ax.set_ylabel("%", fontsize=6)
        ax.legend(fontsize=5, loc="best")

    return card_figure(
        title="MLB 2025: pitch-mix + outcome-proxy shift by count leverage",
        panels=[("pitch mix (top %d types)" % len(types), panel_mix),
                ("outcome proxies", panel_proxy)],
        source_artifact=showcase["source"],
        floors="class n>=%d; rates over non-null denom" % CLASS_MIN_N,
        as_of=showcase["as_of"],
        out_path=path,
    )


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
        assert showcase["n_pitches_valid_count"] > 0
        assert len(showcase["chart_pitch_types"]) > 0
        reported = [e for e in showcase["by_leverage_class"] if "outcome_proxies" in e]
        assert reported, "no leverage class cleared the floor"
        for e in reported:
            assert 0 < e["pitch_type_n"] <= e["n"]
            sr = e["outcome_proxies"]["strike_rate_type_S"]
            assert sr is None or 0.0 <= sr <= 1.0
        assert len(showcase["by_exact_count"]) > 0
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
            "n_pitches_valid_count": result.get("n_pitches_valid_count"),
            "chart_pitch_types": result.get("chart_pitch_types"),
        }, indent=2))
        print("wrote %s" % OUT_JSON)
        if result["status"] == "ok":
            print("wrote %s" % OUT_PNG)
