"""scripts/platformkit/reliability_diagram.py -- Reliability diagram generator.

ASCII/Markdown reliability tables (predicted-vs-observed per bin, n per bin, sparse-bin
flags) from the committed golden + ledger fixtures. Optional matplotlib PNG (import-guarded
so the module runs offline with stdlib + numpy only).

HONESTY ANCHOR: the fixtures are SYNTHETIC reproducibility anchors; live OOS numbers are a
HUMAN-RUN step on the real corpus. "No edge / MARKET-EFFICIENT HERE" is a first-class state,
never a failure. Each number is badged (model-in-corpus / devigged-market / score-only).

Usage: python -m scripts.platformkit.reliability_diagram --fixture {golden|ledger} [--png p]
<=300 LOC. No src/kernel/api edits. ASCII output only (no unicode).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

# --- optional matplotlib guard (never hard-fails if absent) ---
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore[import]
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False

_REPO = pathlib.Path(__file__).resolve().parents[2]
_GOLDEN_FIXTURE = _REPO / "tests" / "fixtures" / "golden" / "game_states.json"
_LEDGER_FIXTURE = _REPO / "tests" / "fixtures" / "ledger" / "ledger_demo.csv"

SPARSE_THRESHOLD = 30   # bins with n < this are flagged

def _load_golden() -> List[Dict]:
    """Load the committed golden gate fixture (JSON; {"states": [...]} or a bare list)."""
    import json
    if not _GOLDEN_FIXTURE.exists():
        return []
    with open(_GOLDEN_FIXTURE, "r", encoding="ascii") as fh:
        payload = json.load(fh)
    return payload["states"] if isinstance(payload, dict) else payload


def _golden_model_rows() -> "Tuple[np.ndarray, np.ndarray]":
    """Real per-row (p_model, outcome) for the golden corpus via the SAME leak-free
    walk_forward the eval gate uses. Keeps this generator consistent with run_gate /
    calibration_record instead of reading a non-existent p_model field off the fixture.
    """
    from scripts.platformkit.eval_gate.walkforward import walk_forward
    from scripts.platformkit.eval_gate.offline_predict import offline_predict_fn
    states = _load_golden()
    res = walk_forward(states, offline_predict_fn, select_inside=True)
    pm = np.array([r["p_model"] for r in res.records], dtype=float)
    y = np.array([r["y"] for r in res.records], dtype=float)
    return pm, y


def _load_ledger() -> "import pandas; pandas.DataFrame":  # type annotation only
    """Load the committed ledger fixture (CSV with calibrated_prob + outcome)."""
    import pandas as pd
    if not _LEDGER_FIXTURE.exists():
        return None
    df = pd.read_csv(_LEDGER_FIXTURE)
    return df[df["outcome"].notna()].reset_index(drop=True)

def compute_diagram(
    probs: np.ndarray,
    outcomes: np.ndarray,
    bins: int = 10,
) -> Dict:
    """Reliability data per bin: bin_centers, pred_means, obs_freq, n_per_bin,
    sparse_flags (n<SPARSE_THRESHOLD), ece, sharpness (forecast var), n_total."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    centers: List[float] = []
    pred_means: List[float] = []
    obs: List[float] = []
    ns: List[int] = []
    sparse: List[bool] = []
    ece_acc = 0.0
    n_total = len(probs)

    for k in range(bins):
        lo, hi = edges[k], edges[k + 1]
        mask = (probs >= lo) & (probs < hi) if k < bins - 1 else (probs >= lo) & (probs <= hi)
        n = int(mask.sum())
        center = float((lo + hi) / 2)
        centers.append(center)
        ns.append(n)
        if n == 0:
            pred_means.append(float("nan"))
            obs.append(float("nan"))
            sparse.append(True)
            continue
        p_bar = float(probs[mask].mean())
        o_bar = float(outcomes[mask].mean())
        pred_means.append(p_bar)
        obs.append(o_bar)
        sparse.append(n < SPARSE_THRESHOLD)
        ece_acc += (n / n_total) * abs(o_bar - p_bar)

    return {
        "bin_centers": centers,
        "pred_means": pred_means,   # actual mean forecast per bin (not the bin midpoint)
        "obs_freq": obs,
        "n_per_bin": ns,
        "sparse_flags": sparse,
        "ece": round(ece_acc, 6),
        "sharpness": round(float(np.var(probs)), 6),
        "n_total": n_total,
    }

def format_ascii(
    diag: Dict,
    title: str = "Reliability Diagram",
    brier: Optional[float] = None,
    brier_close: Optional[float] = None,
    verdict: str = "",
    source_badge: str = "",
) -> str:
    """Render a reliability diagram as an ASCII/Markdown table.

    Sparse bins (n < 30) are flagged with [SPARSE]. The verdict line front-
    loads 'no edge / MARKET-EFFICIENT HERE' when appropriate.
    """
    lines: List[str] = []
    lines.append(f"\n=== {title} ===")
    lines.append(f"n={diag['n_total']}  ece={diag['ece']:.4f}  "
                 f"sharpness={diag['sharpness']:.4f}")
    if brier is not None:
        brier_line = f"Brier model={brier:.4f}"
        if brier_close is not None:
            brier_line += f"  Brier close (devigged)={brier_close:.4f}"
        lines.append(brier_line)
    if verdict:
        lines.append(f"Verdict: {verdict}")
    if source_badge:
        lines.append(f"Source: {source_badge}")
    lines.append("")
    header = f"{'Bin center':>12} | {'Pred mean':>10} | {'Obs freq':>9} | {'N':>6} | {'Flag':<8}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)
    # prefer the real per-bin mean forecast; fall back to the bin center for older dicts
    pred_means = diag.get("pred_means", diag["bin_centers"])
    for i, (center, pmean, obs, n, sp) in enumerate(zip(
        diag["bin_centers"], pred_means, diag["obs_freq"],
        diag["n_per_bin"], diag["sparse_flags"]
    )):
        if n == 0:
            flag = "[EMPTY]"
            obs_str = "---"
            pmean_str = "---"
        else:
            flag = "[SPARSE]" if sp else ""
            obs_str = f"{obs:.3f}"
            pmean_str = f"{pmean:.3f}"
        lines.append(
            f"{center:>12.2f} | {pmean_str:>10} | {obs_str:>9} | {n:>6} | {flag:<8}"
        )
    lines.append(sep)
    lines.append(
        "NOTE: calibration (reliability) != edge. "
        "MARKET-EFFICIENT HERE is a first-class state, not a failure. "
        "Source badge shows model-in-corpus / devigged-market / score-only."
    )
    lines.append("")
    return "\n".join(lines)

def save_png(diag: Dict, path: str, title: str = "Reliability Diagram") -> None:
    """Save reliability diagram as PNG. Raises ImportError if matplotlib absent."""
    if not _HAS_MPL:
        raise ImportError("matplotlib not available; install it to use --png")
    x = diag.get("pred_means", diag["bin_centers"])

    def _pts(want_sparse):  # (predicted, observed) for populated bins of one density class
        rows = zip(x, diag["obs_freq"], diag["n_per_bin"], diag["sparse_flags"])
        pts = [(c, o) for c, o, n, sp in rows if n > 0 and sp == want_sparse and not (o != o)]
        return [p[0] for p in pts], [p[1] for p in pts]

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
    full_c, full_o = _pts(False)
    sparse_c, sparse_o = _pts(True)
    if full_c:
        ax.plot(full_c, full_o, "o-", color="#2563eb", label="Observed (n>=30)")
    if sparse_c:
        ax.plot(sparse_c, sparse_o, "s", color="#f59e0b", label="Sparse bin (n<30)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Observed frequency")
    ax.set_title(f"{title}\nECE={diag['ece']:.4f}  n={diag['n_total']}")
    ax.legend(fontsize=8)
    ax.text(0.02, 0.96, "Calibration != edge. Market-efficient = success.",
            fontsize=7, color="#6b7280", transform=ax.transAxes, va="top")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)

def run_golden(bins: int = 10, png: Optional[str] = None) -> int:
    """Run reliability diagram on the committed golden gate fixture."""
    states = _load_golden()
    if not states:
        print("golden fixture not found at", _GOLDEN_FIXTURE)
        print("Run: python -m scripts.platformkit.eval_gate.gen_golden to generate it.")
        return 1
    # real per-row model probs from the leak-free walk_forward (matches run_gate)
    probs, outcomes = _golden_model_rows()
    diag = compute_diagram(probs, outcomes, bins=bins)
    print(format_ascii(diag, title="Golden Fixture -- Reliability (SYNTHETIC ANCHOR)",
                       source_badge="score-only-anchor (SYNTHETIC; not a real calibration claim)"))
    if png:
        save_png(diag, png, title="Golden Fixture Reliability (SYNTHETIC ANCHOR)")
        print(f"PNG saved: {png}")
    return 0


def run_ledger(bins: int = 10, png: Optional[str] = None) -> int:
    """Run reliability diagram on the committed ledger fixture per sport."""
    try:
        import pandas as pd
    except ImportError:
        print("pandas required for ledger fixture; not available")
        return 1
    df = _load_ledger()
    if df is None or len(df) == 0:
        print("ledger fixture not found at", _LEDGER_FIXTURE)
        return 1
    for sport, g in df.groupby("sport"):
        probs = g["calibrated_prob"].to_numpy(float)
        outcomes = g["outcome"].to_numpy(float)
        brier_m = float(np.mean((probs - outcomes) ** 2))
        brier_c = None
        verdict = "MATCHES_CLOSE (fixture only)"
        source_badge = "model-in-corpus"
        mkt = g[g["devig_close_prob"].notna()]
        if len(mkt):
            cp = mkt["devig_close_prob"].to_numpy(float)
            oy = mkt["outcome"].to_numpy(float)
            brier_c = round(float(np.mean((cp - oy) ** 2)), 4)
            bss = 1.0 - brier_m / brier_c if brier_c > 0 else 0.0
            if bss > 0.01:
                verdict = "BEATS_CLOSE (fixture only -- not a live claim)"
            elif bss > -0.01:
                verdict = "MATCHES_CLOSE -- no edge / MARKET-EFFICIENT HERE"
            else:
                verdict = "BEHIND -- market efficient; gap = freshness/data"
            source_badge = "model-in-corpus vs devigged-market"
        diag = compute_diagram(probs, outcomes, bins=bins)
        label = f"Ledger Fixture [{sport}] -- Reliability"
        print(format_ascii(diag, title=label, brier=brier_m, brier_close=brier_c,
                           verdict=verdict, source_badge=source_badge))
        if png:
            sport_png = png.replace(".png", f"_{sport}.png")
            try:
                save_png(diag, sport_png, title=f"Ledger Reliability [{sport}]")
                print(f"PNG saved: {sport_png}")
            except ImportError as exc:
                print(f"[PNG skipped] {exc}")
    print("VALIDATION_PENDING: live-ledger OOS results are a HUMAN-RUN step on a real corpus.")
    print("edge_claimed=False. Honest MATCH/REJECT is the success.")
    return 0

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reliability diagram generator (ASCII/Markdown + optional PNG).")
    ap.add_argument("--fixture", choices=["golden", "ledger"], default="ledger",
                    help="Which committed fixture to use (default: ledger)")
    ap.add_argument("--bins", type=int, default=10, help="Number of probability bins")
    ap.add_argument("--png", default=None, metavar="PATH",
                    help="Optional PNG output path (requires matplotlib)")
    args = ap.parse_args(argv)
    if args.fixture == "golden":
        return run_golden(bins=args.bins, png=args.png)
    return run_ledger(bins=args.bins, png=args.png)


if __name__ == "__main__":
    raise SystemExit(main())
