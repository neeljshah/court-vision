"""compare_to_lines.py — compare model predictions vs YOUR pasted sportsbook lines.

Lets you ingest actual prop O/U lines from a CSV/TSV file and see where the
model has claimed edge. Output is a sortable ranking of bets by EV.

The CSV must have these columns (case-insensitive):
    player        — full player name (NBA stats.com canonical)
    opp           — opponent team abbrev (LAL, DEN, etc.)
    venue         — 'home' or 'away' (player's team's side)
    stat          — one of: pts reb ast fg3m stl blk tov
    line          — the over/under number from the book (e.g. 22.5)
  optional:
    over_odds     — American odds for OVER (e.g. -110). Default -110.
    under_odds    — American odds for UNDER. Default -110.
    rest_days     — defaults to 2.0 if missing
    season        — defaults to current

Usage:
    python scripts/compare_to_lines.py tonight.csv
    python scripts/compare_to_lines.py tonight.csv --min-edge 1.0
    python scripts/compare_to_lines.py tonight.csv --kelly --bankroll 1000

Output (sorted by EV):
    player           stat  line   model  edge   bet   prob   odds   EV/$   Kelly%
    Nikola Jokic     REB   11.5   13.07  +1.57  OVER  0.671  -110  +27.96  5.42%
    ...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, date as _date

import numpy as np

# Cycle 51: injury statuses that mean "don't bet this player". QUESTIONABLE
# is intentionally NOT in this set — the player is more likely than not to
# play, and the model's L5/L10 features already partially account for limited
# minutes. PROBABLE / AVAILABLE / NOT-LISTED never skip.
_UNAVAILABLE_STATUSES = {"OUT", "DOUBTFUL", "NOT WITH TEAM"}

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, SCRIPTS_DIR)

from lib_betting_validation import safe_odds  # Bug 10 guard

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)
from src.prediction.quantile_calibration import apply as apply_quantile_calibration  # noqa: E402
from src.prediction.quantile_calibration import apply_conformal as _apply_conformal  # noqa: E402
# Cycle 90f (loop 5), T4-A: rolling-window calibration, opt-in via --rolling-cal.
# Import is wrapped so the script still runs on installs without the parquet.
try:
    from scripts.quantile_calibration_rolling import (  # noqa: E402
        apply_rolling as apply_quantile_calibration_rolling,
    )
except Exception:
    apply_quantile_calibration_rolling = None  # type: ignore
from src.data.injuries import load_unavailable_players  # noqa: E402
from src.data.lineups import (  # noqa: E402
    build_starter_index, classify_starter, STATUS_SCALE,
)
from src.prediction import live_adjustment as _live_adjust  # noqa: E402
from src.prediction import live_context as _live_ctx  # noqa: E402
from src.prediction import pregame_calibration as _pregame_cal  # noqa: E402
from src.prediction import availability as _availability  # noqa: E402


def _strip_accents(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str):
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


def _current_season() -> str:
    now = datetime.now()
    start = now.year if now.month >= 10 else now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _american_to_implied_prob(odds: int) -> float:
    """-110 → 0.5238; +150 → 0.4 ; -150 → 0.6."""
    odds = int(odds)
    if odds > 0:
        return 100 / (odds + 100)
    return -odds / (-odds + 100)


def _american_payout(odds: int, stake: float = 1.0) -> float:
    """Profit on $stake bet given odds (NOT including stake return). -110 = 0.909."""
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100)
    return stake * (100 / -odds)


def _asym_hit_prob_enabled() -> bool:
    """H5 fix gate. Default OFF — the symmetric-sigma path stays byte-identical
    so the validated book is preserved. Set CV_ASYM_HIT_PROB=1 to switch the
    served hit-prob to the split-normal that respects the asymmetric calibrated
    band. See docs/_audits/ASYM_HIT_PROB_AB_2026-06-02.md."""
    return os.environ.get("CV_ASYM_HIT_PROB", "0").strip().lower() in (
        "1", "true", "yes", "on")


def _split_normal_p_over(line: float, center: float,
                         sigma_lo: float, sigma_hi: float) -> float:
    """P(X > line) for a two-piece (split / Fechner) normal whose CDF passes
    through (center, 0.5). Below the center the dispersion is sigma_lo, above it
    sigma_hi; the halves are spliced at the median so the CDF is continuous and
    integrates to 1. With sigma_lo == sigma_hi it reduces exactly to a Normal."""
    from math import erf, sqrt
    sigma_lo = max(float(sigma_lo), 1e-6)
    sigma_hi = max(float(sigma_hi), 1e-6)
    if line <= center:
        z = (line - center) / sigma_lo
    else:
        z = (line - center) / sigma_hi
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    return 1.0 - cdf


def _model_hit_prob(stat: str, point_pred: float, qint: dict, line: float, side: str,
                    use_rolling: bool = False, on_or_before: str = None) -> float:
    """Approximate the model's predicted probability of WINNING the side at the given line.

    Default (CV_ASYM_HIT_PROB OFF): centers a SYMMETRIC normal at the BLEND's
    point prediction and uses the CYCLE-40 CALIBRATED q90 - q10 spread to estimate
    sigma. Calibration brings each stat's interval to actually-80% coverage (raw
    was 71-91%) — without it the Kelly probability estimates are systematically off
    (PTS/AST under-cover means too-confident bets; STL/BLK over-cover means too-cautious).

    When CV_ASYM_HIT_PROB is ON (H5 fix): a SPLIT-NORMAL respecting the asymmetric
    calibrated band — sigma_lo from (q50 - cal_q10), sigma_hi from (cal_q90 - q50),
    both /1.2816, centred at q50 — so the served CDF passes through (cal_q10, .10),
    (q50, .50), (cal_q90, .90). For symmetric bands this collapses to the OFF result
    exactly. See docs/_audits/ASYM_HIT_PROB_AB_2026-06-02.md.

    Cycle 90f T4-A: when ``use_rolling`` is True and the rolling parquet exists,
    use the prior-60-game window scale for ``on_or_before`` instead of the
    global cycle-40 scale. Default (False) preserves cycle-40 behaviour.
    """
    q10 = qint.get("q10"); q50 = qint.get("q50"); q90 = qint.get("q90")
    if q10 is None or q90 is None or point_pred is None:
        return None
    # CV_QUANTILE_CAL=1: use split-conformal (CQR) calibration instead of the
    # existing val-slice scale-factor. The conformal path is the default branch
    # when the flag is ON; rolling-cal composing is skipped (rolling-cal is an
    # alternative, not additive). Flag OFF: identical to previous behaviour.
    import os as _os_ctl
    if _os_ctl.environ.get("CV_QUANTILE_CAL", "0") == "1":
        cal_q10, cal_q90 = _apply_conformal(stat, q10, q50 or point_pred, q90)
    elif use_rolling and apply_quantile_calibration_rolling is not None:
        cal_q10, cal_q90 = apply_quantile_calibration_rolling(
            stat, q10, q50 or point_pred, q90,
            on_or_before=on_or_before or _date.today().isoformat(),
        )
    else:
        cal_q10, cal_q90 = apply_quantile_calibration(stat, q10, q50 or point_pred, q90)
    if _asym_hit_prob_enabled():
        center = q50 if q50 is not None else point_pred
        sigma_lo = max((center - cal_q10) / 1.2816, 1e-6)
        sigma_hi = max((cal_q90 - center) / 1.2816, 1e-6)
        p_over = _split_normal_p_over(line, center, sigma_lo, sigma_hi)
        return p_over if side == "OVER" else 1 - p_over
    sigma = max((cal_q90 - cal_q10) / (2 * 1.2816), 1e-6)
    from math import erf, sqrt
    z = (line - point_pred) / sigma
    cdf_at_line = 0.5 * (1 + erf(z / sqrt(2)))
    p_over = 1 - cdf_at_line
    return p_over if side == "OVER" else 1 - p_over


def _kelly_fraction(prob: float, odds: int) -> float:
    """Kelly fraction for a single bet. Returns 0 if no edge."""
    b = _american_payout(odds, 1.0)  # net odds per unit
    p = prob; q = 1 - p
    f = (b * p - q) / b
    return max(0.0, f)


def load_injury_unavailable(path: str) -> dict:
    """Cycle-51 wrapper kept for the existing test suite. Cycle 53 moved the
    implementation to src/data/injuries.load_unavailable_players() for reuse
    across compare_to_lines, predict_player, and predict_slate.
    """
    return load_unavailable_players(path)


def append_bet_log(out_path: str, results: list,
                    kelly_bankroll: float = None) -> int:
    """Cycle 68: append the ranked positive-EV bets to a CSV. Creates header
    on first write. Returns rows written.

    Schema:
      timestamp,date,player,stat,line,side,model,edge,prob,odds,ev_per_dollar,
      kelly_pct,kelly_stake,bankroll
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    file_exists = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    ts = datetime.now().isoformat(timespec="seconds")
    date_str = _date.today().isoformat()
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not file_exists:
            w.writerow(["timestamp", "date", "player", "stat", "line", "side",
                        "model", "edge", "prob", "odds", "ev_per_dollar",
                        "kelly_pct", "kelly_stake", "bankroll"])
        for r in results:
            w.writerow([
                ts, date_str, r["player"], r["stat"], r["line"], r["side"],
                r["model"], r["edge"], r["prob"], r["odds"], r["ev"],
                r["kelly_pct"], r["kelly_stake"],
                f"{kelly_bankroll:.2f}" if kelly_bankroll is not None else "",
            ])
    return len(results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV file with prop lines")
    ap.add_argument("--min-edge", type=float, default=0.0,
                    help="Minimum |model - line| in stat units to show. Default 0.")
    ap.add_argument("--kelly", action="store_true", help="Also show Kelly fraction")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll for Kelly stake sizing (default $1000)")
    ap.add_argument("--season", default=None)
    ap.add_argument("--injuries", nargs="?", const="__default__", default=None,
                    help="Skip players listed OUT/DOUBTFUL in the injury JSON. "
                         "Bare flag → data/injuries_<today>.json; with arg → that path.")
    ap.add_argument("--include-injured", action="store_true",
                    help="Override --injuries: include all players regardless of status.")
    ap.add_argument("--lineups", nargs="?", const="__default__", default=None,
                    help="Cycle 64. Skip players not classified starter/questionable in the "
                         "cycle-61 rotowire lineup JSON. Bare flag → data/lineups_<today>.json.")
    ap.add_argument("--scale-by-status", action="store_true",
                    help="Cycle 67. Scale model_pred + q10/q90 by the lineup classification "
                         "(questionable*0.75) before computing edge / EV. Requires --lineups.")
    ap.add_argument("--bet-log", nargs="?", const="__default__", default=None,
                    help="Cycle 68. Append recommended bets (positive EV) to a CSV for later "
                         "CLV / settlement analysis. Bare flag → data/bets/<today>.csv; with "
                         "arg → that path.")
    ap.add_argument("--strategy", default="pregame_auto",
                    help="A/B strategy tag (cycle 104c) stamped on the output "
                         "command suggestions. Default 'pregame_auto'.")
    ap.add_argument("--register-strategy", action="store_true",
                    help="If set, auto-register --strategy in ab_strategies.csv "
                         "with bankroll $1000 / max_bet_pct 0.05 when missing.")
    ap.add_argument("--rolling-cal", action="store_true",
                    help="Cycle 90f T4-A. Use prior-60-game rolling quantile calibration "
                         "(data/models/quantile_cal_rolling.parquet) instead of the global "
                         "cycle-40 scales. Default off; cycle-40 stays canonical.")
    ap.add_argument("--live-adjust", action="store_true",
                    help="2026-06-01. Apply the same-day live pace/blowout adjustment "
                         "(src/prediction/live_adjustment.py) using tonight's mainline "
                         "total/spread. Also enabled via CV_LIVE_ADJUST=1. Default off "
                         "(strict no-op) so the proven projection path is unchanged.")
    ap.add_argument("--calibrate", action="store_true",
                    help="2026-06-01. Apply per-stat pregame calibration "
                         "(src/prediction/pregame_calibration.py); PTS-only by default "
                         "(cuts its -8.89%% Vegas ROI to -5.04%%; AST left RAW). Also via "
                         "CV_PREGAME_CAL=1. Default off (strict no-op).")
    args = ap.parse_args()

    _live_adjust_on = args.live_adjust or _live_adjust.is_enabled()
    if _live_adjust_on:
        print("  [live-adjust] ON — applying same-day pace/blowout context "
              "(inactive-usage term fed from tonight's confirmed-inactives report)")
    _pregame_cal_on = args.calibrate or _pregame_cal.is_enabled()
    if _pregame_cal_on:
        print(f"  [calibrate] ON — recalibrating stats {sorted(_pregame_cal.enabled_stats())} "
              "(AST left raw to preserve divergence edge)")

    # Confirmed-inactives -> vacated load (powers both the live-adjust inactive
    # term and the calibrator's vacated covariates). Computed once per run.
    _vac_map: dict = {}
    if _live_adjust_on or _pregame_cal_on:
        try:
            _vac_map = _availability.team_vacated_map(
                _date.today().isoformat(), _resolve_player_id)
            _n_out_teams = sum(1 for v in _vac_map.values() if v.get("n_out"))
            print(f"  [inactives] loaded vacated load for {_n_out_teams} team(s) "
                  "from tonight's injury report")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [inactives] unavailable ({exc}); vacated terms = 0")

    inj_unavail: dict = {}
    if args.injuries is not None and not args.include_injured:
        inj_path = (os.path.join(PROJECT_DIR, "data",
                                  f"injuries_{_date.today().isoformat()}.json")
                    if args.injuries == "__default__" else args.injuries)
        inj_unavail = load_injury_unavailable(inj_path)
        print(f"  [injuries] loaded {len(inj_unavail)} unavailable player(s) from "
              f"{os.path.basename(inj_path)}")

    starter_idx: dict = {}
    if args.lineups is not None:
        lu_path = (os.path.join(PROJECT_DIR, "data",
                                  f"lineups_{_date.today().isoformat()}.json")
                    if args.lineups == "__default__" else args.lineups)
        starter_idx = build_starter_index(lu_path)
        print(f"  [lineups] loaded {len(starter_idx)} starter(s) from "
              f"{os.path.basename(lu_path)}")

    season_default = args.season or _current_season()
    gamelog_dir = os.path.join(PROJECT_DIR, "data", "nba")
    model_dir   = os.path.join(PROJECT_DIR, "data", "models")

    rows_in = []
    with open(args.csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows_in.append({k.strip().lower(): v.strip() for k, v in r.items()})
    if not rows_in:
        print("[fail] empty CSV"); sys.exit(1)

    results = []
    skipped_inj = []
    skipped_lu = []
    for r in rows_in:
        name = r.get("player", ""); opp = r.get("opp", "").upper()
        venue = r.get("venue", "home").lower(); stat = r.get("stat", "").lower()
        try:
            line = float(r.get("line", "nan"))
        except ValueError:
            line = float("nan")
        if not (name and opp and stat in STATS and not np.isnan(line)):
            print(f"  [skip] bad row: {r}"); continue
        if inj_unavail:
            key = _strip_accents(name).lower()
            if key in inj_unavail:
                skipped_inj.append((name, inj_unavail[key]))
                continue
        if starter_idx:
            cls = classify_starter(name, starter_idx)
            if cls in ("bench", "no-game"):
                skipped_lu.append((name, cls))
                continue
        rest_days = float(r.get("rest_days") or 2.0)
        season = r.get("season") or season_default
        is_home = (venue.startswith("h"))
        over_odds = safe_odds(r.get("over_odds") or -110)  # Bug 10 guard
        under_odds = safe_odds(r.get("under_odds") or -110)  # Bug 10 guard

        pid = _resolve_player_id(name)
        if pid is None:
            print(f"  [skip] cannot resolve player '{name}'"); continue
        prow = build_prediction_row(pid, opp, season, is_home=is_home,
                                    rest_days=rest_days, gamelog_dir=gamelog_dir)
        if prow is None:
            print(f"  [skip] no gamelog for {name} season={season}"); continue
        model_pred = predict_pergame(stat, prow, model_dir)
        qint = predict_pergame_quantiles(stat, prow, model_dir)
        if model_pred is None or qint is None:
            print(f"  [skip] {name} {stat}: no model output"); continue
        # Cycle 67: scale by lineup classification before EV math.
        if args.scale_by_status and starter_idx:
            cls = classify_starter(name, starter_idx)
            factor = STATUS_SCALE.get(cls, 1.0)
            if factor != 1.0:
                model_pred = round(float(model_pred) * factor, 2)
                qint = {k: (round(float(v) * factor, 2)
                            if isinstance(v, (int, float)) else v)
                        for k, v in qint.items()}
        # Resolve the player's own team unconditionally so the live-adjust context
        # lookup can use context_for_team (keyed on exact frozenset) rather than the
        # weaker context_for_opponent scan — which fails on multi-game slates when the
        # opponent appears in more than one game. _team is always assigned here so no
        # branch below risks a NameError or stale loop value on a quiet night.
        _team = _availability.player_team(pid, season)

        # Tonight's vacated load for this player (confirmed-inactives feed).
        _vac = {"vac_min": 0.0, "vac_pts": 0.0, "n_out": 0, "vac_share": 0.0}
        if _vac_map:
            _vac = _availability.player_vacated(
                float(prow.get("l10_pts") or 0.0), _team, _vac_map)

        # Capture the base projection BEFORE either adjustment layer fires so
        # the pregame_layer_log can later A/B base vs each layer against actuals.
        _base_pred = float(model_pred)
        _after_cal_pred: Optional[float] = None
        _live_total: Optional[float] = None
        _live_spread: Optional[float] = None

        # Pregame calibration (2026-06-01): recalibrate the point estimate on
        # stats where the base model loses to Vegas (PTS by default). OFF unless
        # CV_PREGAME_CAL=1 or --calibrate. Strict no-op otherwise; AST is left RAW
        # on purpose (calibration kills its edge). docs/VS_VEGAS_ASSESSMENT.md §5.
        if _pregame_cal_on:
            opp_pace, opp_def = _live_ctx.team_pace_def(opp, season)
            cov = _availability.player_form_covariates(
                pid, season, _date.today().isoformat())
            cov.update({
                "rest_days": rest_days, "is_b2b": 1 if rest_days <= 1 else 0,
                "is_home": 1 if is_home else 0,
                "opp_pace": opp_pace, "opp_def": opp_def,
                "vac_min": _vac["vac_min"], "vac_pts": _vac["vac_pts"],
                "n_out": _vac["n_out"], "month": _date.today().month,
            })
            model_pred = round(_pregame_cal.apply(stat, float(model_pred), cov,
                                                  force=True), 2)
            _after_cal_pred = float(model_pred)
        # Same-day adjustment (2026-06-01): inject tonight's live pace/blowout
        # context the trained model can't see at serve time. OFF unless
        # CV_LIVE_ADJUST=1 or --live-adjust — a strict no-op otherwise, so the
        # proven projection path is untouched by default. See
        # src/prediction/live_adjustment.py + docs/VS_VEGAS_ASSESSMENT.md §3.
        if _live_adjust_on:
            _today = _date.today().isoformat()
            if _team:
                total, spread_abs = _live_ctx.context_for_team(
                    _team, opp, _today)
            else:
                # _team unresolvable (rare / quiet night): fall back to the
                # opponent-scan path which is correct on single-game slates.
                total, spread_abs = _live_ctx.context_for_opponent(
                    opp, _today)
            _live_total = total; _live_spread = spread_abs
            if total is not None or spread_abs is not None or _vac["vac_share"] > 0:
                adj = _live_adjust.adjust_projection(
                    {stat: float(model_pred)}, vac_share=_vac["vac_share"],
                    game_total=total, game_spread=spread_abs)
                model_pred = round(adj[stat], 2)
        # Layer shadow logger (2026-06-01): record base vs after-cal vs after-live
        # so the live-only term can be graded vs actuals nightly. Strict no-op
        # unless CV_LAYER_LOG=1. See src/prediction/pregame_layer_log.py and
        # docs/VS_VEGAS_ASSESSMENT.md §4.
        try:
            from src.prediction import pregame_layer_log as _layer_log
            if _layer_log.is_enabled():
                _layer_log.log(
                    date=_date.today().isoformat(),
                    player_id=pid, stat=stat, line=line, side=None,
                    base=_base_pred,
                    after_cal=_after_cal_pred,
                    after_live=(float(model_pred) if _live_adjust_on else None),
                    over_odds=over_odds, under_odds=under_odds,
                    vac_share=_vac.get("vac_share"),
                    game_total=_live_total, game_spread=_live_spread,
                    opp=opp,
                )
        except Exception:
            pass  # logger MUST NOT crash production
        edge = model_pred - line
        # Per-policy per-stat min-edge override (CV_BET_POLICY). Can only
        # TIGHTEN the global --min-edge, never relax it. Under ast_high, AST
        # requires edge >= 0.75. See src/prediction/bet_policy.py.
        _eff_min = args.min_edge
        try:
            from src.prediction.bet_policy import policy_min_edge as _policy_min
            _eff_min = max(_eff_min, _policy_min(stat))
        except Exception:
            pass
        if abs(edge) < _eff_min:
            continue
        # Bet-policy stat allowlist (CV_BET_POLICY). Strict no-op under iter57.
        # Also enforces the per-stat closing-line cap (e.g. ast_high drops
        # AST lines > 7.5 — the very_high tier sign-flipped between halves).
        try:
            from src.prediction.bet_policy import policy_allows_stat as _policy_allows
            from src.prediction.bet_policy import policy_drops_line as _policy_drops_line
            if not _policy_allows(stat):
                continue
            if _policy_drops_line(stat, line):
                continue
        except Exception:
            pass
        side = "OVER" if edge > 0 else "UNDER"
        odds = over_odds if side == "OVER" else under_odds
        prob = _model_hit_prob(stat, model_pred, qint, line, side,
                               use_rolling=args.rolling_cal,
                               on_or_before=_date.today().isoformat())
        net_payout = _american_payout(odds, 1.0)
        ev_per_dollar = prob * net_payout - (1 - prob) * 1.0 if prob is not None else 0.0
        kf = _kelly_fraction(prob, odds) if prob is not None else 0.0

        results.append({
            "player": name, "stat": stat.upper(), "line": line,
            "model": round(model_pred, 2), "edge": round(edge, 2),
            "side": side, "prob": round(prob, 3) if prob else None,
            "odds": odds, "ev": round(ev_per_dollar, 4),
            "kelly_pct": round(kf * 100, 2),
            "kelly_stake": round(kf * args.bankroll, 2),
        })

    if skipped_inj:
        print(f"\n  [injuries] skipped {len(skipped_inj)} line(s) for OUT/DOUBTFUL players:")
        # De-duplicate (a player has multiple lines) before printing.
        seen = set()
        for n, s in skipped_inj:
            if n in seen:
                continue
            seen.add(n)
            print(f"    - {n} ({s})")
    if skipped_lu:
        print(f"\n  [lineups] skipped {len(skipped_lu)} line(s) for non-starters:")
        seen = set()
        for n, c in skipped_lu:
            if n in seen:
                continue
            seen.add(n)
            print(f"    - {n} ({c})")

    if not results:
        print("[done] no bets passed --min-edge filter"); return

    # Sort by EV descending
    results.sort(key=lambda x: x["ev"], reverse=True)
    print(f"\n  {'player':<22s} {'stat':4s} {'line':>5s}  {'model':>5s} {'edge':>6s}  {'side':5s}  {'prob':>5s}  {'odds':>5s}  {'EV/$':>7s}  {'Kelly%':>7s}")
    print(f"  {'-'*22} {'-'*4} {'-'*5}  {'-'*5} {'-'*6}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*7}")
    for r in results:
        pr = f"{r['prob']:.3f}" if r['prob'] is not None else "  —  "
        od = f"{int(round(r['odds'])):+d}" if r['odds'] is not None else "  —  "
        print(f"  {r['player']:<22s} {r['stat']:4s} {r['line']:>5.1f}  {r['model']:>5.2f} {r['edge']:>+6.2f}  {r['side']:5s}  {pr:>5s}  {od:>5s}  {r['ev']:>+7.4f}  {r['kelly_pct']:>6.2f}%")
    if args.kelly:
        total_stake = sum(r["kelly_stake"] for r in results)
        print(f"\n  Total Kelly stake on positive-EV bets: ${total_stake:.2f} of ${args.bankroll:.2f} bankroll")

    # Cycle 104c: A/B strategy tagging + copy-pasteable place_bet commands.
    if args.register_strategy:
        try:
            from src.betting.recommendation import ensure_strategy_registered
            ensure_strategy_registered(args.strategy, bankroll=1000.0,
                                        max_bet_pct=0.05)
        except Exception as exc:
            print(f"  [warn] could not auto-register {args.strategy!r}: {exc}")
    print(f"\n  --- copy-pasteable place_bet commands (strategy={args.strategy}) ---")
    try:
        from src.betting.recommendation import to_place_bet_command
        for r in results:
            r_low = dict(r); r_low["stat"] = str(r["stat"]).lower()
            print("  " + to_place_bet_command(r_low, args.strategy,
                                              odds=int(r["odds"])))
    except Exception as exc:
        print(f"  [warn] could not emit commands: {exc}")

    if args.bet_log is not None and results:
        bet_path = (os.path.join(PROJECT_DIR, "data", "bets",
                                  f"{_date.today().isoformat()}.csv")
                    if args.bet_log == "__default__" else args.bet_log)
        n = append_bet_log(bet_path, results, args.bankroll if args.kelly else None)
        print(f"  Logged {n} bet(s) -> {bet_path}")


if __name__ == "__main__":
    main()
