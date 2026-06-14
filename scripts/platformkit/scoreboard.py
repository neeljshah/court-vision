"""scripts/platformkit/scoreboard.py — Honest calibration scoreboard.

Scores walk-forward-recalibrated forecasts vs the CLOSING LINE and naive
baselines.  The closing line is the benchmark; market_beats_model=True is the
expected honest result.  NEVER claim an edge.  CLI: python -m scripts.platformkit.scoreboard
"""
from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

# ---------------------------------------------------------------------------
# Helpers — kernel re-use where available
# ---------------------------------------------------------------------------

HONEST_FOOTER = (
    "\nDISCIPLINE: closing line is the world's best benchmark; "
    "approaching/matching its calibration is the win; "
    "market_beats_model=True is the expected honest result; NO edge claimed."
)

_ADAPTER_REGISTRY: Dict[str, tuple] = {
    "basketball_nba": ("domains.basketball_nba.adapter", "NBAAdapter"),
    "tennis":         ("domains.tennis.adapter",          "TennisAdapter"),
    "soccer":         ("domains.soccer.adapter",          "SoccerAdapter"),
    "mlb":            ("domains.mlb.adapter",             "MLBAdapter"),
}


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    try:
        from kernel.validation.proof_metrics import brier as _k; return _k(p, y)
    except ImportError:
        return float(np.mean((p - y) ** 2))


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    pc = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def _ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    try:
        from kernel.validation.proof_metrics import ece as _k; return _k(p, y, bins=bins)
    except ImportError:
        pass
    edges = np.linspace(0.0, 1.0, bins + 1)
    total, val = len(p), 0.0
    if total == 0:
        return 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        nb = int(mask.sum())
        if nb:
            val += (nb / total) * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(val)


def _reliability_slope(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    try:
        from kernel.validation.proof_metrics import reliability_slope as _k; return _k(p, y, bins=bins)
    except ImportError:
        pass
    edges = np.linspace(0.0, 1.0, bins + 1)
    xs, ys = [], []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        if mask.sum() >= 3:
            xs.append(float(p[mask].mean())); ys.append(float(y[mask].mean()))
    if len(xs) < 2:
        return float("nan")
    xa, ya = np.array(xs), np.array(ys)
    var = float(np.var(xa, ddof=1))
    return float("nan") if var < 1e-12 else float(np.cov(xa, ya, ddof=1)[0, 1]) / var


def score_forecaster(probs: Sequence[float], outcomes: Sequence[float]) -> Dict:
    """Score a single forecaster.  Returns dict with brier/log_loss/ece/reliability_slope/n."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    mask = np.isfinite(p) & np.isfinite(y)
    p, y = p[mask], y[mask]
    n = int(len(p))
    if n == 0:
        return {"brier": float("nan"), "log_loss": float("nan"),
                "ece": float("nan"), "reliability_slope": float("nan"), "n": 0}
    return {
        "brier":             _brier(p, y),
        "log_loss":          _log_loss(p, y),
        "ece":               _ece(p, y),
        "reliability_slope": _reliability_slope(p, y),
        "n":                 n,
    }


def score_sport(
    sport: str,
    adapter,
    seasons: Optional[Sequence[str]] = None,
) -> List[Dict]:
    """Build bundle, score all forecasters, return list of result rows."""
    from scripts.platformkit.recalibration import walk_forward_recalibrate

    bundle = adapter.feature_bundle(hypothesis=None, seasons=list(seasons or []))
    model_raw  = np.asarray(bundle.signal_col, dtype=float)
    target     = np.asarray(bundle.target, dtype=float)
    closing    = np.asarray(bundle.closing, dtype=float) if bundle.closing is not None \
                 else np.full(len(target), float("nan"))

    # Walk-forward recalibration (leak-free)
    model_recal = walk_forward_recalibrate(model_raw, target, refit_every=20)

    close_mask = np.isfinite(closing)
    n_close = int(close_mask.sum())
    target_label = getattr(adapter, "MARKET_LABEL", "win_prob")
    rows: List[Dict] = []

    def _row(forecaster: str, pvec: np.ndarray) -> Dict:
        p_sub = pvec[close_mask] if n_close > 0 else pvec
        y_sub = target[close_mask] if n_close > 0 else target
        return {"sport": sport, "market": target_label, "forecaster": forecaster,
                **score_forecaster(p_sub, y_sub)}

    close_brier = score_forecaster(closing[close_mask], target[close_mask])["brier"] \
        if n_close > 0 else float("nan")
    base_rate = float(target[np.isfinite(target)].mean()) if np.isfinite(target).any() else 0.5

    for fname, pvec in [
        ("model_raw",       model_raw),
        ("model_recal",     model_recal),
        ("naive_coin",      np.full(len(target), 0.5)),
        ("naive_base_rate", np.full(len(target), base_rate)),
    ]:
        r = _row(fname, pvec)
        if fname.startswith("model") and n_close > 0:
            r["dBrier_vs_close"]    = r["brier"] - close_brier
            r["market_beats_model"] = close_brier < r["brier"]
        rows.append(r)

    if n_close > 0:
        cr = _row("market_close", closing)
        cr["dBrier_vs_close"] = 0.0; cr["market_beats_model"] = False
        rows.append(cr)
    else:
        rows.append({"sport": sport, "market": target_label, "forecaster": "market_close",
                     "brier": float("nan"), "log_loss": float("nan"), "ece": float("nan"),
                     "reliability_slope": float("nan"), "n": 0,
                     "dBrier_vs_close": float("nan"), "market_beats_model": float("nan")})

    return rows


def build_scoreboard(
    sports: Optional[Sequence[str]] = None,
    repo_root: Optional[Path] = None,
) -> List[Dict]:
    """Run score_sport across all adapters; skip absent corpora gracefully."""
    rows: List[Dict] = []
    for sport in list(_ADAPTER_REGISTRY.keys() if sports is None else sports):
        if sport not in _ADAPTER_REGISTRY:
            continue
        mod_path, cls_name = _ADAPTER_REGISTRY[sport]
        try:
            mod = importlib.import_module(mod_path)
            adapter = getattr(mod, cls_name)()
            adapter.MARKET_LABEL = f"{sport}_win_prob"
            rows.extend(score_sport(sport, adapter))
        except FileNotFoundError as exc:
            rows.append({"sport": sport, "error": f"Corpus absent: {exc}", "forecaster": "SKIP"})
        except Exception as exc:  # noqa: BLE001
            rows.append({"sport": sport, "error": str(exc)[:120], "forecaster": "ERROR"})
    return rows


def format_leaderboard(rows: List[Dict]) -> str:
    """Readable table grouped by sport, with honest footer."""
    lines: List[str] = []
    lines.append("=" * 90)
    lines.append("CALIBRATION SCOREBOARD — walk-forward model vs closing line vs baselines")
    lines.append("=" * 90)

    by_sport: Dict[str, List[Dict]] = {}
    for r in rows:
        by_sport.setdefault(r.get("sport", "?"), []).append(r)

    _ORDER = {f: i for i, f in enumerate(
        ["model_raw", "model_recal", "market_close", "naive_base_rate", "naive_coin"])}

    for sport, sport_rows in by_sport.items():
        lines.append(f"\nSPORT: {sport}")
        errors = [r for r in sport_rows if r.get("forecaster") in ("SKIP", "ERROR")]
        if errors:
            for e in errors:
                lines.append(f"  [{e['forecaster']}] {e.get('error','')}")
            continue
        sport_rows_sorted = sorted(sport_rows,
                                   key=lambda r: _ORDER.get(r.get("forecaster", ""), 99))

        hdr = (f"  {'Forecaster':<18} {'N':>6} {'Brier':>8} {'LogLoss':>9} "
               f"{'ECE':>8} {'RelSlope':>9} {'dBrier':>8} {'Mkt>Mdl':>9}")
        lines.append(hdr)
        lines.append("  " + "-" * (len(hdr) - 2))

        def _f(v, w=8, d=5) -> str:
            if v == "" or (isinstance(v, float) and math.isnan(v)):
                return " " * w
            if isinstance(v, bool):
                return f"{'YES' if v else 'no':>{w}}"
            try:
                return f"{float(v):{w}.{d}f}"
            except (TypeError, ValueError):
                return " " * w

        for r in sport_rows_sorted:
            lines.append(
                f"  {r.get('forecaster','?'):<18} {r.get('n',0):>6} "
                f"{_f(r.get('brier',float('nan')))} {_f(r.get('log_loss',float('nan')))} "
                f"{_f(r.get('ece',float('nan')))} {_f(r.get('reliability_slope',float('nan')))} "
                f"{_f(r.get('dBrier_vs_close',''))} {_f(r.get('market_beats_model',''),w=9)}"
            )

    lines.append("\n" + "=" * 90)
    lines.append(HONEST_FOOTER)
    lines.append("=" * 90)
    return "\n".join(lines)


def _main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    rows = build_scoreboard(repo_root=repo_root)
    table = format_leaderboard(rows)
    print(table)

    # Write JSON artifact if vault present
    vault_dir = repo_root / "vault" / "Frontend"
    if vault_dir.exists():
        out_path = vault_dir / "scoreboard.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2, default=str)
        print(f"\n[scoreboard] JSON written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
