"""Bootstrap CI bands on 10-bin reliability curves (model vs market).

Cluster-bootstraps the row-level joined grade corpora in
data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl to put a 95% CI on
every reliability-diagram bin, model side and market side. Per bin it answers:
is the gap between predicted and observed (mean_p vs mean_y) a REAL
miscalibration, or just sampling noise?

Why CLUSTER bootstrap (by game_id): one game contributes many autocorrelated
per-timestamp rows, so a naive row-level resample understates the CIs
(overconfident). The honest unit is the whole game -- draw games with
replacement and re-bin each resample; the test is conservative on purpose.
A bin is SIGNIFICANT only when it clears the games floor AND its gap CI
excludes 0. Expect several populated bins to LOSE significance (within noise);
the module prints whatever the bootstrap says.

Scope + floors (DESCRIPTIVE_ONLY, edge_claimed=False -- docs/JOB_EVIDENCE_PACKET.md):
  - Sports: mlb, soccer_intl (mlb_clean is a byte-identical dup, skipped).
  - 10 equal-width bins over [0,1). Cluster unit: game_id.
  - n_boot=1000, seed=20260722, CI = 95% percentile [2.5, 97.5].
  - A bin needs >= 5 contributing games to be significance-eligible; below that
    it is reported low_n and excluded from the tally. A sport under 30 games is
    flagged low_power. No $/ROI/edge claim -- calibration-uncertainty only.

atlas_factory note: its card family is for compact entity cards, not a
CI-ribbon reliability diagram, so -- like sibling murphy_decomposition.py on
the same corpora -- this module renders its own figure and does not import it.

Usage:
    python -m scripts.platformkit.analytics_showcase.calibration_stability
    python -m scripts.platformkit.analytics_showcase.calibration_stability --check
"""
import argparse
import glob
import json
import os
from datetime import datetime, timezone

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_DIR = os.path.join(REPO_ROOT, "data", "cache", "ingame_grade_joined")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "calibration_stability.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "calibration_stability.png")

SPORTS = ["mlb", "soccer_intl"]
SIDES = [("model_prob", "model"), ("market_prob", "market")]
N_BINS = 10
N_BOOT = 1000
SEED = 20260722
CI_LO, CI_HI = 2.5, 97.5
MIN_GAMES_PER_BIN = 5   # cluster-bootstrap significance eligibility floor
LOW_POWER_GAMES = 30    # below this the whole sport is flagged low_power


def load_sport(sport):
    """Column-selective jsonl read: keep only (game_id, model_prob, market_prob,
    outcome) per row; drop rows missing any of them. mlb_clean is not read."""
    gid, mp, kp, y = [], [], [], []
    for path in sorted(glob.glob(os.path.join(IN_DIR, sport, "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("model_prob") is None or r.get("market_prob") is None or r.get("outcome") is None:
                    continue
                gid.append(r.get("game_id", "?"))
                mp.append(r["model_prob"])
                kp.append(r["market_prob"])
                y.append(r["outcome"])
    return gid, np.asarray(mp, float), np.asarray(kp, float), np.asarray(y, float)


def bin_index(prob):
    """Map probs to 10 equal-width bins; p==1.0 folds into the top bin."""
    return np.clip((np.asarray(prob, float) * N_BINS).astype(int), 0, N_BINS - 1)


def aggregate_per_game(game_idx, bidx, prob, outcome, n_games):
    """Per-game per-bin (count, sum_p, sum_y) arrays, shape (n_games, N_BINS).
    Precomputing these lets each bootstrap resample be a cheap row-sum over
    sampled games instead of a re-scan of every row."""
    flat = game_idx * N_BINS + bidx
    size = n_games * N_BINS
    count = np.bincount(flat, minlength=size).reshape(n_games, N_BINS).astype(float)
    sump = np.bincount(flat, weights=prob, minlength=size).reshape(n_games, N_BINS)
    sumy = np.bincount(flat, weights=outcome, minlength=size).reshape(n_games, N_BINS)
    return count, sump, sumy


def _rates(C, SP, SY):
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_p = np.where(C > 0, SP / C, np.nan)
        mean_y = np.where(C > 0, SY / C, np.nan)
    return mean_p, mean_y


def bootstrap_side(count, sump, sumy, rng, n_boot):
    """Cluster bootstrap over games. Returns per-bin point estimates + the
    percentile CIs on observed rate (ribbon) and on the calibration gap."""
    G = count.shape[0]
    C0, SP0, SY0 = count.sum(0), sump.sum(0), sumy.sum(0)
    mean_p0, mean_y0 = _rates(C0, SP0, SY0)
    n_games_bin = (count > 0).sum(0)

    my = np.full((n_boot, N_BINS), np.nan)
    gp = np.full((n_boot, N_BINS), np.nan)
    for b in range(n_boot):
        gi = rng.integers(0, G, G)  # resample whole games with replacement
        Cb, SPb, SYb = count[gi].sum(0), sump[gi].sum(0), sumy[gi].sum(0)
        mpb, myb = _rates(Cb, SPb, SYb)
        my[b] = myb
        gp[b] = myb - mpb

    with np.errstate(invalid="ignore"):
        my_lo, my_hi = np.nanpercentile(my, [CI_LO, CI_HI], axis=0)
        gp_lo, gp_hi = np.nanpercentile(gp, [CI_LO, CI_HI], axis=0)
    return {
        "C0": C0, "mean_p0": mean_p0, "mean_y0": mean_y0, "gap0": mean_y0 - mean_p0,
        "n_games_bin": n_games_bin,
        "my_lo": my_lo, "my_hi": my_hi, "gp_lo": gp_lo, "gp_hi": gp_hi,
    }


def _f(x, nd=4):
    if x is None:
        return None
    x = float(x)
    return None if np.isnan(x) else round(x, nd)


def side_summary(res):
    """Turn per-bin arrays into serializable rows + significant/eligible tallies.
    Significant = eligible (>= floor games) AND gap CI excludes 0."""
    bins, n_elig, n_sig = [], 0, 0
    for k in range(N_BINS):
        C = int(res["C0"][k])
        ng = int(res["n_games_bin"][k])
        populated = C > 0
        eligible = populated and ng >= MIN_GAMES_PER_BIN
        gl, gh = res["gp_lo"][k], res["gp_hi"][k]
        sig = bool(eligible and not np.isnan(gl) and not np.isnan(gh) and (gl > 0 or gh < 0))
        if eligible:
            n_elig += 1
            n_sig += int(sig)
        bins.append({
            "bin_lo": round(k / N_BINS, 1), "bin_hi": round((k + 1) / N_BINS, 1), "n": C, "n_games": ng,
            "mean_p": _f(res["mean_p0"][k]), "mean_y": _f(res["mean_y0"][k]), "gap": _f(res["gap0"][k]),
            "mean_y_ci": [_f(res["my_lo"][k]), _f(res["my_hi"][k])], "gap_ci": [_f(gl), _f(gh)],
            "significant": sig, "low_n": bool(populated and not eligible),
        })
    return bins, n_elig, n_sig


def build_verdict(result):
    parts = []
    for sport, so in result.get("sports", {}).items():
        for _, sd in so["sides"].items():
            parts.append(
                f"{sport}/{sd['label']}: {sd['n_significant_bins']}/{sd['n_eligible_bins']} "
                f"eligible bins have a calibration-gap 95% CI that excludes 0; "
                f"{sd['n_within_noise_bins']} within noise."
            )
        if so.get("low_power"):
            parts.append(f"{sport}: only {so['n_games']} games -- low power, read all bins cautiously.")
    return " ".join(parts) if parts else "No sport had usable rows."


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    sports = [s for s in SPORTS if s in result["sports"]]
    if not sports:
        return False
    colors = {"model_prob": "#1f77b4", "market_prob": "#d62728"}
    fig, axes = plt.subplots(1, len(sports), figsize=(5.5 * len(sports), 5), squeeze=False)
    for ax, sport in zip(axes[0], sports):
        so = result["sports"][sport]
        for field, sd in so["sides"].items():
            b = [x for x in sd["bins"] if x["n"] > 0 and x["mean_p"] is not None]
            if not b:
                continue
            xs = [x["mean_p"] for x in b]
            ys = [x["mean_y"] for x in b]
            lo = [x["mean_y_ci"][0] for x in b]
            hi = [x["mean_y_ci"][1] for x in b]
            c = colors[field]
            ax.plot(xs, ys, "-", color=c, lw=1.2,
                    label=f"{sd['label']} (Brier={sd['brier']:.4f}, sig {sd['n_significant_bins']}/{sd['n_eligible_bins']})")
            ax.fill_between(xs, lo, hi, color=c, alpha=0.18)
            xa, ya, sa = np.array(xs), np.array(ys), np.array([x["significant"] for x in b], bool)
            ax.scatter(xa[sa], ya[sa], color=c, s=42, zorder=5, edgecolor="black", linewidth=0.5)
            ax.scatter(xa[~sa], ya[~sa], facecolor="white", edgecolor=c, s=36, zorder=5)
        ax.plot([0, 1], [0, 1], "--", color="gray", lw=1)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_title(f"{sport} (n_games={so['n_games']})")
        ax.set_xlabel("mean predicted prob (bin)")
        ax.legend(fontsize=7, loc="upper left")
    axes[0][0].set_ylabel("mean observed outcome (bin)")
    fig.suptitle("Reliability with 95% cluster-bootstrap CI ribbons: model vs market\n"
                 "filled marker = gap CI excludes 0 (significant); hollow = within noise", fontsize=10)
    fig.text(0.5, 0.005,
             f"source: data/cache/ingame_grade_joined/{{mlb,soccer_intl}} | cluster=game_id, "
             f"n_boot={N_BOOT}, seed={SEED}, floor>={MIN_GAMES_PER_BIN} games/bin | "
             f"DESCRIPTIVE_ONLY, edge_claimed=False", ha="center", fontsize=6.5, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=130)
    plt.close(fig)
    return True


def run():
    rng = np.random.default_rng(SEED)
    result = {
        "edge_claimed": False, "descriptive_only": True, "seed": SEED, "n_boot": N_BOOT,
        "ci_pct": [CI_LO, CI_HI], "cluster_unit": "game_id", "min_games_per_bin_floor": MIN_GAMES_PER_BIN,
        "method": "cluster bootstrap (resample game_id with replacement, re-bin) on 10-bin reliability curves",
        "source_artifact": "data/cache/ingame_grade_joined/{mlb,soccer_intl}",
        "as_of": datetime.now(timezone.utc).isoformat(), "sports": {},
        "skipped": [{"sport": "mlb_clean", "reason": "byte-identical duplicate of mlb corpus -- excluded to avoid double counting"}],
    }
    for sport in SPORTS:
        gids, mp, kp, y = load_sport(sport)
        if len(y) == 0:
            result["skipped"].append({"sport": sport, "reason": "no usable rows"})
            continue
        uniq = {g: i for i, g in enumerate(dict.fromkeys(gids))}
        gidx = np.fromiter((uniq[g] for g in gids), dtype=int, count=len(gids))
        G = len(uniq)
        sport_out = {"n_rows": int(len(y)), "n_games": G, "low_power": bool(G < LOW_POWER_GAMES), "sides": {}}
        for field, label in SIDES:
            prob = mp if field == "model_prob" else kp
            count, sump, sumy = aggregate_per_game(gidx, bin_index(prob), prob, y, G)
            bins, n_elig, n_sig = side_summary(bootstrap_side(count, sump, sumy, rng, N_BOOT))
            sport_out["sides"][field] = {
                "label": label,
                "brier": round(float(np.mean((prob - y) ** 2)), 6),
                "n_eligible_bins": n_elig, "n_significant_bins": n_sig,
                "n_within_noise_bins": n_elig - n_sig, "bins": bins,
            }
        result["sports"][sport] = sport_out

    result["verdict"] = build_verdict(result)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    result["plot_written"] = make_plot(result)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    """Self-check with a KNOWN answer, then assert the built outputs exist.
    Synthetic: bin ~0.9 = 40 one-row games, always outcome 0 -> gap far from 0,
    must be significant. bin ~0.5 = 40 one-row games, half win -> gap ~0 with
    game-to-game variance, must NOT be significant."""
    rng = np.random.default_rng(SEED)
    g, p, y = [], [], []
    for game in range(40):
        g.append(game); p.append(0.9); y.append(0.0)               # bin 9 miscalibrated
    for i, game in enumerate(range(40, 80)):
        g.append(game); p.append(0.5); y.append(float(i % 2))      # bin 5 calibrated
    g = np.asarray(g, int); p = np.asarray(p, float); y = np.asarray(y, float)
    count, sump, sumy = aggregate_per_game(g, bin_index(p), p, y, 80)
    bins, n_elig, n_sig = side_summary(bootstrap_side(count, sump, sumy, rng, 300))
    assert bins[9]["significant"] is True, f"miscalibrated 0.9 bin should be significant: {bins[9]}"
    assert bins[5]["significant"] is False, f"calibrated 0.5 bin should not be significant: {bins[5]}"
    assert n_elig >= 2 and n_sig >= 1, (n_elig, n_sig)

    for path in (OUT_JSON, OUT_PNG):
        assert os.path.exists(path), f"missing output {path} -- run the module with no args first"
        assert os.path.getsize(path) > 0, f"empty output {path}"
    with open(OUT_JSON, encoding="utf-8") as f:
        data = json.load(f)
    assert data["edge_claimed"] is False and data["seed"] == SEED
    assert data["sports"], "no sports in output JSON"
    print("OK: calibration_stability self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        summ = {s: {"n_rows": v["n_rows"], "n_games": v["n_games"]} for s, v in res["sports"].items()}
        print(json.dumps({"verdict": res["verdict"], "plot_written": res.get("plot_written"), "sports": summ}, indent=2))
