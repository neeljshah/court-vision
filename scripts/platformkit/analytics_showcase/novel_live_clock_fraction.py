"""Novel stat #5 -- Live-Clock Fraction (LCF).

METRIC: one 0-1 axis per sport for "how long the game stays genuinely contested"
-- the fraction of the game clock that is still live before the score gap crosses
a point-of-no-return, at each sport's near-median decisive threshold. Paired with
comeback_rate as an independent decisiveness cross-check.

FORMULA (per sport):
    near-median threshold = the non-masked threshold whose decided_frac_of_games
                            is closest to 0.50
    LCF = decided_clockfrac_median at that threshold
          (the share of the clock elapsed when the gap becomes permanent; HIGHER
          = the game stays contested LATER)

ORIENTATION NOTE: the deliverable is a single 0-1 axis where higher = stays
contested later ("baseball stays contested later than soccer"). LCF is therefore
the decided_clockfrac_median directly -- the live/contested portion of the clock --
consistent with the metric name and headline. (A '1 - x' orientation would invert
the axis and contradict both.)

Reads blowout_dynamics.json + xsport_structure.json (committed). Buildable for
mlb + soccer_intl only; nba/tennis have no blowout corpus -> honest not_buildable.
edge_claimed=False -- descriptive game flow, no $/ROI claim.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_live_clock_fraction
    python -m scripts.platformkit.analytics_showcase.novel_live_clock_fraction --check
"""
import json
import os

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_BLOWOUT = os.path.join(SHOWCASE, "out", "blowout_dynamics.json")
IN_XSPORT = os.path.join(SHOWCASE, "out", "xsport_structure.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_live_clock_fraction.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_live_clock_fraction.png")

PRIOR_ART_VERDICT = "INCREMENTAL_NOVEL"
PRIOR_ART_CITATION = (
    "The within-sport method EXISTS: blowout_dynamics.json's own prior_art block cites Bill "
    "James safe-lead heuristics and win-probability clinch points ('Not a new method; do not "
    "claim first-ever'). Only the normalized cross-sport live-clock axis is the contribution."
)
DECLARED_CONFOUNDS = [
    "thresholds are NOT truly equated across sports (2 runs != any goal margin != any NBA "
    "margin) and clock units differ (innings vs minutes), so the cross-sport ranking is "
    "indicative, not metric.",
    "buildable for mlb + soccer_intl ONLY -- nba/tennis have no blowout corpus (honest not_buildable).",
    "the near-median threshold is chosen by proximity to 0.50 decided_frac_of_games; soccer_intl "
    "has only one non-masked threshold, so no choice is exercised there.",
]


def _pick_threshold(thresholds):
    """Non-masked threshold whose decided_frac_of_games is closest to 0.50."""
    usable = [t for t in thresholds if not t.get("masked_below_floor")
              and t.get("decided_clockfrac_median") is not None
              and t.get("decided_frac_of_games") is not None]
    if not usable:
        return None
    return min(usable, key=lambda t: abs(t["decided_frac_of_games"] - 0.5))


def build():
    blow = json.loads(open(IN_BLOWOUT, encoding="utf-8").read())
    xsp = json.loads(open(IN_XSPORT, encoding="utf-8").read())

    rows = []
    not_buildable = []
    for sport in ["mlb", "soccer_intl"]:
        s = blow.get("sports", {}).get(sport)
        if not s:
            not_buildable.append({"sport": sport, "reason": "absent from blowout_dynamics"})
            continue
        t = _pick_threshold(s.get("thresholds", []))
        if t is None:
            not_buildable.append({"sport": sport, "reason": "no non-masked threshold with a decided clock fraction"})
            continue
        rows.append({
            "sport": sport,
            "unit": s.get("unit"),
            "clock_field": s.get("clock_field"),
            "near_median_threshold": t["threshold"],
            "decided_frac_of_games": t["decided_frac_of_games"],
            "n_games_decided": t["n_games_decided"],
            "n_games_total": t.get("n_games_total"),
            "live_clock_fraction": t["decided_clockfrac_median"],
        })
    for sport in ["nba", "tennis"]:
        not_buildable.append({"sport": sport, "reason": "no blowout corpus"})
    rows.sort(key=lambda r: r["live_clock_fraction"], reverse=True)

    # companion decisiveness cross-check: nba comeback_rate (from xsport_structure)
    nba_cb = (xsp.get("sports", {}).get("nba", {}) or {}).get("comeback_proxy", {})
    companion = {
        "nba_comeback_rate": nba_cb.get("comeback_rate"),
        "nba_favorite_hold_rate": nba_cb.get("favorite_hold_rate"),
        "note": "independent decisiveness cross-check from xsport_structure; nba has no LCF (no blowout corpus).",
    }

    payload = {
        "stat_name": "Live-Clock Fraction",
        "abbrev": "LCF",
        "edge_claimed": False,
        "descriptive_only": True,
        "metric_definition": "The 0-1 share of a sport's game clock that stays genuinely contested before the score gap crosses a point-of-no-return (near-median threshold).",
        "formula": "LCF = decided_clockfrac_median at the non-masked threshold whose decided_frac_of_games is closest to 0.50 (higher = contested later).",
        "source_artifacts": [
            os.path.relpath(IN_BLOWOUT, ROOT).replace("\\", "/"),
            os.path.relpath(IN_XSPORT, ROOT).replace("\\", "/"),
        ],
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "results": rows,
        "not_buildable": not_buildable,
        "companion_cross_check": companion,
        "headline": _headline(rows, companion),
        "index_card": None,
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _headline(rows, companion):
    if len(rows) < 1:
        return "No sport had a buildable Live-Clock Fraction."
    if len(rows) >= 2:
        hi, lo = rows[0], rows[1]
        cb = companion.get("nba_comeback_rate")
        cbtxt = f" (nba comeback-rate cross-check {cb})" if cb is not None else ""
        return (f"{hi['sport']} stays contested later (LCF {hi['live_clock_fraction']:.3f}) than "
                f"{lo['sport']} (LCF {lo['live_clock_fraction']:.3f}).{cbtxt}")
    r = rows[0]
    return f"{r['sport']} LCF {r['live_clock_fraction']:.3f} (only buildable sport)."


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_live_clock_fraction",
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
    rows = payload["results"]
    if not rows:
        return False
    labels = [f"{r['sport']}\n(thr {r['near_median_threshold']} {r['unit']})" for r in rows]
    vals = [r["live_clock_fraction"] for r in rows]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    x = range(len(rows))
    ax.bar(list(x), vals, color="#2b6cb0", width=0.55)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.01, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Live-Clock Fraction (higher = contested later)")
    ax.set_title("Live-Clock Fraction by sport\ncross-sport thresholds not equated -- indicative only. edge_claimed=False", fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["results"], "no LCF rows"
    for r in d["results"]:
        assert 0.0 <= r["live_clock_fraction"] <= 1.0


def check():
    if not (os.path.exists(IN_BLOWOUT) and os.path.exists(IN_XSPORT)):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_live_clock_fraction")
        return
    payload = build()
    _validate(payload)
    mlb = next((r for r in payload["results"] if r["sport"] == "mlb"), None)
    # mlb near-median threshold = 3 (decided_frac 0.5337), LCF = decided_clockfrac_median 0.8333
    assert mlb and mlb["near_median_threshold"] == 3 and abs(mlb["live_clock_fraction"] - 0.8333) < 1e-4, mlb
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_live_clock_fraction ({len(payload['results'])} sports buildable, "
          f"mlb LCF {mlb['live_clock_fraction']:.3f}, plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"], "results": p["results"],
                          "companion_cross_check": p["companion_cross_check"],
                          "not_buildable": p["not_buildable"]}, indent=2))
