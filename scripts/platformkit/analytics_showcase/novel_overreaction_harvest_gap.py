"""Novel stat #6 -- Overreaction Harvest Gap (OHG).

METRIC (a self-critical diagnostic whose HONEST finding is a NULL): structural
market overshoot exists at large in-game moves, but OUR model is NOT the tool
that catches it. OHG crosses "the market is wrong" with "and we still can't cash
it".

FORMULA (per sport):
    overreaction  = n-weighted mean |moved_to_minus_outcome| over the largest move
                    buckets {3-6pt, 6-10pt, 10pt+}      (market_overreaction.json)
    model_can_beat = model_closer_rate at the largest disagreement bucket (>=.10)
                     (market_disagreement_profile.json)
    OHG           = overreaction * (0.5 - model_can_beat)

MANDATORY NO-EDGE FRAMING: OHG is reported as the honest null it is -- at max
disagreement the market is usually RIGHT (model_closer_rate ~0.38 mlb / ~0.22
soccer). OHG measures a FAILURE to harvest, NOT an available edge. edge_claimed=False.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_overreaction_harvest_gap
    python -m scripts.platformkit.analytics_showcase.novel_overreaction_harvest_gap --check
"""
import json
import os

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_OVER = os.path.join(SHOWCASE, "out", "market_overreaction.json")
IN_DISAGREE = os.path.join(SHOWCASE, "out", "market_disagreement_profile.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_overreaction_harvest_gap.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_overreaction_harvest_gap.png")

LARGE_MOVE_BUCKETS = ["3-6pt", "6-10pt", "10pt+"]
MAX_DISAGREE_BUCKET = ">=.10"

PRIOR_ART_VERDICT = "NOVEL_SELF_CRITICAL_CROSS"
PRIOR_ART_CITATION = (
    "Overreaction/reversion is Moskowitz (2021, Journal of Finance, 'Asset Pricing and Sports "
    "Betting') and Choi & Hui (2014, JEBO) -- market_overreaction.json's own block flags the "
    "component INCREMENTAL. Disagreement skill is standard forecast verification. Crossing them "
    "into 'the market is wrong AND we still can't cash it' is a measured-FAILURE diagnostic that "
    "no one publishes (papers publish edges, not confessions). Do not claim the components as new."
)
DECLARED_CONFOUNDS = [
    "MANDATORY: OHG is an honest NULL -- at max disagreement the market is usually right "
    "(model_closer_rate 0.38 mlb / 0.22 soccer). It measures a FAILURE to harvest, NOT an edge.",
    "consecutive-row grain, in-game; mlb + soccer_intl only.",
    "soccer tail buckets are tiny (n=21-103), so the soccer overreaction magnitude is noisy.",
]


def _overreaction(buckets):
    """n-weighted mean |moved_to_minus_outcome| over the largest move buckets."""
    num = den = 0.0
    used = []
    for b in LARGE_MOVE_BUCKETS:
        cell = buckets.get(b)
        if not cell or cell.get("moved_to_minus_outcome") is None or not cell.get("n"):
            continue
        n = cell["n"]
        num += abs(cell["moved_to_minus_outcome"]) * n
        den += n
        used.append({"bucket": b, "n": n, "abs_moved_to_minus_outcome": round(abs(cell["moved_to_minus_outcome"]), 4)})
    if den == 0:
        return None, used
    return num / den, used


def build():
    over = json.loads(open(IN_OVER, encoding="utf-8").read()).get("buckets", {})
    disagree = json.loads(open(IN_DISAGREE, encoding="utf-8").read()).get("sports", {})

    rows = []
    for sport in sorted(set(over) & set(disagree)):
        ov, used = _overreaction(over[sport])
        maxrow = next((r for r in disagree[sport] if r.get("bucket") == MAX_DISAGREE_BUCKET), None)
        if ov is None or maxrow is None:
            continue
        mcb = maxrow.get("model_closer_rate")
        ohg = ov * (0.5 - mcb)
        rows.append({
            "sport": sport,
            "overreaction_abs_mean": round(ov, 4),
            "overreaction_buckets_used": used,
            "model_can_beat_model_closer_rate": mcb,
            "max_disagreement_bucket": MAX_DISAGREE_BUCKET,
            "max_disagreement_n": maxrow.get("n"),
            "model_brier_at_max_disagree": maxrow.get("model_brier"),
            "market_brier_at_max_disagree": maxrow.get("market_brier"),
            "ohg": round(ohg, 4),
            "market_usually_right_at_max_disagree": mcb < 0.5,
        })
    rows.sort(key=lambda r: r["ohg"], reverse=True)

    payload = {
        "stat_name": "Overreaction Harvest Gap",
        "abbrev": "OHG",
        "edge_claimed": False,
        "descriptive_only": True,
        "is_honest_null": True,
        "metric_definition": "Structural market overshoot at large in-game moves, scaled by how far short our model falls of beating the market at max disagreement -- a measured failure to harvest, not an edge.",
        "formula": "OHG = (n-weighted mean |moved_to - outcome| over {3-6pt,6-10pt,10pt+}) * (0.5 - model_closer_rate at >=.10 disagreement).",
        "source_artifacts": [
            os.path.relpath(IN_OVER, ROOT).replace("\\", "/"),
            os.path.relpath(IN_DISAGREE, ROOT).replace("\\", "/"),
        ],
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "results": rows,
        "headline": _headline(rows),
        "index_card": None,
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _headline(rows):
    if not rows:
        return "No sport had both instruments."
    parts = []
    for r in rows:
        parts.append(f"{r['sport']}: overshoot {r['overreaction_abs_mean']:.3f} but model beats market only "
                     f"{r['model_can_beat_model_closer_rate']:.0%} of the time at max disagreement -> "
                     f"OHG {r['ohg']:.3f} (a failure to harvest, not an edge)")
    return "; ".join(parts)


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_overreaction_harvest_gap",
        "formula": p["formula"], "prior_art_verdict": p["prior_art_verdict"],
        "headline": p["headline"], "edge_claimed": False, "is_honest_null": True,
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
    rows = payload["results"]
    if not rows:
        return False
    sports = [r["sport"] for r in rows]
    over = [r["overreaction_abs_mean"] for r in rows]
    shortfall = [0.5 - r["model_can_beat_model_closer_rate"] for r in rows]
    ohg = [r["ohg"] for r in rows]
    x = list(range(len(rows)))
    w = 0.26
    fig, ax = plt.subplots(figsize=(7, 4.3))
    ax.bar([i - w for i in x], over, w, label="overreaction (|moved_to - outcome|)", color="#b7791f")
    ax.bar(x, shortfall, w, label="0.5 - model_closer_rate (shortfall)", color="#888888")
    ax.bar([i + w for i in x], ohg, w, label="OHG (product)", color="#c0392b")
    ax.set_xticks(list(x))
    ax.set_xticklabels(sports)
    ax.set_ylabel("value")
    ax.set_title("Overreaction Harvest Gap -- an honest NULL\n"
                 "market overshoots, but the model can't beat it at max disagreement. edge_claimed=False", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["is_honest_null"] is True
    assert d["results"], "no OHG rows"
    for r in d["results"]:
        assert r["market_usually_right_at_max_disagree"] is True, "OHG must stay a null: model does not beat market"


def check():
    if not (os.path.exists(IN_OVER) and os.path.exists(IN_DISAGREE)):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_overreaction_harvest_gap")
        return
    payload = build()
    _validate(payload)
    mlb = next((r for r in payload["results"] if r["sport"] == "mlb"), None)
    assert mlb and abs(mlb["ohg"] - 0.0088) < 5e-4, mlb  # 0.0721 * (0.5-0.3773)
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_overreaction_harvest_gap ({len(payload['results'])} sports, "
          f"mlb OHG {mlb['ohg']:.4f} [honest null], plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"], "results": p["results"]}, indent=2))
