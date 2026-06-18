"""scripts.platformkit.prop_loop -- UNATTENDED paper-accrual loop for World Cup props.

One self-contained tick that lets REAL outcomes judge which prop edges are real:

  1. (optional) ingest realized post-match player stats for recent dates so newly
     -final World Cup matches land in espn_player_stats.parquet (the settlement
     source). A feed failure is GUARDED -- it never aborts the tick.
  2. refresh the board/snapshot (one compute per cycle) via snapshot_writer.write_all.
  3. record the TRUSTWORTHY edges (reliable + ev_flag=="ok") to the paper ledger.
     With the prop_paper dedup fix (key = match/player/stat/line/side, NOT as_of)
     only NEW props are added even though the board is rebuilt every cycle.
  4. grade still-open bets whose match is now final in the refreshed parquet.
  5. summarize per-stat + overall {n, hit_rate, paper_roi, mean_model_p_over}.

PAPER ONLY -- no real-money path; the ledger is the human's own paper record.
HONESTY: calibration is the yardstick; paper_roi is small-N P&L at the taken price.
CLV-vs-close is NOT computed here (no closing-line capture) -- no $-edge is claimed.

Every stage is GUARDED: one failing feed (e.g. ESPN down) degrades that stage and
the tick still returns a dict. run_tick / run_forever / main NEVER raise. All seams
are injectable so tests run fully offline.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_loop.py -q
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _default_dates() -> List[str]:
    """Today + yesterday (UTC) as YYYYMMDD -- catches matches that just went final."""
    today = dt.datetime.now(dt.timezone.utc).date()
    return [
        today.strftime("%Y%m%d"),
        (today - dt.timedelta(days=1)).strftime("%Y%m%d"),
    ]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _guard(name: str, fn: Callable[[], Any], health: Dict[str, str]) -> Any:
    """Run *fn* GUARDED -- record health[name]=ok|error:<Type> and return its result
    or None on failure so one broken stage never sinks the tick."""
    try:
        result = fn()
        health[name] = "ok"
        return result
    except Exception as exc:  # noqa: BLE001 -- a stage failure must not kill the tick
        logger.warning("prop_loop stage %s failed: %s", name, exc)
        health[name] = "error: %s" % type(exc).__name__
        return None


def run_tick(
    *,
    sports: Sequence[str] = ("soccer_intl", "mlb"),
    dates: Optional[Sequence[str]] = None,
    ingest: bool = True,
    writer: Optional[Callable[..., Any]] = None,
    recorder: Optional[Callable[..., Dict[str, Any]]] = None,
    grader: Optional[Callable[..., Dict[str, Any]]] = None,
    summarizer: Optional[Callable[..., Dict[str, Any]]] = None,
    board_builder: Optional[Callable[[str], Dict[str, Any]]] = None,
    ingester: Optional[Callable[..., Any]] = None,
    ledger_path: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run ONE unattended paper-accrual tick and return an assembled status dict.

    Stages (each GUARDED -- a raise is caught, logged, and the tick still returns):
      ingest -> refresh-board -> record (per sport) -> grade -> summarize.

    All seams are injectable so the test runs network-free:
      ingester  := ingest_espn_players.ingest_range
      writer    := snapshot_writer.write_all
      board_builder := prop_edge.build_prop_board
      recorder  := prop_paper.record_board
      grader    := prop_paper.grade_open
      summarizer:= prop_paper.prop_summary

    Returns {as_of, recorded, graded, summary, sources}. NEVER raises.
    """
    sport_list = list(sports)
    use_dates = list(dates) if dates is not None else _default_dates()
    health: Dict[str, str] = {}
    out: Dict[str, Any] = {
        "as_of": _now_iso(),
        "sports": sport_list,
        "dates": use_dates,
        "recorded": 0,
        "graded": 0,
        "summary": None,
        "sources": health,
    }

    # 1. ingest realized stats (guarded; off when ingest=False).
    if ingest:
        ing = ingester
        if ing is None:
            from domains.soccer import ingest_espn_players as _iep
            ing = _iep.ingest_range
        _guard("ingest", lambda: ing(use_dates, leagues=("fifa.world",)), health)
    else:
        health["ingest"] = "skipped"

    # 2. refresh the board/snapshot (one compute per cycle).
    wr = writer
    if wr is None:
        from scripts.platformkit.frontend import snapshot_writer as _sw
        wr = _sw.write_all
    _guard("snapshot", lambda: wr(sport_list), health)

    # 3. record passing edges (dedup fix -> only NEW props added).
    bb = board_builder
    if bb is None:
        from scripts.platformkit.prop_edge import build_prop_board as _bpb
        bb = _bpb
    rec = recorder
    if rec is None:
        from scripts.platformkit.prop_paper import record_board as _rb
        rec = _rb
    # Closing-line capture: log every priced line each tick (guarded). The history
    # accrues up to kickoff so the LAST logged line is the closing-line proxy that
    # prop_paper grading uses to attach CLV-vs-close. Paper-only; no $-edge claim.
    from scripts.platformkit import prop_line_history as _plh
    recorded = 0
    rec_detail: Dict[str, Any] = {}
    for sport in sport_list:
        def _do_record(s: str = sport) -> Dict[str, Any]:
            board = bb(s)
            _guard("lines:%s" % s, lambda: _plh.log_board_lines(board), health)
            return rec(board, only_reliable=True, ledger_path=ledger_path)
        res = _guard("record:%s" % sport, _do_record, health)
        if isinstance(res, dict):
            rec_detail[sport] = res
            recorded += int(res.get("recorded", 0) or 0)
    out["recorded"] = recorded
    out["record_detail"] = rec_detail

    # 4. grade open bets now-final in the refreshed parquet.
    gr = grader
    if gr is None:
        from scripts.platformkit.prop_paper import grade_open as _go
        gr = _go
    g = _guard("grade", lambda: gr(ledger_path=ledger_path), health)
    if isinstance(g, dict):
        out["graded"] = int(g.get("graded", 0) or 0)
        out["grade_detail"] = g

    # 5. summarize per-stat + overall.
    sm = summarizer
    if sm is None:
        from scripts.platformkit.prop_paper import prop_summary as _ps
        sm = _ps
    s = _guard("summary", lambda: sm(ledger_path=ledger_path), health)
    out["summary"] = s if isinstance(s, dict) else None
    return out


def run_forever(
    interval_s: float = 900.0,
    sleep: Callable[[float], Any] = time.sleep,
    max_ticks: Optional[int] = None,
    **kw: Any,
) -> List[Dict[str, Any]]:
    """Loop run_tick every *interval_s* seconds (default 15 min). Each tick AND each
    sleep is guarded so the daemon never dies. *max_ticks* bounds the loop (tests);
    None = run until killed. Returns the list of per-tick dicts produced. Never raises.
    """
    ticks: List[Dict[str, Any]] = []
    count = 0
    while max_ticks is None or count < max_ticks:
        try:
            ticks.append(run_tick(**kw))
        except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders: tick never kills loop
            logger.warning("prop_loop tick crashed: %s", exc)
            ticks.append({"as_of": _now_iso(), "sources": {"tick": "error: %s"
                                                            % type(exc).__name__}})
        count += 1
        if max_ticks is not None and count >= max_ticks:
            break
        try:
            sleep(interval_s)
        except Exception as exc:  # noqa: BLE001 -- a sleep failure must not kill the loop
            logger.warning("prop_loop sleep failed: %s", exc)
    return ticks


def _fmt_summary(summary: Optional[Dict[str, Any]]) -> str:
    """ASCII per-stat + overall summary table from a prop_summary() dict."""
    if not isinstance(summary, dict):
        return "  (no summary)"
    lines: List[str] = []
    hdr = "  %-10s %4s %9s %9s %9s" % ("stat", "n", "hit_rate", "paper_roi", "mean_p")
    lines.append(hdr)

    def _row(name: str, b: Dict[str, Any]) -> str:
        def f(v: Any) -> str:
            return "-" if v is None else ("%.4f" % v if isinstance(v, float) else str(v))
        return "  %-10s %4s %9s %9s %9s" % (
            name[:10], f(b.get("n")), f(b.get("hit_rate")),
            f(b.get("paper_roi")), f(b.get("mean_model_p_over")),
        )

    by_stat = summary.get("by_stat") or {}
    for stat, b in sorted(by_stat.items()):
        if isinstance(b, dict):
            lines.append(_row(stat, b))
    overall = summary.get("overall")
    if isinstance(overall, dict):
        lines.append(_row("OVERALL", overall))
    return "\n".join(lines)


def _print_tick(tick: Dict[str, Any]) -> None:
    print("tick as_of=%s recorded=%s graded=%s" % (
        tick.get("as_of"), tick.get("recorded"), tick.get("graded")))
    print("  sources: %s" % tick.get("sources"))
    print(_fmt_summary(tick.get("summary")))
    summary = tick.get("summary") or {}
    note = summary.get("note") if isinstance(summary, dict) else None
    if note:
        print("  note: %s" % note)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: python -m scripts.platformkit.prop_loop [--once] [--interval 900]
    [--sports soccer_intl] [--no-ingest]. Never raises."""
    ap = argparse.ArgumentParser(
        description="Unattended PAPER prop-accrual loop (no real money).")
    ap.add_argument("--once", action="store_true", help="run a single tick then exit")
    ap.add_argument("--interval", type=float, default=900.0,
                    help="seconds between ticks in --forever mode (default 900)")
    ap.add_argument("--sports", nargs="+", default=["soccer_intl", "mlb"])
    ap.add_argument("--no-ingest", action="store_true",
                    help="skip the realized-stats refresh (offline/replay)")
    args = ap.parse_args(argv)
    try:
        kw = {"sports": tuple(args.sports), "ingest": not args.no_ingest}
        if args.once:
            _print_tick(run_tick(**kw))
            return 0
        for tick in run_forever(interval_s=args.interval, **kw):
            _print_tick(tick)
        return 0
    except Exception as exc:  # noqa: BLE001 -- CLI must never raise
        print("prop_loop error: %s" % type(exc).__name__)
        return 1


__all__ = ["run_tick", "run_forever", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
