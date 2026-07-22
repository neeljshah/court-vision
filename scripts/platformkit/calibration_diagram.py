"""calibration_diagram.py -- turn a scalar Brier claim into the calibration picture.

READ-ONLY over already-settled (p, y) pairs. No training, no new prediction, no
model load. Given predicted probabilities p and binary outcomes y it computes:

  (a) a 10-equal-width-bin reliability table (n, mean predicted p, empirical
      frequency, gap),
  (b) the Murphy 3-component decomposition of the Brier score
      (reliability - resolution + uncertainty), with the exact identity check,
  (c) ECE and MCE,

and renders a Markdown artifact (docs/CALIBRATION_DIAGRAM.md) with an ASCII
reliability chart, plus an optional PNG if matplotlib is importable.

Murphy identity note (exact, not approximate): the 3 components sum EXACTLY to
the Brier score OF THE BINNED FORECAST (each p replaced by its bin mean),
    BS_binned = REL - RES + UNC.
The raw Brier of the continuous forecast differs only by a small binning-
discretization gap, reported alongside. The self-check asserts the exact
identity to 1e-9 and asserts bin counts sum to N.

Run:
    python -m scripts.platformkit.calibration_diagram --self-check
    python -m scripts.platformkit.calibration_diagram            # build the doc
    python -m scripts.platformkit.calibration_diagram --input "path/*.jsonl"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_CORPUS = os.path.join(PROJECT_DIR, "data", "cache",
                               "ingame_grade_joined", "mlb", "*.jsonl")
_OUT_MD = os.path.join(PROJECT_DIR, "docs", "CALIBRATION_DIAGRAM.md")
_OUT_PNG = os.path.join(PROJECT_DIR, "docs", "assets", "calibration_diagram.png")
N_BINS = 10


def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> List[Dict]:
    """One row per equal-width bin: [lo, hi), n, mean predicted p, empirical freq, gap."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # rightmost edge inclusive so p == 1.0 lands in the last bin.
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    rows: List[Dict] = []
    for k in range(n_bins):
        m = idx == k
        n = int(m.sum())
        mean_p = float(p[m].mean()) if n else float("nan")
        freq = float(y[m].mean()) if n else float("nan")
        gap = (mean_p - freq) if n else float("nan")
        rows.append({"lo": float(edges[k]), "hi": float(edges[k + 1]), "n": n,
                     "mean_p": mean_p, "freq": freq, "gap": gap})
    return rows


def murphy(p: np.ndarray, y: np.ndarray, n_bins: int = N_BINS) -> Dict[str, float]:
    """Murphy 3-component decomposition. REL - RES + UNC == BS_binned (exact)."""
    n = p.shape[0]
    o_bar = float(y.mean())
    rows = reliability_table(p, y, n_bins)
    rel = res = 0.0
    p_binned = np.empty_like(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    for k, r in enumerate(rows):
        if r["n"] == 0:
            continue
        rel += r["n"] * (r["mean_p"] - r["freq"]) ** 2
        res += r["n"] * (r["freq"] - o_bar) ** 2
        p_binned[idx == k] = r["mean_p"]
    rel /= n
    res /= n
    unc = o_bar * (1.0 - o_bar)
    bs_binned = float(np.mean((p_binned - y) ** 2))
    bs_raw = float(np.mean((p - y) ** 2))
    return {"reliability": rel, "resolution": res, "uncertainty": unc,
            "bs_binned": bs_binned, "bs_raw": bs_raw,
            "identity_sum": rel - res + unc, "gap_raw_binned": bs_raw - bs_binned,
            "o_bar": o_bar, "n": n}


def ece_mce(rows: List[Dict], n: int) -> Tuple[float, float]:
    """Expected and Maximum Calibration Error over the reliability bins."""
    ece = 0.0
    mce = 0.0
    for r in rows:
        if r["n"] == 0:
            continue
        g = abs(r["gap"])
        ece += (r["n"] / n) * g
        mce = max(mce, g)
    return ece, mce


def ascii_chart(rows: List[Dict], width: int = 40) -> str:
    """Predicted (P) vs empirical (E) per bin on a 0..1 track."""
    lines = ["  bin        pred|emp    0" + " " * (width - 5) + "1"]
    for r in rows:
        label = f"[{r['lo']:.1f},{r['hi']:.1f})"
        if r["n"] == 0:
            lines.append(f"  {label:<11}   (empty)")
            continue
        track = [" "] * (width + 1)
        pe = min(width, max(0, round(r["mean_p"] * width)))
        ee = min(width, max(0, round(r["freq"] * width)))
        track[ee] = "E"
        track[pe] = "P" if pe != ee else "X"  # X where predicted meets empirical
        lines.append(f"  {label:<11} {r['mean_p']:.2f}|{r['freq']:.2f}  |"
                     + "".join(track) + "|")
    lines.append("  (P=predicted  E=empirical  X=coincide;  horizontal P-E distance = calibration gap)")
    return "\n".join(lines)


def load_jsonl_corpus(pattern: str) -> Tuple[np.ndarray, np.ndarray, int]:
    """Read model_prob + outcome from a glob of settled-join jsonl files."""
    ps: List[float] = []
    ys: List[float] = []
    files = sorted(glob.glob(pattern))
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                mp = r.get("model_prob")
                oc = r.get("outcome")
                if mp is None or oc is None:
                    continue
                ps.append(float(mp))
                ys.append(float(oc))
    return np.asarray(ps, dtype=float), np.asarray(ys, dtype=float), len(files)


def render_markdown(rows: List[Dict], dec: Dict[str, float], ece: float, mce: float,
                    source_note: str, n_files: int, png_rel: str | None) -> str:
    n = dec["n"]
    out: List[str] = []
    out.append("# Reliability diagram + Murphy Brier decomposition\n")
    out.append("> **READ-ONLY calibration artifact.** Computed over already-settled "
               "(predicted probability, binary outcome) pairs. No model is trained, "
               "loaded, or re-predicted here; this only re-scores outcomes that are "
               "already final. `edge_claimed = False` -- this is forecaster calibration, "
               "not a dollar/ROI/edge claim. A live book sees the same in-game state, so "
               "no beat-the-market test applies.\n")
    out.append(f"**Data it ran on:** {source_note}  \n")
    out.append(f"**N = {n:,} observations** across {n_files} settled game files; "
               f"base rate (outcome mean) = {dec['o_bar']:.4f}.\n")
    out.append("---\n")

    out.append("## Reliability table (10 equal-width bins)\n")
    out.append("| bin | n | mean predicted p | empirical freq | gap (p - freq) |")
    out.append("|---|---:|---:|---:|---:|")
    for r in rows:
        if r["n"] == 0:
            out.append(f"| [{r['lo']:.1f}, {r['hi']:.1f}) | 0 | - | - | - |")
        else:
            out.append(f"| [{r['lo']:.1f}, {r['hi']:.1f}) | {r['n']:,} | "
                       f"{r['mean_p']:.4f} | {r['freq']:.4f} | {r['gap']:+.4f} |")
    out.append("")
    out.append(f"- **ECE** (n-weighted mean |gap|) = **{ece:.4f}**")
    out.append(f"- **MCE** (worst-bin |gap|) = **{mce:.4f}**\n")

    out.append("## ASCII reliability chart\n")
    out.append("```")
    out.append(ascii_chart(rows))
    out.append("```\n")
    if png_rel:
        out.append(f"![reliability diagram]({png_rel})\n")

    out.append("## Murphy 3-component Brier decomposition\n")
    out.append("Brier = **Reliability - Resolution + Uncertainty** (Murphy 1973). "
               "Lower reliability is better (calibration error); higher resolution is "
               "better (discrimination); uncertainty is the irreducible base-rate term.\n")
    out.append("| component | value | meaning |")
    out.append("|---|---:|---|")
    out.append(f"| Reliability (REL) | {dec['reliability']:.6f} | calibration error -- lower better |")
    out.append(f"| Resolution (RES)  | {dec['resolution']:.6f} | discrimination -- higher better |")
    out.append(f"| Uncertainty (UNC) | {dec['uncertainty']:.6f} | base-rate variance (irreducible) |")
    out.append("")
    out.append("**Identity check (exact):**")
    out.append("```")
    out.append(f"REL - RES + UNC = {dec['reliability']:.6f} - {dec['resolution']:.6f} "
               f"+ {dec['uncertainty']:.6f}")
    out.append(f"                = {dec['identity_sum']:.6f}   (Brier of the binned forecast)")
    out.append(f"raw Brier         = {dec['bs_raw']:.6f}")
    out.append(f"binning gap       = {dec['gap_raw_binned']:+.6f}  (raw - binned; "
               "discretization only)")
    out.append("```")
    out.append("The three components sum to the binned Brier exactly (verified to 1e-9 in "
               "the self-check); the raw continuous Brier differs only by the small "
               "binning-discretization gap shown above.\n")
    out.append("---")
    out.append("*Generated by `scripts/platformkit/calibration_diagram.py "
               "--self-check` then default build. No dollar/edge/ROI figure appears here; "
               "calibration only.*")
    return "\n".join(out) + "\n"


def _maybe_png(rows: List[Dict]) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    xs = [r["mean_p"] for r in rows if r["n"]]
    ys = [r["freq"] for r in rows if r["n"]]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="perfect calibration")
    ax.plot(xs, ys, "o-", color="#c47f17", label="model")
    ax.set_xlabel("mean predicted probability")
    ax.set_ylabel("empirical frequency")
    ax.set_title("Reliability diagram (read-only, settled outcomes)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    os.makedirs(os.path.dirname(_OUT_PNG), exist_ok=True)
    fig.tight_layout()
    fig.savefig(_OUT_PNG, dpi=110)
    plt.close(fig)
    return os.path.relpath(_OUT_PNG, os.path.dirname(_OUT_MD)).replace(os.sep, "/")


def _self_check() -> None:
    """Assert Murphy identity and bin-count invariants on a synthetic (p, y)."""
    rng = np.random.default_rng(0)
    n = 5000
    p = rng.uniform(0, 1, n)
    # deliberately miscalibrated + noisy so all bins populate and REL > 0.
    y = (rng.uniform(0, 1, n) < np.clip(p * 0.8 + 0.1, 0, 1)).astype(float)

    rows = reliability_table(p, y)
    assert sum(r["n"] for r in rows) == n, "bin counts must sum to N"

    dec = murphy(p, y)
    lhs = dec["reliability"] - dec["resolution"] + dec["uncertainty"]
    assert abs(lhs - dec["bs_binned"]) < 1e-9, \
        f"Murphy identity broken: {lhs} vs {dec['bs_binned']}"
    assert abs(dec["identity_sum"] - dec["bs_binned"]) < 1e-6, "identity within 1e-6"
    assert abs(dec["uncertainty"] - dec["o_bar"] * (1 - dec["o_bar"])) < 1e-12

    ece, mce = ece_mce(rows, n)
    assert 0.0 <= ece <= mce <= 1.0, "ECE must be <= MCE and both in [0,1]"

    print("[self-check] PASS")
    print(f"  bins sum to N: {sum(r['n'] for r in rows)} == {n}")
    print(f"  REL-RES+UNC = {lhs:.8f}  BS_binned = {dec['bs_binned']:.8f}  "
          f"|diff| = {abs(lhs - dec['bs_binned']):.2e} (< 1e-9)")
    print(f"  raw Brier = {dec['bs_raw']:.8f}  binning gap = {dec['gap_raw_binned']:+.2e}")
    print(f"  ECE = {ece:.6f}  MCE = {mce:.6f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--input", default=_DEFAULT_CORPUS,
                    help="glob of jsonl files carrying model_prob + outcome")
    ap.add_argument("--out", default=_OUT_MD)
    args = ap.parse_args()

    if args.self_check:
        _self_check()
        return 0

    p, y, n_files = load_jsonl_corpus(args.input)
    if p.size == 0:
        print(f"[skip] no (model_prob, outcome) rows under {args.input}")
        print("       (local in-game corpus is gitignored -- absent on a fresh clone)")
        return 1
    rows = reliability_table(p, y)
    dec = murphy(p, y)
    ece, mce = ece_mce(rows, p.size)
    png_rel = _maybe_png(rows)
    src = ("local MLB in-game settlement join "
           "(`data/cache/ingame_grade_joined/mlb/*.jsonl`, gitignored -- absent from a "
           "fresh clone), each row = model_prob vs realized outcome, `edge_claimed=False`. "
           "No committed per-observation win-prob walk-forward arrays exist "
           "(`results/winprob_walk_forward_results.json` holds only 3-fold summary "
           "scalars), so the reliability picture is built on this real settled corpus.")
    md = render_markdown(rows, dec, ece, mce, src, n_files, png_rel)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[ok] wrote {os.path.relpath(args.out, PROJECT_DIR)}  "
          f"(N={p.size:,}, {n_files} files, PNG={'yes' if png_rel else 'no'})")
    print(f"     Brier raw={dec['bs_raw']:.4f}  ECE={ece:.4f}  MCE={mce:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
