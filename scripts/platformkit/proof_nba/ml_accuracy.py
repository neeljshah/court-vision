"""scripts.platformkit.proof_nba.ml_accuracy — moneyline: do we match the close on win-prob?

The totals beat-the-close map is done (W134-W140). This runs the same test on the HEADLINE
market: a leak-free box-based margin-of-victory Elo win-probability vs the market's devigged
implied P(home), scored on Brier/log-loss against realized outcomes over the 2025-26 overlap.

"Beat the best prediction" = lower Brier than the devigged close. Markets are efficient, so
matching the close (within sampling noise) is the realistic best case; beating it would imply
information the close lacks. Honest either way. No $ edge claimed.

Leak-free: Elo updates AFTER each game's snapshot; the closing line is a market datum used
only as the comparison forecaster, never a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.ml_accuracy
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import (  # noqa: E402
    _NBA, load_box, load_close)


def _corpus_from_env() -> Optional[Path]:
    """Shared corpus-override contract: $PROOF_CORPUS_ROOT/nba if set, else None."""
    r = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(r) / "nba" if r else None

_K = 20.0
_HFA = 60.0       # home-court advantage in Elo points (~2.7 pts -> ~60 Elo)
_INIT = 1500.0


def american_to_prob(ml: float) -> float:
    """American moneyline -> implied probability (with vig)."""
    ml = float(ml)
    return (-ml) / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def _p_home(r_h: float, r_a: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(r_h - r_a + _HFA) / 400.0))


def _walk_forward_elo(box) -> np.ndarray:
    """Leak-free MOV-aware Elo (538-style multiplier). Returns pre-game P(home win)."""
    rat: Dict[str, float] = {}
    p = np.empty(len(box))
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        rat.setdefault(ht, _INIT); rat.setdefault(at, _INIT)
        ph = _p_home(rat[ht], rat[at])
        p[i] = ph
        s = 1.0 if hp[i] > ap[i] else 0.0
        margin = abs(hp[i] - ap[i])
        elo_diff = (rat[ht] - rat[at] + _HFA) * (1 if s else -1)
        mov = np.log(margin + 1.0) * (2.2 / (elo_diff * 0.001 + 2.2))   # 538 MOV multiplier
        delta = _K * mov * (s - ph)
        rat[ht] += delta; rat[at] -= delta
    return p


def _brier_logloss(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(np.mean((p - y) ** 2)), float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def run(corpus: Optional[Path] = None) -> Dict:
    root = corpus or _corpus_from_env() or _NBA   # arg > env > real data/domains path
    box = load_box(root)
    box["p_model"] = _walk_forward_elo(box)
    import pandas as pd
    raw = pd.read_parquet(root / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"])
    raw["imp_h"] = raw["home_ml"].map(american_to_prob)
    raw["imp_a"] = raw["away_ml"].map(american_to_prob)
    raw["p_market"] = raw["imp_h"] / (raw["imp_h"] + raw["imp_a"])     # devig
    m = box.merge(raw[["date", "home_abbr", "away_abbr", "p_market"]],
                  on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)
    n = len(m)
    if n < 60:
        return {"status": "data_limited", "n_overlap": n}

    y = (m["home_pts"] > m["away_pts"]).to_numpy(float)
    pm = m["p_model"].to_numpy(float)
    pk = m["p_market"].to_numpy(float)
    # evaluate on the held-out second half (model warms up on the first)
    mid = n // 2
    te = slice(mid, n)
    b_model, ll_model = _brier_logloss(pm[te], y[te])
    b_mkt, ll_mkt = _brier_logloss(pk[te], y[te])
    gap = round(b_model - b_mkt, 4)          # >0 => market sharper
    return {
        "status": "ok", "n_overlap": n, "n_holdout": n - mid,
        "model_brier": round(b_model, 4), "market_brier": round(b_mkt, 4),
        "model_logloss": round(ll_model, 4), "market_logloss": round(ll_mkt, 4),
        "brier_gap_to_market": gap,
        "corr_model_market": round(float(np.corrcoef(pm, pk)[0, 1]), 3),
        "verdict": (
            f"OUR model BEATS the close on Brier ({round(b_model,4)} vs {round(b_mkt,4)})"
            if gap < -0.002 else
            (f"OUR model MATCHES the close (Brier {round(b_model,4)} vs {round(b_mkt,4)}, "
             f"gap {gap:+})" if gap <= 0.012 else
             f"close sharper by {gap} Brier — the freshness edge (injuries/lineups)")),
        "note": "Win-prob accuracy vs the devigged close on real outcomes. No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n_overlap')}"); return 0
    print(f"=== NBA moneyline: OUR Elo win-prob vs the devigged close "
          f"(n={rep['n_overlap']}, holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>13}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'devig close':>13}  {rep['market_brier']:>8} {rep['market_logloss']:>8}")
    print(f"  {'our Elo':>13}  {rep['model_brier']:>8} {rep['model_logloss']:>8}")
    print(f"\ncorr(model, market) = {rep['corr_model_market']}  |  "
          f"Brier gap to market: {rep['brier_gap_to_market']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
