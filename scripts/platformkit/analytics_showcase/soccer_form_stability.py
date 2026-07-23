"""soccer_form_stability.py -- soccer_intl team-form rank stability (DESCRIPTIVE_ONLY).

SCOPE: reads two soccer_intl team-form CLAIM STORES in data/cache/intel_claims/
(read-only; only team+value pulled per ranking entry): soccer_intl_form_claims.jsonl
(trailing-10 form win-rate, ONE as-of snapshot per national team) and
soccer_intl_strength_claims.jsonl (walk-forward net-xG EW strength gf_ew-ga_ew,
ONE as-of snapshot). Question: does a team's short-horizon FORM track its
longer-horizon STRENGTH -- is the ordering stable across two independent lenses?
A parallel-forms rank-stability (convergent-validity) read: tie-corrected Spearman
rho + Pearson r over the shared, above-floor team population.

NOT SUPPORTED (reported, never faked): a TRUE within-season temporal split-half
(first-half vs second-half form) needs per-team form at >=2 disjoint chronological
windows. Each store holds only ONE as-of snapshot (verified: 1 claim line each), so
temporal_split_half is emitted status=NOT_AVAILABLE_IN_STORE with fields_needed.

FLOORS (declared): inherits each claim's min_sample n_matches>=200 (below-floor
teams pre-excluded upstream, never re-added); MIN_OVERLAP=30 (<30 shared teams ->
degrade, no correlation/chart); upstream form win-rate is quantized to 1 decimal ->
heavy ties -> tie_fraction reported as attenuation caveat + average-rank Spearman.

DESCRIPTIVE_ONLY, edge_claimed=False: NOT a predictor -- soccer_intl PREDICTIVE gate
is CLOSED upstream (NO_ADD_BEYOND_MARKET). No market/$/ROI edge. Truth source:
docs/JOB_EVIDENCE_PACKET.md.

Output: out/soccer_form_stability.json + ONE chart docs/img/soccer_form_stability.png
Usage:
    python -m scripts.platformkit.analytics_showcase.soccer_form_stability
    python -m scripts.platformkit.analytics_showcase.soccer_form_stability --check
"""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
OUT_JSON = os.path.join(HERE, "out", "soccer_form_stability.json")
OUT_PNG = os.path.join(REPO, "docs", "img", "soccer_form_stability.png")

FORM_FAMILY = "soccer_intl_form_claims"
STRENGTH_FAMILY = "soccer_intl_strength_claims"
MIN_OVERLAP = 30

FIELDS_NEEDED_FOR_TEMPORAL_SPLIT = [
    "per-team form at >=2 disjoint chronological windows in one season (e.g. first-half vs second-half), OR",
    "a per-team match-level result series with dates so windows can be cut here "
    "(store exposes only one as-of ranking vector per metric).",
]


def _avg_ranks(vals):
    """1-based average ranks; tied values share the mean of their rank block."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def spearman(xs, ys):
    """Tie-corrected Spearman rho = Pearson on average ranks."""
    return _pearson(_avg_ranks(xs), _avg_ranks(ys))


def find_corpus_dir():
    tried = []
    for rel in ("data/cache/intel_claims",):
        p = os.path.join(REPO, rel)
        tried.append(p)
        if os.path.isdir(p):
            return p, tried
    return None, tried


def _verdict_summary(corpus_dir, family):
    """Provenance: verified/mismatch counts from the *_validation.json sidecar."""
    sidecar = os.path.join(corpus_dir, family + "_validation.json")
    if not os.path.isfile(sidecar):
        return None
    try:
        vd = json.load(open(sidecar, "r", encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "sidecar_unreadable"}
    return {"n_claims": vd.get("n_claims"), "n_verified": vd.get("n_verified"),
            "n_mismatch": vd.get("n_mismatch"), "edge_claimed": vd.get("edge_claimed")}


def load_claim(corpus_dir, family):
    """Read the single claim line; return (meta, {team: value}). None if absent/empty.

    Column-selective: only `team` and `value` are extracted per ranking entry.
    """
    path = os.path.join(corpus_dir, family + ".jsonl")
    if not os.path.isfile(path):
        return None
    obj = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                break
    if obj is None:
        return None
    vals = {}
    for e in obj.get("ranking") or []:
        team = e.get("team") or e.get("entity_name") or e.get("entity_id")
        if team is None or e.get("value") is None:
            continue
        vals[team] = float(e["value"])
    crit = obj.get("criteria") or {}
    meta = {
        "claim_id": obj.get("claim_id"),
        "metric": crit.get("metric"),
        "window": crit.get("window"),
        "min_sample": crit.get("min_sample"),
        "n_considered": obj.get("n_considered"),
        "n_excluded_below_floor": obj.get("n_excluded_below_floor"),
        "n_ranked": len(vals),
        "validation": _verdict_summary(corpus_dir, family),
    }
    return meta, vals


def build():
    now = datetime.now(timezone.utc).isoformat()
    base = {
        "component": "soccer_form_stability",
        "mode": "DESCRIPTIVE_ONLY",
        "edge_claimed": False,
        "generated_at": now,
        "floors": {
            "inherited_min_sample": "n_matches>=200 (per upstream claim; below-floor teams pre-excluded)",
            "min_overlap": MIN_OVERLAP,
        },
        "truth_source": "docs/JOB_EVIDENCE_PACKET.md",
        # Permanent property of these single-snapshot stores -- always reported.
        "temporal_split_half": {
            "status": "NOT_AVAILABLE_IN_STORE",
            "reason": "each claim store holds ONE as-of ranking vector per metric "
                      "(form=trailing_10_asof_corpus_end, strength=asof_2026-06-28); "
                      "no within-season time series to cut into halves.",
            "fields_needed": FIELDS_NEEDED_FOR_TEMPORAL_SPLIT,
        },
    }

    corpus_dir, tried = find_corpus_dir()
    if corpus_dir is None:
        base["status"] = "no_data"
        base["paths_tried"] = tried
        return base

    form = load_claim(corpus_dir, FORM_FAMILY)
    strength = load_claim(corpus_dir, STRENGTH_FAMILY)
    missing = [fam for fam, got in ((FORM_FAMILY, form), (STRENGTH_FAMILY, strength)) if got is None]
    if missing:
        base["status"] = "no_data"
        base["missing_families"] = missing
        base["corpus_dir"] = os.path.relpath(corpus_dir, REPO).replace("\\", "/")
        return base

    form_meta, form_vals = form
    strength_meta, strength_vals = strength
    base["sources"] = {"form": form_meta, "strength": strength_meta}

    common = sorted(set(form_vals) & set(strength_vals))
    n_overlap = len(common)
    if n_overlap < MIN_OVERLAP:
        base["status"] = "insufficient_overlap"
        base["concordance"] = {"n_overlap": n_overlap, "min_overlap": MIN_OVERLAP}
        return base

    xs = [form_vals[t] for t in common]      # trailing-10 form win-rate
    ys = [strength_vals[t] for t in common]  # net-xG EW strength
    rho = spearman(xs, ys)
    r = _pearson(xs, ys)
    tie_frac_form = round(1.0 - len(set(xs)) / len(xs), 4)
    tie_frac_strength = round(1.0 - len(set(ys)) / len(ys), 4)

    base["status"] = "ok"
    base["corpus_dir"] = os.path.relpath(corpus_dir, REPO).replace("\\", "/")
    base["concordance"] = {
        "measure": "cross-lens rank stability (parallel-forms): trailing-10 form "
                   "win-rate vs net-xG EW strength, shared above-floor national teams",
        "n_overlap": n_overlap,
        "n_form_only": len(set(form_vals) - set(strength_vals)),
        "n_strength_only": len(set(strength_vals) - set(form_vals)),
        "spearman_rho": round(rho, 4) if rho is not None else None,
        "pearson_r": round(r, 4) if r is not None else None,
        "tie_fraction_form": tie_frac_form,
        "tie_fraction_strength": tie_frac_strength,
        "points": [{"team": t, "form": form_vals[t], "strength": strength_vals[t]} for t in common],
    }
    base["caveats"] = [
        "DESCRIPTIVE cross-lens rank concordance only -- NOT a temporal split-half "
        "and NOT a predictor of any future match; soccer_intl PREDICTIVE gate is "
        "CLOSED upstream (NO_ADD_BEYOND_MARKET). No market/$/ROI edge claimed.",
        "The two lenses differ in horizon (form=trailing 10 matches; strength=full EW "
        "history) -- read the correlation as convergent validity, not pure persistence.",
        "Upstream form win-rate is quantized to 1 decimal (tie_fraction_form=%s) -> "
        "inflates ties + ATTENUATES rho toward 0; reported rho is tie-corrected (average-rank)." % tie_frac_form,
    ]
    base["honest_note"] = (
        "n=%d shared national teams. Spearman rho=%s, Pearson r=%s between trailing-10 "
        "form win-rate and net-xG strength -- a parallel-forms rank-stability read, "
        "NOT a temporal split-half (that series is absent from the store) and NOT a "
        "predictor. edge_claimed=False."
        % (n_overlap, base["concordance"]["spearman_rho"], base["concordance"]["pearson_r"])
    )
    return base


def make_plot(result, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    c = result["concordance"]
    xs = [p["form"] for p in c["points"]]
    ys = [p["strength"] for p in c["points"]]
    rho = c["spearman_rho"]
    r = c["pearson_r"]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(xs, ys, s=24, color="#2b7a78", alpha=0.75, edgecolor="white", linewidth=0.4)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_xlabel("trailing-10 form win-rate  (as-of corpus end; quantized to 0.1)")
    ax.set_ylabel("net-xG EW strength  gf_ew - ga_ew  (as-of 2026-06-28)")
    ax.set_title("soccer_intl form vs strength -- cross-lens rank concordance\n"
                 "Spearman rho=%s   Pearson r=%s   n=%d teams   (DESCRIPTIVE, edge_claimed=False)"
                 % (rho, r, c["n_overlap"]), fontsize=10)
    fig.text(0.5, 0.005,
             "Two independent as-of lenses on the SAME national-team population -- a parallel-forms "
             "rank-stability read, NOT a temporal split-half and NOT a predictor. "
             "Source: data/cache/intel_claims/soccer_intl_{form,strength}_claims.jsonl",
             ha="center", fontsize=6.5, color="gray", wrap=True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return True


def main():
    result = build()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    if result["status"] == "ok":
        result["plot_written"] = make_plot(result, OUT_PNG)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("wrote %s" % OUT_JSON)
        print("wrote %s (plot_written=%s)" % (OUT_PNG, result["plot_written"]))
        print(result["honest_note"])
    else:
        print("status=%s -- %s" % (result["status"], OUT_JSON))
        print("temporal_split_half=%s" % result["temporal_split_half"]["status"])


def check():
    """Runnable guards: math sanity + outputs nonzero."""
    # tie-corrected Spearman sanity: monotone -> +1, reversed -> -1, ties handled.
    assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-9
    assert abs(_avg_ranks([5, 5, 9])[0] - 1.5) < 1e-9  # tie block shares mean rank
    assert os.path.exists(OUT_JSON) and os.path.getsize(OUT_JSON) > 0, OUT_JSON
    res = json.load(open(OUT_JSON, "r", encoding="utf-8"))
    assert res.get("temporal_split_half", {}).get("status") == "NOT_AVAILABLE_IN_STORE"
    if res.get("status") == "ok":
        assert res["concordance"]["n_overlap"] >= MIN_OVERLAP, res["concordance"]["n_overlap"]
        assert res["concordance"]["spearman_rho"] is not None
        assert os.path.exists(OUT_PNG) and os.path.getsize(OUT_PNG) > 0, OUT_PNG
    print("OK: soccer_form_stability self-check passed (status=%s)" % res.get("status"))


if __name__ == "__main__":
    check() if "--check" in sys.argv else main()
