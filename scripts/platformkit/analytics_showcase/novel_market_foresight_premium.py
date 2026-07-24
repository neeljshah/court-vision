"""Novel stat #2 -- Market Foresight Premium (MFP).

METRIC: per (sport, game-time checkpoint), the market's EXCESS resolving power
over a scoreboard-only model, normalized per bit of uncertainty still left in
the game. A rising MFP curve = the market prices in-game news the state-only
model cannot see, and the gap grows as the game resolves.

FORMULA (per sport, checkpoint t):
    market_skill = (naive_brier - market_brier) / naive_brier
    model_skill  = (naive_brier - model_brier)  / naive_brier
    MFP(t)       = (market_skill - model_skill) / max(mean_entropy_market_bits(t), 0.15)

Joins two committed instruments on (sport, checkpoint): info_arrival_curve.json
carries the paired model/market/naive Brier; market_convergence.json carries the
mean market Bernoulli entropy (bits). Only checkpoints present in BOTH are used.
edge_claimed=False -- calibration/foresight, not a $ claim.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_market_foresight_premium
    python -m scripts.platformkit.analytics_showcase.novel_market_foresight_premium --check
"""
import json
import os

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_BRIER = os.path.join(SHOWCASE, "out", "info_arrival_curve.json")       # model/market/naive brier
IN_ENTROPY = os.path.join(SHOWCASE, "out", "market_convergence.json")     # mean_entropy_market_bits
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_market_foresight_premium.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_market_foresight_premium.png")

ENTROPY_FLOOR = 0.15  # bits; keeps MFP finite as entropy -> 0 late in a game

PRIOR_ART_VERDICT = "INCREMENTAL"
PRIOR_ART_CITATION = (
    "The absorption instrument (paired model/market/naive Brier by game-time) is arXiv "
    "2606.07811 ('When Do Markets Fully Process Public Information', Kalshi/NBA), which "
    "info_arrival_curve.json's own novelty block flags INCREMENTAL. Entropy decay is "
    "textbook (Shannon). Do NOT claim first-ever on the components -- only the skill-gap-"
    "PER-BIT normalization (the unpublished cross of the two separate literatures) is claimed."
)
DECLARED_CONFOUNDS = [
    "'model' is one specific state-only forecaster, so MFP conflates genuine news the market "
    "prices (lineups, momentum) with plain model misspecification.",
    "Entropy -> 0 late in a game would explode the ratio; the 0.15-bit floor caps that.",
    "mlb (inning) and soccer_intl (5-min bucket) only; different clock units, not equated.",
]


def _skill(naive, other):
    if not naive:
        return None
    return (naive - other) / naive


def build():
    brier = json.loads(open(IN_BRIER, encoding="utf-8").read()).get("checkpoints", {})
    entropy = json.loads(open(IN_ENTROPY, encoding="utf-8").read()).get("checkpoints", {})
    sports = {}
    for sport, cps in brier.items():
        ent_cps = entropy.get(sport, {})
        curve = []
        for t, c in cps.items():
            ent = ent_cps.get(t, {}).get("mean_entropy_market_bits")
            if ent is None:
                continue  # need both instruments at this checkpoint
            mkt = _skill(c.get("naive_brier"), c.get("market_brier"))
            mdl = _skill(c.get("naive_brier"), c.get("model_brier"))
            if mkt is None or mdl is None:
                continue
            denom = max(ent, ENTROPY_FLOOR)
            curve.append({
                "checkpoint": t,
                "n": c.get("n"),
                "market_skill": round(mkt, 4),
                "model_skill": round(mdl, 4),
                "entropy_market_bits": ent,
                "entropy_floored": ent < ENTROPY_FLOOR,
                "mfp": round((mkt - mdl) / denom, 4),
            })
        if not curve:
            continue
        curve.sort(key=lambda r: float(r["checkpoint"]))
        mfps = [r["mfp"] for r in curve]
        sports[sport] = {
            "checkpoints": curve,
            "n_checkpoints": len(curve),
            "mfp_first": curve[0]["mfp"],
            "mfp_last": curve[-1]["mfp"],
            "mfp_mean": round(sum(mfps) / len(mfps), 4),
            "mfp_delta_last_minus_first": round(curve[-1]["mfp"] - curve[0]["mfp"], 4),
        }

    payload = {
        "stat_name": "Market Foresight Premium",
        "abbrev": "MFP",
        "edge_claimed": False,
        "descriptive_only": True,
        "metric_definition": "The market's excess resolving power over a scoreboard-only model, per bit of uncertainty still left in the game, by checkpoint.",
        "formula": "MFP(t) = ((naive-market)/naive - (naive-model)/naive) / max(entropy_market_bits, 0.15)",
        "source_artifacts": [
            os.path.relpath(IN_BRIER, ROOT).replace("\\", "/"),
            os.path.relpath(IN_ENTROPY, ROOT).replace("\\", "/"),
        ],
        "entropy_floor_bits": ENTROPY_FLOOR,
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "results": sports,
        "headline": _headline(sports),
        "index_card": None,
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _headline(sports):
    parts = []
    for s, d in sports.items():
        trend = "rises" if d["mfp_delta_last_minus_first"] > 0 else "flat/falls"
        parts.append(f"{s}: MFP {trend} from {d['mfp_first']:.2f} to {d['mfp_last']:.2f} over the game (mean {d['mfp_mean']:.2f})")
    return "; ".join(parts) if parts else "No sport had both instruments on a shared checkpoint."


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_market_foresight_premium",
        "formula": p["formula"], "prior_art_verdict": p["prior_art_verdict"],
        "headline": p["headline"], "edge_claimed": False,
        "source_artifacts": p["source_artifacts"],
        "chart": os.path.relpath(OUT_PNG, ROOT).replace("\\", "/"),
        "n_results": len(p["results"]),
    }


def plot(payload):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    sports = payload["results"]
    if not sports:
        return False
    names = list(sports.keys())
    fig, axes = plt.subplots(1, len(names), figsize=(5.5 * len(names), 4.2), squeeze=False)
    for ax, s in zip(axes[0], names):
        curve = sports[s]["checkpoints"]
        xs = [float(r["checkpoint"]) for r in curve]
        ys = [r["mfp"] for r in curve]
        ax.plot(xs, ys, marker="o", color="#2b6cb0")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        ax.set_title(f"{s} (n_cp={len(curve)})")
        ax.set_xlabel("checkpoint (inning / minute)")
    axes[0][0].set_ylabel("MFP = market excess skill per bit")
    fig.suptitle("Market Foresight Premium over game time -- edge_claimed=False", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["results"], "no MFP curves"
    for s, v in d["results"].items():
        assert v["checkpoints"], f"{s} empty"


def check():
    if not (os.path.exists(IN_BRIER) and os.path.exists(IN_ENTROPY)):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_market_foresight_premium")
        return
    payload = build()
    _validate(payload)
    mlb = payload["results"].get("mlb")
    assert mlb is not None
    first = mlb["checkpoints"][0]
    assert first["checkpoint"] == "1" and 0.04 < first["mfp"] < 0.08, first
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_market_foresight_premium ({len(payload['results'])} sports, "
          f"mlb cp1 MFP {first['mfp']:.3f}, plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"],
                          "summary": {s: {k: v[k] for k in ("n_checkpoints", "mfp_first", "mfp_last", "mfp_mean")}
                                      for s, v in p["results"].items()}}, indent=2))
