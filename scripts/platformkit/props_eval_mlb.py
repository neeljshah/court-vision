"""PROPS EVAL-GATE / calibration readout for MLB player props.

THE QUESTION (north star -- calibration, NOT a $-edge): does the MLB engine's
P(over line) match realized outcomes? A negative / null BSS or a high ECE on some
stat is an HONEST finding to report, never spun. The MLB engine likely projects
multi-outcome counting stats (Total Bases, RBIs, Runs) too high; this backtest
reveals which MLB stats are actually calibrated.

DESIGN (honesty, mirrors props_eval.py for soccer):
  * Walk-forward over MLB games by date. For each game G (as_of = G's date), the
    engine builds its rate from data with date < as_of ONLY (LEAK-FREE).
  * We feed the player's REALIZED exposure in G as ``exposure`` (PA proxy =
    atBats+baseOnBalls+hitByPitch for batters; battersFaced for pitchers; the
    per-start path needs no exposure) -- so we test RATE / shape calibration, NOT
    the exposure projection.
  * Representative line: the .5 line nearest the player's prior-mean lam (per stat;
    never pushes). outcome = realized stat in G > line.
  * Engine status != ok (no prior yet) is SKIPPED -- only real predictions score.
  * score_prop_predictions (IMPORTED from props_eval, sport-agnostic) does the
    proper-scoring readout; ECE is paired with sharpness so a collapse-to-0.5
    model can NOT look "good". bss is vs the empirical base-rate reference.

Public functions NEVER raise. ASCII only. Per-file test only (full pytest freezes):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval_mlb.py -q
"""
from __future__ import annotations

import logging
import math
import os
from typing import Dict, List, Optional, Sequence

from scripts.platformkit import prop_tiering
from scripts.platformkit.prop_tiering import load_calibration  # re-export
from scripts.platformkit.props_eval import (  # sport-agnostic scorer + line helper
    _nearest_half_line,
    score_prop_predictions,
)

logger = logging.getLogger(__name__)

# Default MLB calibration cache path (sport-specific; same JSON shape as soccer so
# prop_tiering's loader / classify / apply_tier reuse works unchanged).
CALIBRATION_PATH_MLB = os.path.join(
    "data", "domains", "mlb", "prop_calibration.json")
_DEFAULT_DATA = os.path.join("data", "domains", "mlb", "player_gamelogs.parquet")


def _game_order(df):
    """(game_pk, as_of) pairs in chronological date order. [] on bad input."""
    try:
        import pandas as pd
        if df is None or len(df) == 0 or "game_pk" not in df.columns \
                or "date" not in df.columns:
            return []
        sub = df[["game_pk", "date"]].copy()
        sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
        sub = sub.dropna(subset=["date"]).drop_duplicates("game_pk")
        sub = sub.sort_values(["date", "game_pk"])
        return list(zip(sub["game_pk"].tolist(), sub["date"].tolist()))
    except Exception:  # noqa: BLE001
        return []


def _num(row, col):
    """Numeric cell value (0.0 on missing / non-finite). Never raises."""
    try:
        v = float(row.get(col))
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _realized_exposure(row, is_pitcher, per_start):
    """Player's REALIZED exposure in this game.

    batter -> PA proxy (atBats+baseOnBalls+hitByPitch); pitcher per-BF ->
    battersFaced; per-start (Outs) -> None (engine models it per start, no
    exposure). Returns None when the relevant exposure is 0 (player didn't appear
    in that role)."""
    if per_start:
        return None
    if is_pitcher:
        bf = _num(row, "battersFaced")
        return bf if bf > 0.0 else None
    pa = _num(row, "atBats") + _num(row, "baseOnBalls") + _num(row, "hitByPitch")
    return pa if pa > 0.0 else None


def _realized_stat(row, cols):
    """Sum of the canonical stat's raw columns in this game row. Never raises."""
    return sum(_num(row, c) for c in (cols or []))


def _collect_per_stat_preds(df, use_stats):
    """Shared LEAK-FREE pred-gen loop -> per_stat_preds (or None on bad deps/data).

    per_stat_preds maps stat -> [{"p_over", "outcome", "date"}, ...]. For each game
    (date order) / player-row / modeled stat: builds the dist from date < as_of
    ONLY, feeding the REALIZED exposure so only RATE/shape calibration is tested.
    Never raises.
    """
    try:
        import pandas as pd  # noqa: F401
        from domains.mlb.player_rates_mlb import MLB_CANON, PER_START_STATS
        from domains.mlb.prop_engine_mlb import prop_distribution
    except Exception:  # noqa: BLE001
        return None
    try:
        if df is None or len(df) == 0:
            return None
    except Exception:  # noqa: BLE001 -- non-frame input
        return None
    games = _game_order(df)
    if not games:
        return None
    stats = [s for s in use_stats if s in MLB_CANON]
    if not stats:
        return None
    per_stat_preds: Dict[str, List[dict]] = {s: [] for s in stats}
    pk_is_str = None

    for game_pk, as_of in games:
        try:
            if pk_is_str is None:
                pk_is_str = df["game_pk"].dtype == object
            played = df[df["game_pk"] == game_pk] if not pk_is_str \
                else df[df["game_pk"].astype(str) == str(game_pk)]
        except Exception:  # noqa: BLE001
            continue
        if len(played) == 0:
            continue
        for _, row in played.iterrows():
            pid = row.get("player_id")
            try:
                is_pit = bool(row.get("is_pitcher"))
            except Exception:  # noqa: BLE001
                is_pit = False
            batting_order = row.get("batting_order")
            for stat in stats:
                spec = MLB_CANON[stat]
                # only score a stat for the role that actually owns it
                if (spec.get("role") == "pitcher") != is_pit:
                    continue
                per_start = stat in PER_START_STATS
                exposure = _realized_exposure(row, is_pit, per_start)
                if not per_start and (exposure is None):
                    continue  # player didn't take the field in this role
                dist = prop_distribution(
                    df, pid, stat, as_of, exposure=exposure,
                    batting_order=batting_order)
                if dist.get("status") != "ok" or not callable(dist.get("p_over")):
                    continue
                lam = dist.get("lam")
                line = _nearest_half_line(
                    float(lam) if lam is not None else 0.5)
                p = dist["p_over"](line)
                if not isinstance(p, float) or math.isnan(p):
                    continue
                realized = _realized_stat(row, spec.get("cols"))
                outcome = 1 if float(realized) > line else 0
                per_stat_preds[stat].append(
                    {"p_over": p, "outcome": outcome, "date": as_of})
    return per_stat_preds


def backtest_calibration_mlb(
    df, *, stats: Optional[Sequence[str]] = None, lines=None,
) -> Dict[str, object]:
    """Leak-free walk-forward calibration backtest over MLB games.

    For each game G (date order) / player / modeled MLB stat: as_of = G's date; the
    engine builds the rate from data with date < as_of ONLY. We feed the player's
    REALIZED exposure in G as ``exposure`` (PA proxy for batters; battersFaced for
    pitchers; per-start Outs needs none) -- so this tests RATE / shape calibration,
    NOT the exposure projection. Representative line = .5 line nearest lam (never
    pushes); outcome = realized > line. Engine status != ok (no prior) is SKIPPED.
    ``lines`` accepted for API compat. Returns {mode, n, stats, overall, per_stat,
    note}. Never raises.
    """
    mode = "strict leak-free (realized exposure)"
    base = {"mode": mode, "n": 0, "stats": [],
            "overall": score_prop_predictions([]), "per_stat": {}, "note": ""}
    try:
        from domains.mlb.player_rates_mlb import MLB_CANON
        use_stats = list(stats) if stats else list(MLB_CANON.keys())
    except Exception:  # noqa: BLE001
        return base
    per_stat_preds = _collect_per_stat_preds(df, use_stats)
    if per_stat_preds is None:
        return base
    ordered = [s for s in use_stats if s in per_stat_preds]
    all_preds: List[dict] = []
    per_stat: Dict[str, object] = {}
    for stat in ordered:
        pr = per_stat_preds[stat]
        all_preds.extend(pr)
        per_stat[stat] = score_prop_predictions(pr)
    overall = score_prop_predictions(all_preds)
    note = ("strict leak-free: MLB gamelog history only; early games skipped (no "
            "prior). Realized exposure fed -> RATE/shape calibration, not exposure. "
            "No $-edge claim; calibration is the yardstick.")
    return {
        "mode": mode, "n": overall.get("n", 0), "stats": ordered,
        "overall": overall, "per_stat": per_stat, "note": note,
    }


def write_calibration_cache_mlb(
    df=None, *, out_path: Optional[str] = None,
) -> Dict[str, object]:
    """Run the leak-free MLB backtest and CACHE its per-stat bss to
    prop_calibration.json (sport:"mlb") so the board reads MEASURED skill cheaply.
    Loads the default gamelogs parquet when *df* is None. Atomic write via
    prop_tiering.write_calibration_cache_json. NEVER raises -> payload (with
    "written": bool). HONEST OOS calibration, NOT a $-edge."""
    try:
        if df is None:
            import pandas as pd  # local guarded import
            df = pd.read_parquet(_DEFAULT_DATA)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MLB calibration parquet read failed: %s", exc)
        df = None
    res = backtest_calibration_mlb(df)
    payload = prop_tiering.build_calibration_payload(res)
    payload["sport"] = "mlb"
    payload["written"] = prop_tiering.write_calibration_cache_json(
        payload, out_path or CALIBRATION_PATH_MLB)
    return payload


def _fmt_row(name: str, d: dict) -> str:
    def g(k):
        v = d.get(k)
        return "  -  " if v is None else f"{v:>6}"
    return (f"{name:<20} n={d.get('n', 0):>5}  brier={g('brier')}  "
            f"ece={g('ece')}  hit={g('hit_rate')}  meanP={g('mean_p')}  "
            f"base={g('base_rate')}  bss={g('brier_skill_score')}")


def _print_readout(res: dict) -> None:
    bar = "-" * 100
    print("=" * 100)
    print("MLB PROPS CALIBRATION READOUT  [%s]\n%s\n%s\n%s" % (
        res.get("mode"), bar, res.get("note", ""), bar))
    for stat in res.get("stats", []):
        d = res.get("per_stat", {}).get(stat)
        if d and d.get("n", 0) > 0:
            print(_fmt_row(stat, d))
    print("%s\n%s\n%s" % (bar, _fmt_row("OVERALL", res.get("overall", {})),
                          "=" * 100))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: python -m scripts.platformkit.props_eval_mlb [--data P] [--cache]."""
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="MLB props calibration readout.")
    parser.add_argument("--data", default=None, help="gamelogs parquet path.")
    parser.add_argument("--cache", action="store_true", help="write cache JSON.")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    data_path = Path(args.data) if args.data else (repo / _DEFAULT_DATA)
    try:
        import pandas as pd
        df = pd.read_parquet(data_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read {data_path}: {exc}")
        return 1
    _print_readout(backtest_calibration_mlb(df))
    if args.cache:
        pl = write_calibration_cache_mlb(df)
        print("cache written=%s -> %s" % (pl.get("written"), CALIBRATION_PATH_MLB))
    return 0


__all__ = [
    "backtest_calibration_mlb", "write_calibration_cache_mlb",
    "score_prop_predictions", "load_calibration", "CALIBRATION_PATH_MLB", "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
