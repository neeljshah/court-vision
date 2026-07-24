"""Novel stat #3 -- Schedule Fatigue Tax (SFT).

METRIC: per team-season, how much a team's schedule congestion costs it, using
ONLY the back-to-back (b2b) class -- the one density class with a significance-
tested anchor -- to avoid double-counting the overlapping density windows.
League "schedule-inequality" = the spread of SFT across teams.

FORMULA (per team-season):
    SFT_descriptive = b2b_freq * composite_per36_delta_vs_rested   (composite pts/36)
    SFT_credible    = b2b_freq * b2b_ortg_effect                   (pts/100 ORtg)
where b2b_ortg_effect = -1.73 pts/100 (the repo's CONFIRMED_LOCAL b2b_rest_penalty
receipt, n=4732, p=0.0056), and composite_per36_delta_vs_rested = -0.315.
schedule_inequality = spread (std / max-min) of SFT across the 90 team-seasons.

Reads schedule_density.json (committed). edge_claimed=False -- a DESCRIPTIVE
points tax, not a forecast; the anchor is single-corpus CONFIRMED_LOCAL.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_schedule_fatigue_tax
    python -m scripts.platformkit.analytics_showcase.novel_schedule_fatigue_tax --check
"""
import json
import os
import re
import statistics

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "schedule_density.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_schedule_fatigue_tax.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_schedule_fatigue_tax.png")

PRIOR_ART_VERDICT = "INCREMENTAL"
PRIOR_ART_CITATION = (
    "The b2b fatigue effect is heavily documented (3-5% scoring drop / 1-3 pts / ~44% win "
    "rate / 2-4 pt spread adjust; academic 'Basketball performance affected by schedule "
    "congestion', ResearchGate 339933590). CITE the effect as prior art. The per-team-season "
    "aggregation into a points 'tax' plus a league schedule-inequality spread, anchored to the "
    "repo's own tested b2b_rest_penalty receipt, is the fresh packaging -- the effect is not new."
)
DECLARED_CONFOUNDS = [
    "per-36 deltas are raw pooled means, NOT roster/opponent/minutes/home-away adjusted.",
    "the three density classes (b2b, 3in4, 4in6) OVERLAP and are NON-additive; this formula "
    "deliberately uses b2b alone -- summing b2b+3in4+4in6 would double-count congestion.",
    "the -1.73 pts/100 anchor is a single-corpus CONFIRMED_LOCAL effect: a DESCRIPTIVE tax, "
    "not a forecast, and not re-tested here.",
    "b2b_ortg_effect sign is normalized to a fatigue penalty (negative), matching the negative "
    "composite_per36 delta and the mechanism framing; the receipt labels its magnitude 'rested minus b2b'.",
]


def _first_float(s):
    m = re.search(r"[-+]?\d+\.?\d*", s or "")
    return float(m.group()) if m else None


def build():
    src = json.loads(open(IN_JSON, encoding="utf-8").read())
    receipt = src.get("mechanism_receipt", {})
    anchor = _first_float(receipt.get("effect_cited_from_receipt", ""))
    assert anchor is not None, "could not parse b2b ORtg anchor from receipt"
    b2b_ortg_effect = -abs(anchor)  # fatigue penalty, sign-normalized negative
    composite_delta = src["per36_deltas"]["b2b"]["composite_per36_delta_vs_rested"]

    rows = []
    for r in src.get("per_team_season_frequencies", []):
        freq = r.get("b2b_freq")
        if freq is None:
            continue
        rows.append({
            "team": r["team"],
            "season": r["season"],
            "b2b_games": r.get("b2b_games"),
            "b2b_freq": freq,
            "sft_descriptive_composite_per36": round(freq * composite_delta, 4),
            "sft_credible_pts_per100_ortg": round(freq * b2b_ortg_effect, 4),
        })
    rows.sort(key=lambda x: x["sft_credible_pts_per100_ortg"])  # most-taxed (most negative) first

    sfts = [x["sft_credible_pts_per100_ortg"] for x in rows]
    freqs = [x["b2b_freq"] for x in rows]
    inequality = {
        "n_team_seasons": len(rows),
        "sft_credible_min": round(min(sfts), 4),
        "sft_credible_max": round(max(sfts), 4),
        "sft_credible_range": round(max(sfts) - min(sfts), 4),
        "sft_credible_std": round(statistics.pstdev(sfts), 4) if len(sfts) > 1 else 0.0,
        "b2b_freq_min": round(min(freqs), 4),
        "b2b_freq_max": round(max(freqs), 4),
        "per_season_b2b_freq_range": _per_season_spread(rows),
    }

    payload = {
        "stat_name": "Schedule Fatigue Tax",
        "abbrev": "SFT",
        "edge_claimed": False,
        "descriptive_only": True,
        "metric_definition": "Per team-season points tax from back-to-back congestion: its b2b frequency times the tested b2b performance penalty.",
        "formula": "SFT_credible = b2b_freq * (-1.73 pts/100 ORtg); SFT_descriptive = b2b_freq * (-0.315 composite/36).",
        "source_artifacts": [os.path.relpath(IN_JSON, ROOT).replace("\\", "/")],
        "b2b_ortg_effect_pts_per100": b2b_ortg_effect,
        "composite_per36_delta_vs_rested": composite_delta,
        "mechanism_receipt": {
            "claim": receipt.get("claim"),
            "verdict": receipt.get("verdict"),
            "effect_cited_from_receipt": receipt.get("effect_cited_from_receipt"),
        },
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "schedule_inequality": inequality,
        "results": rows,
        "headline": _headline(rows, inequality),
        "index_card": None,
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _per_season_spread(rows):
    by = {}
    for r in rows:
        by.setdefault(r["season"], []).append(r["b2b_freq"])
    return {s: round(max(v) - min(v), 4) for s, v in sorted(by.items())}


def _headline(rows, ineq):
    if not rows:
        return "No team-season frequencies available."
    worst = rows[0]
    best = rows[-1]
    return (f"Most-taxed schedule: {worst['team']} {worst['season']} "
            f"({worst['sft_credible_pts_per100_ortg']:.2f} pts/100 ORtg season-averaged); "
            f"least: {best['team']} {best['season']} ({best['sft_credible_pts_per100_ortg']:.2f}). "
            f"League schedule-inequality range {ineq['sft_credible_range']:.2f} pts/100 across "
            f"{ineq['n_team_seasons']} team-seasons.")


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_schedule_fatigue_tax",
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
    rows = payload["results"][:15]  # top-15 most-taxed
    if not rows:
        return False
    labels = [f"{r['team']} {r['season']}" for r in rows]
    vals = [r["sft_credible_pts_per100_ortg"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.45 * len(rows))))
    y = range(len(rows))
    ax.barh(list(y), vals, color="#b7791f")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("SFT (pts/100 ORtg, season-averaged; more negative = heavier fatigue tax)")
    ax.set_title("Schedule Fatigue Tax -- top 15 most-taxed team-seasons\n"
                 "DESCRIPTIVE_ONLY, anchor = CONFIRMED_LOCAL b2b receipt. edge_claimed=False", fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["results"], "no team-season rows"
    assert d["b2b_ortg_effect_pts_per100"] < 0


def check():
    if not os.path.exists(IN_JSON):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_schedule_fatigue_tax")
        return
    payload = build()
    _validate(payload)
    atl = next((r for r in payload["results"] if r["team"] == "ATL" and r["season"] == "2023-24"), None)
    assert atl is not None and abs(atl["b2b_freq"] - 0.183) < 1e-6, atl
    # 0.183 * -1.73 = -0.31659
    assert abs(atl["sft_credible_pts_per100_ortg"] - (-0.3166)) < 1e-3, atl
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_schedule_fatigue_tax ({len(payload['results'])} team-seasons, "
          f"ATL 23-24 SFT {atl['sft_credible_pts_per100_ortg']:.3f}, plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"], "schedule_inequality": p["schedule_inequality"],
                          "top5_taxed": p["results"][:5]}, indent=2))
