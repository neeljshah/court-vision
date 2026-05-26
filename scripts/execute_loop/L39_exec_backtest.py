"""
L39 Execution Backtest Harness — simulate historical bet execution vs real closing lines.

Public API:
    run_exec_backtest(lines_csv, *, initial_bankroll, kelly_frac, edge_threshold_pct, save)
    compute_per_stat_breakdown(bets_df)
    compute_drawdown_series(pnl_series)
    bootstrap_ci(returns, n)

Run:
    python L39_exec_backtest.py run --lines path.csv --kelly 0.25 --edge 5.0
    python L39_exec_backtest.py compare --runs id1,id2

Environment Variables:
    none
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import logging
import math
import os
import random
import sys
import tempfile
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_PROJECT_DIR = _HERE.parents[1]
_RESULTS_DIR = _HERE / "results"
_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REQUIRED_COLS = {
    "date", "player", "opp", "venue", "stat",
    "closing_line", "over_odds", "under_odds", "actual_value",
}

_SIGMA_FIX: Dict[str, float] = {
    "pts": 1.07,
    "reb": 1.07,
    "ast": 0.99,
    "fg3m": 1.44,
    "stl": 1.76,
    "blk": 1.95,
    "tov": 1.30,
}

# Implied win probability at -110 juice: 110/(110+100) = 0.5238...
_BREAKEVEN_PROB = 11.0 / 21.0  # ~0.52381

_MAX_STAKE_PCT = 0.05  # 5% bankroll hard cap


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class BacktestRun:
    run_id: str
    start_date: str
    end_date: str
    n_bets: int
    total_stake: float
    total_pnl: float
    roi_pct: float
    hit_rate: float
    max_dd: float
    sharpe: float
    kelly_frac: float
    initial_bankroll: float
    final_bankroll: float
    ci_lo: float
    ci_hi: float
    ruined: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    """Standard normal CDF using math.erf (no scipy required)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _american_to_decimal(odds: int) -> float:
    """Net payout per unit staked at American odds (e.g. -110 → 0.9091)."""
    if odds < 0:
        return 100.0 / abs(odds)
    return odds / 100.0


# ---------------------------------------------------------------------------
# Player ID resolution  (reused from backtest_vs_closing_lines if importable)
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str) -> Optional[int]:
    """Return nba_api player_id for *name*, or None if not found."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception:
        return None
    needle = _strip_accents(name).lower()
    cands = players.get_players()
    for p in cands:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    for p in cands:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    return None


def _season_from_date(d: str) -> str:
    """NBA season string from ISO date 'YYYY-MM-DD'."""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        dt = datetime.now()
    start = dt.year if dt.month >= 10 else dt.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


# ---------------------------------------------------------------------------
# Core statistics helpers (public API)
# ---------------------------------------------------------------------------

def compute_drawdown_series(pnl_series: List[float]) -> Tuple[float, List[float]]:
    """Return (max_drawdown, drawdown_list) from a running P&L series.

    *pnl_series* is the cumulative P&L at each step (not per-bet delta).
    max_dd is the largest peak-to-trough excursion.
    """
    if not pnl_series:
        return 0.0, []
    peak = pnl_series[0]
    drawdowns: List[float] = []
    max_dd = 0.0
    for val in pnl_series:
        if val > peak:
            peak = val
        dd = peak - val
        drawdowns.append(dd)
        if dd > max_dd:
            max_dd = dd
    return max_dd, drawdowns


def bootstrap_ci(
    returns: List[float],
    n: int = 2000,
    seed: int = 42,
) -> Tuple[float, float]:
    """Bootstrap 95% CI on mean ROI.

    *returns* — per-bet return fractions (pnl / stake for each bet).
    Returns (ci_lo, ci_hi) as percentages (× 100).
    """
    if not returns:
        return 0.0, 0.0
    rng = random.Random(seed)
    k = len(returns)
    means: List[float] = []
    for _ in range(n):
        sample = [returns[rng.randrange(k)] for _ in range(k)]
        means.append(sum(sample) / k * 100.0)
    means.sort()
    lo_idx = int(0.025 * n)
    hi_idx = int(0.975 * n)
    return means[lo_idx], means[min(hi_idx, n - 1)]


def compute_per_stat_breakdown(bets_df: List[Dict[str, Any]]) -> Dict[str, Dict]:
    """Aggregate per-stat hit rate, ROI, n_bets from a list of bet dicts.

    Each dict must have: stat, stake, pnl, won (bool).
    """
    stats: Dict[str, Dict] = {}
    for bet in bets_df:
        s = bet.get("stat", "unknown")
        if s not in stats:
            stats[s] = {"n_bets": 0, "n_wins": 0, "total_stake": 0.0, "total_pnl": 0.0}
        stats[s]["n_bets"] += 1
        if bet.get("won"):
            stats[s]["n_wins"] += 1
        stats[s]["total_stake"] += bet.get("stake", 0.0)
        stats[s]["total_pnl"] += bet.get("pnl", 0.0)
    result: Dict[str, Dict] = {}
    for s, d in stats.items():
        hit = d["n_wins"] / d["n_bets"] if d["n_bets"] else 0.0
        roi = d["total_pnl"] / d["total_stake"] * 100.0 if d["total_stake"] > 0 else 0.0
        result[s] = {
            "n_bets": d["n_bets"],
            "hit_rate": round(hit, 4),
            "roi_pct": round(roi, 2),
            "total_pnl": round(d["total_pnl"], 2),
        }
    return result


# ---------------------------------------------------------------------------
# Main backtest function
# ---------------------------------------------------------------------------

def run_exec_backtest(
    lines_csv: str,
    *,
    initial_bankroll: float = 100_000.0,
    kelly_frac: float = 0.25,
    edge_threshold_pct: float = 5.0,
    save: bool = True,
    # injectable for tests
    _predict_fn=None,
    _quantile_fn=None,
    _build_row_fn=None,
    _resolve_id_fn=None,
) -> BacktestRun:
    """Run the execution backtest and return a BacktestRun dataclass.

    Parameters
    ----------
    lines_csv : path to CSV with required columns
    initial_bankroll : starting bankroll in dollars
    kelly_frac : fractional Kelly multiplier (must be <= 1.0)
    edge_threshold_pct : minimum edge in probability points (e.g. 5.0 = 5pp above breakeven)
    save : whether to write results JSON to scripts/execute_loop/results/
    """
    if kelly_frac > 1.0:
        raise ValueError(
            f"kelly_frac={kelly_frac} implies aggressive bet sizing — "
            "pass a value <= 1.0 (typical: 0.25)"
        )

    # -- lazy imports (real models not needed for tests) --
    if _predict_fn is None:
        import src.data.nba_api_headers_patch  # noqa: F401 — applies headers
        from src.prediction.prop_pergame import predict_pergame as _predict_fn  # type: ignore
    if _quantile_fn is None:
        from src.prediction.prop_quantiles import predict_pergame_quantiles as _quantile_fn  # type: ignore
    if _build_row_fn is None:
        from src.prediction.prop_pergame import build_prediction_row as _build_row_fn  # type: ignore
    if _resolve_id_fn is None:
        _resolve_id_fn = _resolve_player_id

    from src.prediction.quantile_calibration import apply as _cal_apply  # type: ignore

    # -- load & validate CSV --
    csv_path = Path(lines_csv)
    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        # empty file — no required-col check needed, return zero run
        return _zero_run(kelly_frac, initial_bankroll)

    missing = _REQUIRED_COLS - set(rows[0].keys())
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    # -- state --
    bankroll = initial_bankroll
    ruined = False
    bets_log: List[Dict[str, Any]] = []
    cumulative_pnl: List[float] = []  # running P&L at each bet
    dates: List[str] = []

    skipped_unknown_player = 0
    skipped_model_null = 0
    skipped_no_edge = 0

    # -- Kelly helper (reuse L18 module; extract CONFIG for multiplier recovery) --
    from scripts.execute_loop import L18_bankroll_manager as _L18_mod  # type: ignore
    _L18_kelly = _L18_mod.kelly_fraction
    _L18_CONFIG = _L18_mod.CONFIG

    for raw in rows:
        if ruined:
            break

        if bankroll <= 0:
            logger.error("Bankroll <= 0; marking ruined=True, halting bet processing.")
            ruined = True
            break

        # --- parse row ---
        stat = raw.get("stat", "").strip().lower()
        if stat not in _SIGMA_FIX:
            continue

        player_name = raw.get("player", "").strip()
        opp = raw.get("opp", "").strip().upper()
        venue = raw.get("venue", "home").strip().lower()
        date_str = raw.get("date", "")
        is_home = venue.startswith("h")

        try:
            line = float(raw["closing_line"])
            actual = float(raw["actual_value"])
            over_odds = int(raw.get("over_odds") or -110)
            under_odds = int(raw.get("under_odds") or -110)
        except (ValueError, KeyError):
            continue

        season = _season_from_date(date_str)

        # --- resolve player id ---
        pid = _resolve_id_fn(player_name)
        if pid is None:
            logger.debug("Unknown player '%s' — skipping.", player_name)
            skipped_unknown_player += 1
            continue

        # --- build prediction row ---
        try:
            pred_row = _build_row_fn(pid, opp, season, is_home=is_home, rest_days=2.0)
        except Exception as exc:
            logger.debug("build_prediction_row raised %s for %s — skipping.", exc, player_name)
            skipped_model_null += 1
            continue
        if pred_row is None:
            skipped_model_null += 1
            continue

        # --- get point + quantile predictions ---
        try:
            q50 = _predict_fn(stat, pred_row)
            qint = _quantile_fn(stat, pred_row)
        except Exception as exc:
            logger.debug("Prediction error for %s/%s: %s — skipping.", player_name, stat, exc)
            skipped_model_null += 1
            continue
        if q50 is None or qint is None:
            skipped_model_null += 1
            continue

        q10 = qint.get("q10")
        q90 = qint.get("q90")
        if q10 is None or q90 is None:
            skipped_model_null += 1
            continue

        # --- calibrate ---
        try:
            cal_q10, cal_q90 = _cal_apply(stat, q10, q50, q90)
        except Exception:
            cal_q10, cal_q90 = q10, q90

        # --- compute sigma + prob ---
        raw_sigma = (cal_q90 - cal_q10) / (2.0 * 1.2816)
        sigma = max(raw_sigma * _SIGMA_FIX[stat], 1e-6)

        p_over = 1.0 - _normal_cdf((line - q50) / sigma)
        p_under = 1.0 - p_over

        # pick side
        if p_over >= p_under:
            side, p_side, bet_odds = "OVER", p_over, over_odds
        else:
            side, p_side, bet_odds = "UNDER", p_under, under_odds

        edge_pp = (p_side - _BREAKEVEN_PROB) * 100.0
        if edge_pp < edge_threshold_pct:
            skipped_no_edge += 1
            continue

        # --- sizing ---
        # L18.kelly_fraction already applies CONFIG["kelly_fraction_multiplier"].
        # Recover full-Kelly and re-apply our own kelly_frac so the caller
        # controls the fraction (e.g. kelly_frac=0.5 gives 2× the default).
        _l18_raw = _L18_kelly(p_side, bet_odds)
        _l18_mult = _L18_CONFIG.get("kelly_fraction_multiplier", 0.25)
        _full_kelly = (_l18_raw / _l18_mult) if _l18_mult > 0 else _l18_raw
        raw_kelly = _full_kelly * kelly_frac
        stake = raw_kelly * bankroll
        stake = min(stake, _MAX_STAKE_PCT * bankroll)
        stake = round(stake, 2)
        if stake <= 0:
            continue

        # --- settle ---
        if actual == line:
            pnl = 0.0
            won = False
            push = True
        elif (side == "OVER" and actual > line) or (side == "UNDER" and actual < line):
            pnl = stake * _american_to_decimal(bet_odds)
            won = True
            push = False
        else:
            pnl = -stake
            won = False
            push = False

        bankroll += pnl
        running_pnl = bankroll - initial_bankroll
        cumulative_pnl.append(running_pnl)
        dates.append(date_str)

        bets_log.append({
            "date": date_str,
            "player": player_name,
            "stat": stat,
            "side": side,
            "line": line,
            "actual": actual,
            "odds": bet_odds,
            "stake": stake,
            "pnl": pnl,
            "won": won,
            "push": push,
        })

        if bankroll <= 0:
            logger.error("Bankroll exhausted after %d bets. Marking ruined=True.", len(bets_log))
            ruined = True
            break

    # ---------------------------------------------------------------------------
    # Aggregate
    # ---------------------------------------------------------------------------
    n_bets = len(bets_log)
    total_stake = sum(b["stake"] for b in bets_log)
    total_pnl = sum(b["pnl"] for b in bets_log)
    n_wins = sum(1 for b in bets_log if b["won"])

    hit_rate = n_wins / n_bets if n_bets else 0.0
    roi_pct = total_pnl / total_stake * 100.0 if total_stake > 0 else 0.0

    max_dd, _ = compute_drawdown_series(cumulative_pnl) if cumulative_pnl else (0.0, [])

    # Sharpe on daily returns
    sharpe = _compute_sharpe(bets_log)

    # Bootstrap CI
    per_bet_returns = [b["pnl"] / b["stake"] for b in bets_log if b["stake"] > 0]
    ci_lo, ci_hi = bootstrap_ci(per_bet_returns) if per_bet_returns else (0.0, 0.0)

    start_date = min(dates) if dates else ""
    end_date = max(dates) if dates else ""

    run_id = f"exec_bt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    result = BacktestRun(
        run_id=run_id,
        start_date=start_date,
        end_date=end_date,
        n_bets=n_bets,
        total_stake=round(total_stake, 2),
        total_pnl=round(total_pnl, 2),
        roi_pct=round(roi_pct, 2),
        hit_rate=round(hit_rate, 4),
        max_dd=round(max_dd, 2),
        sharpe=round(sharpe, 4),
        kelly_frac=kelly_frac,
        initial_bankroll=initial_bankroll,
        final_bankroll=round(bankroll, 2),
        ci_lo=round(ci_lo, 2),
        ci_hi=round(ci_hi, 2),
        ruined=ruined,
    )

    logger.info(
        "Backtest %s: %d bets, ROI=%.1f%%, hit=%.1f%%, sharpe=%.2f, "
        "skipped(unknown=%d, null=%d, edge=%d)",
        run_id, n_bets, roi_pct, hit_rate * 100,
        sharpe, skipped_unknown_player, skipped_model_null, skipped_no_edge,
    )

    if save:
        _save_result(result, bets_log)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _zero_run(kelly_frac: float, initial_bankroll: float) -> BacktestRun:
    run_id = f"exec_bt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    return BacktestRun(
        run_id=run_id, start_date="", end_date="",
        n_bets=0, total_stake=0.0, total_pnl=0.0, roi_pct=0.0,
        hit_rate=0.0, max_dd=0.0, sharpe=0.0,
        kelly_frac=kelly_frac, initial_bankroll=initial_bankroll,
        final_bankroll=initial_bankroll, ci_lo=0.0, ci_hi=0.0,
    )


def _compute_sharpe(bets_log: List[Dict[str, Any]]) -> float:
    """Daily Sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)."""
    if not bets_log:
        return 0.0
    from collections import defaultdict
    daily: Dict[str, float] = defaultdict(float)
    for b in bets_log:
        daily[b["date"]] += b["pnl"]
    vals = list(daily.values())
    if len(vals) < 2:
        return 0.0
    n = len(vals)
    mean = sum(vals) / n
    variance = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    return (mean / std) * math.sqrt(252.0)


def _atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Write *payload* as JSON to *path* atomically via a sibling temp file.

    Uses tempfile.mkstemp so the temp file lives on the same filesystem as
    *path*, making os.replace an atomic rename rather than a cross-device copy.
    Cleans up the temp file on any failure.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=indent)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically via a sibling temp file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_result(result: BacktestRun, bets_log: List[Dict]) -> None:
    out = result.to_dict()
    out["bets"] = bets_log
    path = _RESULTS_DIR / f"exec_backtest_{result.run_id}.json"
    _atomic_write_json(path, out)
    logger.info("Saved backtest results → %s", path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_exec_backtest(
        args.lines,
        initial_bankroll=args.bankroll,
        kelly_frac=args.kelly,
        edge_threshold_pct=args.edge,
        save=True,
    )
    print(json.dumps(result.to_dict(), indent=2))


def _cli_compare(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_ids = [r.strip() for r in args.runs.split(",")]
    rows_out = []
    for rid in run_ids:
        pattern = list(_RESULTS_DIR.glob(f"exec_backtest_{rid}.json"))
        if not pattern:
            print(f"[WARN] No result file found for run_id={rid}")
            continue
        with pattern[0].open(encoding="utf-8") as fh:
            data = json.load(fh)
        rows_out.append({
            "run_id": data.get("run_id"),
            "n_bets": data.get("n_bets"),
            "roi_pct": data.get("roi_pct"),
            "hit_rate": data.get("hit_rate"),
            "sharpe": data.get("sharpe"),
            "max_dd": data.get("max_dd"),
            "ci_lo": data.get("ci_lo"),
            "ci_hi": data.get("ci_hi"),
        })
    print(json.dumps(rows_out, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="L39 Execution Backtest Harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run a backtest against a lines CSV")
    run_p.add_argument("--lines", required=True, help="Path to lines CSV")
    run_p.add_argument("--kelly", type=float, default=0.25, help="Fractional Kelly (default 0.25)")
    run_p.add_argument("--edge", type=float, default=5.0, help="Edge threshold in pp (default 5.0)")
    run_p.add_argument("--bankroll", type=float, default=100_000.0, help="Initial bankroll")

    cmp_p = sub.add_parser("compare", help="Compare multiple backtest run IDs")
    cmp_p.add_argument("--runs", required=True, help="Comma-separated run IDs")

    args = parser.parse_args()
    if args.cmd == "run":
        _cli_run(args)
    elif args.cmd == "compare":
        _cli_compare(args)


if __name__ == "__main__":
    main()
