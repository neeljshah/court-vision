"""Calibration by market type: which market families can we actually SCORE?

Compares calibration across market TYPES, not just sports. LABELED moneyline /
game-winner markets from the joined grade corpora carry a resolved `outcome`, so
we score model AND market Brier (+ 10-bin ECE) per type. The UNLABELED in-game
TOTALS quote-tracks rescued from the pod carry no resolved outcome (live captures
taken before the total settled), so we DISCLOSE that -- n + model-vs-market
divergence only -- and never fabricate a Brier. The honest point: the scoreboard
can only score market types whose corpora carry resolved labels.

Scope: MLB moneyline, soccer match-result (2-way as graded), MLB totals.
Floors (declared, not tuned): a LABELED type reports Brier/ECE only at n>=MIN_N
(30); ECE = n-weighted |mean_p-mean_y| over N_BINS (10) bins; mlb_clean byte-dup
excluded; divergence = abs(model_prob-market_prob) per row is a calibration-GAP
MEASUREMENT, not an edge. edge_claimed=False. DESCRIPTIVE_ONLY.
Truth source: docs/JOB_EVIDENCE_PACKET.md.
Run: python -m scripts.platformkit.analytics_showcase.calibration_by_market_type [--check]
"""
import argparse
import glob
import json
import os
import statistics as stats

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import load_records
except ImportError:  # pragma: no cover - bare-script invocation
    from state_conditioned_calibration import load_records

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "calibration_by_market_type.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "calibration_by_market_type.png")
DERIV_DIR = os.path.join(REPO_ROOT, "data", "pod_backup_2026_07_20", "ingame_grade_deriv", "mlb")

MIN_N = 30
N_BINS = 10
FLOORS = (
    "labeled market type needs n>=30 usable rows for a Brier/ECE; ECE=n-weighted "
    "|mean_p-mean_y| over 10 bins; mlb_clean byte-dup excluded; edge_claimed=False"
)

# LABELED (joined corpus, has resolved outcome): key -> (sport dir, description)
LABELED = {
    "mlb_moneyline": ("mlb", "MLB in-game moneyline (game winner)"),
    "soccer_match": ("soccer_intl", "soccer in-game match result (2-way, as graded)"),
}
# UNLABELED (rescued live quote-tracks, no outcome): key -> (deriv dir, description)
UNLABELED = {"mlb_total": (DERIV_DIR, "MLB in-game over/under run total (Kalshi KXMLBTOTAL quote-tracks)")}


def brier(pairs):
    """Mean squared error of prob vs 0/1 outcome. pairs = [(p, y), ...]."""
    n = len(pairs)
    return sum((p - y) ** 2 for p, y in pairs) / n if n else None


def ece_10bin(pairs):
    """n-weighted |mean_p - mean_y| over N_BINS equal-width bins (calibration,
    not accuracy). Returns None on empty input."""
    n = len(pairs)
    if n == 0:
        return None
    tot = 0.0
    for k in range(N_BINS):
        lo, hi = k / N_BINS, (k + 1) / N_BINS
        b = [(p, y) for p, y in pairs if (lo <= p < hi) or (k == N_BINS - 1 and p == 1.0)]
        if not b:
            continue
        mp = sum(p for p, _ in b) / len(b)
        my = sum(y for _, y in b) / len(b)
        tot += (len(b) / n) * abs(mp - my)
    return round(tot, 6)


def score_labeled(sport):
    """Score one moneyline market type. Reuses load_records (JSONL rows) and
    keeps ONLY (model_prob, market_prob, outcome) per row -- the JSONL analog
    of a column-selective read. Returns a per-market-type dict or a skip dict."""
    files, recs = load_records(sport)
    if not files:
        return {"has_outcome": True, "scored": False, "reason": "no jsonl files found"}
    model_pairs, market_pairs = [], []
    n_no_outcome = 0
    for r in recs:
        y = r.get("outcome")
        if y is None:
            n_no_outcome += 1
            continue
        mp, kp = r.get("model_prob"), r.get("market_prob")
        if mp is not None:
            model_pairs.append((mp, y))
        if kp is not None:
            market_pairs.append((kp, y))
    n = len(model_pairs)
    out = {
        "has_outcome": True,
        "n_files": len(files),
        "n_rows": len(recs),
        "n_usable_model": n,
        "n_usable_market": len(market_pairs),
        "n_rows_missing_outcome": n_no_outcome,
    }
    if n < MIN_N:
        out.update(scored=False, reason=f"n<{MIN_N} usable rows")
        return out
    mb, kb = brier(model_pairs), brier(market_pairs)
    out.update(
        scored=True,
        model_brier=round(mb, 6) if mb is not None else None,
        market_brier=round(kb, 6) if kb is not None else None,
        model_ece=ece_10bin(model_pairs),
        market_ece=ece_10bin(market_pairs),
        brier_gap_model_minus_market=round(mb - kb, 6) if (mb is not None and kb is not None) else None,
    )
    return out


def measure_unlabeled(deriv_dir, desc):
    """Read totals quote-tracks column-selectively (market_prob/model_prob/line/
    side only). No resolved outcome exists, so report n + model-vs-market
    divergence and disclose that Brier is NOT scorable -- never fabricate one."""
    out = {"has_outcome": False, "description": desc, "scored": False,
           "reason": "no resolved outcome label on rescued live quote-tracks (settlement join unavailable)"}
    if not os.path.isdir(deriv_dir):
        out["reason"] = f"deriv dir absent: {deriv_dir}"
        return out
    files = sorted(glob.glob(os.path.join(deriv_dir, "*.jsonl")))
    if not files:
        out["reason"] = "no *.jsonl quote-track files found"
        return out
    tracks = set()          # (file, line, side)
    divergences = []
    n_rows = 0
    for fp in files:
        fn = os.path.basename(fp)
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n_rows += 1
                tracks.add((fn, r.get("line"), r.get("side")))
                mp, kp = r.get("model_prob"), r.get("market_prob")
                if mp is not None and kp is not None:
                    divergences.append(abs(mp - kp))
    out.update(
        n_files=len(files),
        n_rows=n_rows,
        n_quote_tracks=len(tracks),
        model_vs_market_divergence={
            "n": len(divergences),
            "median": round(stats.median(divergences), 6) if divergences else None,
            "mean": round(stats.mean(divergences), 6) if divergences else None,
            "p90": round(sorted(divergences)[min(len(divergences) - 1, int(round(0.9 * (len(divergences) - 1))))], 6) if divergences else None,
            "note": "abs(model_prob - market_prob) per tick -- a calibration-GAP MEASUREMENT, not an edge",
        },
        brier=None,
        brier_disclosure="Brier is NULL by design: these rows have no resolved outcome; scoring would require fabricating labels.",
    )
    return out


def make_chart(market_types):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labeled = [(k, v) for k, v in market_types.items() if v.get("has_outcome") and v.get("scored")]
    unlabeled = [(k, v) for k, v in market_types.items() if not v.get("has_outcome")]
    order = labeled + unlabeled
    keys = [k for k, _ in order]

    briers = [v.get("model_brier") or 0 for _, v in labeled] + [v.get("market_brier") or 0 for _, v in labeled]
    ymax = max(briers + [0.25]) * 1.5

    fig, ax = plt.subplots(figsize=(9, 5))
    w = 0.35
    for i, (_, v) in enumerate(labeled):
        ax.bar(i - w / 2, v.get("model_brier") or 0, w, color="#4C72B0", label="model Brier" if i == 0 else None)
        ax.bar(i + w / 2, v.get("market_brier") or 0, w, color="#DD8452", label="market Brier" if i == 0 else None)
        ax.text(i - w / 2, (v.get("model_brier") or 0) + ymax * 0.01, f"{v.get('model_brier'):.4f}\nn={v['n_usable_model']}", ha="center", va="bottom", fontsize=7)
        ax.text(i + w / 2, (v.get("market_brier") or 0) + ymax * 0.01, f"{v.get('market_brier'):.4f}", ha="center", va="bottom", fontsize=7)

    for j, (_, v) in enumerate(unlabeled):
        x = len(labeled) + j
        ax.bar(x, ymax, w * 2.4, color="#cccccc", hatch="//", edgecolor="#888888", alpha=0.55)
        div = v.get("model_vs_market_divergence", {}) or {}
        ax.text(x, ymax * 0.5,
                f"NO RESOLVED\nOUTCOMES\n(not scorable)\nn={v.get('n_rows', 0)} rows\ndivergence\nmedian={div.get('median')}",
                ha="center", va="center", fontsize=7.5, color="#333333")

    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(keys, fontsize=9)
    ax.set_ylabel("Brier (lower = better)")
    ax.set_ylim(0, ymax)
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title("Calibration by market type -- Brier where outcomes exist; totals disclosed as unlabeled", fontsize=10)
    fig.text(0.5, 0.005,
             "LABELED src: data/cache/ingame_grade_joined/{mlb,soccer_intl} (resolved outcome). "
             "UNLABELED src: data/pod_backup_2026_07_20/ingame_grade_deriv/mlb (KXMLBTOTAL, no outcome). "
             "DESCRIPTIVE_ONLY, edge_claimed=False. Truth source: docs/JOB_EVIDENCE_PACKET.md.",
             ha="center", fontsize=6.2, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)


def build_verdict(market_types):
    scored = [(k, v) for k, v in market_types.items() if v.get("scored")]
    unscored = [k for k, v in market_types.items() if not v.get("scored")]
    parts = []
    for k, v in scored:
        parts.append(f"{k}: model Brier {v['model_brier']:.4f} vs market {v['market_brier']:.4f} (n={v['n_usable_model']})")
    tail = f" Unscorable market types (no resolved outcome, disclosed not fabricated): {', '.join(unscored)}." if unscored else ""
    return ("Brier scored only for market types whose corpora carry resolved outcomes: "
            + "; ".join(parts) + "." + tail) if parts else ("No market type met the n floor." + tail)


def run():
    result = {
        "edge_claimed": False,
        "descriptive_only": True,
        "story": (
            "Calibration comparison across market TYPES. Moneyline/game-winner corpora carry "
            "resolved outcomes -> model and market Brier scored per type. The rescued in-game "
            "TOTALS quote-tracks carry NO resolved outcome -> disclosed as unscorable "
            "(n + model-vs-market divergence only), never a fabricated Brier."
        ),
        "floors": FLOORS,
        "min_n": MIN_N,
        "n_bins": N_BINS,
        "market_types": {},
        "skipped": [{"market_type": "mlb_clean_moneyline",
                     "reason": "mlb_clean is a byte-identical duplicate of mlb -- excluded to avoid double counting"}],
        "source_artifacts": {
            "labeled": "data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl",
            "unlabeled": "data/pod_backup_2026_07_20/ingame_grade_deriv/mlb/*.jsonl",
        },
        "truth_source": "docs/JOB_EVIDENCE_PACKET.md",
    }

    for key, (sport, desc) in LABELED.items():
        d = score_labeled(sport)
        d["description"] = desc
        result["market_types"][key] = d
    for key, (deriv_dir, desc) in UNLABELED.items():
        result["market_types"][key] = measure_unlabeled(deriv_dir, desc)

    result["verdict"] = build_verdict(result["market_types"])

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if any(v.get("scored") for v in result["market_types"].values()):
        make_chart(result["market_types"])
        result["plot_written"] = True
    else:
        result["plot_written"] = False
        result["png_skipped_reason"] = "no labeled market type met the n floor"
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    assert brier([(1.0, 1.0), (0.0, 0.0)]) == 0.0  # perfect predictor -> Brier 0
    assert ece_10bin([(0.5, 1.0), (0.5, 0.0)]) == 0.0  # bin mean_p 0.5 == mean_y 0.5
    result = run()
    assert os.path.exists(OUT_JSON) and os.path.getsize(OUT_JSON) > 0, OUT_JSON
    mt = result["market_types"]
    assert mt, "no market types produced"
    scored = [v for v in mt.values() if v.get("scored")]
    assert scored, "expected at least one scored (labeled) market type"
    for v in scored:
        assert v["n_usable_model"] > 0
        assert 0.0 < v["model_brier"] < 1.0, v["model_brier"]
    for k in UNLABELED:  # honest no-outcome disclosure must hold for every unlabeled type
        assert mt[k]["has_outcome"] is False and mt[k].get("brier") is None, mt[k]
    if result["plot_written"]:
        assert os.path.exists(OUT_PNG) and os.path.getsize(OUT_PNG) > 0, OUT_PNG
    print("OK: calibration_by_market_type self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        summ = {k: {x: v[x] for x in ("has_outcome", "scored", "model_brier", "market_brier", "n_usable_model", "n_rows") if x in v} for k, v in res["market_types"].items()}
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"], "market_types": summ}, indent=2))
