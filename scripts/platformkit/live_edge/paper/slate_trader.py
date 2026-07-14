"""scripts.platformkit.live_edge.paper.slate_trader -- arms tennis (+ verifies
soccer/mlb) into the PAPER-BRIDGE chain: odds -> model_prob -> event_key ->
paper-bet -> CLV-ready.

STEP 0 FINDING (documented, changes the literal task instruction -- see
resolve_identity.py for the identity-join precedent this follows): the paper
pipeline that already mints mlb/soccer_intl/wnba/npb/kbo bets into
data/frontend/clv_ledger.jsonl is pm_trading.run_paper_today + paper_autobet
(a SEPARATE, human-gated-adjacent pipeline, out of this lane's OWNS). The
D1-SHADOW feed this lane's bridge.py consumes
(data/omni/live_edge/shadow/<date>.jsonl) has REAL predictions for mlb/nba
but a MARKET-ECHO placeholder for tennis today (conditioned_pred ==
market_price exactly, mechanism_applied=None) -- bridge.select()'s divergence
gate can never fire on that feed for tennis. Root cause = no tennis model was
ever wired into the shadow producer, not a sport allowlist.

This module builds tennis shadow rows FROM SCRATCH each run, using a REAL
model (tennis_model.model_prob, domains.tennis.predictor.TennisPredictor)
joined against the same day's line_history odds capture -- then runs them
through the EXISTING, unmodified chain: resolve_identity -> bridge.select ->
bridge.run_bridge_row (clv_ledger.record_bet reused verbatim). For mlb/
soccer_intl it reads the EXISTING on-disk shadow rows (no model of ours to
add -- their bets already flow via the other pipeline) purely to VERIFY the
SAME identity-resolution path works for them too.

Writes ONLY under data/omni/live_edge/paper/dry_run_<sport>_<date>.jsonl by
default (never the real ledger) -- pass live=True to write the paper ledger
that clv_scoreboard reads (still never data/frontend/clv_ledger.jsonl).

INVARIANTS: import bridge/resolve_identity/event_key/tennis_model/clv_ledger/
clv_scoreboard only, never reimplement any of them; ASCII; <=300 LOC;
edge_claimed=False throughout; quarter-Kelly-consistent stake_units (flat 1.0u
default, same convention record_bet already assumes); a row that cannot
resolve/select/price is an honest accounted status, never a silent drop.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger
from scripts.platformkit.clv import clv_scoreboard
from scripts.platformkit.live_edge.paper import bridge, tennis_model
from scripts.platformkit.live_edge.paper.event_key import market_family_of

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_LINE_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "line_history"
_SHADOW_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "shadow"
_PAPER_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "paper"
_LIVE_LEDGER = _PAPER_DIR / "paper_ledger.jsonl"

STAKE_UNITS_DEFAULT = 1.0  # flat unit, same convention as clv_ledger.record_bet


def _read_jsonl(path: pathlib.Path) -> List[dict]:
    if not path.is_file():
        return []
    out: List[dict] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def build_tennis_shadow_rows(date: str, *, line_history_dir: pathlib.Path = _LINE_HISTORY_DIR,
                              market_type: str = "moneyline") -> List[Dict[str, Any]]:
    """Today's real tennis odds capture -> one shadow row per match, with a
    REAL model_prob (tennis_model) as conditioned_pred. One row per game_id
    (the home-side moneyline tick), freshest (last) capture of the day.
    Matches with no home-side moneyline tick, or where the model returns None,
    are honestly skipped (never fabricated)."""
    rows = _read_jsonl(line_history_dir / "tennis" / f"{date}.jsonl")
    latest_home: Dict[str, dict] = {}
    for r in rows:
        if r.get("market_type") != market_type or r.get("side") != "home":
            continue
        gid = str(r.get("game_id"))
        latest_home[gid] = r  # last write wins -> freshest capture that day

    shadow_rows: List[Dict[str, Any]] = []
    for gid, r in latest_home.items():
        home, away = r.get("home"), r.get("away")
        pred = tennis_model.model_prob(home, away)
        if pred is None or r.get("devigged_prob") is None:
            continue
        shadow_rows.append({
            "sport": "tennis", "game": gid,
            "ts": r.get("captured_at") or f"{date}T00:00:00+00:00",
            "market": f"pregame.{market_family_of(market_type)}",
            "market_price": float(r["devigged_prob"]),
            "conditioned_pred": pred, "unconditioned_pred": float(r["devigged_prob"]),
            "book": r.get("book"), "edge_claimed": False, "is_clv_suspect": None,
            "mechanism_applied": "tennis_elo_platt",
        })
    return shadow_rows


def load_existing_shadow_rows(sport: str, date: str, *,
                               shadow_dir: pathlib.Path = _SHADOW_DIR) -> List[Dict[str, Any]]:
    """Verification path for sports this lane does not model (mlb,
    soccer_intl): pull today's rows straight from the EXISTING D1-SHADOW feed
    this lane's bridge already consumes."""
    rows = _read_jsonl(shadow_dir / f"{date}.jsonl")
    return [r for r in rows if r.get("sport") == sport]


def run_sport_slate(sport: str, date: str, *, threshold: float = bridge.DEFAULT_THRESHOLD,
                     stake_units: float = STAKE_UNITS_DEFAULT, live: bool = False,
                     line_history_dir: pathlib.Path = _LINE_HISTORY_DIR,
                     shadow_dir: pathlib.Path = _SHADOW_DIR) -> Dict[str, Any]:
    """One sport, one day, through the full chain. Returns a status-accounted
    summary: n_total/n_resolved/resolution_rate/n_selected/n_recorded/
    statuses/sample_bet/path. Dry-run (default) writes
    dry_run_<sport>_<date>.jsonl under data/omni/live_edge/paper/; live=True
    writes the shared paper_ledger.jsonl that clv_scoreboard reads -- still
    never the real data/frontend/clv_ledger.jsonl (bridge/record_bet never
    touch that path)."""
    if sport == "tennis":
        rows = build_tennis_shadow_rows(date, line_history_dir=line_history_dir)
    else:
        rows = load_existing_shadow_rows(sport, date, shadow_dir=shadow_dir)

    _PAPER_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _LIVE_LEDGER if live else _PAPER_DIR / f"dry_run_{sport}_{date}.jsonl"
    if out_path.exists():
        out_path.unlink()  # idempotent re-run

    statuses: Dict[str, int] = {}
    sample_bet: Optional[Dict[str, Any]] = None
    for r in rows:
        out = bridge.run_bridge_row(r, threshold=threshold, stake_units=stake_units,
                                     path=out_path, line_history_dir=line_history_dir)
        statuses[out["status"]] = statuses.get(out["status"], 0) + 1
        if out["status"] == "recorded" and sample_bet is None:
            sample_bet = out["bet"]

    n_total = len(rows)
    n_resolved = n_total - statuses.get("ungradeable_identity", 0)
    n_selected = statuses.get("recorded", 0) + statuses.get("ungradeable_price", 0)
    board = clv_scoreboard.scoreboard(ledger=clv_ledger.load_ledger(path=out_path))
    return {
        "sport": sport, "date": date, "n_total": n_total, "n_resolved": n_resolved,
        "resolution_rate": (n_resolved / n_total) if n_total else None,
        "n_selected": n_selected, "n_recorded": statuses.get("recorded", 0),
        "statuses": statuses, "sample_bet": sample_bet, "scoreboard": board,
        "path": str(out_path), "live": live,
    }


def render_report(results: List[Dict[str, Any]]) -> str:
    lines = ["# TENNIS-WIRE slate report (dry-run unless noted)", ""]
    for r in results:
        lines.append(f"## {r['sport']} {r['date']}")
        lines.append(f"n_total={r['n_total']} n_resolved={r['n_resolved']} "
                     f"resolution_rate={r['resolution_rate']}")
        lines.append(f"n_selected={r['n_selected']} n_recorded={r['n_recorded']} "
                     f"statuses={r['statuses']}")
        lines.append(f"path={r['path']} live={r['live']}")
        if r["sample_bet"]:
            lines.append(f"sample_bet={json.dumps(r['sample_bet'])}")
        lines.append("")
    lines.append("edge_claimed=False throughout. Same-book basis only. "
                 "0/low n_recorded is honest wiring-proof, not a defect: "
                 "these matches have not settled, and the divergence gate is "
                 "a report-only hook, not a validated +EV trigger.")
    return "\n".join(lines)


def main() -> int:
    import datetime as dt
    date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    results = [run_sport_slate(sp, date) for sp in ("tennis", "mlb", "soccer_intl")]
    report = render_report(results)
    print(report)
    out = _PAPER_DIR / "SLATE_TRADER_REPORT.md"
    _PAPER_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_tennis_shadow_rows", "load_existing_shadow_rows", "run_sport_slate",
           "render_report", "STAKE_UNITS_DEFAULT"]
