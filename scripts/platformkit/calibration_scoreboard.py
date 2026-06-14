"""scripts/platformkit/calibration_scoreboard.py — Per-sport calibration-improvement scoreboard.

Surfaces W93/W94 calibration wins (improved ECE/Brier via sport-specific tuners) without
claiming any market or betting edge.  The improved forecasters are:

  NBA    — scripts.platformkit.nba_winprob_model.fit_winprob (multi-feature WF logistic)
  Tennis — domains.tennis.elo_tune.platt_recalibrate (WF Platt on Elo logit)
  MLB    — domains.mlb.asof_sp_form (SP-form feature; solo-Elo Platt vs Elo+SP-form 2-feat)
  Soccer — domains.soccer.rho_fit.walk_forward_rho (DC rho; DRAW-probability calibration)
           Soccer rho eval capped at SOCCER_SAMPLE_CAP rows (default 3 000) to stay <5 s.
           Full 25k run: python -m domains.soccer.rho_fit_eval

HONESTY: calibration metric (Brier/ECE), NOT a market edge.  No edge claimed.

CLI: python -m scripts.platformkit.calibration_scoreboard
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_PATH = _REPO_ROOT / "vault" / "_Organized" / "_Index" / "_Calibration_Scoreboard.md"

HONEST_BANNER = (
    "> **CALIBRATION METRIC — NOT A MARKET EDGE.**  "
    "Lower Brier / ECE means better-calibrated probabilities, NOT a market edge; "
    "no edge is claimed.  These numbers do not imply beating closing lines or positive EV.  "
    "Markets are efficient."
)

# Re-export for test imports (tests import SOCCER_SAMPLE_CAP from this module)
from scripts.platformkit.calibration_providers import SOCCER_SAMPLE_CAP  # noqa: E402

# ---------------------------------------------------------------------------
# Shared metric helpers (no kernel.* dependency — keep test-friendly)
# ---------------------------------------------------------------------------


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    try:
        from kernel.validation.proof_metrics import brier as _k
        return _k(p, y)
    except ImportError:
        return float(np.mean((p - y) ** 2))


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    pc = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    try:
        from kernel.validation.proof_metrics import ece as _k
        return _k(p, y, bins=bins)
    except ImportError:
        pass
    edges = np.linspace(0.0, 1.0, bins + 1)
    n, val = len(p), 0.0
    if n == 0:
        return float("nan")
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb:
            val += (nb / n) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


def _score(p: np.ndarray, y: np.ndarray) -> Dict:
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = p[mask], y[mask]
    if len(p) == 0:
        return {"n": 0, "brier": float("nan"), "logloss": float("nan"), "ece": float("nan")}
    return {"n": int(len(p)), "brier": _brier(p, y),
            "logloss": _log_loss(p, y), "ece": _ece(p, y)}


# ---------------------------------------------------------------------------
# Per-sport provider type: callable () -> SportMetrics
# Providers are injected lazily; the test suite passes synthetic fakes.
# Real providers live in calibration_providers.py (imported below lazily).
# ---------------------------------------------------------------------------

SportMetrics = Dict  # {baseline: {brier,ece,logloss,n}, improved: {...}, method: str, sport: str}


def _default_providers() -> Dict[str, Callable[[], SportMetrics]]:
    """Return real provider callables (imported lazily to avoid loading heavy deps in tests)."""
    from scripts.platformkit.calibration_providers import (
        _run_nba, _run_tennis, _run_mlb, _run_soccer,
    )
    return {
        "NBA": _run_nba,
        "TENNIS": _run_tennis,
        "MLB": _run_mlb,
        "SOCCER": _run_soccer,
    }


# ---------------------------------------------------------------------------
# Core builder (accepts injectable providers for test isolation)
# ---------------------------------------------------------------------------


def build_calibration_scoreboard(
    providers: Optional[Dict[str, Callable[[], SportMetrics]]] = None,
    vault_root: Optional[Path] = None,
    write: bool = True,
) -> List[SportMetrics]:
    """Compute per-sport baseline vs improved calibration metrics and write artifact.

    Parameters
    ----------
    providers : optional dict sport->callable.  Default = real pipeline runners.
                Tests inject synthetic callables to avoid loading real data.
    vault_root : override path for the Markdown artifact (default: repo vault).
    write : if True, write the Markdown artifact to vault.

    Returns
    -------
    List of SportMetrics dicts (one per sport).
    """
    if providers is None:
        providers = _default_providers()

    rows: List[SportMetrics] = []
    for sport, fn in providers.items():
        try:
            row = fn()
            row.setdefault("sport", sport)
            rows.append(row)
        except Exception as exc:  # noqa: BLE001
            rows.append({"sport": sport, "error": str(exc)[:120]})

    if write:
        _write_artifact(rows, vault_root=vault_root)

    return rows


def _write_artifact(rows: List[SportMetrics], vault_root: Optional[Path] = None) -> Path:
    """Render Markdown and write to vault."""
    out = (vault_root or _ARTIFACT_PATH.parent) / "_Calibration_Scoreboard.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_markdown(rows), encoding="utf-8")
    return out


def _render_markdown(rows: List[SportMetrics]) -> str:
    lines: List[str] = [
        "---",
        "tags: [organized, calibration-scoreboard, w93, w94]",
        "---",
        "# Calibration Scoreboard — Per-Sport Calibration Wins (W93/W94)\n",
        HONEST_BANNER,
        "",
        "Leak-free walk-forward validation only.  Baseline = sport-specific recal baseline.  "
        "Improved = sport-specific tuner (see Method column).  "
        "Lower Brier / lower ECE = better calibrated (NOT a betting edge).\n",
        "| Sport | N | Baseline Brier | Improved Brier | dBrier | "
        "Baseline ECE | Improved ECE | dECE | Method |",
        "|-------|--:|---------------:|---------------:|-------:|"
        "------------:|-------------:|-----:|--------|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r.get('sport','?')} | — | — | — | — | — | — | — "
                         f"| ERROR: {r['error'][:50]} |")
            continue
        bl = r.get("baseline", {})
        im = r.get("improved", {})
        n = im.get("n") or bl.get("n") or 0
        bb, ib = bl.get("brier", float("nan")), im.get("brier", float("nan"))
        be, ie = bl.get("ece", float("nan")), im.get("ece", float("nan"))
        db = ib - bb if _both_finite(bb, ib) else float("nan")
        de = ie - be if _both_finite(be, ie) else float("nan")
        method = r.get("method", "—")
        lines.append(
            f"| {r['sport']} | {n:,} "
            f"| {_fmt(bb)} | {_fmt(ib)} | {_fmt(db, signed=True)} "
            f"| {_fmt(be)} | {_fmt(ie)} | {_fmt(de, signed=True)} | {method} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- **NBA**: multi-feature WF logistic adds rest, pace, rating context to solo-Elo logit.",
        "- **Tennis**: WF Platt recalibration reduces over-confidence in Elo-extreme matches.",
        "- **MLB**: SP-form EW feature (first-6-innings RA) in a 2-feature logistic vs solo-Elo "
        "Platt (time-split 70/30).  Source: domains.mlb.asof_sp_form_eval.",
        "- **Soccer**: DC rho (draw/low-score correction) redistributes mass in "
        "0-0/1-0/0-1/1-1 cells; DRAW-probability Brier/ECE reported (scoreline-level). "
        f"Capped at {SOCCER_SAMPLE_CAP:,} rows for speed (full run: "
        "python -m domains.soccer.rho_fit_eval).",
        "",
        "**Honest reading:** calibration improvement = the model is better at saying "
        "\"this is a 60% game\" when it's really 60%.  It does NOT imply beating the "
        "closing line, positive EV, or any market edge.  No edge is claimed.",
        "",
        "_Generated by `scripts/platformkit/calibration_scoreboard.py`_",
    ]
    return "\n".join(lines) + "\n"


def _fmt(v: float, signed: bool = False, d: int = 5) -> str:
    import math
    if not isinstance(v, float) or math.isnan(v):
        return "—"
    return f"{v:+.{d}f}" if signed else f"{v:.{d}f}"


def _both_finite(a: float, b: float) -> bool:
    import math
    return math.isfinite(a) and math.isfinite(b)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    print("Building calibration scoreboard (real providers) ...")
    results = build_calibration_scoreboard(write=True)
    for r in results:
        if "error" in r:
            print(f"  {r['sport']}: ERROR — {r['error']}")
        else:
            bl = r.get("baseline", {})
            im = r.get("improved", {})
            print(
                f"  {r['sport']:6s}  n={im.get('n', bl.get('n', 0)):,}  "
                f"baseline ECE={bl.get('ece', float('nan')):.5f}  "
                f"improved ECE={im.get('ece', float('nan')):.5f}  "
                f"method={r.get('method','?')}"
            )
    print("Artifact written.")
    sys.exit(0)
