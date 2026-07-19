"""scripts.platformkit.ingame.inplay_derivative_mlb -- MLB IN-PLAY DERIVATIVE
(totals / run-line) paper measurement channel (own daemon; W4 sibling).

PAIRS two pieces that already exist but were never wired together:
  * odds_provider.inplay_kalshi.fetch_inplay("mlb") -- ALREADY returns liquid
    total/spread ticks (market_type="total"|"spread", a real strike `line`,
    a YES `prob`) -- inplay_capture_loop._yes_pair deliberately filters these
    OUT (moneyline-only channel).
  * domains.mlb.repricer.MLBRepricer.reprice(state) -- ALREADY returns a
    distributional surface (over_X/under_X at the negbinom_engine total-line
    grid, rl_home_minus15/rl_away_plus15) from the SAME lambdas
    domains.mlb.predictor.MLBPredictor uses for its served moneyline number.

Per live MLB game, per tick: align each liquid total/spread tick's line
against the repricer surface (mlb_deriv_align.align_tick -- interpolate
between adjacent computed lines only, NEVER extrapolate; no coverage -> honest
skip), ALWAYS capture the (market_prob, model_prob) pair to
data/cache/ingame_grade_deriv/mlb/<gid>.jsonl, then run the SAME gate stack
the moneyline channel uses (inplay_edge_signal.evaluate's strict EV floor --
NOT relaxed day one; execution.ingame_exec_gate.evaluate_placement's
divergence/drift/spread caps; inplay_breaker.allow) before placing via
paper_ingame.record_ingame_bet.

SETTLEMENT is delegated to mlb_deriv_settle.py (split out to keep both files
under the platform's <=300 LOC/file rail): grade_paper_one._outcome is a
HOME/AWAY MONEYLINE comparator and does not fit total/run-line outcomes, so
settlement there is NEW logic (win iff the final total/run-diff is on the
backed side of the line; an INTEGER total line landing exactly on the final
total is a PUSH); the FINAL-score fetch (settled_finals) and the pure
unit-result math (grade_paper_one._unit_result) ARE reused.

LEDGER SIDE CONVENTION (binding, see mlb_deriv_align.ledger_side): the shared
CLV ledger schema requires side in {"home","away"}; this channel uses that
field as a BOOKKEEPING convention only (over/home-favorite -> "home",
under/away-dog -> "away"), NEVER fed through paper_ingame.grade_live /
grade_paper.grade_one (which would misread it as a real moneyline side). The
`market` string (e.g. "total_8.5_over") carries the real proposition.

HONESTY (binding, mirrors inplay_capture_loop): PAPER / UNITS / probability
only; executed is always False; edge_claimed is always False. Capture ALWAYS
runs even when the gate says no_bet. Every skip reason is counted in the
heartbeat. This channel is MEASUREMENT: its first weeks fill the derivative
CLV corpus, not volume.

Does NOT edit inplay_capture_loop.py / inplay_daytrader.py -- runs as its OWN
daemon (own singleton lock, own heartbeat component "m2_inplay_deriv") beside
the moneyline runner.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no
data/registry write, no flag flip, no autostart.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_derivative_mlb.py -q
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import inplay_breaker as _breaker
from scripts.platformkit.ingame import inplay_edge_signal as _sig
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import mlb_deriv_align as _align
from scripts.platformkit.ingame import paper_ingame as _paper

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DERIV_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade_deriv"
DEFAULT_HEARTBEAT = DEFAULT_DERIV_DIR / "_capture_heartbeat.json"
DEFAULT_LOCK = DEFAULT_DERIV_DIR / "mlb_deriv.lock"
HEARTBEAT_COMPONENT = "m2_inplay_deriv"
SPORT = "mlb"

LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0

# Injectable callback signatures (default to the real chains; tests inject offline
# stubs). Mirrors inplay_capture_loop's injection discipline.
FetchFn = Callable[[str], List[Dict[str, Any]]]
StateFn = Callable[[str, List[Dict[str, Any]], Any], Optional[Dict[str, Any]]]
SurfaceFn = Callable[[str, str, int, int, int, str], Optional[Dict[str, Any]]]
FinalsFn = Callable[[str], List[Dict[str, Any]]]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_fetch(sport: str) -> List[Dict[str, Any]]:
    """Default production fetch: inplay_kalshi.fetch_inplay (paced, byte-identical
    caller pattern to inplay_capture_loop._default_inplay_fetch). [] on any error."""
    try:
        from scripts.platformkit.odds_provider import inplay_kalshi as _ik
        return list(_ik.fetch_inplay(sport, stagger_sec=_ik.REQUEST_STAGGER_SEC,
                                     governor_caller="capture"))
    except Exception as exc:  # noqa: BLE001 -- a feed error is never fatal
        logger.warning("inplay_derivative_mlb fetch failed: %s", exc)
        return []


def _default_state(sport: str, ticks: List[Dict[str, Any]], gid: str,
                   nowdt: datetime, cache: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bridge a total/spread tick's game_id to its live ESPN state, REUSING (never
    copying) inplay_capture_loop's own team-bridge machinery. Team names come from
    the Kalshi ticker's own embedded codes (mlb_deriv_align.ticker_team_codes) since
    total/spread tick `side` labels are propositions ("Over 8.5"), not team names."""
    try:
        from scripts.platformkit.ingame import inplay_capture_loop as _cap
        from scripts.platformkit.ingame import ingame_live_state as _ls
        splits = _align.ticker_team_splits(gid)
        if not splits:
            return None
        states = cache.get("states")
        if states is None:
            try:
                states = _ls.live_states(sport)
            except Exception:  # noqa: BLE001 -- a scan failure -> no bridge this cycle
                states = []
            cache["states"] = states
        # The blob split is ambiguous (2-3 letters/side); the scan's BOTH-teams-
        # must-match rule makes trying every candidate safe -- first full match wins.
        for a, b in splits:
            st = _cap._scan_live_by_legs(sport, {a: 1.0, b: 1.0}, gid=gid,
                                         nowdt=nowdt, states=states)
            if st is not None:
                return st
        return None
    except Exception as exc:  # noqa: BLE001 -- bridge failure -> honest skip, never a crash
        logger.debug("inplay_derivative_mlb state bridge failed %s: %s", gid, exc)
        return None


def _default_surface(home: str, away: str, home_score: int, away_score: int,
                     inning: int, half: str) -> Optional[Dict[str, Any]]:
    """The full negbinom repricer surface (over_/under_/rl_ keys) for this live state.

    REUSES the SAME lambda construction domains.mlb.predictor.MLBPredictor.predict_live
    uses (Elo-anchored lam_home/lam_away + fitted r), via the cached corpus predictor
    (frontend.live_board._cached_predictor -- corpus-heavy, built once), then calls
    domains.mlb.repricer.MLBRepricer.reprice directly (predict_live itself trims the
    surface to ml_home/rl_home_minus15 only, dropping the over_/under_ keys this
    channel needs -- so this duplicates that construction, not the model). None on
    any failure (unresolved team name, missing corpus, bad state) -- never fabricated.
    """
    try:
        from scripts.platformkit.frontend.live_board import _cached_predictor
        from domains.mlb.predictor import _anchor_nb_tiesplit, _mov_p_home
        from scripts.platformkit.live_repricer import GameState, get_repricer

        pred = _cached_predictor("mlb")
        ht, au = pred._resolve_or_upper(home), pred._resolve_or_upper(away)
        lam_raw_h, lam_raw_a = pred._lambdas(ht, au)
        tgt = min(max(_mov_p_home(pred._elo_of(ht), pred._elo_of(au)), 0.01), 0.99)
        lam_h, lam_a = _anchor_nb_tiesplit(lam_raw_h, lam_raw_a, pred.r_home, pred.r_away, tgt)
        innings_played = max(0.0, float(inning) - 1.0 + (0.5 if str(half).lower() == "bottom" else 0.0))
        state = GameState("mlb", innings_played * 20.0, int(home_score), int(away_score),
                          pregame_params={"lam_home": lam_h, "lam_away": lam_a,
                                         "r_home": pred.r_home, "r_away": pred.r_away},
                          extra={"innings_played": innings_played})
        out = get_repricer("mlb").reprice(state)
        return out if isinstance(out, dict) else None
    except Exception as exc:  # noqa: BLE001 -- no surface this tick -> honest skip
        logger.debug("inplay_derivative_mlb surface build failed %s/%s: %s", home, away, exc)
        return None


def _capture_row(gid: str, aligned: Dict[str, Any], ts: str,
                 state_summary: Dict[str, Any], grade_dir: Optional[Path]) -> None:
    import json
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_DERIV_DIR
    path = _lg._grade_path(SPORT, gid, base)
    row = {"ts": ts, "market_type": aligned["market_type"], "line": aligned["line"],
          "side": aligned["logical_side"], "market_prob": aligned["market_prob"],
          "model_prob": aligned["model_prob"], "state_summary": state_summary,
          "edge_claimed": False}
    _lg._append_atomic(path, json.dumps(row, ensure_ascii=True))


def poll_once(*, fetch_fn: Optional[FetchFn] = None,
             state_fn: Optional[StateFn] = None,
             surface_fn: Optional[SurfaceFn] = None,
             grade_dir: Optional[Path] = None,
             ledger_path: Optional[Path] = None,
             heartbeat_path: Optional[Path] = None,
             now: Optional[datetime] = None) -> Dict[str, Any]:
    """ONE measurement tick: capture every liquid MLB total/spread pair, gate + paper-
    place the ones that clear, and stamp the heartbeat. UNITS only. Never raises."""
    fetch = fetch_fn or _default_fetch
    st_fn = state_fn or _default_state
    surf_fn = surface_fn or _default_surface
    nowdt = now or datetime.now(timezone.utc)
    ts = _utc_iso()

    n_captured = n_bets = 0
    skip_by_reason: Dict[str, int] = {}
    cache: Dict[str, Any] = {}

    def _skip(reason: str) -> None:
        skip_by_reason[reason] = skip_by_reason.get(reason, 0) + 1

    try:
        ticks = fetch(SPORT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("inplay_derivative_mlb fetch error: %s", exc)
        ticks = []
    deriv_ticks = [t for t in ticks if isinstance(t, dict)
                   and str(t.get("market_type")) in ("total", "spread")]
    by_game: Dict[str, List[Dict[str, Any]]] = {}
    for t in deriv_ticks:
        by_game.setdefault(str(t.get("game_id") or ""), []).append(t)

    for gid, gticks in by_game.items():
        if not gid:
            _skip("no_game_id")
            continue
        state = st_fn(SPORT, gticks, gid, nowdt, cache)
        if not isinstance(state, dict):
            _skip("no_live_state")
            continue
        home = str(state.get("home_display") or state.get("home") or "")
        away = str(state.get("away_display") or state.get("away") or "")
        hs, aws = state.get("home_score"), state.get("away_score")
        inning, half = state.get("inning"), state.get("half")
        if not home or not away or hs is None or aws is None or inning is None:
            _skip("incomplete_state")
            continue
        surface = surf_fn(home, away, int(hs), int(aws), int(inning), str(half or "top"))
        if surface is None:
            _skip("no_surface")
            continue
        state_summary = {"home": home, "away": away, "home_score": hs, "away_score": aws,
                         "inning": inning, "half": half}
        for tick in gticks:
            aligned = _align.align_tick(tick, surface, home, away)
            if aligned is None:
                _skip("no_coverage_or_no_side_match")
                continue
            _capture_row(gid, aligned, ts, state_summary, grade_dir)
            n_captured += 1
            ev = _sig.evaluate(
                model_prob=aligned["model_prob"], yes_home_prob=aligned["market_prob"],
                yes_away_prob=None, obtainable_decimal=None,
                calibration_justified=True, is_liquid=True, is_fresh=True,
                clv_is_proxy=True, min_ev=None)  # STRICT floor day one -- no relaxed tier C
            if ev["action"] != "bet":
                _skip(ev.get("reason") or "below_floor")
                continue
            from scripts.platformkit.execution import ingame_exec_gate as _exec_gate
            gr = _exec_gate.evaluate_placement(ev, tick, ticker=tick.get("ticker"), now=nowdt)
            if gr["suppress"]:
                _skip(gr["reason"] or "exec_gate")
                continue
            market_label = _align.market_key(
                aligned["market_type"], aligned["line"],
                "over" if ev["side"] == "home" and aligned["market_type"] == "total"
                else ("under" if aligned["market_type"] == "total" else aligned["logical_side"]))
            br = _breaker.allow(market_label, nowdt, ledger_path)
            if not br.get("allowed", True):
                _skip("breaker_capped")
                continue
            _paper.record_ingame_bet(
                SPORT, gid, market_label, ev["side"], float(ev["obtainable_decimal"]),
                model_prob=ev.get("bet_model_prob"),
                # flat declared 1u stake (day-1 rows omitted it -> settled at 0
                # units; outcome/CLV measurement was unaffected)
                stake=1.0, path=ledger_path,
                signal_ts=ts, exec_gate=gr["exec_gate"], exec_depth=gr["exec_depth"])
            n_bets += 1

    from scripts.platformkit.ingame import mlb_deriv_settle as _settle
    settle_summary = _settle.settle_open_bets(ledger_path=ledger_path, grade_dir=grade_dir,
                                              now=nowdt)

    heartbeat = {
        "as_of": ts, "component": HEARTBEAT_COMPONENT, "sport": SPORT,
        "n_games": len(by_game), "n_captured": n_captured, "n_bets": n_bets,
        "skip_by_reason": skip_by_reason, "settled": settle_summary,
        "measurement_only": True, "executed": False, "edge_claimed": False,
        "units": "probability",
        "_honest_note": (
            "MLB in-play totals/run-line derivative channel. Pairs Kalshi liquid "
            "total/spread ticks with the negbinom repricer surface; captures ALWAYS "
            "run, gate is the SAME strict floor as the moneyline channel. Paper only, "
            "no $ anywhere, edge_claimed=False."),
    }
    _write_heartbeat(heartbeat, heartbeat_path)
    return heartbeat


def _write_heartbeat(hb: Dict[str, Any], path: Optional[Path]) -> None:
    import json
    target = Path(path) if path is not None else DEFAULT_HEARTBEAT
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(hb, ensure_ascii=True), encoding="ascii")
        os.replace(tmp, target)
    except Exception as exc:  # noqa: BLE001 -- heartbeat write must never sink the loop
        logger.warning("inplay_derivative_mlb heartbeat write failed: %s", exc)


__all__ = ["poll_once", "DEFAULT_DERIV_DIR", "DEFAULT_HEARTBEAT", "DEFAULT_LOCK",
           "HEARTBEAT_COMPONENT", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC"]
