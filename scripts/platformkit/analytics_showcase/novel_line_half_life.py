"""Novel stat #1 -- Line Half-Life.

METRIC: one interpretable per-sport constant -- "half of a sport's pre-game line
motion is complete by X hours before tip." Computed from our own scraped
pre-game line-history absorption instrument (micro_absorption.json).

FORMULA:
    bucket_move(b) = n(b) * mean_abs_move(b)   over the 4 horizon buckets
                     (6h+, 3-6h, 1-3h, 0-1h)
    total          = sum of the four bucket_move(b)
    G(h)           = cumulative bucket_move at MORE than h hours before tip,
                     as a fraction of total, cumulated far->near
    half_life      = the hours-to-tip h at which G(h) crosses 0.50
                     (linear interpolation between the two bracketing bucket
                     boundaries: 6h, 3h, 1h, 0h)

Reads only micro_absorption.json (a committed artifact); computes the derived
half-life. edge_claimed=False -- descriptive line-timing, no $/ROI claim.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_line_half_life
    python -m scripts.platformkit.analytics_showcase.novel_line_half_life --check
"""
import json
import os

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "micro_absorption.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_line_half_life.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_line_half_life.png")

# far->near boundaries in hours-to-tip; each bucket spans [near, far)
BUCKET_ORDER = ["6h+", "3-6h", "1-3h", "0-1h"]
BOUNDARY_H = {"6h+": 6.0, "3-6h": 3.0, "1-3h": 1.0, "0-1h": 0.0}
# soccer is a known timestamp-coverage artifact (all mass in 6h+, mean_abs_move 0.0)
EXCLUDE_SPORTS = {"soccer"}

PRIOR_ART_VERDICT = "NOVEL_PACKAGING"
PRIOR_ART_CITATION = (
    "Line-movement timing (early-sharp vs late-injury/public money) is discussed "
    "qualitatively everywhere (Boyd's Bets opening-vs-closing; PicksOffice; GamingToday); "
    "price-impact half-life is a securities-microstructure staple (Kyle 1985; Amihud 2002). "
    "The underlying line-movement concept is NOT new; only the single per-sport half-life "
    "constant is the fresh packaging."
)
DECLARED_CONFOUNDS = [
    "bucket_move sums ABSOLUTE per-tick moves -> this is churn/activity, not net price "
    "travel; back-and-forth noise and correlated consensus books inflate it.",
    "Only 4 coarse horizon buckets, so the 0.50 crossing is linearly interpolated.",
    "soccer EXCLUDED: all mass in the 6h+ bucket with mean_abs_move 0.0 (timestamp-coverage artifact).",
    "nba is bimodal (early motion + a real 0-1h spike, final_hour_share 0.3247) which a "
    "single half-life hides -- read alongside the final_hour_movement_share column.",
    "Sports whose crossing falls inside the open-ended 6h+ bucket cannot be pinned "
    "(reported as '>6h', half_life_hours=null).",
]


def _half_life(move_by_bucket):
    """Return (half_life_hours or None, crossing_in_open_bucket, cum_fractions)."""
    moves = {}
    for b in BUCKET_ORDER:
        cell = move_by_bucket.get(b) or {}
        n, mam = cell.get("n"), cell.get("mean_abs_move")
        if n is None or mam is None:
            return None, False, None  # incomplete -> not buildable
        moves[b] = n * mam
    total = sum(moves.values())
    if total <= 0:
        return None, False, None
    # cumulative far->near at each near-boundary of the buckets
    cum = 0.0
    cum_at = {}  # hours-to-tip boundary -> fraction completed by then
    for b in BUCKET_ORDER:
        cum += moves[b]
        cum_at[BOUNDARY_H[b]] = round(cum / total, 4)
    # G(6) = fraction done at >6h before tip == 6h+ bucket only
    g6 = moves["6h+"] / total
    if g6 >= 0.5:
        return None, True, cum_at  # crossing is earlier than 6h, open bucket
    # walk boundaries 6->3->1->0, find bracket where cumulative crosses 0.5
    prev_h, prev_c = 6.0, g6
    for b in ["3-6h", "1-3h", "0-1h"]:
        c = sum(moves[x] for x in BUCKET_ORDER[: BUCKET_ORDER.index(b) + 1]) / total
        h = BOUNDARY_H[b]
        if c >= 0.5:
            frac = (0.5 - prev_c) / (c - prev_c) if c != prev_c else 0.0
            hl = prev_h + frac * (h - prev_h)
            return round(hl, 4), False, cum_at
        prev_h, prev_c = h, c
    return round(BOUNDARY_H["0-1h"], 4), False, cum_at


def build():
    src = json.loads(open(IN_JSON, encoding="utf-8").read())
    rows = []
    excluded = []
    for sport, s in sorted(src.get("sports", {}).items()):
        if sport in EXCLUDE_SPORTS:
            excluded.append({"sport": sport, "reason": "timestamp-coverage artifact (all mass in 6h+, mean_abs_move 0.0)"})
            continue
        if s.get("status") != "ok":
            excluded.append({"sport": sport, "reason": s.get("reason", s.get("status", "not ok"))})
            continue
        hl, open_bucket, cum = _half_life(s.get("move_by_bucket", {}))
        if cum is None:
            excluded.append({"sport": sport, "reason": "incomplete horizon buckets"})
            continue
        rows.append({
            "sport": sport,
            "half_life_hours": hl,
            "crossing_in_open_bucket": open_bucket,
            "half_life_label": ">6.0" if open_bucket else f"{hl:.2f}",
            "final_hour_movement_share": s.get("final_hour_movement_share"),
            "total_abs_move": s.get("total_abs_move"),
            "cumulative_fraction_by_boundary_h": cum,
            "n_move_pairs": s.get("n_move_pairs"),
        })
    # rank: pinnable (finite) half-lives first ascending, then open-bucket (>6h) sports
    rows.sort(key=lambda r: (r["crossing_in_open_bucket"], r["half_life_hours"] if r["half_life_hours"] is not None else 999))

    payload = {
        "stat_name": "Line Half-Life",
        "abbrev": "LHL",
        "edge_claimed": False,
        "descriptive_only": True,
        "metric_definition": "Per sport, the number of hours before tip by which half of the pre-game absolute line motion is complete.",
        "formula": "bucket_move=n*mean_abs_move per horizon bucket; G(h)=cum far->near / total; half_life = h where G(h)=0.50 (interpolated).",
        "source_artifacts": [os.path.relpath(IN_JSON, ROOT).replace("\\", "/")],
        "as_of": src.get("as_of"),
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "results": rows,
        "excluded": excluded,
        "headline": _headline(rows),
        "index_card": None,  # filled below
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _headline(rows):
    finite = [r for r in rows if not r["crossing_in_open_bucket"]]
    if not finite:
        return "No sport had a pinnable half-life (all crossings in the open 6h+ bucket)."
    fast = min(finite, key=lambda r: r["half_life_hours"])
    slow = max(finite, key=lambda r: r["half_life_hours"])
    early = [r["sport"] for r in rows if r["crossing_in_open_bucket"]]
    tail = f" {', '.join(early)} move most of their line >6h before tip." if early else ""
    return (f"{fast['sport']} completes half its pre-game line motion by {fast['half_life_hours']:.1f}h "
            f"before tip; {slow['sport']} not until {slow['half_life_hours']:.1f}h.{tail}")


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_line_half_life",
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
    labels = [r["sport"] for r in rows]
    # open-bucket sports drawn at a capped 6.5h with a ">" annotation
    vals = [r["half_life_hours"] if not r["crossing_in_open_bucket"] else 6.5 for r in rows]
    colors = ["#c0392b" if r["crossing_in_open_bucket"] else "#2b6cb0" for r in rows]
    fig, ax = plt.subplots(figsize=(8, max(3, 0.55 * len(rows))))
    y = range(len(rows))
    ax.barh(list(y), vals, color=colors)
    for i, r in enumerate(rows):
        share = r.get("final_hour_movement_share")
        txt = (">6h" if r["crossing_in_open_bucket"] else f"{r['half_life_hours']:.2f}h")
        if share is not None:
            txt += f"  (final-hr {share:.0%})"
        ax.text(vals[i] + 0.08, i, txt, va="center", fontsize=8)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 7.4)
    ax.set_xlabel("hours before tip when half the pre-game line motion is done (higher = moves earlier)")
    ax.set_title("Line Half-Life by sport\nred = crossing in open 6h+ bucket (>6h). edge_claimed=False", fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["results"], "no half-life rows"
    for r in d["results"]:
        assert r["crossing_in_open_bucket"] or r["half_life_hours"] is not None


def check():
    if not os.path.exists(IN_JSON):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_line_half_life")
        return
    payload = build()
    _validate(payload)
    mlb = next((r for r in payload["results"] if r["sport"] == "mlb"), None)
    assert mlb is not None and mlb["half_life_hours"] is not None
    assert 3.4 < mlb["half_life_hours"] < 3.9, mlb["half_life_hours"]
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_line_half_life ({len(payload['results'])} sports, mlb half-life "
          f"{mlb['half_life_hours']:.2f}h, plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"], "results": p["results"], "excluded": p["excluded"]}, indent=2))
