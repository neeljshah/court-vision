"""scripts.platformkit.ingame.ingame_tail_scan -- price-band (tail) miscalibration scan.

THE QUESTION (user thesis 2026-07-02): are in-play LONGSHOT prices flawed?  I.e. in the
tail price bands (venue prob < 0.20 or > 0.80), does the venue's in-play price diverge
from the REALIZED outcome rate -- and does OUR live model price those states better?

Method (leak-free, outcome-graded, game-clustered):
  * Reuses the same data/cache/ingame_grade/<sport>/*.jsonl tick layout as live_grade.
  * Outcome per game: Kalshi tickers via ingame_outcome_label.OutcomeResolver; numeric
    ESPN ids via espn_boxscores.parquet finals.  Unresolvable game -> skipped (honest).
  * Every tick lands in a price band by MARKET prob; per band we compare
      realized outcome rate  vs  mean venue price   (venue_gap  = realized - market)
      model Brier            vs  market Brier       (delta_brier = model - market, <0 = model better)
  * Ticks within a game share one outcome -> all CIs are GAME-clustered bootstrap.
  * Below MIN_GAMES_BAND distinct games a band reads INSUFFICIENT_DATA, never a verdict.

HONESTY: this is a CALIBRATION measurement of venue prices vs outcomes.  It is NOT a $
edge claim; fees, fills and adverse selection are not modeled here (that is the
edge_greenlight ladder's job).  edge_claimed is ALWAYS False.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry write;
no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_scan.py -q
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_BOX_PARQUET = _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
DEFAULT_OUT = _REPO_ROOT / "data" / "frontend" / "ops" / "ingame_tail_scan.json"

BAND_EDGES: List[float] = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 1.0]
TAIL_BANDS = {"[0.00,0.10)", "[0.10,0.20)", "[0.80,0.90)", "[0.90,1.00]"}
MIN_GAMES_BAND: int = 8      # distinct games per band before any verdict
BOOTSTRAP_ITERS: int = 2000
SEED: int = 13


def _band_label(p: float) -> str:
    for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:]):
        if lo <= p < hi or (hi == 1.0 and p == 1.0):
            close = "]" if hi == 1.0 else ")"
            return "[%.2f,%.2f%s" % (lo, hi, close)
    return "UNK"


# --------------------------------------------------------------------------------------- #
# outcome resolution                                                                      #
# --------------------------------------------------------------------------------------- #
def build_outcome_lookup(box_parquet: Optional[Path] = None) -> Callable[[str], Optional[int]]:
    """Return stem -> home_win in {0,1} or None.  Kalshi tickers go through the
    existing OutcomeResolver; bare numeric stems hit the ESPN finals parquet."""
    from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver
    resolver = MlbOutcomeResolver(box_parquet=box_parquet or DEFAULT_BOX_PARQUET)
    espn: Dict[str, int] = {}
    try:
        import pandas as pd
        df = pd.read_parquet(box_parquet or DEFAULT_BOX_PARQUET)
        fin = df[df["status"].astype(str).str.contains("FINAL", case=False, na=False)]
        for _, r in fin.iterrows():
            hs, as_ = float(r["home_score"]), float(r["away_score"])
            if hs != as_:
                espn[str(r["event_id"])] = int(hs > as_)
    except Exception:
        pass

    def lookup(stem: str) -> Optional[int]:
        if stem.isdigit():
            return espn.get(stem)
        return resolver.home_win(stem)
    return lookup


# --------------------------------------------------------------------------------------- #
# tick loading                                                                             #
# --------------------------------------------------------------------------------------- #
def _first_ts(path: Path) -> Optional[str]:
    """ISO ts of the first parseable tick, or None. ISO-Z strings compare lexically."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts = json.loads(line).get("ts")
                except Exception:
                    continue
                if isinstance(ts, str):
                    return ts
    except OSError:
        return None
    return None


def _load_game_ticks(path: Path) -> List[Tuple[float, float]]:
    """Return [(market_prob_home, model_prob_home)] for one grade file; bad rows skipped."""
    out: List[Tuple[float, float]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                mkt, mdl = d.get("market_prob"), d.get("model_prob")
                if not isinstance(mkt, (int, float)) or not isinstance(mdl, (int, float)):
                    continue
                if not (0.0 < float(mkt) < 1.0 and 0.0 < float(mdl) < 1.0):
                    continue
                if str(d.get("side", "home")).lower() == "away":
                    mkt, mdl = 1.0 - float(mkt), 1.0 - float(mdl)
                out.append((float(mkt), float(mdl)))
    except OSError:
        return []
    return out


# --------------------------------------------------------------------------------------- #
# scan                                                                                     #
# --------------------------------------------------------------------------------------- #
def _band_stats(rows: List[Tuple[str, float, float, int]],
                iters: int = BOOTSTRAP_ITERS, seed: int = SEED) -> Dict[str, Any]:
    """rows = [(game_id, market, model, outcome)] for ONE band."""
    games = sorted({r[0] for r in rows})
    n_g, n_t = len(games), len(rows)
    mean_mkt = sum(r[1] for r in rows) / n_t
    mean_mdl = sum(r[2] for r in rows) / n_t
    realized = sum(r[3] for r in rows) / n_t
    b_mkt = sum((r[1] - r[3]) ** 2 for r in rows) / n_t
    b_mdl = sum((r[2] - r[3]) ** 2 for r in rows) / n_t
    out: Dict[str, Any] = {
        "n_ticks": n_t, "n_games": n_g,
        "mean_market": round(mean_mkt, 4), "mean_model": round(mean_mdl, 4),
        "realized_rate": round(realized, 4),
        "venue_gap": round(realized - mean_mkt, 4),
        "brier_market": round(b_mkt, 5), "brier_model": round(b_mdl, 5),
        "delta_brier": round(b_mdl - b_mkt, 5),
    }
    if n_g < MIN_GAMES_BAND:
        out.update(venue_verdict="INSUFFICIENT_DATA", model_verdict="INSUFFICIENT_DATA",
                   venue_gap_ci95=None, delta_brier_ci95=None)
        return out
    by_game: Dict[str, List[Tuple[str, float, float, int]]] = {}
    for r in rows:
        by_game.setdefault(r[0], []).append(r)
    rng = random.Random(seed)
    gaps: List[float] = []
    deltas: List[float] = []
    for _ in range(iters):
        sample: List[Tuple[str, float, float, int]] = []
        for _ in range(n_g):
            sample.extend(by_game[games[rng.randrange(n_g)]])
        nt = len(sample)
        gaps.append(sum(r[3] for r in sample) / nt - sum(r[1] for r in sample) / nt)
        deltas.append(sum((r[2] - r[3]) ** 2 for r in sample) / nt
                      - sum((r[1] - r[3]) ** 2 for r in sample) / nt)
    gaps.sort(); deltas.sort()
    lo_i, hi_i = int(0.025 * iters), min(int(0.975 * iters), iters - 1)
    g_ci = (round(gaps[lo_i], 4), round(gaps[hi_i], 4))
    d_ci = (round(deltas[lo_i], 5), round(deltas[hi_i], 5))
    out["venue_gap_ci95"] = list(g_ci)
    out["delta_brier_ci95"] = list(d_ci)
    if g_ci[0] > 0:
        out["venue_verdict"] = "VENUE_UNDERPRICES"   # realized > price: longshot too cheap
    elif g_ci[1] < 0:
        out["venue_verdict"] = "VENUE_OVERPRICES"    # realized < price: longshot too dear
    else:
        out["venue_verdict"] = "CALIBRATED"
    if d_ci[1] < 0:
        out["model_verdict"] = "MODEL_BETTER"
    elif d_ci[0] > 0:
        out["model_verdict"] = "MARKET_BETTER"
    else:
        out["model_verdict"] = "MATCH"
    return out


def scan(grade_dir: Optional[Path] = None, sport: str = "mlb",
         outcome_lookup: Optional[Callable[[str], Optional[int]]] = None,
         iters: int = BOOTSTRAP_ITERS, since: Optional[str] = None) -> Dict[str, Any]:
    """Run the band scan.  Returns the full result dict (also suitable for the artifact).

    since: ISO-Z timestamp; games whose FIRST tick predates it are excluded.  This is the
    pre-registration filter -- forward evidence must come from games captured AFTER the
    hypothesis was registered (see ingame_tail_gate)."""
    base = (Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR) / sport.lower()
    files = sorted(base.glob("*.jsonl")) if base.is_dir() else []
    files = [f for f in files if not f.name.startswith("_")]
    lookup = outcome_lookup or build_outcome_lookup()
    rows_by_band: Dict[str, List[Tuple[str, float, float, int]]] = {}
    n_resolved = n_unresolved = n_pre_reg = 0
    for f in files:
        if since is not None:
            ts = _first_ts(f)
            if ts is None or ts < since:
                n_pre_reg += 1
                continue
        outcome = lookup(f.stem)
        if outcome is None:
            n_unresolved += 1
            continue
        ticks = _load_game_ticks(f)
        if not ticks:
            continue
        n_resolved += 1
        for mkt, mdl in ticks:
            rows_by_band.setdefault(_band_label(mkt), []).append((f.stem, mkt, mdl, outcome))
    bands: Dict[str, Any] = {}
    for label in sorted(rows_by_band):
        bands[label] = _band_stats(rows_by_band[label], iters=iters)
    tail_rows = [r for b, rs in rows_by_band.items() if b in TAIL_BANDS for r in rs]
    mid_rows = [r for b, rs in rows_by_band.items() if b not in TAIL_BANDS for r in rs]
    pooled = {
        "TAILS": _band_stats(tail_rows, iters=iters) if tail_rows else None,
        "MIDS": _band_stats(mid_rows, iters=iters) if mid_rows else None,
    }
    from datetime import datetime, timezone
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": "m_ingame_tail_scan", "sport": sport,
        "note": ("venue in-play price calibration vs realized outcomes by price band; "
                 "game-clustered bootstrap CIs; calibration measurement, NOT a $ edge "
                 "(no fees/fills modeled)"),
        "n_games_resolved": n_resolved, "n_games_unresolved": n_unresolved,
        "n_games_pre_registration": n_pre_reg, "since": since,
        "min_games_band": MIN_GAMES_BAND,
        "bands": bands, "pooled": pooled, "edge_claimed": False,
    }


def write_artifact(result: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    p = Path(out_path) if out_path is not None else DEFAULT_OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def _fmt_row(label: str, s: Dict[str, Any]) -> str:
    return ("%-14s g=%-4d t=%-6d mkt=%.3f real=%.3f gap=%+.3f %-18s "
            "dBrier=%+.4f %s" % (label, s["n_games"], s["n_ticks"], s["mean_market"],
                                 s["realized_rate"], s["venue_gap"], s["venue_verdict"],
                                 s["delta_brier"], s["model_verdict"]))


def main() -> None:
    result = scan()
    print("in-game price-band scan (%s): %d games resolved, %d unresolved" %
          (result["sport"], result["n_games_resolved"], result["n_games_unresolved"]))
    for label, s in result["bands"].items():
        print("  " + _fmt_row(label, s))
    for label in ("TAILS", "MIDS"):
        s = result["pooled"].get(label)
        if s:
            print("  " + _fmt_row(label, s))
    path = write_artifact(result)
    print("artifact: %s" % path)
    print("NOTE: calibration measurement only -- fees/fills not modeled; no edge claimed.")


if __name__ == "__main__":
    main()
