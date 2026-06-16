"""scripts.platformkit.proof_mlb.beat_the_close_ml — MLB moneyline: do we match the close?

Mirrors proof_nba/ml_accuracy.py on the headline MLB market. A self-contained leak-free
walk-forward MOV-aware Elo produces pre-game P(home win); the devigged closing moneyline
(imp_h / (imp_h + imp_a)) is the comparison forecaster. Both are scored on Brier / log-loss
against realized outcomes over the held-out SECOND HALF (Elo warms up on the first half).

"Beat the best prediction" = lower Brier than the devigged close on the SAME real outcomes.
Markets are efficient, so MATCH (within sampling noise) is the realistic best case. Elo is
pitcher-blind (no starting-pitcher signal), so BEHIND by ~0.005-0.010 Brier is expected and
honest. No $ edge claimed.

Leak-free: Elo updates AFTER each game's snapshot is recorded; the closing line is a market
datum used only as the comparison forecaster, NEVER a model input.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; calibration/accuracy only, no $ edge.
Run: python -m scripts.platformkit.proof_mlb.beat_the_close_ml
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

_GAMES = _REPO / "data/domains/mlb/games.parquet"
_ODDS = _REPO / "data/domains/mlb/odds.parquet"


def _corpus_from_env() -> Optional[Path]:
    """Shared corpus-override contract: $PROOF_CORPUS_ROOT/mlb if set, else None.

    Precedence in run(): explicit corpus arg > $PROOF_CORPUS_ROOT/mlb > real data/domains
    path (unchanged default). The scoreboard sets the env var before calling run() with no
    args, so this proof must honor it by itself.
    """
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return (Path(root) / "mlb") if root else None

# MLB Elo: baseball has a SMALL home edge (~54% home win rate -> modest HFA), low MOV
# multiplier (run margins are small), and a gentle K (162-game seasons, ~even teams).
_K = 6.0
_HFA = 24.0       # ~24 Elo pts -> ~53.5% pre-game home edge for evenly-rated teams
_INIT = 1500.0


def american_to_prob(ml: float) -> float:
    """American moneyline -> implied probability (with vig)."""
    ml = float(ml)
    return (-ml) / (-ml + 100.0) if ml < 0 else 100.0 / (ml + 100.0)


def _p_home(r_h: float, r_a: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(r_h - r_a + _HFA) / 400.0))


def _replay(games) -> Tuple[np.ndarray, Dict[str, float]]:
    """Leak-free MOV-aware Elo replay. Returns (pre-game P(home win) array, FINAL ratings).

    Update AFTER each snapshot (leak-free); ratings carry across seasons (light); rows must
    be in chronological order. The final ratings dict is the as-of rating for the NEXT matchup
    of each team — reused by domains/mlb/predictor.py so the predictor's win-prob is the SAME
    engine this proof scores against the close (parity).
    """
    rat: Dict[str, float] = {}
    p = np.empty(len(games))
    h = games["home_team"].to_numpy()
    a = games["away_team"].to_numpy()
    hr = games["home_runs"].to_numpy(float)
    ar = games["away_runs"].to_numpy(float)
    for i in range(len(games)):
        ht, at = str(h[i]), str(a[i])
        rat.setdefault(ht, _INIT)
        rat.setdefault(at, _INIT)
        ph = _p_home(rat[ht], rat[at])
        p[i] = ph                              # SNAPSHOT recorded before update (leak-free)
        s = 1.0 if hr[i] > ar[i] else 0.0
        margin = abs(hr[i] - ar[i])
        elo_diff = (rat[ht] - rat[at] + _HFA) * (1 if s else -1)
        mov = np.log(margin + 1.0) * (2.2 / (elo_diff * 0.001 + 2.2))   # 538 MOV multiplier
        delta = _K * mov * (s - ph)
        rat[ht] += delta
        rat[at] -= delta
    return p, rat


def _walk_forward_elo(games) -> np.ndarray:
    """Pre-game P(home win) array (chronological order assumed). See _replay."""
    return _replay(games)[0]


def final_ratings(games) -> Dict[str, float]:
    """Final as-of MOV-Elo ratings after replaying the full corpus (sorts internally).

    The single source of truth for MLB win-prob: domains/mlb/predictor.py imports this so
    predict() and the beat-the-close measurement use the IDENTICAL engine (W150 parity fix).
    """
    g = games.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    return _replay(g)[1]


def _brier_logloss(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return (float(np.mean((p - y) ** 2)),
            float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))))


def run(corpus: Optional[Path] = None) -> Dict:
    import pandas as pd
    root = corpus or _corpus_from_env()
    games_path = (root / "games.parquet") if root is not None else _GAMES
    odds_path = (root / "odds.parquet") if root is not None else _ODDS
    games = pd.read_parquet(games_path)
    odds = pd.read_parquet(odds_path)[
        ["event_id", "ml_close_home_am", "ml_close_away_am"]]

    # chronological order so the walk-forward Elo is genuinely leak-free
    games = games.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    games["p_model"] = _walk_forward_elo(games)

    # devig the close moneyline -> market P(home win)
    odds = odds.dropna(subset=["ml_close_home_am", "ml_close_away_am"]).copy()
    odds["imp_h"] = odds["ml_close_home_am"].map(american_to_prob)
    odds["imp_a"] = odds["ml_close_away_am"].map(american_to_prob)
    odds["p_market"] = odds["imp_h"] / (odds["imp_h"] + odds["imp_a"])    # devig

    m = games.merge(odds[["event_id", "p_market"]], on="event_id", how="inner")
    m = m.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    n = len(m)
    if n < 60:
        return {"status": "data_limited", "n": n}

    y = (m["home_runs"] > m["away_runs"]).to_numpy(float)
    pm = m["p_model"].to_numpy(float)
    pk = m["p_market"].to_numpy(float)

    # evaluate on the held-out SECOND HALF (model warms up on the first)
    mid = n // 2
    te = slice(mid, n)
    yh = y[te]
    b_model, ll_model = _brier_logloss(pm[te], yh)
    b_mkt, ll_mkt = _brier_logloss(pk[te], yh)
    gap = round(b_model - b_mkt, 4)                  # >0 => market sharper
    corr = round(float(np.corrcoef(pm[te], pk[te])[0, 1]), 3)

    if gap < -0.002:
        verdict = (f"BEATS: OUR Elo beats the close on Brier "
                   f"({b_model:.4f} vs {b_mkt:.4f})")
    elif gap <= 0.005:
        verdict = (f"MATCH: OUR Elo matches the close (Brier {b_model:.4f} vs "
                   f"{b_mkt:.4f}, gap {gap:+}) within noise")
    else:
        verdict = (f"BEHIND: close sharper by {gap} Brier — Elo is pitcher-blind "
                   f"(no starting-pitcher signal the market prices)")

    return {
        "status": "ok", "n": n, "n_holdout": n - mid,
        "model_brier": round(b_model, 4), "close_brier": round(b_mkt, 4),
        "model_logloss": round(ll_model, 4), "close_logloss": round(ll_mkt, 4),
        "gap": gap, "corr": corr,
        "base_home_rate": round(float(yh.mean()), 4),
        "verdict": verdict,
        "note": "Win-prob accuracy vs the devigged close on real outcomes. No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}")
        return 0
    print(f"=== MLB moneyline: OUR leak-free Elo win-prob vs the devigged close "
          f"(n={rep['n']}, holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>13}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'devig close':>13}  {rep['close_brier']:>8} {rep['close_logloss']:>8}")
    print(f"  {'our Elo':>13}  {rep['model_brier']:>8} {rep['model_logloss']:>8}")
    print(f"\nbase home-win rate (holdout) = {rep['base_home_rate']}  |  "
          f"corr(model, market) = {rep['corr']}  |  gap to close: {rep['gap']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
