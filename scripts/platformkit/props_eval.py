"""PROPS EVAL-GATE / calibration readout for soccer (World Cup) player props.

THE QUESTION (north star -- calibration, NOT a $-edge): does the model's
P(over line) match realized outcomes? A Brier near base-rate (no skill) or a high
ECE is an HONEST finding to report, never spun.

  * score_prop_predictions: pure proper-scoring readout; ECE paired with sharpness
    so a collapse-to-0.5 model can NOT look "good".
  * backtest_calibration: LEAK-FREE walk-forward; each match builds its dist from
    data with date < M ONLY, predicts p_over on a .5 line, settles, accumulates.
  * write_calibration_cache: run the backtest and cache per-stat bss so the board
    reads our MEASURED skill cheaply.

DESIGN (honesty): feed REALIZED minutes as e_minutes (tests RATE calibration); .5
line nearest prior mean lam (never pushes); club_priors=True is a current-season
snapshot (mild lookahead, "approx as-of"; absent parquet -> no-op).

Public functions NEVER raise. ASCII only. Per-file test only (full pytest freezes):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval.py -q
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Sequence
from scripts.platformkit.eval_gate import scoring
from scripts.platformkit import prop_tiering
from scripts.platformkit.prop_tiering import load_calibration  # re-export

logger = logging.getLogger(__name__)

_DEFAULT_STATS = [
    "Shots", "Shots On Target", "Fouls", "Fouls Drawn", "Cards",
    "Assists", "Goal+Assist", "Goals", "Offsides", "Saves",
]
_N_BINS = 10


def _reliability_bins(probs: Sequence[float], outs: Sequence[float], bins: int):
    """[{lo, hi, n, mean_p, frac_pos}] per equal-width bin (empty bins omitted)."""
    out = []
    edges = [k / bins for k in range(bins + 1)]
    for k in range(bins):
        lo, hi = edges[k], edges[k + 1]
        idx = [i for i, p in enumerate(probs)
               if (lo <= p < hi) or (k == bins - 1 and p == hi)]
        if not idx:
            continue
        out.append({
            "lo": round(lo, 3), "hi": round(hi, 3), "n": len(idx),
            "mean_p": round(sum(probs[i] for i in idx) / len(idx), 4),
            "frac_pos": round(sum(outs[i] for i in idx) / len(idx), 4),
        })
    return out


def score_prop_predictions(preds: Sequence[dict]) -> Dict[str, object]:
    """Pure scorer over a list of {p_over: float, outcome: 0|1}.

    Returns {n, brier, ece, log_loss, hit_rate, mean_p, sharpness,
    reliability_bins, base_rate, brier_base, brier_skill_score}. ECE is paired
    with sharpness so a collapse-to-0.5 model is exposed; bss is vs the empirical
    base-rate reference. Never raises -> {"n": 0, ...} on empty / bad input.
    """
    _keys = ("brier", "ece", "log_loss", "hit_rate", "mean_p", "sharpness",
             "base_rate", "brier_base", "brier_skill_score")
    empty = {"n": 0, "reliability_bins": [], **{k: None for k in _keys}}
    try:
        ps: List[float] = []
        ys: List[float] = []
        for r in preds or []:
            p, y = r.get("p_over"), r.get("outcome")
            if p is None or y is None:
                continue
            pf = float(p)
            if not math.isfinite(pf):
                continue
            ps.append(min(1.0, max(0.0, pf)))
            ys.append(1.0 if float(y) > 0.5 else 0.0)
        n = len(ps)
        if n == 0:
            return dict(empty)
        base = sum(ys) / n
        ref = [base] * n
        brier = scoring.brier(ps, ys)
        ece = scoring.ece(ps, ys, _N_BINS)
        ll = scoring.log_loss(ps, ys)
        bss = scoring.brier_skill_score(ps, ref, ys)
        hit = sum(1.0 for p, y in zip(ps, ys) if (p >= 0.5) == (y > 0.5)) / n
        mean_p = sum(ps) / n
        return {
            "n": n, "brier": round(brier, 5), "ece": round(ece, 5),
            "log_loss": round(ll, 5), "hit_rate": round(hit, 4),
            "mean_p": round(mean_p, 4), "sharpness": round(scoring.sharpness(ps), 5),
            "reliability_bins": _reliability_bins(ps, ys, _N_BINS),
            "base_rate": round(base, 4), "brier_base": round(scoring.brier(ref, ys), 5),
            "brier_skill_score": round(bss, 4),
        }
    except Exception:  # noqa: BLE001 -- public fn must never raise
        return dict(empty)


def _nearest_half_line(lam: float) -> float:
    """The .5 line nearest prior mean lam (>=0.5; never pushes):
    round(lam-0.5)+0.5, clamped to a minimum of 0.5."""
    if lam is None or not math.isfinite(lam) or lam < 0:
        return 0.5
    line = round(lam - 0.5) + 0.5
    return line if line >= 0.5 else 0.5


def _match_order(df):
    """(event_id, date) pairs in chronological date order. [] on bad input."""
    try:
        import pandas as pd
        if df is None or len(df) == 0 or "event_id" not in df.columns \
                or "date" not in df.columns:
            return []
        sub = df[["event_id", "date"]].copy()
        sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
        sub = sub.dropna(subset=["date"]).drop_duplicates("event_id").sort_values("date")
        return list(zip(sub["event_id"].tolist(), sub["date"].tolist()))
    except Exception:  # noqa: BLE001
        return []


def _collect_per_stat_preds(df, use_stats, club_priors, opp_adjust=False):
    """Shared LEAK-FREE pred-gen loop -> (per_stat_preds, club_missing).

    per_stat_preds maps stat -> [{"p_over": float, "outcome": 0|1}, ...]. Returns
    (None, False) if deps / data are unavailable. Never raises. Both
    backtest_calibration and backtest_pairs build on this, so the (p, outcome)
    pairs the readout scores are the SAME pairs the recalibrator fits on.
    ``opp_adjust``=True passes a LEAK-FREE opponent multiplier (the OTHER team_abbr
    in that event, data < as_of only); when False the loop is byte-for-byte prior.
    """
    try:
        import pandas as pd  # noqa: F401
        from domains.soccer.dispersion import all_dispersions
        from domains.soccer.prop_engine import prop_distribution
        from domains.soccer.prop_settle import realized_stat
        if opp_adjust:
            from domains.soccer.team_defense import all_multipliers
            from scripts.platformkit.soccer_team_map import opponent_for_team
        if club_priors:
            from domains.soccer.ingest_espn_athlete import club_prior as _club_prior
    except Exception:  # noqa: BLE001
        return None, False
    if df is None or len(df) == 0:
        return None, False
    matches = _match_order(df)
    if not matches:
        return None, False
    per_stat_preds: Dict[str, List[dict]] = {s: [] for s in use_stats}
    club_missing = False

    for event_id, as_of in matches:
        try:
            played = df[df["event_id"].astype(str) == str(event_id)]
        except Exception:  # noqa: BLE001
            continue
        if len(played) == 0:
            continue
        try:
            disp = all_dispersions(df, as_of)
        except Exception:  # noqa: BLE001
            disp = {}
        # Per event: opponent multipliers, computed ONCE per opponent abbr (the
        # allowed-table is the same for every row vs the same opponent at as_of).
        event_teams = None
        opp_mults: Dict[str, Dict[str, float]] = {}
        if opp_adjust and "team_abbr" in played.columns:
            try:
                event_teams = [str(t) for t in played["team_abbr"].dropna().unique()]
            except Exception:  # noqa: BLE001
                event_teams = None
            for ta in (event_teams or []):
                opp = opponent_for_team(event_teams, ta)
                if opp is not None and opp not in opp_mults:
                    opp_mults[opp] = all_multipliers(df, opp, as_of)
        for _, row in played.iterrows():
            pid = row.get("player_id")
            try:
                mins = float(row.get("minutes"))
            except (TypeError, ValueError):
                continue
            if not math.isfinite(mins) or mins <= 0.0:
                continue
            position = row.get("position")
            opp_abbr = None
            if opp_adjust and event_teams is not None:
                opp_abbr = opponent_for_team(event_teams, row.get("team_abbr"))
            for stat in use_stats:
                r = disp.get(stat, {}).get("r")  # NB size from leak-free dispersion
                cp = None
                if club_priors:
                    cp = _club_prior(pid, stat)
                    if isinstance(cp, dict) and cp.get("status") != "ok":
                        club_missing = True
                om = 1.0
                if opp_adjust and opp_abbr is not None:
                    m = opp_mults.get(opp_abbr, {}).get(stat, 1.0)
                    om = float(m) if isinstance(m, (int, float)) else 1.0
                dist = prop_distribution(df, pid, stat, as_of, e_minutes=mins,
                                         position=position, opp_mult=om,
                                         dispersion=r, club_prior=cp)
                if dist.get("status") != "ok" or not callable(dist.get("p_over")):
                    continue
                lam = dist.get("lam")
                line = _nearest_half_line(float(lam) if lam is not None else 0.5)
                p = dist["p_over"](line)
                if not isinstance(p, float) or math.isnan(p):
                    continue
                realized = realized_stat(df, pid, event_id, stat)
                if realized is None:
                    continue
                outcome = 1 if float(realized) > line else 0
                per_stat_preds[stat].append(
                    {"p_over": p, "outcome": outcome, "date": as_of})
    return per_stat_preds, club_missing


def backtest_pairs(df, *, stats: Optional[Sequence[str]] = None,
                   club_priors: bool = False, opp_adjust: bool = False,
                   with_dates: bool = False) -> Dict[str, List[tuple]]:
    """LEAK-FREE (p_over, outcome) pairs per stat -- the raw material a per-stat
    recalibrator fits on. {stat: [(p, 0|1), ...]} (empty lists if unavailable).
    Never raises. Same pred-gen loop as backtest_calibration. ``opp_adjust`` feeds
    the leak-free opponent multiplier (the other team in each event).

    ``with_dates``=True (ADDITIVE) returns 3-tuples (p, 0|1, match_date) per stat
    so callers can split the leak-free pairs TEMPORALLY by match for an honest OOS
    recalibration test. Default False keeps the 2-tuple shape byte-for-byte."""
    use_stats = list(stats) if stats else list(_DEFAULT_STATS)
    try:
        per_stat_preds, _ = _collect_per_stat_preds(
            df, use_stats, club_priors, opp_adjust=opp_adjust)
        if per_stat_preds is None:
            return {s: [] for s in use_stats}
        if with_dates:
            return {s: [(d["p_over"], d["outcome"], d.get("date"))
                        for d in per_stat_preds[s]] for s in use_stats}
        return {s: [(d["p_over"], d["outcome"]) for d in per_stat_preds[s]]
                for s in use_stats}
    except Exception:  # noqa: BLE001 -- public fn must never raise
        return {s: [] for s in use_stats}


def backtest_calibration(df, *, stats: Optional[Sequence[str]] = None,
                         club_priors: bool = False, lines=None,
                         opp_adjust: bool = False) -> Dict[str, object]:
    """Leak-free walk-forward calibration backtest over WC matches.

    For each match M (date order)/player/stat: as_of=M's date; the engine builds
    the rate/dispersion from data with date < as_of ONLY. We feed REALIZED minutes
    as e_minutes (tests RATE calibration, not minutes), apply the NB dispersion,
    predict p_over on the .5 line nearest lam, and settle outcome=realized>line.
    Engine status != ok (no prior yet) is SKIPPED -- only real predictions score.
    club_priors=True augments with the ESPN club prior (current-season snapshot ->
    "approx as-of"). ``opp_adjust``=True applies the LEAK-FREE opponent multiplier
    (the other team in each event, data < as_of only) -- an honest OOS test of
    whether the opponent lever IMPROVES calibration. ``lines`` accepted for API
    compat. Returns {mode, n, stats, overall, per_stat, note}. Never raises.
    """
    mode = "club-augmented (approx as-of)" if club_priors else "strict leak-free"
    if opp_adjust:
        mode += " +opp-adj"
    base = {"mode": mode, "n": 0, "stats": [], "overall": score_prop_predictions([]),
            "per_stat": {}, "note": ""}
    use_stats = list(stats) if stats else list(_DEFAULT_STATS)
    per_stat_preds, club_missing = _collect_per_stat_preds(
        df, use_stats, club_priors, opp_adjust=opp_adjust)
    if per_stat_preds is None:
        return base

    all_preds: List[dict] = []
    per_stat: Dict[str, object] = {}
    for stat in use_stats:
        pr = per_stat_preds[stat]
        all_preds.extend(pr)
        per_stat[stat] = score_prop_predictions(pr)

    overall = score_prop_predictions(all_preds)
    if club_priors:
        note = "club-augmented, approx as-of: current-season snapshot (mild lookahead)."
        if club_missing:
            note += " WARNING: club parquet absent/partial -> ~strict leak-free."
    else:
        note = ("strict leak-free: WC-history only; early matches skipped (no prior), "
                "so n is THIN -- read the verdict with that caveat.")
    return {
        "mode": mode, "n": overall.get("n", 0), "stats": use_stats,
        "overall": overall, "per_stat": per_stat, "note": note,
    }


def write_calibration_cache(df=None, *, club_priors: bool = False,
                            opp_adjust: bool = False,
                            out_path: Optional[str] = None) -> Dict[str, object]:
    """Run the (strict leak-free by default) backtest and CACHE its per-stat bss to
    prop_calibration.json so the board reads our MEASURED skill cheaply. Loads the
    default parquet when *df* is None. ``opp_adjust`` must MATCH the live board's
    setting so the cached tier BSS reflects the model that actually prices the
    board. NEVER raises -> payload (with "written": bool). HONEST OOS calibration,
    NOT a $-edge."""
    try:
        if df is None:
            import os
            import pandas as pd  # local guarded import
            df = pd.read_parquet(os.path.join(
                "data", "domains", "soccer", "espn_player_stats.parquet"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration parquet read failed: %s", exc)
        df = None
    res = backtest_calibration(df, club_priors=club_priors, opp_adjust=opp_adjust)
    payload = prop_tiering.build_calibration_payload(res)
    payload["written"] = prop_tiering.write_calibration_cache_json(
        payload, out_path or prop_tiering.CALIBRATION_PATH)
    return payload


def _fmt_row(name: str, d: dict) -> str:
    def g(k):
        v = d.get(k)
        return "  -  " if v is None else f"{v:>6}"
    return (f"{name:<18} n={d.get('n', 0):>5}  brier={g('brier')}  "
            f"ece={g('ece')}  hit={g('hit_rate')}  meanP={g('mean_p')}  "
            f"base={g('base_rate')}  bss={g('brier_skill_score')}")


def _print_readout(res: dict) -> None:
    bar = "-" * 92
    print("=" * 92)
    print("PROPS CALIBRATION READOUT  [%s]\n%s\n%s\n%s" % (
        res.get("mode"), bar, res.get("note", ""), bar))
    for stat in res.get("stats", []):
        d = res.get("per_stat", {}).get(stat)
        if d and d.get("n", 0) > 0:
            print(_fmt_row(stat, d))
    print("%s\n%s\n%s" % (bar, _fmt_row("OVERALL", res.get("overall", {})),
                          "=" * 92))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: python -m scripts.platformkit.props_eval [--club-priors] [--cache]."""
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Soccer props calibration readout.")
    parser.add_argument("--club-priors", action="store_true",
                        help="augment rate with ESPN club prior (approx as-of).")
    parser.add_argument("--opp-adjust", action="store_true",
                        help="apply the leak-free opponent multiplier.")
    parser.add_argument("--data", default=None, help="player-stats parquet path.")
    parser.add_argument("--cache", action="store_true", help="write cache JSON.")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    data_path = Path(args.data) if args.data else (
        repo / "data" / "domains" / "soccer" / "espn_player_stats.parquet")
    try:
        import pandas as pd
        df = pd.read_parquet(data_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read {data_path}: {exc}")
        return 1
    _print_readout(backtest_calibration(
        df, club_priors=args.club_priors, opp_adjust=args.opp_adjust))
    if args.cache:
        pl = write_calibration_cache(
            df, club_priors=args.club_priors, opp_adjust=args.opp_adjust)
        print("cache written=%s -> %s" % (pl.get("written"),
                                          prop_tiering.CALIBRATION_PATH))
    return 0


__all__ = ["score_prop_predictions", "backtest_calibration", "backtest_pairs",
           "write_calibration_cache", "load_calibration", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
