"""scripts.platformkit.live_edge.paper.run_bridge -- runs the full PAPER-
BRIDGE chain end-to-end on (a) a labelled synthetic fixture (proves
correctness) and (b) the real on-disk soccer/soccer_intl shadow rows (proves
resolution rate on a real slice), then writes
data/omni/live_edge/paper/PAPER_BRIDGE_REPORT.md.

Chain proven: shadow prediction row -> resolve_identity (event_key + entry
price recovered from the row's own capture provenance) -> bridge.select
(divergence gate) -> clv_ledger.record_bet (the EXISTING paper-bet ledger,
reused) -> clv_scoreboard.scoreboard (the EXISTING CLV readout, reused).

Real-slice grading is honestly near-zero: these games have not settled, so
clv_scoreboard (which only aggregates status=='settled' rows) reports "no
settled bets yet" -- a SUCCESS per the CLV discipline (0 gradeable is an
honest state, not a failure), not a defect in this bridge.

INVARIANTS: stdlib + clv_ledger/clv_scoreboard (import only) + this lane's own
paper/ modules; ASCII; <=300 LOC; writes ONLY under
data/omni/live_edge/paper/ (never the real data/frontend/clv_ledger.jsonl).

Run: cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.live_edge.paper.run_bridge
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

from scripts.platformkit import clv_ledger
from scripts.platformkit.clv import clv_scoreboard
from scripts.platformkit.live_edge.paper import bridge
from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SHADOW_PATH = _REPO_ROOT / "data" / "omni" / "live_edge" / "shadow" / "2026-07-14.jsonl"
_PAPER_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "paper"
_PAPER_LEDGER = _PAPER_DIR / "paper_ledger.jsonl"
_REPORT_PATH = _PAPER_DIR / "PAPER_BRIDGE_REPORT.md"
_MIN_RESOLUTION_RATE = 0.95


def _load_shadow_rows(path: pathlib.Path = _SHADOW_PATH, sports=("soccer", "soccer_intl")
                      ) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("sport") in sports:
            rows.append(r)
    return rows


def run_synthetic_fixture(tmp_dir: pathlib.Path) -> Dict[str, Any]:
    """Labelled synthetic fixture: one hand-built line_history capture record
    + its matching shadow row, run through the FULL chain (resolve ->
    select -> record -> settle -> scoreboard). Proves correctness on known
    inputs, independent of any real-data resolution rate."""
    sport, date, game_id = "soccer_fixture", "2026-07-20", "SYN0001"
    lh_dir = tmp_dir / "line_history"
    (lh_dir / sport).mkdir(parents=True, exist_ok=True)
    devig = 0.60
    (lh_dir / sport / f"{date}.jsonl").write_text(
        json.dumps({"sport": sport, "game_id": game_id, "home": "Synthetic United",
                     "away": "Fixture City", "market_type": "moneyline", "side": "home",
                     "line": None, "odds": 1.8, "book": "fixture_book",
                     "devigged_prob": devig, "captured_at": f"{date}T00:00:06+00:00",
                     "commence_time": f"{date}T19:00Z"}) + "\n",
        encoding="utf-8")
    shadow_row = {"book": "fixture_book", "conditioned_pred": 0.70, "edge_claimed": False,
                  "game": game_id, "is_clv_suspect": None, "market": "pregame.moneyline",
                  "market_price": devig, "mechanism_applied": "fixture_mech", "sport": sport,
                  "ts": f"{date}T12:00:00+00:00", "unconditioned_pred": devig}

    identity = resolve_identity(shadow_row, line_history_dir=lh_dir)
    checks = {"identity_resolved": identity is not None}
    if identity is None:
        return {"checks": checks, "pass": False}
    ek = identity["event_key"]
    checks["event_key_correct"] = (
        ek.sport == sport and ek.date == date
        and ek.home == "soccer_fixture:united" and ek.away == "soccer_fixture:city"
        and ek.market_family == "moneyline")
    checks["selected"] = bridge.select(shadow_row, threshold=0.05)  # |0.70-0.60|=0.10 >= 0.05

    ledger_path = tmp_dir / "paper_ledger_fixture.jsonl"
    result = bridge.run_bridge_row(shadow_row, threshold=0.05, path=ledger_path, line_history_dir=lh_dir)
    checks["recorded"] = result["status"] == "recorded"
    bet = result.get("bet")
    checks["bet_channel_tagged"] = bool(bet) and bet.get("channel") == bridge.CHANNEL_LIVE_EDGE_PAPER
    checks["bet_side_home"] = bool(bet) and bet.get("side") == "home"

    settled = None
    if bet is not None:
        # Synthetic close: home closed shorter (fair prob ~0.65) -- proves the
        # settle+scoreboard leg of the chain on a KNOWN, labelled outcome.
        settled = clv_ledger.settle_closing_line(bet, closing_decimal_home=1.54, closing_decimal_away=2.9)
        clv_ledger.append_settlement(settled, path=ledger_path)
    checks["settled_clv_computed"] = settled is not None and settled.get("clv_pct") is not None

    board = clv_scoreboard.scoreboard(ledger=clv_ledger.load_ledger(path=ledger_path))
    checks["scoreboard_sees_settled_bet"] = board["total_settled"] >= 1

    return {"checks": checks, "pass": all(checks.values()), "board": board}


def run_real_slice() -> Dict[str, Any]:
    """The real on-disk soccer/soccer_intl shadow rows -> resolution rate,
    selection/record outcomes, and a provisional scoreboard readout (honestly
    ~0 settled -- these games have not closed)."""
    rows = _load_shadow_rows()
    _PAPER_DIR.mkdir(parents=True, exist_ok=True)
    if _PAPER_LEDGER.exists():
        _PAPER_LEDGER.unlink()  # idempotent re-run of this report generator
    statuses: Dict[str, int] = {}
    sample_bet = None
    for r in rows:
        out = bridge.run_bridge_row(r, path=_PAPER_LEDGER)
        statuses[out["status"]] = statuses.get(out["status"], 0) + 1
        if out["status"] == "recorded" and sample_bet is None:
            sample_bet = out["bet"]
    n_total = len(rows)
    n_resolved = n_total - statuses.get("ungradeable_identity", 0)
    rate = (n_resolved / n_total) if n_total else None
    board = clv_scoreboard.scoreboard(ledger=clv_ledger.load_ledger(path=_PAPER_LEDGER))
    return {
        "n_total": n_total, "n_resolved": n_resolved,
        "resolution_rate": rate, "statuses": statuses,
        "meets_95pct_bar": (rate is not None and rate >= _MIN_RESOLUTION_RATE),
        "sample_bet": sample_bet, "scoreboard": board,
    }


def render_report(synthetic: Dict[str, Any], real: Dict[str, Any]) -> str:
    lines = ["# PAPER-BRIDGE report", "", "## Synthetic fixture (labelled correctness)"]
    for k, v in synthetic["checks"].items():
        lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    lines.append(f"OVERALL: {'PASS' if synthetic['pass'] else 'FAIL'}")
    lines.append("")
    lines.append("## Real slice: on-disk soccer/soccer_intl shadow rows, 2026-07-14")
    lines.append(f"n_total={real['n_total']} n_resolved={real['n_resolved']} "
                 f"resolution_rate={real['resolution_rate']}")
    lines.append(f"meets >=95% bar: {real['meets_95pct_bar']}")
    lines.append(f"status breakdown: {real['statuses']}")
    lines.append("")
    lines.append("## Provisional scoreboard readout (paper_live_edge channel, this ledger only)")
    board = real["scoreboard"]
    lines.append(f"total_settled={board['total_settled']} "
                 f"total_measurable={board['total_measurable']} verdict={board['verdict']}")
    lines.append("")
    lines.append("edge_claimed=False throughout. Same-book basis only. "
                 "0 settled is an honest state (games have not closed), not a defect.")
    return "\n".join(lines)


def main() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        synthetic = run_synthetic_fixture(pathlib.Path(tmp))
    real = run_real_slice()
    report = render_report(synthetic, real)
    print(report)
    _PAPER_DIR.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nwrote {_REPORT_PATH}")
    return 0 if synthetic["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_synthetic_fixture", "run_real_slice", "render_report"]
